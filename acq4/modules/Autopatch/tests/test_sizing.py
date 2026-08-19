"""Tests for the sizing helpers the Autopatch panels floor their scrolling
views with, and for the label that wraps without growing without bound."""
import pytest

from acq4.util import Qt

from acq4.modules.Autopatch.sizing import CompactLabel, floorAtRows, rowsHigh


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _textRow(widget):
    metrics = widget.fontMetrics()
    return max(metrics.height(), metrics.lineSpacing())


def test_a_floor_of_more_rows_is_taller(qapp):
    view = Qt.QListWidget()

    assert rowsHigh(view, 3) > rowsHigh(view, 1)
    assert rowsHigh(view, 3) >= 3 * _textRow(view)


def test_an_empty_view_is_measured_by_its_font(qapp):
    """The case every panel actually calls this in: a floor is set at
    construction, when the queue has no cells in it and no row to measure."""
    empty = Qt.QListWidget()

    assert rowsHigh(empty, 3) >= 3 * _textRow(empty)


def test_a_view_whose_rows_measure_nothing_still_gets_readable_rows(qapp):
    """A pyqtgraph ParameterTree answers a pixel or two for the height of one
    of its rows -- a measurement of its own internal layout rather than of
    anything an operator reads -- and taken at its word it would floor Area 4's
    parameter tree at five pixels for three rows.
    """
    from pyqtgraph.parametertree import Parameter, ParameterTree

    tree = ParameterTree(showHeader=False)
    tree.setParameters(
        Parameter.create(
            name="protocol",
            type="group",
            children=[{"name": "depth", "type": "float", "value": 1.0}],
        ),
        showTop=False,
    )
    assert tree.sizeHintForRow(0) < _textRow(tree), "the case this is about is gone"

    assert rowsHigh(tree, 3) >= 3 * _textRow(tree)


def test_a_floored_view_can_be_squeezed_to_those_rows(qapp):
    """The point of the floor: a list whose own idea of a minimum is
    QAbstractScrollArea's seventy-pixel guess gives way to a few rows of its own
    text, and the layout holding it follows."""
    holder = Qt.QWidget()
    view = Qt.QListWidget()
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    holder.setLayout(layout)
    before = holder.minimumSizeHint().height()

    floorAtRows(view, 3)

    after = holder.minimumSizeHint().height()
    assert after < before
    assert 3 * _textRow(view) <= after <= 4 * _textRow(view)


def test_a_compact_label_stops_growing_after_a_few_rows(qapp):
    label = CompactLabel("a message far too long to fit on any one line " * 20, maxRows=3)

    assert label.wordWrap()
    assert label.sizeHint().height() <= rowsHigh(label, 3)


def test_a_compact_label_never_trades_width_for_height(qapp):
    """A wrapping label ordinarily answers "how tall are you?" with "how wide
    are you making me?", and the narrower it is squeezed the taller it gets --
    which is how squeezing a panel makes the panel bigger. Worse, Qt has no
    minimum height-for-width across a widget boundary, so a layout that catches
    it from one label reports a minimum height equal to its preferred height,
    and everything in that layout stops being able to give way at all.
    """
    holder = Qt.QWidget()
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    label = CompactLabel("a message far too long to fit on any one line " * 20)
    layout.addWidget(label)
    holder.setLayout(layout)

    assert not label.hasHeightForWidth()
    assert not layout.hasHeightForWidth()
    assert holder.minimumSizeHint().height() <= rowsHigh(label, 2)


def test_a_compact_label_never_decides_how_narrow_a_panel_can_be(qapp):
    label = CompactLabel("a message far too long to fit on any one line " * 20)

    assert label.minimumSizeHint().width() == 0
    assert label.minimumSizeHint().height() <= rowsHigh(label, 1)


def test_what_a_compact_label_clips_is_still_readable(qapp):
    """Nothing the cap cuts is lost, only moved somewhere that costs no
    height."""
    message = "ValueError: depth_range must run from the surface downwards " * 5
    label = CompactLabel()

    label.setText(message)

    assert label.toolTip() == message
    assert label.text() == message
