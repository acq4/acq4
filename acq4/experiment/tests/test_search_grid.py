"""Tests for the search-region grid packing: FOV tiling that fully covers a
rectangle, the order the tiles are surveyed in, and choosing the next un-imaged one."""

import math
import time

import pytest

from acq4.experiment.search_grid import (
    _is_visited,
    count_covered,
    count_grid,
    plan_center_out,
    plan_grid,
    select_next,
)


def _covers(grid, x0, y0, x1, y1, fov_w, fov_h):
    """Whether every point of the rect lies inside at least one tile."""
    # Sample the rect densely enough to catch any gap smaller than a tile.
    nx = ny = 25
    for i in range(nx + 1):
        px = x0 + (x1 - x0) * i / nx
        for j in range(ny + 1):
            py = y0 + (y1 - y0) * j / ny
            inside = any(
                abs(px - cx) <= fov_w / 2 + 1e-12 and abs(py - cy) <= fov_h / 2 + 1e-12
                for cx, cy in grid
            )
            if not inside:
                return False
    return True


def test_single_tile_when_rect_smaller_than_fov():
    grid = plan_grid(10, 10, 60, 60, fov_w=100, fov_h=100, overlap=20)
    assert grid == [(35.0, 35.0)]


def test_tile_count_and_spacing_for_known_rect():
    grid = plan_grid(0, 0, 200, 200, fov_w=100, fov_h=100, overlap=20)
    # step = fov - overlap = 80; n = ceil((200-100)/80)+1 = 3 per axis.
    assert len(grid) == 9
    xs = sorted({round(cx, 6) for cx, _ in grid})
    ys = sorted({round(cy, 6) for _, cy in grid})
    assert xs == [20.0, 100.0, 180.0]
    assert ys == [20.0, 100.0, 180.0]


def test_serpentine_row_alternation():
    grid = plan_grid(0, 0, 200, 200, fov_w=100, fov_h=100, overlap=20)
    assert grid == [
        (20.0, 20.0), (100.0, 20.0), (180.0, 20.0),
        (180.0, 100.0), (100.0, 100.0), (20.0, 100.0),
        (20.0, 180.0), (100.0, 180.0), (180.0, 180.0),
    ]


def test_grid_fully_covers_non_multiple_rect():
    # Rect extents are not integer multiples of the step; coverage must still hold.
    x0, y0, x1, y1 = 0, 0, 250, 130
    grid = plan_grid(x0, y0, x1, y1, fov_w=100, fov_h=100, overlap=20)
    assert _covers(grid, x0, y0, x1, y1, 100, 100)


def test_grid_centered_over_rect():
    # Centers are symmetric about the rect center on each axis.
    grid = plan_grid(0, 0, 250, 130, fov_w=100, fov_h=100, overlap=20)
    xs = sorted({round(cx, 6) for cx, _ in grid})
    ys = sorted({round(cy, 6) for _, cy in grid})
    assert math.isclose((xs[0] + xs[-1]) / 2, 125.0)
    assert math.isclose((ys[0] + ys[-1]) / 2, 65.0)


def test_tile_count_stable_across_stage_offsets():
    # A 30um square needs exactly 9 tiles with a 10um FOV no matter where the
    # region sits on the stage, including at millimeter-scale offsets where
    # `hi - lo` picks up floating-point error.
    fov = 10e-6
    side = 30e-6
    for off in (0.0, 500e-6, 1e-3, 2e-3, 5e-3, 1e-2):
        x0, y0 = off, off
        x1, y1 = off + side, off + side
        grid = plan_grid(x0, y0, x1, y1, fov, fov, overlap=0.0)
        assert len(grid) == 9, off
        assert _covers(grid, x0, y0, x1, y1, fov, fov), off


