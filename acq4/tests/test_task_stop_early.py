"""Manager.Task.stopEarly(), with a stand-in manager and fake device tasks."""

import pytest

from acq4.Manager import Task
from acq4.devices.Device import DeviceTask

EVENTS = []


class _Locker:
    def __init__(self, manager):
        self.manager = manager

    def lock(self):
        self.manager.locked += 1

    def unlock(self):
        self.manager.locked -= 1


class _Halt:
    def check(self):
        pass


class _FakeManager:
    def __init__(self, devices):
        self.devices = {d.name(): d for d in devices}
        self.globalHalt = _Halt()
        self.locked = 0

    def getDevice(self, name):
        return self.devices[name]

    def reserveDevices(self, devices, timeout=10.0, reserver=None):
        return _Locker(self)

    def _taskStarted(self, task):
        pass

    def _taskFinished(self, task):
        pass


class _Device:
    def __init__(self, name, taskClass):
        self._name = name
        self.taskClass = taskClass

    def name(self):
        return self._name

    def createTask(self, cmd, parentTask):
        return self.taskClass(self, cmd, parentTask)


class _RecordingTask(DeviceTask):
    supportsEarlyStop = True

    def __init__(self, dev, cmd, parentTask):
        DeviceTask.__init__(self, dev, cmd, parentTask)
        self.done = cmd.get('done', False)

    def isDone(self):
        return self.done

    def stop(self, abort=False):
        EVENTS.append(('stop', self.dev.name(), abort))
        self.done = True

    def getResult(self):
        return self.dev.name()


class _TimingTask(_RecordingTask):
    """Stands in for NiDAQ.Task: owns acquisition timing and truncates in stopEarly()."""

    def __init__(self, dev, cmd, parentTask):
        _RecordingTask.__init__(self, dev, cmd, parentTask)
        self.earlyInfo = cmd.get('earlyInfo', {'numPtsAcquired': 123, 'stopTime': 0.0})
        self.error = cmd.get('error')

    def stopEarly(self):
        EVENTS.append(('stopEarly', self.dev.name()))
        self.done = True
        if self.error is not None:
            raise self.error
        return self.earlyInfo


class _UnsupportedTask(_RecordingTask):
    supportsEarlyStop = False


class _PlainTask(DeviceTask):
    """Inherits DeviceTask's supportsEarlyStop (False)."""


@pytest.fixture(autouse=True)
def clearEvents():
    del EVENTS[:]


def makeTask(devs, duration=10.0):
    devices = [_Device(name, cls) for name, (cls, _) in devs.items()]
    command = {'protocol': {'duration': duration}, **{name: cmd for name, (_, cmd) in devs.items()}}
    dm = _FakeManager(devices)
    return Task(dm, command), dm


def test_timing_tasks_stop_early_before_any_stop():
    task, dm = makeTask({'DAQ': (_TimingTask, {}), 'Clamp': (_RecordingTask, {})})
    task.execute(block=False)
    assert not task.isDone()
    assert task.stopEarly() is True
    assert EVENTS[0] == ('stopEarly', 'DAQ')
    assert sorted(EVENTS[1:]) == [('stop', 'Clamp', False), ('stop', 'DAQ', False)]
    assert task.isDone()
    result = task.getResult()
    assert result['protocol']['stoppedEarly'] is True
    assert result['protocol']['numPtsAcquired'] == {'DAQ': 123}
    assert result['protocol']['stopTime'] == task.stopTime
    assert result['DAQ'] == 'DAQ' and result['Clamp'] == 'Clamp'
    assert dm.locked == 0


def test_untruncated_timing_task_records_stopped_early_false():
    task, dm = makeTask({'DAQ': (_TimingTask, {'earlyInfo': None})})
    task.execute(block=False)
    assert task.stopEarly() is False
    assert task.getResult()['protocol'] == {'startTime': task.startTime, 'stoppedEarly': False}


@pytest.mark.parametrize('cls', [_UnsupportedTask, _PlainTask])
def test_unsupported_device_raises_before_stopping_anything(cls):
    task, dm = makeTask({'DAQ': (_TimingTask, {}), 'Camera': (cls, {})})
    task.execute(block=False)
    with pytest.raises(RuntimeError, match=r"\['Camera'\] cannot truncate"):
        task.stopEarly()
    assert EVENTS == []
    assert not task.stopped and dm.locked == 1
    task.stop(abort=True)
    assert dm.locked == 0


def test_not_started_raises():
    task, dm = makeTask({'DAQ': (_TimingTask, {})})
    with pytest.raises(RuntimeError, match="not been started"):
        task.stopEarly()


def test_finished_task_is_stopped_normally():
    task, dm = makeTask(
        {'DAQ': (_TimingTask, {'done': True}), 'Camera': (_UnsupportedTask, {'done': True})},
        duration=0.0,
    )
    task.execute(block=False)
    assert task.isDone()
    assert task.stopEarly() is False
    assert ('stopEarly', 'DAQ') not in EVENTS
    assert task.getResult()['protocol']['stoppedEarly'] is False


def test_failing_stop_early_aborts_the_task():
    task, dm = makeTask(
        {'DAQ': (_TimingTask, {'error': OSError("DAQ gone")}), 'Clamp': (_RecordingTask, {})}
    )
    task.execute(block=False)
    with pytest.raises(OSError, match="DAQ gone"):
        task.stopEarly()
    assert ('stop', 'Clamp', True) in EVENTS and ('stop', 'DAQ', True) in EVENTS
    assert task.result is None and dm.locked == 0


def test_stop_early_inside_a_partial_handler_raises():
    task, dm = makeTask({'DAQ': (_TimingTask, {})})
    errors = []

    def handler(result):
        try:
            task.stopEarly()
        except RuntimeError as exc:
            errors.append(exc)

    task.addPartialResultHandler(handler)
    task.execute(block=False)
    task.emitPartialResults()
    assert len(errors) == 1 and 'partial-result handler' in str(errors[0])
    assert EVENTS == []
    assert task.stopEarly() is True
