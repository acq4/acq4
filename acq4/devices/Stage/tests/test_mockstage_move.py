"""MockStage move-completion contract.

MockStage is the reference for the "lifetime monitor thread drives MoveFuture
completion" pattern: its single MockStageThread resolves the active move on
arrival and fails it on interrupt, with no per-move polling thread. These tests
lock in that contract (a move returns a future the monitor resolves on arrival
and fails on abort), which every Stage subclass adopting the pattern must meet.
"""
import numpy as np
import pytest
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
