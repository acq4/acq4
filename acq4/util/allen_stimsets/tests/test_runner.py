"""StimsetRunner on the mock NiDAQ with a fake MultiClamp and scripted analysis functions."""

import logging
import threading
import time
from contextlib import contextmanager

import numpy as np
import pytest

from acq4.Manager import Task as ManagerTask
from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    FakeManager,
    WaveDAQ,
    readerThreads,
    waitUntil,
)
from acq4.devices.MultiClamp.multiclamp import MultiClampTask
from acq4.util import ptime
from acq4.util.allen_stimsets import stimset as stimsetModule
from acq4.util.allen_stimsets.amplifier import AmplifierControl, AmplifierScope, commandLimit
from acq4.util.allen_stimsets.core import (
    AbortSet,
    AmplifierSettings,
    EarlyStop,
    Epoch,
    EpochTable,
    SetConfig,
    SetResult,
    SweepConfig,
    SweepDecision,
    ZeroCommand,
)
from acq4.util.allen_stimsets.core import TestPulseSettings as TpSettings
from acq4.util.allen_stimsets.functions.base import AnalysisFunction
from acq4.util.allen_stimsets.notebook import Keys, Notebook
from acq4.util.allen_stimsets import amplifier as amplifierModule
from acq4.util.allen_stimsets import runner as runnerModule
from acq4.util.allen_stimsets.runner import StimsetRunner
from acq4.util.allen_stimsets.stimset import EpochDef, StimsetDef, SweepCommand

AI0, AO = '/Dev1/ai0', '/Dev1/ao0'
DT = 0.05  # ms (20 kHz)
SCALE = {'VC': 1e-9, 'IC': 0.1}  # primary SI per DAQ volt
EXT_CMD = {'VC': 0.02, 'IC': 4e-10}


def primaryWave(n, rate):
    return 0.01 * np.sin(np.arange(n) / rate * 2 * np.pi * 10)


# ---------------------------------------------------------------- fakes


class _Mc:
    def __init__(self, clamp):
        self.clamp = clamp

    def setParam(self, name, value):
        self.clamp.setParam(name, value)

    def setParams(self, params):
        for k, v in params.items():
            self.clamp.setParam(k, v)

    def getParams(self, names):
        return {n: self.clamp.params[self.clamp.mode].get(n, 0.0) for n in names}


class FakeClamp:
    """The parts of MultiClamp/PatchClamp that MultiClampTask and StimsetRunner use."""

    def __init__(self, dm, name='Clamp1'):
        self._name = name
        self.logger = logging.getLogger(f'acq4.device.test.{name}')
        self.config = {
            'primaryChannel': {'device': 'DAQ', 'channel': AI0, 'type': 'ai'},
            'commandChannel': {'device': 'DAQ', 'channel': AO, 'type': 'ao'},
        }
        self.mc = _Mc(self)
        self.mode = 'I=0'
        self.holding = {'VC': -0.07, 'IC': 0.0}
        self.params = {
            'VC': {'HoldingEnable': False, 'PipetteOffset': 0.01, 'PrimarySignalLPF': 10e3},
            'IC': {
                'HoldingEnable': True,
                'BridgeBalEnable': True,
                'BridgeBalResist': 15e6,
                'NeutralizationEnable': False,
                'NeutralizationCap': 0.0,
                'PrimarySignalLPF': 10e3,
                'PipetteOffset': 0.01,
            },
        }
        self.tpEnabled = False
        self.tpPauses = 0
        self.autoBias = {'enabled': False, 'target': -0.07}
        self.modeLog = []
        self.zeroCalls = 0
        dm.devices[name] = self

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return MultiClampTask(self, cmd, parentTask)

    def getDAQName(self, channel):
        return self.config[f'{channel}Channel']['device']

    def getMode(self):
        return self.mode

    def setMode(self, mode):
        if mode != self.mode:
            self.modeLog.append(mode)
        self.mode = mode

    def getHolding(self, mode=None):
        mode = mode or self.mode
        return 0.0 if mode == 'I=0' else self.holding[mode]

    def setHolding(self, mode=None, value=None):
        if mode is not None and value is not None:
            self.holding[mode] = value

    def getParam(self, name):
        return self.params[self.mode][name]

    def setParam(self, name, value):
        assert name in self.params[self.mode], (name, self.mode)
        self.params[self.mode][name] = value

    def autoPipetteOffset(self):
        self.params[self.mode]['PipetteOffset'] = 0.002

    def autoBridgeBalance(self):
        self.params['IC']['BridgeBalResist'] = 22e6

    def getLastState(self, mode=None):
        mode = mode or self.mode
        iv = 'VC' if mode == 'VC' else 'IC'
        return {
            'mode': mode,
            'primaryScaleFactor': SCALE[iv],
            'primaryUnits': 'A' if iv == 'VC' else 'V',
            'extCmdScale': EXT_CMD[iv],
        }

    def extCmdScale(self, mode):
        return EXT_CMD[mode]

    def testPulseEnabled(self):
        return self.tpEnabled

    def enableTestPulse(self, enable=True, block=False):
        self.tpEnabled = enable

    @contextmanager
    def testPulsePaused(self):
        self.tpPauses += 1
        try:
            yield
        finally:
            self.tpPauses -= 1

    def autoBiasEnabled(self):
        return self.autoBias['enabled']

    def enableAutoBias(self, enable=True):
        self.autoBias['enabled'] = enable

    def autoBiasTarget(self):
        return self.autoBias['target']

    def setAutoBiasTarget(self, v):
        self.autoBias['target'] = v

    tpParams = {'vcPulseDuration': 10e-3, 'vcPreDuration': 5e-3, 'vcPostDuration': 5e-3}

    def getTestPulseParameter(self, name):
        return self.tpParams[name]

    def switchToZeroCurrent(self):
        assert self.mode == 'IC'
        self.zeroCalls += 1
        self.setMode('I=0')
        return ptime.time()


