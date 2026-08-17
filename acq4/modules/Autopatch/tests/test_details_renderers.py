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
        "sweep_count": 3,
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
            "sweep_count": 1,
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
            "sweep_count": 1,
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
            "sweep_count": 0,
            "decimation": 1,
            "units": "A",
        },
    )

    assert wrapper is not None
