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
