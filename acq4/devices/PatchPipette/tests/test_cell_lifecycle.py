"""A patch pipette's cell is the feature at its target, and it is retired when that target moves any other way.

Inside the Autopatch module the orchestrator hands every pipette its cell before
the protocol runs. Nothing does that for a hand-driven state change, so the cell
has to come from the target -- and, just as importantly, has to go when the
operator picks a different one, or the next state resumes tracking the old cell
and its tracker pulls the target straight back to it.
"""

from __future__ import annotations

import pytest
from coorx import Point

from acq4.devices.PatchPipette.states._base import PatchPipetteState
from acq4.util import Qt

from test_patchpipette_controls import Rig


class FakeCell(Qt.QObject):
    """The parts of acq4_automation's Cell that the device and the states touch.

    A stand-in rather than the real thing: acq4_automation lives in an internal
    repository and is not installed everywhere these tests run.
    """

    sigPositionChanged = Qt.Signal(object)
    sigTrackingMultipleFramesStart = Qt.Signal(object)
    sigTrackingMultipleFramesFinish = Qt.Signal(object)

    def __init__(self, position=(0.0, 0.0, 0.0), initialized=True):
        Qt.QObject.__init__(self)
        self.position = Point(position, 'global')
        self.isInitialized = initialized
        self.allow_refresh_reference = True
        self.tracking = []
        self._trackingFuture = _FakeTrackingFuture()

    def isTracking(self):
        return bool(self.tracking) and self.tracking[-1] is True

    def enableTracking(self, enable, reason=None):
        self.tracking.append(enable)

    def initializeTracker(self, *args, **kwds):
        self.isInitialized = True


class _FakeTrackingFuture(Qt.QObject):
    sigFinished = Qt.Signal(object)

    def __init__(self):
        Qt.QObject.__init__(self)
        self.is_done = False

    def wait(self, *args, **kwds):
        return None


@pytest.fixture
def rig(qapp):
    r = Rig()
    yield r
    r.quit()


@pytest.fixture
def dev(rig):
    d = rig.makePatchPipette()
    rig.pipette.setTarget((1e-3, 1e-3, 1e-3))
    return d


# ------------------------------------------------------------------- the device


def test_setting_a_cell_keeps_the_cell_it_was_just_given(dev):
    """setCell points the manipulator at the cell it was handed, so the retarget
    rule must not read its own write as the operator choosing something else."""
    cell = FakeCell((2e-3, 2e-3, 2e-3))
    dev.setCell(cell)
    assert dev.cell is cell
    assert tuple(dev.pipetteDevice.targetPosition()) == (2e-3, 2e-3, 2e-3)


def test_a_target_set_for_the_cell_keeps_the_cell(dev):
    """The tracker moves cell and target together; that is the same cell."""
    cell = FakeCell((2e-3, 2e-3, 2e-3))
    dev.setCell(cell)
    dev.setCellTarget((2e-3, 2e-3, 2.001e-3))
    assert dev.cell is cell


def test_a_target_set_any_other_way_retires_the_cell(dev):
    """The operator clicking a new cell in the camera view."""
    cell = FakeCell((2e-3, 2e-3, 2e-3))
    dev.setCell(cell)
    dev.pipetteDevice.setTarget((5e-3, 5e-3, 5e-3))
    assert dev.cell is None


def test_a_late_notice_of_the_cell_target_keeps_the_cell(dev):
    """setCell runs on the Autopatch orchestrator's worker thread, so the target
    change arrives on the GUI thread afterwards. Arriving late must not look like
    the operator choosing something else."""
    cell = FakeCell((2e-3, 2e-3, 2e-3))
    dev.setCell(cell)
    dev._pipetteTargetChanged(dev.pipetteDevice, dev.pipetteDevice.targetPosition())
    assert dev.cell is cell


