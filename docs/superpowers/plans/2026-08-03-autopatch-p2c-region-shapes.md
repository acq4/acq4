# Autopatch P2c — Search Regions as Arbitrary Shapes: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `Slice` survey arbitrary region shapes — rectangle, ellipse, polygon — instead of only axis-aligned rectangles, without changing how a rectangular region behaves.

**Architecture:** A new `acq4/experiment/search_region.py` defines region shape objects answering exactly two questions: `bounds()` (the axis-aligned box to plan a tile grid over) and `overlapsTile(center, fov)` (whether a planned tile is worth imaging). `Slice.tileGrid()` then plans the serpentine grid over each region's bounding box exactly as it does today and drops the tiles the shape does not overlap. `search_grid.plan_grid()` is unchanged. Geometry is exact, pure-Python, and deliberately **not** Qt-based (see Global Constraints).

**Tech Stack:** Python 3.12, pytest, PyQt5 + pyqtgraph (UI layer only). No new dependencies.

## Global Constraints

- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Every command below uses it explicitly; do not use `python`/`python3` from PATH.
- **Full suite for this work:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q` — **467 tests pass at the baseline commit**. A task that ends with any failure is not done.
- **Test output must be pristine.** No new warnings, no added skips, no `xfail`.
- **TDD, strictly:** write the failing test, run it and watch it fail *for the stated reason*, write the minimal implementation, run it and watch it pass, commit. A test that passes before the implementation exists is a broken test, not a fast win.
- **No Qt in `acq4/experiment/search_region.py`.** `QPainterPath.intersects(QRectF)` was measured against an independent oracle on this machine (PyQt5, no QApplication) and is **wrong at SI magnitudes**: for a 3 mm circular region tiled by a 200 µm field it reports 24 of 225 tiles as overlapping when they provably do not, identically at 3 mm/200 µm, at a 5 cm stage offset, and at 30 µm/2 µm, while being exact for the same relative geometry at unit magnitude. The exact closed-form tests in this plan are scale-invariant from 30 µm to 4×10⁷ m. Do not "simplify" them into Qt calls.
- **Coordinates are global metres**, so magnitudes of 1e-6 (a tile) and 1e-1 (stage travel) coexist. Never introduce an absolute epsilon; the geometry here needs none.
- **Style:** match the surrounding code — 4-space indent, ~88 column soft wrap, camelCase for methods on `Slice`/region classes and Qt widgets (the existing convention in these files), snake_case for module-level functions. Docstrings explain *why*, following the density of `slice.py` and `cell_producer.py`.
- **Commits:** one per task, conventional-commit subject, explanatory body, and:
  ```
  git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F <message-file>
  ```
  Message ends with `🤖 Generated with [Claude Code](https://claude.ai/code)`.
- **Branch:** `claude/autopatch-p2c-region-shapes`, already checked out in this worktree off `origin/_reviewed` (`5a81bae27`).

## Non-goals (do not build these here)

- Region **drawing** UI (ROI graphics in Area 1, mirror-to-Camera checkbox) — a later plan. Task 5 adds only a shape selector for the existing "Add region here" button, so ellipse regions are reachable without ROI graphics. Polygon regions stay API-only until drawing exists.
- **Persistence** of regions to the slice directory's `.index`. Not built at all today; adding `to_dict`/`from_dict` now would be unused code.
- **Exclusion** regions ("survey this but not that corner").
- Any change to `search_grid.py`.

## File Structure

| File | Responsibility |
|---|---|
| `acq4/experiment/search_region.py` (**create**) | Region shapes + the exact rect-vs-shape geometry. No Qt, no acq4 imports. |
| `acq4/experiment/tests/test_search_region.py` (**create**) | Geometry unit tests, including the independent oracle and scale-invariance properties. |
| `acq4/experiment/slice.py` (**modify**) | `addRegion` takes a region object; `tileGrid()` plans over bounds and filters by shape. |
| `acq4/experiment/tests/test_slice.py` (**modify**) | Migrate 13 `addRegion(x0, y0, x1, y1)` call sites; add filtering/coverage tests. |
| `acq4/experiment/tests/test_cell_producer.py` (**modify**) | Migrate 2 call sites (lines 41-45, 434). |
| `acq4/experiment/tests/test_detector_producer_seam.py` (**modify**) | Migrate 1 call site (line 59). |
| `acq4/modules/Autopatch/tests/test_orchestrator_cell_panel_seam.py` (**modify**) | Migrate 1 call site (line 73). |
| `acq4/modules/Autopatch/search_panel.py` (**modify**) | Area 2 shape selector + `regionShape()`. |
| `acq4/modules/Autopatch/Autopatch.py` (**modify**) | `addRegionHere()` builds the selected shape. |
| `acq4/modules/Autopatch/tests/test_search_panel.py` (**modify**) | Shape selector tests; add it to the lock parametrize list. |
| `acq4/modules/Autopatch/tests/test_window_integration.py` (**modify**) | Migrate the `regions[0]` 4-tuple unpack (line 617); add an ellipse test. |

---

### Task 1: Region base, tile geometry helper, and `RectRegion`

**Files:**
- Create: `acq4/experiment/search_region.py`
- Test: `acq4/experiment/tests/test_search_region.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `tile_rect(center: tuple[float, float], fov: tuple[float, float]) -> tuple[float, float, float, float]` — the closed `(x0, y0, x1, y1)` a tile images.
  - `class SearchRegion` with `bounds() -> tuple[float, float, float, float]` and `overlapsTile(center, fov) -> bool`, both raising `NotImplementedError`.
  - `class RectRegion(x0, y0, x1, y1)` — frozen dataclass, corner order normalized, `ValueError` on zero extent in either axis.
  - `_BoxRegion` — the shared frozen-dataclass base holding the normalization and `bounds()`; `RectRegion` and (Task 2) `EllipseRegion` subclass it and add only `overlapsTile`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_search_region.py`:

```python
"""Tests for search-region shapes: the bounding box a survey plans its tiles over,
and the exact rect-vs-shape overlap test that decides which of those tiles to image."""

import pytest

from acq4.experiment.search_region import RectRegion, SearchRegion, tile_rect

# A 10 um tile, the size used throughout these tests.
TILE = (10e-6, 10e-6)


def test_tile_rect_is_centered_on_the_tile_center():
    # A tile is named by its center (that is what the stage is driven to), but
    # overlap tests need its extent, and getting this wrong by half a field
    # would shift every survey by half a tile.
    assert tile_rect((10.0, 20.0), (4.0, 6.0)) == (8.0, 17.0, 12.0, 23.0)


def test_the_base_class_refuses_to_answer_for_itself():
    # SearchRegion is the contract, not a usable shape: a subclass that forgets
    # to implement one of the two methods must fail loudly rather than silently
    # surveying nothing.
    region = SearchRegion()
    with pytest.raises(NotImplementedError):
        region.bounds()
    with pytest.raises(NotImplementedError):
        region.overlapsTile((0.0, 0.0), TILE)


def test_rect_bounds_are_normalized_whichever_corners_are_given():
    # An ROI dragged up-and-left produces x1 < x0; the tiler would plan an empty
    # grid from that, so the region normalizes instead of trusting the caller.
    assert RectRegion(30e-6, 30e-6, 0.0, 0.0).bounds() == (0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6).bounds() == (0.0, 0.0, 30e-6, 30e-6)


def test_rect_rejects_zero_extent_in_either_axis():
    # A degenerate region is a mis-drag, not a search: it would plan a grid of
    # tiles over a line and report progress against it.
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 0.0, 30e-6)
    with pytest.raises(ValueError, match="nonzero extent"):
        RectRegion(0.0, 0.0, 30e-6, 0.0)


def test_rect_overlaps_a_tile_inside_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((15e-6, 15e-6), TILE) is True


def test_rect_does_not_overlap_a_tile_clear_of_it():
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((100e-6, 15e-6), TILE) is False


def test_rect_overlaps_a_tile_that_only_touches_its_edge():
    # Closed-rect semantics, and not a curiosity: plan_grid centers its grid over
    # the region so the outermost tiles deliberately overhang the edges. A
    # half-open test would drop a tile at every region border.
    region = RectRegion(0.0, 0.0, 30e-6, 30e-6)
    # This tile spans -10 um .. 0 um, touching the region's near edge exactly.
    assert region.overlapsTile((-5e-6, 15e-6), TILE) is True


def test_rect_regions_with_the_same_corners_are_equal():
    # Tests and UI code compare regions; a slice's region list is only
    # meaningfully assertable if equality is by value.
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) == RectRegion(0.0, 0.0, 30e-6, 30e-6)
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) != RectRegion(0.0, 0.0, 20e-6, 30e-6)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'acq4.experiment.search_region'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/experiment/search_region.py`:

```python
"""Search-region shapes for a Slice: the areas a survey tiles over, and the exact
rect-vs-shape overlap tests that decide which planned tiles are worth imaging."""

from __future__ import annotations

from dataclasses import dataclass


def tile_rect(
    center: tuple[float, float], fov: tuple[float, float]
) -> tuple[float, float, float, float]:
    """The closed (x0, y0, x1, y1) area a tile centered at `center` images."""
    cx, cy = center
    fov_w, fov_h = fov
    return (cx - fov_w / 2, cy - fov_h / 2, cx + fov_w / 2, cy + fov_h / 2)


class SearchRegion:
    """An area of tissue to survey, in global metres.

    Subclasses answer the only two questions the tiler asks: the axis-aligned box
    to plan a serpentine grid over, and whether a given planned tile overlaps the
    shape at all. That pair is what lets Slice.tileGrid() support any shape
    without search_grid.plan_grid() knowing shapes exist.

    Overlap, not containment, is the question on purpose. A region narrower than
    one field of view contains no tile center yet is still tissue the operator
    asked for, and a tile whose center falls in the concave part of an L still
    images real region area. Over-imaging slightly past an edge costs one tile;
    failing to image outlined tissue is a silent hole in the survey.

    The geometry is exact and pure-Python by measurement, not preference:
    Qt's QPainterPath.intersects() misreports 24 of 225 tiles for a 3 mm circular
    region tiled by a 200 um field, at every SI magnitude tried, while agreeing
    with these formulas exactly at unit magnitude.
    """

    def bounds(self) -> tuple[float, float, float, float]:
        """The axis-aligned (x0, y0, x1, y1) box containing this region."""
        raise NotImplementedError

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        """Whether a tile centered at `center` of size `fov` overlaps this region."""
        raise NotImplementedError


@dataclass(frozen=True)
class _BoxRegion(SearchRegion):
    """Shared base for the shapes a bounding box defines: the corner
    normalization and validation, which are identical for both.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self):
        lo_x, hi_x = min(self.x0, self.x1), max(self.x0, self.x1)
        lo_y, hi_y = min(self.y0, self.y1), max(self.y0, self.y1)
        if lo_x == hi_x or lo_y == hi_y:
            raise ValueError(
                f"a region needs nonzero extent in both axes, got "
                f"{(self.x0, self.y0, self.x1, self.y1)}"
            )
        object.__setattr__(self, "x0", lo_x)
        object.__setattr__(self, "y0", lo_y)
        object.__setattr__(self, "x1", hi_x)
        object.__setattr__(self, "y1", hi_y)

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


class RectRegion(_BoxRegion):
    """A rectangular region: the shape "Add region here" seeds, and the shape for
    which tile filtering is provably a no-op (every tile plan_grid plans over a
    rectangle overlaps that rectangle).
    """

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        return (
            tx0 <= self.x1 and tx1 >= self.x0 and ty0 <= self.y1 and ty1 >= self.y0
        )
```

Note: `RectRegion` carries no `@dataclass` decorator of its own. It inherits
`__init__`/`__eq__`/`__repr__` from `_BoxRegion`, and dataclass `__eq__` compares
`other.__class__ is self.__class__`, so a `RectRegion` and an `EllipseRegion` with
identical corners are correctly unequal.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: 8 passed.

- [ ] **Step 5: Confirm nothing else moved, then commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
```

Expected: 475 passed (467 baseline + 8 new).

```bash
git add acq4/experiment/search_region.py acq4/experiment/tests/test_search_region.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add SearchRegion base and RectRegion

The first half of generalising a Slice's search regions from bare
(x0, y0, x1, y1) tuples to shapes. A region answers two questions --
bounds() for the box a tile grid is planned over, and
overlapsTile(center, fov) for whether a planned tile is worth imaging --
which is all Slice.tileGrid() needs to support any shape without
search_grid.plan_grid() knowing shapes exist.

Overlap rather than containment: a region narrower than one field of view
contains no tile center but is still tissue the operator outlined, and a
tile whose center lands in the concave part of an L still covers real
region area.

The geometry is pure-Python by measurement. Qt's
QPainterPath.intersects(QRectF) reports 24 of 225 tiles as overlapping a
3 mm circular region tiled by a 200 um field when they provably do not,
identically at 3 mm/200 um, at a 5 cm stage offset, and at 30 um/2 um,
while being exact for the same relative geometry at unit magnitude.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 2: `EllipseRegion`

**Files:**
- Modify: `acq4/experiment/search_region.py` (append `EllipseRegion` after `RectRegion`)
- Test: `acq4/experiment/tests/test_search_region.py` (append)

**Interfaces:**
- Consumes: `_BoxRegion`, `tile_rect` from Task 1.
- Produces: `class EllipseRegion(x0, y0, x1, y1)` — the ellipse **inscribed in** that bounding box (matching how `pg.EllipseROI` is defined), same normalization and `ValueError` as `RectRegion`.

Every number asserted below was measured against an independent oracle on this
machine before this plan was written. They are not guesses; if one disagrees,
the implementation is wrong, not the number.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_search_region.py` (and extend the import at
the top to `from acq4.experiment.search_region import EllipseRegion, RectRegion, SearchRegion, tile_rect`):

```python
def _selected_pattern(regionClass, fov_len, off):
    """Which of a 15x15 grid of tiles `regionClass` selects, as a tuple of bools.

    The region is a square of exactly 15 tiles per side at `off`, so the same
    *relative* geometry can be built at any magnitude. Identical patterns across
    magnitudes is the property that catches an implementation whose accuracy
    depends on absolute coordinate size -- which is exactly how a Qt-based
    implementation fails here.
    """
    side = 15 * fov_len
    region = regionClass(off, off, off + side, off + side)
    fov = (fov_len, fov_len)
    return tuple(
        region.overlapsTile(
            (off + (gx + 0.5) * fov_len, off + (gy + 0.5) * fov_len), fov
        )
        for gy in range(15)
        for gx in range(15)
    )


def _sampled_overlap(region, center, fov, samples=40):
    """Independent oracle: does any densely sampled point of the tile lie inside
    the ellipse?

    Deliberately a different method from the implementation's closest-point
    formula -- point sampling of the tile -- so agreement means something. If a
    single near-tangent tile ever disagrees, raise `samples`; do not "fix" the
    implementation to match a coarse sampler.
    """
    x0, y0, x1, y1 = region.bounds()
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    tx0, ty0, tx1, ty1 = tile_rect(center, fov)
    for i in range(samples + 1):
        px = tx0 + (tx1 - tx0) * i / samples
        for j in range(samples + 1):
            py = ty0 + (ty1 - ty0) * j / samples
            if ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0:
                return True
    return False


def test_ellipse_is_inscribed_in_the_bounding_box_it_is_given():
    region = EllipseRegion(0.0, 0.0, 30e-6, 20e-6)
    assert region.bounds() == (0.0, 0.0, 30e-6, 20e-6)
    # Center of the box is inside; the box's corner is not.
    assert region.overlapsTile((15e-6, 10e-6), (1e-6, 1e-6)) is True
    assert region.overlapsTile((0.0, 0.0), (1e-9, 1e-9)) is False


def test_ellipse_rejects_zero_extent_like_a_rectangle_does():
    with pytest.raises(ValueError, match="nonzero extent"):
        EllipseRegion(0.0, 0.0, 30e-6, 0.0)


def test_a_small_tile_in_a_bounding_box_corner_is_excluded():
    # The ellipse inscribed in (0,0)-(30,30) um is a circle at (15,15) um of
    # radius 15 um. This tile spans 0..2 um in both axes, so its nearest point to
    # that center is its far corner (2,2) um -- sqrt(2)*13 um = 18.4 um away, well
    # outside the circle. Qt's QPainterPath.intersects() answers True here (a
    # measured false positive); this test is the guard against anyone replacing
    # the closed-form geometry with it.
    region = EllipseRegion(0.0, 0.0, 30e-6, 30e-6)
    assert region.overlapsTile((1e-6, 1e-6), (2e-6, 2e-6)) is False


def test_the_ellipse_tile_pattern_excludes_the_corners_it_should():
    # Pins the reference pattern the invariance test compares against, so that
    # test cannot pass vacuously against an all-True or all-False pattern.
    pattern = _selected_pattern(EllipseRegion, 1.0, 0.0)
    assert len(pattern) == 225
    assert sum(pattern) == 201
    # The four corner tiles of the grid are the unambiguous exclusions.
    assert pattern[0] is False
    assert pattern[14] is False
    assert pattern[210] is False
    assert pattern[224] is False


@pytest.mark.parametrize(
    "fov_len,off",
    [
        (200e-6, 0.0),        # a 3 mm region with a 200 um field: the realistic survey
        (200e-6, 5e-2),       # ...the same, out at a 5 cm stage coordinate
        (2e-6, 1e-3),         # a 30 um region with a 2 um field, off at 1 mm
        (1e-3, 4e7),          # absurd magnitude: pure arithmetic must not care
    ],
)
def test_ellipse_tile_selection_is_identical_at_every_magnitude(fov_len, off):
    # Qt's path intersection fails every one of these while passing the unit-scale
    # reference, which is why this property is tested rather than assumed.
    assert _selected_pattern(EllipseRegion, fov_len, off) == _selected_pattern(
        EllipseRegion, 1.0, 0.0
    )


def test_ellipse_agrees_with_a_sampled_oracle_over_a_whole_grid_of_tiles():
    # 15x15 tiles of 200 um over a 3 mm circular region -- the shape of a real
    # survey, and the configuration in which a Qt-based implementation gets 24 of
    # these 225 answers wrong.
    fov_len = 200e-6
    region = EllipseRegion(0.0, 0.0, 15 * fov_len, 15 * fov_len)
    fov = (fov_len, fov_len)
    for gy in range(15):
        for gx in range(15):
            center = ((gx + 0.5) * fov_len, (gy + 0.5) * fov_len)
            assert region.overlapsTile(center, fov) == _sampled_overlap(
                region, center, fov
            ), (gx, gy)


def test_a_rectangle_and_an_ellipse_with_the_same_box_are_not_equal():
    # Same corners, different tissue: the shapes must never compare equal, or a
    # region list would silently treat one as the other.
    assert RectRegion(0.0, 0.0, 30e-6, 30e-6) != EllipseRegion(0.0, 0.0, 30e-6, 30e-6)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: `ImportError: cannot import name 'EllipseRegion'`.

- [ ] **Step 3: Write the implementation**

Append to `acq4/experiment/search_region.py`:

```python
class EllipseRegion(_BoxRegion):
    """The ellipse inscribed in a bounding box -- the shape a `pg.EllipseROI`
    draws, and the natural outline for a rounded piece of tissue.

    Overlap is exact and needs no iteration: mapping the tile into the frame where
    the ellipse is the unit circle at the origin turns "does this rect reach the
    ellipse" into "is the closest point of a rect to the origin within 1". An
    axis-aligned rect stays axis-aligned under that (per-axis) scaling, which is
    what makes the closest point a per-axis clamp rather than a search.
    """

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        cx = (self.x0 + self.x1) / 2
        cy = (self.y0 + self.y1) / 2
        rx = (self.x1 - self.x0) / 2
        ry = (self.y1 - self.y0) / 2
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        ax0, ax1 = (tx0 - cx) / rx, (tx1 - cx) / rx
        ay0, ay1 = (ty0 - cy) / ry, (ty1 - cy) / ry
        # Clamp the origin into the mapped rect: the result is the rect's closest
        # point to the ellipse center, and zero on an axis the center falls within.
        dx = max(ax0, min(0.0, ax1))
        dy = max(ay0, min(0.0, ay1))
        return dx * dx + dy * dy <= 1.0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: 18 passed (8 from Task 1 + 10 here, counting the 4 parametrized cases).

- [ ] **Step 5: Commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
git add acq4/experiment/search_region.py acq4/experiment/tests/test_search_region.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add EllipseRegion with exact scale-invariant overlap

An ellipse inscribed in its bounding box, the shape a pg.EllipseROI
draws. Overlap maps the tile into the frame where the ellipse is the
unit circle, so the closest point of the tile to the ellipse center is a
per-axis clamp and the test is one comparison -- exact, no iteration.

Tested against a point-sampling oracle over the 225 tiles of a
realistic survey (3 mm region, 200 um field), and for identical tile
selection at four magnitudes from 30 um to 4e7 m. Both properties fail
for an implementation built on QPainterPath.intersects(): it misreports
24 of those 225 tiles at every SI magnitude tried.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 3: `PolygonRegion`

**Files:**
- Modify: `acq4/experiment/search_region.py` (append the two geometry helpers and `PolygonRegion`)
- Test: `acq4/experiment/tests/test_search_region.py` (append)

**Interfaces:**
- Consumes: `SearchRegion`, `tile_rect` from Task 1.
- Produces:
  - `class PolygonRegion(vertices)` — frozen dataclass holding `vertices: tuple[tuple[float, float], ...]`, implicitly closed, `ValueError` under 3 vertices.
  - Module-private `_segment_touches_rect(p, q, x0, y0, x1, y1) -> bool` and `_point_in_polygon(px, py, vertices) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_search_region.py` (extend the import to include `PolygonRegion`):

```python
# A triangle with no edge slope that lands on tile corners: an edge passing
# exactly through a tile corner is a genuine boundary tie (the tile touches the
# shape at a single point), and which way it resolves is float-noise sensitive.
# Those ties are real ambiguity, not precision loss, so the invariance property
# below is stated for a shape that has none.
TRIANGLE = ((0.7, 0.3), (14.1, 2.9), (2.6, 13.1))


def _polygon_pattern(scale, off):
    """TRIANGLE scaled by `scale` and offset to `off`, over a 15x15 tile grid."""
    region = PolygonRegion([(off + vx * scale, off + vy * scale) for vx, vy in TRIANGLE])
    fov = (scale, scale)
    return tuple(
        region.overlapsTile((off + (gx + 0.5) * scale, off + (gy + 0.5) * scale), fov)
        for gy in range(15)
        for gx in range(15)
    )


def test_polygon_needs_at_least_three_vertices():
    with pytest.raises(ValueError, match="at least 3 vertices"):
        PolygonRegion([(0.0, 0.0), (30e-6, 30e-6)])


def test_polygon_bounds_are_the_extremes_of_its_vertices():
    region = PolygonRegion([(10e-6, 5e-6), (30e-6, 8e-6), (12e-6, 25e-6)])
    assert region.bounds() == (10e-6, 5e-6, 30e-6, 25e-6)


def test_a_polygon_excludes_tiles_only_its_bounding_box_would_plan():
    # An L: the 30x30 um box minus the quadrant beyond (12, 12) um. This is the
    # whole point of filtering -- the bounding box plans a 3x3 grid, and one of
    # those tiles sits entirely in tissue the operator excluded.
    region = PolygonRegion(
        [
            (0.0, 0.0),
            (30e-6, 0.0),
            (30e-6, 12e-6),
            (12e-6, 12e-6),
            (12e-6, 30e-6),
            (0.0, 30e-6),
        ]
    )
    assert region.bounds() == (0.0, 0.0, 30e-6, 30e-6)
    # Spans 20..30 um in both axes: entirely inside the notch.
    assert region.overlapsTile((25e-6, 25e-6), TILE) is False
    # Its two neighbours each still clip the 10..12 um arm of the L.
    assert region.overlapsTile((15e-6, 25e-6), TILE) is True
    assert region.overlapsTile((25e-6, 15e-6), TILE) is True


def test_a_band_narrower_than_one_tile_still_selects_tiles():
    # A 2 um-wide diagonal band. This is the case a center-containment test gets
    # catastrophically wrong: no tile center lies inside the band, so it would
    # plan zero tiles and survey nothing at all.
    region = PolygonRegion(
        [(0.0, 6e-6), (22e-6, 28e-6), (22e-6, 30e-6), (0.0, 8e-6)]
    )
    centers = [(x, y) for x in (5e-6, 15e-6, 25e-6) for y in (5e-6, 15e-6, 25e-6)]
    # A zero-size tile is exactly a point test, so this asserts the premise
    # rather than assuming it: not one tile center is inside the band.
    assert not any(region.overlapsTile(c, (0.0, 0.0)) for c in centers)
    # And yet the band crosses five of those tiles, which must be surveyed.
    assert sum(region.overlapsTile(c, TILE) for c in centers) == 5
    # A tile the band misses entirely is still excluded.
    assert region.overlapsTile((15e-6, 5e-6), TILE) is False


def test_a_polygon_wholly_inside_one_tile_overlaps_it():
    # A shape smaller than a field of view is one tile's worth of work, not zero.
    region = PolygonRegion([(4e-6, 4e-6), (6e-6, 4e-6), (5e-6, 6e-6)])
    assert region.overlapsTile((5e-6, 5e-6), TILE) is True


def test_a_tile_wholly_inside_a_polygon_overlaps_it():
    # No edge crosses this tile, so the edge tests all fail and the containment
    # fallback is the only thing that can answer. Without it the interior of every
    # large region reads as "not to be imaged".
    region = PolygonRegion(
        [(0.0, 0.0), (100e-6, 0.0), (100e-6, 100e-6), (0.0, 100e-6)]
    )
    assert region.overlapsTile((50e-6, 50e-6), TILE) is True
    # The same absence of edge crossings must answer False from outside.
    assert region.overlapsTile((500e-6, 500e-6), TILE) is False


def test_the_polygon_tile_pattern_is_neither_everything_nor_nothing():
    # Pins the reference the invariance test compares against.
    pattern = _polygon_pattern(1.0, 0.0)
    assert len(pattern) == 225
    assert sum(pattern) == 111


@pytest.mark.parametrize(
    "scale,off",
    [
        (200e-6, 0.0),
        (200e-6, 5e-2),
        (2e-6, 1e-3),
        (1e-3, 4e7),
        (50e-6, -3.2e-3),   # negative stage coordinates are ordinary
    ],
)
def test_polygon_tile_selection_is_identical_at_every_magnitude(scale, off):
    assert _polygon_pattern(scale, off) == _polygon_pattern(1.0, 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: `ImportError: cannot import name 'PolygonRegion'`.

- [ ] **Step 3: Write the implementation**

Append to `acq4/experiment/search_region.py`. Put the two helpers immediately
above `PolygonRegion`, which is their only caller:

```python
def _segment_touches_rect(
    p: tuple[float, float],
    q: tuple[float, float],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> bool:
    """Whether the segment p->q touches the closed rect (Liang-Barsky clipping).

    Exact and scale-free: every comparison is between quantities of the same
    magnitude, so there is no epsilon to get wrong at either 1e-6 or 1e7.
    """
    px, py = p
    qx, qy = q
    dx = qx - px
    dy = qy - py
    t0, t1 = 0.0, 1.0
    for num, den in ((x0 - px, dx), (px - x1, -dx), (y0 - py, dy), (py - y1, -dy)):
        if den == 0.0:
            # Parallel to this edge: being outside it means no crossing exists.
            if num > 0.0:
                return False
            continue
        t = num / den
        if den > 0.0:
            if t > t1:
                return False
            t0 = max(t0, t)
        else:
            if t < t0:
                return False
            t1 = min(t1, t)
    return True


def _point_in_polygon(px: float, py: float, vertices) -> bool:
    """Crossing-number containment test for an implicitly closed polygon.

    Points exactly on the boundary are not guaranteed either answer, which is
    fine here: this is only consulted for tiles no edge touches, so the point is
    strictly inside or strictly outside.
    """
    inside = False
    j = len(vertices) - 1
    for i in range(len(vertices)):
        xi, yi = vertices[i]
        xj, yj = vertices[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class PolygonRegion(SearchRegion):
    """An arbitrary simple polygon, implicitly closed -- what a `pg.PolyLineROI`
    drawn around a cortical layer or an undamaged patch of slice produces.

    Vertices are stored as a tuple of float pairs so a region stays hashable and
    comparing two regions compares their geometry.
    """

    vertices: tuple

    def __post_init__(self):
        verts = tuple((float(x), float(y)) for x, y in self.vertices)
        if len(verts) < 3:
            raise ValueError(
                f"a polygon region needs at least 3 vertices, got {len(verts)}"
            )
        object.__setattr__(self, "vertices", verts)

    def bounds(self) -> tuple[float, float, float, float]:
        xs = [x for x, _ in self.vertices]
        ys = [y for _, y in self.vertices]
        return (min(xs), min(ys), max(xs), max(ys))

    def overlapsTile(self, center: tuple[float, float], fov: tuple[float, float]) -> bool:
        tx0, ty0, tx1, ty1 = tile_rect(center, fov)
        verts = self.vertices
        # An edge crossing the tile is the common answer, and it also covers the
        # case of a polygon small enough to sit entirely inside one tile.
        for i in range(len(verts)):
            if _segment_touches_rect(
                verts[i], verts[(i + 1) % len(verts)], tx0, ty0, tx1, ty1
            ):
                return True
        # With no edge touching it, the tile is either wholly inside the polygon
        # or wholly outside, so a single corner settles it.
        return _point_in_polygon(tx0, ty0, verts)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_region.py -q
```

Expected: 31 passed.

- [ ] **Step 5: Commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
git add acq4/experiment/search_region.py acq4/experiment/tests/test_search_region.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add PolygonRegion for arbitrary drawn outlines

A simple closed polygon -- what a PolyLineROI drawn around a cortical
layer produces. Overlap is an edge-vs-tile clip over each edge, falling
back to a containment test for tiles no edge touches (which are wholly
inside or wholly outside, so one corner decides).

The edge test is what makes a band narrower than one field of view
surveyable at all: no tile center lies inside such a band, so a
containment-only implementation plans zero tiles and images nothing.
Both halves are covered, and tile selection is pinned identical across
five magnitudes including a negative stage coordinate.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 4: `Slice` takes region objects and filters its tile grid

This is the breaking change: `Slice.addRegion` stops taking four floats. Every
caller and test moves in this task, so the tree is never left half-migrated.

**Files:**
- Modify: `acq4/experiment/slice.py` (lines 96, 105-113, 126-142)
- Modify: `acq4/experiment/tests/test_slice.py` (13 `addRegion` call sites + 1 `regions.append`)
- Modify: `acq4/experiment/tests/test_cell_producer.py` (lines 41-45, 434)
- Modify: `acq4/experiment/tests/test_detector_producer_seam.py` (line 59)
- Modify: `acq4/modules/Autopatch/tests/test_orchestrator_cell_panel_seam.py` (line 73)

**Interfaces:**
- Consumes: `RectRegion`, `EllipseRegion`, `PolygonRegion`, `SearchRegion` from Tasks 1-3.
- Produces: `Slice.addRegion(region: SearchRegion) -> None`; `Slice.regions -> list[SearchRegion]`; `Slice.tileGrid()` unchanged in signature and ordering, now shape-filtered.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_slice.py`, and add these imports at the top
alongside the existing `from acq4.experiment.slice import SearchConstraints, Slice`:

```python
from acq4.experiment.search_grid import plan_grid
from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
```

```python
def test_a_rectangular_region_plans_exactly_its_bounding_box_grid():
    # The regression guard for the whole migration: a rectangle must behave
    # exactly as it did when regions were 4-tuples. It provably does -- plan_grid
    # centers its grid over the box, so every tile it plans overlaps the box --
    # and this pins that so a future filter change cannot quietly cost tiles.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    assert s.tileGrid() == plan_grid(0, 0, 30e-6, 30e-6, FOV[0], FOV[1], 0.0)


def test_an_elliptical_region_drops_the_corner_tiles_its_bounding_box_plans():
    # 15x15 tiles, the resolution at which a bounding box's corners are genuinely
    # outside the ellipse. Those 24 tiles are the imaging time shapes exist to
    # save; at a coarser 3x3 every tile reaches the ellipse and there is nothing
    # to drop, which is why this test is not written at 3x3.
    side = 150e-6
    ellipse = make_slice()
    ellipse.addRegion(EllipseRegion(0, 0, side, side))
    box = make_slice()
    box.addRegion(RectRegion(0, 0, side, side))

    planned = box.tileGrid()
    kept = ellipse.tileGrid()
    assert len(planned) == 225
    assert len(kept) == 201
    # What it drops are the box's corners; what it keeps includes the middle.
    assert planned[0] not in kept
    assert planned[14] not in kept
    assert any(c == pytest.approx((75e-6, 75e-6)) for c in kept)


def test_an_elliptical_regions_tiles_still_cover_the_whole_ellipse():
    # Filtering must not leave holes *inside* the shape: every point of the
    # ellipse has to fall inside some tile that will actually be imaged.
    side = 150e-6
    s = make_slice()
    s.addRegion(EllipseRegion(0, 0, side, side))
    grid = s.tileGrid()
    center = side / 2
    radius = side / 2
    n = 40
    for i in range(n + 1):
        for j in range(n + 1):
            px, py = side * i / n, side * j / n
            if (px - center) ** 2 + (py - center) ** 2 > radius * radius:
                continue
            assert any(
                abs(px - tx) <= FOV[0] / 2 + 1e-12
                and abs(py - ty) <= FOV[1] / 2 + 1e-12
                for tx, ty in grid
            ), (px, py)


def test_filtering_preserves_the_serpentine_order_within_a_region():
    # nextTile hands out tileGrid()'s order, and that order is what keeps stage
    # travel down. Filtering must remove tiles without reordering the survivors.
    side = 150e-6
    ellipse = make_slice()
    ellipse.addRegion(EllipseRegion(0, 0, side, side))
    box = make_slice()
    box.addRegion(RectRegion(0, 0, side, side))

    planned = box.tileGrid()
    positions = [planned.index(c) for c in ellipse.tileGrid()]
    assert positions == sorted(positions)


def test_regions_of_different_shapes_share_one_slice_and_one_coverage_record():
    # Shapes are per region, not per slice: an operator can outline one area as a
    # rectangle and another as an ellipse, and coverage still spans both.
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.addRegion(EllipseRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6))
    assert [type(r) for r in s.regions] == [RectRegion, EllipseRegion]
    # Nine tiles each: at 3x3 every tile of the box reaches the inscribed ellipse.
    assert len(s.tileGrid()) == 18

    s.markCovered(s.nextTile())
    assert s.surveyStats() == (18, 1, pytest.approx(100 / 18))


def test_a_polygon_narrower_than_one_tile_still_gets_a_grid():
    # The end-to-end version of the band case: a 2 um-wide diagonal band contains
    # no tile center at all, so a Slice that filtered by containment would report
    # a region with nothing to survey.
    s = make_slice()
    s.addRegion(
        PolygonRegion([(0.0, 6e-6), (22e-6, 28e-6), (22e-6, 30e-6), (0.0, 8e-6)])
    )
    grid = s.tileGrid()
    assert len(grid) > 0
    assert len(grid) < len(plan_grid(0.0, 6e-6, 22e-6, 30e-6, FOV[0], FOV[1], 0.0))
    assert s.nextTile() == grid[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -q
```

Expected: the six new tests fail with `TypeError: addRegion() missing 3 required
positional arguments` (a region object arriving where four floats are expected).
The pre-existing tests still pass at this point.

- [ ] **Step 3: Migrate `Slice`**

In `acq4/experiment/slice.py`, add the import beside the existing `search_grid` one:

```python
from .search_grid import count_covered, plan_grid, select_next
from .search_region import SearchRegion
```

Change the region store's type in `__init__`:

```python
        self._regions: list[SearchRegion] = []
```

Replace the `regions` property and `addRegion`:

```python
    @property
    def regions(self) -> list[SearchRegion]:
        """The search regions, as a copy: mutating the result changes nothing."""
        return list(self._regions)

    def addRegion(self, region: SearchRegion) -> None:
        """Add a shape to survey, in global coordinates. Coverage is untouched.

        Takes a SearchRegion rather than four floats because tissue is not
        rectangular: a slice with a damaged corner, or one cortical layer worth
        searching, is the ordinary reason to outline a region at all. A rectangle
        is `RectRegion(x0, y0, x1, y1)`.
        """
        self._regions.append(region)
```

Replace `tileGrid`:

```python
    def tileGrid(self) -> list[tuple[float, float]]:
        """Every region's tile centers, concatenated in the order regions were added.

        Each region's grid is planned over its **bounding box** and then filtered
        to the tiles that overlap the region's shape. That split is what lets a
        slice hold ellipses and polygons while `plan_grid` stays a rectangle
        tiler. For a rectangular region the filter removes nothing, since
        `plan_grid` centers its grid over the box and every tile it plans
        therefore overlaps it.

        Filtering is by overlap, not by whether the tile's center is inside: a
        region narrower than one field of view contains no center at all, and a
        tile whose center falls in the concave part of an L still images real
        region area.

        Within a region the surviving centers keep the serpentine order
        `plan_grid` produces: alternating the direction of each row roughly halves
        the stage travel a survey spends getting from one tile to the next, and
        `nextTile` hands them out in exactly this order.
        """
        grid: list[tuple[float, float]] = []
        fov_w, fov_h = self._fov
        for region in self._regions:
            x0, y0, x1, y1 = region.bounds()
            planned = plan_grid(x0, y0, x1, y1, fov_w, fov_h, self._overlap)
            grid.extend(c for c in planned if region.overlapsTile(c, self._fov))
        return grid
```

- [ ] **Step 4: Migrate every existing call site**

All mechanical. In `acq4/experiment/tests/test_slice.py`, wrap all 13 existing
calls: `s.addRegion(0, 0, 30e-6, 30e-6)` becomes
`s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))`, and likewise for the
`(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6)` second-region calls and the two
`plain`/`overlapped` calls. Also fix the mutation test at line 150:

```python
def test_regions_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(RectRegion(0, 0, 30e-6, 30e-6))
    s.regions.append(RectRegion(1e-3, 1e-3, 2e-3, 2e-3))
    assert len(s.regions) == 1
