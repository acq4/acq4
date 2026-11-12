"""Offline replay of ported analysis functions over recorded MIES stimset cycles.

The driver plays one recorded SCI (or a whole recording, in order) through an ``AnalysisFunction``
the way the runner would: ``preSet``, then per sweep ``preSweep``, ``midSweep`` on growing partial data,
``postSweep`` on the full recorded sweep, and ``postSet``. Data is always what MIES recorded; the
function's requests (DAScale, EarlyStop, ZeroCommand, set end) are recorded and compared with the
labnotebook.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping, Optional, Sequence

import numpy as np

from .core import (
    AbortSet,
    EarlyStop,
    Epoch,
    EpochTable,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
)
from .core import SweepDecision, ZeroCommand
from .functions.base import AnalysisFunction, RunContext, functionFor
from .mies_nwb import LBN_PREFIX, UNKNOWN_MODE, MiesRecording, MiesSet, MiesSweep, userKey
from .notebook import Keys, Notebook, SetRecord

if TYPE_CHECKING:
    from .stimset import StimsetDef

# user-epoch name prefixes MIES adds during MID_SWEEP; a port cannot produce them in preSweep
MID_SWEEP_EPOCH_PREFIXES = ('U_BLC',)


@dataclass
class SweepComparison:
    """One replayed sweep: the function's requests next to what MIES recorded."""

    sweep: int
    setSweepIndex: int
    clampMode: str
    sweepConfig: SweepConfig
    miesDascale: float
    midSweepCalls: int
    earlyStop: Optional[EarlyStop]
    earlyStopAt: Optional[float]  # ms of acquired data when EarlyStop was returned
    zeroCommand: Optional[ZeroCommand]
    zeroCommandAt: Optional[float]  # ms
    miesStoppedEarly: bool
    miesAcquired: float  # ms
    stoppedByUser: bool  # MIES DAQ button stopped acquisition during or after this sweep
    decision: SweepDecision
    miesSweepPassed: Optional[bool]  # None when MIES writes no Sweep QC (e.g. PSQ_Rheobase)
    miesContinued: bool  # MIES acquired another sweep of this SCI
    exhausted: bool  # this was the stimset's last sweep
    dascaleRtol: float = 1e-6
    stopTolerance: float = 100.0  # ms
    userEpochDiffs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def dascale(self) -> float:
        return self.sweepConfig.dascale

    def mismatches(self) -> list[str]:
        out = []
        if not math.isclose(self.dascale, self.miesDascale, rel_tol=self.dascaleRtol, abs_tol=1e-9):
            out.append(f"DAScale {self.dascale:g} != MIES {self.miesDascale:g}")
        if self.miesSweepPassed is not None and self.decision.sweepPassed != self.miesSweepPassed:
            out.append(
                f"sweep QC {int(self.decision.sweepPassed)} != MIES {int(self.miesSweepPassed)}"
            )
        miesStop = self.miesStoppedEarly and not self.stoppedByUser
        if (self.earlyStop is not None) != miesStop:
            ours = f"at {self.earlyStopAt:.1f} ms" if self.earlyStop else "no"
            mies = f"at {self.miesAcquired:.1f} ms" if miesStop else "no"
            out.append(f"early stop {ours}, MIES {mies}")
        elif (
            self.earlyStop is not None
            and abs(self.earlyStopAt - self.miesAcquired) > self.stopTolerance
        ):
            out.append(
                f"early stop at {self.earlyStopAt:.1f} ms, MIES at {self.miesAcquired:.1f} ms"
            )
        ended = self.decision.action != 'continue'
        if ended and self.miesContinued:
            out.append(f"action {self.decision.action}, MIES continued")
        elif not ended and not self.miesContinued and not self.exhausted and not self.stoppedByUser:
            out.append("action continue, MIES ended the set")
        out.extend(self.userEpochDiffs)
        return out


