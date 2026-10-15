"""MockStage move-completion contract.

MockStage is the reference for the "lifetime monitor thread drives MoveFuture
completion" pattern: its single MockStageThread resolves the active move on
arrival and fails it on interrupt, with no per-move polling thread. These tests
lock in that contract (a move returns a future the monitor resolves on arrival
and fails on abort), which every Stage subclass adopting the pattern must meet.
"""
import threading

import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from acq4.panic import GlobalHalt
from acq4.devices.MockStage import MockStage, MockStageThread


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


def test_move_resolves_on_arrival(stage):
    # The lifetime MockStageThread, not a per-move thread, completes the move.
    fut = stage._move([100e-6, 0, 0], 1e-3, False)
    fut.wait(timeout=5)
    assert fut.is_done and not fut.is_stopped
    np.testing.assert_allclose(stage.getPosition()[:3], [100e-6, 0, 0], atol=1e-6)


def test_abort_fails_move_in_flight(stage):
    # A slow move is interrupted mid-flight; the monitor completes it as failed.
    fut = stage._move([5e-3, 0, 0], 50e-6, False)
    assert not fut.is_done
    stage.abort()
    with pytest.raises(RuntimeError):
        fut.wait(timeout=5)
    assert fut.is_done


def test_quit_joins_monitor_thread(stage):
    # quit() must not return while the monitor is still running: a live QThread
    # whose Python wrapper is later garbage-collected aborts the process with
    # "QThread: Destroyed while thread is still running".
    stage.quit()
    assert not stage.stageThread.isRunning()


def test_arrival_does_not_resolve_a_superseding_move(qtbot):
    # A move submitted while the monitor is retiring an earlier arrival must keep
    # its target and must not be resolved at the earlier move's position.
    thread = MockStageThread()
    first = MagicMock()
    second = MagicMock()
    superseded = threading.Event()
    resolvedAt = []

    second.mockFinish.side_effect = lambda: resolvedAt.append(thread.getPosition()[:3])

    setPosition = thread._setPosition

    def supersedeOnArrival(pos):
        # Land the second move in the window between the monitor deciding the
        # first has arrived and it clearing/resolving that move.
        setPosition(pos)
        if not superseded.is_set():
            thread.setTarget(second, np.array([100e-6, 0.0, 0.0]), 1e-3)
            superseded.set()

    thread._setPosition = supersedeOnArrival
    thread.setTarget(first, np.zeros(3), 1e-3)
    thread.start()
    try:
        qtbot.waitUntil(superseded.is_set, timeout=2000)
        qtbot.waitUntil(lambda: bool(resolvedAt), timeout=2000)
    finally:
        thread.quit()

    np.testing.assert_allclose(resolvedAt[0], [100e-6, 0, 0], atol=1e-6)