```

In `acq4/experiment/tests/test_cell_producer.py`, the helper at lines 41-45
becomes:

```python
def make_slice(constraints=None, regions=(RectRegion(0, 0, 30e-6, 30e-6),)):
    s = Slice(fov=FOV, constraints=constraints)
    for r in regions:
        s.addRegion(r)
    return s
```

with `from acq4.experiment.search_region import RectRegion` added to its imports,
and line 434's `s.addRegion(0, 0, 30e-6, 30e-6)` wrapped the same way. Check
whether any test in that file passes its own `regions=` tuple of 4-tuples and
wrap those too.

In `acq4/experiment/tests/test_detector_producer_seam.py` line 59 and
`acq4/modules/Autopatch/tests/test_orchestrator_cell_panel_seam.py` line 73, the
`REGION` module constant stays a 4-tuple (it is also read for other assertions);
only the call changes:

```python
        sliceState.addRegion(RectRegion(*REGION))
```

with the import added in each file.

- [ ] **Step 5: Run the full suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
```

Expected: 504 passed, 0 failed (467 baseline + 31 from Tasks 1-3 + 6 here). Treat
the count as informational; **zero failures is the gate**. A `TypeError` about
`addRegion` arguments means a call site was missed.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/slice.py acq4/experiment/tests/test_slice.py \
  acq4/experiment/tests/test_cell_producer.py \
  acq4/experiment/tests/test_detector_producer_seam.py \
  acq4/modules/Autopatch/tests/test_orchestrator_cell_panel_seam.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat!: Slice surveys region shapes, not just rectangles

