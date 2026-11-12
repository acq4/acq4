"""Manager.Task.stopEarly() with DAQGeneric and MockClamp tasks on the mock NI-DAQ driver."""

import threading
import time

import numpy as np
import pytest

from MetaArray import MetaArray
from acq4.Manager import Task as ManagerTask
from acq4.devices.DAQGeneric import DAQGeneric, DAQGenericTask
from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    EARLY_STOP_KEYS,
    FakeManager,
    PartialRecorder,
    WaveDAQ,
    assertSameResult,
    checkTruncatedPartials,
    readerThreads,
    runTask,
    runTaskStoppedEarly,
    waitUntil,
    withoutEarlyStopInfo,
)
from acq4.devices.DAQGeneric.tests.legacy_daqgeneric_result import legacyGetResult
from acq4.devices.DAQGeneric.tests.legacy_subclass_results import legacyMockClampGetResult
from acq4.devices.DAQGeneric.tests.test_daqgeneric_result import (
    AO,
    CHANNELS,
    aiWave,
    diWave,
    AI0,
    AI1,
    DI,
)
from acq4.devices.DAQGeneric.tests.test_daqgeneric_subclass_results import FakeMockClamp

RATE = 100_000.0
NPTS = 99_000  # 0.99 s, divisible by every downsampling factor used; the tests stop it early
INTERVAL = 0.02
ALL = ('In0', 'In1', 'Dig', 'Out', 'DOut')


@pytest.fixture
def rig():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: aiWave(0.0), AI1: aiWave(1.0), DI: diWave})
    gen = DAQGeneric(dm, {'channels': {k: dict(v) for k, v in CHANNELS.items()}}, 'Gen')
    return dm, gen


