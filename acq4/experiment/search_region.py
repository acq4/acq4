"""Search-region shapes for a Slice: the areas a survey tiles over, the exact
rect-vs-shape overlap tests that decide which planned tiles are worth imaging, the
point tests that decide which of the cells found in them may be patched, and the
plain-data form each shape takes to be written into a slice's directory."""

from __future__ import annotations

import math
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

    Subclasses answer three questions, two of them the tiler's: the axis-aligned
    box to plan a grid over, and whether a given planned tile overlaps the shape
    at all. That pair is what lets Slice.tileGrid() support any shape without
    search_grid.plan_grid() knowing shapes exist.

    For the tiler, overlap rather than containment is the question on purpose. A
    region narrower than one field of view contains no tile center yet is still
    tissue the operator asked for, and a tile whose center falls in the concave
    part of an L still images real region area. Over-imaging slightly past an
    edge costs one tile; failing to image outlined tissue is a silent hole in
    the survey.

    The third question is the producer's, and takes exactly the opposite trade:
    whether a single point -- a detected cell -- is inside the shape. A tile is
    an area and is imaged if it touches the region at all, while a cell is a
    location and is patched only if it genuinely lies within it. The two must
    disagree, because the overhang is deliberate: a field of view straddling the
    outline is what gives the segmenter the context to find cells sitting right
    at the edge, so a tile at the border routinely turns up detections in tissue
    the operator did not ask to patch.

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

    def contains(self, point) -> bool:
        """Whether `point` lies inside this region, on the xy plane.

        `point` is any indexable global coordinate; only `[0]` and `[1]` are
        read, so a `coorx.Point`, a detected cell's 3-D `position`, and a bare
        tuple all work alike -- the same latitude `Slice.forceRescan` allows,
        and for the same reason: a region is a shape in the plane, and a cell's
        depth is no part of the question.

        A point exactly on the boundary may answer either way. That tie is real
        ambiguity rather than lost precision, and it costs at most one cell at
        the very edge of the outline being queued or skipped.
        """
        raise NotImplementedError

    def to_dict(self) -> dict:
        """This region as plain data: dicts, lists, strings and numbers only.

        A fourth question, and the only one that is not geometry. It exists
        because a region is a frozen dataclass and neither place a slice's
        state is written can carry one of those. A YAML document cannot without
        tagging the class name into itself, and the Data Manager's `.index` --
        written with `repr()` and read back with `eval()` in a namespace that
        has never heard of RectRegion -- cannot at all.

        The conversion lives here rather than at either writer so that the
        round trip is defined and tested in one place, next to the `box()` and
        `angle` convention it has to honour.

        `region_from_dict` is the inverse, and is what a saved list is rebuilt
        through: a shape names itself in its own record, so a reader gets its
        regions back without switching on type.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class _BoxRegion(SearchRegion):
    """Shared base for the shapes a bounding box defines: the corner
    normalization and validation, which are identical for both, and the angle
    that turns the box off the axes.

    `angle` is in **degrees counter-clockwise about the `(x0, y0)` corner**, and
    every part of that is measured rather than chosen. Degrees and that pivot are
    what `pg.ROI` itself uses: `ROI.setAngle` records degrees and, given no
    explicit centre, turns the ROI about its local origin -- which is exactly
    what `ROI.pos()` reports, and which it leaves untouched. Matching it lets
    `regionForRoi(roiForRegion(r))` read `pos()` and `size()` back with the same
    arithmetic it used at zero angle, so the round trip is exact at every angle.
    A centre pivot cannot be: recovering a corner from a centre costs a halving
    and its inverse, which over 2000 measured regions failed to return the
    original float about half the time -- including at zero angle, where it would
    move regions nobody rotated. Counter-clockwise is the direction Qt's
    transform turns a point in these coordinates, checked corner by corner
    against `[[cos, -sin], [sin, cos]]`.

    Angle zero is a shape's ordinary state and takes the axis-aligned path
    throughout, returning the same floats as a region with no angle at all.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    angle: float = 0.0

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

    def box(self) -> tuple[float, float, float, float]:
        """The unrotated (x0, y0, x1, y1) box this shape is inscribed in.

        Distinct from `bounds()` as soon as there is an angle: this is the box
        the operator sized, which an ROI is rebuilt from, while `bounds()` is the
        axis-aligned extent of the turned shape, which the tiler plans over.
        """
        return (self.x0, self.y0, self.x1, self.y1)

    def _cosSin(self) -> tuple[float, float]:
        th = math.radians(self.angle)
        return (math.cos(th), math.sin(th))

    def _turn(self, x: float, y: float) -> tuple[float, float]:
        """`(x, y)` turned by this region's angle about its pivot."""
        c, s = self._cosSin()
        dx, dy = x - self.x0, y - self.y0
        return (self.x0 + dx * c - dy * s, self.y0 + dx * s + dy * c)

    def _unturn(self, x: float, y: float) -> tuple[float, float]:
        """`(x, y)` brought back into the frame where this shape is axis-aligned.

        The inverse of `_turn`, which is what makes a membership test one
        formula for every angle: bring the point back and the shape is the box
        the operator sized, so containment is the comparison it always was.
        """
        if self.angle == 0.0:
            return (x, y)
        c, s = self._cosSin()
        dx, dy = x - self.x0, y - self.y0
        return (self.x0 + dx * c + dy * s, self.y0 - dx * s + dy * c)

    def _boxCorners(self) -> tuple:
        """The four corners of the turned box, counter-clockwise from the pivot."""
        corners = (
            (self.x0, self.y0),
            (self.x1, self.y0),
            (self.x1, self.y1),
            (self.x0, self.y1),
        )
        if self.angle == 0.0:
            return corners
        return tuple(self._turn(x, y) for x, y in corners)

    def _center(self) -> tuple[float, float]:
        """The shape's centre, after the turn."""
        cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        return (cx, cy) if self.angle == 0.0 else self._turn(cx, cy)

    def to_dict(self) -> dict:
        """`box()` and `angle`, which are exactly the two things stored.

        Deliberately not `bounds()`: as soon as there is an angle those differ,
        and `bounds()` is the axis-aligned hull of the turned shape -- a
        derived quantity that cannot be turned back into the shape it came
        from. `box()` is what the operator sized, what an ROI is rebuilt from,
        and what the angle is measured about, so writing those two makes the
        round trip the identity rather than an approximation of one. The
        reasoning is the same one this class's own docstring gives for pivoting
        about a corner: nothing is halved on the way out, so nothing has to be
        doubled on the way back, and the shape reopens on exactly the floats it
        was drawn at -- at zero angle as much as at any other.
        """
        return {"shape": self.shapeName, "box": list(self.box()), "angle": self.angle}

    @classmethod
    def from_dict(cls, d: dict) -> "_BoxRegion":
        """Rebuild from what `to_dict` wrote.

        A missing `angle` reads as zero, so a record that names only a box --
        one written by hand, or by an older version that had no angles -- is an
        ordinary unturned region rather than a refused one. That is the same
        latitude the dataclass's own default already gives a caller.
        """
        x0, y0, x1, y1 = d["box"]
        return cls(x0, y0, x1, y1, d.get("angle", 0.0))


