"""The exposure heat map: the image it builds over the regions, when it is shown
and refreshed, and where it sits among the region view's other layers."""

import numpy as np
import pyqtgraph as pg
import pytest

from acq4.experiment.search_region import RectRegion
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


REGION = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.2e-3)
FOV = (100e-6, 80e-6)
NOW = 1000.0
SIGMA = 50e-6
TAU = 300.0
INSERTION = (1.2e-3, 2.1e-3, NOW - 1.0)


class Source:
    """What the window would hand the overlay, with a clock the test can move."""

    def __init__(self, insertions=(INSERTION,)):
        self.insertions = insertions
        self.now = NOW

    def __call__(self):
        return [REGION], FOV, self.insertions, SIGMA, TAU


def makeOverlay(source=None):
    from acq4.modules.Autopatch.exposure_overlay import ExposureOverlay

    view = pg.ViewBox()
    source = source or Source()
    return ExposureOverlay(view, source, clock=lambda: source.now), view, source


def test_it_is_hidden_by_default_and_its_timer_is_stopped(qapp):
    overlay, _view, _ = makeOverlay()
    assert not overlay.item.isVisible()
    assert not overlay.isShown()
    assert not overlay.timerActive()


def test_the_timer_runs_only_while_shown(qapp):
    overlay, _view, _ = makeOverlay()

    overlay.setShown(True)
    assert overlay.timerActive()
    assert overlay.timerIntervalMs() == 10_000

    overlay.setShown(False)
    assert not overlay.timerActive()
    assert not overlay.item.isVisible()


def test_the_image_covers_the_regions_padded_by_half_a_field(qapp):
    overlay, _view, _ = makeOverlay()
    overlay.setShown(True)

    rect = overlay.item.mapRectToParent(overlay.item.boundingRect())
    assert rect.left() == pytest.approx(1.0e-3 - FOV[0] / 2)
    assert rect.right() == pytest.approx(1.4e-3 + FOV[0] / 2)
    assert rect.top() == pytest.approx(2.0e-3 - FOV[1] / 2)
    assert rect.bottom() == pytest.approx(2.2e-3 + FOV[1] / 2)
    nx = round((0.4e-3 + FOV[0]) / 10e-6)
    ny = round((0.2e-3 + FOV[1]) / 10e-6)
    assert overlay.item.image.shape == (nx, ny)


def test_the_peak_is_at_the_insertion(qapp):
    overlay, _view, _ = makeOverlay()
    overlay.setShown(True)

    image = overlay.item.image
    ix, iy = np.unravel_index(np.argmax(image), image.shape)
    x0 = 1.0e-3 - FOV[0] / 2
    y0 = 2.0e-3 - FOV[1] / 2
    assert x0 + (ix + 0.5) * 10e-6 == pytest.approx(INSERTION[0], abs=10e-6)
    assert y0 + (iy + 0.5) * 10e-6 == pytest.approx(INSERTION[1], abs=10e-6)
    assert image.max() == pytest.approx(1.0, abs=0.05)


def test_refresh_follows_the_clock(qapp):
    overlay, _view, source = makeOverlay()
    overlay.setShown(True)
    fresh = overlay.item.image.max()

    source.now = NOW + TAU
    overlay.refresh()

    assert overlay.item.image.max() == pytest.approx(fresh * np.exp(-1.0), rel=0.05)


def test_refresh_picks_up_a_new_insertion(qapp):
    overlay, _view, source = makeOverlay(Source(insertions=()))
    overlay.setShown(True)
    assert overlay.item.image.max() == 0.0

    source.insertions = (INSERTION,)
    overlay.refresh()

    assert overlay.item.image.max() > 0.9


def test_a_hidden_overlay_does_not_render(qapp):
    overlay, _view, _ = makeOverlay()
    overlay.refresh()
    assert overlay.item.image is None


def test_no_source_data_leaves_nothing_drawn(qapp):
    from acq4.modules.Autopatch.exposure_overlay import ExposureOverlay

    overlay = ExposureOverlay(pg.ViewBox(), lambda: None)
    overlay.setShown(True)
    assert overlay.item.image is None


def test_it_sits_under_the_coverage_shading(qapp):
    from acq4.modules.Autopatch.progress_overlay import _COVERAGE_Z

    overlay, view, _ = makeOverlay()
    assert overlay.item.zValue() == -55
    assert overlay.item.zValue() < _COVERAGE_Z
    assert overlay.item in view.addedItems


def test_release_takes_the_item_out_and_stops_the_timer(qapp):
    overlay, view, _ = makeOverlay()
    overlay.setShown(True)

    overlay.release()

    assert overlay.item not in view.addedItems
    assert not overlay.timerActive()
