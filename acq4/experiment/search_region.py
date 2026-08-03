"""Search-region shapes for a Slice: the areas a survey tiles over, and the exact
rect-vs-shape overlap tests that decide which planned tiles are worth imaging."""

from __future__ import annotations

from dataclasses import dataclass


def tile_rect(
    center: tuple[float, float], fov: tuple[float, float]
) -> tuple[float, float, float, float]:
    """The closed (x0, y0, x1, y1) area a tile centered at `center` images."""
    cx, cy = center
    fov_w, fov_h = fov
    return (cx - fov_w / 2, cy - fov_h / 2, cx + fov_w / 2, cy + fov_h / 2)


class SearchRegion:
    """An area of tissue to survey, in global metres.

    Subclasses answer the only two questions the tiler asks: the axis-aligned box
    to plan a serpentine grid over, and whether a given planned tile overlaps the
    shape at all. That pair is what lets Slice.tileGrid() support any shape
    without search_grid.plan_grid() knowing shapes exist.

    Overlap, not containment, is the question on purpose. A region narrower than
    one field of view contains no tile center yet is still tissue the operator
    asked for, and a tile whose center falls in the concave part of an L still
    images real region area. Over-imaging slightly past an edge costs one tile;
    failing to image outlined tissue is a silent hole in the survey.

    The geometry is exact and pure-Python by measurement, not preference:
    Qt's QPainterPath.intersects() misreports 24 of 225 tiles for a 3 mm circular
    region tiled by a 200 um field, at every SI magnitude tried, while agreeing
    with these formulas exactly at unit magnitude.
    """

    def bounds(self) -> tuple[float, float, float, float]:
        """The axis-aligned (x0, y0, x1, y1) box containing this region."""
        raise NotImplementedError

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        """Whether a tile centered at `center` of size `fov` overlaps this region."""
        raise NotImplementedError


@dataclass(frozen=True)
class _BoxRegion(SearchRegion):
    """Shared base for the shapes a bounding box defines: the corner
    normalization and validation, which are identical for both.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        lo_x, hi_x = min(self.x0, self.x1), max(self.x0, self.x1)
        lo_y, hi_y = min(self.y0, self.y1), max(self.y0, self.y1)
        if lo_x == hi_x or lo_y == hi_y:
            raise ValueError(
                f"a region needs nonzero extent in both axes, got "
                f"{(self.x0, self.y0, self.x1, self.y1)}"
            )
        object.__setattr__(self, "x0", lo_x)
        object.__setattr__(self, "y0", lo_y)
        object.__setattr__(self, "x1", hi_x)
        object.__setattr__(self, "y1", hi_y)

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class RectRegion(_BoxRegion):
    """A rectangular region: the shape "Add region here" seeds, and the shape for
    which tile filtering is provably a no-op (every tile plan_grid plans over a
    rectangle overlaps that rectangle).
    """

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        return (
            tx0 <= self.x1 and tx1 >= self.x0 and ty0 <= self.y1 and ty1 >= self.y0
        )