def _project(points, ax: float, ay: float) -> tuple[float, float]:
    """The (low, high) shadow `points` cast on the direction `(ax, ay)`."""
    dots = [px * ax + py * ay for px, py in points]
    return (min(dots), max(dots))


class RectRegion(_BoxRegion):
    """A rectangular region: the shape "Add region here" seeds, and -- while it
    sits on the axes -- the shape for which tile filtering is provably a no-op
    (every tile plan_grid plans over an axis-aligned rectangle overlaps that
    rectangle). Turn it and that stops being true: the grid is planned over the
    turned rectangle's larger axis-aligned bounds, whose corners stick out past
    the shape, so the filter starts earning its place.
    """

    # The tag this shape writes into its record and is rebuilt by. The same
    # word RegionPanel's shape selector uses, so one vocabulary describes a
    # shape from the picker that seeds it through to the file it is saved in.
    shapeName = "rect"

    def bounds(self) -> tuple[float, float, float, float]:
        if self.angle == 0.0:
            return self.box()
        corners = self._boxCorners()
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        return (min(xs), min(ys), max(xs), max(ys))

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        if self.angle == 0.0:
            return (
                tx0 <= self.x1 and tx1 >= self.x0 and ty0 <= self.y1 and ty1 >= self.y0
            )
        # Two convex boxes miss each other only if some direction separates
        # them, and for two rectangles the only directions that can are their own
        # edge normals: the tile's two axes and this rectangle's two. So four
        # projections settle it exactly, with no iteration and no epsilon --
        # every comparison is between two shadows cast on the same direction,
        # which is the scale-freedom `_segment_touches_rect` was written for.
        corners = self._boxCorners()
        tileCorners = ((tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1))
        c, s = self._cosSin()
        for ax, ay in ((1.0, 0.0), (0.0, 1.0), (c, s), (-s, c)):
            lo, hi = _project(corners, ax, ay)
            tlo, thi = _project(tileCorners, ax, ay)
            if hi < tlo or thi < lo:
                return False
        return True

    def contains(self, point) -> bool:
        x, y = self._unturn(point[0], point[1])
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1


