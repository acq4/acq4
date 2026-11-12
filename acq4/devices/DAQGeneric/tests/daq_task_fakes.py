"""Shared fakes and checks for DAQ device result tests: a stand-in Manager, the mock NiDAQ, comparisons."""
import copy
import threading
import time

import numpy as np

from acq4.Manager import Task as ManagerTask
from acq4.devices.NiDAQ.nidaq import NiDAQ, Task as NiDAQTask

TIMEOUT = 10.0


class FakeManager:
    """The parts of Manager used by Device.__init__, DAQGeneric and Manager.Task."""

    class _Halt:
        def check(self):
            pass

        def add_abort_callback(self, *args, **kwargs):
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
        if 'device' in interfaces or name not in self.devices:
            self.devices[name] = obj

    def getDevice(self, name):
        return self.devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return self._Locker()

    def _taskStarted(self, task):
        pass

    def _taskFinished(self, task):
        pass


class _WaveTask(NiDAQTask):
    def addChannel(self, channel, type, mode=None, **kwargs):
        if channel in self.dev.waves and 'mockFunc' not in kwargs:
            kwargs['mockFunc'] = self.dev.waves[channel]
        return NiDAQTask.addChannel(self, channel, type, mode, **kwargs)


class WaveDAQ(NiDAQ):
    """Mock-driver NiDAQ that gives input channels in *waves* ({channel: fn(nPts, rate)}) their data."""

    def __init__(self, dm, name='DAQ', waves=None):
        NiDAQ.__init__(self, dm, {'mock': True}, name)
        self.waves = dict(waves or {})

    def createTask(self, cmd, parentTask):
        return _WaveTask(self, cmd, parentTask)


def waitUntil(condition, timeout=TIMEOUT):
    deadline = time.time() + timeout
    while not condition():
        assert time.time() < deadline, "timed out waiting"
        time.sleep(1e-3)


def readerThreads():
    return [t for t in threading.enumerate() if t.name.startswith("NI-DAQ chunk reader")]


class PartialRecorder:
    """Partial-result handler that snapshots one device's result: settled prefixes, settlement, axes."""

    def __init__(self, devName):
        self.devName = devName
        self.calls = []

    def __call__(self, payload):
        res = payload[self.devName]
        data = res.asarray()
        settled = res.settlement()
        names = [c['name'] for c in res._info[0]['cols']]
        self.calls.append({
            'obj': res,
            'keys': set(payload),
            'settled': settled,
            'complete': res.isComplete(),
            'nTime': len(res.xvals('Time')),
            'prefix': {name: data[i, :settled[name]].copy() for i, name in enumerate(names)},
        })


def runTask(dm, command, handler=None):
    """Execute *command* through a real Manager.Task; return (task, result dict)."""
    task = ManagerTask(dm, command)
    if handler is not None:
        task.addPartialResultHandler(handler)
    task.execute(block=False)
    waitUntil(task.isDone)
    result = task.getResult()
    waitUntil(lambda: readerThreads() == [])
    return task, result


def checkPartials(recorder, final, outputs=()):
    """Check *recorder*'s partials against the *final* result object.

    Every partial is *final* itself, full-length in time, with non-decreasing settlement whose
    values equal the final ones exactly; *outputs* are settled from the first.
    """
    assert len(recorder.calls) >= 2
    data = final.asarray()
    names = [c['name'] for c in final._info[0]['cols']]
    n = data.shape[1]
    prev = dict.fromkeys(names, 0)
    for call in recorder.calls:
        assert call['obj'] is final
        assert call['nTime'] == n
        assert not call['complete']
        assert set(call['settled']) == set(names)
        for i, name in enumerate(names):
            s = call['settled'][name]
            assert prev[name] <= s <= n
            prev[name] = s
            if name in outputs:
                assert s == n
            assert np.array_equal(call['prefix'][name], data[i, :s]), name
    assert final.isComplete()
    assert final.settlement() == dict.fromkeys(names, n)


