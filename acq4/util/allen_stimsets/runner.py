"""Run MIES stimsets with their analysis functions on an ACQ4 patch clamp."""

from __future__ import annotations

import dataclasses
import logging
import queue
import threading
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np

from acq4.util import Qt, ptime

from . import stimset as stimsetModule
from .amplifier import AmplifierControl, AmplifierScope, commandLimit, siPerMiesUnit
from .core import (
    AbortSet,
    EarlyStop,
    EpochTable,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepData,
    TestPulseSettings,
    ZeroCommand,
)
from .functions.base import AnalysisFunction, RunContext, functionFor
from .notebook import Keys, Notebook
from .stimset import StimsetDef

logger = logging.getLogger(__name__)

# MIES DAEphys defaults: 10 ms pulse, 35 % baseline, 10 mV VC, -50 pA IC.
DEFAULT_TEST_PULSE = TestPulseSettings(
    pulseDuration=10.0, baselineFraction=0.35, amplitudeVC=10.0, amplitudeIC=-50.0
)


def testPulseFromClamp(clamp) -> tuple[TestPulseSettings, dict[str, str]]:
    """Return the inserted-TP settings taken from *clamp*'s test pulse, and each field's source.

    Durations come from the VC test pulse; the baseline fraction only when its pre and post durations
    are equal. A field the clamp cannot supply is taken from DEFAULT_TEST_PULSE. Sources are
    'clamp:<parameter>' or 'default'.
    """

    getter = getattr(clamp, 'getTestPulseParameter', None)  # None: clamp has no ACQ4 test pulse

    def param(name):
        if getter is None:
            return None
        try:
            return getter(name)
        except KeyError:
            return None

    values = dataclasses.asdict(DEFAULT_TEST_PULSE)
    sources = dict.fromkeys(values, 'default')
    pulse, pre, post = (param(f'vc{k}Duration') for k in ('Pulse', 'Pre', 'Post'))
    if pulse is not None:
        values['pulseDuration'], sources['pulseDuration'] = pulse * 1e3, 'clamp:vcPulseDuration'
        if pre is not None and post is not None and abs(pre - post) < 1e-9:
            values['baselineFraction'] = pre / (pre + pulse + post)
            sources['baselineFraction'] = 'clamp:vcPreDuration/vcPostDuration'
    for field_, name, scale in [
        ('amplitudeVC', 'vcAmplitude', 1e3),
        ('amplitudeIC', 'icAmplitude', 1e12),
    ]:
        v = param(name)
        if v is not None:
            values[field_], sources[field_] = v * scale, f'clamp:{name}'
    return TestPulseSettings(**values), sources


_PRIMARY_UNITS = {'VC': 'A', 'IC': 'V'}


@dataclass
class _Run:
    """State of one top-level runSet/runChain call."""

    dir: Any  # DirHandle or None
    scope: AmplifierScope
    testPulse: TestPulseSettings  # inserted test pulse
    lastSweepEnd: Optional[float] = (
        None  # ptime.time() at the end of the last sweep's acquired data
    )
    pendingIti: float = 0.0  # s, from the end of the last sweep's data to the next sweep
    pendingExtra: float = 0.0  # s added to the next wait
    sets: list = field(default_factory=list)


@dataclass
class _SetOutcome:
    result: SetResult
    endChain: bool


class _PartialCopier:
    """Partial-result handler: queues newly settled primary samples as (start, SI array). DAQ reader thread."""

    def __init__(self, devName: str, out: queue.Queue):
        self.devName = devName
        self.out = out
        self.copied = 0
        self.row = None

    def __call__(self, payload):
        res = payload.get(self.devName)
        if res is None:
            return
        n = res.settlement().get('primary', 0)
        if n <= self.copied:
            return
        if self.row is None:
            self.row = res.listColumns(0).index('primary')
            self.out.put(('units', res.columnUnits(0, 'primary')))
        self.out.put((self.copied, np.array(res.asarray()[self.row, self.copied : n])))
        self.copied = n


