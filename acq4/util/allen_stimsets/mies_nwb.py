"""Reader for MIES-recorded NWB files: sweeps, labnotebook, epochs and stimset cycles.

Units follow the analysis-function boundary (see ``core``): ms, pA, mV. Recorded AD data are pA (VC)
or mV (IC). Recorded DA data are the output command (mV in VC, pA in IC) including DAScale and the
inserted test pulse but excluding holding. MIES marks an early-stopped sweep by NaN-filling AD and DA
after the last acquired sample and adding an ``UA`` (Unacquired) epoch; the arrays keep the planned
length.
"""

from __future__ import annotations

import math
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import h5py
import numpy as np

from .core import ClampMode, Epoch, EpochTable, SweepData

if TYPE_CHECKING:
    from .stimset import StimsetDef

NUM_HEADSTAGES = 8
INDEP = 8  # labnotebook layer for headstage-independent entries

# entrySourceType values (MIES DataAcqModes); AUTO tries DATA_ACQUISITION_MODE, then UNKNOWN_MODE
UNKNOWN_MODE = None
DATA_ACQUISITION_MODE = 0
TEST_PULSE_MODE = 1
AUTO = 'auto'

DQ_STOP_REASON_DAQ_BUTTON = 0x1

# MIES 'Digitizer Hardware Type' -> largest DA output in V: ITC 32767 counts at 3200 counts/V, NI 10 V,
# Sutter headstage output 1 V
_DAC_MAX_VOLTS = {0: 32767 / 3200, 1: 10.0, 2: 1.0}

# MIES analysis function name -> labnotebook key prefix (after "USER_")
LBN_PREFIX = {
    'PSQ_PipetteInBath': 'Pipette in Bath',
    'PSQ_SealEvaluation': 'Seal evaluation',
    'PSQ_TrueRestingMembranePotential': 'True Rest Memb.',
    'PSQ_AccessResistanceSmoke': 'Access Res. Smoke',
    'PSQ_DAScale': 'DA Scale',
    'PSQ_SquarePulse': 'Squ. Pul.',
    'PSQ_Rheobase': 'Rheobase',
    'PSQ_Ramp': 'Ramp',
    'PSQ_Chirp': 'Chirp',
}

_EPOCH_TYPES = {
    'Square pulse': 'square',
    'Ramp': 'ramp',
    'Noise': 'noise',
    'Sin Wave': 'sin',
    'Saw tooth': 'saw',
    'Pulse Train': 'pulseTrain',
    'PSC': 'psc',
    'Load custom wave': 'custom',
    'Combine': 'combine',
}


def userKey(miesName: str, name: str) -> str:
    """Return the labnotebook key ``USER_<prefix> <name>`` for MIES function *miesName*."""
    return f'USER_{LBN_PREFIX[miesName]} {name}'


def decodeParams(encoded: str) -> dict[str, Any]:
    """Decode a MIES analysis-parameter string (``name:type=value,...``).

    Returns float for 'variable', str for 'string', list[float] for 'wave' and list[str] for
    'textwave'; strings are percent-decoded as MIES does.
    """
    out: dict[str, Any] = {}
    for item in encoded.split(','):
        if not item:
            continue
        nameType, _, value = item.partition('=')
        name, _, typ = nameType.partition(':')
        if typ == 'variable':
            out[name] = _igorNum(value)
        elif typ == 'string':
            out[name] = urllib.parse.unquote(value)
        elif typ == 'wave':
            out[name] = [_igorNum(v) for v in value.split('|') if v != '']
        elif typ == 'textwave':
            out[name] = [urllib.parse.unquote(v) for v in value.split('|') if v != '']
        else:
            raise ValueError(f"unknown analysis parameter type {typ!r} in {item!r}")
    return out


def _igorNum(s: str) -> float:
    try:
        return float(s)
    except ValueError:
        return float('nan')  # Igor str2num of a non-number


def _str(x) -> str:
    return x.decode('utf-8') if isinstance(x, bytes) else str(x)


