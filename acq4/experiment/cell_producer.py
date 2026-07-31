"""CellProducer: the callable the orchestrator's refill hook takes, surveying one
tile of a slice per call and returning the cells found there."""

from __future__ import annotations

from acq4.logging_config import get_logger

logger = get_logger(__name__)


class CellProducer:
    """Images one tile of a slice per call and returns the cells found in it.

    Satisfies the orchestrator's producer contract: a call returns either a
    sequence of cells -- possibly empty, meaning "imaged a tile, found nothing
    there, ask again" -- or None, meaning "every tile is imaged, never ask
    again". The distinction is load-bearing: an empty field of view is the
    common case, and reporting it as exhaustion would end a run on the first
    barren tile.

    A producer is a **view onto** its slice, not an owner of it. Coverage,
    regions, and constraints all live on the slice and are shared with every
    other producer made from it, so a producer built for a second run sees the
    coverage the first run accumulated. The slice does not hold a reference
    back (see Slice.makeCellProducer).

    `detector(center, constraints)` is the injected imaging seam: it moves to
    `center`, finds the surface, acquires a stack across the constrained depth
    range, and returns candidate objects exposing `.position` (global metres)
    and `.score` (the health prediction). Keeping it injected is what lets the
    tile walk and the constraint filtering be tested without a microscope.

    `rescans_allowed` grants exactly one extra pass over the slice's tiles, not
    unlimited rescanning: a producer that could always find another tile would
    never return None, and the orchestrator's refill loop would never end.
    """

    def __init__(self, slice_, detector):
        self._slice = slice_
        self._detector = detector
        # Whether this producer has already spent its one rescan pass. Per
        # producer, not per slice: the allowance mirrors the orchestrator's
        # per-run _producerExhausted, so a later run over the same slice may
        # rescan again.
        self._rescanned = False

    def __call__(self) -> list | None:
        tile = self._nextTile()
        if tile is None:
            return None
        constraints = self._slice.constraints
        if self._isCrowded(tile, constraints):
            # Nothing is imaged: the point of the density cap is to spend the
            # imaging time elsewhere. Still marked covered, or this tile is
            # handed out again on every call.
            self._slice.markCovered(tile)
            logger.info("Skipping tile %r: already at the cell-density cap", tile)
            return []
        try:
            candidates = self._detector(tile, constraints)
        finally:
            # Marked whether or not imaging succeeded: a tile that raises must
            # not be handed out again, or a producer reused across runs wedges
            # on the same bad tile forever.
            self._slice.markCovered(tile)
        cells = [c for c in candidates if self._isHealthy(c, constraints)]
        self._slice.registerCells(cells)
        return cells

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

        An unscored candidate passes: a detector that does not score its output,
        or a cell seeded by hand, must not be silently discarded by a cutoff it
        was never measured against.
        """
        score = getattr(candidate, "score", None)
        return score is None or score >= constraints.min_health

    def _isCrowded(self, tile, constraints) -> bool:
        """Whether `tile` already holds cells at or above the density cap."""
        density = len(self._slice.cellsNearTile(tile)) / self._slice.tileVolume()
        return density >= constraints.max_cell_density