@dataclass
class SetComparison:
    """One replayed SCI."""

    mset: MiesSet
    miesName: str
    function: Optional[AnalysisFunction] = None
    setRecord: Optional[SetRecord] = None
    setConfig: Optional[SetConfig] = None
    result: Optional[SetResult] = None
    aborted: Optional[str] = None  # AbortSet message, prefixed by the event
    miesSetPassed: Optional[bool] = None
    miesClampMode: str = ''
    miesSampleInterval: float = float('nan')
    sweeps: list[SweepComparison] = field(default_factory=list)
    unreplayed: list[int] = field(
        default_factory=list
    )  # MIES sweeps after the function ended the set
    notes: list[str] = field(default_factory=list)

    def mismatches(self) -> list[str]:
        out = []
        if self.aborted is not None:
            out.append(f"aborted ({self.aborted}), MIES ran the set")
        if self.setConfig is not None:
            if self.setConfig.clampMode != self.miesClampMode:
                out.append(f"clamp mode {self.setConfig.clampMode} != MIES {self.miesClampMode}")
            if not math.isclose(
                self.setConfig.sampleInterval, self.miesSampleInterval, rel_tol=1e-9
            ):
                out.append(
                    f"sample interval {self.setConfig.sampleInterval:g} != MIES {self.miesSampleInterval:g} ms"
                )
        if (
            self.result is not None
            and self.miesSetPassed is not None
            and self.result.passed != self.miesSetPassed
        ):
            out.append(f"set QC {int(self.result.passed)} != MIES {int(self.miesSetPassed)}")
        for s in self.sweeps:
            out.extend(f"sweep {s.sweep}: {m}" for m in s.mismatches())
        return out


@dataclass
class ReplayResult:
    """Replay of a recording: compared sets and SCIs skipped for lack of a ported function."""

    recording: MiesRecording
    notebook: Notebook
    sets: list[SetComparison] = field(default_factory=list)
    skipped: list[tuple[MiesSet, str]] = field(default_factory=list)  # (set, reason)

    def mismatches(self) -> list[str]:
        return [
            f"{c.mset.stimset} (SCI {c.mset.sci}): {m}" for c in self.sets for m in c.mismatches()
        ]

    def report(self) -> str:
        return formatReport(self.sets, self.skipped)


def unscaledLayout(epochs: EpochTable, dascale: float) -> EpochTable:
    """Return *epochs* with stimset-epoch amplitudes (``E*``) divided by *dascale* (DAScale 1 layout)."""
    out = []
    for ep in epochs:
        if ep.name.startswith('E') and not math.isnan(ep.amplitude):
            amp = ep.amplitude / dascale if dascale != 0 else float('nan')
            ep = Epoch(ep.name, ep.start, ep.end, amp, ep.tags)
        out.append(ep)
    return EpochTable(out)


def stimsetLookup(recording: MiesRecording, stimsets) -> Callable[[str], 'StimsetDef']:
    """Return a name -> ``StimsetDef`` lookup.

    *stimsets*: 'nwb' (embedded stimsets via ``stimset.loadStimsets``), 'labnotebook'
    (``MiesRecording.labnotebookStimset`` of the first sweep that played the stimset), or a mapping.
    """
    if stimsets == 'nwb':
        table = recording.stimsets()
        return table.__getitem__
    if stimsets == 'labnotebook':
        cache: dict[str, 'StimsetDef'] = {}

        def lookup(name: str):
            if name not in cache:
                for s in recording.sweeps():
                    if s.stimset == name:
                        cache[name] = recording.labnotebookStimset(s.sweep, s.headstage)
                        break
                else:
                    raise KeyError(name)
            return cache[name]

        return lookup
    return stimsets.__getitem__


def labnotebookContext(
    recording: MiesRecording,
    current: Callable[[], MiesSweep],
    stimsets: Callable[[str], 'StimsetDef'],
) -> RunContext:
    """Return a ``RunContext`` reading autobias and holding from the labnotebook of ``current()``.

    ``commandLimit`` is fixed at the value for the sweep current when this is called.
    """

    def autobiasTarget():
        s = current()  # 'Autobias Vcom' is the panel target, recorded whether or not autobias is on
        return recording.setting(s.sweep, 'Autobias Vcom', s.headstage)

    s0 = current()
    return RunContext(
        autobiasTarget=autobiasTarget,
        holding=lambda: current().holding,
        commandLimit=recording.commandLimit(s0.sweep, s0.headstage),
        stimsets=stimsets,
    )


