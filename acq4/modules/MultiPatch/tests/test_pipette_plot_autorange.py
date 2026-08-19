"""Tests for PlotWidget's Y-axis autorange behaviour in the resistance modes,
and a scope-creep guard for the modes deliberately left with a fixed range."""

import numpy as np
import pytest

from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _history(count=4):
    """A structured test-pulse history array, shaped like the real thing
    (see test_plot_widget_frozen.py's _history for the same convention)."""
    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(4e6, 7e6, count)
    history["access_resistance"] = np.linspace(4e6, 7e6, count)
    return history


@pytest.mark.parametrize("mode", ["ss resistance", "peak resistance"])
def test_resistance_mode_enables_y_autorange(qapp, mode):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode=mode)

    autoRange = widget.plot.getViewBox().state["autoRange"]
    assert autoRange[1] is not False, f"Y autorange should be enabled for {mode!r}, got {autoRange}"


@pytest.mark.parametrize("mode", ["ss resistance", "peak resistance"])
def test_resistance_mode_keeps_y_autorange_after_data_arrives(qapp, mode):
    """This is the reported bug: the plot loses its autorange once test-pulse
    data starts coming in."""
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode=mode)

    widget.newTestPulse(None, _history())

    autoRange = widget.plot.getViewBox().state["autoRange"]
    assert (
        autoRange[1] is not False
    ), f"Y autorange should still be enabled for {mode!r} after data, got {autoRange}"


def test_time_constant_mode_keeps_its_fixed_y_range(qapp):
    """Scope-creep guard: this task is resistance-only. time constant's mirror-
    image issue (autorange on Y, fixed on X) is a noted follow-up, not fixed here."""
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="time constant")

    autoRange = widget.plot.getViewBox().state["autoRange"]
    assert autoRange[1] is False
    # setYRange pads its target range, so compare loosely rather than exactly.
    lo, hi = widget.plot.getViewBox().viewRange()[1]
    assert lo == pytest.approx(-5, abs=0.5)
    assert hi == pytest.approx(-2, abs=0.5)


def test_capacitance_mode_keeps_its_fixed_y_range(qapp):
    """Scope-creep guard: capacitance's fixed Y range is untouched by this task."""
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="capacitance")

    autoRange = widget.plot.getViewBox().state["autoRange"]
    assert autoRange[1] is False
    # setYRange pads its target range, so compare loosely rather than exactly.
    lo, hi = widget.plot.getViewBox().viewRange()[1]
    assert lo == pytest.approx(0, abs=20e-12)
    assert hi == pytest.approx(100e-12, abs=20e-12)


def test_test_pulse_mode_keeps_full_autorange(qapp):
    """Scope-creep guard: the raw test-pulse trace already autoranges both axes."""
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="test pulse")

    autoRange = widget.plot.getViewBox().state["autoRange"]
    assert autoRange[0] is not False
    assert autoRange[1] is not False
