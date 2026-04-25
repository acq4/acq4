# Tests for ZPositionWidget movement state tracking behavior.
# Uses a mock plot to avoid requiring a full Qt application.

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_plot():
    """A minimal plot mock that returns InfiniteLine-like objects."""
    def make_line():
        line = MagicMock()
        line._value = 0.0
        line.value = lambda: line._value
        line.setValue = lambda v: line.__setattr__('_value', v)
        return line

    plot = MagicMock()
    plot.addLine = MagicMock(side_effect=lambda **kwargs: make_line())
    return plot


@pytest.fixture
def widget(qtbot, mock_plot):
    from acq4.util.ui.ZPositionWidget import ZPositionWidget
    w = ZPositionWidget(mock_plot)
    qtbot.addWidget(w)
    return w


class TestSetMoving:
    def test_setMoving_false_snaps_target_to_focus(self, widget):
        widget.setFocusDepth(100e-6)
        widget.setTargetDepth(200e-6)
        widget.setMovingToTarget(False)
        assert widget.targetLine.value() == pytest.approx(100e-6)

    def test_setMoving_true_leaves_target_unchanged(self, widget):
        widget.setFocusDepth(100e-6)
        widget.setTargetDepth(200e-6)
        widget.setMovingToTarget(True)
        assert widget.targetLine.value() == pytest.approx(200e-6)

    def test_setMoving_false_after_true_snaps_to_updated_focus(self, widget):
        widget.setTargetDepth(200e-6)
        widget.setMovingToTarget(True)
        widget.setFocusDepth(150e-6)  # device moved partway
        widget.setFocusDepth(200e-6)  # device arrived
        widget.setMovingToTarget(False)
        assert widget.targetLine.value() == pytest.approx(200e-6)

    def test_setMoving_false_with_no_prior_target_uses_focus(self, widget):
        widget.setFocusDepth(50e-6)
        widget.setMovingToTarget(False)
        assert widget.targetLine.value() == pytest.approx(50e-6)
