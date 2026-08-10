"""The two one-way mirrors either side of Area 1's view: the Camera module's
pinned frames coming in, and read-only region outlines going out."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.util import Qt


class PinnedFrameMirror:
    """Shows the Camera module's pinned frames in another view.

    A pg.ImageItem belongs to exactly one QGraphicsScene, so displaying the
    pinned frames in both places cannot mean showing the same objects twice --
    adding the Camera module's own items here would take them out of the Camera
    module's view. This builds its own item per pinned frame instead, from the
    same image array and the same global transform.

    Display only: it holds no region state and nothing depends on it existing.
    """

    def __init__(self, view):
        self._view = view
        self._source = None
        self.items: list[pg.ImageItem] = []

    def bind(self, imagingCtrl) -> None:
        """Mirror `imagingCtrl`'s pinned frames, replacing any current binding.

        Draws what is already pinned rather than waiting for the next change:
        pinning frames before opening this window is as ordinary as after.
        """
        self.unbind()
        self._source = imagingCtrl
        imagingCtrl.sigPinnedFramesChanged.connect(self.refresh)
        self.refresh()

    def unbind(self) -> None:
        """Stop mirroring and take the copies out of the view."""
        if self._source is not None:
            Qt.disconnect(self._source.sigPinnedFramesChanged, self.refresh)
            self._source = None
        self._clearItems()

    def refresh(self) -> None:
        """Rebuild the mirrored items from the source's current set.

        Rebuilding wholesale rather than diffing: the set is a handful of frames
        changed by operator clicks, and a diff would be state to keep correct
        for no measurable gain.
        """
        self._clearItems()
        if self._source is None:
            return
        for original in self._source.pinnedFrames:
            copy = pg.ImageItem(original.image)
            copy.setTransform(original.transform())
            # Added before setZValue: ViewBox.addItem() raises an incoming
            # item's z-value to its own if the item's is lower, which would
            # otherwise clobber a pinned frame's deliberately very-low z.
            self._view.addItem(copy)
            copy.setZValue(original.zValue())
            self.items.append(copy)

    def _clearItems(self) -> None:
        for item in self.items:
            self._view.removeItem(item)
        self.items = []
