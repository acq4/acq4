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


class EllipseRegion(_BoxRegion):
    """The ellipse inscribed in a bounding box -- the shape a `pg.EllipseROI`
    draws, and the natural outline for a rounded piece of tissue.

    Overlap is exact and needs no iteration: mapping the tile into the frame where
    the ellipse is the unit circle at the origin turns "does this rect reach the
    ellipse" into "is the closest point of a rect to the origin within 1". An
    axis-aligned rect stays axis-aligned under that (per-axis) scaling, which is
    what makes the closest point a per-axis clamp rather than a search.
    """

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        cx = (self.x0 + self.x1) / 2
        cy = (self.y0 + self.y1) / 2
        rx = (self.x1 - self.x0) / 2
        ry = (self.y1 - self.y0) / 2
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        ax0, ax1 = (tx0 - cx) / rx, (tx1 - cx) / rx
        ay0, ay1 = (ty0 - cy) / ry, (ty1 - cy) / ry
        # Clamp the origin into the mapped rect: the result is the rect's closest
        # point to the ellipse center, and zero on an axis the center falls within.
        dx = max(ax0, min(0.0, ax1))
        dy = max(ay0, min(0.0, ay1))
        return dx * dx + dy * dy <= 1.0


def _segment_touches_rect(
    p: tuple[float, float],
    q: tuple[float, float],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> bool:
    """Whether the segment p->q touches the closed rect (Liang-Barsky clipping).

    Exact and scale-free: every comparison is between quantities of the same
    magnitude, so there is no epsilon to get wrong at either 1e-6 or 1e7.
    """
    px, py = p
    qx, qy = q
    dx = qx - px
    dy = qy - py
    t0, t1 = 0.0, 1.0
    for num, den in ((x0 - px, dx), (px - x1, -dx), (y0 - py, dy), (py - y1, -dy)):
        if den == 0.0:
            # Parallel to this edge: being outside it means no crossing exists.
            if num > 0.0:
                return False
            continue
        t = num / den
        if den > 0.0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


def _point_in_polygon(px: float, py: float, vertices) -> bool:
    """Crossing-number containment test for an implicitly closed polygon.

    Points exactly on the boundary are not guaranteed either answer, which is
    fine here: this is only consulted for tiles no edge touches, so the point is
    strictly inside or strictly outside.
    """
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class PolygonRegion(SearchRegion):
    """An arbitrary simple polygon, implicitly closed -- what a `pg.PolyLineROI`
    drawn around a cortical layer or an undamaged patch of slice produces.

    Vertices are stored as a tuple of float pairs so a region stays hashable and
    comparing two regions compares their geometry.
    """

    vertices: tuple

    def __post_init__(self):
        verts = tuple((float(x), float(y)) for x, y in self.vertices)
        if len(verts) < 3:
            raise ValueError(
                f"a polygon region needs at least 3 vertices, got {len(verts)}"
            )
        object.__setattr__(self, "vertices", verts)

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [x for x, _ in self.vertices]
        ys = [y for _, y in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        verts = self.vertices
        # An edge crossing the tile is the common answer, and it also covers the
        # case of a polygon small enough to sit entirely inside one tile.
        for i in range(len(verts)):
            if _segment_touches_rect(
                verts[i], verts[(i + 1) % len(verts)], tx0, ty0, tx1, ty1
            ):
                return True
        # With no edge touching it, the tile is either wholly inside the polygon
        # or wholly outside, so a single corner settles it.
        return _point_in_polygon(tx0, ty0, verts)
