"""Shared types for the MIES patch-seq stimset port.

Units at the analysis-function boundary follow MIES, not ACQ4: time in ms, current in pA, voltage in
mV, resistance in MOhm. Sweep time t=0 is the first DA sample (it includes the inserted test pulse and
onset delays). The runner converts to and from SI.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Mapping, Optional, Sequence

import numpy as np

ClampMode = Literal['VC', 'IC']

# MIES WAVEBUILDER_MIN_SAMPINT; stimsets are defined on this grid and SamplingMultiplier divides 200 kHz.
MIN_SAMPLE_INTERVAL = 0.005  # ms


@dataclass(frozen=True)
class Epoch:
    """One named time span of a sweep.

    Names follow MIES short names: ``E<i>`` stimset epoch i, ``TP``/``TP_B0``/``TP_P``/``TP_B1`` the
    inserted test pulse, ``U_*`` user epochs added by an analysis function (e.g. ``U_TP0_P``, ``U_BLS0``).
    ``amplitude`` is in DA units (pA in IC, mV in VC), already multiplied by DAScale; NaN when undefined.
    """

    name: str
    start: float  # ms
    end: float  # ms
    amplitude: float = float('nan')
    tags: Mapping[str, str] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


class EpochTable(Sequence[Epoch]):
    """Ordered epochs of one sweep; lookups by name raise KeyError when absent."""

    def __init__(self, epochs: Sequence[Epoch] = ()):
        self._epochs: list[Epoch] = list(epochs)

    def __getitem__(self, i):
        return self._epochs[i]

    def __len__(self) -> int:
        return len(self._epochs)

    def __iter__(self) -> Iterator[Epoch]:
        return iter(self._epochs)

    def __repr__(self) -> str:
        return f"EpochTable({self._epochs!r})"

    def add(self, *epochs: Epoch) -> None:
        self._epochs.extend(epochs)

    def get(self, name: str) -> Epoch:
        for ep in self._epochs:
            if ep.name == name:
                return ep
        raise KeyError(name)

    def has(self, name: str) -> bool:
        return any(ep.name == name for ep in self._epochs)

    def withPrefix(self, prefix: str) -> list[Epoch]:
        """Return epochs whose name starts with *prefix*, sorted by start time."""
        return sorted((ep for ep in self._epochs if ep.name.startswith(prefix)), key=lambda ep: ep.start)

    def stimsetEpoch(self, i: int) -> Epoch:
        return self.get(f'E{i}')

    def copy(self) -> EpochTable:
        return EpochTable(self._epochs)


@dataclass(frozen=True)
class TestPulseSettings:
    """The test pulse MIES inserts at the start of every sweep ("Insert TP")."""

    pulseDuration: float  # ms
    baselineFraction: float  # fraction of the whole TP before (and after) the pulse
    amplitudeVC: float  # mV
    amplitudeIC: float  # pA


@dataclass
class SweepData:
    """AD and DA traces of one sweep, complete or in progress.

    ``data`` and ``command`` always have the full planned length; only ``data[:numValid]`` is acquired
    and settled, the rest is NaN. ``command`` is what was output (stimset x DAScale plus inserted TP),
    excluding holding, after any mid-sweep zeroing. Successive ``midSweep`` calls may receive the same
    arrays filled in place; copy anything kept across calls.
    """

    sweep: int  # experiment-wide sweep number
    clampMode: ClampMode
    sampleInterval: float  # ms
    data: np.ndarray  # pA (VC) or mV (IC)
    command: np.ndarray  # mV (VC) or pA (IC)
    numValid: int
    epochs: EpochTable
    dascale: float
    stoppedEarly: bool = False
    commandZeroedAt: Optional[float] = None  # ms; when a ZeroCommand took effect

    @property
    def complete(self) -> bool:
        return self.numValid >= len(self.data)

    @property
    def acquiredDuration(self) -> float:
        return self.numValid * self.sampleInterval

    def index(self, t: float) -> int:
        """Return the sample index for sweep time *t* (ms): ``trunc(t/dt)``, snapped within 1e-6 points."""
        x = t / self.sampleInterval
        r = round(x)
        return int(r) if abs(x - r) < 1e-6 else int(x)


@dataclass
class AmplifierSettings:
    """Amplifier and clamp-device changes requested by an analysis function; None leaves a setting alone.

    The runner snapshots every setting it changes and restores it at the end of the requested scope.
    """

    holdingEnabled: Optional[bool] = None
    holding: Optional[float] = None  # pA (IC) or mV (VC)
    bridgeBalanceEnabled: Optional[bool] = None
    bridgeBalance: Optional[float | Literal['auto']] = None  # MOhm
    capNeutralizationEnabled: Optional[bool] = None
    capNeutralization: Optional[float] = None  # pF
    pipetteOffset: Optional[Literal['auto']] = None
    besselFilter: Optional[float] = None  # Hz; primary output low-pass
    autobiasEnabled: Optional[bool] = None
    autobiasTarget: Optional[float] = None  # mV

    def changes(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if getattr(self, f.name) is not None}


@dataclass
class SetConfig:
    """Returned by ``preSet``: acquisition settings for every sweep of the set."""

    clampMode: ClampMode
    sampleInterval: float  # ms; MIN_SAMPLE_INTERVAL x SamplingMultiplier
    insertTestPulse: bool = True
    userOnsetDelay: float = 0.0  # ms, before the stimset (after the inserted TP)
    terminationDelay: float = 0.0  # ms, after the stimset
    amplifier: AmplifierSettings = field(default_factory=AmplifierSettings)  # restored at set end
    runAmplifier: AmplifierSettings = field(default_factory=AmplifierSettings)  # restored at run end


@dataclass
class SweepConfig:
    """Returned by ``preSweep``: settings for the next sweep."""

    dascale: float  # pA (IC) or mV (VC) per stimset unit
    userEpochs: list[Epoch] = field(default_factory=list)
    iti: Optional[float] = None  # s before this sweep; None uses the stimset ITI


@dataclass(frozen=True)
class EarlyStop:
    """``midSweep`` result: stop acquiring now and keep what was acquired."""

    reason: str
    # s added to the following ITI, which is counted from the end of acquired data (MIES
    # ANALYSIS_FUNC_RET_REPURP_TIME: includes the unacquired remainder of the sweep)
    extraIti: float = 0.0


@dataclass(frozen=True)
class ZeroCommand:
    """``midSweep`` result: stop stimulating for the rest of the sweep while recording continues."""

    reason: str


MidSweepAction = Optional[EarlyStop | ZeroCommand]

SetAction = Literal['continue', 'endSetPassed', 'endSetFailed', 'abort']


@dataclass
class SweepDecision:
    """Returned by ``postSweep``.

    ``action``: 'continue' acquires the next sweep of the set; 'endSetPassed'/'endSetFailed' end the set
    (``postSet`` still runs); 'abort' ends the set and the chain.
    """

    sweepPassed: bool
    action: SetAction
    extraIti: float = 0.0  # s
    iti: Optional[float] = None  # s; replaces the ITI before the next sweep
    reason: str = ''


@dataclass
class SetResult:
    """Returned by ``postSet``."""

    passed: bool
    nextStimset: Optional[str] = None  # MIES NextStimSetName, applied by the chain runner on pass
    nextIndexingEnd: Optional[str] = None  # MIES NextIndexingEndStimSetName
    runAmplifier: AmplifierSettings = field(default_factory=AmplifierSettings)  # kept until run end
    values: dict[str, Any] = field(default_factory=dict)


class AbortSet(Exception):
    """Raised by an analysis function when the set cannot run (MIES: event handler returned 1)."""
