"""The Dover control thread's move handling, against a fake MotionSynergy axis.

No DLL and no hardware: the control thread is built without its ``__init__``, the only part
that touches MotionSynergy. What the real axis does is recorded at the top of
``acq4/drivers/dovermotion/smartstage.py``.
"""

from __future__ import annotations

import queue

import numpy as np
import pytest

pytest.importorskip("pythonnet")

try:
    from acq4.drivers.dovermotion.control_thread import (
        SmartStageControlThread,
        SmartStageRequestFuture,
    )
except RuntimeError as exc:
    # pythonnet installs anywhere, but loading coreclr is the first thing
    # motionsynergy_api does at import, and that needs a .NET runtime present.
    pytest.skip(f"no .NET runtime for MotionSynergy: {exc}", allow_module_level=True)


class FakeAlert:
    UserDescription = ''
    Description = 'Success'


class FakeResult:
    def __init__(self, success=True):
        self.Success = success
        self.Alert = FakeAlert()


class FakeValueResult(FakeResult):
    def __init__(self, value):
        FakeResult.__init__(self)
        self.Value = value


class FakeTask:
    """Stands in for a Task<InstrumentResult>: completes only when told to."""

    def __init__(self):
        self.IsCompleted = False
        self.Result = FakeResult()

    def complete(self, success=True):
        self.Result = FakeResult(success)
        self.IsCompleted = True


class FakeAxis:
    """One MotionSynergy axis. Appends every call to the shared *log*."""

    def __init__(self, name, pos, log):
        self.Name = name
        self.pos = pos
        self.log = log
        self.tasks = []

    def _record(self, *call):
        self.log.append((self.Name,) + call)

    def GetActualPosition(self):
        self._record('GetActualPosition')
        return FakeValueResult(self.pos)

    def MoveContinuous(self, position, acceleration, velocity, deceleration):
        self._record('MoveContinuous', position, acceleration, velocity, deceleration)
        return FakeResult()

    def WaitForContinuousMoveToComplete(self):
        self._record('WaitForContinuousMoveToComplete')
        task = FakeTask()
        self.tasks.append(task)
        return task

    def MoveAbsolute(self, position):
        self._record('MoveAbsolute', position)
        return FakeTask()

    def Stop(self):
        self._record('Stop')
        return FakeTask()

    def SetVelocity(self, velocity):
        self._record('SetVelocity', velocity)
        return FakeResult()

    def SetAcceleration(self, acceleration):
        self._record('SetAcceleration', acceleration)
        return FakeResult()


def make_thread(positions=(0.0, 0.0, 0.0), move_complete_threshold=5e-7):
    """Build a control thread around fake axes, skipping the MotionSynergy __init__."""
    log = []
    axes = [FakeAxis(n, p, log) for n, p in zip('XYZ', positions)]
    ct = SmartStageControlThread.__new__(SmartStageControlThread)
    ct.axes = axes
    ct.log = log
    ct.move_complete_threshold = move_complete_threshold
    ct.last_known_pos = np.array(positions, dtype=float)
    ct.last_reported_pos = None
    ct.pos_callback = None
    ct.enable_state_callback = None
    ct.last_enabled_state = None
    ct.last_enabled_poll = None
    ct.enabled_poll_interval = 0.5
    ct.target_update_rate = 1000.0
    ct.mean_loop_period = None
    ct._next_poll_deadline = 0.0
    ct.current_move = None
    ct.quit_request = None
    ct.request_queue = queue.Queue()
    ct.thread = None
    return ct


def move_request(ct, pos, speed=1.0, acceleration=10.0, name=None):
    return SmartStageRequestFuture(
        ct, 'move', dict(pos=list(pos), speed=speed, acceleration=acceleration, name=name)
    )


def calls(ct, kind):
    return [c for c in ct.log if c[1] == kind]


def test_move_from_rest_commands_every_axis_with_move_continuous():
    ct = make_thread()
    fut = move_request(ct, (1.0, 2.0, 2.0), speed=3.0, acceleration=30.0)
    ct._handle_move(fut)

    assert [c[0] for c in calls(ct, 'MoveContinuous')] == ['X', 'Y', 'Z']
    assert ct.current_move is fut
    assert fut.axes_commanded == frozenset({0, 1, 2})
    assert len(fut.tasks) == 3
    # speed and acceleration split in proportion to each axis' share of the distance
    per_axis = {c[0]: c for c in calls(ct, 'MoveContinuous')}
    dist = np.linalg.norm([1.0, 2.0, 2.0])
    for name, target in zip('XYZ', (1.0, 2.0, 2.0)):
        _, _, position, acceleration, velocity, deceleration = per_axis[name]
        assert position == target
        assert velocity == pytest.approx(3.0 * target / dist)
        assert acceleration == pytest.approx(30.0 * target / dist)
        assert deceleration == acceleration


def test_completion_task_is_taken_after_the_command():
    # the other order completes the move at once on an axis that was still at rest
    ct = make_thread()
    ct._handle_move(move_request(ct, (1.0, None, None)))
    assert [c[1] for c in ct.log if c[0] == 'X'] == [
        'MoveContinuous',
        'WaitForContinuousMoveToComplete',
    ]


def test_axis_already_at_its_target_is_not_commanded():
    ct = make_thread(positions=(5.0, 0.0, 0.0))
    fut = move_request(ct, (5.0, 1.0, None))
    ct._handle_move(fut)

    assert [c[0] for c in calls(ct, 'MoveContinuous')] == ['Y']
    assert fut.axes_commanded == frozenset({1})


