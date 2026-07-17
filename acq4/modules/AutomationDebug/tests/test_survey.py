"""Tests for the survey-region grid packing used by the autopatch demo.

Cover plan_grid (serpentine FOV tiling that fully covers a rectangle) and
select_next (choosing the next un-imaged tile), the pure logic behind surveying
a user-defined region one z-stack per tile.
"""

import math

from acq4.modules.AutomationDebug.survey import (
    _is_visited,
    count_covered,
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
