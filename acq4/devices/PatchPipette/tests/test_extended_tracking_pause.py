"""Tests that the pipette stays still for every multi-frame tracking acquisition.

The pause used to be a one-shot latch that rewired its own two signals from inside
their handlers. A Start arriving before the matching Finish had been delivered was
silently dropped, and the first Finish then released the pause while an acquisition
was still running -- which is what a second reference stack taken straight after the
first produces, leaving the pipette free to move during it.
"""

import pytest
from acq4.util import Qt

from acq4.devices.PatchPipette.states._base import PatchPipetteState


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _FakeDev:
    def __init__(self):
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()


class _Cell(Qt.QObject):
    """Just the two signals Cell.updatePosition brackets a multi-frame step with."""

    sigTrackingMultipleFramesStart = Qt.Signal(object)
    sigTrackingMultipleFramesFinish = Qt.Signal(object)


@pytest.fixture
def state_and_cell(qapp):
    state = PatchPipetteState(_FakeDev(), config={})
    cell = _Cell()
    state._connectExtendedTrackingPause(cell)
    return state, cell


def test_a_multi_frame_step_pauses_the_pipette(state_and_cell):
    state, cell = state_and_cell
    cell.sigTrackingMultipleFramesStart.emit(cell)
    assert state._pauseMovement is True


def test_the_pipette_resumes_when_the_step_finishes(state_and_cell):
    state, cell = state_and_cell
    cell.sigTrackingMultipleFramesStart.emit(cell)
    cell.sigTrackingMultipleFramesFinish.emit(cell)
    assert state._pauseMovement is False


def test_consecutive_steps_each_pause(state_and_cell):
    """Two reference stacks in a row: the second must pause as the first did."""
    state, cell = state_and_cell
    for _ in range(2):
        cell.sigTrackingMultipleFramesStart.emit(cell)
        assert state._pauseMovement is True
        cell.sigTrackingMultipleFramesFinish.emit(cell)
        assert state._pauseMovement is False


def test_a_second_start_before_the_first_finish_keeps_the_pause(state_and_cell):
    """The reported failure. Whatever the interleaving, the pipette must not be
    released while an acquisition is outstanding."""
    state, cell = state_and_cell
    cell.sigTrackingMultipleFramesStart.emit(cell)
    cell.sigTrackingMultipleFramesStart.emit(cell)
    cell.sigTrackingMultipleFramesFinish.emit(cell)
    assert state._pauseMovement is True, "released while a second stack was running"
    cell.sigTrackingMultipleFramesFinish.emit(cell)
    assert state._pauseMovement is False


def test_an_unmatched_finish_does_not_raise(state_and_cell):
    """A stop between the two emissions can strand a Finish with no Start."""
    state, cell = state_and_cell
    cell.sigTrackingMultipleFramesFinish.emit(cell)
    assert state._pauseMovement is False
    cell.sigTrackingMultipleFramesStart.emit(cell)
    assert state._pauseMovement is True


def test_the_pause_starts_released(qapp):
    state = PatchPipetteState(_FakeDev(), config={})
    assert state._pauseMovement is False
