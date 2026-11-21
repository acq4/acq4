"""DAQGenericTask results through a real Manager.Task and NiDAQ on the mock driver, against the original getResult."""
import logging
import threading

import numpy as np
import pytest

from MetaArray import MetaArray
from acq4.Manager import Task as ManagerTask
from acq4.devices.DAQGeneric import DAQGeneric
from acq4.devices.DAQGeneric.tests.daq_task_fakes import (
    FakeManager, WaveDAQ, PartialRecorder, assertSameResult, assertSameValue, checkPartials, readerThreads, runTask,
    stripValidSamples, waitUntil,
)
from acq4.devices.DAQGeneric.tests.legacy_daqgeneric_result import legacyGetResult
from acq4.util.partial_results import TaskResultArray

RATE = 100_000.0
NPTS = 18_000  # 0.18 s; divisible by every downsampling factor used here
INTERVAL = 0.02

AI0, AI1, DI, AO, DO = '/Dev1/ai0', '/Dev1/ai1', '/Dev1/port0/line1', '/Dev1/ao0', '/Dev1/port0/line2'

BESSEL = {'filterMethod': 'Bessel', 'besselCutoff': 2000.0, 'besselOrder': 4, 'besselBidirectional': True}
DENOISE = {'denoiseMethod': 'Pointwise', 'denoiseWidth': 1, 'denoiseThreshold': 3.0}

DAQ_VARIANTS = {
    'plain': {},
    'noneMethods': {'filterMethod': 'None', 'denoiseMethod': 'None'},
    'downsample3': {'downsample': 3},
    'downsample4': {'downsample': 4},
    'downsample10': {'downsample': 10},
}


def aiWave(phase):
    def fn(n, rate):
        t = np.arange(n) / rate
        return -0.81 + 0.5 * np.sin(2 * np.pi * 40 * t + phase) + 0.02 * np.random.default_rng(n).standard_normal(n)
    return fn


def diWave(n, rate):
    return ((np.arange(n) // 17) % 2) * 2


CHANNELS = {
    'In0': {'device': 'DAQ', 'channel': AI0, 'type': 'ai', 'units': 'A', 'scale': 2.5e-9, 'offset': 0.1},
    'In1': {'device': 'DAQ', 'channel': AI1, 'type': 'ai', 'units': 'V'},
    'Dig': {'device': 'DAQ', 'channel': DI, 'type': 'di'},
    'Out': {'device': 'DAQ', 'channel': AO, 'type': 'ao', 'units': 'V', 'scale': 0.5, 'offset': -0.2, 'holding': 0.1},
    'DOut': {'device': 'DAQ', 'channel': DO, 'type': 'do', 'holding': 0},
}


@pytest.fixture
def rig():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: aiWave(0.0), AI1: aiWave(1.0), DI: diWave})
    gen = DAQGeneric(dm, {'channels': {k: dict(v) for k, v in CHANNELS.items()}}, 'Gen')
    return dm, gen


