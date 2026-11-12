"""Per-cell record of sweeps and sets, standing in for the MIES labnotebook."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


class Keys:
    """Notebook value names that other analysis functions read. Values are in MIES units."""

    SWEEP_QC = 'SweepQC'  # bool, every type
    SET_QC = 'SetQC'  # bool, every type
    BASELINE_QC = 'BaselineQC'  # bool
    SPIKE_DETECT = 'SpikeDetect'  # bool, SP/RB per sweep
    FINAL_SCALE = 'FinalScale'  # pA, SP set result read by RB
    PULSE_DURATION = 'PulseDuration'  # ms, RB set
    OPERATION_MODE = 'OperationMode'  # str, DA set: 'Sub' | 'Supra' | 'AdaptiveSupra'
    RESISTANCE_FROM_FIT = 'ResistanceFromFit'  # MOhm, DA Sub set, read by CR
    FULL_AVERAGE = 'FullAverage'  # mV, VM set, read by CR and autobias
    SPIKE_COUNT = 'SpikeCount'  # int, per sweep
    AP_FREQUENCY = 'APFrequency'  # Hz, DA per sweep


@dataclass
class SweepRecord:
    sweep: int
    sci: int
    stimset: str
    analysisType: str  # MIES prefix: PB, SE, AR, VM, DA, SP, RB, RA, CR
    dascale: float
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class SetRecord:
    sci: int
    stimset: str
    analysisType: str
    sweeps: list[int] = field(default_factory=list)
    values: dict[str, Any] = field(default_factory=dict)


class Notebook:
    """Append-only sweep and set records for one cell, optionally saved as JSON.

    Sweep numbers are experiment-wide and increase monotonically; ``sci`` (MIES stimset cycle id)
    numbers each pass through a stimset. Queries return records oldest first.
    """

    def __init__(self, path: Optional[Path | str] = None):
        self.path = Path(path) if path is not None else None
        self._sweeps: dict[int, SweepRecord] = {}
        self._sets: dict[int, SetRecord] = {}
        if self.path is not None and self.path.exists():
            self._load()

    def nextSweepNumber(self) -> int:
        return max(self._sweeps, default=-1) + 1

    def newSet(self, stimset: str, analysisType: str) -> SetRecord:
        sci = max(self._sets, default=-1) + 1
        rec = SetRecord(sci=sci, stimset=stimset, analysisType=analysisType)
        self._sets[sci] = rec
        return rec

    def addSweep(
        self, sweep: int, sci: int, dascale: float, values: Optional[dict] = None
    ) -> SweepRecord:
        """Record a sweep of set *sci*; raises ValueError if *sweep* already exists."""
        if sweep in self._sweeps:
            raise ValueError(f"sweep {sweep} already recorded")
        s = self._sets[sci]
        rec = SweepRecord(sweep, sci, s.stimset, s.analysisType, dascale, dict(values or {}))
        self._sweeps[sweep] = rec
        s.sweeps.append(sweep)
        return rec

    def sweep(self, sweep: int) -> SweepRecord:
        return self._sweeps[sweep]

    def set(self, sci: int) -> SetRecord:
        return self._sets[sci]

    def setOf(self, sweep: int) -> SetRecord:
        return self._sets[self._sweeps[sweep].sci]

    def sweeps(
        self,
        analysisType: Optional[str] = None,
        sci: Optional[int] = None,
        where: Optional[Callable[[SweepRecord], bool]] = None,
    ) -> list[SweepRecord]:
        out = [
            r
            for r in self._sweeps.values()
            if (analysisType is None or r.analysisType == analysisType)
            and (sci is None or r.sci == sci)
        ]
        out.sort(key=lambda r: r.sweep)
        return [r for r in out if where is None or where(r)]

    def sets(
        self,
        analysisType: Optional[str] = None,
        stimset: Optional[str] = None,
        where: Optional[Callable[[SetRecord], bool]] = None,
    ) -> list[SetRecord]:
        out = [
            r
            for r in self._sets.values()
            if (analysisType is None or r.analysisType == analysisType)
            and (stimset is None or r.stimset == stimset)
        ]
        out.sort(key=lambda r: r.sci)
        return [r for r in out if where is None or where(r)]

    def lastSet(
        self, analysisType: str, where: Optional[Callable[[SetRecord], bool]] = None
    ) -> Optional[SetRecord]:
        """Return the newest set of *analysisType* matching *where*, or None."""
        found = self.sets(analysisType, where=where)
        return found[-1] if found else None

    def lastSweepWith(self, key: str, analysisType: Optional[str] = None) -> Optional[SweepRecord]:
        """Return the newest sweep that has a value for *key*, or None (MIES GetLastSweepWithSetting)."""
        found = self.sweeps(analysisType, where=lambda r: key in r.values)
        return found[-1] if found else None

    def save(self) -> None:
        """Write the notebook to ``path``; no-op when the notebook has no path."""
        if self.path is None:
            return
        doc = {
            'sets': [asdict(s) for s in self.sets()],
            'sweeps': [asdict(s) for s in self.sweeps()],
        }
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(doc, indent=1, default=_jsonDefault))
        tmp.replace(self.path)

    def _load(self) -> None:
        doc = json.loads(self.path.read_text())
        for s in doc['sets']:
            self._sets[s['sci']] = SetRecord(**s)
        for s in doc['sweeps']:
            self._sweeps[s['sweep']] = SweepRecord(**s)


def _jsonDefault(obj):
    # numpy scalars and arrays
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")
