"""Field-of-view tiling over a rectangular search region -- serpentine rows, or a
spiral outward from the most interior tile -- and tracking which have been imaged."""

from __future__ import annotations

import math
from collections import deque


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


def _distance_from_outside(cells) -> dict:
    """How many lattice steps each of `cells` is from anything not in `cells`.

    A discrete distance transform, run as one breadth-first sweep inward from
    every cell that touches the outside. Off-lattice counts as outside for free,
    since a neighbour that was never a cell is simply not in the set -- so the
    edge of the plan and a hole the shape punched in it are the same kind of
    boundary, which is what makes this work on an L or a ring as readily as on a
    rectangle.

    Distance 1 means "on the boundary". Four-connected, which over a rectangle
    is exactly the number of tiles between a cell and the nearest edge.

    Linear in the number of cells: each is enqueued once, and each looks at four
    neighbours. `tileGrid()` is rebuilt on every `nextTile()` over as many as
    MAX_PLANNED_TILES cells, so anything worse than that would be felt between
    every pair of tiles a survey images.
    """
    inside = set(cells)
    neighbours = ((1, 0), (-1, 0), (0, 1), (0, -1))
    distance = {}
    queue = deque()
    for i, j in cells:
        if any((i + di, j + dj) not in inside for di, dj in neighbours):
            distance[(i, j)] = 1
            queue.append((i, j))
    while queue:
        i, j = queue.popleft()
        step = distance[(i, j)] + 1
        for di, dj in neighbours:
            nxt = (i + di, j + dj)
            if nxt in inside and nxt not in distance:
                distance[nxt] = step
                queue.append(nxt)
    return distance


def _seed_cell(cells) -> tuple[int, int]:
    """The cell to start a centre-out survey from: the most interior one.

    "Most interior" is the greatest distance from the outside, not the cell
    nearest a centroid. The two differ exactly where it matters: the centroid of
    an L, or of any region drawn around damaged tissue, can land in the notch --
    on ground the operator excluded -- and would seed the survey at whichever
    tile happened to be nearest that empty spot.

    Ties are broken toward the centroid and then by lattice position, which
    settles two different situations. A shape with no interior at all -- a band
    one tile wide, where every cell is on the boundary -- has every cell tied,
    and the centroid is then exactly the right answer: the middle of the band.
    A shape with an even-sized interior has a small plateau of equally deep
    cells, and the centroid picks the one nearest the middle of it. The final
    (j, i) is there so the answer never depends on set iteration order.
    """
    distance = _distance_from_outside(cells)
    cx = sum(i for i, _ in cells) / len(cells)
    cy = sum(j for _, j in cells) / len(cells)
    return min(
        cells,
        key=lambda c: (
            -distance[c],
            (c[0] - cx) ** 2 + (c[1] - cy) ** 2,
            c[1],
            c[0],
        ),
    )


def _ring_key(di: int, dj: int) -> tuple[int, int]:
    """Where `(di, dj)` falls in the spiral: its ring, and its place around it.

    The ring is the Chebyshev distance from the seed, so a ring is the square of
    cells exactly that far out and every cell of one ring is surveyed before any
    cell of the next. The second number walks that square's perimeter
    counter-clockwise from its bottom-right corner, as an exact integer rather
    than an angle: consecutive cells of a ring are then genuinely adjacent,
    which sorting by `atan2` does not guarantee near the corners, and there is
    no float to tie.

    Starting each ring at the corner just outside where the last one ended is
    what keeps the seam cheap: a ring ends one cell short of its own start, so
    stepping out to the next ring's corner is a two-tile move rather than a trip
    back across the whole surveyed area.

    The one place adjacency gives way is a ring the region only partly contains,
    where the surviving cells form two arcs -- a region much longer than it is
    wide reaches that state early, and crossing between the arcs costs one long
    move per ring. That is the price of "finish this ring before starting the
    next", which is the operator's first requirement; the alternative orderings
    that avoid the crossing all abandon it.
    """
    r = max(abs(di), abs(dj))
    if r == 0:
        return (0, 0)
    if di == r:
        step = dj + r  # up the right edge, from the bottom-right corner
    elif dj == r:
        step = 3 * r - di  # left along the top
    elif di == -r:
        step = 5 * r - dj  # down the left edge
    else:
        step = 7 * r + di  # right along the bottom, stopping short of the start
    return (r, step)


def plan_center_out(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fov_w: float,
    fov_h: float,
    overlap: float,
    keep=None,
) -> list[tuple[float, float]]:
    """The same tiles ``plan_grid`` plans, ordered outward from the middle.

    A survey ordered by rows starts at a corner, which is the worst ground on a
    slice: the edges are where the tissue is damaged, and a cell found there is
    the farthest from everything else the run will do. Starting at the most
    interior tile and spiralling out puts the healthiest tissue first, and means
    an operator who stops the run early has surveyed a compact area around the
    middle rather than a band along one side.

    ``keep(center)`` is the caller's shape filter, applied *before* the ordering
    rather than after it. It has to be: which tile is most interior, and which
    ring a tile falls in, are both properties of the set of tiles that survive
    the shape, so a filter applied afterwards would order a plan it no longer
    describes -- the middle of a bounding box is not the middle of the L inside
    it. Passing the filter in as a predicate is what keeps this function
    ignorant of shapes, exactly as ``plan_grid`` is.

    O(n log n) in the number of tiles, the sort dominating. Every other step is
    linear, which matters because ``Slice.tileGrid()`` rebuilds this on every
    ``nextTile()``.
    """
    xs = _axis_centers(min(x0, x1), max(x0, x1), fov_w, overlap)
    ys = _axis_centers(min(y0, y1), max(y0, y1), fov_h, overlap)
    # The lattice indices of the tiles that survive the shape. Ordering happens
    # on indices rather than on the centers themselves so that adjacency is
    # exact integer arithmetic, with no tolerance to choose: a stage coordinate
    # is metres from an origin that may be far away, and differences of tile
    # centers out there do not land on clean multiples of the step.
    cells = [
        (i, j)
        for j, cy in enumerate(ys)
        for i, cx in enumerate(xs)
        if keep is None or keep((cx, cy))
    ]
    if not cells:
        return []
    si, sj = _seed_cell(cells)
    cells.sort(key=lambda c: _ring_key(c[0] - si, c[1] - sj))
    return [(xs[i], ys[j]) for i, j in cells]


def count_grid(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    fov_w: float,
    fov_h: float,
    overlap: float,
) -> int:
    """How many tiles either planner would return for this rectangle.

    Arithmetic, so a caller can find out how big a grid is before deciding
    whether to build it: a planner materialises every center, which is minutes
    of compute and a list to match once a rectangle is large enough relative to
    the field of view. The two orderings plan the same tiles, so one count
    answers for both.

    Shares ``_axis_count`` with the planners rather than re-deriving the count,
    so they cannot disagree about where a tolerance-sized extent falls.
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
