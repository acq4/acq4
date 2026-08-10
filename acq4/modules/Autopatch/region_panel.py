"""RegionPanel: Area 1's global-coordinate view of the slice -- the pinned
imagery to draw over, and the search regions drawn on it as editable ROIs."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
)

# Yellow at 2px, matching the survey ROI the AutomationDebug bench already
# draws, so the same shape reads the same way in either module.
REGION_PEN = pg.mkPen("y", width=2)


class _AxisAlignedEllipseROI(pg.EllipseROI):
    """A pg.EllipseROI with no rotate handle.

    EllipseRegion is the ellipse inscribed in an axis-aligned bounding box, so
    there is no region for a rotated ROI to map back to: regionForRoi reads the
    ROI's position and size, and a rotation would be dropped without trace --
    the operator would draw one shape and the survey would tile another.
    """

    def _addHandles(self):
        self.addScaleHandle([1.0, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5, 1.0], [0.5, 0.5])


def roiForRegion(region: SearchRegion) -> pg.ROI:
    """The editable ROI that draws `region`."""
    if isinstance(region, PolygonRegion):
        return pg.PolyLineROI(
            [list(v) for v in region.vertices],
            closed=True,
            pen=REGION_PEN,
            removable=True,
        )
    x0, y0, x1, y1 = region.bounds()
    roiClass = _AxisAlignedEllipseROI if isinstance(region, EllipseRegion) else pg.RectROI
    return roiClass(
        (x0, y0), (x1 - x0, y1 - y0), pen=REGION_PEN, removable=True
    )


def regionForRoi(roi: pg.ROI) -> SearchRegion | None:
    """The region `roi` currently describes, or None if it does not describe one.

    An ROI can be dragged flat, and its handles can be dragged collinear;
    SearchRegion rejects both, since a region with no extent has no tiles. This
    is reached from a Qt signal while the operator is mid-drag, so it reports
    the failure by returning None rather than by raising a traceback out of a
    slot -- the same choice `SearchPanel.constraints()` makes, and for the same
    reason.

    Corner normalization is left to `_BoxRegion.__post_init__`, which already
    orders its corners -- an ROI resized past its own origin reports a negative
    size, and both paths through that hazard should agree by construction rather
    than by two implementations happening to match.
    """
    try:
        if isinstance(roi, pg.PolyLineROI):
            vertices = []
            for _, localPos in roi.getLocalHandlePositions():
                globalPos = roi.mapToParent(localPos)
                vertices.append((globalPos.x(), globalPos.y()))
            return PolygonRegion(tuple(vertices))
        pos = roi.pos()
        size = roi.size()
        x0, y0 = pos.x(), pos.y()
        regionClass = EllipseRegion if isinstance(roi, pg.EllipseROI) else RectRegion
        return regionClass(x0, y0, x0 + size.x(), y0 + size.y())
    except ValueError:
        return None
