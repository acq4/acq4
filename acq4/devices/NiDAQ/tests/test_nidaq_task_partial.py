"""NiDAQ.Task partial-result wiring, driven through the real NiDAQ device on the mock driver."""
import logging
import math
import threading
import time

import numpy as np
import pytest

from acq4.Manager import Task as ManagerTask
from acq4.devices.Device import DeviceTask
from acq4.devices.NiDAQ.nidaq import NiDAQ
from acq4.devices.NiDAQ.tests.legacy_getdata import legacyGetData

RATE = 100_000.0
NPTS = 20_000  # 0.2 s
AI = '/Dev1/ai0'
AI2 = '/Dev1/ai1'
DI = '/Dev1/port0/line1'
AO = '/Dev1/ao0'
TIMEOUT = 5.0
DS10 = {'downsample': 10}


def aiWave(n, rate=RATE, phase=0.0):
    t = np.arange(n) / rate
    return -0.81 + 0.5 * np.sin(2 * np.pi * 40 * t + phase) + 0.02 * np.random.default_rng(n).standard_normal(n)


def diWave(n, rate=RATE):
    return ((np.arange(n) // 17) % 2) * 2


def aoWave(n):
    return np.linspace(-12.0, 12.0, n)


def waitUntil(condition, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while not condition():
        assert time.time() < deadline, "timed out waiting"
        time.sleep(1e-3)


def readerThreads():
    return [t for t in threading.enumerate() if t.name.startswith("NI-DAQ chunk reader")]


class _FakeManager:
    """The parts of Manager used by Device.__init__ and Manager.Task."""

    class _Halt:
        def check(self):
            pass

    class _Locker:
        def lock(self):
            pass

        def unlock(self):
            pass

    def __init__(self):
        self.devices = {}
        self.globalHalt = self._Halt()

    def declareInterface(self, name, interfaces, obj):
        self.devices[name] = obj

    def getDevice(self, name):
        return self.devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return self._Locker()

    def _taskStarted(self, task):
        pass

    def _taskFinished(self, task):
        pass


class _FakeParentTask:
    def __init__(self, interval=None, events=None):
        self.tasks = {}
        self.interval = interval
        self.events = [] if events is None else events
        self.emitError = None
        self.partialResultErrors = []

    def updateInterval(self):
        return self.interval

    def emitPartialResults(self):
        self.events.append('emit')
        if self.emitError is not None:
            raise self.emitError


class _RecorderTask(DeviceTask):
    """Device task that records DAQ channels through accumulators and snapshots them per chunk."""

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.events = cmd.get('events', [])
        self.snapshots = []
        self.accs = {}

    def createChannels(self, daqTask):
        daqTask.addChannel(AI, 'ai', mockFunc=lambda n, rate: aiWave(n, rate))
        daqTask.addChannel(AI2, 'ai', mockFunc=lambda n, rate: aiWave(n, rate, phase=1.0))
        daqTask.addChannel(DI, 'di', mockFunc=lambda n, rate: diWave(n, rate))
        daqTask.addChannel(AO, 'ao')
        for ch in (AI, AI2, DI, AO):
            self.accs[ch] = daqTask.channelAccumulator(ch)
        daqTask.setWaveform(AO, aoWave(daqTask.cmd['numPts']))
        daqTask.addChunkListener(self.onChunk)
        self.daqTask = daqTask

    def onChunk(self):
        self.events.append('listener')
        self.snapshots.append({ch: acc.output[:acc.nSettled].copy() for ch, acc in self.accs.items()})

    def partialResult(self):
        return {ch: acc.nSettled for ch, acc in self.accs.items()}


class _RecorderDevice:
    def __init__(self, name='Recorder'):
        self._name = name

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return _RecorderTask(self, cmd, parentTask)


@pytest.fixture
def daq():
    return NiDAQ(_FakeManager(), {'mock': True}, 'DAQ')


def makeTasks(daq, interval=None, **cmd):
    events = []
    parent = _FakeParentTask(interval, events)
    daqCmd = {'rate': RATE, 'numPts': NPTS, **cmd}
    daqTask = daq.createTask(daqCmd, parent)
    rec = _RecorderTask(_RecorderDevice(), {'events': events}, parent)
    parent.tasks = {'DAQ': daqTask, 'Recorder': rec}
    chunkCalls = []
    origSet = daqTask.st.setChunkHandler

    def setChunkHandler(chunkSize, handler):
        chunkCalls.append(chunkSize)
        return origSet(chunkSize, handler)

    daqTask.st.setChunkHandler = setChunkHandler
    return parent, daqTask, rec, chunkCalls


def instrumentUpdates(rec):
    for ch, acc in rec.accs.items():
        def update(raw, n, orig=acc.update, ch=ch):
            rec.events.append(('update', ch))
            return orig(raw, n)
        acc.update = update


def run(daqTask):
    daqTask.start()
    waitUntil(daqTask.isDone)
    daqTask.stop()


def assertSameResult(new, old):
    assert new['data'].dtype == old['data'].dtype and new['data'].shape == old['data'].shape
    assert np.array_equal(new['data'], old['data'])
    assert list(new['info'].items()) == list(old['info'].items())


@pytest.mark.parametrize("cmd", [DS10, {'downsample': 3}, {}], ids=['downsample10', 'downsample3', 'plain'])
def test_partial_run_settles_prefix_and_final_matches_original(daq, cmd):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01, **cmd)
    daqTask.configure()
    assert chunkCalls == [{1: 1000, 3: 1002, 10: 1000}[cmd.get('downsample', 1)]]
    assert daqTask.settleSpecs() == {}
    assert rec.accs[AI].settleSpec.updates

    ao = rec.accs[AO]
    assert ao.nSettled == ao.numOutput  # outputs are settled before the run starts
    instrumentUpdates(rec)
    run(daqTask)

    # per chunk: input accumulators, then the listener, then emit
    inputs = {('update', ch) for ch in (AI, AI2, DI)}
    nChunks = len(rec.snapshots)
    assert nChunks >= 2
    assert len(rec.events) == nChunks * 5
    for i in range(nChunks):
        chunk = rec.events[5 * i:5 * i + 5]
        assert set(chunk[:3]) == inputs and chunk[3:] == ['listener', 'emit']

    finals = {}
    for ch in (AI, AI2, DI, AO):
        result = daqTask.getData(ch)
        assertSameResult(result, legacyGetData(daqTask, ch))
        finals[ch] = result['data'].copy()
    assert finals[AO].shape == (ao.numOutput,)  # the clipped waveform, processed like every channel
    assert daqTask.getData(AO)['info']['startTime'] == daqTask.st.startTime is not None

    for ch in (AI, AI2, DI, AO):
        prev = 0
        for snap in rec.snapshots:
            part = snap[ch]
            assert len(part) >= prev
            prev = len(part)
            assert part.dtype == finals[ch].dtype and np.array_equal(part, finals[ch][:len(part)])
        assert prev == len(finals[ch])  # the last chunk settles everything
        assert rec.accs[ch].settleSpec.updates
    assert len(rec.snapshots[0][AO]) == ao.numOutput
    assert 0 < len(rec.snapshots[0][AI]) < rec.accs[AI].numOutput


def test_no_update_interval_is_inert(daq):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=None, **DS10)
    daqTask.configure()
    daqTask.start()
    assert readerThreads() == []
    waitUntil(daqTask.isDone)
    daqTask.stop()
    assert chunkCalls == []
    assert rec.events == [] and parent.events == []
    assert daqTask.settleSpecs() == {}
    assert rec.accs[AI].nSettled == 0
    for ch in (AI, DI, AO):
        assertSameResult(daqTask.getData(ch), legacyGetData(daqTask, ch))
    assert rec.accs[AI].nSettled == rec.accs[AI].numOutput


def test_chunk_spanning_the_record_disables_updates(daq):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=NPTS / RATE)
    daqTask.configure()
    assert chunkCalls == []
    specs = daqTask.settleSpecs()
    assert list(specs) == ['']
    assert specs[''].delay == math.inf and "update interval" in specs[''].reason
    run(daqTask)
    assert rec.events == []
    assertSameResult(daqTask.getData(AI), legacyGetData(daqTask, AI))