class Labnotebook:
    """One MIES labnotebook (numerical or textual) with MIES ``GetLastSetting`` semantics.

    Values are indexed ``[row, key, layer]``; layers 0-7 are headstages, 8 is headstage independent.
    Key lookups are case-insensitive, as in MIES.
    """

    def __init__(self, keys: np.ndarray, values: np.ndarray):
        self.text = values.dtype.kind in 'OSU'
        self.names = [_str(k) for k in keys[0]]
        self.units = [_str(u) for u in keys[1]]
        self._index = {n.lower(): i for i, n in enumerate(self.names)}
        if self.text:
            values = np.vectorize(_str, otypes=[object])(values) if values.size else values
        self.values = values
        sweepCol = self._index['sweepnum']
        self._sweeps = self._num(values[:, sweepCol, 0])
        srcCol = self._index.get('entrysourcetype')
        self._sourceRaw = None if srcCol is None else values[:, srcCol, 0]
        self._source = None if srcCol is None else self._num(self._sourceRaw)
        self._tpPeak = self._index.get('tp peak resistance')
        self._tpDuration = self._index.get('tp pulse duration')

    def _num(self, col) -> np.ndarray:
        if not self.text:
            return np.asarray(col, dtype=float)
        return np.array([_igorNum(v) if v != '' else np.nan for v in col], dtype=float)

    def has(self, key: str) -> bool:
        return key.lower() in self._index

    def column(self, key: str) -> int:
        return self._index[key.lower()]

    def unit(self, key: str) -> str:
        return self.units[self.column(key)]

    def _valid(self, row: int, col: int) -> bool:
        v = self.values[row, col]
        if self.text:
            return any(x != '' for x in v)
        return bool(np.any(~np.isnan(v)))

    def _findRange(self, sweep: int, sourceType: Optional[int]) -> Optional[tuple[int, int]]:
        """Return (first, last) rows of the newest consecutive block of *sweep* rows (MIES FindRange)."""
        idx = np.nonzero(self._sweeps == sweep)[0]
        if len(idx) == 0:
            return None
        if sourceType is not None and self._source is not None:
            lo, hi = idx[0], idx[-1]
            src = np.nonzero(self._source[lo : hi + 1] == sourceType)[0] + lo
            if len(src):
                idx = np.intersect1d(idx, src)
            elif sourceType == DATA_ACQUISITION_MODE and not self.text:
                for col in (self._tpPeak, self._index.get('tp baseline fraction')):
                    if col is not None:
                        tp = (
                            np.nonzero(np.any(~np.isnan(self.values[lo : hi + 1, col]), axis=1))[0]
                            + lo
                        )
                        idx = np.setdiff1d(idx, tp)
            if len(idx) == 0:
                return None
        first = last = idx[-1]
        for index in idx[-2::-1]:
            if index < first - 1 and self._source is not None:
                gap = self._sourceRaw[index + 1 : first]
                if self.text:
                    if any(g != '' for g in gap):
                        break
                elif np.any(~np.isnan(np.asarray(gap, dtype=float))):
                    break
            first = index
        return first, last

    def lastSetting(self, sweep: int, key: str, sourceType: Optional[int] = DATA_ACQUISITION_MODE):
        """Return the 9-layer row of the newest entry of *key* for *sweep*, or None (MIES GetLastSetting).

        The row is the last one (within the sweep's newest block of rows, filtered by *sourceType*) where
        any layer is set; layers that row leaves empty are NaN/'' even if older rows set them.
        """
        if not self.has(key):
            return None
        col = self.column(key)
        rng = self._findRange(sweep, sourceType)
        if rng is None:
            return None
        first, last = rng
        i = last
        while i >= first:
            if self._sweeps[i] != sweep and not np.isnan(self._sweeps[i]):
                i -= 1
                continue
            if sourceType is not None and self._source is not None:
                src = self._source[i]
                if np.isnan(src):
                    if self.text:
                        if sourceType == TEST_PULSE_MODE:
                            return None
                    else:
                        block, length = self._guessBlock(i)
                        if sourceType == DATA_ACQUISITION_MODE and block == TEST_PULSE_MODE:
                            i -= 1 + length
                            continue
                        if sourceType == TEST_PULSE_MODE and block == DATA_ACQUISITION_MODE:
                            return None
                elif src != sourceType:
                    i -= 1
                    continue
            if self._valid(i, col):
                return self.values[i, col].copy()
            i -= 1
        return None

    def _guessBlock(self, i: int) -> tuple[int, int]:
        """Classify a row without entrySourceType as TP or DAQ the way MIES does; returns (mode, extra rows)."""
        if self._tpPeak is None:
            return DATA_ACQUISITION_MODE, 0
        if self._tpDuration is not None and self._valid(i, self._tpDuration):
            if i > 0 and self._valid(i - 1, self._tpPeak):
                return TEST_PULSE_MODE, 1
            return DATA_ACQUISITION_MODE, 0
        if self._valid(i, self._tpPeak):
            return TEST_PULSE_MODE, 0
        return DATA_ACQUISITION_MODE, 0

    def sweepsWith(self, key: str) -> list[int]:
        """Return the sorted sweep numbers that have any entry for *key* (MIES GetSweepsWithSetting)."""
        if not self.has(key):
            return []
        col = self.column(key)
        rows = [
            i
            for i in range(len(self._sweeps))
            if self._valid(i, col) and not np.isnan(self._sweeps[i])
        ]
        return sorted({int(self._sweeps[i]) for i in rows})