addRegion now takes a SearchRegion instead of four floats, and tileGrid
plans each region's grid over its bounding box and then drops the tiles
that do not overlap the shape. search_grid.plan_grid is untouched: it
stays a rectangle tiler and never learns that shapes exist.

A rectangle behaves exactly as before, provably and by test -- plan_grid
centers its grid over the box, so every tile it plans overlaps that box
and the filter removes nothing. An ellipse over a 15x15 grid drops the 24
corner tiles its bounding box would have imaged, while still covering
every point inside the ellipse and keeping the serpentine order nextTile
depends on.

BREAKING: Slice.addRegion(x0, y0, x1, y1) is now
Slice.addRegion(RectRegion(x0, y0, x1, y1)), and Slice.regions yields
region objects rather than 4-tuples (call .bounds() for the box).

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 5: Area 2 selects the shape "Add region here" seeds

Without this, an ellipse region is unreachable from the UI and the feature ships
dark. Region *drawing* is still out of scope: this is a two-item selector beside
the existing button.

**Files:**
- Modify: `acq4/modules/Autopatch/search_panel.py`
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`addRegionHere`, lines 224-244)
- Test: `acq4/modules/Autopatch/tests/test_search_panel.py` (append + extend the parametrize list at line 232)
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py` (fix line 617's unpack; append one test)

**Interfaces:**
- Consumes: `RectRegion`, `EllipseRegion` (Tasks 1-2); `Slice.addRegion` (Task 4).
- Produces: `SearchPanel.shapeCombo` (a `Qt.QComboBox` whose item data is `"rect"`/`"ellipse"`), `SearchPanel.regionShape() -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_search_panel.py`:

```python
def test_the_region_shape_defaults_to_a_rectangle(qapp):
    # The shape every existing survey used, so the default must not change what
    # pressing the button has always done.
    panel = makePanel()
    assert panel.regionShape() == "rect"


