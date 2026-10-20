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
from acq4.devices.Stage import Stage
from acq4.modules.PipetteTraining.PipetteTraining import (
    ALIGNMENT_DRIFT_ALLOWANCE,
    DEFAULT_MAX_STEP,
    REFERENCE_FRAMES_PER_STEP,
    REFERENCE_Z_STEP,
    SAMPLE_FRAMES_PER_STEP,
    PipetteTrainingWindow,
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

    ``_tipPosition`` reaches only for the parent stage and the tip's global position,
    and the behaviour under test belongs to the real Stage this delegates to.
    """

    def __init__(self, stage):
        self.parentStage = stage

    def globalPosition(self):
        return self.parentStage.globalPosition()


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
