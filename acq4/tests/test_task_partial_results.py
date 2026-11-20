"""Manager.Task partial-result API, with a stand-in manager and fake device tasks."""

import logging
import threading
import time

import pytest

from acq4.Manager import Task
from acq4.devices.Device import DeviceTask
from acq4.util.partial_results import SettleSpec

TIMEOUT = 5.0


class _FakeDeviceTask(DeviceTask):
    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.partial = cmd.get('partial')
        self.partialError = cmd.get('partialError')
        self.specs = cmd.get('specs', {})
        self.partialCalls = 0

    def partialResult(self):
        self.partialCalls += 1
        if self.partialError is not None:
            raise self.partialError
        return self.partial

    def settleSpecs(self):
        if isinstance(self.specs, Exception):
            raise self.specs
        return self.specs


class _PlainDeviceTask(DeviceTask):
    """Uses DeviceTask's default partialResult() and settleSpecs()."""


class _FakeDevice:
    def __init__(self, name, taskClass=_FakeDeviceTask):
        self._name = name
        self.taskClass = taskClass

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        if self.taskClass is None:
            return None
        return self.taskClass(self, cmd, parentTask)


class _FakeLocker:
    def lock(self):
        pass

    def unlock(self):
        pass


class _FakeHalt:
    def check(self):
        pass


class _FakeManager:
    """The parts of Manager that Task.__init__, execute() and stop() use."""

    def __init__(self, devices):
        self.devices = {d.name(): d for d in devices}
        self.globalHalt = _FakeHalt()

    def getDevice(self, name):
        return self.devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return _FakeLocker()

    def _taskStarted(self, task):
        pass

    def _taskFinished(self, task):
        pass


def _makeTask(devCmds, protocol=None, devClasses=None):
    devClasses = devClasses or {}
    devices = [_FakeDevice(name, devClasses.get(name, _FakeDeviceTask)) for name in devCmds]
    command = {'protocol': {'duration': 0.0, **(protocol or {})}, **devCmds}
    return Task(_FakeManager(devices), command)


class _Recorder:
    def __init__(self, fail=0):
        self.calls = []
        self.fail = fail  # number of upcoming calls that raise

    def __call__(self, result):
        self.calls.append(result)
        if self.fail > 0:
            self.fail -= 1
            raise RuntimeError("handler failure")


def test_payload_shape():
    objA = object()
    task = _makeTask(
        {'A': {'partial': objA}, 'B': {}, 'C': {}, 'D': {}},
        devClasses={'C': _PlainDeviceTask, 'D': None},
    )
    assert set(task.tasks) == {'A', 'B', 'C'}
    task.startTime = 12.5
    handler = _Recorder()
    task.addPartialResultHandler(handler)
    task.emitPartialResults()

    assert len(handler.calls) == 1
    payload = handler.calls[0]
    assert payload == {'protocol': {'startTime': 12.5}, 'A': objA}
    assert payload['A'] is objA


def test_every_handler_called_in_order():
    order = []
    task = _makeTask({'A': {'partial': 1}})
    task.addPartialResultHandler(lambda r: order.append('first'))
    task.addPartialResultHandler(lambda r: order.append('second'))
    task.emitPartialResults()
    assert order == ['first', 'second']


def test_no_handler_fast_path():
    task = _makeTask({'A': {'partial': 1}})
    task.emitPartialResults()
    assert task.tasks['A'].partialCalls == 0

    handler = _Recorder()
    task.addPartialResultHandler(handler)
    task.removePartialResultHandler(handler)
    task.emitPartialResults()
    assert task.tasks['A'].partialCalls == 0
    assert handler.calls == []


def test_remove_bound_method_handler():
    class Consumer:
        def __init__(self):
            self.n = 0

        def onPartial(self, result):
            self.n += 1

    consumer = Consumer()
    task = _makeTask({'A': {'partial': 1}})
    task.addPartialResultHandler(consumer.onPartial)
    task.emitPartialResults()
    task.removePartialResultHandler(consumer.onPartial)
    task.emitPartialResults()
    assert consumer.n == 1


def test_handler_removed_after_three_consecutive_failures(caplog):
    task = _makeTask({'A': {'partial': 1}})
    bad = _Recorder(fail=100)
    good = _Recorder()
    task.addPartialResultHandler(bad)
    task.addPartialResultHandler(good)

    with caplog.at_level(logging.ERROR, logger='acq4'):
        for _ in range(3):
            task.emitPartialResults()  # must not raise
    assert len(bad.calls) == 3
    assert len(task.partialResultErrors) == 1
    assert repr(bad) in task.partialResultErrors[0]
    assert task.partialResultErrors[0] in caplog.text

    task.emitPartialResults()
    assert len(bad.calls) == 3
    assert len(good.calls) == 4


def test_handler_success_resets_failure_count():
    task = _makeTask({'A': {'partial': 1}})
    handler = _Recorder(fail=2)
    task.addPartialResultHandler(handler)
    for _ in range(3):  # fail, fail, succeed
        task.emitPartialResults()
    handler.fail = 2
    for _ in range(2):  # fail, fail
        task.emitPartialResults()
    assert len(handler.calls) == 5
    assert task.partialResultErrors == []

    handler.fail = 1
    task.emitPartialResults()  # third consecutive failure
    task.emitPartialResults()
    assert len(handler.calls) == 6
    assert len(task.partialResultErrors) == 1


