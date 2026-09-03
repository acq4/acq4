"""Tests for the sizing helpers the Autopatch panels floor their scrolling
views with, and for the label that wraps without growing without bound."""
import pytest

from acq4.util import Qt

from acq4.modules.Autopatch.sizing import (
    CompactLabel,
    PinnedRowsList,
    floorAtRows,
    rowsHigh,
)


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
    # A fixed, modest font: the host's desktop theme (GTK/GNOME settings Qt
    # picks up even under the offscreen platform) can set a default font tall
    # enough that three rows of it alone exceeds QAbstractScrollArea's fixed
    # ~70px guess, which would make this comparison meaningless regardless of
    # what floorAtRows does.
    view.setFont(Qt.QFont("Sans Serif", 9))
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view)
    holder.setLayout(layout)
    before = holder.minimumSizeHint().height()

    floorAtRows(view, 3)

    after = holder.minimumSizeHint().height()
    assert after < before
    assert 3 * _textRow(view) <= after <= 4 * _textRow(view)


def test_a_fractional_row_count_lands_between_whole_rows(qapp):
    """Half a row is the affordance a pinned list is sized in: a row cut off at
    the bottom edge is what says there is more below it."""
    view = Qt.QListWidget()

    assert rowsHigh(view, 4) < rowsHigh(view, 4.5) < rowsHigh(view, 5)


def test_a_pinned_list_does_not_grow_with_its_contents(qapp):
    """The point of the pin: whatever arrives in the list, the panel around it
    stays where the operator left it."""
    holder = Qt.QWidget()
    view = PinnedRowsList(4.5)
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view, 0, Qt.Qt.AlignTop)
    holder.setLayout(layout)
    holder.resize(200, 600)
    holder.layout().activate()
    empty = view.height()

    for i in range(40):
        view.addItem(f"cell {i}")
    holder.layout().activate()

    assert view.height() == empty


def test_a_pinned_list_shows_four_and_a_half_of_its_own_rows(qapp):
    """Measured in the rows the list actually draws -- delegate, checkbox and
    all -- not in rows of the bare font, which is what it has to fall back on
    while it is still empty."""
    view = PinnedRowsList(4.5)
    for i in range(40):
        view.addItem(f"cell {i}")
    view.resize(200, view.sizeHint().height())

    row = view.sizeHintForRow(0)
    assert 4 * row < view.height() < 5 * row, (view.height(), row)


def test_a_pinned_list_measures_the_rows_it_actually_draws(qapp):
    """A drawn row is taller than a line of text under plenty of conditions --
    an icon, a checkbox, a high-DPI desktop, a rig's own stylesheet -- and a
    view pinned to the font's idea of a row shows four and a half rows on this
    desktop and three and a bit on that one.

    The catch is that a list is asked what a row measures long before it has
    one: a panel builds its views while the queue is empty, and rowsHigh has
    nothing to fall back on but the font. Nothing about a row arriving makes a
    QListWidget tell the layout above it to ask again, so a pin left to that
    latches at the empty guess and never corrects.
    """
    holder = Qt.QWidget()
    view = PinnedRowsList(4.5)
    view.setStyleSheet("QListView::item { min-height: 34px; }")
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view, 0, Qt.Qt.AlignTop)
    holder.setLayout(layout)
    holder.resize(300, 600)
    # Shown, because a scroll area lays its viewport out in its resize event:
    # measuring the viewport of a list nobody ever showed reads back whatever
    # size it was born with.
    holder.show()
    try:
        qapp.processEvents()

        for i in range(10):
            view.addItem(f"cell {i}")
        qapp.processEvents()

        row = view.sizeHintForRow(0)
        assert row > _textRow(view), "the case this is about is gone"
        assert 4 * row < view.viewport().height() < 5 * row, (
            view.viewport().height(),
            row,
        )
    finally:
        holder.close()


def test_a_pinned_list_settles_once_and_stays_there(qapp):
    """The correction the test above asks for happens when the first rows
    arrive, and never again: a queue that re-measured itself as it filled would
    be the moving target the pin exists to stop."""
    holder = Qt.QWidget()
    view = PinnedRowsList(4.5)
    view.setStyleSheet("QListView::item { min-height: 34px; }")
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(view, 0, Qt.Qt.AlignTop)
    holder.setLayout(layout)
    holder.resize(300, 600)
    holder.show()
    try:
        view.addItem("cell 0")
        qapp.processEvents()
        settled = view.height()

        for i in range(40):
            view.addItem(f"cell {i + 1}")
        qapp.processEvents()

        assert view.height() == settled
    finally:
        holder.close()


def test_a_pinned_list_is_the_only_height_a_layout_will_give_it(qapp):
    """Pinned in both directions: a layout with room to spare may not stretch
    it, and one short of room may not squeeze it either -- that shortfall comes
    out of the views around it, which scroll."""
    view = PinnedRowsList(4.5)

    assert view.sizeHint().height() == rowsHigh(view, 4.5)
    assert view.minimumSizeHint().height() == rowsHigh(view, 4.5)
    assert view.sizePolicy().verticalPolicy() == Qt.QSizePolicy.Fixed


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