def test_the_region_shape_reports_a_key_not_the_combo_label(qapp):
    # The window maps this to a region class; keying on display text would break
    # the first time the label is reworded.
    panel = makePanel()
    panel.shapeCombo.setCurrentIndex(panel.shapeCombo.findData("ellipse"))
    assert panel.regionShape() == "ellipse"
```

Add `"shapeCombo"` to the `widgetName` parametrize list of
`test_locking_disables_editing_but_not_the_readout` (it seeds a region, so a run
in flight must not be able to change it).

Append to `acq4/modules/Autopatch/tests/test_window_integration.py` (importing
`EllipseRegion` and `RectRegion` from `acq4.experiment.search_region`):

```python
def test_add_region_here_builds_the_shape_area_2_selects(qapp, tmp_path):
    # Until Area 1 can draw ROIs, this selector is the only way to seed a
    # non-rectangular region, so the button has to read it rather than always
    # building a rectangle.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.searchPanel.shapeCombo.setCurrentIndex(
        win.searchPanel.shapeCombo.findData("ellipse")
    )

    win.addRegionHere()

    region = win.slice.regions[0]
    assert isinstance(region, EllipseRegion)
    # Inscribed in the same 3x3-field box a rectangle would have used, centered
    # on the camera's "roi" center -- computed off the fake camera directly so a
    # bug in _cameraFov() is caught rather than echoed back.
    camera = win.cameraSelector.getSelectedObj()
    _, _, fov_w, fov_h = camera.getBoundary(globalCoords=True, mode="roi")
    cx, cy, _ = camera.globalCenterPosition("roi")
    assert region.bounds() == pytest.approx(
        (
            cx - 3 * fov_w / 2,
            cy - 3 * fov_h / 2,
            cx + 3 * fov_w / 2,
            cy + 3 * fov_h / 2,
        )
    )
    # And it is actually surveyable, not merely recorded.
    assert len(win.slice.tileGrid()) > 1
