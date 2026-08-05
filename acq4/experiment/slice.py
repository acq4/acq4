"""Slice: the search state for one piece of tissue -- the regions to survey, the
tiles already imaged, the search constraints, and the cell producers it hands out."""

from __future__ import annotations

from dataclasses import dataclass

from .search_grid import count_covered, plan_grid, select_next
from .search_region import SearchRegion


@dataclass(frozen=True)
class SearchConstraints:
    """The Area 2 search constraints that parameterise a cell producer.

    `depth_range` is a pair of z offsets **relative to the tissue surface**, in
    metres, negative being deeper: the design's "-20 um through -60 um" is
    (-20e-6, -60e-6). Surface is found per tile, so the slab follows uneven
    tissue rather than being absolute stage z. Either ordering is accepted.

    `min_health` is the classification model's score cutoff in [0, 1]; cells
    scoring below it are not queued. `max_cell_density` is cells per cubic
    metre, above which a tile counts as already crowded and is skipped rather
    than having more targets packed into it. `rescans_allowed` permits
    re-imaging tiles that have already been covered.
    """

    depth_range: tuple[float, float] = (-20e-6, -60e-6)
    min_health: float = 0.5
    # 5e12 cells/m^3 is 5 cells per (100 um)^3 -- dense for cortex, so the
    # default cap only rejects genuinely crowded tissue.
    max_cell_density: float = 5e12
    rescans_allowed: bool = False

    def __post_init__(self):
        near, far = self.depth_range
        if near > 0 or far > 0:
            raise ValueError(
                f"depth_range offsets must be at or below the surface (<= 0), got {self.depth_range}"
            )
        if near == far:
            raise ValueError(
                f"depth_range must span a nonzero thickness, got {self.depth_range}"
            )
        if not 0.0 <= self.min_health <= 1.0:
            raise ValueError(
                f"min_health must be between 0 and 1, got {self.min_health}"
            )
        if self.max_cell_density <= 0:
            raise ValueError(
                f"max_cell_density must be positive, got {self.max_cell_density}"
            )

    def z_span(self) -> float:
        """Thickness of the searched slab, in metres."""
        near, far = self.depth_range
        return abs(near - far)

    def z_bounds(self, surface: float) -> tuple[float, float]:
        """Absolute (shallower, deeper) z for a tile whose surface is at `surface`."""
        near, far = self.depth_range
        return surface + max(near, far), surface + min(near, far)


