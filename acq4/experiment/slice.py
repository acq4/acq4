"""Slice: the search state for one piece of tissue -- the regions to survey, the
tiles already imaged, the search constraints, the cell producers it hands out, and
the record of all of that it writes into its data directory."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from acq4.logging_config import get_logger

from .search_grid import (
    COVERED_FRACTION,
    count_grid,
    covered_fraction,
    footprint,
    plan_center_out,
)
from .survey import Survey, cellDistance
from .search_region import SearchRegion, region_from_dict


logger = get_logger(__name__)


# The two files a slice's state is written to, inside its own data directory.
# Two rather than one because they answer different questions and are edited at
# different rates: the regions are what the operator traced by hand and are the
# irreplaceable half, while the search parameters and coverage are reproducible
# from a rerun. Splitting them also means a reader that only wants the outlines
# -- to redraw last night's slice, say -- does not have to parse a tile list of
# up to MAX_PLANNED_TILES entries to get them.
REGIONS_FILE = "regions.yaml"
SEARCH_STATE_FILE = "search_state.yaml"
PROTOCOL_STATE_FILE = "protocol_state.yaml"

# The subdirectory a slice's pinned frames are archived into, inside that
# slice's own data directory. A directory of MetaArrays rather than one
# container file: the Data Manager already reads and displays a `.ma`, so this
# costs no new file type and no new viewer, and one frame per file is also what
# lets a partly-written archive still be worth something.
PINNED_FRAMES_DIR = "pinned_frames"
_FRAME_FILE = re.compile(r"frame_\d{3,}\.ma")

# The most tiles one region's bounding box may plan. At a 130 um field a
# generous 10 mm slice is about 77x77 = 5,900 tiles, so this is roughly an
# 18 mm square: past any tissue that fits on a rig, and still three orders of
# magnitude short of what one mis-drag plans -- the 0.687 m x 0.873 m polygon
# that prompted this cap planned 35,208,476 tiles at a 130.6 um field, minutes
# of compute per ROI edit and a list of that length to hold.
MAX_PLANNED_TILES = 20_000


def writePinnedFrames(dirHandle, frames) -> list[str]:
    """Make `dirHandle`'s PINNED_FRAMES_DIR hold exactly `frames`, one
    MetaArray each as `frame_000.ma`, `frame_001.ma`, ... Returns the names.

    Any `frame_NNN.ma` beyond the new count is deleted, so the directory
    always equals the set written last. An empty set where no directory
    exists creates none: a slice whose operator pinned nothing should not
    leave an empty folder behind claiming otherwise.
    """
    frames = list(frames)
    if not frames and not dirHandle.exists(PINNED_FRAMES_DIR):
        return []
    archive = dirHandle.getDir(PINNED_FRAMES_DIR, create=True)
    names = []
    for i, frame in enumerate(frames):
        name = f"frame_{i:03d}.ma"
        archive.writeFile(frame, name, fileType="MetaArray")
        names.append(name)
    for name in archive.ls():
        if _FRAME_FILE.fullmatch(name) and name not in names:
            archive[name].delete()
    return names


class RegionTooLarge(ValueError):
    """A region whose bounding box would plan more than MAX_PLANNED_TILES tiles.

    A ValueError because it is a rejected argument, not an orchestration state:
    nothing routes it to an exception handler, and the only caller that catches
    it is the UI seam that refuses the operator's edit.
    """


@dataclass(frozen=True)
class SearchConstraints:
    """The Area 2 search constraints that parameterise a cell producer.

    `depth_range` is a pair of z offsets **relative to the tissue surface**, in
    metres, negative being deeper: the design's "-20 um through -60 um" is
    (-20e-6, -60e-6). Surface is found per tile, so the slab follows uneven
    tissue rather than being absolute stage z. Either ordering is accepted.

    `min_health` is the classification model's score cutoff in [0, 1]; cells
    scoring below it are not queued. `min_cell_spacing` is the closest, in metres
    and in 3D, that a queued cell's centre may be to any other handed-out cell's;
    the tile density cap is derived from it (see `max_cell_density`).
    `rescans_allowed` permits re-imaging tiles that have already been covered.

    `min_volume_m3` and `step_z` parameterise the tile detector rather than
    the search itself: a volume floor below which a detected blob is not a
    cell, and the z step its detection stack is acquired at. They live here
    (rather than as a separate, unpersisted rig setting) so an operator's
    choice for one slice is exactly as reproducible as the health cutoff or
    the density cap.
    """

    depth_range: tuple[float, float] = (-20e-6, -60e-6)
    min_health: float = 0.5
    min_cell_spacing: float = 30e-6
    rescans_allowed: bool = False
    min_volume_m3: float = 0.0
    step_z: float = 1e-6

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
        if self.min_cell_spacing <= 0:
            raise ValueError(
                f"min_cell_spacing must be positive, got {self.min_cell_spacing}"
            )
        if self.step_z <= 0:
            raise ValueError(f"step_z must be positive, got {self.step_z}")
        if self.min_volume_m3 < 0:
            raise ValueError(
                f"min_volume_m3 must be non-negative, got {self.min_volume_m3}"
            )

    def z_span(self) -> float:
        """Thickness of the searched slab, in metres."""
        near, far = self.depth_range
        return abs(near - far)

    def z_bounds(self, surface: float) -> tuple[float, float]:
        """Absolute (shallower, deeper) z for a tile whose surface is at `surface`."""
        near, far = self.depth_range
        return surface + max(near, far), surface + min(near, far)

    @property
    def max_cell_density(self) -> float:
        """Cells per cubic metre at which a tile counts as crowded and is skipped:
        one sphere of radius `min_cell_spacing` per cell.

        Deliberately below what the spacing alone permits. Centres placed at
        random no closer than r apart saturate near 0.38 volume fraction of r/2
        spheres, about three times this figure, so a tile is skipped as not worth
        the imaging time well before it is provably full.
        """
        return 1.0 / (4.0 / 3.0 * math.pi * self.min_cell_spacing**3)


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

    def __init__(self, fov, constraints=None, overlap=0.0, dirHandle=None):
        fov_w, fov_h = fov
        if fov_w <= 0 or fov_h <= 0:
            raise ValueError(f"fov must be positive in both axes, got {fov}")
        self._fov = (abs(fov_w), abs(fov_h))
        self._overlap = overlap
        self._constraints = (
            constraints if constraints is not None else SearchConstraints()
        )
        self._regions: list[SearchRegion] = []
        self.survey = Survey(self._fov, dirHandle)
        self._dirHandle = dirHandle

    # The Data Manager directory this slice's data is written under, or None
    # for a slice that came into existence to hold a region rather than by
    # way of New slice. The handle is also what a later change would call
    # setInfo()/info() on to persist regions and coverage.
    @property
    def dirHandle(self):
        return self._dirHandle

    @dirHandle.setter
    def dirHandle(self, handle):
        self._dirHandle = handle
        self.survey._dirHandle = handle

    # ---- constraints ----
    @property
    def constraints(self) -> SearchConstraints:
        return self._constraints

    def setConstraints(self, constraints: SearchConstraints) -> None:
        self._constraints = constraints

    @property
    def fov(self) -> tuple[float, float]:
        """The imaged field's (width, height) in global metres."""
        return self._fov

    # ---- regions ----
    @property
    def regions(self) -> list[SearchRegion]:
        """The search regions, as a copy: mutating the result changes nothing."""
        return list(self._regions)

    def setRegions(self, regions) -> None:
        """Replace the regions to survey, in one step. Coverage is untouched.

        Rebinding the attribute rather than mutating the list is what makes this
        safe to call from the GUI thread while a producer is reading regions on
        the worker thread: `tileGrid()` binds its loop to whichever list object
        was current when it started, so a reader sees either the whole old set
        or the whole new one and never a list changing under its own iteration.
        The same "make it one step" discipline `Orchestrator._refillQueue`
        applies to the producer reference.

        Raises RegionTooLarge, leaving the current regions in place, if any of
        `regions` would plan more tiles than a survey can sensibly hold. Every
        region reaches a slice through here, which is why the check lives here
        rather than in the UI: the count is checked before the swap, so a
        refused list changes nothing at all.
        """
        regions = list(regions)
        for region in regions:
            self._checkPlannedTiles(region)
        self._regions = regions

    def _checkPlannedTiles(self, region: SearchRegion) -> None:
        """Raise RegionTooLarge if `region` would plan more than the cap allows.

        Counted arithmetically rather than by planning, because the count is the
        hazard: `tileGrid()` has the planner build the whole bounding-box grid
        before any of it is filtered against the shape, so a check that planned
        first would spend exactly the time and memory it exists to prevent.
        """
        x0, y0, x1, y1 = region.bounds()
        fov_w, fov_h = self._fov
        planned = count_grid(x0, y0, x1, y1, fov_w, fov_h, self._overlap)
        if planned > MAX_PLANNED_TILES:
            raise RegionTooLarge(
                f"a region of {abs(x1 - x0):.3g} m x {abs(y1 - y0):.3g} m would "
                f"plan {planned} tiles at this field of view, over the "
                f"{MAX_PLANNED_TILES} tile limit"
            )

    def addRegion(self, region: SearchRegion) -> None:
        """Add a shape to survey, in global coordinates. Coverage is untouched.

        Takes a SearchRegion rather than four floats because tissue is not
        rectangular: a slice with a damaged corner, or one cortical layer worth
        searching, is the ordinary reason to outline a region at all. A rectangle
        is `RectRegion(x0, y0, x1, y1)`.

        Raises RegionTooLarge, adding nothing, for a region past the tile cap --
        this goes through setRegions(), which is where that check lives.
        """
        self.setRegions(self._regions + [region])

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
        slice hold ellipses and polygons while `plan_center_out` stays a
        rectangle tiler. For a rectangular region the filter removes nothing,
        since the planner centers its grid over the box and every tile it plans
        therefore overlaps it.

        Filtering is by overlap, not by whether the tile's center is inside: a
        region narrower than one field of view contains no center at all, and a
        tile whose center falls in the concave part of an L still images real
        region area.

        Within a region the centers are ordered outward from its most interior
        tile, and `nextTile` hands them out in exactly that order. A survey then
        starts on the best tissue a region has -- its middle, farthest from the
        damaged edges -- and each tile it moves to is next to ground it has
        already imaged, so an operator who stops the run early is left with a
        compact surveyed area rather than a band along one side.

        Ordering is per region, and regions keep the order they were added in.
        Two regions are two pieces of tissue with a stage move between them;
        interleaving their tiles would pay that move over and over, and "outward
        from the middle" has no meaning across a gap.
        """
        # Bound once: setRegions() can land from the GUI thread while this runs.
        return self._tileGridFor(self._regions)

    def _tileGridFor(self, regions) -> list[tuple[float, float]]:
        """tileGrid()'s body, over a region list the caller has already bound.

        Split out so that a caller which has to derive several things from one
        set of regions -- saveState(), which writes the outlines and the tile
        counts they imply into the same record -- can do so from a single
        binding. Re-reading self._regions per derivation would leave that
        record describing two different slices.
        """
        grid: list[tuple[float, float]] = []
        fov_w, fov_h = self._fov
        for region in regions:
            x0, y0, x1, y1 = region.bounds()
            # The shape filter is handed to the planner rather than applied to
            # its output, because the order depends on which tiles survive it:
            # the most interior tile of an L is not the most interior tile of
            # the box around it.
            grid.extend(
                plan_center_out(
                    x0,
                    y0,
                    x1,
                    y1,
                    fov_w,
                    fov_h,
                    self._overlap,
                    keep=lambda c, region=region: region.overlapsTile(c, self._fov),
                )
            )
        return grid

    def containsPoint(self, position) -> bool:
        """Whether `position` falls inside any of this slice's regions.

        The gate on what a survey is allowed to patch. The tiles it images
        deliberately overhang the outline -- a field of view straddling the edge
        is what gives the segmenter the context to find cells sitting right at
        it -- so a detection landing outside the drawn region is the ordinary
        case at every border tile, not a rare one.

        A slice with no regions contains everything: "no region drawn" means
        there is nothing to be outside of. Hand seeds never reach this gate; the
        survey hands them out through operator intent.

        `position` is any indexable global coordinate, the same latitude
        `forceRescan` allows; only its first two coordinates are read.
        """
        # Bound once, for the reason setRegions() documents: the GUI thread can
        # swap the whole list while a producer is asking this on the worker
        # thread, and one binding sees either the whole old set or the whole new
        # one rather than a list changing under its own iteration.
        regions = self._regions
        if not regions:
            return True
        return any(r.contains(position) for r in regions)

    def isCovered(self, center) -> bool:
        return self._isCoveredBy(center, self.survey.footprints())

    def _isCoveredBy(self, center, footprints) -> bool:
        return covered_fraction(footprint(center, self._fov), footprints) >= COVERED_FRACTION

    def uncoveredTiles(self) -> list[tuple[float, float]]:
        footprints = self.survey.footprints()
        return [t for t in self.tileGrid() if not self._isCoveredBy(t, footprints)]

    def nextTile(self) -> tuple[float, float] | None:
        """The next tile center not yet covered, or None when all are.

        Reports only: the caller records a tile once it has actually
        imaged it, so a tile abandoned by a stop is not silently skipped on the
        next run.
        """
        footprints = self.survey.footprints()
        for tile in self.tileGrid():
            if not self._isCoveredBy(tile, footprints):
                return tile
        return None

    def resetCoverage(self) -> None:
        """Forget which tiles have been imaged by superseding every record; the
        records stay on disk as data."""
        self.survey.supersede(lambda record: True)

    def forceRescan(self, position, isAttempted) -> int:
        """Re-open the region(s) around `position` for imaging. Returns the number of tile records superseded.

        The response to the tracker losing a cell: the coordinates around it are
        no longer trustworthy, so the records covering that ground are
        superseded, and the cells found there have to be
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
        handed out at their old positions -- near enough, since the motion is
        small -- so they keep counting toward the density cap and the rescan is
        less likely to resurface a cell already worked. Never-attempted cells are
        dropped so their tiles can come back uncrowded and be found again where
        they now are. The predicate is a parameter because attempted-ness is
        orchestration state held by the UI, not something a slice can know.

        A position inside no region frees nothing: no region's tiles cover it,
        so there is no coverage to invalidate.

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

        def isStale(record):
            center = tuple(record.header["tile_center"])
            fov = tuple(record.header.get("fov", self._fov))
            return any(r.overlapsTile(center, fov) for r in here)

        stale = [r for r in self.survey.tiles() if not r.superseded and isStale(r)]
        staleIds = {id(r) for r in stale}
        staleFootprints = [
            footprint(r.header["tile_center"], r.header.get("fov", self._fov))
            for r in stale
        ]
        for cell in self.survey.handedOut():
            inside = any(
                x0 <= cell.position[0] <= x1 and y0 <= cell.position[1] <= y1
                for x0, y0, x1, y1 in staleFootprints
            )
            if inside and not isAttempted(cell):
                self.survey.release(cell.candidate_id)
        return self.survey.supersede(lambda r: id(r) in staleIds)

    def surveyStats(self) -> tuple[int, int, float]:
        """(total tiles, covered tiles, percent covered) across every region."""
        return self._surveyStatsFor(self._regions, self.survey.footprints())

    def _surveyStatsFor(self, regions, footprints) -> tuple[int, int, float]:
        """surveyStats()'s body, over a region list and coverage the caller has
        already bound -- see _tileGridFor for why that split exists."""
        grid = self._tileGridFor(regions)
        total = len(grid)
        n = sum(1 for t in grid if self._isCoveredBy(t, footprints))
        percent = 100.0 * n / total if total else 0.0
        return total, n, percent

    def tileVolume(self) -> float:
        """The volume one tile searches: FOV area times the constrained depth span."""
        fov_w, fov_h = self._fov
        return fov_w * fov_h * self._constraints.z_span()

    # ---- the record on disk ----
    def snapshotState(self) -> dict | None:
        """Capture everything saveState() would write, as one plain-data dict
        with no reference back into this Slice.

        The split from writeSnapshot() below exists for a caller that must not
        read this Slice from anywhere but the thread it is being mutated on --
        AutopatchWindow._flushSliceState captures a snapshot here on the GUI
        thread and hands it to a worker thread to write, so the worker never
        touches self._regions/self.survey/self._constraints, only the plain
        data already pulled out of them. Every region is already to_dict()'d
        and every coordinate already float()'d for exactly that reason: a
        setRegions() or a tile record landing on the GUI thread after this
        returns must not be able to reach into a snapshot already handed off.

        Returns None for a slice with no directory, matching saveState()'s own
        no-op in that case -- there is nothing for writeSnapshot() to do with a
        directory-less snapshot, so there is no reason to build one.
        """
        dirHandle = self.dirHandle
        if dirHandle is None:
            return None
        # Bound once each, and everything below derived from these bindings:
        # the GUI thread can swap the whole region list while the worker thread
        # is covering tiles, and a record whose outlines and whose tile counts
        # came from two different readings describes a slice that never
        # existed. The same discipline setRegions() and tileGrid() keep.
        regions = self._regions
        footprints = self.survey.footprints()
        constraints = self._constraints
        total, nCovered, percent = self._surveyStatsFor(regions, footprints)
        # float()/bool() throughout, because these coordinates arrive from a
        # camera's boundary and a numpy-backed tiler, and a numpy scalar left
        # in the payload is written as a tagged Python object that no plain
        # YAML reader can load back. The conversion is exact.
        return {
            "dirHandle": dirHandle,
            "regions": [region.to_dict() for region in regions],
            "state": {
                "fov": [float(v) for v in self._fov],
                "overlap": float(self._overlap),
                "constraints": {
                    "depth_range": [float(v) for v in constraints.depth_range],
                    "min_health": float(constraints.min_health),
                    "min_cell_spacing": float(constraints.min_cell_spacing),
                    "rescans_allowed": bool(constraints.rescans_allowed),
                    "min_volume_m3": float(constraints.min_volume_m3),
                    "step_z": float(constraints.step_z),
                },
                "survey": {
                    "total_tiles": int(total),
                    "covered_tiles": int(nCovered),
                    "percent_covered": float(percent),
                },
            },
            "info": {
                "n_regions": len(regions),
                "percent_covered": float(percent),
                "min_health": float(constraints.min_health),
                "depth_range": [float(v) for v in constraints.depth_range],
            },
        }

    @staticmethod
    def writeSnapshot(snapshot: dict) -> None:
        """Write a snapshot captured by snapshotState() into its directory.

        A staticmethod, not an instance method: it must not touch a live
        Slice at all, only the plain data already sitting in `snapshot` and
        the DirHandle inside it (DirHandle's own writes are safe to call from
        any thread, the same way the orchestrator already calls them from its
        worker thread to save cell data). That is what lets a caller build the
        snapshot on the GUI thread and have this run -- possibly later,
        possibly on another thread entirely -- without a second thread ever
        touching this Slice's mutable state.

        Nothing raises out of here. Every caller is either a GUI slot that has
        already committed the operator's edit by the time it asks for a save,
        a worker thread writing a snapshot handed to it, or New slice partway
        through discarding the slice being saved -- and in all three, a raise
        costs far more than the file it failed to write. Each section is
        guarded separately so that a failure specific to one does not take the
        others with it, and the regions go first because they are the
        irreplaceable half of the search state: coverage and constraints can be
        re-derived from a rerun, while an outline traced around a piece of
        tissue cannot.

        Each section is written only when the snapshot carries it, so a
        snapshot of the pinned frames alone (see writePinnedFrames) leaves the
        search state as it is, and one without them leaves the frames alone.

        The summary put on the directory index rides with the search state
        rather than being guarded on its own, because it is the same numbers
        said twice: small scalars only, since the index is written with repr()
        and read back with eval() (a region or an array put there would be
        written and never read).
        """
        dirHandle = snapshot["dirHandle"]
        if "regions" in snapshot:
            try:
                dirHandle.writeFile(snapshot["regions"], REGIONS_FILE, fileType="YamlFile")
            except Exception:
                logger.exception("Could not write this slice's search regions")
        if "state" in snapshot:
            try:
                dirHandle.writeFile(snapshot["state"], SEARCH_STATE_FILE, fileType="YamlFile")
                dirHandle.setInfo(**snapshot["info"])
            except Exception:
                logger.exception("Could not write this slice's search state")
        if "pinnedFrames" in snapshot:
            try:
                writePinnedFrames(dirHandle, snapshot["pinnedFrames"])
            except Exception:
                logger.exception("Could not write this slice's pinned frames")
        if "protocolState" in snapshot:
            try:
                dirHandle.writeFile(
                    snapshot["protocolState"], PROTOCOL_STATE_FILE, fileType="YamlFile"
                )
            except Exception:
                logger.exception("Could not write this slice's protocol state")

    def saveState(self) -> None:
        """Write this slice's search state into its own data directory.

        What goes down is everything a slice knows that nothing else records:
        the regions the operator traced by hand, the field of view and overlap
        the tiles were planned at, the search constraints, which tiles have
        been imaged, and the survey those imply. The per-cell directories
        underneath already hold what was found; this is the shape of the search
        that found it, and until now it existed only in RAM and died with the
        next New slice.

        A slice with no directory writes nothing and says nothing about it.
        That is the "Add region here" slice, which came into existence to hold
        a region rather than by way of New slice (see `dirHandle`), and it
        honestly has nowhere to write.

        snapshotState() immediately followed by writeSnapshot() -- see either
        for the split's own reason. This is the synchronous, same-thread
        convenience the rest of this Slice's callers use; a caller that must
        write off-thread (see AutopatchWindow._flushSliceState) calls the two
        halves itself instead.
        """
        snapshot = self.snapshotState()
        if snapshot is not None:
            Slice.writeSnapshot(snapshot)

    def loadState(self) -> bool:
        """Restore the search state saved into this slice's data directory, and
        rebuild its survey -- coverage, upcoming picks and the cells already
        attempted -- from the tile records, manual file and Cell dirs there.

        Reports whether there was a record to read at all, so a caller can tell
        a slice directory written before this existed -- or one whose save
        failed -- from a slice that genuinely had no regions.

        The one thing deliberately not restored is the field of view. That
        belongs to the camera mounted now, not to whichever one was mounted
        when the record was written, and a slice built for a 130 um field must
        not silently start planning a 200 um one because a file said so. It is
        written down all the same: the survey's tile records are
        footprints, and knowing the field they were planned at is what makes
        them interpretable at all.

        Unlike saveState(), this does raise. A save is a side benefit of doing
        something else and must not take that something else down with it,
        while a load is the operator asking for these regions specifically, and
        quietly handing back a slice with the wrong outlines -- or none -- is
        exactly the failure the whole record exists to prevent. In particular
        setRegions()'s tile cap is checked against the *current* field of view,
        so a record saved at a wider field can legitimately be refused here;
        the partial state applied before that point is left in place, since a
        refused region list is precisely the state the operator has to see.
        Survey records are the exception: each bad one is logged and skipped,
        because a resumed slice with one unreadable tile record is still worth
        resuming.
        """
        dirHandle = self.dirHandle
        if dirHandle is None:
            return False
        found = False
        # Search parameters before regions, because setRegions() checks its
        # tile cap against the overlap: reading them in the other order would
        # measure a saved region against a fresh slice's overlap rather than
        # the one it was planned at.
        if dirHandle.exists(SEARCH_STATE_FILE):
            found = True
            state = dirHandle[SEARCH_STATE_FILE].read()
            self._overlap = state["overlap"]
            constraints = state["constraints"]
            self._constraints = SearchConstraints(
                depth_range=tuple(constraints["depth_range"]),
                min_health=constraints["min_health"],
                rescans_allowed=constraints["rescans_allowed"],
                # .get() with the library defaults, not a migration: a record
                # written before these existed simply lacks the keys, and a
                # slice loaded from one gets the same defaults it would have
                # gotten unconfigured.
                min_volume_m3=constraints.get("min_volume_m3", 0.0),
                step_z=constraints.get("step_z", 1e-6),
                min_cell_spacing=constraints.get(
                    "min_cell_spacing", SearchConstraints.min_cell_spacing
                ),
            )
            if "max_cell_density" in constraints:
                logger.info(
                    "Search record has a max_cell_density of %s; ignoring it and "
                    "using the default min_cell_spacing of %s",
                    constraints["max_cell_density"],
                    self._constraints.min_cell_spacing,
                )
            if state.get("covered"):
                logger.info(
                    "Search record lists %d covered tile centres; ignoring them, "
                    "since coverage now comes from the tile records",
                    len(state["covered"]),
                )
        if dirHandle.exists(REGIONS_FILE):
            found = True
            self.setRegions(
                [region_from_dict(d) for d in dirHandle[REGIONS_FILE].read()]
            )
        self.survey.load(dirHandle)
        if self.survey.tiles() or self.survey.handedOut():
            found = True
        return found

    # ---- cells found in this tissue ----
    def cellsNearTile(self, center: tuple[float, float]) -> list:
        """Handed-out cells whose position falls within `center`'s tile."""
        cx, cy = center
        fov_w, fov_h = self._fov
        found = []
        for cell in self.survey.handedOut():
            pos = cell.position
            if abs(pos[0] - cx) <= fov_w / 2 and abs(pos[1] - cy) <= fov_h / 2:
                found.append(cell)
        return found

    def cellsWithin(self, position, radius) -> list:
        """Handed-out cells whose centre is closer than `radius` to `position`, in 3D."""
        return [c for c in self.survey.handedOut() if cellDistance(c.position, position) < radius]

    # ---- cell producers ----
    def makeCellProducer(self, detector=None) -> "CellProducer":
        """A producer that surveys this slice, handing out at most one cell per call.

        This slice keeps no reference to what it hands back. The producer holds
        the slice, the orchestrator holds the producer, and that one-way chain
        is refcount-freeable; storing producers here would close it into a cycle
        only the cyclic GC could reclaim.
        """
        from .cell_producer import CellProducer

        return CellProducer(self, detector)
