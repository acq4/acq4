"""Serpentine field-of-view tiling over a rectangular search region, and
tracking which of those tiles have already been imaged."""

from __future__ import annotations

import math


def _axis_step(fov: float, overlap: float) -> float:
    """The distance between adjacent tile centers along one axis."""
    step = fov - overlap
    if step <= 0:
        # Degrade gracefully if the overlap swallows the whole FOV.
        step = fov
    return step


def _axis_count(lo: float, hi: float, fov: float, overlap: float) -> int:
    """How many tiles along one axis it takes to cover [lo, hi].

    Step between tiles is ``fov - overlap``, and the count is the smallest that
    spans the extent.

    ``extent`` is computed as ``hi - lo``, and ``lo``/``hi`` may be as large as a
    stage's absolute travel range while ``fov``/``step`` are tiny by comparison,
    so that subtraction carries rounding error proportional to the magnitude of
    ``lo``/``hi`` rather than of the extent itself. A tolerance scaled to the
    largest quantity involved (divided by ``step`` to put it in the same units
    as the tile-count ratio) absorbs that error so a ratio that is only a
    rounding error away from an integer is treated as that integer instead of
    being rounded up to one more tile.
    """
    extent = hi - lo
    step = _axis_step(fov, overlap)
    scale = max(abs(lo), abs(hi), fov, step)
    length_tol = scale * 1e-9
    if extent <= fov + length_tol:
        return 1
    ratio = (extent - fov) / step
    ratio_tol = length_tol / step
    rounded_ratio = round(ratio)
    if abs(ratio - rounded_ratio) <= ratio_tol:
        return int(rounded_ratio) + 1
    return math.ceil(ratio) + 1


def _axis_centers(lo: float, hi: float, fov: float, overlap: float) -> list[float]:
    """Tile centers along one axis whose union covers [lo, hi].

    The tiles are centered over the extent so their union fully covers [lo, hi]
    (the outermost tiles may extend past the edges). A single tile at the
    midpoint covers an extent no larger than one FOV.
    """
    n = _axis_count(lo, hi, fov, overlap)
    if n == 1:
        return [(lo + hi) / 2.0]
    step = _axis_step(fov, overlap)
    covered = fov + (n - 1) * step
    extra = covered - (hi - lo)
    start = lo + fov / 2.0 - extra / 2.0
    return [start + i * step for i in range(n)]


def plan_grid(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fov_w: float,
    fov_h: float,
    overlap: float,
) -> list[tuple[float, float]]:
    """Serpentine-ordered tile centers whose union fully covers the rectangle.

    The step between adjacent tiles is ``fov - overlap`` (an absolute distance).
    The grid is centered over the rectangle so no part of it is left uncovered;
    the outermost tiles may extend past the edges. A single tile at the rect
    center is returned when the rect is smaller than one FOV. Rows alternate
    direction (boustrophedon) to minimize stage travel.
    """
    xs = _axis_centers(min(x0, x1), max(x0, x1), fov_w, overlap)
    ys = _axis_centers(min(y0, y1), max(y0, y1), fov_h, overlap)
    grid: list[tuple[float, float]] = []
    for j, cy in enumerate(ys):
        row = xs if j % 2 == 0 else list(reversed(xs))
        for cx in row:
            grid.append((cx, cy))
    return grid


def count_grid(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fov_w: float,
    fov_h: float,
    overlap: float,
) -> int:
    """How many tiles ``plan_grid`` would return for this rectangle.

    Arithmetic, so a caller can find out how big a grid is before deciding
    whether to build it: ``plan_grid`` materialises every center, which is
    minutes of compute and a list to match once a rectangle is large enough
    relative to the field of view.

    Shares ``_axis_count`` with ``plan_grid`` rather than re-deriving the count,
    so the two cannot disagree about where a tolerance-sized extent falls.
    """
    return _axis_count(min(x0, x1), max(x0, x1), fov_w, overlap) * _axis_count(
        min(y0, y1), max(y0, y1), fov_h, overlap
    )


def _is_visited(
    cx: float,
    cy: float,
    visited: list[tuple[float, float]],
    threshold: float,
) -> bool:
    """Whether ``(cx, cy)`` lies within ``threshold`` of any visited center."""
    return any(math.hypot(cx - vx, cy - vy) < threshold for vx, vy in visited)


def select_next(
    grid: list[tuple[float, float]],
    visited: list[tuple[float, float]],
    threshold: float,
) -> tuple[float, float] | None:
    """First center in ``grid`` not within ``threshold`` of any visited center.

    Returns None when every planned tile has already been imaged.
    """
    for cx, cy in grid:
        if not _is_visited(cx, cy, visited, threshold):
            return (cx, cy)
    return None


def count_covered(
    grid: list[tuple[float, float]],
    visited: list[tuple[float, float]],
    threshold: float,
) -> int:
    """Number of centers in ``grid`` within ``threshold`` of some visited center."""
    return sum(1 for cx, cy in grid if _is_visited(cx, cy, visited, threshold))
