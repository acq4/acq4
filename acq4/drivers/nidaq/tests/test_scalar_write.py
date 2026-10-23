"""Tests for _NIDAQ.writeAnalogSample error handling on cached scalar tasks."""
import pytest

pytest.importorskip("PyDAQmx")

from acq4.drivers.nidaq.nidaq import _NIDAQ


class _FakeTask:
    def __init__(self, error=None):
        self.error = error
        self.writes = []
        self.stopped = False

    def WriteAnalogScalarF64(self, autoStart, timeout, value):
        self.writes.append(value)
        if self.error is not None:
            raise self.error

    def StopTask(self):
        self.stopped = True


def _driverWithTask(task, chan="/Dev1/ao0"):
    driver = _NIDAQ.__new__(_NIDAQ)  # skip the singleton guard
    driver._scalarTasks = {("ao", chan): task}
    return driver


def test_failed_write_stops_task_and_raises():
    task = _FakeTask(error=RuntimeError("value out of range"))
    driver = _driverWithTask(task)
    with pytest.raises(RuntimeError, match="out of range"):
        driver.writeAnalogSample("/Dev1/ao0", 17.67)
    assert task.stopped


def test_successful_write_leaves_task_running():
    task = _FakeTask()
    driver = _driverWithTask(task)
    driver.writeAnalogSample("/Dev1/ao0", 1.0)
    assert task.writes == [1.0]
    assert not task.stopped
