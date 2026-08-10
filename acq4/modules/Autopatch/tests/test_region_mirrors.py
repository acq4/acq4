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


def makeFrameItem(value, x, y):
    # Asymmetric image on purpose: a transposed copy of a square array is
    # indistinguishable from the original.
    item = pg.ImageItem(np.full((4, 7), value, dtype=float))
    transform = Qt.QTransform()
    transform.translate(x, y)
    transform.scale(1e-6, 2e-6)
    item.setTransform(transform)
    return item


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

    source.unpin(item)

    assert mirror.items == []


def test_the_mirrored_item_carries_the_same_pixels_and_placement(qapp):
    # A mirror that showed the right image in the wrong place would have the
    # operator draw regions over tissue that is somewhere else.
    source = FakeImagingCtrl()
    original = makeFrameItem(3.0, 1e-3, 2e-3)
    source.pin(original)
    mirror, _view = makeMirror()
    mirror.bind(source)

    copy = mirror.items[0]
    assert np.array_equal(copy.image, original.image)
    assert copy.transform() == original.transform()
    assert copy.zValue() == original.zValue()


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