def test_handler_can_remove_itself():
    task = _makeTask({'A': {'partial': 1}})
    calls = []

    def handler(result):
        calls.append(result)
        task.removePartialResultHandler(handler)

    task.addPartialResultHandler(handler)
    task.emitPartialResults()
    task.emitPartialResults()
    assert len(calls) == 1


def test_reentrant_emit_returns_immediately():
    task = _makeTask({'A': {'partial': 1}})
    calls = []

    def handler(result):
        calls.append(result)
        task.emitPartialResults()

    task.addPartialResultHandler(handler)
    task.emitPartialResults()
    assert len(calls) == 1
    assert task.partialResultErrors == []


def test_raising_device_skipped_for_rest_of_run(caplog):
    task = _makeTask({'A': {'partial': 'a'}, 'B': {'partialError': RuntimeError("broken device")}})
    handler = _Recorder()
    task.addPartialResultHandler(handler)

    with caplog.at_level(logging.ERROR, logger='acq4'):
        for _ in range(3):
            task.emitPartialResults()

    assert task.tasks['B'].partialCalls == 1
    assert [sorted(c) for c in handler.calls] == [['A', 'protocol']] * 3
    assert len(task.partialResultErrors) == 1
    assert "'B'" in task.partialResultErrors[0]
    assert len([r for r in caplog.records if 'broken device' in r.getMessage()]) == 1


def test_execute_resets_per_run_state():
    task = _makeTask({'A': {'partial': 1}, 'B': {'partialError': RuntimeError("broken")}})
    handler = _Recorder(fail=2)
    task.addPartialResultHandler(handler)
    task.emitPartialResults()
    task.emitPartialResults()
    previousErrors = task.partialResultErrors
    assert len(previousErrors) == 1  # device B disabled; handler at 2 consecutive failures

    task.execute(block=False)
    try:
        assert task.partialResultErrors == []
        assert len(previousErrors) == 1
        handler.fail = 2
        task.emitPartialResults()
        task.emitPartialResults()
        # B is retried (and disabled again); the handler's count restarted, so it survives.
        assert task.tasks['B'].partialCalls == 2
        assert len(task.partialResultErrors) == 1
        task.emitPartialResults()
        assert len(handler.calls) == 5
    finally:
        task.stop()


def test_handlers_never_run_concurrently():
    task = _makeTask({'A': {'partial': 1}})
    state = {'active': 0, 'maxActive': 0, 'calls': 0}
    lock = threading.Lock()

    def handler(result):
        with lock:
            state['active'] += 1
            state['maxActive'] = max(state['maxActive'], state['active'])
            state['calls'] += 1
        time.sleep(0.002)
        with lock:
            state['active'] -= 1

    task.addPartialResultHandler(handler)
    nPerThread = 25
    barrier = threading.Barrier(2)

    def reader():
        barrier.wait(TIMEOUT)
        for _ in range(nPerThread):
            task.emitPartialResults()

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(TIMEOUT)
        assert not t.is_alive()
    assert state['calls'] == 2 * nPerThread
    assert state['maxActive'] == 1


def test_emit_does_not_take_task_lock():
    task = _makeTask({'A': {'partial': 1}})
    handler = _Recorder()
    task.addPartialResultHandler(handler)

    task.taskLock.lock()
    try:
        t = threading.Thread(target=task.emitPartialResults, daemon=True)
        t.start()
        t.join(TIMEOUT)
        assert not t.is_alive()
    finally:
        task.taskLock.unlock()
    assert len(handler.calls) == 1


class _ReaderDeviceTask(_FakeDeviceTask):
    """Like a DAQ reader: emits once, then once more while stop() joins it."""

    def start(self):
        self._stopRequested = threading.Event()
        self.joined = None
        task = self.parentTask()

        def run():
            task.emitPartialResults()
            self._stopRequested.wait(TIMEOUT)
            task.emitPartialResults()  # Task.stop() holds taskLock here

        self._reader = threading.Thread(target=run, daemon=True)
        self._reader.start()

    def stop(self, abort=False):
        self._stopRequested.set()
        self._reader.join(TIMEOUT)
        self.joined = not self._reader.is_alive()


def test_stop_joins_emitting_reader_thread():
    task = _makeTask({'A': {'partial': 1}}, devClasses={'A': _ReaderDeviceTask})
    handler = _Recorder()
    task.addPartialResultHandler(handler)
    task.execute(block=False)
    task.stop()
    assert task.tasks['A'].joined is True
    assert len(handler.calls) == 2


@pytest.mark.parametrize('protocol, expected', [
    ({}, None),
    ({'updateInterval': None}, None),
    ({'updateInterval': 0}, None),
    ({'updateInterval': -0.05}, None),
    ({'updateInterval': 0.05}, 0.05),
    ({'updateInterval': 1}, 1.0),
])
def test_update_interval(protocol, expected):
    task = _makeTask({'A': {}}, protocol=protocol)
    assert task.updateInterval() == expected


def test_settle_specs_aggregation(caplog):
    specA = {'primary': SettleSpec(0.0335, '10x mean downsampling'), 'command': SettleSpec(0.0)}
    task = _makeTask(
        {'A': {'specs': specA}, 'B': {'specs': {}}, 'C': {}, 'D': {'specs': RuntimeError('bad')}},
        devClasses={'C': _PlainDeviceTask},
    )
    with caplog.at_level(logging.ERROR, logger='acq4'):
        specs = task.settleSpecs()
    assert specs == {'A': specA}
    assert "D" in caplog.text
    specs['A']['primary'] = None
    assert task.tasks['A'].specs['primary'] == SettleSpec(0.0335, '10x mean downsampling')