def stripValidSamples(info):
    """Return a deep copy of MetaArray *info* without info[-1]['DAQ'][ch]['validSamples']."""
    info = copy.deepcopy(info)
    for state in info[-1].get('DAQ', {}).values():
        state.pop('validSamples', None)
    return info


def assertSameValue(a, b, path='info'):
    """Assert *a* and *b* are equal and of the same type, recursing into dicts, lists and arrays."""
    assert type(a) is type(b), (path, type(a), type(b))
    if isinstance(a, np.ndarray):
        assert a.dtype == b.dtype and a.shape == b.shape, path
        np.testing.assert_array_equal(a, b, err_msg=path)
    elif isinstance(a, dict):
        assert list(a.keys()) == list(b.keys()), (path, list(a.keys()), list(b.keys()))
        for k in a:
            assertSameValue(a[k], b[k], f"{path}[{k!r}]")
    elif isinstance(a, (list, tuple)):
        assert len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a, b)):
            assertSameValue(x, y, f"{path}[{i}]")
    elif callable(a):
        assert a is b, path
    elif isinstance(a, float) and np.isnan(a):
        assert np.isnan(b), path
    else:
        assert a == b, (path, a, b)


def assertSameResult(new, old, buffered):
    """Assert *new* equals the legacy MetaArray *old*, plus validSamples for each *buffered* channel."""
    assert type(old).__name__ == 'MetaArray'
    newArr, oldArr = new.asarray(), old.asarray()
    assert newArr.dtype == oldArr.dtype and newArr.shape == oldArr.shape
    np.testing.assert_array_equal(newArr, oldArr)
    daq = new._info[-1]['DAQ']
    for ch in buffered:
        assert daq[ch]['validSamples'] == newArr.shape[1]
        assert isinstance(daq[ch]['validSamples'], int)
    for ch in daq:
        if ch not in buffered:
            assert 'validSamples' not in daq[ch]
    assertSameValue(stripValidSamples(new._info), old._info)



EARLY_STOP_KEYS = ('stoppedEarly', 'numPtsRequested', 'numPtsAcquired', 'stopTime')


def runTaskStoppedEarly(dm, command, recorder, minCalls=3):
    """Execute *command*, call stopEarly() from this thread after *recorder* has *minCalls* calls.

    Returns (task, stopEarly() return value, result dict).
    """
    task = ManagerTask(dm, command)
    task.addPartialResultHandler(recorder)
    task.execute(block=False)
    waitUntil(lambda: len(recorder.calls) >= minCalls)
    truncated = task.stopEarly()
    assert task.isDone()
    result = task.getResult()
    waitUntil(lambda: readerThreads() == [])
    return task, truncated, result


def checkTruncatedPartials(recorder, final, nPlanned, outputs=()):
    """Check *recorder*'s partials of an early-stopped run against the truncated *final* result.

    Partials were *final* itself at the planned length *nPlanned*; their settled values equal the
    final ones wherever both exist, and inputs never settled past the final length.
    """
    assert recorder.calls
    data = final.asarray()
    names = [c['name'] for c in final._info[0]['cols']]
    m = data.shape[1]
    assert m < nPlanned
    for call in recorder.calls:
        assert call['obj'] is final
        assert call['nTime'] == nPlanned
        for i, name in enumerate(names):
            s = call['settled'][name]
            if name in outputs:
                assert s == nPlanned
            else:
                assert s <= m
            k = min(s, m)
            assert np.array_equal(call['prefix'][name][:k], data[i, :k]), name
    assert final.isComplete()
    assert final.settlement() == dict.fromkeys(names, m)


def withoutEarlyStopInfo(result):
    """Return a MetaArray copy of *result* without the early-stop entries in its info[-1]."""
    from MetaArray import MetaArray

    info = copy.deepcopy(result._info)
    for k in EARLY_STOP_KEYS:
        info[-1].pop(k)
    return MetaArray(result.asarray().copy(), info=info)
