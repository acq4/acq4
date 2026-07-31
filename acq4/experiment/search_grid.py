"""Serpentine field-of-view tiling over a rectangular search region, and
tracking which of those tiles have already been imaged."""

from __future__ import annotations

import math


def _axis_centers(lo: float, hi: float, fov: float, overlap: float) -> list[float]:
    """Tile centers along one axis whose union covers [lo, hi].

    Step between tiles is ``fov - overlap``; the tile count is the smallest that
    spans the extent, and the tiles are centered over it so the union fully
    covers [lo, hi] (the outermost tiles may extend past the edges).
    """
    extent = hi - lo
    step = fov - overlap
    if step <= 0:
        # Degrade gracefully if the overlap swallows the whole FOV.
        step = fov
    if extent <= fov:
        return [(lo + hi) / 2.0]
    n = math.ceil((extent - fov) / step) + 1
    covered = fov + (n - 1) * step
    extra = covered - extent
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
