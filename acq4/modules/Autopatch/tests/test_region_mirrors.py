"""Tests for Area 1's two one-way mirrors: the Camera module's pinned frames
coming in, and region outlines going out."""

import gc
import weakref

import numpy as np
import pyqtgraph as pg
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class FakeImagingCtrl(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl: a list of pinned image
    items and the signal that says it changed."""

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self):
        super().__init__()
        self.pinnedFrames = []

    def pin(self, item):
        item.setZValue(-10000 + len(self.pinnedFrames))
        self.pinnedFrames.append(item)
        self.sigPinnedFramesChanged.emit()

    def unpin(self, item):
        self.pinnedFrames.remove(item)
        self.sigPinnedFramesChanged.emit()


def makeFrameItem(value, x, y, levels=None, lut=None):
    # Asymmetric image on purpose: a transposed copy of a square array is
    # indistinguishable from the original.
    item = pg.ImageItem(np.full((4, 7), value, dtype=float), levels=levels, lut=lut)
    transform = Qt.QTransform()
    transform.translate(x, y)
    transform.scale(1e-6, 2e-6)
    item.setTransform(transform)
    return item


def makeLut():
    """A lookup table like the one ImagingCtrl.pinCurrentFrame takes off the
    contrast histogram."""
    return np.repeat(np.arange(256, dtype=np.ubyte)[:, np.newaxis], 3, axis=1)


def makeMirror():
    from acq4.modules.Autopatch.region_mirrors import PinnedFrameMirror

    view = pg.ViewBox()
    return PinnedFrameMirror(view), view


def test_binding_shows_the_frames_already_pinned(qapp):
    # The operator pins frames before opening Autopatch as often as after.
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))
    mirror, _view = makeMirror()

    mirror.bind(source)

    assert len(mirror.items) == 1


def test_a_frame_pinned_later_appears(qapp):
    source = FakeImagingCtrl()
    mirror, _view = makeMirror()
    mirror.bind(source)

    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))

    assert len(mirror.items) == 1


def test_a_frame_unpinned_disappears(qapp):
    source = FakeImagingCtrl()
    item = makeFrameItem(1.0, 1e-3, 2e-3)
    source.pin(item)
    mirror, _view = makeMirror()
    mirror.bind(source)
    assert len(mirror.items) == 1

    source.unpin(item)

    assert mirror.items == []


def test_the_mirrored_item_carries_the_same_pixels_and_placement(qapp):
    # A mirror that showed the right image in the wrong place would have the
    # operator draw regions over tissue that is somewhere else.
    #
    # Levels and lut are part of the placement problem, not a cosmetic
    # preference: a real pinned frame is built with both spelled out
    # (ImagingCtrl.pinCurrentFrame, Frame.imageItem), and an item given neither
    # scales itself to its own contents. Every mirrored frame in a mosaic would
    # then get its own independent auto-scale, and a 16-bit frame with a narrow
    # range renders near-flat -- which is not a backdrop anyone can draw on.
    lut = makeLut()
    source = FakeImagingCtrl()
    original = makeFrameItem(3.0, 1e-3, 2e-3, levels=(1.0, 9.0), lut=lut)
    source.pin(original)
    mirror, _view = makeMirror()
    mirror.bind(source)

    copy = mirror.items[0]
    assert np.array_equal(copy.image, original.image)
    assert copy.transform() == original.transform()
    assert copy.zValue() == original.zValue()
    assert np.array_equal(copy.getLevels(), original.getLevels())
    assert np.array_equal(copy.lut, lut)


def test_a_frame_with_no_levels_or_lut_is_mirrored_anyway(qapp):
    # Both are optional on the way in -- Frame.imageItem passes None for each
    # when a frame carries no contrast info -- so copying them must not turn an
    # absent one into a failure.
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(3.0, 1e-3, 2e-3))
    mirror, _view = makeMirror()

    mirror.bind(source)

    assert len(mirror.items) == 1
    assert mirror.items[0].lut is None


def test_the_mirrored_item_is_a_distinct_object_in_this_view(qapp):
    # An ImageItem lives in exactly one scene, so re-adding the Camera module's
    # own item would take it out of the Camera module's view.
    source = FakeImagingCtrl()
    original = makeFrameItem(3.0, 1e-3, 2e-3)
    source.pin(original)
    mirror, view = makeMirror()
    mirror.bind(source)

    assert mirror.items[0] is not original
    assert mirror.items[0] in view.addedItems


def test_unbinding_clears_the_view_and_stops_listening(qapp):
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))
    mirror, _view = makeMirror()
    mirror.bind(source)
    assert len(mirror.items) == 1

    mirror.unbind()
    source.pin(makeFrameItem(2.0, 3e-3, 4e-3))

    assert mirror.items == []


def test_unbinding_releases_the_source(qapp):
    # A connection outliving its owner is this module's most-repeated defect:
    # a mirror still listening after teardown draws into a dead view.
    source = FakeImagingCtrl()
    mirror, _view = makeMirror()
    mirror.bind(source)
    ref = weakref.ref(source)

    mirror.unbind()
    del source
    gc.disable()
    try:
        assert ref() is None
    finally:
        gc.enable()


def test_unbinding_disconnects_from_the_source_signal(qapp):
    # test_unbinding_releases_the_source only proves the last Python
    # reference to the source is dropped, which follows from `self._source =
    # None` alone regardless of whether the Qt connection was severed. This
    # test instead inspects the connection itself: a long-lived source (the
    # real Camera module's ImagingCtrl) would otherwise keep calling a
    # torn-down mirror's refresh() forever.
    source = FakeImagingCtrl()
    mirror, _view = makeMirror()
    mirror.bind(source)
    assert source.receivers(source.sigPinnedFramesChanged) == 1

    mirror.unbind()

    assert source.receivers(source.sigPinnedFramesChanged) == 0


class DeletedImagingCtrl:
    """A source whose underlying C++ object Qt has already destroyed.

    The Python wrapper outlives it and raises RuntimeError on every attribute
    reached through it -- including the signal, which is why pg.disconnect
    swallowing RuntimeError is not enough on its own: the signal has to be read
    before it can be handed to pg.disconnect at all.

    Written as a stand-in rather than by actually deleting a QObject so the test
    says which behaviour it depends on, and does not depend on which Qt binding
    acq4 was imported with.
    """

    @property
    def sigPinnedFramesChanged(self):
        raise RuntimeError("wrapped C/C++ object of type ImagingCtrl has been deleted")


def test_unbinding_survives_a_source_whose_c_object_is_gone(qapp):
    # unbind() is the first thing AutopatchWindow.teardown() reaches for, so a
    # raise here would leave the orchestrator running and every panel still
    # wired to it. An application shutdown that destroys the Camera module
    # before Autopatch is an ordinary way to arrive here.
    mirror, _view = makeMirror()
    mirror._source = DeletedImagingCtrl()

    mirror.unbind()

    assert mirror._source is None
    assert mirror.items == []


def test_pinning_three_frames_preserves_their_relative_z_order(qapp):
    # Pinned frames stack, and which one is on top is the operator's record of
    # what they imaged last. A single-frame test already catches an absolute
    # z-value being clobbered; what needs three is the relative order surviving
    # -- a mirror that rebuilt its items in the wrong sequence would give every
    # one of them a plausible z and still stack the mosaic wrongly.
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))
    source.pin(makeFrameItem(2.0, 3e-3, 4e-3))
    source.pin(makeFrameItem(3.0, 5e-3, 6e-3))
    mirror, _view = makeMirror()

    mirror.bind(source)

    assert [item.zValue() for item in mirror.items] == [-10000, -9999, -9998]


from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion

RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
ELLIPSE = EllipseRegion(3.0e-3, 1.0e-3, 3.6e-3, 1.2e-3)
TRIANGLE = PolygonRegion(((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3)))


class FakeCameraWindow:
    """Stands in for the Camera module's window: the addItem/removeItem pair
    Autopatch reaches it through."""

    def __init__(self):
        self.items = []

    def addItem(self, item, pos=(0, 0), scale=(1, 1), z=None, **kwds):
        self.items.append(item)
        if z is not None:
            item.setZValue(z)

    def removeItem(self, item):
        self.items.remove(item)


def makeCameraMirror(window):
    from acq4.modules.Autopatch.region_mirrors import CameraMirror

    return CameraMirror(lambda: window)


def test_disabled_by_default_nothing_reaches_the_camera(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)

    mirror.setRegions([RECT, ELLIPSE])

    assert window.items == []


def test_enabling_draws_the_regions_already_set(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setRegions([RECT, ELLIPSE])

    mirror.setEnabled(True)

    assert len(window.items) == 2


def test_regions_set_while_enabled_are_drawn(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)

    mirror.setRegions([RECT, ELLIPSE, TRIANGLE])

    assert len(window.items) == 3


def test_disabling_takes_them_out_again(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    mirror.setEnabled(False)

    assert window.items == []


def test_the_outlines_cannot_be_grabbed(qapp):
    # Autopatch is the only place a region is edited. A mirrored outline that
    # accepted a mouse press would be a second, silent editing surface.
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    assert window.items[0].acceptedMouseButtons() == Qt.Qt.NoButton


@pytest.mark.parametrize(
    "region,expected",
    [(RECT, (1.0e-3, 2.0e-3, 0.4e-3, 0.1e-3)), (ELLIPSE, (3.0e-3, 1.0e-3, 0.6e-3, 0.2e-3))],
)
def test_an_outline_lands_on_its_regions_bounds(qapp, region, expected):
    # Asymmetric bounds on both shapes: a square outline cannot catch a width
    # and height that have been swapped.
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([region])

    rect = window.items[0].path().boundingRect()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == pytest.approx(expected)


def test_a_polygon_outline_has_a_vertex_per_vertex(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([TRIANGLE])

    path = window.items[0].path()
    drawn = {(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())}
    for vertex in TRIANGLE.vertices:
        assert any(
            abs(x - vertex[0]) < 1e-12 and abs(y - vertex[1]) < 1e-12 for x, y in drawn
        )


def test_the_outline_keeps_its_assigned_z_value(qapp):
    # What this pins is that CameraMirror hands its z to the window rather than
    # setting it itself: the fake records whatever it is passed. It cannot show
    # the z surviving pg.ViewBox.addItem()'s raise-if-lower rule, which is real
    # but lives in CameraWindow.addItem() -- that calls view.addItem() first and
    # applies the given z after, so the order is already right on the real path.
    from acq4.modules.Autopatch.region_mirrors import _MIRROR_Z

    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    assert window.items[0].zValue() == _MIRROR_Z


def test_no_camera_window_is_not_an_error(qapp):
    # A rig with the Camera module unloaded is ordinary; the checkbox is a
    # display preference, not a requirement.
    from acq4.modules.Autopatch.region_mirrors import CameraMirror

    mirror = CameraMirror(lambda: None)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    assert mirror.items == []


def test_clear_removes_everything_it_put_there(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT, ELLIPSE])

    mirror.clear()

    assert window.items == []
    assert mirror.items == []