```

Fix the existing unpack at line 617 of the same file:

```python
    region = win.slice.regions[0]
    assert isinstance(region, RectRegion)
    x0, y0, x1, y1 = region.bounds()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_search_panel.py acq4/modules/Autopatch/tests/test_window_integration.py -q
```

Expected: `AttributeError: 'SearchPanel' object has no attribute 'shapeCombo'`.

- [ ] **Step 3: Implement the selector**

In `acq4/modules/Autopatch/search_panel.py`, build the combo next to the other
controls (after `self.rescansCheck`, before `self.addRegionBtn`):

```python
        # Item data, not display text, is what regionShape() returns: the window
        # maps it to a region class, and a label is a label.
        self.shapeCombo = Qt.QComboBox()
        for label, key in (("Rectangle", "rect"), ("Ellipse", "ellipse")):
            self.shapeCombo.addItem(label, key)
        self.shapeCombo.setToolTip(
            "The shape \"Add region here\" seeds. An ellipse is inscribed in the "
            "same 3x3-field box as the rectangle, so it searches the rounded "
            "middle and skips the corners."
        )
```

Add it to the form, after the four constraint rows:

```python
        form.addRow("Region shape", self.shapeCombo)
```

Add the accessor next to `constraints()`:

```python
    def regionShape(self) -> str:
        """The shape key for the next seeded region: "rect" or "ellipse"."""
        return self.shapeCombo.currentData()