@pytest.mark.parametrize("interval, ds, chunkSize", [(0.0105, 3, 1050), (0.0101, 3, 1011), (0.003, 10, 300),
                                                     (0.00301, 10, 310)])
def test_chunk_size_is_a_whole_number_of_bins(daq, interval, ds, chunkSize):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=interval, downsample=ds)
    daqTask.configure()
    assert chunkCalls == [chunkSize]
    daqTask.stop(abort=True)


def fillRaw(daqTask):
    for ch in (AI, AI2):
        daqTask.st.rawChannelData(ch)[:] = aiWave(NPTS)
    daqTask.st.rawChannelData(DI)[:] = diWave(NPTS)


def test_failing_accumulator_and_listener_are_isolated(daq, caplog):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01)
    calls = {'bad': 0, 'good': 0}

    def badListener():
        calls['bad'] += 1
        raise RuntimeError("listener failure")

    def goodListener():
        calls['good'] += 1

    daqTask.configure()
    daqTask.addChunkListener(badListener)
    daqTask.addChunkListener(goodListener)

    def badUpdate(raw, n):
        raise RuntimeError("accumulator failure")

    rec.accs[AI].update = badUpdate
    fillRaw(daqTask)
    with caplog.at_level(logging.ERROR, logger='acq4'):
        for n in range(1000, NPTS + 1, 1000):
            daqTask._onChunk(n)  # must not raise
    assert calls == {'bad': 1, 'good': 20}
    assert parent.events.count('emit') == 20 and parent.events.count('listener') == 20
    assert rec.accs[AI].nSettled == 0
    assert rec.accs[AI2].nSettled == rec.accs[AI2].numOutput  # the others carry on
    messages = [r.getMessage() for r in caplog.records]
    assert sum(AI in m for m in messages) == 1
    assert sum('badListener' in m for m in messages) == 1
    daqTask.stop(abort=True)


