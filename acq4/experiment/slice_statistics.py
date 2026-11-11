"""The slice-level seal statistics the early-exit rule compares against, read
back off the outcome records the patch drives leave on a slice's cell
directories."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from statistics import median

from acq4.logging_config import get_logger

logger = get_logger(__name__)

# How many driven cells a slice needs before its own numbers are trusted over the
# configured defaults. Below this the estimates are dominated by sampling noise,
# and a slice that yields fifteen attempts would spend most of itself being
# governed by its first two.
DEFAULT_MIN_CELLS = 5


@dataclass(frozen=True)
class SealTerms:
    """Everything the stopping rule needs about a slice, in seconds and
    probabilities. Plain floats throughout, because these are pinned onto a patch
    profile as parameters and a profile parameter is a scalar.

    `measured` says whether these came from the slice's own cells or from the
    configured defaults -- the rule does not care, but an operator reading why a
    cell was abandoned does.
    """

    restart_cost: float = 0.0
    seal_probability: float = 0.0
    expected_seal_duration: float = 0.0
    expected_failed_seal_duration: float = 0.0
    probability_decay_tau: float = 0.0
    expected_quality: float = 0.0
    n_cells: int = 0
    measured: bool = False


def _finite(value) -> float | None:
    """`value` as a float, or None if it is missing or not a finite number."""
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def cell_quality(info) -> float | None:
    """The recording quality of the cell whose index this is, as input resistance
    over access resistance -- the standard figure of merit for a whole-cell
    recording, higher being better.

    None when the cell has no recording to judge. Deliberately not zero: an
    unmeasured cell is not a bad cell, and the two must not be averaged together.
    """
    input_resistance = _finite(info.get("input_resistance"))
    access_resistance = _finite(info.get("access_resistance"))
    if input_resistance is None or access_resistance is None:
        return None
    if access_resistance <= 0:
        return None
    return input_resistance / access_resistance


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _restart_cost(episodes) -> float | None:
    """The typical overhead between one seal episode ending and the next
    beginning: clean, approach, detection, and any attempt in between that never
    reached seal at all.

    That last part is why this is measured as a gap rather than assembled from
    per-state timings -- a wasted approach between two seals sits inside the gap
    and needs no term of its own. This is the "amortized discovery time" the rule
    charges against giving up.

    A median rather than a mean, because an operator's lunch break is also a gap
    between two seal episodes, and one of those would otherwise swamp a whole
    slice's estimate. Negative gaps are dropped: two pipettes sealing
    concurrently interleave their episodes, and an overlap is not a negative
    overhead.
    """
    chain = sorted(
        (e for e in episodes if _finite(e.get("seal_duration_s")) is not None),
        key=lambda e: _finite(e.get("seal_entered_at")),
    )
    gaps = []
    for previous, following in zip(chain, chain[1:]):
        gap = _finite(following["seal_entered_at"]) - (
            _finite(previous["seal_entered_at"]) + _finite(previous["seal_duration_s"])
        )
        if gap >= 0:
            gaps.append(gap)
    return median(gaps) if gaps else None


def seal_terms_from_records(records, defaults, min_cells=DEFAULT_MIN_CELLS) -> SealTerms:
    """The slice's seal terms, from the outcome records of the cells it has driven.

    Falls back to `defaults` wholesale below `min_cells`, and per-term above it
    for any term this slice has not produced evidence for. A term is never
    invented: an absent measurement takes the configured number rather than a
    zero, because a zero here is a claim about the slice rather than an admission
    of ignorance.

    A *measured* seal probability of zero is kept, though. A slice that has
    sealed nothing is information: it makes the expected time to the next seal
    infinite, and the rule correctly stops abandoning cells, there being nothing
    better to go to.
    """
    attempts = [r for r in records if r.get("patch_outcome")]
    n_cells = len(attempts)
    if n_cells < min_cells:
        return replace(defaults, n_cells=n_cells, measured=False)

    episodes = [r for r in attempts if _finite(r.get("seal_entered_at")) is not None]
    sealed = [e for e in episodes if e.get("sealed")]
    failed = [e for e in episodes if not e.get("sealed")]

    probability = len(sealed) / len(episodes) if episodes else None
    seal_duration = _mean(_finite(e.get("seal_duration_s")) for e in sealed)
    failed_duration = _mean(_finite(e.get("seal_duration_s")) for e in failed)
    restart_cost = _restart_cost(episodes)
    quality = _mean(cell_quality(r) for r in attempts)

    return SealTerms(
        restart_cost=defaults.restart_cost if restart_cost is None else restart_cost,
        seal_probability=(
            defaults.seal_probability if probability is None else probability
        ),
        expected_seal_duration=(
            defaults.expected_seal_duration if seal_duration is None else seal_duration
        ),
        expected_failed_seal_duration=(
            defaults.expected_failed_seal_duration
            if failed_duration is None
            else failed_duration
        ),
        # Never measured here: fitting a survival curve is the offline
        # calibration pass's job, and the rig only ever carries its result.
        probability_decay_tau=defaults.probability_decay_tau,
        expected_quality=defaults.expected_quality if quality is None else quality,
        n_cells=n_cells,
        measured=True,
    )


class SliceStatistics:
    """Reads a slice's cell directories and reports what the early-exit rule needs.

    Holds no state beyond its configuration: every call re-reads the directory, so
    a slice that gained a cell since the last patch is reflected without anything
    having to invalidate a cache.

    Nothing raises out of here. These numbers only ever tune a timeout, and a
    slice whose index cannot be read should fall back to the configured defaults
    rather than stop a run.
    """

    def __init__(self, dirHandle=None, defaults=None, min_cells=DEFAULT_MIN_CELLS):
        self.dirHandle = dirHandle
        self.defaults = defaults if defaults is not None else SealTerms()
        self.min_cells = min_cells

    def records(self) -> list[dict]:
        """The index of every Cell directory under this slice."""
        if self.dirHandle is None:
            return []
        try:
            names = self.dirHandle.ls()
        except Exception:
            logger.exception("Could not list this slice's cell directories")
            return []
        records = []
        for name in names:
            # Guarded per child: one unreadable directory must not blind the rule
            # to the rest of the slice.
            try:
                handle = self.dirHandle[name]
                if not handle.isDir():
                    continue
                info = handle.info()
            except Exception:
                logger.exception("Could not read the index of %r", name)
                continue
            if (info or {}).get("dirType") != "Cell":
                continue
            records.append(dict(info))
        return records

    def sealTerms(self) -> SealTerms:
        return seal_terms_from_records(self.records(), self.defaults, self.min_cells)

    def prizeValue(self, info, terms: SealTerms) -> float:
        """What a nucleus from this cell is worth relative to one from a fresh cell.

        Relative, not absolute, and that is the whole point: on a uniformly sick
        slice this lands at 1 and the rule correctly stops discriminating, because
        the replacement is no better than what it is being compared against.

        1.0 whenever there is nothing to compare -- no measurement on this cell,
        or no slice average yet. An unmeasured cell must not be discounted.
        """
        quality = cell_quality(info or {})
        if quality is None or terms.expected_quality <= 0:
            return 1.0
        return quality / terms.expected_quality