```

And add `self.shapeCombo` to the tuple in `setInteractionLocked`.

- [ ] **Step 4: Implement the window side**

In `acq4/modules/Autopatch/Autopatch.py`, add the import:

```python
from acq4.experiment.search_region import EllipseRegion, RectRegion
```

and replace the `addRegion` call at the end of `addRegionHere()`:

```python
        # Area 2 owns the shape; this button owns the placement. An ellipse is
        # inscribed in the same box, so both shapes cover the same 3x3 fields and
        # only the corners differ.
        regionClass = (
            EllipseRegion
            if self.searchPanel.regionShape() == "ellipse"
            else RectRegion
        )
        self.slice.addRegion(
            regionClass(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        )
```

Update that method's docstring to say the shape comes from Area 2's selector.

- [ ] **Step 5: Run the full suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
```

Expected: 508 passed, 0 failed (504 + 2 search-panel + 1 window + 1 new
parametrize case). Zero failures is the gate.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/search_panel.py acq4/modules/Autopatch/Autopatch.py \
  acq4/modules/Autopatch/tests/test_search_panel.py \
  acq4/modules/Autopatch/tests/test_window_integration.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: let Area 2 choose the shape "Add region here" seeds

A two-item selector (rectangle, ellipse) beside the existing button, so
an elliptical region is reachable before Area 1 can draw ROIs -- without
it the shape support added in this branch would ship dark. The combo
returns an item-data key rather than its label, since the window maps
that key to a region class.

Rectangle stays the default, so pressing the button does what it always
did, and the selector locks with the rest of Area 2 while a run is in
flight: it parameterises a region a live producer may already be
surveying.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

## Definition of done

- [ ] `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q` → 508 passed, 0 failed, no new warnings.
- [ ] `git grep -n "addRegion(" -- acq4/` shows no remaining four-float call.
- [ ] `git grep -n "QPainterPath" -- acq4/experiment/` finds nothing.
- [ ] Five commits, one per task, each with a passing suite at that commit.

## Notes for the reviewer

- The two properties that carry this work are **scale invariance** of tile
  selection and **rectangle behaviour unchanged**. If either is deleted, the
  remaining tests would still pass against an implementation that is wrong at
  every real stage coordinate.
- Any suggestion to "simplify" the geometry into `QPainterPath.intersects()` must
  be rejected: it is a measured false-positive rate of 24/225 on the realistic
  survey configuration, at every SI magnitude tested.
- The design spec for this work is §6b "Regions are shapes, not rectangles" of
  `autopatch-orchestration-design.md`, which is untracked and lives in the main
  checkout rather than in this worktree.