def test_retarget_redirects_in_flight_and_never_stops():
    ct = make_thread()
    first = move_request(ct, (1.0, 1.0, 1.0), name='first')
    ct._handle_move(first)
    ct.last_known_pos = np.array([0.5, 0.5, 0.5])
    second = move_request(ct, (-1.0, -1.0, -1.0), name='second')
    ct._handle_move(second)

    assert len(calls(ct, 'MoveContinuous')) == 6
    assert calls(ct, 'Stop') == []
    # SetVelocity is refused by the hardware while an axis moves; nothing may rely on it
    assert calls(ct, 'SetVelocity') == []
    assert calls(ct, 'SetAcceleration') == []
    assert calls(ct, 'MoveAbsolute') == []
    assert ct.current_move is second


def test_superseded_request_reads_as_failed():
    ct = make_thread()
    first = move_request(ct, (1.0, 1.0, 1.0), name='first')
    ct._handle_move(first)
    ct._handle_move(move_request(ct, (2.0, 2.0, 2.0), name='second'))

    assert first.done()
    assert first.exc_info is None
    assert "'first'" in first.error
    assert "'second'" in first.error
    with pytest.raises(SmartStageRequestFuture.FutureError):
        first.wait(timeout=0)


def test_retarget_recommands_a_moving_axis_already_at_its_new_target():
    # a moving axis is not going to stay where it is, so the threshold must not skip it
    ct = make_thread()
    ct._handle_move(move_request(ct, (1.0, 1.0, 1.0)))
    ct.last_known_pos = np.array([0.5, 0.5, 0.5])
    ct.log.clear()
    ct._handle_move(move_request(ct, (0.5, 1.0, 1.0)))

    assert [c[0] for c in calls(ct, 'MoveContinuous')] == ['X', 'Y', 'Z']


def test_retarget_stops_a_moving_axis_the_new_request_does_not_target():
    ct = make_thread()
    ct._handle_move(move_request(ct, (1.0, 1.0, 1.0)))
    ct.last_known_pos = np.array([0.5, 0.5, 0.5])
    ct.log.clear()
    ct._handle_move(move_request(ct, (2.0, None, 2.0)))

    assert [c[0] for c in calls(ct, 'Stop')] == ['Y']
    assert [c[0] for c in calls(ct, 'MoveContinuous')] == ['X', 'Z']


def test_move_completes_when_every_commanded_axis_comes_to_rest():
    ct = make_thread()
    fut = move_request(ct, (1.0, 1.0, 1.0))
    ct._handle_move(fut)

    fut.tasks[0].complete()
    ct._check_move_status()
    assert not fut.done()

    for task in fut.tasks[1:]:
        task.complete()
    ct._check_move_status()
    assert fut.done()
    assert fut.error is None
    assert ct.current_move is None


def test_a_superseded_requests_tasks_cannot_complete_the_live_move():
    # they complete at the redirected target, so the live move must not be watching them
    ct = make_thread()
    first = move_request(ct, (1.0, 1.0, 1.0))
    ct._handle_move(first)
    second = move_request(ct, (2.0, 2.0, 2.0))
    ct._handle_move(second)

    for task in first.tasks:
        task.complete()
    ct._check_move_status()
    assert not second.done()
    assert ct.current_move is second


def test_a_failing_axis_fails_the_move():
    ct = make_thread()
    fut = move_request(ct, (1.0, 1.0, 1.0), name='doomed')
    ct._handle_move(fut)
    fut.tasks[0].complete(success=False)
    for task in fut.tasks[1:]:
        task.complete()
    ct._check_move_status()

    assert fut.done()
    assert 'doomed' in fut.error


def test_the_request_queue_is_drained_in_one_iteration():
    # a gamepad produces targets faster than the ~20 Hz loop
    ct = make_thread()
    iterations = []
    ct._check_position = lambda: iterations.append(len(ct.log))
    ct._check_enabled_state = lambda: None

    for i in range(5):
        ct.request_queue.put(move_request(ct, (float(i + 1), None, None)))
    quit_req = SmartStageRequestFuture(ct, 'quit', {})
    ct.request_queue.put(quit_req)
    ct._run()

    assert len(iterations) == 1
    assert [c[2] for c in calls(ct, 'MoveContinuous')] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert quit_req.done()


def _reporting_thread(positions, callback):
    ct = make_thread(positions=positions)
    ct.callback_threshold = 1e-6
    ct.pos_callback = callback
    return ct


def test_a_failing_position_callback_does_not_stop_the_loop():
    # the first report is as exposed as every later one: an exception here would leave a
    # stage in MoveContinuous with no supervisor and no way to stop it
    seen = []

    def callback(pos):
        seen.append(list(pos))
        raise RuntimeError('callback blew up')

    ct = _reporting_thread((1.0, 2.0, 3.0), callback)
    ct._check_position()
    assert seen == [[1.0, 2.0, 3.0]]
    assert list(ct.last_known_pos) == [1.0, 2.0, 3.0]
    assert ct.last_reported_pos is None  # not recorded as reported, so the next one fires

    ct.axes[0].pos = 5.0
    ct._check_position()
    assert seen == [[1.0, 2.0, 3.0], [5.0, 2.0, 3.0]]


def test_position_reports_follow_the_threshold():
    seen = []
    ct = _reporting_thread((1.0, 2.0, 3.0), lambda pos: seen.append(list(pos)))
    ct._check_position()
    ct._check_position()
    assert seen == [[1.0, 2.0, 3.0]]        # first report, then nothing while at rest
    ct.axes[2].pos = 3.0 + 1e-9
    ct._check_position()
    assert len(seen) == 1                   # under the threshold
    ct.axes[2].pos = 4.0
    ct._check_position()
    assert seen[-1] == [1.0, 2.0, 4.0]
    assert list(ct.last_reported_pos) == [1.0, 2.0, 4.0]