@pytest.mark.parametrize("failAt", [1, 4, None], ids=['first', 'fourth', 'never'])
@pytest.mark.parametrize("cmd", [{}, {'downsample': 3}], ids=['plain', 'downsample3'])
def test_failed_partials_complete_from_the_raw_buffer(daq, cmd, failAt):
    """A channel whose update() raised gets the values a run without the failure gives, flagged partialsFailed."""
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01, **cmd)
    daqTask.configure()
    acc = rec.accs[AI]
    calls = []

    def flakyUpdate(raw, n, orig=acc.update):
        calls.append(n)
        if len(calls) == failAt:
            raise RuntimeError("transient accumulator failure")
        return orig(raw, n)

    acc.update = flakyUpdate
    run(daqTask)
    failed = failAt is not None
    assert len(calls) == (failAt if failed else len(rec.snapshots))
    for ch in (AI, AI2, DI):
        result = daqTask.getData(ch)
        expected = legacyGetData(daqTask, ch)
        flagged = failed and ch == AI
        assert result['info'].pop('partialsFailed', False) is flagged
        assertSameResult(result, expected)
        for snap in rec.snapshots:
            assert np.array_equal(snap[ch], result['data'][:len(snap[ch])])
    daqTask.getData(AI)  # reported once per run
    assert len(parent.partialResultErrors) == int(failed)
    if failed:
        assert AI in parent.partialResultErrors[0]


def test_emit_failure_is_contained(daq, caplog):
    parent, daqTask, rec, chunkCalls = makeTasks(daq, interval=0.01)
    daqTask.configure()
    parent.emitError = RuntimeError("emit failure")
    fillRaw(daqTask)
    with caplog.at_level(logging.ERROR, logger='acq4'):
        for n in (1000, 2000, 3000):
            daqTask._onChunk(n)
    assert parent.events.count('emit') == 3 and len(rec.snapshots) == 3
    assert sum('emitting partial' in r.getMessage() for r in caplog.records) == 1
    daqTask.stop(abort=True)


def test_channel_accumulator_create_or_get(daq):
    parent, daqTask, rec, chunkCalls = makeTasks(daq)
    daqTask.configure()
    acc = daqTask.channelAccumulator('ai0')
    assert acc is rec.accs[AI] and acc.channel == AI and acc.chanType == 'ai'
    assert daqTask.channelAccumulator(AI) is acc
    with pytest.raises(ValueError):
        daqTask.channelAccumulator('/Dev1/ai3')
    daqTask.stop(abort=True)


def test_manager_task_delivers_partials_and_final(daq):
    """Manager.Task + real NiDAQ on the mock: handler payloads, then the normal final result."""
    dm = daq.dm
    dm.devices['Recorder'] = _RecorderDevice()
    command = {
        'protocol': {'duration': NPTS / RATE, 'updateInterval': 0.02},
        'DAQ': {'rate': RATE, 'numPts': NPTS, **DS10},
        'Recorder': {},
    }
    task = ManagerTask(dm, command)
    payloads = []
    task.addPartialResultHandler(lambda result: payloads.append({k: dict(v) if isinstance(v, dict) else v
                                                                for k, v in result.items()}))
    task.execute(block=False)
    waitUntil(task.isDone)
    result = task.getResult()
    rec = task.tasks['Recorder']

    assert len(payloads) >= 2 and len(payloads) == len(rec.snapshots)
    assert all(set(p) == {'protocol', 'Recorder'} for p in payloads)
    settled = [p['Recorder'][AI] for p in payloads]
    assert settled == sorted(settled) and settled[-1] == NPTS // 10
    assert result['DAQ'] is None and result['Recorder'] is None
    assertSameResult(task.tasks['DAQ'].getData(AI), legacyGetData(task.tasks['DAQ'], AI))
    assert task.partialResultErrors == []
    assert readerThreads() == []
