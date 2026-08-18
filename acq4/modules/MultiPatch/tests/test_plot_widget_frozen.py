"""Tests for PlotWidget's frozen mode: plotting a retained test-pulse history
with no live PatchClampTestPulse to read a current value from.

Autopatch's Area 5 reuses this widget for a finished action's plot (design doc
§4.5, "reuse, do not reimplement"), and its retained payload deliberately holds
no PatchClampTestPulse -- so tp is None there."""
import numpy as np
import pytest

from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _history(count=5):
    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(1e6, 1e9, count)
    history["access_resistance"] = np.linspace(1e6, 2e7, count)
    history["baseline_current"] = np.linspace(-1e-10, 1e-10, count)
    history["baseline_potential"] = np.linspace(-0.07, -0.06, count)
    history["time_constant"] = np.linspace(1e-4, 1e-3, count)
    history["capacitance"] = np.linspace(1e-12, 5e-12, count)
    return history


@pytest.mark.parametrize(
    "mode",
    [
        "ss resistance",
        "peak resistance",
        "holding current",
        "holding potential",
        "time constant",
        "capacitance",
    ],
)
def test_analysis_modes_plot_a_history_with_no_test_pulse(qapp, mode):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode=mode)

    widget.newTestPulse(None, _history())

    assert len(widget.plot.plotItem.listDataItems()) == 1


def test_the_current_value_label_is_blank_with_no_test_pulse(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.newTestPulse(None, _history())

    assert widget.tpLabel.toPlainText() == ""


def test_an_empty_history_plots_nothing_and_does_not_raise(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.newTestPulse(None, _history(count=0))

    assert widget.plot.plotItem.listDataItems() == []


def test_test_pulse_modes_clear_rather_than_raise_with_no_test_pulse(qapp):
    # 'test pulse' and 'tp analysis' need the recording itself, which a frozen
    # payload deliberately does not retain. They must degrade, not crash.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    for mode in ("test pulse", "tp analysis"):
        widget = PlotWidget(mode=mode)
        widget.newTestPulse(None, _history())
        assert widget.plot.plotItem.listDataItems() == []


def test_set_frozen_removes_the_modes_a_history_cannot_serve(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.setFrozen(True)

    items = [widget.modeCombo.itemText(i) for i in range(widget.modeCombo.count())]
    assert "test pulse" not in items
    assert "tp analysis" not in items
    assert "ss resistance" in items
    assert "capacitance" in items


def test_set_frozen_keeps_the_current_mode_selected(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="capacitance")

    widget.setFrozen(True)

    assert widget.modeCombo.currentText() == "capacitance"
    assert widget.mode == "capacitance"