@dataclass
class MiesSweep:
    """One headstage of one recorded sweep. Data arrays load on first access."""

    recording: 'MiesRecording' = field(repr=False)
    sweep: int
    headstage: int
    adChannel: int
    daChannel: int
    stimset: str
    clampMode: ClampMode
    clampModeCode: int  # MIES: 0 VC, 1 IC, 2 I=0 (mapped to 'IC')
    sampleInterval: float  # ms
    dascale: float  # Stim Scale Factor, pA (IC) or mV (VC) per stimset unit
    setSweepIndex: int  # Set Sweep Count: stimset sweep (column) played
    sci: int  # Stimset Acq Cycle ID
    rac: int  # Repeated Acq Cycle ID
    analysisFunction: Optional[str]  # MIES generic function name
    params: dict[str, Any]
    numPoints: int  # planned length
    numValid: int  # acquired samples
    holding: float  # pA (IC) or mV (VC); 0 when holding is disabled
    daqStopReason: Optional[int]  # set on the sweep after which DAQ stopped

    @property
    def stoppedEarly(self) -> bool:
        return self.numValid < self.numPoints

    @property
    def stoppedByUser(self) -> bool:
        """True when DAQ was stopped with the DAQ button after this sweep (or during it)."""
        return self.daqStopReason is not None and bool(
            self.daqStopReason & DQ_STOP_REASON_DAQ_BUTTON
        )

    @property
    def acquiredDuration(self) -> float:
        return self.numValid * self.sampleInterval

    @property
    def data(self) -> np.ndarray:
        """AD trace in pA (VC) or mV (IC), planned length, NaN after the last acquired sample."""
        return self.recording._trace('acquisition', self.sweep, 'AD', self.adChannel)

    @property
    def command(self) -> np.ndarray:
        """DA output in mV (VC) or pA (IC) without holding, planned length, NaN where unacquired."""
        return self.recording._trace('stimulus/presentation', self.sweep, 'DA', self.daChannel)

    def epochs(self) -> EpochTable:
        return self.recording.epochs(self.sweep, self.headstage)

    def plannedEpochs(self, user: bool = False) -> EpochTable:
        return self.recording.plannedEpochs(self.sweep, self.headstage, user=user)

    def sweepData(self, epochs: Optional[EpochTable] = None) -> SweepData:
        """Return the recorded sweep as ``SweepData``; *epochs* defaults to the recorded epochs."""
        return SweepData(
            sweep=self.sweep,
            clampMode=self.clampMode,
            sampleInterval=self.sampleInterval,
            data=self.data,
            command=self.command,
            numValid=self.numValid,
            epochs=self.epochs() if epochs is None else epochs,
            dascale=self.dascale,
            stoppedEarly=self.stoppedEarly,
        )


@dataclass
class MiesSet:
    """One stimset cycle (SCI) of one headstage: consecutive sweeps sharing a Stimset Acq Cycle ID."""

    sci: int
    headstage: int
    stimset: str
    analysisFunction: Optional[str]
    params: dict[str, Any]
    sweeps: list[int]  # experiment-wide sweep numbers, ascending