class RunnerManager(FakeManager):
    class _Lock:
        def lock(self):
            pass

        def unlock(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def createTask(self, cmd):
        return ManagerTask(self, cmd)

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return self._Lock()


def fakeBuildSweep(
    stimset,
    setSweepIndex,
    dascale,
    sampleInterval,
    clampMode,
    testPulse,
    userOnsetDelay=0.0,
    terminationDelay=0.0,
):
    """Square epochs after an 'ST' epoch with NaN amplitude, no test pulse; amplitude x DAScale."""
    epochs = EpochTable([Epoch('ST', 0.0, sum(ep.duration for ep in stimset.epochs))])
    t = 0.0
    pieces = []
    for i, ep in enumerate(stimset.epochs):
        n = int(round(ep.duration / sampleInterval))
        pieces.append(np.full(n, ep.amplitude * dascale))
        epochs.add(Epoch(f'E{i}', t, t + ep.duration, ep.amplitude * dascale))
        t += ep.duration
    return SweepCommand(np.concatenate(pieces), sampleInterval, epochs, 0.0)


def makeStimset(name, numSweeps=2, iti=0.0, duration=200.0, amplitude=5.0, af='Scripted'):
    epochs = [
        EpochDef('square', duration / 4),
        EpochDef('square', duration / 2, amplitude),
        EpochDef('square', duration / 4),
    ]
    return StimsetDef(name=name, epochs=epochs, numSweeps=numSweeps, iti=iti, analysisFunction=af)


def scripted(
    mode='VC',
    amplifier=None,
    runAmplifier=None,
    mid=None,
    post=None,
    preSweep=None,
    preSet=None,
    postSet=None,
    log=None,
):
    """Return an AnalysisFunction class whose events are given callables; every call is logged."""
    log = log if log is not None else []

    class Scripted(AnalysisFunction):
        miesName = 'Scripted'
        analysisType = 'XX'
        clampMode = mode
        calls = log

        def preSet(self):
            log.append(('preSet',))
            if preSet is not None:
                return preSet(self)
            return SetConfig(
                clampMode=mode,
                sampleInterval=DT,
                amplifier=amplifier or AmplifierSettings(),
                runAmplifier=runAmplifier or AmplifierSettings(),
            )

        def preSweep(self, i, layout):
            log.append(('preSweep', i, [ep.name for ep in layout]))
            if preSweep is not None:
                return preSweep(self, i)
            return SweepConfig(dascale=2.0, userEpochs=[Epoch('U_X', 1.0, 2.0)])

        def midSweep(self, data):
            valid = data.data[: data.numValid]
            log.append(
                (
                    'midSweep',
                    data.numValid,
                    len(data.data),
                    bool(np.all(np.isnan(data.data[data.numValid :]))),
                    bool(np.all(np.isfinite(valid))),
                )
            )
            return mid(self, data) if mid is not None else None

        def postSweep(self, data):
            log.append(('postSweep', data))
            if post is not None:
                return post(self, data)
            return SweepDecision(sweepPassed=True, action='continue')

        def postSet(self):
            log.append(('postSet',))
            if postSet is not None:
                return postSet(self)
            return SetResult(passed=True)

    return Scripted


@pytest.fixture
def rig(tmp_path):
    from acq4.util import DataManager

    dm = RunnerManager()
    WaveDAQ(dm, waves={AI0: primaryWave})
    clamp = FakeClamp(dm)
    storage = DataManager.getDirHandle(str(tmp_path / 'cell'), create=True)
    notebook = Notebook(tmp_path / 'cell' / 'notebook.json')
    yield dm, clamp, storage, notebook
    waitUntil(lambda: readerThreads() == [])


@pytest.fixture(autouse=True)
def _fakeBuild(monkeypatch):
    monkeypatch.setattr(stimsetModule, 'buildSweep', fakeBuildSweep)
    # pytest's thread is the GUI thread once any test has made a QApplication
    monkeypatch.setattr(runnerModule, '_requireWorkerThread', lambda: None)


def makeRunner(rig, stimsets, functions, **kw):
    dm, clamp, storage, notebook = rig
    return StimsetRunner(
        clamp,
        stimsets,
        notebook,
        storage,
        manager=dm,
        functions=functions,
        updateInterval=0.03,
        **kw,
    )


def calls(fn, name):
    return [c for c in fn.calls if c[0] == name]


# ---------------------------------------------------------------- tests


def test_vc_set_events_data_storage_and_notebook(rig):
    dm, clamp, storage, notebook = rig

    def post(self, data):
        self.notebook.sweep(data.sweep).values[Keys.SPIKE_COUNT] = data.sweep
        return SweepDecision(sweepPassed=True, action='continue')

    fn = scripted(
        'VC', post=post, postSet=lambda self: SetResult(True, values={Keys.FINAL_SCALE: 3.0})
    )
    runner = makeRunner(rig, {'S': makeStimset('S')}, {'S': fn})
    events = []
    runner.addListener(lambda ev, info: events.append(ev))
    result = runner.runSet('S')

    assert result.passed
    assert [c[0] for c in fn.calls if c[0] != 'midSweep'] == [
        'preSet',
        'preSweep',
        'postSweep',
        'preSweep',
        'postSweep',
        'postSet',
    ]
    assert calls(fn, 'preSweep')[0][2] == ['ST', 'E0', 'E1', 'E2']
    mids = calls(fn, 'midSweep')
    n = int(200 / DT)
    assert all(m[2] == n and m[3] and m[4] for m in mids)
    assert any(m[1] < n for m in mids)  # partial calls
    assert sum(m[1] == n for m in mids) == 2  # one full-data call per sweep

    data = calls(fn, 'postSweep')[0][1]
    assert data.complete and data.numValid == n and data.dascale == 2.0
    assert data.clampMode == 'VC' and data.sampleInterval == DT
    expected = primaryWave(n, 1e3 / DT) * SCALE['VC'] * 1e12  # pA
    np.testing.assert_allclose(data.data, expected, rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(data.command[n // 2], 5.0 * 2.0)  # mV, no holding
    assert data.epochs.has('U_X') and data.epochs.get('E1').amplitude == 10.0

    assert [r.sweep for r in notebook.sweeps()] == [0, 1]
    assert all(r.values[Keys.SWEEP_QC] for r in notebook.sweeps())
    assert notebook.set(0).values == {Keys.FINAL_SCALE: 3.0, Keys.SET_QC: True}
    assert [r.values[Keys.SPIKE_COUNT] for r in notebook.sweeps()] == [0, 1]
    assert (notebook.path).exists()

    runDir = storage['AllenStimsets_000']
    assert runDir.info()['dirType'] == 'StimsetRun' and runDir.info()['asyncQC'] == 'skipped'
    setDir = runDir['S_000']
    assert setDir.info()['dirType'] == 'StimsetSet' and setDir.info()['result']['passed'] is True
    sweepDir = setDir['sweep_000']
    sweepDir._index = None  # read back from the file
    info = sweepDir.info()
    assert (
        info['dascale'] == 2.0 and info['sweep'] == 0 and info['decision']['action'] == 'continue'
    )
    assert [e['name'] for e in info['epochs']] == ['ST', 'E0', 'E1', 'E2', 'U_X']
    assert info['holding'] == pytest.approx(-70.0)
    assert sweepDir.exists('Clamp1.ma')
    stored = sweepDir['Clamp1.ma'].read()
    np.testing.assert_allclose(stored['primary'].asarray(), expected * 1e-12, rtol=1e-6, atol=1e-18)
    np.testing.assert_allclose(stored['command'].asarray()[n // 2], (10.0e-3 - 0.07), rtol=1e-6)

    assert clamp.mode == 'VC'
    assert clamp.tpEnabled is False and clamp.tpPauses == 0
    assert events[0] == 'runStarted' and events[-1] == 'runFinished' and 'iti' in events


def test_early_stop_truncates_and_extends_iti(rig):
    dm, clamp, storage, notebook = rig
    n = int(1000 / DT)

    def mid(self, data):
        if data.numValid > n // 5 and not getattr(self, 'stopped', False):
            self.stopped = True
            return EarlyStop('baseline passed', extraIti=0.2)

    fn = scripted('VC', mid=mid)
    stim = makeStimset('S', numSweeps=2, iti=0.0, duration=1000.0)
    runner = makeRunner(rig, {'S': stim}, {'S': fn})
    t0 = time.time()
    runner.runSet('S')
    elapsed = time.time() - t0

    first = calls(fn, 'postSweep')[0][1]
    assert first.stoppedEarly and n // 5 < first.numValid < n
    assert np.all(np.isnan(first.data[first.numValid :])) and np.all(
        np.isfinite(first.data[: first.numValid])
    )
    info = storage['AllenStimsets_000']['S_000']['sweep_000'].info()
    assert (
        info['earlyStop']['reason'] == 'baseline passed' and info['earlyStop']['truncated'] is True
    )
    stored = storage['AllenStimsets_000']['S_000']['sweep_000']['Clamp1.ma'].read()
    assert stored.shape[1] == first.numValid
    # stimset ITI 0: the second sweep waits extraIti after the end of the acquired data
    iti = storage['AllenStimsets_000']['S_000']['sweep_001'].info()['iti']
    assert iti['extra'] == pytest.approx(0.2)
    assert 0.0 <= iti['waited'] <= 0.2
    starts = [
        storage['AllenStimsets_000']['S_000'][f'sweep_00{i}']['Clamp1.ma']
        .read()
        ._info[-1]['startTime']
        for i in range(2)
    ]
    assert starts[1] - starts[0] == pytest.approx(first.numValid * DT * 1e-3 + 0.2, abs=0.15)
    assert elapsed < 3.0


def test_zero_command_switches_to_i0_and_restores_ic(rig):
    dm, clamp, storage, notebook = rig
    n = int(400 / DT)

    def mid(self, data):
        if data.numValid > n // 3 and data.commandZeroedAt is None:
            return ZeroCommand('5 spikes')

    fn = scripted('IC', mid=mid)
    runner = makeRunner(
        rig, {'R': makeStimset('R', numSweeps=1, duration=400.0, amplitude=100.0)}, {'R': fn}
    )
    runner.runSet('R')

    assert clamp.zeroCalls == 1
    assert clamp.modeLog[-2:] == ['I=0', 'IC'] and clamp.mode == 'IC'
    data = calls(fn, 'postSweep')[0][1]
    assert data.complete and not data.stoppedEarly
    z = data.commandZeroedAt
    assert z is not None and n // 3 * DT <= z < 400
    idx = int(z / DT)
    assert np.all(data.command[idx:] == 0) and data.command[idx - 1] == 200.0
    # later midSweep calls see the zeroed sweep
    assert any(m[1] == n for m in calls(fn, 'midSweep'))
    info = storage['AllenStimsets_000']['R_000']['sweep_000'].info()
    assert info['commandZero']['commandZeroedAt'] == pytest.approx(z)
    assert info['commandZero']['mccLatency'] >= 0


def test_zero_command_in_vc_raises_and_releases(rig):
    dm, clamp, storage, notebook = rig
    fn = scripted('VC', mid=lambda self, data: ZeroCommand('no'))
    runner = makeRunner(rig, {'S': makeStimset('S', numSweeps=1)}, {'S': fn})
    with pytest.raises(ValueError, match='requires IC'):
        runner.runSet('S')
    assert clamp.tpPauses == 0
    assert 'error' in storage['AllenStimsets_000']['S_000'].info()


def test_iti_override_and_extra(rig):
    dm, clamp, storage, notebook = rig

    def post(self, data):
        return SweepDecision(sweepPassed=True, action='continue', iti=0.6, extraIti=0.1)

    def preSweep(self, i):
        return SweepConfig(dascale=1.0, iti=0.9 if i == 2 else None)

    fn = scripted('VC', post=post, preSweep=preSweep)
    runner = makeRunner(
        rig, {'S': makeStimset('S', numSweeps=3, iti=5.0, duration=100.0)}, {'S': fn}
    )
    runner.runSet('S')
    sweeps = storage['AllenStimsets_000']['S_000']
    starts = [sweeps[f'sweep_00{i}']['Clamp1.ma'].read()._info[-1]['startTime'] for i in range(3)]
    i1, i2 = sweeps['sweep_001'].info()['iti'], sweeps['sweep_002'].info()['iti']
    assert i1['iti'] == 0.6 and i1['extra'] == pytest.approx(
        0.1
    )  # decision.iti replaces the stimset's 5 s
    assert i2['iti'] == 0.9  # SweepConfig.iti wins over decision.iti
    # ITI + extra after each 100 ms sweep
    assert starts[1] - starts[0] == pytest.approx(0.8, abs=0.15)
    assert starts[2] - starts[1] == pytest.approx(1.1, abs=0.15)


def test_set_end_and_chain(rig):
    dm, clamp, storage, notebook = rig
    log = []
    post = lambda self, data: SweepDecision(sweepPassed=True, action='endSetPassed')
    stimsets = {k: makeStimset(k, numSweeps=3, duration=60.0) for k in ['A', 'X1', 'X2', 'X3', 'Z']}
    fns = {
        'A': scripted(
            'VC',
            post=post,
            log=log,
            postSet=lambda self: SetResult(True, nextStimset='X1', nextIndexingEnd='X3'),
        ),
        'X1': scripted('VC', post=post, log=log),
        'X2': scripted('IC', post=post, log=log),
        'X3': scripted(
            'IC', post=post, log=log, postSet=lambda self: SetResult(True, nextStimset='Z')
        ),
        'Z': scripted(
            'IC', post=post, log=log, postSet=lambda self: SetResult(False, nextStimset='A')
        ),
    }
    runner = makeRunner(rig, stimsets, fns)
    results = runner.runChain('A')
    assert [name for name, _ in results] == ['A', 'X1', 'X2', 'X3', 'Z']
    assert sum(1 for c in log if c[0] == 'postSweep') == 5  # one sweep per set
    assert [s.stimset for s in notebook.sets()] == ['A', 'X1', 'X2', 'X3', 'Z']
    assert notebook.set(4).values[Keys.SET_QC] is False

    runner2 = makeRunner(rig, stimsets, fns)
    assert [n for n, _ in runner2.runChain('A', end='X2')] == ['A', 'X1', 'X2']
    assert storage.exists('AllenStimsets_001')


def test_chain_end_after_start_indexes(rig):
    post = lambda self, data: SweepDecision(sweepPassed=True, action='endSetPassed')
    names = ['X0', 'X1', 'x2', 'X3', 'Z']
    stimsets = {k: makeStimset(k, numSweeps=1, duration=60.0) for k in names}
    fns = {k: scripted('IC', post=post) for k in names}
    # X0 names X1 as next stimset and nothing after it: indexing alone reaches X3
    fns['X0'] = scripted('IC', post=post, postSet=lambda self: SetResult(True, nextStimset='X1'))
    results = makeRunner(rig, stimsets, fns).runChain('x0', 'x3')
    assert [n for n, _ in results] == ['X0', 'X1', 'x2', 'X3']
    with pytest.raises(KeyError, match='not loaded'):
        makeRunner(rig, stimsets, fns).runChain('X9')


def test_run_chains_share_one_run(rig):
    dm, clamp, storage, notebook = rig
    before = clamp.autoBiasTarget()
    seen = {}
    fns = {
        'A': scripted(
            'IC',
            post=lambda s, d: SweepDecision(True, 'endSetFailed'),
            postSet=lambda s: SetResult(
                False, runAmplifier=AmplifierSettings(autobiasEnabled=True, autobiasTarget=-61.0)
            ),
        ),
        'C': scripted(
            'IC',
            post=lambda s, d: seen.setdefault('C', s.context.autobiasTarget())
            and SweepDecision(True, 'endSetPassed'),
        ),
    }
    stimsets = {k: makeStimset(k, 1, duration=60.0) for k in ['A', 'C']}
    results = makeRunner(rig, stimsets, fns).runChains([('A', None), ('C', None)])
    assert [n for n, _ in results] == ['A', 'C']  # A's failed chain does not skip C
    assert seen['C'] == pytest.approx(-61.0)  # run scope carried into the second chain
    assert clamp.autoBiasTarget() == pytest.approx(before)  # restored at run end
    assert storage.exists('AllenStimsets_000') and not storage.exists('AllenStimsets_001')


def test_abort_decision_ends_chain_after_post_set(rig):
    dm, clamp, storage, notebook = rig
    log = []
    stimsets = {k: makeStimset(k, numSweeps=3, duration=60.0) for k in ['A', 'B']}
    fns = {
        'A': scripted(
            'VC',
            log=log,
            post=lambda s, d: SweepDecision(False, 'abort'),
            postSet=lambda s: SetResult(True, nextStimset='B'),
        ),
        'B': scripted('VC', log=log),
    }
    results = makeRunner(rig, stimsets, fns).runChain('A')
    assert [n for n, _ in results] == ['A']
    assert [c[0] for c in log if c[0] != 'midSweep'] == [
        'preSet',
        'preSweep',
        'postSweep',
        'postSet',
    ]
    assert notebook.sweep(0).values[Keys.SWEEP_QC] is False


def test_abort_set_in_pre_set(rig):
    dm, clamp, storage, notebook = rig

    def preSet(self):
        raise AbortSet('wrong clamp mode')

    fn = scripted('VC', preSet=preSet)
    results = makeRunner(rig, {'A': makeStimset('A'), 'B': makeStimset('B')}, {'A': fn}).runChain(
        'A'
    )
    assert results[0][1].passed is False and len(results) == 1
    assert [c[0] for c in fn.calls] == ['preSet']
    assert storage['AllenStimsets_000']['A_000'].info()['abortSet']['reason'] == 'wrong clamp mode'
    assert notebook.set(0).values[Keys.SET_QC] is False


def test_stop_ends_sweep_early_and_run(rig):
    dm, clamp, storage, notebook = rig
    fn = scripted('VC')
    runner = makeRunner(rig, {'S': makeStimset('S', numSweeps=3, duration=2000.0)}, {'S': fn})
    threading.Timer(0.5, runner.stop).start()
    t0 = time.time()
    result = runner.runSet('S')
    assert time.time() - t0 < 1.8
    assert result.passed is False and notebook.set(0).values[Keys.SET_QC] is False
    posts = calls(fn, 'postSweep')
    assert len(posts) == 1 and posts[0][1].stoppedEarly
    assert calls(fn, 'postSet')
    info = storage['AllenStimsets_000']['S_000']['sweep_000'].info()
    assert info['stoppedByUser'] is True and info['earlyStop']['reason'] == 'stopped by user'
    assert storage['AllenStimsets_000'].info()['stopped'] is True


def test_amplifier_scopes_restored(rig):
    dm, clamp, storage, notebook = rig
    clamp.mode = 'IC'
    clamp.holding['IC'] = 30e-12
    setAmp = AmplifierSettings(
        holdingEnabled=False,
        bridgeBalanceEnabled=True,
        bridgeBalance='auto',
        capNeutralizationEnabled=True,
        capNeutralization=2.5,
        besselFilter=6000.0,
        pipetteOffset='auto',
    )
    runAmp = AmplifierSettings(autobiasEnabled=True, autobiasTarget=-65.0)
    seen = {}

    def post(self, data):
        seen['holding'] = self.context.holding()
        seen['autobias'] = self.context.autobiasTarget()
        seen['params'] = dict(clamp.params['IC'])
        seen['limit'] = self.context.commandLimit
        return SweepDecision(True, 'endSetPassed')

    fns = {
        'A': scripted(
            'IC',
            amplifier=setAmp,
            runAmplifier=runAmp,
            post=post,
            postSet=lambda s: SetResult(
                True, nextStimset='B', runAmplifier=AmplifierSettings(autobiasTarget=-60.0)
            ),
        ),
        'B': scripted(
            'IC',
            post=lambda s, d: seen.setdefault('B', s.context.autobiasTarget())
            and SweepDecision(True, 'endSetPassed'),
        ),
    }
    before = {m: dict(p) for m, p in clamp.params.items()}
    runner = makeRunner(
        rig, {'A': makeStimset('A', 1, duration=60.0), 'B': makeStimset('B', 1, duration=60.0)}, fns
    )
    runner.runChain('A')

    assert seen['holding'] == 0.0 and seen['autobias'] == pytest.approx(-65.0)
    assert seen['params']['HoldingEnable'] is False and seen['params']['BridgeBalResist'] == 22e6
    assert (
        seen['params']['NeutralizationCap'] == pytest.approx(2.5e-12)
        and seen['params']['PrimarySignalLPF'] == 6000.0
    )
    assert seen['params']['PipetteOffset'] == 0.002
    assert seen['limit'] == pytest.approx(10 * 4e-10 * 1e12)
    assert seen['B'] == pytest.approx(-60.0)  # SetResult.runAmplifier kept into the next set
    # auto calibrations are kept; everything else is restored
    assert clamp.params['IC'].pop('PipetteOffset') == 0.002
    assert clamp.params['IC'].pop('BridgeBalResist') == 22e6
    for p in ('PipetteOffset', 'BridgeBalResist'):
        before['IC'].pop(p)
    assert clamp.params == before and clamp.holding['IC'] == 30e-12
    assert clamp.autoBias == {'enabled': False, 'target': -0.07}
    changes = storage['AllenStimsets_000']['A_000'].info()['amplifierChanges']
    assert {c['name'] for c in changes} >= {
        'HoldingEnable',
        'holding',
        'BridgeBalResist',
        'PipetteOffset',
    }


def test_restore_on_exception(rig):
    dm, clamp, storage, notebook = rig
    clamp.mode = 'IC'

    def mid(self, data):
        raise RuntimeError('analysis bug')

    fn = scripted(
        'IC',
        amplifier=AmplifierSettings(besselFilter=3000.0),
        runAmplifier=AmplifierSettings(autobiasEnabled=True),
        mid=mid,
    )
    runner = makeRunner(rig, {'A': makeStimset('A', 1, duration=1000.0)}, {'A': fn})
    t0 = time.time()
    with pytest.raises(RuntimeError, match='analysis bug'):
        runner.runSet('A')
    assert time.time() - t0 < 0.9  # task aborted, not run to the end
    assert clamp.params['IC']['PrimarySignalLPF'] == 10e3
    assert clamp.autoBias['enabled'] is False
    assert clamp.tpEnabled is False and clamp.tpPauses == 0


def test_restore_switches_mode_for_other_mode_params(rig):
    dm, clamp, storage, notebook = rig
    clamp.mode = 'VC'
    control = AmplifierControl(clamp)
    scope = AmplifierScope('test')
    control.apply(AmplifierSettings(besselFilter=2000.0, holding=-50.0), 'VC', scope)
    assert clamp.params['VC']['PrimarySignalLPF'] == 2000.0 and clamp.holding[
        'VC'
    ] == pytest.approx(-0.05)
    clamp.setMode('IC')
    control.restore(scope)
    assert clamp.params['VC']['PrimarySignalLPF'] == 10e3 and clamp.holding['VC'] == pytest.approx(
        -0.07
    )
    assert clamp.mode == 'IC' and clamp.modeLog[-2:] == ['VC', 'IC']
    assert not scope


def test_amplifier_rejects_ic_settings_in_vc(rig):
    dm, clamp, storage, notebook = rig
    clamp.mode = 'VC'
    with pytest.raises(ValueError, match='only in IC'):
        AmplifierControl(clamp).apply(
            AmplifierSettings(bridgeBalance='auto'), 'VC', AmplifierScope('t')
        )
    assert commandLimit(clamp, 'VC', dm) == pytest.approx(200.0)


def test_autobias_target_read_while_disabled(rig):
    dm, clamp, storage, notebook = rig
    assert clamp.autoBias['enabled'] is False
    assert AmplifierControl(clamp).autobiasTarget() == pytest.approx(-70.0)


def test_requires_function_for_stimset_without_one(rig):
    runner = makeRunner(rig, {'S': makeStimset('S', af=None)}, {})
    with pytest.raises(ValueError, match='no analysis function'):
        runner.runSet('S')


def test_test_pulse_runs_unpaused_during_iti(rig):
    dm, clamp, storage, notebook = rig
    seen = []
    runner = makeRunner(
        rig, {'S': makeStimset('S', numSweeps=2, iti=0.3, duration=60.0)}, {'S': scripted('VC')}
    )
    runner.addListener(lambda ev, info: seen.append((ev, clamp.tpEnabled, clamp.tpPauses)))
    runner.runSet('S')
    assert ('iti', True, 0) in seen
    assert ('sweepStarted', True, 1) in seen  # paused while acquiring


def test_test_pulse_thread_pause_holds_the_loop():
    from types import SimpleNamespace

    from acq4.devices.PatchClamp import testpulse
    from acq4.util import Qt

    Qt.QApplication.instance() or Qt.QApplication([])
    thread = testpulse.TestPulseThread.__new__(testpulse.TestPulseThread)
    Qt.QThread.__init__(thread)
    thread._stop = False
    thread._pauseCount = 0
    thread._pauseLock = threading.Lock()
    thread._params = {'interval': None}
    thread._clampDev = SimpleNamespace(logger=logging.getLogger(__name__))
    runs = []
    thread.runOnce = lambda checkStop=False: (runs.append(1), time.sleep(0.005))
    worker = threading.Thread(target=thread.run)
    worker.start()
    try:
        waitUntil(lambda: len(runs) > 2)
        thread.pause()
        thread.pause()
        time.sleep(0.02)
        count = len(runs)
        time.sleep(0.1)
        assert len(runs) == count
        thread.resume()
        time.sleep(0.05)
        assert len(runs) == count and thread.isPaused()
        thread.resume()
        waitUntil(lambda: len(runs) > count)
        with pytest.raises(RuntimeError):
            thread.resume()
    finally:
        thread._stop = True
        worker.join(5)
    assert not worker.is_alive()


def test_set_without_iti_test_pulse_keeps_it_paused(rig):
    dm, clamp, storage, notebook = rig
    seen = []

    def preSet(self):
        return SetConfig(clampMode='VC', sampleInterval=DT, testPulseDuringIti=False)

    runner = makeRunner(
        rig,
        {'S': makeStimset('S', numSweeps=2, iti=0.3, duration=60.0)},
        {'S': scripted('VC', preSet=preSet)},
    )
    runner.addListener(lambda ev, info: seen.append((ev, clamp.tpPauses)))
    runner.runSet('S')
    assert ('iti', 1) in seen and ('sweepStarted', 2) in seen
    assert clamp.tpPauses == 0
    assert storage['AllenStimsets_000']['S_000'].info()['testPulseDuringIti'] is False


def test_inserted_test_pulse_from_clamp(rig, monkeypatch):
    dm, clamp, storage, notebook = rig
    used = []

    def build(stimset, i, dascale, dt, mode, testPulse, *args):
        used.append(testPulse)
        return fakeBuildSweep(stimset, i, dascale, dt, mode, testPulse, *args)

    monkeypatch.setattr(stimsetModule, 'buildSweep', build)
    clamp.tpParams = dict(clamp.tpParams, icAmplitude=-20e-12)
    makeRunner(rig, {'S': makeStimset('S', numSweeps=1)}, {'S': scripted('VC')}).runSet('S')
    tp = used[-1]
    assert tp.pulseDuration == pytest.approx(10.0) and tp.baselineFraction == pytest.approx(0.25)
    assert (
        tp.amplitudeIC == pytest.approx(-20.0) and tp.amplitudeVC == 10.0
    )  # VC amplitude: default
    source = storage['AllenStimsets_000'].info()['testPulseSource']
    assert source['amplitudeVC'] == 'default' and source['amplitudeIC'] == 'clamp:icAmplitude'

    clamp.tpParams = {'vcPulseDuration': 20e-3, 'vcPreDuration': 5e-3, 'vcPostDuration': 8e-3}
    tp, source = amplifierModule.testPulseFromClamp(clamp)
    assert tp.pulseDuration == pytest.approx(20.0) and tp.baselineFraction == 0.35
    assert source['baselineFraction'] == 'default'

    given = TpSettings(5.0, 0.3, 7.0, -30.0)
    makeRunner(
        rig, {'S': makeStimset('S', numSweeps=1)}, {'S': scripted('VC')}, testPulse=given
    ).runSet('S')
    assert used[-1] is given
    assert storage['AllenStimsets_001'].info()['testPulseSource'] == 'given'


def test_auto_calibration_outlives_older_scope_entries(rig):
    dm, clamp, storage, notebook = rig
    clamp.mode = 'IC'
    control = AmplifierControl(clamp)
    run, setScope = AmplifierScope('run'), AmplifierScope('set')
    control.apply(AmplifierSettings(bridgeBalance=10.0), 'IC', run)
    control.apply(AmplifierSettings(bridgeBalance='auto'), 'IC', setScope)
    later = AmplifierScope('later')
    control.apply(AmplifierSettings(bridgeBalance=12.0), 'IC', later)
    control.restore(later)
    assert clamp.params['IC']['BridgeBalResist'] == 22e6  # back to the calibrated value
    control.restore(setScope)
    control.restore(run)
    assert clamp.params['IC']['BridgeBalResist'] == 22e6  # calibration kept over the run's original


def test_refuses_the_gui_thread(rig, monkeypatch):
    from acq4.util import Qt

    monkeypatch.undo()
    app = Qt.QApplication.instance() or Qt.QApplication([])  # kept: an unreferenced app is deleted
    runner = makeRunner(rig, {'S': makeStimset('S')}, {'S': scripted('VC')})
    with pytest.raises(RuntimeError, match='GUI thread'):
        runner.runSet('S')
    assert app is Qt.QCoreApplication.instance()