def genCommand(channels=ALL):
    cmd = {}
    for ch in channels:
        if CHANNELS[ch]['type'] in ('ai', 'di'):
            cmd[ch] = {'record': True}
        elif CHANNELS[ch]['type'] == 'ao':
            cmd[ch] = {'command': np.linspace(-1.0, 1.0, NPTS), 'holding': 0.1}
        else:
            cmd[ch] = {'command': ((np.arange(NPTS) // 100) % 2).astype(float)}
    return cmd


def taskCommand(daqCmd=None, interval=INTERVAL, channels=ALL, **protocol):
    protocol = {'duration': NPTS / RATE, **protocol}
    if interval is not None:
        protocol['updateInterval'] = interval
    return {
        'protocol': protocol,
        'DAQ': {'rate': RATE, 'numPts': NPTS, **(daqCmd or {})},
        'Gen': genCommand(channels),
    }


@pytest.mark.parametrize(
    'daqCmd', [{}, {'downsample': 3}, {'downsample': 10}], ids=['plain', 'ds3', 'ds10']
)
def test_stop_early_truncates_every_channel_consistently(rig, daqCmd):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    t0 = time.time()
    task, truncated, result = runTaskStoppedEarly(dm, taskCommand(daqCmd), rec)
    assert truncated is True
    assert time.time() - t0 < 0.7 * NPTS / RATE
    genTask = task.tasks['Gen']
    final = result['Gen']
    ds = daqCmd.get('downsample', 1)

    prot = result['protocol']
    assert prot['stoppedEarly'] is True
    n = prot['numPtsAcquired']['DAQ']
    assert 0 < n < NPTS
    assert prot['startTime'] < prot['stopTime'] == task.stopTime
    assert task.runTime() < NPTS / RATE

    assert n % ds == 0
    m = n // ds
    assert final.shape == (5, m)
    assert len(final.xvals('Time')) == m
    top = final._info[-1]
    assert top['stoppedEarly'] is True
    assert (top['numPtsRequested'], top['numPtsAcquired']) == (NPTS, n)
    assert top['stopTime'] <= prot['stopTime']
    for ch in ALL:
        daq = top['DAQ'][ch]
        assert daq['numPts'] == daq['validSamples'] == m
        assert daq['stoppedEarly'] is True and daq['numPtsAcquired'] == n

    checkTruncatedPartials(rec, final, NPTS // ds if ds > 1 else NPTS, outputs=('Out', 'DOut'))
    assert genTask.getResult() is final and genTask.partialResult() is final
    assertSameResult(withoutEarlyStopInfo(final), legacyGetResult(genTask), buffered=list(ALL))


def test_outputs_return_to_holding(rig, monkeypatch):
    dm, gen = rig
    daq = dm.getDevice('DAQ')
    sets = []
    orig = daq.setChannelValue

    def setChannelValue(chan, value, **kwargs):
        sets.append((chan, value))
        return orig(chan, value, **kwargs)

    monkeypatch.setattr(daq, 'setChannelValue', setChannelValue)
    rec = PartialRecorder('Gen')
    task = ManagerTask(dm, taskCommand(channels=('In0', 'Out')))
    task.addPartialResultHandler(rec)
    task.execute(block=False)
    waitUntil(lambda: len(rec.calls) >= 2)
    del sets[:]
    task.stopEarly()
    assert sets == [(AO, gen.mapToDAQ('Out', 0.1))]


def test_no_partial_results(rig):
    dm, gen = rig
    task = ManagerTask(dm, taskCommand(interval=None))
    task.execute(block=False)
    time.sleep(0.1)
    assert task.stopEarly() is True
    final = task.getResult()['Gen']
    n = task.getResult()['protocol']['numPtsAcquired']['DAQ']
    assert final.shape == (5, n) and 0 < n < NPTS
    assert final.settlement() == dict.fromkeys(ALL, n)
    assertSameResult(
        withoutEarlyStopInfo(final), legacyGetResult(task.tasks['Gen']), buffered=list(ALL)
    )


def test_stored_data_is_truncated(rig, tmp_path):
    from acq4.util import DataManager

    dm, gen = rig
    dh = DataManager.getDirHandle(str(tmp_path))
    rec = PartialRecorder('Gen')
    task, truncated, result = runTaskStoppedEarly(
        dm, taskCommand({'downsample': 3}, storeData=True, storageDir=dh), rec
    )
    final = result['Gen']
    stored = MetaArray(file=str(tmp_path / 'Gen.ma'))
    np.testing.assert_array_equal(stored.asarray(), final.asarray())
    assert stored.shape[1] == final.shape[1] < NPTS // 3
    for k in EARLY_STOP_KEYS:
        assert stored._info[-1][k] == final._info[-1][k]
    info = dh.info()
    assert info['stoppedEarly'] is True
    assert info['numPtsAcquired'] == result['protocol']['numPtsAcquired']
    assert info['stopTime'] == result['protocol']['stopTime']


def test_stop_early_after_completion_is_a_normal_stop(rig):
    dm, gen = rig
    command = taskCommand(channels=('In0', 'Out'))
    command['protocol']['duration'] = 0.05  # finished (by duration and DAQ) once the DAQ is done
    command['DAQ']['numPts'] = 5000
    command['Gen'] = {'In0': {'record': True}, 'Out': {'command': np.zeros(5000), 'holding': 0.1}}
    rec = PartialRecorder('Gen')
    task = ManagerTask(dm, command)
    task.addPartialResultHandler(rec)
    task.execute(block=False)
    waitUntil(task.isDone)
    assert task.stopEarly() is False
    result = task.getResult()
    final = result['Gen']
    assert result['protocol']['stoppedEarly'] is False
    assert 'numPtsAcquired' not in result['protocol']
    assert final.shape == (2, 5000)
    assert not any(k in final._info[-1] for k in EARLY_STOP_KEYS)
    assert task.stopEarly() is False  # already stopped: as stop()


def test_stop_early_unblocks_a_blocking_execute(rig, qtbot):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task = ManagerTask(dm, taskCommand(channels=('In0',)))
    task.addPartialResultHandler(rec)
    done = threading.Event()

    def run():
        task.execute(block=True, processEvents=False)
        done.set()

    t0 = time.time()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    waitUntil(lambda: len(rec.calls) >= 2)
    assert task.stopEarly() is True
    assert done.wait(0.3 * NPTS / RATE)
    assert time.time() - t0 < 0.7 * NPTS / RATE
    assert task.getResult()['Gen'].shape[1] < NPTS


def test_stop_early_from_a_partial_result_handler_raises(rig):
    dm, gen = rig
    errors = []
    task = ManagerTask(dm, taskCommand(channels=('In0',)))

    def handler(result):
        if not errors:
            try:
                task.stopEarly()
            except RuntimeError as exc:
                errors.append(exc)

    task.addPartialResultHandler(handler)
    task.execute(block=False)
    waitUntil(lambda: errors)
    assert 'partial-result handler' in str(errors[0])
    assert not task.isDone()  # nothing was stopped
    assert task.stopEarly() is True
    assert task.getResult()['Gen'].shape[1] < NPTS


class _ExtraDataTask(DAQGenericTask):
    """A DAQGenericTask subclass that does not opt in to early stop."""


class _ExtraDataGeneric(DAQGeneric):
    def createTask(self, cmd, parentTask):
        return _ExtraDataTask(self, cmd, parentTask)


def test_unsupported_device_raises_before_stopping_anything(rig):
    dm, gen = rig
    _ExtraDataGeneric(dm, {'channels': {'In1': dict(CHANNELS['In1'])}}, 'Extra')
    command = taskCommand(channels=('In0',))
    command['Extra'] = {'In1': {'record': True}}
    task = ManagerTask(dm, command)
    assert not task.tasks['Extra'].supportsEarlyStop and task.tasks['Gen'].supportsEarlyStop
    task.execute(block=False)
    time.sleep(0.05)
    with pytest.raises(RuntimeError, match=r"\['Extra'\] cannot truncate"):
        task.stopEarly()
    assert not task.isDone() and not task.stopped
    task.stop(abort=True)
    waitUntil(lambda: readerThreads() == [])


def test_mock_clamp_stop_early():
    dm = FakeManager()
    WaveDAQ(dm)
    clamp = FakeMockClamp(dm)
    rec = PartialRecorder('Clamp1')
    command = {
        'protocol': {'duration': NPTS / RATE, 'updateInterval': INTERVAL},
        'DAQ': {'rate': RATE, 'numPts': NPTS},
        'Clamp1': {'mode': 'VC', 'command': -0.05 + 0.01 * ((np.arange(NPTS) // 2000) % 2)},
    }
    task, truncated, result = runTaskStoppedEarly(dm, command, rec)
    assert truncated is True
    clampTask = task.tasks['Clamp1']
    final = result['Clamp1']
    n = result['protocol']['numPtsAcquired']['DAQ']
    assert final.shape == (2, n)
    assert final._info[-1]['ClampState'] is clampTask.ampState
    assert final._info[-1]['stoppedEarly'] is True
    checkTruncatedPartials(rec, final, NPTS, outputs=('command',))
    assertSameResult(
        withoutEarlyStopInfo(final),
        legacyMockClampGetResult(clampTask),
        buffered=['command', 'primary'],
    )


def test_full_run_after_early_stop(rig):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    runTaskStoppedEarly(dm, taskCommand(channels=('In0', 'Out')), rec)
    command = taskCommand(channels=('In0', 'Out'))
    command['DAQ']['numPts'] = 5000
    command['protocol']['duration'] = 0.05
    command['Gen'] = {'In0': {'record': True}, 'Out': {'command': np.zeros(5000), 'holding': 0.1}}
    task, result = runTask(dm, command)
    assert result['Gen'].shape == (2, 5000)
    assert 'stoppedEarly' not in result['protocol']