class StimsetRunner:
    """Plays MIES stimsets on one patch clamp, driving their analysis functions, storage and notebook.

    Each top-level ``runSet``/``runChain`` call is one run: it creates ``AllenStimsets_NNN`` in
    *storageDir* (None: store nothing), restores run-scope amplifier settings at its end, and leaves the
    test pulse as it found it. The test pulse runs during ITIs when both *testPulseDuringIti* and the
    set's ``SetConfig.testPulseDuringIti`` are true, and is paused while the runner configures the
    amplifier or acquires. Blocking methods run analysis functions and
    listeners on the calling thread, which must not be the GUI thread.

    Parameters
    ----------
    clamp : PatchClamp or str
        Clamp device or its name.
    stimsets : dict
        {name: StimsetDef}; also the name list used for indexing.
    notebook : Notebook
        Per-cell notebook; saved after every sweep.
    storageDir : DirHandle or None
        Cell directory to create run directories in.
    testPulse : TestPulseSettings, optional
        Inserted test pulse; default ``testPulseFromClamp(clamp)`` at the start of each run.
    paramOverrides : dict, optional
        {stimset name: {analysis parameter: value}} applied over the stimset's parameters.
    manager : Manager, optional
        Default ``getManager()``.
    functions : dict, optional
        {stimset name: AnalysisFunction subclass} used instead of the registry lookup.
    updateInterval : float
        Partial-result interval, s.
    testPulseDuringIti : bool
        Run the clamp's test pulse (and its autobias) between sweeps of sets that allow it.
    recordSecondary : bool
        Also record and store the clamp's secondary signal.
    """

    def __init__(
        self,
        clamp,
        stimsets: dict[str, StimsetDef],
        notebook: Notebook,
        storageDir,
        *,
        testPulse: Optional[TestPulseSettings] = None,
        paramOverrides: Optional[dict[str, dict]] = None,
        manager=None,
        functions: Optional[dict[str, type[AnalysisFunction]]] = None,
        updateInterval: float = 0.1,
        testPulseDuringIti: bool = True,
        recordSecondary: bool = False,
    ):
        if manager is None:
            from acq4.Manager import getManager

            manager = getManager()
        self.manager = manager
        self.clamp = manager.getDevice(clamp) if isinstance(clamp, str) else clamp
        self.daqName = self.clamp.getDAQName('primary')
        self.stimsets = stimsets
        self.notebook = notebook
        self.storageDir = storageDir
        self.testPulse = testPulse
        self.paramOverrides = dict(paramOverrides or {})
        self.functions = dict(functions or {})
        self.updateInterval = updateInterval
        self.testPulseDuringIti = testPulseDuringIti
        self.recordSecondary = recordSecondary
        self.amp = AmplifierControl(self.clamp, logger)
        self._stopEvent = threading.Event()
        self._listeners: list[Callable[[str, dict], None]] = []
        self._running = threading.Lock()

    # ------------------------------------------------------------------ public API

    def addListener(self, fn: Callable[[str, dict], None]) -> None:
        """Call ``fn(event, info)`` on the runner thread for progress events.

        Events: 'runStarted', 'setStarted', 'iti', 'sweepStarted', 'midSweep', 'sweepFinished',
        'setFinished', 'runFinished'. A listener that raises is logged and kept.
        """
        self._listeners.append(fn)

    def stop(self) -> None:
        """Request the run to end: the current sweep stops early, then the set ends. Thread-safe."""
        self._stopEvent.set()

    @property
    def stopRequested(self) -> bool:
        return self._stopEvent.is_set()

    def runSet(self, name: str) -> SetResult:
        """Run stimset *name* as a run of its own and return its SetResult. Blocks."""
        name = self._stimsetName(name)
        with self._runScope(start=name, end=name) as run:
            return self._runSet(name, run).result

    def runChain(self, start: str, end: Optional[str] = None) -> list[tuple[str, SetResult]]:
        """Run *start*, then follow indexing and NextStimSetName on each pass, up to and including *end*.

        Stops after a failed set, an abort, ``stop()``, *end*, or a set that names no next stimset.
        Indexing plays the stimsets up to an indexing end in case-insensitive name order. It starts
        from a set's NextIndexingEndStimSetName, or from the start when *end* sorts after *start*
        (what MIES does after EXTPBREAKN names X0NRMP and indexing end X7RampN3). Stimset names
        match case-insensitively, as in MIES. Blocks.
        """
        return self.runChains([(start, end)])

    def runChains(self, chains: list[tuple[str, Optional[str]]]) -> list[tuple[str, SetResult]]:
        """Run several chains, each as `runChain` does, in one run, and return all results in order.

        Run-scope settings (e.g. VM's autobias target) carry over between chains and are restored
        at the end. A chain that ends on a failed set does not stop later chains; ``stop()`` does.
        """
        chains = [
            (self._stimsetName(s), None if e is None else self._stimsetName(e)) for s, e in chains
        ]
        results = []
        with self._runScope(start=chains[0][0], end=chains[-1][1]) as run:
            for start, end in chains:
                if self.stopRequested:
                    break
                results += self._chain(start, end, run)
        return results

    def _chain(self, start: str, end: Optional[str], run: _Run) -> list[tuple[str, SetResult]]:
        results = []
        name = start
        indexEnd = end if end is not None and start.lower() < end.lower() else None
        while True:
            outcome = self._runSet(name, run)
            results.append((name, outcome.result))
            if outcome.endChain or self.stopRequested or not outcome.result.passed or name == end:
                break
            name, indexEnd = self._nextStimset(name, outcome.result, indexEnd)
            if name is None:
                break
        return results

    # ------------------------------------------------------------------ run / set

    @contextmanager
    def _runScope(self, start: str, end: Optional[str]):
        _requireWorkerThread()
        if not self._running.acquire(blocking=False):
            raise RuntimeError("StimsetRunner is already running")
        try:
            self._stopEvent.clear()
            if self.testPulse is not None:
                testPulse, tpSource = self.testPulse, 'given'
            else:
                testPulse, tpSource = testPulseFromClamp(self.clamp)
            runDir = None
            if self.storageDir is not None:
                runDir = self.storageDir.mkdir(
                    'AllenStimsets',
                    autoIncrement=True,
                    info={
                        'dirType': 'StimsetRun',
                        'start': start,
                        'end': end,
                        'clamp': self.clamp.name(),
                        'testPulse': _plain(testPulse),
                        'testPulseSource': tpSource,
                        'paramOverrides': _plain(self.paramOverrides),
                        'testPulseDuringIti': self.testPulseDuringIti,
                        'updateInterval': self.updateInterval,
                        'asyncQC': 'skipped',
                    },
                )
            run = _Run(dir=runDir, scope=AmplifierScope('run'), testPulse=testPulse)
            tpWasEnabled = self.clamp.testPulseEnabled()
            if self.testPulseDuringIti and not tpWasEnabled:
                self.clamp.enableTestPulse(True)
            self._emit('runStarted', start=start, end=end)
            try:
                yield run
            finally:
                try:
                    with self._exclusive('restoreRun'):
                        self.amp.restore(run.scope)
                finally:
                    if self.testPulseDuringIti and not tpWasEnabled:
                        # stop while paused but not reserved: a pulse waiting on the reservation then aborts
                        with self.clamp.testPulsePaused():
                            self.clamp.enableTestPulse(False, block=True)
                    if runDir is not None:
                        runDir.setInfo(
                            sets=run.sets,
                            stopped=self.stopRequested,
                            runAmplifierChanges=_plain(run.scope.changes),
                        )
                    self._emit('runFinished', sets=run.sets)
        finally:
            self._running.release()

    def _nextStimset(self, name: str, result: SetResult, indexEnd: Optional[str]):
        if indexEnd is not None and name.lower() < indexEnd.lower():
            names = sorted(self.stimsets, key=str.lower)
            return names[names.index(name) + 1], indexEnd
        if result.nextStimset is None:
            return None, None
        nxt = self._stimsetName(result.nextStimset, f"{name} names next stimset")
        indexEnd = result.nextIndexingEnd
        if indexEnd is not None:
            indexEnd = self._stimsetName(indexEnd, f"{name} names indexing end")
        return nxt, indexEnd

    def _stimsetName(self, name: str, what: str = "stimset") -> str:
        """Return the loaded stimset name matching *name* case-insensitively; KeyError if none."""
        if name in self.stimsets:
            return name
        matches = [k for k in self.stimsets if k.lower() == name.lower()]
        if len(matches) != 1:
            raise KeyError(f"{what} {name!r}, which is not loaded")
        return matches[0]

    def _functionClass(self, name: str, stimset: StimsetDef) -> type[AnalysisFunction]:
        if name in self.functions:
            return self.functions[name]
        if stimset.analysisFunction is None:
            raise ValueError(
                f"stimset {name} has no analysis function; pass one in functions={{...}}"
            )
        return functionFor(stimset.analysisFunction)

    def _runSet(self, name: str, run: _Run) -> _SetOutcome:
        stimset = self.stimsets[name]
        cls = self._functionClass(name, stimset)
        params = dict(stimset.params)
        params.update(self.paramOverrides.get(name, {}))
        modeRef = [cls.clampMode or self.clamp.getMode()]
        context = RunContext(
            autobiasTarget=self.amp.autobiasTarget,
            holding=lambda: self.amp.holding(modeRef[0]),
            commandLimit=(
                commandLimit(self.clamp, modeRef[0], self.manager)
                if modeRef[0] in ('VC', 'IC')
                else float('nan')
            ),
            stimsets=self.stimsets.__getitem__,
        )
        fn = cls(stimset, params, self.notebook, context)
        setRecord = self.notebook.newSet(name, cls.analysisType)
        fn.setRecord = setRecord
        setDir = None
        setInfo = {
            'dirType': 'StimsetSet',
            'stimset': name,
            'analysisFunction': cls.miesName or cls.__name__,
            'analysisType': cls.analysisType,
            'params': _plain(params),
            'sci': setRecord.sci,
        }
        if run.dir is not None:
            setDir = run.dir.mkdir(name, autoIncrement=True, info=setInfo)
        setScope = AmplifierScope(f"{name} set")
        self._emit('setStarted', stimset=name, sci=setRecord.sci)
        outcome = None
        mode = None
        try:
            try:
                setConfig = fn.preSet()
            except AbortSet as exc:
                outcome = self._abortedSet(name, 'preSet', exc, setInfo, setRecord)
                return outcome
            mode = setConfig.clampMode
            if mode not in ('VC', 'IC'):
                raise ValueError(f"{name}: preSet returned clamp mode {mode!r}")
            modeRef[0] = mode
            context.commandLimit = commandLimit(self.clamp, mode, self.manager)
            setInfo['setConfig'] = _plain(setConfig)
            with self._exclusive('preSet'):
                self.clamp.setMode(mode)
                self.amp.apply(setConfig.runAmplifier, mode, run.scope)
                self.amp.apply(setConfig.amplifier, mode, setScope)
            itiTp = self.testPulseDuringIti and setConfig.testPulseDuringIti
            setInfo['testPulseDuringIti'] = itiTp
            with nullcontext() if itiTp else self.clamp.testPulsePaused():
                outcome = self._runSweeps(
                    name, stimset, fn, setConfig, setRecord, setDir, setInfo, run
                )
            return outcome
        except Exception as exc:
            setInfo['error'] = repr(exc)
            raise
        finally:
            try:
                with self._exclusive('restoreSet'):
                    self.amp.restore(setScope)
                if (
                    outcome is not None
                    and outcome.result.runAmplifier.changes()
                    and mode is not None
                ):
                    with self._exclusive('postSet'):
                        self.amp.apply(outcome.result.runAmplifier, mode, run.scope)
            finally:
                setInfo['amplifierChanges'] = _plain(setScope.changes)
                if outcome is not None:
                    setInfo['result'] = _plain(outcome.result)
                    setInfo['endChain'] = outcome.endChain
                setInfo['sweeps'] = list(setRecord.sweeps)
                setInfo['stopped'] = self.stopRequested
                if setDir is not None:
                    setDir.setInfo(setInfo)
                self.notebook.save()
                run.sets.append(
                    {
                        'stimset': name,
                        'sci': setRecord.sci,
                        'passed': outcome.result.passed if outcome else None,
                    }
                )
                self._emit(
                    'setFinished',
                    stimset=name,
                    sci=setRecord.sci,
                    result=outcome.result if outcome else None,
                )

    def _abortedSet(
        self, name: str, event: str, exc: AbortSet, setInfo: dict, setRecord
    ) -> _SetOutcome:
        logger.warning(f"{name}: {event} aborted the set: {exc}")
        setInfo['abortSet'] = {'event': event, 'reason': str(exc)}
        setRecord.values[Keys.SET_QC] = False
        return _SetOutcome(SetResult(passed=False, values={'abortSet': str(exc)}), endChain=True)

    def _runSweeps(
        self, name, stimset, fn, setConfig: SetConfig, setRecord, setDir, setInfo, run
    ) -> _SetOutcome:
        mode = setConfig.clampMode
        dt = setConfig.sampleInterval
        testPulse = run.testPulse if setConfig.insertTestPulse else None
        endChain = False
        for i in range(stimset.numSweeps):
            if self.stopRequested:
                break
            layout = stimsetModule.buildSweep(
                stimset,
                i,
                1.0,
                dt,
                mode,
                testPulse,
                setConfig.userOnsetDelay,
                setConfig.terminationDelay,
            ).epochs
            try:
                cfg = fn.preSweep(i, layout)
            except AbortSet as exc:
                return self._abortedSet(name, f'preSweep({i})', exc, setInfo, setRecord)
            itiInfo = self._waitIti(run, cfg.iti)
            if self.stopRequested:
                break
            decision, stoppedByUser = self._runSweep(
                name, stimset, i, fn, cfg, setConfig, testPulse, setRecord, setDir, run, itiInfo
            )
            run.pendingIti = decision.iti if decision.iti is not None else stimset.iti
            run.pendingExtra += decision.extraIti
            if decision.action == 'abort':
                endChain = True
                break
            if decision.action != 'continue' or stoppedByUser:
                break
        result = fn.postSet()
        setRecord.values.update(result.values)
        if self.stopRequested:
            result = dataclasses.replace(result, passed=False)
            setRecord.values[Keys.SET_QC] = False
        setRecord.values.setdefault(Keys.SET_QC, bool(result.passed))
        return _SetOutcome(result, endChain)

    # ------------------------------------------------------------------ sweep

    def _waitIti(self, run: _Run, itiOverride: Optional[float]) -> dict:
        """Wait ITI + extra from the end of the last sweep's acquired data; return what was waited, s.

        The ITI is *itiOverride*, else the last SweepDecision.iti, else the stimset ITI.
        """
        iti = itiOverride if itiOverride is not None else run.pendingIti
        extra = run.pendingExtra
        run.pendingExtra = 0.0
        if run.lastSweepEnd is None:
            return {'iti': iti, 'extra': extra, 'waited': 0.0}
        wait = iti - (ptime.time() - run.lastSweepEnd) + extra
        self._emit('iti', iti=iti, extra=extra, wait=max(wait, 0.0))
        start = ptime.time()
        deadline = start + wait
        while not self.stopRequested:
            remaining = deadline - ptime.time()
            if remaining <= 0:
                break
            time.sleep(min(remaining, 0.05))
        return {'iti': iti, 'extra': extra, 'waited': ptime.time() - start}

    def _taskCommand(
        self, command: np.ndarray, mode: str, dt: float, holding: float, sweepDir
    ) -> dict:
        n = len(command)
        protocol = {'duration': n * dt * 1e-3, 'updateInterval': self.updateInterval}
        if sweepDir is not None:
            protocol.update(storeData=True, storageDir=sweepDir)
        return {
            'protocol': protocol,
            self.daqName: {'rate': 1e3 / dt, 'numPts': n, 'downsample': 1},
            self.clamp.name(): {
                'mode': mode,
                'command': command * siPerMiesUnit(mode, 'command') + holding,
                'recordSecondary': self.recordSecondary,
                'recordState': True,
            },
        }

    def _runSweep(
        self,
        name,
        stimset,
        setSweepIndex,
        fn,
        cfg: SweepConfig,
        setConfig,
        testPulse,
        setRecord,
        setDir,
        run,
        itiInfo,
    ):
        """Acquire one sweep and run midSweep/postSweep; return (SweepDecision, stoppedByUser)."""
        mode = setConfig.clampMode
        dt = setConfig.sampleInterval
        built = stimsetModule.buildSweep(
            stimset,
            setSweepIndex,
            cfg.dascale,
            dt,
            mode,
            testPulse,
            setConfig.userOnsetDelay,
            setConfig.terminationDelay,
        )
        epochs = built.epochs.copy()
        epochs.add(*cfg.userEpochs)
        command = np.array(built.command, dtype=float)
        n = len(command)
        sweepNo = self.notebook.nextSweepNumber()
        dataScale = 1.0 / siPerMiesUnit(mode, 'data')
        data = np.full(n, np.nan)
        sweepDir = setDir.mkdir('sweep', autoIncrement=True) if setDir is not None else None
        info = {
            'dirType': 'StimsetSweep',
            'stimset': name,
            'sweep': sweepNo,
            'sci': setRecord.sci,
            'setSweepIndex': setSweepIndex,
            'clampMode': mode,
            'sampleInterval': dt,
            'dascale': cfg.dascale,
            'stimsetStart': built.stimsetStart,
            'epochs': _plain(list(epochs)),
            'iti': itiInfo,
            'asyncQC': 'skipped',
            'midSweep': [],
            'earlyStop': None,
            'commandZero': None,
        }
        state = {'numValid': 0, 'zeroedAt': None, 'stoppedEarly': False}

        def sweepData():
            return SweepData(
                sweep=sweepNo,
                clampMode=mode,
                sampleInterval=dt,
                data=data,
                command=command,
                numValid=state['numValid'],
                epochs=epochs,
                dascale=cfg.dascale,
                stoppedEarly=state['stoppedEarly'],
                commandZeroedAt=state['zeroedAt'],
            )

        stoppedByUser = False
        q: queue.Queue = queue.Queue()
        with self._exclusive('sweep'):
            holding = self.clamp.getHolding(mode)
            info['holding'] = holding / siPerMiesUnit(mode, 'command')
            task = self.manager.createTask(self._taskCommand(command, mode, dt, holding, sweepDir))
            task.addPartialResultHandler(_PartialCopier(self.clamp.name(), q))
            self._emit(
                'sweepStarted',
                stimset=name,
                sweep=sweepNo,
                setSweepIndex=setSweepIndex,
                dascale=cfg.dascale,
            )
            result = None
            lastCalled = 0
            try:
                task.execute(block=False)
                while result is None:
                    done = task.isDone()
                    state['numValid'] = _drain(q, data, state['numValid'], dataScale, mode)
                    if self.stopRequested:
                        stoppedByUser = True
                        result = self._stopEarly(task, EarlyStop('stopped by user'), info, state, n)
                        break
                    if lastCalled < state['numValid'] < n:
                        lastCalled = state['numValid']
                        action = fn.midSweep(sweepData())
                        taken = self._midSweepAction(action, task, mode, command, info, state)
                        self._emit('midSweep', sweep=sweepNo, numValid=lastCalled, action=action)
                        if isinstance(action, EarlyStop) and taken:
                            result = self._stopEarly(task, action, info, state, n)
                            run.pendingExtra += action.extraIti
                            break
                    if done:
                        result = task.getResult()
                        break
                    time.sleep(0.01)
            except BaseException:
                if result is None:
                    task.stop(abort=True)
                raise
            finally:
                if state['zeroedAt'] is not None:
                    self.clamp.setMode(mode)

        if result is None or result.get(self.clamp.name()) is None:
            raise RuntimeError(
                f"{name} sweep {sweepNo}: task returned no {self.clamp.name()} result"
            )
        clampResult = result[self.clamp.name()]
        _checkUnits(clampResult.columnUnits(0, 'primary'), mode)
        primary = np.asarray(clampResult['primary'].asarray(), dtype=float)
        nAcq = min(len(primary), n)
        run.lastSweepEnd = task.startTime + nAcq * dt * 1e-3
        data[:nAcq] = primary[:nAcq] * dataScale
        data[nAcq:] = np.nan
        state['numValid'] = nAcq
        if not state['stoppedEarly'] and lastCalled < n:
            action = fn.midSweep(sweepData())
            if action is not None:
                info['midSweep'].append(
                    _actionInfo(action, n, dt, taken=False, note='sweep complete')
                )

        sd = sweepData()
        record = self.notebook.addSweep(sweepNo, setRecord.sci, cfg.dascale)
        decision = fn.postSweep(sd)
        record.values.setdefault(Keys.SWEEP_QC, bool(decision.sweepPassed))
        info['decision'] = _plain(decision)
        info['numValid'] = nAcq
        info['stoppedByUser'] = stoppedByUser
        info['notebook'] = _plain(record.values)
        info['partialResultErrors'] = list(getattr(task, 'partialResultErrors', []))
        self.notebook.save()
        if sweepDir is not None:
            sweepDir.setInfo(info)
        self._emit('sweepFinished', stimset=name, sweep=sweepNo, data=sd, decision=decision)
        return decision, stoppedByUser

    def _midSweepAction(self, action, task, mode, command, info, state) -> bool:
        """Record a midSweep result and carry out a ZeroCommand; return whether *action* was acted on."""
        if action is None:
            return False
        dt = info['sampleInterval']
        if isinstance(action, EarlyStop):
            info['midSweep'].append(_actionInfo(action, state['numValid'], dt, taken=True))
            return True
        if not isinstance(action, ZeroCommand):
            raise TypeError(f"midSweep returned {action!r}")
        if state['zeroedAt'] is not None:
            info['midSweep'].append(
                _actionInfo(action, state['numValid'], dt, taken=False, note='already zeroed')
            )
            return False
        if mode != 'IC':
            raise ValueError(f"ZeroCommand requires IC, not {mode}")
        requested = ptime.time()
        effective = self.clamp.switchToZeroCurrent()
        zeroedAt = (effective - task.startTime) * 1e3
        state['zeroedAt'] = zeroedAt
        command[min(int(zeroedAt / dt), len(command)) :] = 0.0
        info['commandZero'] = {
            'reason': action.reason,
            'requestedAt': (requested - task.startTime) * 1e3,
            'commandZeroedAt': zeroedAt,
            'mccLatency': (effective - requested) * 1e3,
            'numValidAtRequest': state['numValid'],
        }
        info['midSweep'].append(_actionInfo(action, state['numValid'], dt, taken=True))
        logger.info(
            f"ZeroCommand ({action.reason}) took effect at {zeroedAt:.1f} ms, MCC call {(effective - requested) * 1e3:.1f} ms"
        )
        return True

    def _stopEarly(self, task, action: EarlyStop, info: dict, state: dict, n: int):
        requested = ptime.time()
        truncated = task.stopEarly()
        result = task.getResult()
        stopTime = result['protocol'].get('stopTime')
        state['stoppedEarly'] = truncated
        info['earlyStop'] = {
            'reason': action.reason,
            'extraIti': action.extraIti,
            'requestedAt': (requested - task.startTime) * 1e3,
            'stopLatency': (ptime.time() - requested) * 1e3,  # includes storing the result
            'stoppedAt': _plain((stopTime - task.startTime) * 1e3 if stopTime else None),
            'numValidAtRequest': state['numValid'],
            'numPtsAcquired': _plain(result['protocol'].get('numPtsAcquired')),
            'truncated': truncated,
            'plannedPts': n,
        }
        return result

    # ------------------------------------------------------------------ helpers

    @contextmanager
    def _exclusive(self, label: str):
        """Pause the test pulse and reserve the clamp and DAQ (waits for a pulse in progress)."""
        with self.clamp.testPulsePaused():
            with self.manager.reserveDevices(
                [self.clamp, self.daqName], reserver=f"StimsetRunner.{label}"
            ):
                yield

    def _emit(self, event: str, **info) -> None:
        for fn in self._listeners:
            try:
                fn(event, info)
            except Exception:
                logger.exception(f"StimsetRunner listener {fn!r} failed on {event!r}")


