"""Tests for Area 1's progress overlay: what it draws into the region view,
and what it reports when the operator clicks a cell marker."""

import pyqtgraph as pg
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


# Asymmetric and in metres throughout: a square fixture cannot catch a swapped
# x/y, and a unit-scale one cannot catch a metres/millimetres mixup.
FOV = (220e-6, 170e-6)
POS_A = (1.0e-3, 2.0e-3)
POS_B = (1.4e-3, 2.1e-3)


def makeOverlay():
    from acq4.modules.Autopatch.progress_overlay import ProgressOverlay

    view = pg.ViewBox()
    return ProgressOverlay(view), view


def test_markers_are_drawn_at_their_positions(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()

    overlay.setMarkers([
        Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111),
        Marker(POS_B[0], POS_B[1], pg.mkBrush(220, 40, 40), 222),
    ])

    spots = overlay.scatter.getData()
    assert list(spots[0]) == [POS_A[0], POS_B[0]]
    assert list(spots[1]) == [POS_A[1], POS_B[1]]


def test_setting_markers_replaces_rather_than_appends(qapp):
    """A refresh redraws the whole set, so the second call must not stack."""
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])

    overlay.setMarkers([Marker(POS_B[0], POS_B[1], pg.mkBrush(220, 40, 40), 222)])

    assert len(overlay.scatter.getData()[0]) == 1


def test_marker_carries_its_cell_id_not_the_cell(qapp):
    """Point data holds an id so the scatter never keeps a Cell alive."""
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])

    assert overlay.scatter.points()[0].data() == 111


def test_coverage_draws_one_rect_per_todo_tile(qapp):
    overlay, _view = makeOverlay()

    overlay.setCoverage([POS_A, POS_B], FOV)

    assert len(overlay.coverageItems()) == 2


def test_coverage_rect_spans_one_field_around_the_tile_centre(qapp):
    overlay, _view = makeOverlay()

    overlay.setCoverage([POS_A], FOV)

    rect = overlay.coverageItems()[0].rect()
    assert rect.width() == pytest.approx(FOV[0])
    assert rect.height() == pytest.approx(FOV[1])
    assert rect.center().x() == pytest.approx(POS_A[0])
    assert rect.center().y() == pytest.approx(POS_A[1])


def test_clear_removes_markers_and_coverage(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    overlay.setCoverage([POS_A], FOV)

    overlay.clear()

    assert len(overlay.scatter.getData()[0]) == 0
    assert overlay.coverageItems() == []


def test_release_takes_every_item_out_of_the_view(qapp):
    """The view outlives the overlay, so release must leave nothing behind.

    The coverage items are captured *before* release, because release empties
    the list they are read from: iterating the emptied list afterwards proves
    nothing, and would pass for an implementation that dropped its references
    without ever taking the items out of the view.
    """
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    overlay.setCoverage([POS_A], FOV)
    coverage = overlay.coverageItems()
    assert coverage, "fixture must actually put coverage items in the view"

    overlay.release()

    assert overlay.scatter not in view.addedItems
    assert not any(item in view.addedItems for item in coverage)


def test_clicking_a_marker_reports_its_cell_id(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    seen = []
    overlay.sigMarkerClicked.connect(seen.append)

    overlay.scatter.sigClicked.emit(overlay.scatter, [overlay.scatter.points()[0]], None)

    assert seen == [111]
