"""CellProducer: the callable the orchestrator's refill hook takes, handing out the
slice survey's best cell per call and imaging a tile only when none is left to pick."""

from __future__ import annotations

from acq4.experiment.slice import cellDistance
from acq4.experiment.survey import Pick, TileRecord
from acq4.experiment.survey_record import (
    DETECTIONS_SUFFIX,
    detectionEntry,
    tileSaveTarget,
    writeRecord,
)
from acq4.logging_config import get_logger
from acq4.util.task import Stopped

__all__ = ["CellProducer"]

logger = get_logger(__name__)

QUEUED = "queued"
UNHEALTHY = "unhealthy"
OUT_OF_REGION = "out_of_region"
TOO_CLOSE = "too_close"


class CellProducer:
    """Hands out at most one cell per call, chosen by the slice's survey.

    Satisfies the orchestrator's producer contract: a call returns either a
    sequence of cells -- possibly empty, meaning "imaged a tile, found nothing
    usable there, ask again" -- or None, meaning "nothing is left to hand out
    or image, never ask again". The distinction is load-bearing: an empty field
    of view is the common case, and reporting it as exhaustion would end a run
    on the first barren tile.

    A call first asks the survey for a cell it already knows of. Only when
    there is none does it image one tile, and then it hands out that tile's
    best cell, if any. The detector is optional: with none, the producer hands
    out only manual entries.

    A producer is a **view onto** its slice, not an owner of it. The survey,
    regions, and constraints all live on the slice and are shared with every
    other producer made from it, so a producer built for a second run sees the
    tiles the first run imaged. The slice does not hold a reference back (see
    Slice.makeCellProducer).

    `detector(center, constraints)` is the injected imaging seam: it moves to
    `center`, finds the surface, acquires a stack across the constrained depth
    range, and returns detections exposing `.position` (global metres) and
    `.score` (the health prediction). Keeping it injected is what lets the tile
    walk and the constraint filtering be tested without a microscope.

    `rescans_allowed` grants exactly one extra pass over the slice's tiles, not
    unlimited rescanning: a producer that could always find another tile would
    never return None, and the orchestrator's refill loop would never end.

    """

    def __init__(self, slice_, detector=None):
        self._slice = slice_
        self._detector = detector
        # Whether this producer has already spent its one rescan pass. Per
        # producer, not per slice: the allowance mirrors the orchestrator's
        # per-run _producerExhausted, so a later run over the same slice may
        # rescan again.
        self._rescanned = False

    def __call__(self) -> list | None:
        while True:
            cell = self._pick()
            if cell is not None:
                return [cell]
            if self._detector is None:
                return None
            tile = self._nextTile()
            if tile is None:
                return None
            constraints = self._slice.constraints
            if self._isCrowded(tile, constraints):
                # Nothing is imaged: the density cap exists to spend imaging time elsewhere.
                logger.info("Skipping tile %r: already at the cell-density cap", tile)
                self._record(tile, [], constraints, skipped="crowded")
                continue
            try:
                candidates = self._detector(tile, constraints)
            except Stopped:
                # Only a cooperative stop is guaranteed to leave nothing half-done,
                # so it alone leaves the tile unrecorded.
                logger.info("Stopped while imaging tile %r; leaving it uncovered", tile)
                raise
            except BaseException as exc:
                # Recorded so a reused producer never wedges on a bad tile.
                self._record(tile, [], constraints, failed=str(exc) or type(exc).__name__)
                raise
            self._record(tile, candidates, constraints)
            cell = self._pick()
            return [] if cell is None else [cell]

    def _pick(self):
        survey = self._slice.survey
        choice = survey.next(self._slice.constraints, self._slice.containsPoint)
        return survey.handOut(choice.entry) if isinstance(choice, Pick) else None

    def _record(self, tile, candidates, constraints, skipped=None, failed=None) -> None:
        header = dict(getattr(candidates, "header", None) or {})
        header.setdefault("tile_center", [float(tile[0]), float(tile[1])])
        header["fov"] = [float(v) for v in self._slice.fov]
        if skipped:
            header["skipped"] = skipped
        if failed:
            header["failed"] = failed
        recordDir = getattr(candidates, "recordDir", None)
        recordName = getattr(candidates, "recordName", None)
        if recordDir is None and (skipped or failed):
            recordDir, base = tileSaveTarget(self._slice.dirHandle)
            recordName = None if base is None else f"{base}{DETECTIONS_SUFFIX}"
        detections = tuple(self._triage(candidates, constraints))
        writeRecord(recordDir, recordName, {**header, "detections": list(detections)})
        self._slice.survey.addTile(TileRecord(header, detections, recordDir, recordName))

    def _triage(self, candidates, constraints) -> list:
        """The record entry for every candidate, in detection order. A candidate
        whose fields can't be read or recorded is logged and dropped before it
        can take a spacing slot.

        The verdict is made at survey time and is informational: the survey's
        own selector decides what is handed out.
        """
        # Health and region before spacing: a cell outside the region or below
        # the cutoff must not crowd out a usable neighbour as "too close".
        kept = []
        entries = []
        for candidate in candidates:
            try:
                disposition = self._disposition(candidate, kept, constraints)
                entry = detectionEntry(candidate, disposition)
            except (TypeError, ValueError, IndexError, AttributeError):
                logger.exception("Dropping a detection that could not be triaged: %r", candidate)
                continue
            if disposition == QUEUED:
                kept.append(candidate)
            entries.append(entry)
        return entries

    def _disposition(self, candidate, kept, constraints) -> str:
        if not self._isHealthy(candidate, constraints):
            return UNHEALTHY
        if not self._isInRegion(candidate):
            return OUT_OF_REGION
        if self._isTooClose(candidate, kept, constraints):
            return TOO_CLOSE
        return QUEUED

    def _isTooClose(self, candidate, kept, constraints) -> bool:
        """Whether `candidate` is within the spacing of a handed-out cell or of a
        better candidate already kept from this tile."""
        radius = constraints.min_cell_spacing
        if self._slice.cellsWithin(candidate.position, radius):
            return True
        return any(cellDistance(candidate.position, k.position) < radius for k in kept)

    def _nextTile(self):
        """The next tile to image, spending the rescan allowance if needed."""
        tile = self._slice.nextTile()
        if tile is not None:
            return tile
        if not self._slice.constraints.rescans_allowed or self._rescanned:
            return None
        # One extra pass, and only one: an unbounded rescan loop could never
        # return None, and the orchestrator's refill loop would never end.
        self._rescanned = True
        self._slice.resetCoverage()
        logger.info("Rescanning: every tile was covered and rescans are allowed")
        return self._slice.nextTile()

    @staticmethod
    def _isHealthy(candidate, constraints) -> bool:
        """Whether `candidate` clears the health cutoff.

        An unscored candidate passes: a detector that does not score its output
        must not have its cells silently discarded by a cutoff they were never
        measured against.
        """
        score = getattr(candidate, "score", None)
        return score is None or score >= constraints.min_health

    def _isInRegion(self, candidate) -> bool:
        """Whether `candidate` lies inside the tissue the operator outlined.

        Delegated to the slice, which answers True for every point when no
        region has been drawn.
        """
        return self._slice.containsPoint(candidate.position)

    def _isCrowded(self, tile, constraints) -> bool:
        """Whether `tile` already holds cells at or above the density cap."""
        density = len(self._slice.cellsNearTile(tile)) / self._slice.tileVolume()
        return density >= constraints.max_cell_density