def replaySet(
    recording: MiesRecording,
    mset: MiesSet,
    cls: Optional[type[AnalysisFunction]] = None,
    notebook: Optional[Notebook] = None,
    stimsets='nwb',
    chunk: float = 100.0,
    stopTolerance: Optional[float] = None,
    dascaleRtol: float = 1e-6,
) -> SetComparison:
    """Replay one recorded SCI through an analysis function.

    Parameters
    ----------
    cls : function class; defaults to ``functionFor(mset.analysisFunction)``.
    notebook : notebook the set is recorded in (a new one when None).
    stimsets : see ``stimsetLookup``; a callable lookup is used as is.
    chunk : ms of new data per ``midSweep`` call; the last call has all recorded samples.
    stopTolerance : allowed |our EarlyStop time - MIES acquired time| in ms; defaults to *chunk*.

    ``midSweep`` receives a new ``SweepData`` per call, but all calls of one sweep share one data buffer
    that is filled in place. After an EarlyStop no further ``midSweep`` calls are made; after a
    ZeroCommand ``commandZeroedAt`` is set but ``command`` stays as recorded. As in the runner, the
    notebook sweep record (with the function's DAScale) is added after ``midSweep`` and before
    ``postSweep``, and ``SweepQC``/``SetQC`` are filled from the decision/result when the function did not
    set them. ``AbortSet`` ends the replay without ``postSet``.
    """
    notebook = Notebook() if notebook is None else notebook
    cls = functionFor(mset.analysisFunction) if cls is None else cls
    lookup = stimsets if callable(stimsets) else stimsetLookup(recording, stimsets)
    hs = mset.headstage
    first = recording.sweep(mset.sweeps[0], hs)
    state = {'current': first}
    context = labnotebookContext(recording, lambda: state['current'], lookup)
    stimset = lookup(mset.stimset)
    numSweeps = recording.stimWaveNote(first.sweep, hs)['numSweeps']
    miesName = mset.analysisFunction or cls.miesName

    cmp = SetComparison(
        mset=mset,
        miesName=miesName,
        miesClampMode=first.clampMode,
        miesSampleInterval=first.sampleInterval,
        miesSetPassed=_miesSetPassed(recording, mset, miesName),
    )
    af = cls(stimset, mset.params, notebook, context)
    setRec = notebook.newSet(mset.stimset, cls.analysisType)
    af.setRecord = setRec
    cmp.function, cmp.setRecord = af, setRec
    try:
        cmp.setConfig = af.preSet()
    except AbortSet as exc:
        cmp.aborted = f"preSet: {exc}"
        return cmp

    tol = chunk if stopTolerance is None else stopTolerance
    for k, sweepNo in enumerate(mset.sweeps):
        ms = recording.sweep(sweepNo, hs)
        state['current'] = ms
        planned = recording.plannedEpochs(sweepNo, hs)
        try:
            swCfg = af.preSweep(k, unscaledLayout(planned, ms.dascale))
        except AbortSet as exc:
            cmp.aborted = f"preSweep {sweepNo}: {exc}"
            cmp.unreplayed = mset.sweeps[k:]
            return cmp
        epochs = planned.copy()
        epochs.add(*swCfg.userEpochs)
        sc = _feedSweep(af, ms, epochs, chunk)
        notebook.addSweep(sweepNo, setRec.sci, swCfg.dascale)
        sc.update(
            sweepConfig=swCfg,
            setSweepIndex=ms.setSweepIndex,
            clampMode=ms.clampMode,
            miesDascale=ms.dascale,
            miesStoppedEarly=ms.stoppedEarly,
            miesAcquired=ms.acquiredDuration,
            stoppedByUser=ms.stoppedByUser,
            miesSweepPassed=(
                _bool(recording.setting(sweepNo, userKey(miesName, 'Sweep QC'), hs, UNKNOWN_MODE))
                if miesName in LBN_PREFIX
                else None
            ),
            miesContinued=k < len(mset.sweeps) - 1,
            exhausted=ms.setSweepIndex >= numSweeps - 1,
            dascaleRtol=dascaleRtol,
            stopTolerance=tol,
        )
        full = SweepData(
            sweep=sweepNo,
            clampMode=ms.clampMode,
            sampleInterval=ms.sampleInterval,
            data=ms.data.copy(),
            command=ms.command.copy(),
            numValid=ms.numValid,
            epochs=epochs,
            dascale=ms.dascale,
            stoppedEarly=ms.stoppedEarly,
            commandZeroedAt=sc['zeroCommandAt'],
        )
        decision = af.postSweep(full)
        notebook.sweep(sweepNo).values.setdefault(Keys.SWEEP_QC, decision.sweepPassed)
        comp = SweepComparison(decision=decision, sweep=sweepNo, **sc)
        comp.userEpochDiffs = _userEpochDiffs(recording, ms, swCfg.userEpochs)
        if ms.setSweepIndex != k:
            comp.notes.append(f"stimset sweep {ms.setSweepIndex} played as set sweep {k}")
        if ms.clampMode != cmp.setConfig.clampMode:
            comp.notes.append(f"MIES clamp mode {ms.clampMode}")
        if ms.stoppedByUser:
            comp.notes.append("MIES DAQ stopped by user")
        cmp.sweeps.append(comp)
        if decision.action != 'continue':
            cmp.unreplayed = mset.sweeps[k + 1 :]
            break

    cmp.result = af.postSet()
    setRec.values.setdefault(Keys.SET_QC, cmp.result.passed)
    return cmp


