"""A move carries its caller's throughline, plus its own name, into the thread that drives it.

Move completion is driven by raw producer threads (per-move monitors, or a stage's
lifetime monitor thread), which start with an empty context; without an explicit
restore, everything logged while a move runs is orphaned from the operation that
asked for the move.
"""
import threading

import pytest
from gentletask import task_chain, throughline
from unittest.mock import patch

from acq4.panic import GlobalHalt
from acq4.devices.MockStage import MockStage
from acq4.devices.Stage.Stage import MoveFuture


@pytest.fixture
def stage(qtbot):
    class MockDM:
        def __init__(self):
            self.globalHalt = GlobalHalt()

        def declareInterface(self, name, interfaces, obj):
            pass

        def getDevice(self, name):
            return None

        def readConfigFile(self, fn):
            return {}

    mock_dm = MockDM()
    config = {'driver': 'MockStage', 'nAxes': 3}
    with patch("acq4.Manager.Manager.single") as single:
        single.return_value = mock_dm
        dev = MockStage(mock_dm, config, "MockMoveStage")
        yield dev
        dev.quit()


def test_move_restores_callers_throughline_in_another_thread(stage):
    """A producer thread entering the move's context sees caller chain + move name."""
    with throughline(name="clean state"):
        fut = stage._move([100e-6, 0, 0], 1e-3, False, name="move to clean well")

    seen = []

    def producer():
        with fut.throughlineContext():
            seen.append(task_chain())

    thread = threading.Thread(target=producer)
    thread.start()
    thread.join(timeout=5)

    assert seen == [("clean state", "move to clean well")]


def test_producer_thread_runs_under_the_move_throughline(stage):
    """producerThread() gives device drivers a monitor thread with the context restored."""
    with throughline(name="clean state"):
        fut = stage._move([100e-6, 0, 0], 1e-3, False, name="move to clean well")

    seen = []
    thread = fut.producerThread(lambda: seen.append(task_chain()), name="fake monitor")
    thread.start()
    thread.join(timeout=5)

    assert thread.daemon
    assert seen == [("clean state", "move to clean well")]


def test_producer_thread_error_fails_the_move(stage):
    """A producer that raises before completing its move fails the move rather than leaving it pending."""
    fut = MoveFuture(stage, [100e-6, 0, 0], 1e-3, name="move with a failing monitor")

    def monitor():
        raise RuntimeError("no reply from device")

    thread = fut.producerThread(monitor, name="failing monitor")
    thread.start()
    thread.join(timeout=5)

    assert fut.is_done
    with pytest.raises(RuntimeError, match="no reply from device"):
        fut.wait(timeout=1)


def test_producer_thread_error_after_completion_is_still_raised(stage):
    """An error after the move already has an outcome is raised in the thread, not swallowed."""
    fut = MoveFuture(stage, [100e-6, 0, 0], 1e-3, name="completed move")
    thread_errors = []

    def monitor():
        fut.resolve(None)
        raise RuntimeError("late failure")

    with patch.object(threading, "excepthook", lambda args: thread_errors.append(args.exc_value)):
        thread = fut.producerThread(monitor, name="late-failing monitor")
        thread.start()
        thread.join(timeout=5)

    assert fut.wait(timeout=1) is None
    assert [str(e) for e in thread_errors] == ["late failure"]


def test_path_move_steps_nest_under_the_path_throughline(stage):
    """Each step of a path move carries the caller's chain, the path, and the step."""
    with throughline(name="clean state"):
        fut = stage.movePath(
            [
                {'position': [100e-6, 0, 0], 'speed': 1e-3, 'explanation': 'into the well'},
                {'position': [0, 0, 0], 'speed': 1e-3, 'explanation': 'back out'},
            ],
            name="clean path",
        )

    chains = []
    fired = threading.Event()

    def record(result, exc):
        chains.append(task_chain())
        fired.set()

    fut.add_finish_callback(record)

    assert fired.wait(timeout=10)
    assert chains == [("clean state", "clean path")]


def test_move_is_completed_under_the_move_throughline(stage):
    """The thread that actually completes the move runs under the move's throughline.

    Finish callbacks fire on the completing thread, so they observe the context the
    monitor thread was running under when it resolved the move.
    """
    chains = []
    fired = threading.Event()

    def record(result, exc):
        chains.append(task_chain())
        fired.set()

    with throughline(name="clean state"):
        fut = stage._move([1e-3, 0, 0], 1e-3, False, name="move to clean well")
        # Registered inside the context and immediately after the move starts: a
        # callback added after completion would fire inline on this thread instead of
        # on the thread that completed the move.
        fut.add_finish_callback(record)

    # Wait on the callback, not on the future: _finish wakes waiters before it runs
    # finish callbacks, so wait() can return before `record` has been called.
    assert fired.wait(timeout=10)
    assert chains == [("clean state", "move to clean well")]