def _drain(q: queue.Queue, data: np.ndarray, numValid: int, scale: float, mode: str) -> int:
    """Copy queued partial chunks into *data* (MIES units); return the new settled count."""
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            return numValid
        if item[0] == 'units':
            _checkUnits(item[1], mode)
            continue
        start, chunk = item
        end = min(start + len(chunk), len(data))
        data[start:end] = chunk[: end - start] * scale
        numValid = max(numValid, end)


def _checkUnits(units: str, mode: str) -> None:
    if units != _PRIMARY_UNITS[mode]:
        raise ValueError(f"primary signal is in {units!r}; {mode} needs {_PRIMARY_UNITS[mode]!r}")


def _actionInfo(action, numValid: int, dt: float, taken: bool, note: str = '') -> dict:
    return {
        'action': type(action).__name__,
        'reason': action.reason,
        'at': numValid * dt,  # ms of acquired data
        'taken': taken,
        'note': note,
    }


def _requireWorkerThread() -> None:
    app = Qt.QCoreApplication.instance()
    if app is not None and Qt.QThread.currentThread() == app.thread():
        raise RuntimeError("StimsetRunner blocks; run it on a worker thread, not the GUI thread")


def _plain(obj):
    """Return *obj* as nested dict/list/str/number for .index metadata."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, EpochTable):
        return [_plain(ep) for ep in obj]
    if isinstance(obj, dict) or hasattr(obj, 'items') and callable(obj.items):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return _plain(obj.item())
    if isinstance(obj, float) and not np.isfinite(obj):
        return None  # .index files cannot read nan/inf back
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return repr(obj)