def replayRecording(
    recording: MiesRecording,
    functions: Optional[Mapping[str, type[AnalysisFunction]]] = None,
    notebook: Optional[Notebook] = None,
    stimsets='nwb',
    include: Optional[Callable[[MiesSet], bool]] = None,
    **kwargs,
) -> ReplayResult:
    """Replay every SCI that has a ported analysis function, in acquisition order, into one notebook.

    *functions* maps MIES names to classes (default: ``functionFor``; unported names are skipped).
    *include* filters SCIs. Other keyword arguments go to ``replaySet``.
    """
    result = ReplayResult(recording, Notebook() if notebook is None else notebook)
    lookup = stimsetLookup(recording, stimsets)
    for mset in recording.sets():
        if mset.analysisFunction is None:
            result.skipped.append((mset, 'no analysis function'))
            continue
        if include is not None and not include(mset):
            result.skipped.append((mset, 'excluded'))
            continue
        if functions is not None:
            cls = functions.get(mset.analysisFunction)
        else:
            try:
                cls = functionFor(mset.analysisFunction)
            except KeyError:
                cls = None
        if cls is None:
            result.skipped.append((mset, f'{mset.analysisFunction} not ported'))
            continue
        result.sets.append(replaySet(recording, mset, cls, result.notebook, lookup, **kwargs))
    return result


def _feedSweep(af: AnalysisFunction, ms: MiesSweep, epochs: EpochTable, chunk: float) -> dict:
    """Call ``midSweep`` on growing partial data; return the recorded requests as SweepComparison fields."""
    dt = ms.sampleInterval
    step = max(1, int(round(chunk / dt)))
    recorded, command = ms.data, ms.command.copy()
    buf = np.full(len(recorded), np.nan)
    out = dict(
        earlyStop=None, earlyStopAt=None, zeroCommand=None, zeroCommandAt=None, midSweepCalls=0
    )
    pos = 0
    while pos < ms.numValid:
        new = min(pos + step, ms.numValid)
        buf[pos:new] = recorded[pos:new]
        pos = new
        partial = SweepData(
            sweep=ms.sweep,
            clampMode=ms.clampMode,
            sampleInterval=dt,
            data=buf,
            command=command,
            numValid=pos,
            epochs=epochs,
            dascale=ms.dascale,
            commandZeroedAt=out['zeroCommandAt'],
        )
        action = af.midSweep(partial)
        out['midSweepCalls'] += 1
        if isinstance(action, EarlyStop):
            out.update(earlyStop=action, earlyStopAt=pos * dt)
            break
        if isinstance(action, ZeroCommand) and out['zeroCommand'] is None:
            out.update(zeroCommand=action, zeroCommandAt=pos * dt)
    return out