def test_single_tile_when_rect_is_exactly_one_fov_at_stage_offset():
    # A rect exactly one FOV wide returns a single tile at the origin and also
    # at a millimeter-scale offset, where `hi - lo` picks up floating-point
    # error relative to the FOV.
    fov = 100e-6
    for off in (0.0, 1e-3):
        x0, y0 = off, off
        x1, y1 = off + fov, off + fov
        grid = plan_grid(x0, y0, x1, y1, fov, fov, overlap=0.0)
        assert len(grid) == 1, off
        assert grid == [((x0 + x1) / 2.0, (y0 + y1) / 2.0)]


def test_extra_tile_kept_when_genuinely_needed():
    # A rect a hair wider than an exact multiple of the step must still get
    # the extra tile: the excess here (10% of a step) is far larger than any
    # floating-point error but smaller than a full step, so it must not be
    # absorbed by the tolerance that protects against rounding error.
    fov, overlap = 100e-6, 20e-6
    step = fov - overlap
    excess = step * 0.1
    extent = fov + 2 * step + excess
    off = 1e-3
    x0, y0 = off, off
    x1, y1 = off + extent, off + extent
    grid = plan_grid(x0, y0, x1, y1, fov, fov, overlap)
    assert len(grid) == 16
    assert _covers(grid, x0, y0, x1, y1, fov, fov)


def test_tile_count_holds_at_a_coordinate_whose_magnitude_dwarfs_the_tile_geometry():
    # hi - lo carries rounding error proportional to the magnitude of lo/hi
    # themselves, not to the (much smaller) tile geometry, so at a large
    # enough coordinate that error outgrows a tolerance fixed to a bare
    # nanometre. The tolerance must scale with the coordinate to keep
    # absorbing it, which this offset is large enough to require.
    fov = 1e-3
    step = fov
    n_tiles = 50
    off = 4e7
    x0, y0 = off, off
    x1, y1 = off + fov + (n_tiles - 1) * step, off + fov
    grid = plan_grid(x0, y0, x1, y1, fov, fov, overlap=0.0)
    assert len(grid) == n_tiles


# Rectangles that between them exercise every branch of the axis tile count:
# smaller than one FOV, an exact multiple, a ragged remainder, an extent that is
# one FOV only to within float error at a realistic stage coordinate, and one
# large enough that building the tile list is the thing worth avoiding.
_COUNT_CASES = [
    (10.0, 10.0, 60.0, 60.0, 100.0, 100.0, 20.0),
    (0.0, 0.0, 200.0, 200.0, 100.0, 100.0, 20.0),
    (0.0, 0.0, 250.0, 130.0, 100.0, 100.0, 20.0),
    (1e-3, 2e-3, 1e-3 + 100e-6, 2e-3 + 50e-6, 100e-6, 50e-6, 0.0),
    (1.5e-3, -2.5e-3, 1.5e-3 + 3.1e-3, -2.5e-3 + 2.7e-3, 130.6e-6, 130.6e-6, 0.0),
]


@pytest.mark.parametrize("x0,y0,x1,y1,fov_w,fov_h,overlap", _COUNT_CASES)
def test_count_grid_matches_what_plan_grid_actually_produces(
    x0, y0, x1, y1, fov_w, fov_h, overlap
):
    # count_grid() exists so a caller can find out how big a grid would be
    # without building it, and it is worth nothing unless it is the same number.
    # Checked against plan_grid itself rather than against hand-computed counts,
    # which could drift from it.
    assert count_grid(x0, y0, x1, y1, fov_w, fov_h, overlap) == len(
        plan_grid(x0, y0, x1, y1, fov_w, fov_h, overlap)
    )


def test_count_grid_normalizes_its_corners_the_way_plan_grid_does():
    # An ROI resized past its own origin reports a negative size, so the corners
    # can arrive either way round.
    assert count_grid(200, 200, 0, 0, 100, 100, 20) == count_grid(
        0, 0, 200, 200, 100, 100, 20
    )


def test_is_visited_false_when_nothing_visited():
    assert _is_visited(0.0, 0.0, visited=[], threshold=1.0) is False


