"""Tests for the PipetteTraining module's labelling invariants.

Everything here is headless. The stage behaviour under test is a real
:class:`~acq4.devices.Stage.Stage` subclass whose driver publishes positions the way
PMD, Dover and Mock do -- out of band, never from ``_getPosition`` -- since that
publication is precisely what the saved labels depend on.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

import acq4.Manager
import pyqtgraph as pg
from acq4.devices.Stage import Stage
from acq4.modules.PipetteTraining.PipetteTraining import (
    ALIGNMENT_DRIFT_ALLOWANCE,
    BACKGROUND_SURFACE_CLEARANCE,
    DEFAULT_MAX_STEP,
    REFERENCE_FRAMES_PER_STEP,
    REFERENCE_Z_STEP,
    SAMPLE_FRAMES_PER_STEP,
    PipetteTrainingWindow,
    _Skip,
)
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def manager(monkeypatch):
    """Install a stand-in in the global Manager singleton slot.

    InterfaceCombo and the device properties resolve devices on the global Manager;
    nothing tested here reaches a real one.
    """
    dm = MagicMock()
    monkeypatch.setattr(acq4.Manager.Manager, "single", dm)
    return dm


@pytest.fixture
def window(qapp, manager):
    module = MagicMock()
    module.manager = manager
    win = PipetteTrainingWindow(module)
    yield win
    win.close()


class TrailingStage(Stage):
    """A stage whose controller position and published position are separate things.

    ``_getPosition`` reads the controller and publishes nothing, which is what
    ``PMDStage``, ``DoverStage`` and ``MockStage`` do; only :meth:`publish` moves the
    device transform that ``globalPosition`` reads.
    """

    def __init__(self, dm, config, name):
        self._controllerPos = np.zeros(3)
        Stage.__init__(self, dm, config, name)

    def axes(self):
        return ("x", "y", "z")

    def _getPosition(self):
        return self._controllerPos.copy()

    @property
    def positionUpdatesPerSecond(self):
        return 50.0

    def publish(self):
        """Report the controller's position, as a driver's control thread would."""
        self.posChanged(self._controllerPos.copy())


class StageTip:
    """Stands in for the Pipette: a tip rigidly attached to the stage origin.

    The module reaches a pipette only for its orientation, its parent stage and its
    global position, and the behaviour under test belongs to the real Stage the last
    two delegate to.
    """

    def __init__(self, stage):
        self.parentStage = stage

    def globalPosition(self):
        return self.parentStage.globalPosition()

    def yawAngle(self):
        return 30.0

    def pitchAngle(self):
        return 25.0


@pytest.fixture
def trailingStage(qapp):
    stage = TrailingStage(MagicMock(), {}, "TrailingStage")
    stage.publish()  # settled at the origin
    return stage


class TestTipPosition:
    def test_waits_for_the_stage_to_publish_a_finished_move(self, trailingStage):
        """A move the controller has finished but not yet published must not be read
        back as the position it started from."""
        moved = np.array([1e-3, 0.0, 0.0])
        trailingStage._controllerPos = moved.copy()
        timer = threading.Timer(0.15, trailingStage.publish)
        timer.start()
        try:
            pos = PipetteTrainingWindow._tipPosition(StageTip(trailingStage))
        finally:
            timer.cancel()
        assert pos == pytest.approx(moved)

    def test_returns_an_already_published_position_without_waiting(self, trailingStage):
        moved = np.array([0.0, 2e-3, 0.0])
        trailingStage._controllerPos = moved.copy()
        trailingStage.publish()
        assert PipetteTrainingWindow._tipPosition(StageTip(trailingStage)) == pytest.approx(moved)


class FakeFrame:
    """A stack frame reduced to the only thing the alignment check reads."""

    def __init__(self, depth: float):
        self.depth = depth


def stackPair(step: float, count: int, offset: float) -> tuple[list, list]:
    """Two stacks of *count* frames *step* apart, the second shifted by *offset*."""
    first = [FakeFrame(i * step) for i in range(count)]
    second = [FakeFrame(i * step + offset) for i in range(count)]
    return first, second


class TestAssertStacksAligned:
    """The tolerance has to admit nearest-frame selection and nothing more.

    Each stack's planes land within half a frame spacing of the commanded depth, so a
    pair can disagree by one spacing with no drift at all; what the check exists to
    catch is the focus drift on top of that.
    """

    SAMPLE_STEP = DEFAULT_MAX_STEP  # the worst case: the widest step drawn
    SAMPLE_SPACING = SAMPLE_STEP / SAMPLE_FRAMES_PER_STEP

    def test_selection_granularity_alone_passes(self, window):
        first, second = stackPair(self.SAMPLE_STEP, 8, self.SAMPLE_SPACING)
        window._assertStacksAligned(
            first, second, "a.ma", "b.ma", self.SAMPLE_STEP, SAMPLE_FRAMES_PER_STEP
        )

    def test_drift_beyond_the_allowance_is_rejected(self, window):
        offset = self.SAMPLE_SPACING + 2 * ALIGNMENT_DRIFT_ALLOWANCE
        first, second = stackPair(self.SAMPLE_STEP, 8, offset)
        with pytest.raises(RuntimeError, match="Stack z mismatch"):
            window._assertStacksAligned(
                first, second, "a.ma", "b.ma", self.SAMPLE_STEP, SAMPLE_FRAMES_PER_STEP
            )

    def test_a_pair_cannot_disagree_by_more_than_the_displacement_it_labels(self, window):
        """At the widest z step the old step/2 tolerance was 7.5 um, more than the
        axial nudge the pair exists to teach."""
        first, second = stackPair(self.SAMPLE_STEP, 8, 7e-6)
        with pytest.raises(RuntimeError, match="Stack z mismatch"):
            window._assertStacksAligned(
                first, second, "a.ma", "b.ma", self.SAMPLE_STEP, SAMPLE_FRAMES_PER_STEP
            )

    def test_the_reference_pair_has_margin_over_its_own_selection_error(self, window):
        """Reference stacks are swept at frames_per_step 2.0, so their worst-case
        selection error is half their step -- which used to be the whole tolerance."""
        spacing = REFERENCE_Z_STEP / REFERENCE_FRAMES_PER_STEP
        first, second = stackPair(REFERENCE_Z_STEP, 8, spacing + 0.4e-6)
        window._assertStacksAligned(
            first, second, "ref.ma", "bg.ma", REFERENCE_Z_STEP, REFERENCE_FRAMES_PER_STEP
        )

    def test_reference_drift_beyond_the_allowance_is_still_rejected(self, window):
        spacing = REFERENCE_Z_STEP / REFERENCE_FRAMES_PER_STEP
        first, second = stackPair(REFERENCE_Z_STEP, 8, spacing + 1.2e-6)
        with pytest.raises(RuntimeError, match="Stack z mismatch"):
            window._assertStacksAligned(
                first, second, "ref.ma", "bg.ma", REFERENCE_Z_STEP, REFERENCE_FRAMES_PER_STEP
            )

    def test_a_length_mismatch_raises_without_relying_on_assert(self, window):
        """python -O strips assert, and a length mismatch must still stop the write."""
        first, second = stackPair(self.SAMPLE_STEP, 8, 0.0)
        with pytest.raises(RuntimeError, match="Stack length mismatch"):
            window._assertStacksAligned(
                first, second[:-1], "a.ma", "b.ma", self.SAMPLE_STEP, SAMPLE_FRAMES_PER_STEP
            )


FIELD_WIDTH = 300e-6
FIELD_HEIGHT = 200e-6
FIELD_CENTER = (1e-3, 2e-3, -1e-4)


SURFACE_Z = -5e-5


class FakeScope:
    def getSurfaceDepth(self):
        return SURFACE_Z


class FakeCamera:
    """A camera reduced to the field geometry the off-field target is derived from."""

    scopeDev = FakeScope()

    def globalCenterPosition(self, mode):
        assert mode == "roi"
        return np.array(FIELD_CENTER)

    def getBoundary(self, globalCoords=True, mode="roi"):
        x, y, _ = FIELD_CENTER
        return x - FIELD_WIDTH / 2, y - FIELD_HEIGHT / 2, FIELD_WIDTH, FIELD_HEIGHT


class FakePipette:
    """A pipette reduced to its orientation, which is all the geometry depends on."""

    def __init__(self, yaw: float, pitch: float = np.radians(30)):
        self._yaw = yaw
        self._pitch = pitch

    def yawRadians(self):
        return self._yaw

    def globalDirection(self):
        """Unit vector the tip points along, from the shank towards the tip."""
        return np.array(
            [
                np.cos(self._pitch) * np.cos(self._yaw),
                np.cos(self._pitch) * np.sin(self._yaw),
                -np.sin(self._pitch),
            ]
        )


class TestOffFieldTarget:
    HALF_DIAGONAL = np.hypot(FIELD_WIDTH, FIELD_HEIGHT) / 2

    def test_the_whole_shank_clears_the_frame_corner(self, window):
        """The 90-270 degree yaw constraint is what makes the 1.2 factor enough.

        It puts the frame center behind the tip, so the closest the shank ray comes to
        the center is the tip's own distance from it -- which the factor holds past the
        corner. A wider angle range would let the shank cross the field with the tip
        still outside it.
        """
        surfaceZ = FIELD_CENTER[2]
        for yaw in np.linspace(0, 2 * np.pi, 17):
            pip = FakePipette(yaw)
            for _ in range(50):
                target = window._offFieldTarget(pip, FakeCamera(), surfaceZ)
                toCenter = np.array(FIELD_CENTER)[:2] - target[:2]
                assert np.linalg.norm(toCenter) >= 1.2 * self.HALF_DIAGONAL
                # The shank runs backwards from the tip; a non-positive projection onto
                # it means the ray only ever gets further from the center.
                shank = -pip.globalDirection()[:2]
                assert np.dot(toCenter, shank) <= 0

    def test_the_spinner_adds_to_the_clearance_rather_than_capping_it(self, window):
        """The configured distance is extra beyond field clearance, so no value of it
        can put the pipette inside the frame."""
        extra = 40e-6
        window.backgroundMaxDistanceSpin.setValue(extra)
        for _ in range(100):
            target = window._offFieldTarget(FakePipette(0.0), FakeCamera(), FIELD_CENTER[2])
            reach = np.linalg.norm(np.array(FIELD_CENTER)[:2] - target[:2])
            assert 1.2 * self.HALF_DIAGONAL <= reach <= 1.2 * self.HALF_DIAGONAL + extra

    def test_a_zero_spinner_still_clears_the_field(self, window):
        window.backgroundMaxDistanceSpin.setValue(0.0)
        target = window._offFieldTarget(FakePipette(0.0), FakeCamera(), FIELD_CENTER[2])
        reach = np.linalg.norm(np.array(FIELD_CENTER)[:2] - target[:2])
        assert reach == pytest.approx(1.2 * self.HALF_DIAGONAL)

    def test_a_tip_at_sample_depth_is_not_carried_to_the_unviewed_spot(self, window):
        """Depth is irrelevant to a background stack, and the surface is one global
        number -- the tissue or chamber floor where nobody is looking may be higher."""
        tipZ = SURFACE_Z - 50e-6  # 50 um below the surface, the deepest default sample
        target = window._offFieldTarget(FakePipette(0.0), FakeCamera(), tipZ)
        assert target[2] >= SURFACE_Z + BACKGROUND_SURFACE_CLEARANCE

    def test_a_tip_already_clear_of_the_surface_is_not_driven_down(self, window):
        tipZ = SURFACE_Z + 10 * BACKGROUND_SURFACE_CLEARANCE
        target = window._offFieldTarget(FakePipette(0.0), FakeCamera(), tipZ)
        assert target[2] == pytest.approx(tipZ)


class TestSkipRequests:
    def test_a_skip_pressed_between_pairs_is_not_discarded(self, window):
        """The button is live across the whole run, so a press that lands between two
        pairs has to be honoured by the next one rather than thrown away."""
        window._skipRequested.set()
        with pytest.raises(_Skip):
            window._collectSamplePair(MagicMock(), MagicMock(), MagicMock())

    def test_a_honoured_skip_does_not_carry_into_the_next_location(self, window):
        window._skipRequested.set()
        with pytest.raises(_Skip):
            window._checkSkip()
        window._checkSkip()


class TestRandomTarget:
    """The lateral walk has to keep moving, and say so when it cannot."""

    @pytest.fixture(autouse=True)
    def camera(self, manager):
        manager.getDevice.return_value = FakeCamera()

    def test_successive_targets_move_laterally(self, window):
        window._roi = pg.RectROI((0.0, 0.0), (2e-3, 2e-3))
        first = window.randomTarget()
        second = window.randomTarget()
        assert not np.allclose(first[:2], second[:2])

    def test_a_region_with_no_area_is_rejected(self, window):
        """A region dragged to zero width froze the walk: every target shared one x,y
        and the run collected the same location forever without complaint."""
        window._roi = pg.RectROI((0.0, 0.0), (0.0, 2e-3))
        with pytest.raises(RuntimeError, match="no area"):
            window.randomTarget()


class TestPipettePose:
    """Whether the operator independently checked z has to survive into the dataset.

    The focus is put back on the commanded tip depth before the click, so a click with
    no refocus behind it reads that depth straight back and the label reproduces the
    calibration error. The correction the click made is the only thing that tells a
    pair whose z was checked from one whose z was not.
    """

    def test_records_how_far_the_click_corrected_the_commanded_depth(self, trailingStage):
        pose = PipetteTrainingWindow._pipettePose(StageTip(trailingStage), 8e-6)
        assert pose["tipClickZCorrection"] == pytest.approx(8e-6)
        assert pose["pipetteGlobalPosition"] == pytest.approx([0.0, 0.0, 0.0])

    def test_a_stack_with_no_click_behind_it_says_so(self, trailingStage):
        """Background stacks are acquired before the pair's click."""
        pose = PipetteTrainingWindow._pipettePose(StageTip(trailingStage), None)
        assert pose["tipClickZCorrection"] is None