def test_a_retired_cell_stops_tracking_and_is_kept(dev):
    cell = FakeCell((2e-3, 2e-3, 2e-3))
    dev.setCell(cell)
    dev.pipetteDevice.setTarget((5e-3, 5e-3, 5e-3))
    assert cell.tracking[-1] is False
    assert dev.previousCells[-1] is cell


def test_retiring_a_cell_still_reports_the_new_target(dev):
    """Closing the cell is extra work on this signal path, not a replacement for
    what it already did."""
    seen = []
    dev.sigTargetChanged.connect(lambda _dev, pos: seen.append(tuple(pos)))
    dev.setCell(FakeCell((2e-3, 2e-3, 2e-3)))
    dev.pipetteDevice.setTarget((5e-3, 5e-3, 5e-3))
    assert seen[-1] == (5e-3, 5e-3, 5e-3)


# -------------------------------------------------------------------- the states


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass

    def disconnect(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


class _FakeManipulator:
    def __init__(self):
        self.target = (0.0, 0.0, 0.0)

    def targetPosition(self):
        return self.target

    def globalPosition(self):
        # Far from the target, so a state is never "close enough to detect".
        return (0.0, 0.0, 1e-3)

    def setTarget(self, target):
        self.target = tuple(target)

    def imagingDevice(self):
        return None


class _FakeDev:
    """A PatchPipette as the tracking helpers in PatchPipetteState see one."""

    def __init__(self, cell=None):
        self.sigTargetChanged = _FakeSignal()
        self.sigActiveChanged = _FakeSignal()
        self.pipetteDevice = _FakeManipulator()
        self.cell = cell
        self.newCellCalls = 0
        self.cellTargets = []

    def newCell(self):
        self.newCellCalls += 1
        self.cell = FakeCell(self.pipetteDevice.targetPosition())

    def setCellTarget(self, target):
        self.cellTargets.append(tuple(target))
        self.pipetteDevice.setTarget(target)


def _trackingState(qapp, cell=None):
    dev = _FakeDev(cell)
    config = {'visualTargetTracking': True, 'minDetectionDistance': 7e-6}
    return PatchPipetteState(dev, config=config), dev


def test_tracking_makes_a_cell_when_the_pipette_has_none(qapp):
    """The reported crash: a hand-driven approach has no cell, and asking the
    pipette whether it is tracking blew up on None."""
    state, dev = _trackingState(qapp)
    state.maybeVisuallyTrackTarget()
    assert dev.newCellCalls == 1
    assert dev.cell.isTracking()


def test_tracking_keeps_the_cell_the_pipette_was_given(qapp):
    cell = FakeCell()
    state, dev = _trackingState(qapp, cell)
    state.maybeVisuallyTrackTarget()
    assert dev.newCellCalls == 0
    assert dev.cell is cell


def test_tracker_updates_reach_the_target_through_the_device(qapp):
    """Routed through PatchPipette.setCellTarget rather than straight at the
    manipulator, so the cell's own updates are not read as a retarget."""
    cell = FakeCell()
    state, dev = _trackingState(qapp, cell)
    state.maybeVisuallyTrackTarget()
    cell.sigPositionChanged.emit((7e-6, 8e-6, 9e-6))
    assert dev.cellTargets == [(7e-6, 8e-6, 9e-6)]


def test_stopping_tracking_on_a_retired_cell_is_quiet(qapp):
    state, dev = _trackingState(qapp, FakeCell())
    state.maybeVisuallyTrackTarget()
    dev.cell = None
    state.stopVisualTargetTracking("operator picked a different cell")


def test_the_tracking_future_finishing_after_a_retire_is_quiet(qapp):
    """closeCell() turns tracking off and drops the cell; the future's finish can
    land after that, and the handler must still know whose signals to undo."""
    cell = FakeCell()
    state, dev = _trackingState(qapp, cell)
    state.maybeVisuallyTrackTarget()
    dev.cell = None
    cell._trackingFuture.sigFinished.emit(cell._trackingFuture)
