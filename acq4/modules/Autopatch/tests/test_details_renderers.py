"""Tests for the kind -> widget builders behind Area 5's detail pane, each
given the plain-data payload an action's set_details() hands over."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_text_builder_renders_each_line_read_only(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {"lines": ["surface at 1.2 mm", "depth ok"]})

    assert widget.isReadOnly()
    assert "surface at 1.2 mm" in widget.toPlainText()
    assert "depth ok" in widget.toPlainText()


def test_text_builder_tolerates_a_missing_lines_key(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {})

    assert widget.toPlainText() == ""


def test_text_builder_stringifies_non_strings(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {"lines": [42, None]})

    assert "42" in widget.toPlainText()
    assert "None" in widget.toPlainText()


def test_error_builder_returns_an_error_block(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget
    from acq4.modules.Autopatch.error_display import ErrorBlock

    widget = buildDetailsWidget(
        "error",
        {
            "exc_type": "BrokenPipette",
            "exc_message": "tip sheared off",
            "traceback_text": "Traceback...\nBrokenPipette: tip sheared off",
            "cell_repr": "<Cell 0x1>",
        },
    )

    assert isinstance(widget, ErrorBlock)
    assert "BrokenPipette" in widget.headlineLabel.text()
    assert "tip sheared off" in widget.headlineLabel.text()
    assert "<Cell 0x1>" in widget.cellLabel.text()


def test_error_builder_tolerates_a_missing_cell_repr(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "error",
        {"exc_type": "E", "exc_message": "m", "traceback_text": "t"},
    )

    assert not widget.cellLabel.isVisible()


def test_unregistered_kind_renders_as_text_rather_than_raising(qapp):
    # A payload crosses a thread boundary out of protocol code. A protocol
    # author's typo must leave the pane usable, not take it down.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("no_such_kind", {"a": 1})

    assert "no_such_kind" in widget.toPlainText()
    assert "'a': 1" in widget.toPlainText()


def test_captioned_puts_the_caption_above_the_widget(qapp):
    from acq4.modules.Autopatch.details_renderers import captioned

    inner = Qt.QLabel("inner")
    wrapper = captioned(inner, ["12 sweeps", "saved to protocol_000"])

    assert wrapper.layout().indexOf(inner) != -1
    caption = wrapper.layout().itemAt(0).widget()
    assert "12 sweeps" in caption.text()
    assert "saved to protocol_000" in caption.text()


def test_captioned_with_no_lines_returns_the_widget_itself(qapp):
    from acq4.modules.Autopatch.details_renderers import captioned

    inner = Qt.QLabel("inner")

    assert captioned(inner, []) is inner


def test_image_stack_builder_opens_at_the_center_index(qapp):
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    wrapper = buildDetailsWidget(
        "image_stack", {"stack": stack, "center_index": 2, "title": "Cellfie"}
    )

    view = wrapper.findChild(pg.ImageView)
    assert view is not None
    assert view.currentIndex == 2


def test_image_stack_builder_shows_the_title_as_its_caption(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "image_stack",
        {"stack": np.zeros((3, 4, 4)), "center_index": 1, "title": "Cellfie"},
    )

    caption = wrapper.layout().itemAt(0).widget()
    assert "Cellfie" in caption.text()


def test_image_stack_builder_tolerates_a_none_center_index(qapp):
    # A 2D image or a single-frame stack has no meaningful center frame.
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "image_stack", {"stack": np.zeros((4, 4)), "center_index": None, "title": ""}
    )

    # An empty title means captioned() returns the view itself, unwrapped.
    assert isinstance(wrapper, pg.ImageView)
    assert wrapper.currentIndex == 0


def test_task_results_builder_plots_one_curve_per_sweep(qapp):
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    payload = {
        "traces": [(t, t * 1.0), (t, t * 2.0), (t, t * 3.0)],
        "sequence_dir": "protocol_000",
        "decimation": 1,
        "units": "A",
    }

    wrapper = buildDetailsWidget("task_results", payload)

    plot = wrapper.findChild(pg.PlotWidget)
    assert plot is not None
    assert len(plot.plotItem.listDataItems()) == 3


def test_task_results_caption_reports_sweeps_directory_and_decimation(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [(t, t)],
            "sequence_dir": "protocol_007",
            "decimation": 25,
            "units": "A",
        },
    )

    text = wrapper.layout().itemAt(0).widget().text()
    assert "1" in text
    assert "protocol_007" in text
    assert "25" in text


def test_task_results_caption_omits_decimation_when_undecimated(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [(t, t)],
            "sequence_dir": "protocol_000",
            "decimation": 1,
            "units": "A",
        },
    )

    assert "decimated" not in wrapper.layout().itemAt(0).widget().text()


def test_task_results_builder_tolerates_no_traces(qapp):
    # A sequence stopped before its first sweep completed.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [],
            "sequence_dir": "protocol_000",
            "decimation": 1,
            "units": "A",
        },
    )

    assert wrapper is not None


def _tpHistory(count=5):
    import numpy as np
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(1e6, 1e9, count)
    return history


def _tpPayload(**overrides):
    payload = {
        "history": _tpHistory(),
        "transitions": [(0.0, "approach"), (1.5, "seal"), (3.0, "whole cell")],
        "entry_state": "approach",
        "reached": "whole cell",
        "log_file": "MultiPatch_004.log",
    }
    payload.update(overrides)
    return payload


def test_test_pulse_history_plots_the_retained_history(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    assert plot is not None
    assert len(plot.plot.plotItem.listDataItems()) == 1


def test_test_pulse_history_keeps_the_mode_combo_visible(qapp):
    # Re-reading a finished attempt through a different field is what the
    # dropdown is for; only the live plot hides it.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    assert not plot.modeCombo.isHidden()


def test_test_pulse_history_offers_no_live_only_modes(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    items = [plot.modeCombo.itemText(i) for i in range(plot.modeCombo.count())]
    assert "test pulse" not in items
    assert "tp analysis" not in items


def test_test_pulse_history_lists_the_state_transitions(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    transitions = widget.findChild(Qt.QListWidget)
    assert transitions is not None
    rows = [transitions.item(i).text() for i in range(transitions.count())]
    assert len(rows) == 3
    assert "approach" in rows[0]
    assert "seal" in rows[1]
    assert "whole cell" in rows[2]


def test_transition_rows_show_the_elapsed_time_from_the_first(qapp):
    # Absolute epoch timestamps are unreadable; what matters is how long the
    # FSM sat in each state.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history",
        _tpPayload(transitions=[(1000.0, "approach"), (1002.5, "seal")]),
    )

    transitions = widget.findChild(Qt.QListWidget)
    assert "0.00" in transitions.item(0).text()
    assert "2.50" in transitions.item(1).text()


def test_test_pulse_history_caption_reports_the_terminal_state_and_log(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    caption = widget.layout().itemAt(0).widget().text()
    assert "approach" in caption
    assert "whole cell" in caption
    assert "MultiPatch_004.log" in caption


def test_test_pulse_history_caption_handles_never_reaching_a_terminal(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history", _tpPayload(reached=None, log_file=None)
    )

    caption = widget.layout().itemAt(0).widget().text()
    assert "approach" in caption
    assert "no terminal state" in caption


def test_test_pulse_history_tolerates_an_empty_history(qapp):
    # A patch stopped before its first test pulse landed.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history", _tpPayload(history=_tpHistory(count=0), transitions=[])
    )

    assert widget is not None


def test_test_pulse_history_tolerates_no_transitions(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload(transitions=[]))

    assert widget.findChild(Qt.QListWidget).count() == 0


def _curveData(plot):
    """The (x, y) a PlotWidget's single curve was given.

    The underlying data, not getData()'s display copy: the display copy is
    log-transformed with the mode's log setting, so it moves whenever the mode
    does, whether or not anything re-plotted.
    """
    items = plot.plot.plotItem.listDataItems()
    assert len(items) == 1
    return items[0].xData, items[0].yData


def test_switching_a_frozen_plots_mode_replots_the_new_field(qapp):
    # setMode only moves the axis label, the log mode and the Y range. A live
    # plot redraws on its next test pulse; a frozen one never gets another, so
    # without a re-plot the resistance curve would sit under a "Capacitance / F"
    # axis -- wrong scientific data in front of an operator judging an attempt.
    import numpy as np

    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    history = _tpHistory()
    history["capacitance"] = np.linspace(1e-12, 50e-12, len(history))
    widget = buildDetailsWidget("test_pulse_history", _tpPayload(history=history))
    plot = widget.findChild(PlotWidget)
    before = _curveData(plot)

    plot.modeCombo.setText("capacitance")

    assert plot.mode == "capacitance"
    after = _curveData(plot)
    assert not np.array_equal(after[1], before[1])
    assert np.allclose(after[1], history["capacitance"])


def _viewRange(plot):
    """The plot's (xRange, yRange), with any pending auto-range applied.

    pyqtgraph defers an enabled auto-range until the view is next painted.
    Nothing paints in a headless test, so ask the view for the same
    recomputation a paint would trigger before reading its range.
    """
    vb = plot.plot.plotItem.vb
    vb.prepareForPaint()
    return vb.viewRange()


def test_test_pulse_history_opens_fitted_to_its_data(qapp):
    # 'ss resistance' opens on MultiPatch's fixed 1 MΩ - 10 GΩ window, which
    # suits a live plot whose scale must hold still while numbers stream in. A
    # finished attempt is the opposite case: the whole history is already there
    # and the operator should not have to fit it by hand to read it.
    import numpy as np

    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    history = _tpHistory(count=6)
    history["steady_state_resistance"] = np.linspace(2e8, 8e10, 6)
    widget = buildDetailsWidget("test_pulse_history", _tpPayload(history=history))
    plot = widget.findChild(PlotWidget)

    (xLo, xHi), (yLo, yHi) = _viewRange(plot)
    # This mode is log-y, so the view range is in decades, not ohms.
    dataLo, dataHi = np.log10(2e8), np.log10(8e10)
    assert yLo <= dataLo and yHi >= dataHi
    # Covering the data is not enough: a window far wider than the data covers
    # it too. The fit has to be snug, modulo pyqtgraph's own padding.
    assert (yHi - yLo) < (dataHi - dataLo) * 1.5
    assert xLo <= 0 and xHi >= 5
    assert (xHi - xLo) < 5 * 1.5


def test_switching_a_frozen_plots_mode_refits_the_new_field(qapp):
    # Each mode carries its own fixed Y range, so re-reading the attempt as
    # capacitance would otherwise drop a 500-900 pF curve into a 0-100 pF
    # window and show the operator an empty plot.
    import numpy as np

    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    history = _tpHistory(count=6)
    history["capacitance"] = np.linspace(5e-10, 9e-10, 6)
    widget = buildDetailsWidget("test_pulse_history", _tpPayload(history=history))
    plot = widget.findChild(PlotWidget)

    plot.modeCombo.setText("capacitance")

    _, (yLo, yHi) = _viewRange(plot)
    assert yLo <= 5e-10 and yHi >= 9e-10
    assert (yHi - yLo) < (9e-10 - 5e-10) * 1.5


def test_a_hand_zoom_is_not_fought_back_by_the_fit(qapp):
    # pyqtgraph turns auto-range off the moment a range is set by hand, which is
    # exactly the wanted division of labour: fit until the operator takes over.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())
    plot = widget.findChild(PlotWidget)
    vb = plot.plot.plotItem.vb
    _viewRange(plot)

    vb.scaleBy((0.5, 0.5))  # what a scroll wheel over the plot does

    assert vb.autoRangeEnabled() == [False, False]
    zoomed = vb.viewRange()
    vb.prepareForPaint()
    assert vb.viewRange() == zoomed


def test_an_empty_history_leaves_the_fit_harmless(qapp):
    # Nothing was plotted, so there is nothing to fit to; asking anyway must not
    # raise or leave the axes on a degenerate range.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history", _tpPayload(history=_tpHistory(count=0), transitions=[])
    )
    plot = widget.findChild(PlotWidget)

    (xLo, xHi), (yLo, yHi) = _viewRange(plot)
    assert xHi > xLo
    assert yHi > yLo


def test_a_live_plot_does_not_replot_on_a_mode_change(qapp):
    # The live path is unchanged: its next test pulse is what redraws it, and a
    # mode change must not re-read a history that is about to be superseded.
    import numpy as np

    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    history = _tpHistory()
    history["capacitance"] = np.linspace(1e-12, 50e-12, len(history))
    plot = PlotWidget(mode="ss resistance")
    plot.newTestPulse(None, history)
    before = _curveData(plot)

    plot.modeCombo.setText("capacitance")

    assert plot.mode == "capacitance"
    assert np.array_equal(_curveData(plot)[1], before[1])
