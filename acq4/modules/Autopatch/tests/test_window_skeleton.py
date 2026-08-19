"""Tests that AutopatchWindow constructs and exposes the five design-doc areas
as labeled group boxes the operator can resize freely against each other."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    """A QApplication is required to instantiate any QWidget."""
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeDeviceSelector(Qt.QWidget):
    """Stands in for InterfaceCombo so these skeleton tests never trigger its
    internal getManager() call."""

    def getSelectedObj(self):
        return None


def _makeWindow(tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    return AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )


def test_window_constructs_with_five_area_boxes(qapp, tmp_path):
    win = _makeWindow(tmp_path)

    assert isinstance(win.area1Box, Qt.QGroupBox)
    assert isinstance(win.area2Box, Qt.QGroupBox)
    assert isinstance(win.area3Box, Qt.QGroupBox)
    assert isinstance(win.area4Box, Qt.QGroupBox)
    assert isinstance(win.area5Box, Qt.QGroupBox)


def test_area_titles_name_their_design_doc_role(qapp, tmp_path):
    win = _makeWindow(tmp_path)

    assert "slice" in win.area1Box.title().lower()
    assert "cell" in win.area2Box.title().lower() and "find" in win.area2Box.title().lower()
    assert "status" in win.area3Box.title().lower() or "action" in win.area3Box.title().lower()
    assert "protocol" in win.area4Box.title().lower()
    assert "cell" in win.area5Box.title().lower()


def test_area_titles_name_their_content_not_their_internal_number(qapp, tmp_path):
    """"Area 3" is how this module's code and design doc refer to the
    status/actions box; it tells an operator nothing about what is in it. The
    titles they read name the content alone."""
    win = _makeWindow(tmp_path)

    for box in (win.area1Box, win.area2Box, win.area3Box, win.area4Box, win.area5Box):
        title = box.title()
        assert "area" not in title.lower(), title
        assert not any(ch.isdigit() for ch in title), title


def test_window_has_a_title(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    assert win.windowTitle() == "Autopatch"


def test_default_pipette_selector_is_built_for_the_patchpipette_interface(qapp, tmp_path, monkeypatch):
    """The device actions (Cellfie/GoApproach/Patch/Focus*/etc.) are written
    against a PatchPipette (interface "patchpipette"), not the bare
    manipulator (interface "pipette") -- so the default pipette selector
    (built when the caller doesn't inject one) must resolve the
    "patchpipette" interface."""
    import importlib

    # NOT `import acq4.modules.Autopatch.Autopatch as autopatch_module`: the
    # package's __init__.py does `from .Autopatch import Autopatch`, which
    # shadows the submodule's own name in the package namespace with the
    # class, so that dotted-attribute path resolves to the class instead of
    # the module. importlib.import_module bypasses that by returning the
    # module straight from sys.modules.
    autopatch_module = importlib.import_module("acq4.modules.Autopatch.Autopatch")

    captured = {}

    class _SpyInterfaceCombo(Qt.QWidget):
        def __init__(self, types=None):
            super().__init__()
            captured["types"] = types

        def getSelectedObj(self):
            return None

    monkeypatch.setattr(autopatch_module, "InterfaceCombo", _SpyInterfaceCombo)

    autopatch_module.AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        cameraSelector=_FakeDeviceSelector(),
    )

    assert captured["types"] == ["patchpipette"]


def test_areas_are_arranged_in_two_columns_of_splitters(qapp, tmp_path):
    """Left column (top->bottom): Area 1, Area 2. Right column (top->bottom):
    Area 3, Area 4, Area 5.

    Every boundary between areas is a splitter handle -- the one between the
    columns and the ones between the areas stacked inside each column -- so the
    operator, not this constructor, decides how the window is divided.
    """
    win = _makeWindow(tmp_path)

    outer = win.layout()
    assert isinstance(outer, Qt.QHBoxLayout)
    assert outer.count() == 1

    columns = outer.itemAt(0).widget()
    assert isinstance(columns, Qt.QSplitter)
    assert columns.orientation() == Qt.Qt.Horizontal
    assert columns.count() == 2

    leftCol, rightCol = columns.widget(0), columns.widget(1)
    assert isinstance(leftCol, Qt.QSplitter)
    assert isinstance(rightCol, Qt.QSplitter)
    assert leftCol.orientation() == Qt.Qt.Vertical
    assert rightCol.orientation() == Qt.Qt.Vertical

    assert [leftCol.widget(i) for i in range(leftCol.count())] == [
        win.area1Box,
        win.area2Box,
    ]
    assert [rightCol.widget(i) for i in range(rightCol.count())] == [
        win.area3Box,
        win.area4Box,
        win.area5Box,
    ]


def _areaViewport(box):
    """The scrolling viewport an area holds its panel in.

    Not every QScrollArea under the box: Area 5 mounts each action's details
    widget in a scroll area of its own (see cell_panel._DetailsViewport), and
    that one is the panel's own business rather than the area's. The area's is
    the one the group box holds directly.
    """
    scrolls = [s for s in box.findChildren(Qt.QScrollArea) if s.parent() is box]
    assert len(scrolls) == 1, (box.title(), scrolls)
    return scrolls[0]


def test_each_area_holds_its_content_in_a_scroll_area(qapp, tmp_path):
    """The panels live inside scrolling viewports, which is what lets an area be
    given less room than its content wants: the content scrolls instead of
    refusing to shrink."""
    win = _makeWindow(tmp_path)

    for box, panel in (
        (win.area1Box, win.regionPanel),
        (win.area2Box, win.searchPanel),
        (win.area3Box, win.statusPanel),
        (win.area4Box, win.protocolPanel),
        (win.area5Box, win.cellPanel),
    ):
        scroll = _areaViewport(box)
        assert scroll.widgetResizable(), box.title()
        assert scroll.isAncestorOf(panel), box.title()


def test_an_area_can_be_squeezed_below_what_its_content_asks_for(qapp, tmp_path):
    """A QSplitter will not drag a child below its minimumSizeHint, so an area
    that inherits its panel's hint -- Area 1's slice view alone asks for a
    square of a few hundred pixels, Area 5's button row plus two lists plus a
    log for far more -- would refuse the size the operator chose. Wrapped, each
    area's hint is a viewport's, and the handle keeps moving."""
    win = _makeWindow(tmp_path)

    for box in (win.area1Box, win.area2Box, win.area3Box, win.area4Box, win.area5Box):
        hint = box.minimumSizeHint()
        assert hint.height() <= 100, (box.title(), hint.height())
        assert hint.width() <= 250, (box.title(), hint.width())


def test_the_operator_chosen_split_is_what_the_areas_actually_get(qapp, tmp_path):
    """The end-to-end version of the check above, driven through the splitters
    the operator drags: sizes asked for are sizes honoured, not clamped back up
    to what the content inside would prefer."""
    win = _makeWindow(tmp_path)
    win.resize(900, 700)
    win.show()
    try:
        qapp.processEvents()
        columns = win.layout().itemAt(0).widget()
        leftCol, rightCol = columns.widget(0), columns.widget(1)

        # A narrow left column and a right column dominated by one area: both
        # squeeze several panels well under their natural size.
        columns.setSizes([200, 700])
        leftCol.setSizes([500, 100])
        rightCol.setSizes([60, 60, 500])
        qapp.processEvents()

        assert win.area1Box.width() <= 220
        assert win.area2Box.height() <= 150
        assert win.area3Box.height() <= 110
        assert win.area4Box.height() <= 110
    finally:
        win.close()


def test_an_area_asks_for_room_enough_for_the_content_it_holds(qapp, tmp_path):
    """The other half of squeezing: the wrapping must not shrink what an area
    asks for before the operator has touched a handle.

    QScrollArea computes its sizeHint from the widget it was handed and then
    caches it forever -- a cache only setWidget() clears -- and this window hands
    those widgets over empty and fills them afterwards. Left to that cache every
    area's hint is the empty one, which opens the whole window a couple of
    hundred pixels across with all five areas already scrolled.
    """
    win = _makeWindow(tmp_path)

    for box, panel in (
        (win.area1Box, win.regionPanel),
        (win.area2Box, win.searchPanel),
        (win.area3Box, win.statusPanel),
        (win.area4Box, win.protocolPanel),
        (win.area5Box, win.cellPanel),
    ):
        hint, wanted = box.sizeHint(), panel.sizeHint()
        assert hint.width() >= wanted.width(), (box.title(), hint, wanted)
        assert hint.height() >= wanted.height(), (box.title(), hint, wanted)


def test_the_window_opens_with_each_column_wide_enough_for_its_content(qapp, tmp_path):
    """The opening arrangement is seeded from what the areas ask for, not from
    the stretch factors alone: those describe how *extra* room is shared as the
    window grows, and a bare 2:1 of a window that is only just big enough hands
    the left column room the right column needed -- so an operator's first sight
    of the window is Area 5's buttons behind a horizontal scrollbar, with the
    slice view sitting on space it was not asking for.
    """
    win = _makeWindow(tmp_path)
    wanted = [win.leftColumn.sizeHint().width(), win.rightColumn.sizeHint().width()]
    # Comfortably more than both columns together, so nothing here is about what
    # gives when there genuinely is not enough room.
    win.resize(sum(wanted) + 200, 800)
    win.show()
    try:
        qapp.processEvents()
        for got, asked in zip(win.columnSplitter.sizes(), wanted):
            assert got >= asked, (win.columnSplitter.sizes(), wanted)
    finally:
        win.close()


# ---- how small the panels are willing to get ----
#
# The areas themselves already give way (see the two tests above): each one's
# content sits in a viewport that insists on nothing, so the handles move
# wherever they are dragged. What is checked here is one level in -- whether the
# panel *inside* that viewport gives way too. A panel that insists on its full
# height turns every squeeze into scrollbars: the operator drags Area 5 up to
# see more of the slice and gets a scrolled panel with the cell queue off the
# bottom, rather than a shorter queue. Everything scrollable in these panels --
# the two lists, the log, the parameter tree, the details pane -- can show a few
# rows and scroll the rest within itself instead.


def _rowsHigh(widget, rows):
    """The height `rows` rows of that widget's own text occupy."""
    return rows * widget.fontMetrics().height()


def _panelFloor(panel):
    """What any one panel may insist on: a dozen rows of its own text, plus a
    row of controls, which is not text and does not shrink.

    Generous on purpose -- this is a ceiling on a minimum, not a target -- but
    small enough that an area squeezed to it still shows something of every
    panel: Area 1's view above its controls, three or four rows of Area 5's
    cell queue, the top of Area 4's parameter tree.
    """
    return Qt.QPushButton("x").sizeHint().height() + _rowsHigh(panel, 12)


def _panels(win):
    return (win.regionPanel, win.searchPanel, win.statusPanel, win.protocolPanel, win.cellPanel)


def test_every_panel_can_be_squeezed_to_a_few_rows(qapp, tmp_path):
    win = _makeWindow(tmp_path)

    for panel in _panels(win):
        floor = _panelFloor(panel)
        assert panel.minimumSizeHint().height() <= floor, (
            type(panel).__name__,
            panel.minimumSizeHint().height(),
            floor,
        )


def test_every_panel_still_prefers_more_room_than_it_insists_on(qapp, tmp_path):
    """The other half of the same property: a smaller minimum, not a smaller
    preference. _seedOpeningSplit divides each splitter in proportion to what
    the areas ask for, so a panel that let its sizeHint collapse onto its
    minimum would be handed a sliver of the window it opens in.
    """
    win = _makeWindow(tmp_path)

    for panel in _panels(win):
        assert panel.sizeHint().height() >= panel.minimumSizeHint().height(), (
            type(panel).__name__,
            panel.sizeHint().height(),
            panel.minimumSizeHint().height(),
        )


def test_squeezing_an_area_compacts_its_panel_rather_than_scrolling_it(qapp, tmp_path):
    """End to end, through the handle the operator actually drags, and with
    Area 5 carrying what it carries mid-run: a queue of cells, a wrapped status
    message, and a details widget of the size an ImageView or a test-pulse plot
    asks for. Given room enough for the floor above, the panel is expected to
    fit it -- its own lists and log scrolling within themselves -- rather than
    overflow the viewport and be scrolled bodily, which is what puts the buttons
    and the queue off the top of the area the operator just made room with.
    """
    win = _makeWindow(tmp_path)
    for _ in range(25):
        win.cellPanel.addCell(object())
    win.cellPanel.statusLabel.setText("waiting for the pipette to reach the cell " * 6)
    insistent = Qt.QWidget()
    insistent.setMinimumSize(400, 400)
    win.cellPanel.showContainer.layout().addWidget(insistent)
    win.resize(1000, 900)
    win.show()
    try:
        qapp.processEvents()
        # Sizes that add up to the room the column actually has, since a
        # QSplitter rescales anything else: Area 5 squeezed to the floor above
        # plus the group box's own chrome, and the rest shared between 3 and 4.
        area5 = _panelFloor(win.cellPanel) + 60
        rest = (win.rightColumn.height() - area5) // 2
        win.rightColumn.setSizes([rest, rest, area5])
        # Several passes of the loop: mounting a widget reaches the details pane
        # in one and the panel's own layout in the next.
        for _ in range(3):
            qapp.processEvents()

        scroll = _areaViewport(win.area5Box)
        assert win.cellPanel.height() <= scroll.viewport().height(), (
            win.cellPanel.height(),
            scroll.viewport().height(),
        )
        assert not scroll.verticalScrollBar().isVisible()
        # And what fits is still worth reading: rows of the queue, and the
        # buttons above it.
        assert win.cellPanel.cellList.height() >= _rowsHigh(win.cellPanel.cellList, 3)
        assert win.cellPanel.addFromTargetBtn.isVisible()
    finally:
        win.close()