def genCommand(channels=('In0', 'In1', 'Dig', 'Out', 'DOut'), npts=NPTS):
    cmd = {}
    for ch in channels:
        if CHANNELS[ch]['type'] in ('ai', 'di'):
            cmd[ch] = {'record': True}
        elif CHANNELS[ch]['type'] == 'ao':
            cmd[ch] = {'command': np.linspace(-1.0, 1.0, npts), 'holding': 0.1}
        else:
            cmd[ch] = {'command': ((np.arange(npts) // 100) % 2).astype(float)}
    return cmd


def taskCommand(daqCmd=None, interval=None, channels=('In0', 'In1', 'Dig', 'Out', 'DOut'), npts=NPTS):
    protocol = {'duration': npts / RATE}
    if interval is not None:
        protocol['updateInterval'] = interval
    return {
        'protocol': protocol,
        'DAQ': {'rate': RATE, 'numPts': npts, **(daqCmd or {})},
        'Gen': genCommand(channels, npts),
    }


@pytest.mark.parametrize('variant', list(DAQ_VARIANTS))
def test_partials_are_the_final_object_and_final_matches_original(rig, variant):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task, result = runTask(dm, taskCommand(DAQ_VARIANTS[variant], interval=INTERVAL), rec)
    genTask = task.tasks['Gen']
    final = result['Gen']

    assert isinstance(final, TaskResultArray)
    assert task.partialResultErrors == []
    checkPartials(rec, final, outputs=('Out', 'DOut'))
    assert all(call['keys'] == {'protocol', 'Gen'} for call in rec.calls)
    assert genTask.getResult() is final
    assert genTask.partialResult() is final

    specs = genTask.settleSpecs()
    assert set(specs) == {'In0', 'In1', 'Dig'}
    last = rec.calls[-1]['settled']
    for ch, spec in specs.items():
        assert spec.updates
        assert last[ch] == final.shape[1]  # the last chunk settles everything
    assert any(0 < call['settled']['In0'] < final.shape[1] for call in rec.calls)

    assertSameResult(final, legacyGetResult(genTask), buffered=['In0', 'In1', 'Dig', 'Out', 'DOut'])


@pytest.mark.parametrize('variant', ['plain', 'downsample3', 'downsample10'])
def test_no_update_interval_is_inert_and_matches_original(rig, variant):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task, result = runTask(dm, taskCommand(DAQ_VARIANTS[variant]), rec)
    genTask = task.tasks['Gen']
    final = result['Gen']
    assert rec.calls == []
    assert isinstance(final, TaskResultArray) and final.isComplete()
    assert final.settlement() == dict.fromkeys(['In0', 'In1', 'Dig', 'Out', 'DOut'], final.shape[1])
    assert genTask.getResult() is final and genTask.partialResult() is final
    assertSameResult(final, legacyGetResult(genTask), buffered=['In0', 'In1', 'Dig', 'Out', 'DOut'])


@pytest.mark.parametrize('channels', [('In0',), ('Out',), ('Dig', 'DOut'), ('In1', 'Out')])
def test_channel_subsets_match_original(rig, channels):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task, result = runTask(dm, taskCommand(interval=INTERVAL, channels=channels), rec)
    genTask = task.tasks['Gen']
    final = result['Gen']
    inputs = [ch for ch in channels if CHANNELS[ch]['type'] in ('ai', 'di')]
    if inputs:
        checkPartials(rec, final, outputs=[ch for ch in channels if ch not in inputs])
    assert set(genTask.settleSpecs()) == set(inputs)
    assertSameResult(final, legacyGetResult(genTask), buffered=list(channels))


def test_no_buffered_channels_returns_none(rig):
    dm, gen = rig
    DAQGeneric(dm, {'channels': {'P': dict(CHANNELS['In1'])}}, 'Probe')
    command = taskCommand(interval=INTERVAL, channels=())
    command['Gen'] = {'In0': {'record': False}, 'Out': {'holding': 0.3}}
    command['Probe'] = {'P': {'record': True}}
    rec = PartialRecorder('Probe')
    task, result = runTask(dm, command, rec)
    genTask = task.tasks['Gen']
    assert result['Gen'] is None
    assert genTask.partialResult() is None
    assert genTask.settleSpecs() == {}
    assert legacyGetResult(genTask) is None
    assert all('Gen' not in call['keys'] for call in rec.calls)
    assert len(rec.calls) >= 2


def test_mismatched_lengths_raise_as_before(rig):
    """ai is mean-downsampled to floor(n/3) samples but di is subsampled to ceil(n/3): the original raises."""
    dm, gen = rig
    task, result = runTask(dm, taskCommand({'downsample': 3}, interval=INTERVAL, channels=('In0', 'Dig'),
                                           npts=NPTS + 1))
    genTask = task.tasks['Gen']
    assert result['Gen'] is None  # Manager.Task logged the error
    assert genTask.partialResult() is None
    with pytest.raises(ValueError):
        genTask.getResult()
    with pytest.raises(ValueError):
        legacyGetResult(genTask)


def test_partial_layout_mismatch_raises(rig, caplog):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task, _ = runTask(dm, taskCommand(interval=INTERVAL, channels=('In0', 'Out')), rec)
    genTask = task.tasks['Gen']
    partial = rec.calls[-1]['obj']
    # stand-in for a partial result whose layout disagrees with the final data
    genTask._resultAcc._complete = False
    genTask._resultAcc._result = TaskResultArray(np.zeros((2, 5)), info=partial.infoCopy()[:1] + [{}, {}])
    with caplog.at_level(logging.ERROR, logger='acq4'):
        with pytest.raises(RuntimeError, match="layout"):
            genTask.getResult()
    assert any('layout' in r.getMessage() and r.levelno == logging.ERROR for r in caplog.records)


def test_settled_values_that_disagree_with_the_final_data_raise(rig, caplog):
    dm, gen = rig
    task, result = runTask(dm, taskCommand(interval=INTERVAL, channels=('In0', 'Out')), PartialRecorder('Gen'))
    genTask = task.tasks['Gen']
    genTask._resultAcc._complete = False  # as if getResult() had not run yet
    result['Gen'].asarray()[0, 0] += 1.0
    with caplog.at_level(logging.ERROR, logger='acq4'):
        with pytest.raises(RuntimeError, match="differs from its published settled values"):
            genTask.getResult()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_failed_partials_are_flagged_and_final_matches_original(rig):
    dm, gen = rig
    rec = PartialRecorder('Gen')
    task = ManagerTask(dm, taskCommand({'downsample': 3}, interval=INTERVAL, channels=('In0', 'In1', 'Out')))
    task.addPartialResultHandler(rec)
    daqTask = task.tasks['DAQ']
    calls = []
    origAccumulator = daqTask.channelAccumulator

    def channelAccumulator(channel):
        acc = origAccumulator(channel)
        if acc.channel == AI1 and 'update' not in vars(acc):
            def flakyUpdate(raw, n, orig=acc.update):
                calls.append(n)
                if len(calls) == 3:
                    raise RuntimeError("transient accumulator failure")
                return orig(raw, n)
            acc.update = flakyUpdate
        return acc

    daqTask.channelAccumulator = channelAccumulator
    task.execute(block=False)
    waitUntil(task.isDone)
    final = task.getResult()['Gen']
    waitUntil(lambda: readerThreads() == [])
    genTask = task.tasks['Gen']

    assert len(calls) == 3
    daq = final._info[-1]['DAQ']
    assert daq['In1']['partialsFailed'] is True
    assert 'partialsFailed' not in daq['In0'] and 'partialsFailed' not in daq['Out']
    assert len(task.partialResultErrors) == 1 and AI1 in task.partialResultErrors[0]
    assert rec.calls[-1]['settled']['In1'] < final.shape[1] == rec.calls[-1]['settled']['In0']
    checkPartials(rec, final, outputs=('Out',))
    legacy = legacyGetResult(genTask)  # the same DAQ task, so its info is flagged too
    assertSameResult(final, legacy, buffered=['In0', 'In1', 'Out'])
    for info in (final._info, legacy._info):
        info[-1]['DAQ']['In1'].pop('partialsFailed')
    unfailed = runTask(dm, taskCommand({'downsample': 3}, interval=INTERVAL, channels=('In0', 'In1', 'Out')))[1]
    np.testing.assert_array_equal(final.asarray(), unfailed['Gen'].asarray())


def test_store_result_writes_the_same_object(rig, tmp_path):
    from acq4.util import DataManager
    dm, gen = rig
    task, result = runTask(dm, taskCommand({'downsample': 3}, interval=INTERVAL, channels=('In0', 'Out')))
    genTask = task.tasks['Gen']
    final = result['Gen']

    written = []

    class _Dir:
        def writeFile(self, obj, name):
            written.append((obj, name))

    genTask.storeResult(_Dir())
    assert written == [(final, 'Gen')]

    dh = DataManager.getDirHandle(str(tmp_path))
    dh.writeFile(final, 'Gen')
    dh.writeFile(legacyGetResult(genTask), 'Legacy')
    stored = MetaArray(file=str(tmp_path / 'Gen.ma'))
    legacy = MetaArray(file=str(tmp_path / 'Legacy.ma'))
    np.testing.assert_array_equal(stored.asarray(), legacy.asarray())
    assert stored.asarray().dtype == legacy.asarray().dtype
    assert [stored._info[-1]['DAQ'][ch].get('validSamples') for ch in ('In0', 'Out', 'In1')] == [NPTS // 3] * 2 + [None]
    assertSameValue(stripValidSamples(stored._info), legacy._info)


def test_settle_specs_before_the_run(rig):
    dm, gen = rig
    task = ManagerTask(dm, taskCommand({'downsample': 10}, interval=INTERVAL))
    genTask = task.tasks['Gen']
    for devName in task.getConfigOrder():
        task.tasks[devName].configure()
    specs = genTask.settleSpecs()
    assert set(specs) == {'In0', 'In1', 'Dig'}
    assert specs['In0'].delay == specs['In1'].delay == 9 / RATE and specs['Dig'].delay == 0
    assert task.settleSpecs()['Gen'] == specs
    task.tasks['DAQ'].stop(abort=True)
    assert readerThreads() == []


@pytest.mark.parametrize('daqCmd', [BESSEL, DENOISE], ids=['bessel', 'denoise'])
def test_filter_commands_are_refused(rig, daqCmd):
    dm, gen = rig
    with pytest.raises(ValueError, match="filtering was removed"):
        ManagerTask(dm, taskCommand(daqCmd, interval=INTERVAL))


def test_get_result_raises_for_a_stuck_listener(rig, caplog, monkeypatch):
    from acq4.devices.DAQGeneric import resultAccumulator
    monkeypatch.setattr(resultAccumulator, '_FINISH_LOCK_TIMEOUT', 0.05)
    dm, gen = rig
    task, _ = runTask(dm, taskCommand(interval=INTERVAL, channels=('In0', 'Out')), PartialRecorder('Gen'))
    genTask = task.tasks['Gen']
    genTask._resultAcc._complete = False  # as if getResult() had not run yet
    with genTask._resultAcc._lock:  # held by a chunk listener that never returns
        with caplog.at_level(logging.ERROR, logger='acq4'):
            with pytest.raises(RuntimeError, match="did not finish updating"):
                genTask.getResult()
    assert any('did not finish updating' in r.getMessage() and r.levelno == logging.ERROR
               for r in caplog.records)


class _TelegraphUnitsGeneric(DAQGeneric):
    """DAQGeneric whose getChanUnits() stands in for a hardware read; records the calling threads."""

    def __init__(self, *args, **kwargs):
        self.unitThreads = []
        DAQGeneric.__init__(self, *args, **kwargs)

    def getChanUnits(self, ch):
        self.unitThreads.append(threading.current_thread())
        return 'A' if ch == 'In0' else DAQGeneric.getChanUnits(self, ch)


def test_device_units_are_only_read_on_the_task_thread():
    dm = FakeManager()
    WaveDAQ(dm, waves={AI0: aiWave(0.0)})
    gen = _TelegraphUnitsGeneric(dm, {'channels': {'In0': dict(CHANNELS['In0'], units=None)}}, 'Gen')
    rec = PartialRecorder('Gen')
    task, result = runTask(dm, taskCommand(interval=INTERVAL, channels=('In0',)), rec)
    final = result['Gen']
    checkPartials(rec, final)
    assert gen.unitThreads and set(gen.unitThreads) == {threading.current_thread()}
    assert final._info[0]['cols'] == [{'name': 'In0', 'units': 'A'}]
    assertSameResult(final, legacyGetResult(task.tasks['Gen']), buffered=['In0'])