class MiesRecording:
    """A MIES-recorded NWB file (NWB 2, ndx-mies).

    Parameters
    ----------
    path : path of the ``.nwb`` file.
    device : labnotebook device name (e.g. 'ITC18USB_Dev_0'); required only if the file has several.
    """

    def __init__(self, path: Path | str, device: Optional[str] = None):
        self.path = Path(path)
        self._file = h5py.File(self.path, 'r')
        devices = list(self._file['general/labnotebook'])
        if device is None:
            if len(devices) != 1:
                raise ValueError(f"{self.path}: several devices {devices}; pass device=")
            device = devices[0]
        self.device = device
        g = self._file['general/labnotebook'][device]
        self.numerical = Labnotebook(g['numericalKeys'][()], g['numericalValues'][()])
        self.textual = Labnotebook(g['textualKeys'][()], g['textualValues'][()])
        self._traces: dict[tuple, np.ndarray] = {}
        self._sweepCache: dict[tuple[int, int], MiesSweep] = {}
        self._channels = self._scanChannels()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> 'MiesRecording':
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<MiesRecording {self.path.name}>"

    # ---- stimsets

    @property
    def stimsetPath(self) -> Path:
        """File holding the embedded stimsets (``general/stimsets``), for ``stimset.loadStimsets``."""
        return self.path

    def stimsets(self) -> dict[str, 'StimsetDef']:
        """Return the embedded stimsets via ``stimset.loadStimsets``."""
        from .stimset import loadStimsets

        return loadStimsets(self.stimsetPath)

    def labnotebookStimset(self, sweep: int, headstage: Optional[int] = None) -> 'StimsetDef':
        """Return a ``StimsetDef`` built from the sweep's labnotebook (stim wave note, ITI, function).

        ``epochs`` are those of stimset sweep 0. Only for use where the embedded stimsets are not needed;
        the wave and epoch-table methods are lane-A code.
        """
        from .stimset import EpochDef, StimsetDef

        hs = self._headstage(sweep, headstage)
        note = self.stimWaveNote(sweep, hs)
        epochs = []
        for ep in note['sweeps'][0]:
            params = {
                k: v
                for k, v in ep.items()
                if k not in ('Sweep', 'Epoch', 'Type', 'Duration', 'Amplitude')
            }
            epochs.append(
                EpochDef(
                    type=_EPOCH_TYPES.get(ep['Type'], ep['Type']),
                    duration=float(ep['Duration']),
                    amplitude=float(ep.get('Amplitude', 0)),
                    offset=float(ep.get('Offset', 0)),
                    params=params,
                )
            )
        func = self.setting(sweep, 'Generic function', hs) or None
        return StimsetDef(
            name=self.setting(sweep, 'Stim Wave Name', hs),
            epochs=epochs,
            numSweeps=note['numSweeps'],
            iti=float(note['sweepInfo'][0]['ITI']),
            analysisFunction=func,
            params=decodeParams(self.setting(sweep, 'Function params (encoded)', hs) or ''),
        )

    # ---- labnotebook

    def lastSetting(self, sweep: int, key: str, sourceType=AUTO) -> Optional[np.ndarray]:
        """Return the 9-layer labnotebook row for *key* (numerical, else textual), or None.

        *sourceType*: DATA_ACQUISITION_MODE, TEST_PULSE_MODE, UNKNOWN_MODE (None, any row of the
        sweep's newest block), or AUTO: DAQ rows first, then any row. USER_ entries and post-sweep
        entries (e.g. 'Skip Sweeps', 'DAQ stop reason') have no source type and need UNKNOWN_MODE or AUTO.
        """
        nb = self.numerical if self.numerical.has(key) else self.textual
        if sourceType == AUTO:
            v = nb.lastSetting(sweep, key, DATA_ACQUISITION_MODE)
            return v if v is not None else nb.lastSetting(sweep, key, UNKNOWN_MODE)
        return nb.lastSetting(sweep, key, sourceType)

    def setting(self, sweep: int, key: str, headstage: Optional[int] = None, sourceType=AUTO):
        """Return *key* for *headstage* (its layer, else the INDEP layer), or None when not set.

        Numerical values are float, textual values str. *headstage* defaults to the sweep's only
        active headstage.
        """
        row = self.lastSetting(sweep, key, sourceType)
        if row is None:
            return None
        text = row.dtype == object
        if headstage is None:
            headstage = self._headstage(sweep, None) if self._channels.get(sweep) else INDEP
        for layer in (headstage, INDEP):
            v = row[layer]
            if (v != '') if text else not np.isnan(v):
                return v if text else float(v)
        return None

    def settingIndep(self, sweep: int, key: str, sourceType=AUTO):
        """Return the headstage-independent (layer 8) value of *key*, or None."""
        row = self.lastSetting(sweep, key, sourceType)
        if row is None:
            return None
        v = row[INDEP]
        if row.dtype == object:
            return v if v != '' else None
        return None if np.isnan(v) else float(v)

    def commandLimit(self, sweep: int, headstage: Optional[int] = None) -> float:
        """Return the largest positive DA command, pA (IC) or mV (VC), from 'DA Gain' and the digitizer range."""
        hs = self._headstage(sweep, headstage)
        gain = self.setting(sweep, 'DA Gain', hs)  # command units per V
        hw = int(self.settingIndep(sweep, 'Digitizer Hardware Type'))
        return _DAC_MAX_VOLTS[hw] * gain

    # ---- sweeps and sets

    def _scanChannels(self) -> dict[int, dict[int, tuple[int, int]]]:
        """Map sweep -> headstage -> (AD channel, DA channel) for every acquired AD series."""
        out: dict[int, dict[int, tuple[int, int]]] = {}
        for name in self._file['acquisition']:
            parts = name.split('_')
            if len(parts) != 3 or parts[0] != 'data' or not parts[2].startswith('AD'):
                continue
            sweep, ad = int(parts[1]), int(parts[2][2:])
            adcs = self.numerical.lastSetting(sweep, 'ADC')
            dacs = self.numerical.lastSetting(sweep, 'DAC')
            if adcs is None or dacs is None:
                continue
            hits = [hs for hs in range(NUM_HEADSTAGES) if adcs[hs] == ad]
            if not hits:
                continue  # unassociated AD channel
            hs = hits[0]
            out.setdefault(sweep, {})[hs] = (ad, int(dacs[hs]))
        return out

    def sweepNumbers(self) -> list[int]:
        """Sweeps with acquired headstage data, ascending."""
        return sorted(self._channels)

    def headstages(self, sweep: int) -> list[int]:
        return sorted(self._channels[sweep])

    def _headstage(self, sweep: int, headstage: Optional[int]) -> int:
        if headstage is not None:
            return headstage
        hss = self.headstages(sweep)
        if len(hss) != 1:
            raise ValueError(f"sweep {sweep} has headstages {hss}; pass headstage=")
        return hss[0]

    def sweep(self, sweep: int, headstage: Optional[int] = None) -> MiesSweep:
        hs = self._headstage(sweep, headstage)
        key = (sweep, hs)
        if key not in self._sweepCache:
            self._sweepCache[key] = self._makeSweep(sweep, hs)
        return self._sweepCache[key]

    def sweeps(self) -> list[MiesSweep]:
        """Every (sweep, headstage) with acquired data, in acquisition order."""
        return [self.sweep(sw, hs) for sw in self.sweepNumbers() for hs in self.headstages(sw)]

    def _makeSweep(self, sweep: int, hs: int) -> MiesSweep:
        ad, da = self._channels[sweep][hs]
        grp = self._file[f'acquisition/data_{sweep:05d}_AD{ad}']
        ds = grp['data']
        dt = float(ds.attrs['IGORWaveScaling'][1, 0])
        mode = int(self.setting(sweep, 'Clamp Mode', hs))
        clampMode: ClampMode = 'VC' if mode == 0 else 'IC'
        data = self._trace('acquisition', sweep, 'AD', ad)
        nan = np.flatnonzero(np.isnan(data))
        numValid = int(nan[0]) if len(nan) else len(data)
        if clampMode == 'IC':
            on = self.setting(sweep, 'I-Clamp Holding Enable', hs)
            level = self.setting(sweep, 'I-Clamp Holding Level', hs)
        else:
            on = self.setting(sweep, 'V-Clamp Holding Enable', hs)
            level = self.setting(sweep, 'V-Clamp Holding Level', hs)
        stop = self.settingIndep(sweep, 'DAQ stop reason')
        func = self.setting(sweep, 'Generic function', hs) or None
        return MiesSweep(
            recording=self,
            sweep=sweep,
            headstage=hs,
            adChannel=ad,
            daChannel=da,
            stimset=self.setting(sweep, 'Stim Wave Name', hs),
            clampMode=clampMode,
            clampModeCode=mode,
            sampleInterval=dt,
            dascale=self.setting(sweep, 'Stim Scale Factor', hs),
            setSweepIndex=int(self.setting(sweep, 'Set Sweep Count', hs)),
            sci=int(self.setting(sweep, 'Stimset Acq Cycle ID', hs)),
            rac=int(self.settingIndep(sweep, 'Repeated Acq Cycle ID')),
            analysisFunction=func,
            params=(
                decodeParams(self.setting(sweep, 'Function params (encoded)', hs) or '')
                if func
                else {}
            ),
            numPoints=len(data),
            numValid=numValid,
            holding=float(level) if on else 0.0,
            daqStopReason=None if stop is None else int(stop),
        )

    def _trace(self, group: str, sweep: int, kind: str, channel: int) -> np.ndarray:
        key = (group, sweep, kind, channel)
        if key not in self._traces:
            ds = self._file[f'{group}/data_{sweep:05d}_{kind}{channel}/data']
            unit = _str(ds.attrs['IGORWaveUnits'][0])
            if unit not in ('pA', 'mV'):
                raise ValueError(f"{ds.name}: unexpected unit {unit!r}")
            self._traces[key] = np.asarray(ds[()], dtype=float)
        return self._traces[key]

    def sciSweeps(self, sweep: int, headstage: Optional[int] = None) -> list[int]:
        """Sweeps of the stimset cycle containing *sweep* (MIES AFH_GetSweepsFromSameSCI)."""
        hs = self._headstage(sweep, headstage)
        sci = self.sweep(sweep, hs).sci
        return [
            sw
            for sw in self.sweepNumbers()
            if hs in self._channels[sw] and self.sweep(sw, hs).sci == sci
        ]

    def racSweeps(self, sweep: int) -> list[int]:
        """Sweeps of the repeated-acquisition cycle containing *sweep*."""
        rac = self.settingIndep(sweep, 'Repeated Acq Cycle ID')
        return [
            sw
            for sw in self.sweepNumbers()
            if self.settingIndep(sw, 'Repeated Acq Cycle ID') == rac
        ]

    def sets(self) -> list[MiesSet]:
        """Every stimset cycle, ordered by its first sweep."""
        out: dict[tuple[int, int], MiesSet] = {}
        for s in self.sweeps():
            key = (s.headstage, s.sci)
            if key not in out:
                out[key] = MiesSet(s.sci, s.headstage, s.stimset, s.analysisFunction, s.params, [])
            out[key].sweeps.append(s.sweep)
        return sorted(out.values(), key=lambda m: m.sweeps[0])

    # ---- epochs

    def epochs(self, sweep: int, headstage: Optional[int] = None) -> EpochTable:
        """Return the sweep's DA epochs as MIES stored them (newest 'Epochs' entry), in LBN order.

        Times are ms; ``name`` is the ShortName; tags keep the other MIES tags plus 'TreeLevel'
        (-1 for user epochs). ``amplitude`` is the Amplitude tag (DAScale applied) or NaN.
        """
        hs = self._headstage(sweep, headstage)
        s = self.setting(sweep, 'Epochs', hs, sourceType=DATA_ACQUISITION_MODE)
        return parseEpochs(s or '')

    def plannedEpochs(
        self, sweep: int, headstage: Optional[int] = None, user: bool = False
    ) -> EpochTable:
        """Return the sweep's epochs as planned, before any early stop truncated them.

        Drops ``UA`` and (unless *user*) user epochs. For early-stopped sweeps, stimset epochs ``ST`` and
        ``E<i>`` that MIES cut or removed are rebuilt from the stim wave note; rebuilt epochs carry the
        tag ``Reconstructed=True``. Epochs below ``E<i>`` (e.g. pulse-train pulses) are not rebuilt.
        """
        hs = self._headstage(sweep, headstage)
        rec = self.sweep(sweep, hs)
        kept = [
            ep
            for ep in self.epochs(sweep, hs)
            if ep.name != 'UA' and (user or ep.tags.get('TreeLevel') != '-1')
        ]
        if not rec.stoppedEarly:
            return EpochTable(kept)
        planned = {ep.name: ep for ep in self._stimsetEpochs(rec)}
        acquiredEnd = round(rec.numValid * rec.sampleInterval, 4)
        out = []
        for ep in kept:
            if ep.name in planned and ep.end >= acquiredEnd - 1e-3:
                out.append(planned.pop(ep.name))
            else:
                planned.pop(ep.name, None)
                out.append(ep)
        out.extend(planned.values())
        return EpochTable(sorted(out, key=lambda ep: ep.start))

    def _stimsetEpochs(self, rec: MiesSweep) -> list[Epoch]:
        """Rebuild ``ST`` and ``E<i>`` from the stim wave note and onset delays."""
        hs = rec.headstage
        note = self.stimWaveNote(rec.sweep, hs)
        delay = self.setting(rec.sweep, 'Delay onset auto', hs) + self.setting(
            rec.sweep, 'Delay onset user', hs
        )
        oodDAQ = self.setting(rec.sweep, 'Delay onset oodDAQ', hs)  # absent in older files
        delay += 0.0 if oodDAQ is None else oodDAQ
        dt = rec.sampleInterval
        eps = note['sweeps'][rec.setSweepIndex]
        total = sum(float(ep['Duration']) for ep in eps)
        stEnd = round(delay + total - dt, 4)
        out = [
            Epoch(
                'ST',
                delay,
                stEnd,
                tags={'Type': 'Stimset', 'TreeLevel': '0', 'Reconstructed': 'True'},
            )
        ]
        t = delay
        for ep in eps:
            i = int(float(ep['Epoch']))
            dur = float(ep['Duration'])
            amp = float(ep['Amplitude']) * rec.dascale if 'Amplitude' in ep else float('nan')
            tags = {
                'Type': 'Epoch',
                'EpochType': ep['Type'],
                'Epoch': str(i),
                'TreeLevel': '1',
                'Reconstructed': 'True',
            }
            if not math.isnan(amp):
                tags['Amplitude'] = f'{amp:g}'
            out.append(Epoch(f'E{i}', round(t, 4), min(round(t + dur, 4), stEnd), amp, tags))
            t += dur
        return out

    def stimWaveNote(self, sweep: int, headstage: Optional[int] = None) -> dict[str, Any]:
        """Parse the sweep's 'Stim Wave Note'.

        Returns ``{'version', 'numSweeps', 'sweeps': {k: [epoch dicts]}, 'sweepInfo': {k: dict}}``;
        epoch dicts map wave-note keys (e.g. 'Type', 'Duration' in ms, 'Amplitude') to strings.
        """
        hs = self._headstage(sweep, headstage)
        note = self.setting(sweep, 'Stim Wave Note', hs)
        if note is None:
            raise KeyError(f"sweep {sweep} headstage {hs} has no 'Stim Wave Note'")
        return parseStimWaveNote(note)


