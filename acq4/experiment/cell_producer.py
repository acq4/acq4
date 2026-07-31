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
    """

    def __init__(self, slice_, detector):
        self._slice = slice_
        self._detector = detector

    def __call__(self) -> list | None:
        tile = self._slice.nextTile()
        if tile is None:
            return None
        try:
            candidates = self._detector(tile, self._slice.constraints)
        finally:
            # Marked whether or not imaging succeeded: a tile that raises must
            # not be handed out again, or a producer reused across runs wedges
            # on the same bad tile forever.
            self._slice.markCovered(tile)
        cells = list(candidates)
        self._slice.registerCells(cells)
        return cells
