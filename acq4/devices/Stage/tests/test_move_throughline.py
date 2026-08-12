"""A move carries its caller's throughline, plus its own name, into the thread that drives it.

Move completion is driven by raw producer threads (per-move monitors, or a stage's
lifetime monitor thread), which start with an empty context; without an explicit
restore, everything logged while a move runs is orphaned from the operation that
asked for the move.
"""
import threading

import pytest
from gentletask import task_chain, throughline
from unittest.mock import MagicMock, patch

from acq4.devices.MockStage import MockStage


@pytest.fixture
def stage(qtbot):
    class MockDM:
        def __init__(self):
            self.sigAbortAll = MagicMock()

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
    fut.add_finish_callback(lambda result, exc: chains.append(task_chain()))
    fut.wait(timeout=10)

    assert chains == [("clean state", "clean path")]


def test_move_is_completed_under_the_move_throughline(stage):
    """The thread that actually completes the move runs under the move's throughline.

    Finish callbacks fire on the completing thread, so they observe the context the
    monitor thread was running under when it resolved the move.
    """
    chains = []
    with throughline(name="clean state"):
        fut = stage._move([1e-3, 0, 0], 1e-3, False, name="move to clean well")
    fut.add_finish_callback(lambda result, exc: chains.append(task_chain()))

    fut.wait(timeout=10)

    assert chains == [("clean state", "move to clean well")]