def test_is_visited_true_within_threshold():
    # A visited center a hair off the query point still counts as imaged.
    assert _is_visited(0.0, 0.0, visited=[(0.3, 0.0)], threshold=1.0) is True


def test_is_visited_false_outside_threshold():
    assert _is_visited(0.0, 0.0, visited=[(10.0, 0.0)], threshold=1.0) is False


def test_select_next_returns_first_when_nothing_visited():
    grid = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    assert select_next(grid, visited=[], threshold=1.0) == (0.0, 0.0)


def test_select_next_skips_visited():
    grid = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    assert select_next(grid, visited=[(0.0, 0.0)], threshold=1.0) == (10.0, 0.0)


def test_select_next_matches_within_threshold():
    grid = [(0.0, 0.0), (10.0, 0.0)]
    # A visited center a hair off the planned one still counts as imaged.
    assert select_next(grid, visited=[(0.3, 0.0)], threshold=1.0) == (10.0, 0.0)


def test_select_next_none_when_all_visited():
    grid = [(0.0, 0.0), (10.0, 0.0)]
    assert select_next(grid, visited=[(0.0, 0.0), (10.0, 0.0)], threshold=1.0) is None


def test_count_covered_none_when_nothing_visited():
    grid = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    assert count_covered(grid, visited=[], threshold=1.0) == 0


def test_count_covered_all_when_all_visited():
    grid = [(0.0, 0.0), (10.0, 0.0)]
    assert count_covered(grid, visited=[(0.0, 0.0), (10.0, 0.0)], threshold=1.0) == 2


def test_count_covered_partial_within_threshold():
    grid = [(0.0, 0.0), (10.0, 0.0), (20.0, 0.0)]
    # Visited centers a hair off two of the three planned tiles still count them.
    assert count_covered(grid, visited=[(0.2, 0.0), (19.8, 0.0)], threshold=1.0) == 2


# ---- centre-out ordering ----
# A survey starting at a corner spends its first hour on the edge of the tissue,
# where the slice is most damaged and where a cell lost to drift costs the whole
# journey back. Starting in the middle and working outward puts the best tissue
# first and keeps each tile next to ground already imaged.


def _lattice(grid, fov_w, fov_h):
    """`grid`'s centers as integer lattice indices, so tests can talk about
    adjacency without floating-point tile arithmetic."""
    xs = sorted({cx for cx, _ in grid})
    ys = sorted({cy for _, cy in grid})
    return [(xs.index(cx), ys.index(cy)) for cx, cy in grid]


def _chebyshev_steps(cells):
    """The lattice distance between each consecutive pair."""
    return [
        max(abs(bx - ax), abs(by - ay))
        for (ax, ay), (bx, by) in zip(cells, cells[1:])
    ]


def test_center_out_starts_at_the_middle_of_an_odd_grid():
    grid = plan_center_out(0, 0, 300, 300, fov_w=100, fov_h=100, overlap=0)
    assert len(grid) == 9
    assert grid[0] == (150.0, 150.0)


def test_center_out_covers_exactly_the_tiles_the_serpentine_plan_does():
    # Only the order changes. Coverage, the tile count surveyStats reports, and
    # the threshold select_next matches against all depend on the set being
    # identical to what plan_grid produces.
    args = (0, 0, 530, 370, 100, 100, 20)
    assert sorted(plan_center_out(*args)) == sorted(plan_grid(*args))


def test_center_out_finishes_each_ring_before_starting_the_next():
    # "Far from all edges first" is a statement about rings: every tile at
    # lattice distance 1 from the seed is imaged before any tile at distance 2,
    # so the surveyed area grows as a compact blob rather than a tendril.
    grid = plan_center_out(0, 0, 500, 500, fov_w=100, fov_h=100, overlap=0)
    cells = _lattice(grid, 100, 100)
    seed = cells[0]
    rings = [max(abs(cx - seed[0]), abs(cy - seed[1])) for cx, cy in cells]
    assert rings == sorted(rings)
    assert rings.count(0) == 1
    assert rings.count(1) == 8
    assert rings.count(2) == 16


