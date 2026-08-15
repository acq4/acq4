"""The two one-way mirrors either side of Area 1's view: the Camera module's
pinned frames coming in, and read-only region outlines going out."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.experiment.search_region import EllipseRegion, PolygonRegion
from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException

from .region_panel import REGION_PEN


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
        """Stop mirroring and take the copies out of the view.

        Tolerant of a source Qt has already destroyed. pg.disconnect swallows
        the RuntimeError a dead connection raises, but the signal is read off
        the source before it can be handed to pg.disconnect at all, and that
        read raises through a wrapper whose C++ object is gone. A raise here
        would abandon the rest of AutopatchWindow.teardown(), leaving every
        panel still wired to the orchestrator it had just stopped.
        """
        source, self._source = self._source, None
        if source is not None:
            try:
                Qt.disconnect(source.sigPinnedFramesChanged, self.refresh)
            except RuntimeError:
                pass
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
            # A real pinned frame is built with its levels and lookup table
            # spelled out (ImagingCtrl.pinCurrentFrame, Frame.imageItem), and an
            # ImageItem given neither scales itself to its own contents. Copies
            # left to do that would each pick their own scale, so adjacent
            # frames in one mosaic would not match, and a 16-bit frame with a
            # narrow range would render near-flat. Both are optional on the way
            # in, so an absent one is left absent rather than invented.
            levels = original.getLevels()
            if levels is not None:
                copy.setLevels(levels)
            if original.lut is not None:
                copy.setLookupTable(original.lut)
            # addItem() must run before setZValue(): ViewBox.addItem() raises
            # an incoming item's z-value to the view's own if the item's is
            # lower, which would clobber a pinned frame's deliberately
            # very-low z if the z-value were already set beforehand.
            self._view.addItem(copy)
            copy.setZValue(original.zValue())
            self.items.append(copy)

    def _clearItems(self) -> None:
        for item in self.items:
            self._view.removeItem(item)
        self.items = []


# Above the camera frame image so an outline is visible over tissue, below the
# pipette target and its arrows at z=5000 so those stay on top -- the same band
# the AutomationDebug survey ROI sits in.
_MIRROR_Z = 4000


def _pathForRegion(region) -> Qt.QPainterPath:
    """The outline of `region`, in global metres.

    A QPainterPath is the right tool for drawing an outline even though P2c-1
    removed QPainterPath from the *overlap* test: that finding is about asking
    Qt to decide whether a rect and a shape intersect, where its clipper's
    absolute tolerances misreport tiles at SI-metre magnitudes. Drawing asks Qt
    no such question.
    """
    path = Qt.QPainterPath()
    if isinstance(region, PolygonRegion):
        first = region.vertices[0]
        path.moveTo(first[0], first[1])
        for x, y in region.vertices[1:]:
            path.lineTo(x, y)
        path.closeSubpath()
        return path
    # `box()`, not `bounds()`: once a region has an angle those differ, and it is
    # the box the operator sized that gets drawn and then turned. Drawing
    # `bounds()` would put the axis-aligned hull on screen instead of the shape.
    x0, y0, x1, y1 = region.box()
    rect = Qt.QRectF(x0, y0, x1 - x0, y1 - y0)
    if isinstance(region, EllipseRegion):
        path.addEllipse(rect)
    else:
        path.addRect(rect)
    if region.angle:
        # About the (x0, y0) corner, the region's own pivot. `QTransform.rotate`
        # is the same call `pg.ROI.setAngle` makes, so the mirrored outline and
        # the editable ROI in Area 1 turn together by construction.
        turn = Qt.QTransform()
        turn.translate(x0, y0)
        turn.rotate(region.angle)
        turn.translate(-x0, -y0)
        path = turn.map(path)
    return path


class CameraMirror:
    """Draws read-only outlines of Autopatch's regions in the Camera window.

    Outlines are QGraphicsPathItems, not ROIs, and that is what makes them
    read-only structurally rather than by policy: there is no handle to grab and
    no second copy of a region's state to reconcile. Autopatch stays the only
    place a region is edited.

    Holds no region state of its own -- it is told what to draw. A Camera module
    that is not loaded is ordinary, not an error: this is a display preference.
    """

    def __init__(self, cameraWindowGetter):
        self._cameraWindow = cameraWindowGetter
        self._enabled = False
        self._regions = []
        self.items = []

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._redraw()

    def setRegions(self, regions) -> None:
        self._regions = list(regions)
        self._redraw()

    def clear(self) -> None:
        """Take every outline out of the Camera window.

        Separate from setEnabled(False) because teardown has to remove them
        without changing what the operator asked for.
        """
        window = self._windowOrNone()
        for item in self.items:
            if window is not None:
                window.removeItem(item)
        self.items = []

    def _redraw(self) -> None:
        self.clear()
        if not self._enabled:
            return
        window = self._windowOrNone()
        if window is None:
            return
        for region in self._regions:
            item = Qt.QGraphicsPathItem(_pathForRegion(region))
            item.setPen(REGION_PEN)
            item.setAcceptedMouseButtons(Qt.Qt.NoButton)
            window.addItem(item, z=_MIRROR_Z)
            self.items.append(item)

    def _windowOrNone(self):
        """The Camera window, or None if there is not one.

        The getter (AutopatchWindow._cameraModuleWindow) raises rather than
        answering None everywhere else, since a missing Camera module is an
        operator-facing error there. Here it stays what the class docstring
        above says it always was: no manager (a headless window), no Camera
        module, or one closed since this window opened are all ordinary --
        this mirror is a display preference, not a dependency -- so any of
        those is folded back into the None this class already knows how to do
        nothing with.
        """
        try:
            return self._cameraWindow()
        except HelpfulException:
            return None