def _userEpochDiffs(
    recording: MiesRecording, ms: MiesSweep, ours: Sequence[Epoch], tol: float = 1e-3
) -> list[str]:
    """Compare the function's user epochs with MIES's; MIES mid-sweep epochs and epochs past an early
    stop are not compared."""
    acquiredEnd = ms.acquiredDuration
    mies = {
        ep.name: ep
        for ep in recording.epochs(ms.sweep, ms.headstage)
        if ep.tags.get('TreeLevel') == '-1' and not ep.name.startswith(MID_SWEEP_EPOCH_PREFIXES)
    }
    out = []
    for ep in ours:
        if ms.stoppedEarly and ep.start >= acquiredEnd:
            mies.pop(ep.name, None)
            continue
        m = mies.pop(ep.name, None)
        if m is None:
            out.append(f"user epoch {ep.name} not in MIES")
        elif abs(m.start - ep.start) > tol or (
            abs(m.end - ep.end) > tol and not (ms.stoppedEarly and m.end <= ep.end)
        ):
            out.append(
                f"user epoch {ep.name} {ep.start:g}-{ep.end:g} != MIES {m.start:g}-{m.end:g} ms"
            )
    out.extend(f"MIES user epoch {name} missing" for name in mies)
    return out


def _miesSetPassed(recording: MiesRecording, mset: MiesSet, miesName: str) -> Optional[bool]:
    if miesName not in LBN_PREFIX:
        return None
    key = userKey(miesName, 'Set QC')
    for sw in reversed(mset.sweeps):
        v = recording.setting(sw, key, mset.headstage, UNKNOWN_MODE)
        if v is not None:
            return _bool(v)
    return None


def _bool(v) -> Optional[bool]:
    return None if v is None else bool(v)


def _fmt(v, spec='g') -> str:
    if v is None:
        return '-'
    if isinstance(v, bool):
        return str(int(v))
    return format(v, spec)


def formatReport(sets: Sequence[SetComparison], skipped: Sequence[tuple[MiesSet, str]] = ()) -> str:
    """Return a text table of replayed sets and sweeps; mismatching rows end with their mismatches."""
    lines = []
    for c in sets:
        ours = _fmt(c.result.passed) if c.result is not None else ('abort' if c.aborted else '-')
        lines.append(
            f"SCI {c.mset.sci}  {c.mset.stimset}  {c.miesName}  HS{c.mset.headstage}  "
            f"set QC {ours}/{_fmt(c.miesSetPassed)}"
        )
        lines.extend(f"  !! {m}" for m in c.mismatches() if not m.startswith('sweep '))
        lines.append(
            f"  {'sweep':>5} {'idx':>3} {'DAScale ours/MIES':>20} {'stop ms ours/MIES':>21} "
            f"{'QC':>5} {'action':>14} {'MIES':>5}"
        )
        for s in c.sweeps:
            miesStop = f"{s.miesAcquired:.1f}" if s.miesStoppedEarly else '-'
            ourStop = f"{s.earlyStopAt:.1f}" if s.earlyStop else '-'
            miesNext = 'cont' if s.miesContinued else ('user' if s.stoppedByUser else 'end')
            row = (
                f"  {s.sweep:>5} {s.setSweepIndex:>3} {_fmt(s.dascale):>9} / {_fmt(s.miesDascale):<8} "
                f"{ourStop:>9} / {miesStop:<9} {_fmt(s.decision.sweepPassed)}/{_fmt(s.miesSweepPassed)}   "
                f"{s.decision.action:>14} {miesNext:>5}"
            )
            mm = s.mismatches()
            if mm:
                row += '  !! ' + '; '.join(mm)
            if s.notes:
                row += '  (' + '; '.join(s.notes) + ')'
            lines.append(row)
        if c.unreplayed:
            lines.append(f"  not replayed (function ended the set): {c.unreplayed}")
    for mset, reason in skipped:
        lines.append(
            f"skipped SCI {mset.sci} {mset.stimset} sweeps {mset.sweeps[0]}-{mset.sweeps[-1]}: {reason}"
        )
    return '\n'.join(lines)