def parseEpochs(s: str) -> EpochTable:
    """Parse a MIES labnotebook 'Epochs' string (``start,end,tags,level,:...``, times in s)."""
    out = []
    for row in s.split(':'):
        if not row.strip():
            continue
        cols = row.split(',')
        start, end, tagStr, level = cols[0], cols[1], cols[2], cols[3]
        tags = {}
        for item in tagStr.split(';'):
            if not item:
                continue
            k, sep, v = item.partition('=')
            tags[k] = v if sep else ''
        name = tags.pop('ShortName', tagStr)
        tags['TreeLevel'] = level
        amp = _igorNum(tags['Amplitude']) if 'Amplitude' in tags else float('nan')
        out.append(Epoch(name, round(float(start) * 1e3, 4), round(float(end) * 1e3, 4), amp, tags))
    return EpochTable(out)


def parseStimWaveNote(note: str) -> dict[str, Any]:
    """Parse a WaveBuilder stimset wave note; see ``MiesRecording.stimWaveNote``."""
    version = None
    sweeps: dict[int, list[dict[str, str]]] = {}
    info: dict[int, dict[str, str]] = {}
    for line in note.replace('\r', '\n').split('\n'):
        entry = {}
        for item in line.split(';'):
            k, sep, v = item.partition(' = ')
            if sep:
                entry[k.strip()] = v.strip()
        if 'Version' in entry and 'Sweep' not in entry:
            version = _igorNum(entry['Version'])
        if 'Sweep' not in entry:
            continue
        sw = int(float(entry['Sweep']))
        if entry.get('Epoch', 'nan') == 'nan':
            info[sw] = entry
        else:
            sweeps.setdefault(sw, []).append(entry)
    numSweeps = max(set(sweeps) | set(info), default=-1) + 1
    return {'version': version, 'numSweeps': numSweeps, 'sweeps': sweeps, 'sweepInfo': info}