def test_consecutive_tiles_stay_next_to_each_other():
    # The other half of the operator's request: each tile adjacent to the last
    # one surveyed. Within a ring that is exact, because the ring is walked
    # around its perimeter rather than by raw angle; the step from the end of
    # one ring to the start of the next is the one place it can be two, which is
    # what walking each ring back around to where it started buys.
    grid = plan_center_out(0, 0, 700, 700, fov_w=100, fov_h=100, overlap=0)
    steps = _chebyshev_steps(_lattice(grid, 100, 100))
    assert max(steps) <= 2
    # And overwhelmingly it is one: a spiral that hopped every other tile would
    # satisfy the bound above while travelling twice as far.
    assert steps.count(1) > 0.8 * len(steps)


def test_a_tile_the_shape_excludes_is_skipped_rather_than_surveyed():
    # `keep` is how a Slice hands its region's shape to the ordering without
    # search_grid knowing shapes exist.
    holed = plan_center_out(
        0, 0, 300, 300, fov_w=100, fov_h=100, overlap=0,
        keep=lambda c: c != (250.0, 250.0),
    )
    assert len(holed) == 8
    assert (250.0, 250.0) not in holed


def test_the_seed_is_the_most_interior_tile_of_a_concave_shape():
    # An L, where a centroid lands in the notch -- outside the shape entirely --
    # and would seed the survey at whatever tile happened to be nearest it. The
    # distance-to-the-outside measure has no such failure: it names the tile
    # with the most surveyed ground around it, wherever that is.
    #
    # The L is a 7x7 lattice keeping only the two leftmost columns and the two
    # bottom rows: 24 tiles whose centroid falls at about (2, 2), a lattice cell
    # the shape does not contain at all. The tile with the most surveyed ground
    # around it is the corner of the L at (1, 1) -- the only one a full two
    # steps from the outside -- and that is where the survey starts.
    def keep(center):
        gx, gy = round(center[0] / 100 - 0.5), round(center[1] / 100 - 0.5)
        return gx <= 1 or gy <= 1

    grid = plan_center_out(0, 0, 700, 700, fov_w=100, fov_h=100, overlap=0, keep=keep)
    assert len(grid) == 24
    assert grid[0] == (150.0, 150.0)


def test_the_seed_of_a_strip_with_no_interior_is_its_middle():
    # A region one tile wide has no tile that is far from every edge: they are
    # all on one. Ties there fall to the tile nearest the middle of the lattice,
    # which is the answer the operator asked for -- not the first tile in
    # whatever order the grid happened to be built in.
    grid = plan_center_out(0, 0, 700, 100, fov_w=100, fov_h=100, overlap=0)
    assert len(grid) == 7
    assert grid[0] == (350.0, 50.0)


def test_the_order_does_not_depend_on_where_the_stage_is():
    # The same relative geometry a metre away must produce the same relative
    # order, or a survey's behaviour would depend on the stage's origin.
    here = plan_center_out(0, 0, 500, 300, 100, 100, 0)
    there = plan_center_out(1e6, 2e6, 1e6 + 500, 2e6 + 300, 100, 100, 0)
    assert [(x - 1e6, y - 2e6) for x, y in there] == here


def test_ordering_a_full_sized_grid_is_not_quadratic():
    # tileGrid() is rebuilt on every nextTile(), and MAX_PLANNED_TILES is
    # 20,000, so an O(n^2) nearest-neighbour walk -- 400 million distance
    # comparisons -- would stall the survey between every tile. The bound is
    # deliberately loose: the point is to catch a change of complexity, not to
    # measure this machine.
    start = time.perf_counter()
    grid = plan_center_out(0, 0, 14000, 14000, fov_w=100, fov_h=100, overlap=0)
    elapsed = time.perf_counter() - start
    assert len(grid) == 19600
    assert elapsed < 5.0