class EllipseRegion(_BoxRegion):
    """The ellipse inscribed in a bounding box -- the shape a `pg.EllipseROI`
    draws, and the natural outline for a rounded piece of tissue.

    Overlap is exact and needs no iteration: mapping the tile into the frame where
    the ellipse is the unit circle at the origin turns "does this rect reach the
    ellipse" into "is the closest point of a rect to the origin within 1". While
    the ellipse sits on the axes, an axis-aligned rect stays axis-aligned under
    that (per-axis) scaling, which is what makes the closest point a per-axis
    clamp rather than a search. Turn the ellipse and the map gains a rotation, so
    the tile arrives as a parallelogram and the clamp gives way to the distance
    from the origin to that quadrilateral -- still closed form, still one pass.
    """

    shapeName = "ellipse"

    def bounds(self) -> tuple[float, float, float, float]:
        if self.angle == 0.0:
            return self.box()
        # A turned ellipse is strictly narrower than the box it was inscribed in,
        # so hulling the four turned corners would plan a ring of tiles that can
        # never touch it. These half-extents are the exact support of the ellipse
        # along each axis, in closed form.
        rx = (self.x1 - self.x0) / 2
        ry = (self.y1 - self.y0) / 2
        c, s = self._cosSin()
        hw = math.hypot(rx * c, ry * s)
        hh = math.hypot(rx * s, ry * c)
        cx, cy = self._center()
        return (cx - hw, cy - hh, cx + hw, cy + hh)

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        rx = (self.x1 - self.x0) / 2
        ry = (self.y1 - self.y0) / 2
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        if self.angle == 0.0:
            cx = (self.x0 + self.x1) / 2
            cy = (self.y0 + self.y1) / 2
            ax0, ax1 = (tx0 - cx) / rx, (tx1 - cx) / rx
            ay0, ay1 = (ty0 - cy) / ry, (ty1 - cy) / ry
            # Clamp the origin into the mapped rect: the result is the rect's
            # closest point to the ellipse center, and zero on an axis the center
            # falls within.
            dx = max(ax0, min(0.0, ax1))
            dy = max(ay0, min(0.0, ay1))
            return dx * dx + dy * dy <= 1.0
        cx, cy = self._center()
        c, s = self._cosSin()
        # Into the ellipse's own frame -- translate to its centre, turn back by
        # the angle, then divide each axis by its radius. The map is affine, so
        # the tile arrives as a parallelogram with its corners in the same cyclic
        # order, and the ellipse arrives as the unit circle at the origin.
        quad = []
        for px, py in ((tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)):
            dx, dy = px - cx, py - cy
            quad.append(((dx * c + dy * s) / rx, (-dx * s + dy * c) / ry))
        # Which leaves one question: is the origin within 1 of that quadrilateral.
        # Zero when it is inside, and otherwise the nearest point lies on an edge.
        if _point_in_polygon(0.0, 0.0, quad):
            return True
        return any(
            _point_segment_distance_sq(0.0, 0.0, quad[i], quad[(i + 1) % 4]) <= 1.0
            for i in range(4)
        )

    def contains(self, point) -> bool:
        # The same map the overlap test uses, applied to a single point: into
        # the frame where this ellipse is the unit circle at the origin, where
        # membership is one comparison against 1 whatever the angle or the
        # aspect ratio.
        x, y = self._unturn(point[0], point[1])
        cx, cy = (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
        dx = (x - cx) / ((self.x1 - self.x0) / 2)
        dy = (y - cy) / ((self.y1 - self.y0) / 2)
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


def _point_segment_distance_sq(
    px: float, py: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    """The squared distance from `(px, py)` to the segment `a`->`b`.

    Squared, because every caller compares it against a squared radius and the
    square root would only cost precision on the way to the same answer.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    lengthSq = dx * dx + dy * dy
    if lengthSq == 0.0:
        t = 0.0
    else:
        # Where the perpendicular foot falls along the segment, clamped to it.
        t = min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / lengthSq))
    nx, ny = px - (ax + t * dx), py - (ay + t * dy)
    return nx * nx + ny * ny


def _point_in_polygon(px: float, py: float, vertices) -> bool:
    """Crossing-number containment test for an implicitly closed polygon.

    Points exactly on the boundary are not guaranteed either answer, which is
    fine here: this is only consulted for tiles no edge touches, so the point is
    inside or outside, with a boundary tie resolving either way and costing at
    most one tile of over- or under-imaging.
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

    shapeName = "polygon"

    vertices: tuple

    def __post_init__(self):
        verts = tuple((float(x), float(y)) for x, y in self.vertices)
        if len(verts) < 3:
            raise ValueError(
                f"a polygon region needs at least 3 vertices, got {len(verts)}"
            )
        xs = [x for x, _ in verts]
        ys = [y for _, y in verts]
        if min(xs) == max(xs) or min(ys) == max(ys):
            raise ValueError(
                f"a region needs nonzero extent in both axes, got {verts}"
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

    def contains(self, point) -> bool:
        # A polygon carries no angle: its vertices are already the global
        # coordinates the operator's ROI put them at, turned or not, so there is
        # no frame to come back from.
        return _point_in_polygon(float(point[0]), float(point[1]), self.vertices)

    def to_dict(self) -> dict:
        # Lists of two floats rather than the tuples held here, because a tuple
        # is not plain data everywhere this record has to go: yaml.dump writes
        # one as a tagged Python object rather than as a sequence. Nothing is
        # lost by that -- __post_init__ turns whatever it is given back into
        # tuples of floats -- and a polygon carries no angle, so its vertices
        # are the whole of its geometry.
        return {"shape": self.shapeName, "vertices": [[x, y] for x, y in self.vertices]}

    @classmethod
    def from_dict(cls, d: dict) -> "PolygonRegion":
        return cls(d["vertices"])


# Every shape a slice's record may name. The tag lives on the class rather than
# in a table here, so a shape cannot end up with its name spelled one way where
# it is written and another where it is read.
_REGION_CLASSES = (RectRegion, EllipseRegion, PolygonRegion)


def region_from_dict(d: dict) -> SearchRegion:
    """Rebuild whichever region `d` describes.

    The dispatch a saved list is read back through, so restoring the outlines
    an operator drew is one comprehension rather than a switch on shape at
    every reader.

    An unrecognised tag raises rather than falling back to a rectangle. The two
    things that produce one are a record written by a later version and a file
    edited by hand, and in both cases a silent fallback would plan a survey
    over tissue that is not the shape anybody outlined -- and would report
    coverage against it. A region that fails to load is recoverable; a region
    nobody drew is not.
    """
    shape = d.get("shape")
    for cls in _REGION_CLASSES:
        if cls.shapeName == shape:
            return cls.from_dict(d)
    raise ValueError(
        f"unknown region shape {shape!r}; expected one of "
        f"{[c.shapeName for c in _REGION_CLASSES]}"
    )