class Slice:
    """The search state for one piece of tissue, and the source of its cell producers.

    Owns the regions to survey (global-coordinate shapes), the coverage
    record of which field-of-view tiles have been imaged, the search
    constraints, and -- once a producer is made from it -- the tiles and cells
    that producer accumulates. Coverage is shared by every producer this slice
    makes: that is what stops a second region's survey from re-imaging the
    first's, and what gives `rescans_allowed` something to decide.

    A slice, its coverage, and its producers persist across orchestrator runs.
    They are replaced only when the operator starts a new slice. This is
    deliberately the opposite of Orchestrator._producerExhausted, which is a
    per-run cache: a producer that reported exhaustion is asked again next run,
    precisely so a slice that has gained a region can be surveyed further.

    Not a QObject: it holds no widgets, and staying a plain object keeps it
    refcount-freeable rather than depending on Qt teardown ordering.
    """

    def __init__(self, fov, constraints=None, overlap=0.0):
        fov_w, fov_h = fov
        if fov_w <= 0 or fov_h <= 0:
            raise ValueError(f"fov must be positive in both axes, got {fov}")
        self._fov = (abs(fov_w), abs(fov_h))
        self._overlap = overlap
        self._constraints = (
            constraints if constraints is not None else SearchConstraints()
        )
        self._regions: list[SearchRegion] = []
        self._covered: list[tuple[float, float]] = []
        self._cells: list = []

    # ---- constraints ----
    @property
    def constraints(self) -> SearchConstraints:
        return self._constraints

    def setConstraints(self, constraints: SearchConstraints) -> None:
        self._constraints = constraints

    # ---- regions ----
    @property
    def regions(self) -> list[SearchRegion]:
        """The search regions, as a copy: mutating the result changes nothing."""
        return list(self._regions)

    def addRegion(self, region: SearchRegion) -> None:
        """Add a shape to survey, in global coordinates. Coverage is untouched.

        Takes a SearchRegion rather than four floats because tissue is not
        rectangular: a slice with a damaged corner, or one cortical layer worth
        searching, is the ordinary reason to outline a region at all. A rectangle
        is `RectRegion(x0, y0, x1, y1)`.
        """
        self._regions.append(region)

    # ---- tiles and coverage ----
    @property
    def threshold(self) -> float:
        """Distance below which two tile centers are the same tile."""
        fov_w, fov_h = self._fov
        step = min(fov_w - self._overlap, fov_h - self._overlap)
        if step <= 0:
            step = min(fov_w, fov_h)
        return step / 2

    def tileGrid(self) -> list[tuple[float, float]]:
        """Every region's tile centers, concatenated in the order regions were added.

        Each region's grid is planned over its **bounding box** and then filtered
        to the tiles that overlap the region's shape. That split is what lets a
        slice hold ellipses and polygons while `plan_grid` stays a rectangle
        tiler. For a rectangular region the filter removes nothing, since
        `plan_grid` centers its grid over the box and every tile it plans
        therefore overlaps it.

        Filtering is by overlap, not by whether the tile's center is inside: a
        region narrower than one field of view contains no center at all, and a
        tile whose center falls in the concave part of an L still images real
        region area.

        Within a region the surviving centers keep the serpentine order
        `plan_grid` produces: alternating the direction of each row roughly halves
        the stage travel a survey spends getting from one tile to the next, and
        `nextTile` hands them out in exactly this order.
        """
        grid: list[tuple[float, float]] = []
        fov_w, fov_h = self._fov
        for region in self._regions:
            x0, y0, x1, y1 = region.bounds()
            planned = plan_grid(x0, y0, x1, y1, fov_w, fov_h, self._overlap)
            grid.extend(c for c in planned if region.overlapsTile(c, self._fov))
        return grid

    def nextTile(self) -> tuple[float, float] | None:
        """The next tile center not yet covered, or None when all are.

        Reports only: the caller marks a tile covered once it has actually
        imaged it, so a tile abandoned by a stop is not silently skipped on the
        next run.
        """
        return select_next(self.tileGrid(), self._covered, self.threshold)

    def markCovered(self, center: tuple[float, float]) -> None:
        self._covered.append(tuple(center))

    def resetCoverage(self) -> None:
        """Forget which tiles have been imaged, keeping regions and constraints."""
        self._covered = []

    def forceRescan(self, position, isAttempted) -> int:
        """Re-open the region(s) around `position` for imaging. Returns tiles freed.

        The response to the tracker losing a cell: the coordinates around it are
        no longer trustworthy, so the coverage record claiming that ground was
        already searched has to go, and the cells found there have to be
        rediscovered where they actually are now.

        Scoped to the region(s) the position falls in, not the whole slice. An
        operator working through their third region should not pay to re-image
        the two they finished, and re-imaging a finished region is also a chance
        to re-detect and re-patch cells already dealt with.

        The cost of that scoping, deliberately accepted: tissue motion is global,
        while this treats it as local. If the slice genuinely shifted, finished
        regions are stale too and are not re-imaged here. That is the right
        trade for settling, drift, and swelling -- motion small relative to a
        region -- and the wrong one for a slice that was physically bumped, where
        the tool is New slice rather than a rescan. Nothing here can tell those
        two cases apart.

        `isAttempted` decides which cells survive. Attempted cells stay
        registered at their old positions -- near enough, since the motion is
        small -- so they keep counting toward the density cap and the rescan is
        less likely to resurface a cell already worked. Never-attempted cells are
        dropped so their tiles can come back uncrowded and be found again where
        they now are. The predicate is a parameter because attempted-ness is
        orchestration state held by the UI, not something a slice can know.

        A position inside no region frees nothing: a hand-seeded cell was never
        part of the survey, so there is no coverage of it to invalidate.

        `position` is an indexable global coordinate; only `[0]` and `[1]` are
        read, so a `coorx.Point` and a plain tuple both work, and a 3-D
        position (as a detected cell's is) works too.
        """
        # A region is a shape in the xy plane, so only the first two
        # coordinates of position matter here; a cell's depth is not part of
        # the overlap question. Narrowing to a plain (x, y) tuple also lets
        # this accept a coorx.Point, a Cell.position, or a bare tuple alike.
        xy = (position[0], position[1])
        here = [r for r in self._regions if r.overlapsTile(xy, self._fov)]
        if not here:
            return 0
        stale = [
            t
            for t in self._covered
            if any(r.overlapsTile(t, self._fov) for r in here)
        ]
        if not stale:
            return 0
        drop = set()
        for tile in stale:
            for cell in self.cellsNearTile(tile):
                if not isAttempted(cell):
                    drop.add(id(cell))
        self._cells = [c for c in self._cells if id(c) not in drop]
        stale_ids = {id(t) for t in stale}
        self._covered = [t for t in self._covered if id(t) not in stale_ids]
        return len(stale)

    @property
    def coveredTiles(self) -> list[tuple[float, float]]:
        return list(self._covered)

    def surveyStats(self) -> tuple[int, int, float]:
        """(total tiles, covered tiles, percent covered) across every region."""
        grid = self.tileGrid()
        total = len(grid)
        covered = count_covered(grid, self._covered, self.threshold)
        percent = 100.0 * covered / total if total else 0.0
        return total, covered, percent

    def tileVolume(self) -> float:
        """The volume one tile searches: FOV area times the constrained depth span."""
        fov_w, fov_h = self._fov
        return fov_w * fov_h * self._constraints.z_span()

    # ---- cells found in this tissue ----
    def registerCells(self, cells) -> None:
        """Record cells found in this slice, for the density cap's bookkeeping."""
        self._cells.extend(cells)

    def cellsNearTile(self, center: tuple[float, float]) -> list:
        """Registered cells whose position falls within `center`'s tile."""
        cx, cy = center
        fov_w, fov_h = self._fov
        found = []
        for cell in self._cells:
            pos = cell.position
            if abs(pos[0] - cx) <= fov_w / 2 and abs(pos[1] - cy) <= fov_h / 2:
                found.append(cell)
        return found

    # ---- cell producers ----
    def makeCellProducer(self, detector) -> "CellProducer":
        """A producer that surveys this slice, one tile per call.

        This slice keeps no reference to what it hands back. The producer holds
        the slice, the orchestrator holds the producer, and that one-way chain
        is refcount-freeable; storing producers here would close it into a cycle
        only the cyclic GC could reclaim.
        """
        from .cell_producer import CellProducer

        return CellProducer(self, detector)
