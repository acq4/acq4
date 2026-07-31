# Autopatch P2b — `Slice`, Area 2 cell-finding config, and a real cell producer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `Slice` object that owns a piece of tissue's search state, make it hand out real cell producers that image and detect cells tile by tile, and give the operator an Area 2 panel to configure the search — so the P2a `cellProducer` hook finally has something real plugged into it.

**Architecture:** Three layers, split so the testable part is actually tested. (1) **Pure geometry** — the serpentine tile grid, already TDD'd in `acq4/modules/AutomationDebug/survey.py`, moves into `acq4/experiment/search_grid.py` where CI can reach it. (2) **Pure search logic** — `Slice` (regions, coverage, constraints) and `CellProducer` (tile walk, health cutoff, density cap, rescans, and the `[]`-vs-`None` exhaustion contract) are plain objects with no device or `acq4_automation` imports, driven in tests by a fake detector. (3) **Device glue** — `tile_detector.py` holds the one function that moves the stage, finds the surface, acquires a z-stack, and calls `detect_neurons`; it is thin by design because nothing headless can test it.

`Slice` lives in `acq4/experiment/` (owner decision, 2026-07-30, resolving design §6b's open question) so its tests run on a public runner rather than in the `acq4_automation`-gated `modules/Autopatch/tests` directory that `conftest.py` skips.

**Tech Stack:** Python 3.12, PyQt (via `acq4.util.Qt`), pyqtgraph, `acq4.util.task` (gentletask bridge: `check_stop`, `Stopped`, `run_in_gui_thread`, `synch`), pytest + pytest-qt, `acq4_automation` (internal: `object_detection.detect_neurons`, `feature_tracking.cell.Cell`).

## Global Constraints

- Python interpreter is `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Never `acq4-torch`.
- All new files start with a brief 2-line comment/docstring explaining what the file does.
- Comments are evergreen: never refer to refactors, "recently", "now", phases, or change history.
- Commit format per repo `CLAUDE.md`: `<type>: <description>`, plus `--author` containing `(claude)`, plus the `🤖 Generated with [Claude Code](https://claude.ai/code)` footer. Commit email `outofculture@gmail.com`.
- Never `git commit --no-verify`.
- TDD: failing test first, watch it fail, minimal implementation, watch it pass, commit.
- **Mutation-verify any test whose assertion is about absence, or about a value that could be trivially already-correct.** Three P2a tests were vacuous — they asserted the right property but could not reach the state that distinguishes fixed from broken code. Where this plan says "mutation-verify", it means: apply the named defect to the implementation, observe the named test fail, revert the defect. This is not optional and is not satisfied by re-reading the test.
- "Depth" in this plan is *always* a z-range relative to the tissue surface. It is never a queue length. The `targetQueueDepth` concept was built in P2a and deleted on owner review; do not reintroduce it.
- The producer contract from design §3.2 is load-bearing and must not be "simplified": `producer() -> Sequence[cell] | None`, where `[]` means "made progress, found nothing here, ask me again" and `None` means "exhausted, never ask again". A producer that returns `[]` forever wedges the run loop.
- No `acq4_automation` import at module top level in any file under `acq4/experiment/`. Import it inside the function that needs it, the way `acq4/modules/AutomationDebug/detection.py` does — otherwise `acq4/experiment/tests` stops collecting on a public runner.
- `Slice` and `CellProducer` are plain Python objects, not `QObject`s. They hold no widgets and must stay refcount-freeable (see Task 6).

**Reference documents:**
- Design doc: `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` (untracked, in the main checkout, not in this worktree) — §3.2 (Start loop / producer contract), §6b (`Slice`), §7 Area 1/Area 2, §10 (phasing).
- P2a plan: `docs/superpowers/plans/2026-07-29-autopatch-p2a-cell-producer.md`.

**Explicitly out of scope for P2b** (P2c or later): Area 1's draggable ROI graphics and the mirror-to-Camera checkbox; the progress heatmap rendering; the pinned-frames imaging workflow; disk persistence of slice state via `DirHandle.setInfo()` (design §6b calls this "not required for a first cut"); the cross-repo `acq4_automation.Cell` expansion the heatmap's per-cell colouring would force.

---

## File Structure

**Created:**

| File | Responsibility |
|---|---|
| `acq4/experiment/search_grid.py` | Pure serpentine tile-grid geometry, moved verbatim from `AutomationDebug/survey.py`. |
| `acq4/experiment/slice.py` | `SearchConstraints` (the four Area 2 constraints, validated) and `Slice` (regions, coverage, constraints, `makeCellProducer()`). |
| `acq4/experiment/cell_producer.py` | `CellProducer` — the callable the orchestrator's refill hook takes. Tile walk, filtering, exhaustion. |
| `acq4/experiment/tile_detector.py` | `make_tile_detector()` — the real device glue: move stage, find surface, z-stack, `detect_neurons`. Lazy `acq4_automation` import. |
| `acq4/experiment/tests/test_search_grid.py` | Grid geometry tests, moved from `AutomationDebug/tests/test_survey.py`. |
| `acq4/experiment/tests/test_slice.py` | `SearchConstraints` validation, `Slice` regions/coverage/stats. |
| `acq4/experiment/tests/test_cell_producer.py` | Tile walk, `[]` vs `None`, health cutoff, density cap, rescans, leak. |
| `acq4/experiment/tests/test_tile_detector.py` | Per-tile depth arithmetic, focus restoration, stop handling, cell construction. |
| `acq4/modules/Autopatch/search_panel.py` | Area 2 widget: the four constraints, "Add region here", survey readout. |
| `acq4/modules/Autopatch/tests/test_search_panel.py` | Area 2 widget behaviour. |
| `.superpowers/sdd/p2b-smoke-brief.md` | Human-run live smoke-test brief (Task 12). |

**Modified:**

| File | Change |
|---|---|
| `acq4/modules/AutomationDebug/survey.py` | Re-export the grid functions from `acq4/experiment/search_grid.py` instead of defining them. |
| `acq4/modules/AutomationDebug/tests/test_survey.py` | Deleted; its content moves to `acq4/experiment/tests/test_search_grid.py`. |
| `acq4/experiment/orchestrator.py` | Add the `"surveying"` status, clear `sigCurrentCell` before a refill, add `clearQueue()`. |
| `acq4/experiment/tests/test_orchestrator_producer.py` | Tests for the three orchestrator changes above. |
| `acq4/modules/Autopatch/status_panel.py` | Handle `"surveying"` in `_onStatus`/`_updateButtons`. |
| `acq4/modules/Autopatch/tests/test_status_panel.py` | Tests for the `"surveying"` gating. |
| `acq4/modules/Autopatch/Autopatch.py` | Own the `Slice`, Area 1 "New slice" button, Area 2 panel, install/clear the producer. |
| `acq4/modules/Autopatch/tests/test_window_integration.py` | Producer install at Start, `setCellProducer(None)` on teardown/reload. |

**Two decisions this plan makes, flagged for owner confirmation:**

1. **`rescans_allowed=True` grants exactly one extra pass, not unlimited rescanning.** An unbounded rescan loop would never return `None`, which violates the §3.2 contract and wedges the run loop — so "unlimited" is not an available reading. One extra pass per producer is the smallest thing that makes the switch mean something while keeping the contract. Recorded in `CellProducer`'s docstring.
2. **Depth range is stored as signed offsets from the surface** (design §7's example, −20 µm to −60 µm, is `depth_range=(-20e-6, -60e-6)`), so `z = surface + offset`. `AutomationDebug`'s spinboxes instead hold *positive* depths and subtract (`start_z = surface - spin.value()`); the signed form is used here because it matches the design doc's notation and makes the sign explicit at the one place it matters.

---

### Task 1: Move the tile-grid geometry into the engine

The serpentine grid math is already written and TDD'd, but it lives in a UI module that `conftest.py` excludes from public CI, and P2b's producer needs it from the engine. Move it; leave `AutomationDebug` working by re-exporting. This is a refactor — no behaviour changes.

**Files:**
- Create: `acq4/experiment/search_grid.py`
- Create: `acq4/experiment/tests/test_search_grid.py`
- Modify: `acq4/modules/AutomationDebug/survey.py:1-96`
- Delete: `acq4/modules/AutomationDebug/tests/test_survey.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `plan_grid(x0, y0, x1, y1, fov_w, fov_h, overlap) -> list[tuple[float, float]]`; `select_next(grid, visited, threshold) -> tuple[float, float] | None`; `count_covered(grid, visited, threshold) -> int`; `_is_visited(cx, cy, visited, threshold) -> bool`. All coordinates are global metres.

- [ ] **Step 1: Create the new module by moving the four functions verbatim**

Create `acq4/experiment/search_grid.py`. Copy `_axis_centers`, `plan_grid`, `_is_visited`, `select_next`, and `count_covered` from `acq4/modules/AutomationDebug/survey.py` **unchanged, including their docstrings** — they are correct and reviewed. Only the module docstring and the imports are new:

```python
"""Serpentine field-of-view tiling over a rectangular search region, and
tracking which of those tiles have already been imaged."""

from __future__ import annotations

import math
```

Do not copy `import pyqtgraph as pg`, the `TYPE_CHECKING` block, or `SurveyRegion` — those are Qt/camera glue and stay in `AutomationDebug`.

- [ ] **Step 2: Move the test file**

Create `acq4/experiment/tests/test_search_grid.py` with the full content of `acq4/modules/AutomationDebug/tests/test_survey.py`, changing only the import and the module docstring:

```python
"""Tests for the search-region grid packing: serpentine FOV tiling that fully
covers a rectangle, and choosing the next un-imaged tile."""

import math

from acq4.experiment.search_grid import (
    _is_visited,
    count_covered,
    plan_grid,
    select_next,
)
```

Then delete `acq4/modules/AutomationDebug/tests/test_survey.py`.

- [ ] **Step 3: Run the moved tests**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_search_grid.py -v
```

Expected: 12 passed (the same count `test_survey.py` had).

- [ ] **Step 4: Repoint `survey.py` at the engine module**

In `acq4/modules/AutomationDebug/survey.py`, delete the bodies of `_axis_centers`, `plan_grid`, `_is_visited`, `select_next`, and `count_covered`, and delete `import math`. Replace the import block so `SurveyRegion` (which stays) and any other importer get the functions from their new home:

```python
"""Survey-region support for the autopatch demo: pack the camera field of view as
a grid over a user-defined rectangle and track which tiles have been imaged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg

from acq4.experiment.search_grid import count_covered, plan_grid, select_next

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow
```

`SurveyRegion` itself is untouched. Note `_is_visited` is not re-exported: nothing outside the deleted test file used it.

- [ ] **Step 5: Verify no importer broke**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "from acq4.modules.AutomationDebug.survey import SurveyRegion, plan_grid, select_next, count_covered; print('ok')"
```

Expected: `ok`.

Then confirm nothing else referenced the moved names:

```bash
grep -rn "AutomationDebug.survey\|from .survey" --include=*.py acq4/
```

Expected: only `acq4/modules/AutomationDebug/AutomationDebug.py:27` (`from .survey import SurveyRegion`).

- [ ] **Step 6: Run the full engine suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -q
```

Expected: all pass, 12 more than the pre-task count.

- [ ] **Step 7: Commit**

```bash
git add acq4/experiment/search_grid.py acq4/experiment/tests/test_search_grid.py acq4/modules/AutomationDebug/survey.py acq4/modules/AutomationDebug/tests/test_survey.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
refactor: move the search-region grid math into acq4/experiment

The serpentine tile grid is engine logic, needed by the cell producer, and
its tests only ran where acq4_automation is installed because they lived
under AutomationDebug/tests. SurveyRegion re-exports from the new home.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 2: `SearchConstraints`

The four Area 2 search constraints as one validated value object. Validation matters because these come from operator spinboxes and a bad value silently produces either zero cells or every cell.

**Files:**
- Create: `acq4/experiment/slice.py`
- Create: `acq4/experiment/tests/test_slice.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SearchConstraints(depth_range: tuple[float, float] = (-20e-6, -60e-6), min_health: float = 0.5, max_cell_density: float = 5e12, rescans_allowed: bool = False)`, a frozen dataclass raising `ValueError` from `__post_init__` on invalid input. `max_cell_density` is cells per cubic metre (5e12 /m³ ≈ 5 cells per 1000 µm³... see Step 1's note on units).

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_slice.py`:

```python
"""Tests for SearchConstraints validation and the Slice object's regions,
coverage, and survey statistics."""

import pytest

from acq4.experiment.slice import SearchConstraints


def test_defaults_are_a_usable_search():
    c = SearchConstraints()
    assert c.depth_range == (-20e-6, -60e-6)
    assert 0.0 <= c.min_health <= 1.0
    assert c.max_cell_density > 0
    assert c.rescans_allowed is False


def test_depth_range_offsets_must_be_at_or_below_the_surface():
    # Offsets are relative to the tissue surface and negative is deeper, so a
    # positive offset would search in the bath above the tissue.
    with pytest.raises(ValueError, match="at or below the surface"):
        SearchConstraints(depth_range=(20e-6, -60e-6))


def test_depth_range_must_span_a_nonzero_thickness():
    with pytest.raises(ValueError, match="nonzero thickness"):
        SearchConstraints(depth_range=(-40e-6, -40e-6))


def test_depth_range_accepts_either_ordering():
    # An operator may type the deeper bound first; both describe the same slab.
    shallow_first = SearchConstraints(depth_range=(-20e-6, -60e-6))
    deep_first = SearchConstraints(depth_range=(-60e-6, -20e-6))
    assert shallow_first.z_span() == deep_first.z_span()
    assert shallow_first.z_span() == pytest.approx(40e-6)


def test_min_health_must_be_a_probability():
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=1.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        SearchConstraints(min_health=-0.1)


def test_max_cell_density_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        SearchConstraints(max_cell_density=0.0)


def test_constraints_are_frozen():
    c = SearchConstraints()
    with pytest.raises(Exception):
        c.min_health = 0.9
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v
```

Expected: collection error, `ModuleNotFoundError: No module named 'acq4.experiment.slice'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/experiment/slice.py`:

```python
"""Slice: the search state for one piece of tissue -- the regions to survey, the
tiles already imaged, the search constraints, and the cell producers it hands out."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConstraints:
    """The Area 2 search constraints that parameterise a cell producer.

    `depth_range` is a pair of z offsets **relative to the tissue surface**, in
    metres, negative being deeper: the design's "-20 um through -60 um" is
    (-20e-6, -60e-6). Surface is found per tile, so the slab follows uneven
    tissue rather than being absolute stage z. Either ordering is accepted.

    `min_health` is the classification model's score cutoff in [0, 1]; cells
    scoring below it are not queued. `max_cell_density` is cells per cubic
    metre, above which a tile counts as already crowded and is skipped rather
    than having more targets packed into it. `rescans_allowed` permits
    re-imaging tiles that have already been covered.
    """

    depth_range: tuple[float, float] = (-20e-6, -60e-6)
    min_health: float = 0.5
    # 5e12 cells/m^3 is 5 cells per (100 um)^3 -- dense for cortex, so the
    # default cap only rejects genuinely crowded tissue.
    max_cell_density: float = 5e12
    rescans_allowed: bool = False

    def __post_init__(self):
        near, far = self.depth_range
        if near > 0 or far > 0:
            raise ValueError(
                f"depth_range offsets must be at or below the surface (<= 0), got {self.depth_range}"
            )
        if near == far:
            raise ValueError(f"depth_range must span a nonzero thickness, got {self.depth_range}")
        if not 0.0 <= self.min_health <= 1.0:
            raise ValueError(f"min_health must be between 0 and 1, got {self.min_health}")
        if self.max_cell_density <= 0:
            raise ValueError(f"max_cell_density must be positive, got {self.max_cell_density}")

    def z_span(self) -> float:
        """Thickness of the searched slab, in metres."""
        near, far = self.depth_range
        return abs(near - far)

    def z_bounds(self, surface: float) -> tuple[float, float]:
        """Absolute (shallower, deeper) z for a tile whose surface is at `surface`."""
        near, far = self.depth_range
        return surface + max(near, far), surface + min(near, far)
```

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/slice.py acq4/experiment/tests/test_slice.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add SearchConstraints, the validated Area 2 search parameters

Depth range is a signed pair of offsets from the tissue surface, never a
queue length. Validation rejects a range above the surface, a zero-thickness
slab, an out-of-range health cutoff, and a nonpositive density cap.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 3: `Slice` — regions, coverage, and survey stats

`Slice` is the tissue-scoped state that outlives any one run. This task builds everything except `makeCellProducer()`, which Task 4 adds once there is a producer to make.

**Files:**
- Modify: `acq4/experiment/slice.py` (append `Slice`)
- Modify: `acq4/experiment/tests/test_slice.py` (append `Slice` tests)

**Interfaces:**
- Consumes: `SearchConstraints` from Task 2; `plan_grid`, `select_next`, `count_covered` from Task 1.
- Produces:
  - `Slice(fov: tuple[float, float], constraints: SearchConstraints | None = None, overlap: float = 0.0, directory=None)`
  - `slice_.addRegion(x0, y0, x1, y1) -> None`
  - `slice_.regions -> list[tuple[float, float, float, float]]` (read-only copy)
  - `slice_.constraints -> SearchConstraints`; `slice_.setConstraints(c) -> None`
  - `slice_.tileGrid() -> list[tuple[float, float]]` — every region's tiles concatenated, region order preserved
  - `slice_.nextTile() -> tuple[float, float] | None` — next uncovered tile; does **not** mark it
  - `slice_.markCovered(center) -> None`
  - `slice_.resetCoverage() -> None`
  - `slice_.coveredTiles -> list[tuple[float, float]]` (read-only copy)
  - `slice_.surveyStats() -> tuple[int, int, float]` — `(total_tiles, covered_tiles, percent)`
  - `slice_.tileVolume() -> float` — one tile's searched volume in m³
  - `slice_.registerCells(cells) -> None`; `slice_.cellsNearTile(center) -> list` — the density cap's bookkeeping
  - `slice_.threshold -> float` — the "same tile" match radius

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_slice.py`:

```python
from acq4.experiment.slice import Slice

# A 10x10 um FOV with no overlap, so a 30x30 um region is exactly a 3x3 grid of
# tiles and tile centers land on predictable coordinates.
FOV = (10e-6, 10e-6)


def make_slice(**kwargs):
    kwargs.setdefault("fov", FOV)
    return Slice(**kwargs)


class FakeCell:
    """Stand-in for acq4_automation's Cell: a global position and a health score."""

    def __init__(self, position, score=1.0):
        self.position = position
        self.score = score


def test_a_new_slice_has_no_regions_and_nothing_to_survey():
    s = make_slice()
    assert s.regions == []
    assert s.tileGrid() == []
    assert s.nextTile() is None
    assert s.surveyStats() == (0, 0, 0.0)


def test_adding_a_region_produces_a_tile_grid():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    assert len(s.tileGrid()) == 9
    assert s.surveyStats() == (9, 0, 0.0)


def test_regions_is_a_copy_so_callers_cannot_mutate_slice_state():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    s.regions.append((1, 1, 2, 2))
    assert len(s.regions) == 1


def test_a_second_region_extends_the_grid_without_disturbing_the_first():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    first = s.tileGrid()
    s.addRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6)
    both = s.tileGrid()
    assert both[: len(first)] == first
    assert len(both) == 18


def test_marking_a_tile_covered_advances_next_tile():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    first = s.nextTile()
    assert s.nextTile() == first, "nextTile must not mark; it only reports"
    s.markCovered(first)
    assert s.nextTile() != first
    assert s.surveyStats() == (9, 1, pytest.approx(100 / 9))


def test_next_tile_is_none_once_every_tile_is_covered():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    for _ in range(9):
        s.markCovered(s.nextTile())
    assert s.nextTile() is None
    assert s.surveyStats() == (9, 9, 100.0)


def test_coverage_survives_a_new_region_being_added():
    # Shared coverage is the whole point: a second region's survey must not
    # re-image the first region's tiles.
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    covered = s.nextTile()
    s.markCovered(covered)
    s.addRegion(1e-3, 1e-3, 1e-3 + 30e-6, 1e-3 + 30e-6)
    assert covered in s.coveredTiles
    assert s.surveyStats()[1] == 1


def test_reset_coverage_forgets_imaged_tiles_but_keeps_regions():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    s.markCovered(s.nextTile())
    s.resetCoverage()
    assert s.coveredTiles == []
    assert len(s.regions) == 1
    assert s.surveyStats() == (9, 0, 0.0)


def test_tile_volume_is_fov_area_times_the_depth_span():
    s = make_slice(constraints=SearchConstraints(depth_range=(-20e-6, -60e-6)))
    assert s.tileVolume() == pytest.approx(10e-6 * 10e-6 * 40e-6)


def test_registered_cells_are_found_near_their_own_tile_only():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    tile = s.nextTile()
    here = FakeCell((tile[0], tile[1], 0.0))
    far = FakeCell((tile[0] + 1e-3, tile[1], 0.0))
    s.registerCells([here, far])
    near = s.cellsNearTile(tile)
    assert here in near
    assert far not in near


def test_setting_constraints_replaces_them_wholesale():
    s = make_slice()
    replacement = SearchConstraints(min_health=0.9)
    s.setConstraints(replacement)
    assert s.constraints is replacement
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v
```

Expected: `ImportError: cannot import name 'Slice'`.

- [ ] **Step 3: Write the implementation**

Append to `acq4/experiment/slice.py` (and add `from .search_grid import count_covered, plan_grid, select_next` to its imports):

```python
class Slice:
    """The search state for one piece of tissue, and the source of its cell producers.

    Owns the regions to survey (global-coordinate rectangles), the coverage
    record of which field-of-view tiles have been imaged, the search
    constraints, and -- once a producer is made from it -- the tiles and cells
    that producer accumulates. Coverage is shared by every producer this slice
    makes: that is what stops a second region's survey from re-imaging the
    first's, and what gives `rescans_allowed` something to decide.

    A slice, its coverage, and its producers persist across orchestrator runs.
    They are replaced only when the operator starts a new slice. This is
    deliberately the opposite of Orchestrator._producerExhausted, which is a
    per-run cache: a producer that reported exhaustion is asked again next run,
    precisely so a slice that has gained a region can be surveyed further.

    Not a QObject: it holds no widgets, and staying a plain object keeps it
    refcount-freeable rather than depending on Qt teardown ordering.
    """

    def __init__(self, fov, constraints=None, overlap=0.0, directory=None):
        fov_w, fov_h = fov
        if fov_w <= 0 or fov_h <= 0:
            raise ValueError(f"fov must be positive in both axes, got {fov}")
        self._fov = (abs(fov_w), abs(fov_h))
        self._overlap = overlap
        self._constraints = constraints if constraints is not None else SearchConstraints()
        self._regions: list[tuple[float, float, float, float]] = []
        self._covered: list[tuple[float, float]] = []
        self._cells: list = []
        # The acq4 slice directory (a DirHandle) this state belongs to, kept so
        # a caller can write per-slice data alongside it. Not required for the
        # in-memory search itself.
        self.directory = directory

    # ---- constraints ----
    @property
    def constraints(self) -> SearchConstraints:
        return self._constraints

    def setConstraints(self, constraints: SearchConstraints) -> None:
        self._constraints = constraints

    # ---- regions ----
    @property
    def regions(self) -> list[tuple[float, float, float, float]]:
        """The search rectangles, as a copy: mutating the result changes nothing."""
        return list(self._regions)

    def addRegion(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Add a global-coordinate rectangle to survey. Coverage is untouched."""
        self._regions.append((x0, y0, x1, y1))

    # ---- tiles and coverage ----
    @property
    def threshold(self) -> float:
        """Distance below which two tile centers are the same tile."""
        fov_w, fov_h = self._fov
        step = min(fov_w - self._overlap, fov_h - self._overlap)
        if step <= 0:
            step = min(fov_w, fov_h)
        return step / 2

    def tileGrid(self) -> list[tuple[float, float]]:
        """Every region's tile centers, concatenated in the order regions were added."""
        grid: list[tuple[float, float]] = []
        fov_w, fov_h = self._fov
        for x0, y0, x1, y1 in self._regions:
            grid.extend(plan_grid(x0, y0, x1, y1, fov_w, fov_h, self._overlap))
        return grid

    def nextTile(self) -> tuple[float, float] | None:
        """The next tile center not yet covered, or None when all are.

        Reports only: the caller marks a tile covered once it has actually
        imaged it, so a tile abandoned by a stop is not silently skipped on the
        next run.
        """
        return select_next(self.tileGrid(), self._covered, self.threshold)

    def markCovered(self, center: tuple[float, float]) -> None:
        self._covered.append(tuple(center))

    def resetCoverage(self) -> None:
        """Forget which tiles have been imaged, keeping regions and constraints."""
        self._covered = []

    @property
    def coveredTiles(self) -> list[tuple[float, float]]:
        return list(self._covered)

    def surveyStats(self) -> tuple[int, int, float]:
        """(total tiles, covered tiles, percent covered) across every region."""
        grid = self.tileGrid()
        total = len(grid)
        covered = count_covered(grid, self._covered, self.threshold)
        percent = 100.0 * covered / total if total else 0.0
        return total, covered, percent

    def tileVolume(self) -> float:
        """The volume one tile searches: FOV area times the constrained depth span."""
        fov_w, fov_h = self._fov
        return fov_w * fov_h * self._constraints.z_span()

    # ---- cells found in this tissue ----
    def registerCells(self, cells) -> None:
        """Record cells found in this slice, for the density cap's bookkeeping."""
        self._cells.extend(cells)

    def cellsNearTile(self, center: tuple[float, float]) -> list:
        """Registered cells whose position falls within `center`'s tile."""
        cx, cy = center
        fov_w, fov_h = self._fov
        found = []
        for cell in self._cells:
            pos = cell.position
            if abs(pos[0] - cx) <= fov_w / 2 and abs(pos[1] - cy) <= fov_h / 2:
                found.append(cell)
        return found
```

Note `cell.position` is indexed, not attribute-accessed per axis: `acq4_automation.feature_tracking.cell.Cell` holds a `coorx.Point`, which supports indexing, and the tests' `FakeCell` uses a plain tuple.

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v
```

Expected: 18 passed.

- [ ] **Step 5: Mutation-verify the two absence-shaped assertions**

`test_marking_a_tile_covered_advances_next_tile` asserts `nextTile()` does *not* mark, and `test_coverage_survives_a_new_region_being_added` asserts coverage is *not* lost. Both could pass against broken code.

First, make `nextTile` mark the tile it returns:

```python
    def nextTile(self):
        center = select_next(self.tileGrid(), self._covered, self.threshold)
        if center is not None:
            self.markCovered(center)      # DEFECT: nextTile must only report
        return center
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py::test_marking_a_tile_covered_advances_next_tile -v
```

Expected: FAIL on `assert s.nextTile() == first, "nextTile must not mark; it only reports"`. Revert the defect.

Second, make `addRegion` clear coverage (the mistake `SurveyRegion.addRegion` actually makes — it calls `clearRegion()` first):

```python
    def addRegion(self, x0, y0, x1, y1):
        self._covered = []                # DEFECT: coverage is shared, not per-region
        self._regions.append((x0, y0, x1, y1))
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py::test_coverage_survives_a_new_region_being_added -v
```

Expected: FAIL on `assert covered in s.coveredTiles`. Revert the defect.

- [ ] **Step 6: Re-run and commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -q
```

Expected: 18 passed.

```bash
git add acq4/experiment/slice.py acq4/experiment/tests/test_slice.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add Slice, the per-tissue search state

Owns the regions to survey, the shared coverage record, the search
constraints, and the cells found in this tissue. Coverage is shared across
regions and across producers, which is what stops a second region's survey
from re-imaging the first's.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 4: `CellProducer` — the tile walk and the exhaustion contract

The callable the orchestrator's refill hook takes. This task builds the walk and the `[]`-vs-`None` contract; Task 5 adds filtering.

**Files:**
- Create: `acq4/experiment/cell_producer.py`
- Create: `acq4/experiment/tests/test_cell_producer.py`
- Modify: `acq4/experiment/slice.py` (add `makeCellProducer`)
- Modify: `acq4/experiment/tests/test_slice.py` (add the `makeCellProducer` test)

**Interfaces:**
- Consumes: `Slice` (`nextTile`, `markCovered`, `constraints`, `registerCells`, `cellsNearTile`, `tileVolume`, `resetCoverage`) from Task 3.
- Produces:
  - `CellProducer(slice_, detector)` with `__call__() -> list | None`.
  - `detector(center: tuple[float, float], constraints: SearchConstraints) -> Sequence` — the injected seam. Returns candidate objects each exposing `.position` (indexable, global metres) and `.score` (health prediction in `[0, 1]`).
  - `Slice.makeCellProducer(detector) -> CellProducer`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_cell_producer.py`:

```python
"""Tests for CellProducer: walking a slice's tiles, the []-versus-None
exhaustion contract, and the search constraints it filters candidates against."""

import pytest

from acq4.experiment.cell_producer import CellProducer
from acq4.experiment.slice import SearchConstraints, Slice

FOV = (10e-6, 10e-6)


class FakeCandidate:
    """Stand-in for a detected cell: a global position and a health score."""

    def __init__(self, position, score=1.0):
        self.position = position
        self.score = score

    def __repr__(self):
        return f"FakeCandidate({self.position}, score={self.score})"


class RecordingDetector:
    """A detector seam that returns scripted results and records its calls.

    `results` maps nothing -- it is consumed in order, one entry per call, each
    entry being the list of candidates that call returns. Running past the end
    returns an empty list (a barren tile), which is the common real case.
    """

    def __init__(self, results=()):
        self._results = list(results)
        self.calls = []

    def __call__(self, center, constraints):
        self.calls.append((tuple(center), constraints))
        return self._results.pop(0) if self._results else []


def make_slice(constraints=None, regions=((0, 0, 30e-6, 30e-6),)):
    s = Slice(fov=FOV, constraints=constraints)
    for r in regions:
        s.addRegion(*r)
    return s


def test_a_call_images_one_tile_and_returns_its_cells():
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))
    detector = RecordingDetector([[cell]])
    producer = CellProducer(s, detector)

    assert producer() == [cell]
    assert detector.calls[0][0] == tile


def test_the_imaged_tile_is_marked_covered_so_the_next_call_advances():
    s = make_slice()
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    producer()
    producer()

    assert detector.calls[0][0] != detector.calls[1][0]
    assert len(s.coveredTiles) == 2


def test_a_barren_tile_returns_empty_not_none():
    # [] is "made progress, found nothing here, ask again"; None would end the
    # whole run on the first empty field of view.
    s = make_slice()
    producer = CellProducer(s, RecordingDetector([[]]))
    result = producer()
    assert result == []
    assert result is not None


def test_none_only_once_every_tile_is_imaged():
    s = make_slice(regions=((0, 0, 10e-6, 10e-6),))  # exactly one tile
    producer = CellProducer(s, RecordingDetector())

    assert producer() == []
    assert producer() is None


def test_a_slice_with_no_regions_is_exhausted_immediately():
    s = Slice(fov=FOV)
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() is None
    assert detector.calls == [], "nothing to image, so the detector must not run"


def test_the_detector_receives_the_slices_current_constraints():
    constraints = SearchConstraints(min_health=0.0, depth_range=(-5e-6, -25e-6))
    s = make_slice(constraints=constraints)
    detector = RecordingDetector()
    CellProducer(s, detector)()
    assert detector.calls[0][1] is constraints


def test_found_cells_are_registered_with_the_slice():
    s = make_slice()
    tile = s.nextTile()
    cell = FakeCandidate((tile[0], tile[1], -30e-6))
    CellProducer(s, RecordingDetector([[cell]]))()
    assert s.cellsNearTile(tile) == [cell]


def test_a_detector_failure_marks_the_tile_covered_rather_than_retrying_it_forever():
    # A tile that raises must not be handed out again on the next call: the
    # orchestrator wraps a producer exception into AbortExperiment, but a
    # producer used across runs would otherwise wedge on the same bad tile.
    s = make_slice()
    tile = s.nextTile()

    def exploding(center, constraints):
        raise RuntimeError("imaging failed")

    producer = CellProducer(s, exploding)
    with pytest.raises(RuntimeError, match="imaging failed"):
        producer()
    assert tile in s.coveredTiles
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py -v
```

Expected: `ModuleNotFoundError: No module named 'acq4.experiment.cell_producer'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/experiment/cell_producer.py`:

```python
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
```

Then append `makeCellProducer` to `Slice` in `acq4/experiment/slice.py`:

```python
    def makeCellProducer(self, detector) -> "CellProducer":
        """A producer that surveys this slice, one tile per call.

        This slice keeps no reference to what it hands back. The producer holds
        the slice, the orchestrator holds the producer, and that one-way chain
        is refcount-freeable; storing producers here would close it into a cycle
        only the cyclic GC could reclaim.
        """
        from .cell_producer import CellProducer

        return CellProducer(self, detector)
```

The import is function-local to keep `slice.py` and `cell_producer.py` from importing each other at module scope.

- [ ] **Step 4: Add the `makeCellProducer` test**

Append to `acq4/experiment/tests/test_slice.py`:

```python
def test_make_cell_producer_returns_a_view_the_slice_does_not_retain():
    s = make_slice()
    s.addRegion(0, 0, 30e-6, 30e-6)
    producer = s.makeCellProducer(lambda center, constraints: [])
    assert producer() == []
    # The slice must not be reachable back to the producer, or the pair is a
    # reference cycle. Nothing on the slice may hold it.
    assert not any(v is producer for v in vars(s).values())
```

- [ ] **Step 5: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py acq4/experiment/tests/test_slice.py -v
```

Expected: 9 + 19 = 28 passed.

- [ ] **Step 6: Mutation-verify the contract tests**

`test_a_barren_tile_returns_empty_not_none` and `test_none_only_once_every_tile_is_imaged` are the two halves of the contract; a broken producer can pass one. Collapse the distinction:

```python
    def __call__(self):
        tile = self._slice.nextTile()
        if tile is None:
            return None
        try:
            candidates = self._detector(tile, self._slice.constraints)
        finally:
            self._slice.markCovered(tile)
        cells = list(candidates)
        if not cells:
            return None               # DEFECT: a barren tile is not exhaustion
        self._slice.registerCells(cells)
        return cells
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py -v
```

Expected: `test_a_barren_tile_returns_empty_not_none` FAILS on `assert result == []`. Revert.

Then verify the tile-marking test is not vacuous by removing the `finally`:

```python
        candidates = self._detector(tile, self._slice.constraints)
        self._slice.markCovered(tile)     # DEFECT: not marked when imaging raises
```

Expected: `test_a_detector_failure_marks_the_tile_covered_rather_than_retrying_it_forever` FAILS on `assert tile in s.coveredTiles`. Revert.

- [ ] **Step 7: Commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -q
```

Expected: all pass.

```bash
git add acq4/experiment/cell_producer.py acq4/experiment/tests/test_cell_producer.py acq4/experiment/slice.py acq4/experiment/tests/test_slice.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add CellProducer, surveying one slice tile per call

Satisfies the orchestrator's producer contract: [] for a barren tile that
should be asked again, None only once every tile is imaged. The imaging step
is an injected seam so the tile walk is testable without a microscope.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 5: `CellProducer` — health cutoff, density cap, and rescans

The three remaining Area 2 constraints. `depth_range` is already passed through to the detector (it is the detector's job to acquire over it); these three are the producer's own filtering.

**Files:**
- Modify: `acq4/experiment/cell_producer.py`
- Modify: `acq4/experiment/tests/test_cell_producer.py`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces: no new public names. `CellProducer.__call__` now filters by `constraints.min_health`, skips tiles already at `constraints.max_cell_density`, and honours `constraints.rescans_allowed`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_cell_producer.py`:

```python
def test_candidates_below_the_health_cutoff_are_not_queued():
    s = make_slice(constraints=SearchConstraints(min_health=0.6))
    tile = s.nextTile()
    good = FakeCandidate((tile[0], tile[1], -30e-6), score=0.9)
    bad = FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6), score=0.3)
    producer = CellProducer(s, RecordingDetector([[good, bad]]))

    assert producer() == [good]


def test_a_candidate_exactly_at_the_cutoff_is_kept():
    s = make_slice(constraints=SearchConstraints(min_health=0.6))
    tile = s.nextTile()
    borderline = FakeCandidate((tile[0], tile[1], -30e-6), score=0.6)
    assert CellProducer(s, RecordingDetector([[borderline]]))() == [borderline]


def test_a_tile_whose_every_candidate_is_rejected_returns_empty_not_none():
    # Filtering everything out is still "made progress on a tile"; reporting it
    # as exhaustion would end the run.
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    producer = CellProducer(s, RecordingDetector([[weak]]))
    result = producer()
    assert result == []
    assert result is not None


def test_rejected_candidates_are_not_registered_with_the_slice():
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    weak = FakeCandidate((tile[0], tile[1], -30e-6), score=0.1)
    CellProducer(s, RecordingDetector([[weak]]))()
    assert s.cellsNearTile(tile) == []


def test_a_candidate_without_a_score_passes_the_cutoff():
    # "Add from target" cells and any detector that does not score its output
    # must not be silently discarded by a nonzero cutoff.
    s = make_slice(constraints=SearchConstraints(min_health=0.9))
    tile = s.nextTile()
    unscored = FakeCandidate((tile[0], tile[1], -30e-6))
    unscored.score = None
    assert CellProducer(s, RecordingDetector([[unscored]]))() == [unscored]


def _crowding_constraints(cells_per_tile):
    """Constraints whose density cap is reached by `cells_per_tile` in one tile."""
    volume = 10e-6 * 10e-6 * 40e-6
    return SearchConstraints(
        depth_range=(-20e-6, -60e-6),
        min_health=0.0,
        max_cell_density=cells_per_tile / volume,
    )


def test_a_tile_already_at_the_density_cap_is_skipped_without_imaging():
    s = make_slice(constraints=_crowding_constraints(2))
    tile = s.nextTile()
    s.registerCells([
        FakeCandidate((tile[0], tile[1], -30e-6)),
        FakeCandidate((tile[0] + 1e-6, tile[1], -30e-6)),
    ])
    detector = RecordingDetector([[FakeCandidate((tile[0], tile[1], -30e-6))]])
    producer = CellProducer(s, detector)

    assert producer() == []
    assert detector.calls == [], "a crowded tile must not be imaged at all"
    assert tile in s.coveredTiles, "and it must not be handed out again"


def test_a_tile_below_the_density_cap_is_imaged_normally():
    s = make_slice(constraints=_crowding_constraints(2))
    tile = s.nextTile()
    s.registerCells([FakeCandidate((tile[0], tile[1], -30e-6))])
    found = FakeCandidate((tile[0], tile[1], -35e-6))
    detector = RecordingDetector([[found]])

    assert CellProducer(s, detector)() == [found]
    assert len(detector.calls) == 1


def test_without_rescans_exhaustion_is_final():
    s = make_slice(regions=((0, 0, 10e-6, 10e-6),),
                   constraints=SearchConstraints(rescans_allowed=False))
    producer = CellProducer(s, RecordingDetector())
    producer()
    assert producer() is None
    assert producer() is None


def test_rescans_allowed_grants_exactly_one_more_pass():
    # Unlimited rescanning could never return None, which would wedge the run
    # loop; one extra pass makes the switch mean something and keeps the
    # contract. See CellProducer's docstring.
    s = make_slice(regions=((0, 0, 10e-6, 10e-6),),
                   constraints=SearchConstraints(rescans_allowed=True))
    detector = RecordingDetector()
    producer = CellProducer(s, detector)

    assert producer() == []          # first pass images the only tile
    assert producer() == []          # rescan re-images it
    assert producer() is None        # and then it really is exhausted
    assert len(detector.calls) == 2


def test_a_second_producer_from_the_same_slice_gets_its_own_rescan_allowance():
    # The allowance is per-producer, matching _producerExhausted's per-run
    # lifetime, so a later run over the same slice may rescan again.
    s = make_slice(regions=((0, 0, 10e-6, 10e-6),),
                   constraints=SearchConstraints(rescans_allowed=True))
    first = s.makeCellProducer(RecordingDetector())
    first()
    first()
    assert first() is None

    second = s.makeCellProducer(RecordingDetector())
    assert second() == []
    assert second() is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py -v
```

Expected: `test_candidates_below_the_health_cutoff_are_not_queued` fails (both candidates returned), and the density/rescan tests fail similarly. Confirm each of the 11 new tests fails for the stated reason rather than erroring on a typo.

- [ ] **Step 3: Write the implementation**

Replace `CellProducer.__call__` in `acq4/experiment/cell_producer.py` and add the rescan state to `__init__`:

```python
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
        volume = self._slice.tileVolume()
        if volume <= 0:
            return False
        density = len(self._slice.cellsNearTile(tile)) / volume
        return density >= constraints.max_cell_density
```

Extend the class docstring's final paragraph to record the rescan decision:

```python
    `rescans_allowed` grants exactly one extra pass over the slice's tiles, not
    unlimited rescanning: a producer that could always find another tile would
    never return None, and the orchestrator's refill loop would never end.
```

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py -v
```

Expected: 20 passed.

- [ ] **Step 5: Mutation-verify the three absence-shaped assertions**

(a) The crowded tile must not be imaged. Change `_isCrowded`'s comparison to `>` so a tile *at* the cap is imaged:

```python
        return density > constraints.max_cell_density   # DEFECT: at the cap is crowded
```

Expected: `test_a_tile_already_at_the_density_cap_is_skipped_without_imaging` FAILS on `assert detector.calls == []`. Revert.

(b) The rescan allowance must be spent. Remove the `self._rescanned` guard:

```python
        if not self._slice.constraints.rescans_allowed:
            return None
        self._slice.resetCoverage()        # DEFECT: unbounded rescanning
```

Expected: `test_rescans_allowed_grants_exactly_one_more_pass` FAILS on `assert producer() is None`. Revert.

(c) A fully-filtered tile must not read as exhaustion. Return `None` for an empty filtered list:

```python
        cells = [c for c in candidates if self._isHealthy(c, constraints)]
        if not cells:
            return None                    # DEFECT: filtered-out is not exhausted
```

Expected: `test_a_tile_whose_every_candidate_is_rejected_returns_empty_not_none` FAILS. Revert.

- [ ] **Step 6: Commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -q
```

Expected: all pass.

```bash
git add acq4/experiment/cell_producer.py acq4/experiment/tests/test_cell_producer.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: filter produced cells by health, density, and rescan policy

A tile at the density cap is skipped without being imaged; candidates below
the health cutoff are dropped without being registered; both still report []
rather than exhaustion. rescans_allowed grants one extra pass, since an
unbounded one could never return None.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 6: Prove the slice/producer graph is refcount-freeable

P1.5's exit segfault came from parentless `QObject`s cross-wired into a cycle only the cyclic GC could reclaim, and P2a added a leak test for the producer. `Slice` and `CellProducer` are new long-lived objects in that same graph, so they get the same proof.

**Files:**
- Modify: `acq4/experiment/tests/test_cell_producer.py`

**Interfaces:**
- Consumes: `Slice`, `CellProducer`.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_cell_producer.py`:

```python
def test_slice_and_producer_are_freed_by_refcounting_alone():
    """No cycle between a slice and the producers it makes.

    Both outlive individual runs and neither is a QObject, so they must be
    reclaimable without the cyclic collector -- the failure mode that produced
    P1.5's exit segfault was a graph only gc could break, collected
    non-deterministically and possibly off the GUI thread.
    """
    import gc
    import weakref

    s = Slice(fov=FOV)
    s.addRegion(0, 0, 30e-6, 30e-6)
    producer = s.makeCellProducer(RecordingDetector())
    producer()

    slice_ref = weakref.ref(s)
    producer_ref = weakref.ref(producer)

    gc.disable()
    try:
        del producer
        assert producer_ref() is None, "producer survived; a cycle holds it"
        del s
        assert slice_ref() is None, "slice survived; a cycle holds it"
    finally:
        gc.enable()
```

- [ ] **Step 2: Run it**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py::test_slice_and_producer_are_freed_by_refcounting_alone -v
```

Expected: PASS — Tasks 3–5 already avoid the cycle deliberately (`makeCellProducer` stores nothing). A test that passes immediately is exactly the vacuous shape the global constraints warn about, so Step 3 is mandatory, not optional.

- [ ] **Step 3: Mutation-verify by introducing the cycle**

Make `Slice.makeCellProducer` retain what it hands out — the natural mistake:

```python
    def makeCellProducer(self, detector) -> "CellProducer":
        from .cell_producer import CellProducer

        producer = CellProducer(self, detector)
        self._producers = getattr(self, "_producers", [])
        self._producers.append(producer)      # DEFECT: closes the cycle
        return producer
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_cell_producer.py::test_slice_and_producer_are_freed_by_refcounting_alone -v
```

Expected: FAIL on `assert producer_ref() is None, "producer survived; a cycle holds it"`. Revert the defect.

Also confirm the `makeCellProducer` test from Task 4 catches it:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py::test_make_cell_producer_returns_a_view_the_slice_does_not_retain -v
```

Expected: with the defect applied, FAIL; after reverting, PASS.

- [ ] **Step 4: Commit**

```bash
git add acq4/experiment/tests/test_cell_producer.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
test: prove a slice and its producers are freed without the cyclic collector

Both outlive individual runs, so a cycle between them would only be reclaimed
non-deterministically -- the shape behind the P1.5 exit segfault. Verified by
introducing the cycle and watching the test fail.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 7: Orchestrator — the `"surveying"` status, and `clearQueue()`

Three engine changes. The first two close a P2a review deferral: nothing in `sigStatus` distinguishes surveying from patching, and `sigCurrentCell` still holds the finished cell while the producer images — which is what made P2a's Critical reachable in the first place. The third is needed by Task 11: "New slice" clears the cell list, and `CellPanel.clearCells()` only clears the panel's own bookkeeping, leaving the orchestrator's deque still holding cells in tissue that is no longer under the objective.

**Files:**
- Modify: `acq4/experiment/orchestrator.py:23-27` (signal docstring), `:158-217` (`_runLoopBody`), plus a new `clearQueue`
- Modify: `acq4/experiment/tests/test_orchestrator_producer.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `sigStatus` may now emit `"surveying"`; `Orchestrator.clearQueue() -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_orchestrator_producer.py`. Follow the existing file's fixtures — it already has `make_producer(batches)` and takes `make_pf` from `acq4/experiment/tests/conftest.py`; read the top of the file before writing so the helper use matches.

```python
def test_surveying_status_is_emitted_around_a_refill(make_pf):
    orch = Orchestrator(make_pf())
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.setCellProducer(make_producer([[object()], None]))

    orch.run_sync()

    assert "surveying" in statuses
    # And it must not be the last word: the run reports back to running for the
    # cell it then works, and waiting once drained.
    assert statuses.index("surveying") < statuses.index("waiting")


def test_a_barren_survey_reports_surveying_without_ever_reporting_running(make_pf):
    # The operator watching a slow, empty stretch of region must see
    # "surveying", not a stale "running" that implies a cell is being patched.
    orch = Orchestrator(make_pf())
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.setCellProducer(make_producer([[], [], None]))

    orch.run_sync()

    assert statuses.count("surveying") == 3


def test_current_cell_is_cleared_before_the_producer_runs(make_pf):
    # sigCurrentCell must not still name the just-finished cell while the
    # producer images: Area 5 would attribute survey time to that cell, and it
    # is the state that made P2a's next-cell Critical reachable.
    pf = make_pf()
    first = object()
    orch = Orchestrator(pf)
    orch.enqueue(first)

    seen = []
    orch.sigCurrentCell.connect(seen.append)

    def producer():
        # Whatever the orchestrator last announced must not be `first`.
        assert seen[-1] is None, f"still following {seen[-1]!r} while surveying"
        return None

    orch.setCellProducer(producer)
    orch.run_sync()

    assert first in seen


def test_clear_queue_drops_pending_cells(make_pf):
    orch = Orchestrator(make_pf())
    ran = []
    orch.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)
    orch.enqueue(object())
    orch.enqueue(object())

    orch.clearQueue()
    orch.run_sync()

    assert ran == []


def test_clear_queue_leaves_a_later_enqueue_working(make_pf):
    orch = Orchestrator(make_pf())
    ran = []
    orch.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)
    orch.enqueue(object())
    orch.clearQueue()
    kept = object()
    orch.enqueue(kept)

    orch.run_sync()

    assert ran == [kept]
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v -k "surveying or current_cell_is_cleared or clear_queue"
```

Expected: the two `surveying` tests fail on `assert "surveying" in statuses`; `test_current_cell_is_cleared_before_the_producer_runs` fails its in-producer assertion (or `IndexError` on `seen[-1]` when no cell ran before the producer — if so, seed the queue so a cell always precedes the refill, as written above); the two `clear_queue` tests fail with `AttributeError: 'Orchestrator' object has no attribute 'clearQueue'`.

- [ ] **Step 3: Write the implementation**

In `acq4/experiment/orchestrator.py`, update the signal declaration comment:

```python
    sigStatus = Qt.Signal(str)                 # "running"/"surveying"/"waiting"/"paused"/"error"
```

Add `clearQueue` next to `enqueue`:

```python
    def clearQueue(self) -> None:
        """Drop every cell waiting in the queue, leaving any running cell alone.

        The caller that seeded these cells is discarding them -- the operator
        has swapped the tissue, so every queued position is a place not to
        drive a pipette. Clearing the panel's own bookkeeping is not enough:
        the deque is a separate strong reference and would otherwise keep
        handing those positions to the protocol.
        """
        self._queue.clear()
```

In `_runLoopBody`, replace the refill branch:

```python
                if self._shouldRefill():
                    # Surveying is not patching, and the operator watching a
                    # slow, barren stretch of region must not read a stale
                    # "running" as "a cell is being worked". Clearing the
                    # current cell first is the same honesty: leaving the
                    # just-finished cell named here made Area 5 attribute
                    # survey time to it.
                    self.sigCurrentCell.emit(None)
                    self.sigStatus.emit("surveying")
                    self._refillQueue()
                    # Refill only ever runs against an empty queue, so a
                    # request that arrived while the producer was working had
                    # no cell to advance past: nothing was running and nothing
                    # was queued. Consuming it against the first cell the
                    # producer then returned would skip a cell the operator
                    # never saw, without it ever being attempted.
                    self._nextCellRequested = False
                    # Back to the top rather than falling through to a cell:
                    # re-checks pause and stop between refills, and lets a
                    # producer returning [] be asked again next pass. Imaging
                    # a tile is slow, so an operator pressing Stop mid-survey
                    # must not have to wait out a refill that already started.
                    continue
```

`_processCell` already emits `"running"` at the top of its retry loop, so a cell worked after a refill puts the status back without further change.

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v
```

Expected: all pass, including the 18 pre-existing tests.

- [ ] **Step 5: Mutation-verify the current-cell clear**

`test_current_cell_is_cleared_before_the_producer_runs` asserts an *absence* (that a stale cell is not still named). Remove the clear:

```python
                if self._shouldRefill():
                    self.sigStatus.emit("surveying")     # DEFECT: no sigCurrentCell(None)
                    self._refillQueue()
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py::test_current_cell_is_cleared_before_the_producer_runs -v
```

Expected: FAIL on `assert seen[-1] is None, f"still following ..."`. Revert.

- [ ] **Step 6: Run the whole engine suite and commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -q
```

Expected: all pass. Confirm no pre-existing test asserted an exact `sigStatus` sequence that a new `"surveying"` entry now breaks; if one did, update it to expect the new value rather than filtering it out.

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_producer.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: report a distinct surveying status and add Orchestrator.clearQueue

Surveying is not patching: the status now says so, and the current cell is
cleared before the producer runs so a finished cell stops being credited with
survey time. clearQueue lets a caller discarding its cells drop the deque's
separate strong reference to them.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 8: StatusPanel — gate the buttons during a survey

`_updateButtons`' final `else` disables *every* button for an unrecognised status. With Task 7 in place that means an operator watching a long survey cannot press Stop — the exact situation design §3.2 says Stop must work in ("imaging a tile is slow, so an operator pressing Stop during a barren stretch of region must not wait for the producer to find something first").

**Files:**
- Modify: `acq4/modules/Autopatch/status_panel.py:130-181`
- Modify: `acq4/modules/Autopatch/tests/test_status_panel.py`

**Interfaces:**
- Consumes: `"surveying"` from `Orchestrator.sigStatus` (Task 7).
- Produces: `StatusPanel.sigStatusChanged = Qt.Signal(str)` — the bound orchestrator's status, re-emitted. Task 11's window listens to this to refresh the survey readout as tiles are imaged, rather than connecting itself to the orchestrator directly; the orchestrator is a parentless `QObject` and giving it a reference back to the window is the cycle shape that caused P1.5's exit segfault, which is why `sigInteractionLocked` already exists instead of a direct connection.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_status_panel.py`. The file has no `qtbot`/fixture-based panel setup: every test takes the module-scoped `qapp` fixture, constructs `StatusPanel()` inline, and binds it to the file's `_FakeOrchestrator()` and `_FakeEntrySource()`. Match that, and capture signals with a plain list rather than `qtbot.waitSignal`.

```python
def _boundPanel():
    """A StatusPanel bound to a fake orchestrator, as every test here builds it."""
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    return panel, orch


def test_surveying_keeps_stop_and_pause_available(qapp):
    # Imaging a tile is slow. An operator who wants out mid-survey must not
    # have to wait for the producer to find a cell first.
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")

    assert panel.stopBtn.isEnabled()
    assert panel.pauseBtn.isEnabled()
    assert not panel.startBtn.isEnabled()


def test_surveying_disables_next_cell(qapp):
    # A next-cell request during a refill is discarded by design (nothing is
    # running and nothing is queued to advance past), so the button must not
    # invite a press that does nothing.
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")

    assert not panel.nextBtn.isEnabled()


def test_surveying_shows_in_the_status_label(qapp):
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")
    assert panel.statusLabel.text() == "surveying"


def test_surveying_locks_area_4(qapp):
    # A run is in flight, so the protocol picker must stay locked -- reloading
    # a protocol mid-survey is the second-orchestrator hazard.
    panel, orch = _boundPanel()
    locked = []
    panel.sigInteractionLocked.connect(locked.append)
    orch.sigStatus.emit("surveying")
    assert locked[-1] is True


def test_surveying_keeps_pause_labeled_pause(qapp):
    panel, orch = _boundPanel()
    orch.sigStatus.emit("surveying")
    assert panel.pauseBtn.text() == "Pause"


def test_status_is_re_emitted_for_panels_that_must_not_touch_the_orchestrator(qapp):
    # The window needs the status to refresh Area 2's survey readout, but the
    # orchestrator is a parentless QObject and must not hold a reference back
    # to the window. This passthrough is that indirection.
    panel, orch = _boundPanel()
    seen = []
    panel.sigStatusChanged.connect(seen.append)

    orch.sigStatus.emit("surveying")
    orch.sigStatus.emit("waiting")

    assert seen == ["surveying", "waiting"]


def test_the_status_passthrough_stops_on_unbind(qapp):
    panel, orch = _boundPanel()
    seen = []
    panel.sigStatusChanged.connect(seen.append)

    panel.unbindOrchestrator()
    orch.sigStatus.emit("surveying")

    assert seen == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v -k "surveying or passthrough"
```

Expected: `test_surveying_keeps_stop_and_pause_available` and `test_surveying_locks_area_4` FAIL (the `else` branch disables everything and `sigInteractionLocked` emits `False`); the two passthrough tests FAIL with `AttributeError: 'StatusPanel' object has no attribute 'sigStatusChanged'`. `test_surveying_disables_next_cell`, `test_surveying_shows_in_the_status_label`, and `test_surveying_keeps_pause_labeled_pause` pass already — for the wrong reason, which Step 4 pins down.

- [ ] **Step 3: Write the implementation**

In `acq4/modules/Autopatch/status_panel.py`, declare the passthrough signal next to `sigInteractionLocked`:

```python
    # The bound orchestrator's status, re-emitted for panels that need it but
    # must not connect to the orchestrator themselves. The orchestrator is a
    # parentless QObject, so a connection from it to the window would give it a
    # reference back and rebuild the cycle bindOrchestrator/unbindOrchestrator
    # exist to avoid -- the same reason sigInteractionLocked is routed this way.
    sigStatusChanged = Qt.Signal(str)
```

Emit it from `_onStatus`, and extend the lock condition there:

```python
        self.sigInteractionLocked.emit(status in ("running", "surveying", "paused"))
        self.sigStatusChanged.emit(status)
```

and add a `"surveying"` branch to `_updateButtons`, updating its docstring:

```python
    def _updateButtons(self) -> None:
        """Gate Start/Stop/Pause/Next on whether a protocol is loaded (an
        orchestrator is bound) and the orchestrator's last-reported status.

        No protocol bound: everything disabled. Otherwise: "waiting" (or no
        status yet, i.e. freshly bound and not yet started) enables only
        Start; "running" enables Stop/Pause/Next; "surveying" enables
        Stop/Pause but not Next, since a next-cell request during a refill is
        discarded (nothing is running and nothing is queued to advance past);
        "paused" enables Stop/Pause (relabeled "Resume") but not Next;
        "error" enables only Stop.
        """
        hasProtocol = self._orchestrator is not None
        status = self._currentStatus
        if not hasProtocol:
            start = stop = pause = next_ = False
        elif status in (None, "waiting"):
            start, stop, pause, next_ = True, False, False, False
        elif status == "running":
            start, stop, pause, next_ = False, True, True, True
        elif status == "surveying":
            start, stop, pause, next_ = False, True, True, False
        elif status == "paused":
            start, stop, pause, next_ = False, True, True, False
        elif status == "error":
            start, stop, pause, next_ = False, True, False, False
        else:
            start, stop, pause, next_ = False, False, False, False
```

- [ ] **Step 4: Run to verify they pass, then mutation-verify the two that passed early**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v
```

Expected: all pass.

`test_surveying_disables_next_cell` passed before the fix because the catch-all `else` disabled everything, so it does not yet prove the `"surveying"` branch. Apply the plausible-but-wrong version that treats surveying exactly like running:

```python
        elif status in ("running", "surveying"):
            start, stop, pause, next_ = False, True, True, True   # DEFECT
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v -k surveying
```

Expected: `test_surveying_disables_next_cell` FAILS. Revert.

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/status_panel.py acq4/modules/Autopatch/tests/test_status_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: gate Area 3's buttons for the surveying status

Stop and Pause stay available during a survey -- imaging a tile is slow and
an operator must not have to wait for a cell to be found. Next cell is
disabled, since a request during a refill is discarded by design.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 9: The real tile detector

The one function that touches devices: move the stage to a tile, find that tile's surface, acquire a stack across the constrained depth range, detect and score cells, and build `Cell` objects with their trackers seeded from that stack. Modelled on `AutomationDebug/detection.py:_detectNeuronsZStack` and `autopatch.py:_autopatchFindCell`, which are the working reference for every one of these calls.

The device calls themselves cannot be exercised headlessly, but the orchestration around them can, and it holds the mistakes worth catching: the sign of the depth arithmetic, restoring focus on the failure path, and honouring a stop between slow steps. So the file is deliberately split — `detect()` sequences, and `_acquire`/`_detect`/`_newCell`/`_health_models` are module-level functions a test replaces with fakes via `monkeypatch.setattr`. No production seam is added for testability beyond that split, and no test asserts a call sequence for its own sake.

**Files:**
- Create: `acq4/experiment/tile_detector.py`
- Create: `acq4/experiment/tests/test_tile_detector.py`

**Interfaces:**
- Consumes: `SearchConstraints.z_bounds(surface)` (Task 2).
- Produces: `make_tile_detector(camera, scope, manager, step_z=1e-6, min_volume_m3=0.0, max_candidates=5) -> Callable[[tuple[float, float], SearchConstraints], list]`. The returned callable is the `detector` seam `CellProducer` takes (Task 4), and runs on the orchestrator's worker thread. Module-level helpers `_acquire(camera, start_z, stop_z, step_z) -> list`, `_detect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates) -> list[tuple]`, `_newCell(position) -> Cell`, `_health_models(manager) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_tile_detector.py`:

```python
"""Tests for the tile detector's orchestration: the depth arithmetic it derives
from each tile's surface, focus restoration, stop handling, and cell construction."""

import pytest

from acq4.experiment import tile_detector
from acq4.experiment.slice import SearchConstraints
from acq4.util.task import Stopped


class FakeScope:
    def __init__(self, surface=0.0):
        self.surface = surface
        self.moves = []

    def setGlobalPosition(self, pos, speed="fast", name=None):
        self.moves.append(tuple(pos))
        return FakeFuture()

    def findSurfaceDepth(self, imager):
        return self.surface


class FakeFuture:
    def wait(self, **kwargs):
        return None


class FakeCamera:
    def __init__(self, focus=-1e-3):
        self._focus = focus
        self.focusSets = []

    def name(self):
        return "FakeCamera"

    def getFocusDepth(self):
        return self._focus

    def setFocusDepth(self, z, speed="fast", name=None):
        self.focusSets.append(z)
        return FakeFuture()

    def getPixelSize(self):
        return (0.32e-6, 0.32e-6)


class FakeCell:
    """Stand-in for acq4_automation's Cell; `trackerFails` makes tracker init raise."""

    trackerFails = False

    def __init__(self, position):
        self.position = position
        self.score = None
        self.trackerInits = 0

    def initializeTrackerFromStack(self, camera, stack, use_cellpose=False):
        self.trackerInits += 1
        if self.trackerFails:
            raise ValueError("cell too close to the stack edge")


@pytest.fixture
def rig(monkeypatch):
    """A detector wired to fake devices, with the device-touching helpers replaced.

    Returns a namespace carrying the camera, the scope, the recorded _acquire
    arguments, and the detector callable itself.
    """
    camera = FakeCamera()
    scope = FakeScope(surface=-500e-6)
    acquireCalls = []
    detectCalls = []

    def fakeAcquire(cam, start_z, stop_z, step_z):
        acquireCalls.append((start_z, stop_z, step_z))
        return ["frame"]

    def fakeDetect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates):
        detectCalls.append(
            (stack, xy_scale, z_scale, models, min_volume_m3, max_candidates)
        )
        return [((1e-6, 2e-6, -530e-6), 0.8)]

    monkeypatch.setattr(tile_detector, "_acquire", fakeAcquire)
    monkeypatch.setattr(tile_detector, "_detect", fakeDetect)
    monkeypatch.setattr(tile_detector, "_newCell", FakeCell)

    detect = tile_detector.make_tile_detector(camera=camera, scope=scope, manager=None)

    class Rig:
        pass

    rig = Rig()
    rig.camera = camera
    rig.scope = scope
    rig.acquireCalls = acquireCalls
    rig.detectCalls = detectCalls
    rig.detect = detect
    return rig


def test_the_stack_spans_the_constrained_range_below_this_tiles_surface(rig):
    # The whole reason depth is expressed as offsets from the surface: the slab
    # follows the tissue, so a tile whose surface is at -500 um must be searched
    # 20-60 um below THAT, not below zero.
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-20e-6, -60e-6)))

    start_z, stop_z, step_z = rig.acquireCalls[0]
    assert start_z == pytest.approx(-520e-6)
    assert stop_z == pytest.approx(-560e-6)
    assert step_z == pytest.approx(1e-6)


def test_the_depth_range_is_read_from_the_constraints_it_is_given(rig):
    # Not from a value captured when the detector was built: the operator may
    # edit the range between runs, and the slice hands its current constraints
    # to every call.
    rig.detect((0.0, 0.0), SearchConstraints(depth_range=(-5e-6, -15e-6)))

    start_z, stop_z, _ = rig.acquireCalls[0]
    assert start_z == pytest.approx(-505e-6)
    assert stop_z == pytest.approx(-515e-6)


def test_the_stage_moves_to_the_tile_before_the_surface_is_found(rig):
    # Surface is per tile, so searching for it before arriving would measure the
    # previous tile's tissue.
    rig.detect((3e-6, 4e-6), SearchConstraints())
    assert rig.scope.moves == [(3e-6, 4e-6)]


def test_focus_is_restored_after_a_successful_survey(rig):
    before = rig.camera.getFocusDepth()
    rig.detect((0.0, 0.0), SearchConstraints())
    assert rig.camera.focusSets[-1] == pytest.approx(before)


def test_focus_is_restored_when_acquisition_raises(rig, monkeypatch):
    # A survey that dies mid-stack must not leave the objective parked deep in
    # the tissue for whatever runs next.
    before = rig.camera.getFocusDepth()

    def boom(cam, start_z, stop_z, step_z):
        raise RuntimeError("camera died")

    monkeypatch.setattr(tile_detector, "_acquire", boom)

    with pytest.raises(RuntimeError, match="camera died"):
        rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.camera.focusSets[-1] == pytest.approx(before)


def test_a_stop_prevents_the_survey_from_imaging(rig, monkeypatch):
    # Imaging a tile is slow, so a stop must be honoured before the stack starts,
    # not only after it finishes.
    def stopNow():
        raise Stopped("stopped by operator")

    monkeypatch.setattr(tile_detector, "check_stop", stopNow)

    with pytest.raises(Stopped):
        rig.detect((0.0, 0.0), SearchConstraints())

    assert rig.acquireCalls == []
    assert rig.scope.moves == []


def test_detected_cells_carry_their_health_score(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)
    assert cells[0].position == (1e-6, 2e-6, -530e-6)


def test_tracking_is_seeded_from_the_stack_the_cell_was_found_in(rig):
    cells = rig.detect((0.0, 0.0), SearchConstraints())
    assert cells[0].trackerInits == 1


def test_a_cell_whose_tracker_cannot_be_seeded_is_still_returned(rig, monkeypatch):
    # A cell too close to the stack edge cannot be extracted, but it is a real
    # detection: discarding it would silently drop cells at every tile boundary.
    monkeypatch.setattr(FakeCell, "trackerFails", True)

    cells = rig.detect((0.0, 0.0), SearchConstraints())

    assert len(cells) == 1
    assert cells[0].score == pytest.approx(0.8)


def test_the_pixel_size_and_step_reach_detection(rig):
    rig.detect((0.0, 0.0), SearchConstraints())
    stack, xy_scale, z_scale, _models, _min_volume, _n = rig.detectCalls[0]
    assert stack == ["frame"]
    assert xy_scale == pytest.approx(0.32e-6)
    assert z_scale == pytest.approx(1e-6)


class FakeManager:
    def __init__(self, misc):
        self.config = {"misc": misc}


def test_health_models_come_from_the_misc_config():
    models = tile_detector._health_models(
        FakeManager({"segmenterPath": "/seg.pt", "classifierPath": "/cls.pt"})
    )
    assert models["segmenter"] == "/seg.pt"
    assert models["classifier"] == "/cls.pt"
    assert models["autoencoder"] is None
    assert models["resnet_classifier"] is None


def test_health_models_without_a_manager_are_all_unset():
    # A headless or partially-configured rig must not raise here; detect_neurons
    # accepts None for every model.
    assert set(tile_detector._health_models(None).values()) == {None}
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_tile_detector.py -v
```

Expected: `ModuleNotFoundError: No module named 'acq4.experiment.tile_detector'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/experiment/tile_detector.py`:

```python
"""The imaging half of a cell producer: move to a tile, find its surface, acquire
a stack over the constrained depth range, and return scored cell candidates."""

from __future__ import annotations

from typing import Callable

from acq4.logging_config import get_logger
from acq4.util.task import check_stop, synch

logger = get_logger(__name__)


def make_tile_detector(
    camera,
    scope,
    manager,
    step_z: float = 1e-6,
    min_volume_m3: float = 0.0,
    max_candidates: int = 5,
) -> Callable:
    """Build the detector seam `Slice.makeCellProducer()` needs.

    `camera` and `scope` must be resolved on the GUI thread and passed in; the
    returned callable runs on the orchestrator's worker thread, where reading a
    device selector widget is not safe.

    Surface is found per tile rather than once per slice, so the searched slab
    follows uneven tissue -- that is the whole reason the depth range is
    expressed as offsets from the surface instead of absolute stage z.
    """

    def detect(center, constraints) -> list:
        check_stop()
        logger.info("Surveying tile at %r", center)
        scope.setGlobalPosition(center, name="autopatch survey move").wait()

        check_stop()
        surface = synch(scope.findSurfaceDepth)(camera)
        start_z, stop_z = constraints.z_bounds(surface)

        check_stop()
        restore_depth = camera.getFocusDepth()
        try:
            stack = _acquire(camera, start_z, stop_z, step_z)
        finally:
            # Restored on the failure path too: a survey that dies mid-stack
            # must not leave the objective parked deep in the tissue for
            # whatever runs next.
            camera.setFocusDepth(
                restore_depth, name=f"{camera.name()} restore focus after survey stack"
            )

        check_stop()
        results = _detect(
            stack,
            xy_scale=camera.getPixelSize()[0],
            z_scale=step_z,
            models=_health_models(manager),
            min_volume_m3=min_volume_m3,
            max_candidates=max_candidates,
        )
        logger.info("Tile at %r yielded %d candidates", center, len(results))
        return _build_cells(camera, stack, results)

    return detect


def _build_cells(camera, stack, results) -> list:
    """Cells for each (position, score) detection, tracking seeded from `stack`."""
    cells = []
    for position, score in results:
        cell = _newCell(position)
        cell.score = score
        try:
            # Seeded from the stack the cell was found in, so tracking is ready
            # without re-acquiring a stack per cell.
            cell.initializeTrackerFromStack(camera, stack, use_cellpose=True)
        except Exception:
            # A cell too close to the stack edge cannot be extracted, but it is
            # still a real detection: queue it rather than silently dropping
            # every cell near a tile boundary.
            logger.warning(
                "Could not initialize tracking for the cell detected at %r",
                position,
                exc_info=True,
            )
        cells.append(cell)
    return cells


def _newCell(position):
    """A Cell at a global position.

    Imported here, not at module scope: acq4_automation lives in an internal
    repository, and a top-level import would stop every test under
    acq4/experiment from collecting where it is absent.
    """
    from acq4_automation.feature_tracking.cell import Cell
    from coorx import Point

    return Cell(Point(position, "global"))


def _acquire(camera, start_z: float, stop_z: float, step_z: float) -> list:
    """The tile's z-stack."""
    from acq4.util.imaging.sequencer import acquire_z_stack

    return acquire_z_stack(
        camera, start_z, stop_z, step_z, slow_fallback=False, name="autopatch survey stack"
    )


def _detect(stack, xy_scale, z_scale, models, min_volume_m3, max_candidates) -> list:
    """Scored (position, score) candidates in `stack`. See _newCell on the import."""
    from acq4_automation.object_detection import detect_neurons

    return detect_neurons(
        stack,
        xy_scale=xy_scale,
        z_scale=z_scale,
        trim_edges=True,
        min_volume_m3=min_volume_m3,
        n=max_candidates,
        **models,
    )


def _health_models(manager) -> dict:
    """The configured detection/classification model paths from global `misc` config.

    The same keys AutomationDebug reads, so a rig configured for the debug
    bench needs no extra configuration to run a survey.
    """
    misc = manager.config.get("misc", {}) if manager is not None else {}
    return {
        "segmenter": misc.get("segmenterPath", None),
        "autoencoder": misc.get("autoencoderPath", None),
        "classifier": misc.get("classifierPath", None),
        "resnet_classifier": misc.get("resnetClassifierPath", None),
    }
```

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_tile_detector.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Mutation-verify the three absence-shaped assertions**

(a) The depth sign. `z_bounds` is the one place the sign convention is applied, and a flipped sign would drive the objective *above* the tissue. Subtract instead of add in `SearchConstraints.z_bounds`:

```python
    def z_bounds(self, surface):
        near, far = self.depth_range
        return surface - max(near, far), surface - min(near, far)   # DEFECT
```

Expected: `test_the_stack_spans_the_constrained_range_below_this_tiles_surface` FAILS with `-480e-6` where `-520e-6` was expected. Revert.

(b) Focus restoration on the failure path. Move the restore out of the `finally`:

```python
        stack = _acquire(camera, start_z, stop_z, step_z)
        camera.setFocusDepth(restore_depth, name=...)     # DEFECT: not restored on raise
```

Expected: `test_focus_is_restored_when_acquisition_raises` FAILS (`focusSets` is empty, raising `IndexError`, or holds no restore value). Revert.

(c) A cell with a failed tracker must survive. Re-raise instead of logging:

```python
        try:
            cell.initializeTrackerFromStack(camera, stack, use_cellpose=True)
        except Exception:
            logger.warning(...)
            continue                                       # DEFECT: drops a real detection
```

Expected: `test_a_cell_whose_tracker_cannot_be_seeded_is_still_returned` FAILS on `assert len(cells) == 1`. Revert.

- [ ] **Step 6: Verify the module imports where `acq4_automation` is absent**

This is the property that keeps `acq4/experiment/tests` collecting on a public runner:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "
import sys
sys.modules['acq4_automation'] = None
import acq4.experiment.tile_detector as td
print('imports clean:', callable(td.make_tile_detector))
"
```

Expected: `imports clean: True`.

- [ ] **Step 7: Run the whole engine suite and commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -q
```

Expected: all pass, no collection errors.

```bash
git add acq4/experiment/tile_detector.py acq4/experiment/tests/test_tile_detector.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add the tile detector, a cell producer's imaging half

Moves to a tile, finds that tile's surface, acquires a stack across the
constrained depth range, and returns scored cells with trackers seeded from
that stack. The device calls are module-level functions so the orchestration
around them -- the depth arithmetic, focus restoration on the failure path,
and stop handling -- is tested with fakes. acq4_automation is imported lazily
so the engine's tests still collect where it is absent.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 10: Area 2 — the cell-finding config panel

The operator-facing controls: the four search constraints, a button to seed a region around the current field of view, and a readout of survey progress. Region *graphics* (draggable ROIs, the mirror-to-Camera checkbox, the heatmap) are P2c; this panel's job is to make the producer configurable and startable.

**Files:**
- Create: `acq4/modules/Autopatch/search_panel.py`
- Create: `acq4/modules/Autopatch/tests/test_search_panel.py`

**Interfaces:**
- Consumes: `SearchConstraints` (Task 2), `Slice` (Task 3).
- Produces:
  - `SearchPanel(cameraGetter=None)` — a `QWidget`.
  - `panel.constraints() -> SearchConstraints | None` — built from the current widget values, or `None` when they do not describe a valid search.
  - `panel.sigConstraintsChanged = Qt.Signal(object)` — emits a fresh `SearchConstraints` on any edit.
  - `panel.sigAddRegionRequested = Qt.Signal()` — the "Add region here" button.
  - `panel.setSurveyStats(total, covered, percent) -> None` — updates the readout.
  - `panel.setInteractionLocked(locked: bool) -> None` — disables editing while a run is in flight.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_search_panel.py`. Match the sibling panel tests' style: a module-scoped `qapp` fixture, the widget constructed inline per test, and signals captured with a plain list — those files do not use `pytest-qt`'s `qtbot`.

```python
"""Tests for Area 2's cell-finding config: the search constraints it builds, the
region-seeding request it emits, and the survey readout it shows."""

import pytest

from acq4.experiment.slice import SearchConstraints
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def makePanel():
    from acq4.modules.Autopatch.search_panel import SearchPanel

    return SearchPanel()


def test_defaults_match_the_engines_defaults(qapp):
    # An operator who touches nothing must get the same search the engine
    # documents, not a second set of defaults that silently disagrees.
    assert makePanel().constraints() == SearchConstraints()


def test_editing_the_depth_range_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.nearDepthSpin.setValue(-10e-6)
    panel.farDepthSpin.setValue(-50e-6)
    assert panel.constraints().depth_range == (
        pytest.approx(-10e-6),
        pytest.approx(-50e-6),
    )


def test_editing_the_health_cutoff_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.minHealthSpin.setValue(0.8)
    assert panel.constraints().min_health == pytest.approx(0.8)


def test_editing_rescans_is_reflected_in_the_constraints(qapp):
    panel = makePanel()
    panel.rescansCheck.setChecked(True)
    assert panel.constraints().rescans_allowed is True


def test_an_edit_emits_the_new_constraints(qapp):
    panel = makePanel()
    emitted = []
    panel.sigConstraintsChanged.connect(emitted.append)

    panel.minHealthSpin.setValue(0.75)

    assert emitted, "editing a constraint must announce the new search"
    assert emitted[-1].min_health == pytest.approx(0.75)


def test_an_invalid_depth_range_does_not_raise_out_of_the_widget(qapp):
    # Constraint validation raises, and an operator dragging a spinbox through
    # an invalid intermediate value must not crash the GUI thread.
    panel = makePanel()
    panel.nearDepthSpin.setValue(-30e-6)
    panel.farDepthSpin.setValue(-30e-6)
    assert panel.constraints() is None
    assert panel.errorLabel.text() != ""


def test_an_invalid_edit_announces_none_rather_than_staying_silent(qapp):
    # A listener holding the last-good constraints has to be told the widget no
    # longer describes a valid search, or it cannot decide to keep them.
    panel = makePanel()
    emitted = []
    panel.sigConstraintsChanged.connect(emitted.append)

    panel.farDepthSpin.setValue(panel.nearDepthSpin.value())

    assert emitted[-1] is None


def test_recovering_from_an_invalid_range_clears_the_error(qapp):
    panel = makePanel()
    panel.farDepthSpin.setValue(panel.nearDepthSpin.value())
    assert panel.constraints() is None
    panel.farDepthSpin.setValue(-70e-6)
    assert panel.constraints() is not None
    assert panel.errorLabel.text() == ""


def test_add_region_button_emits_a_request(qapp):
    panel = makePanel()
    requests = []
    panel.sigAddRegionRequested.connect(lambda: requests.append(True))

    panel.addRegionBtn.click()

    assert requests == [True]


def test_survey_stats_are_shown(qapp):
    panel = makePanel()
    panel.setSurveyStats(9, 3, 100 / 3)
    text = panel.surveyLabel.text()
    assert "3" in text and "9" in text and "33" in text


def test_survey_stats_with_no_region_read_as_no_region(qapp):
    panel = makePanel()
    panel.setSurveyStats(0, 0, 0.0)
    assert "no region" in panel.surveyLabel.text().lower()


def test_locking_disables_editing_but_not_the_readout(qapp):
    panel = makePanel()
    panel.setInteractionLocked(True)
    assert not panel.minHealthSpin.isEnabled()
    assert not panel.addRegionBtn.isEnabled()
    panel.setInteractionLocked(False)
    assert panel.minHealthSpin.isEnabled()
    assert panel.addRegionBtn.isEnabled()
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_search_panel.py -v
```

Expected: `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.search_panel'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/modules/Autopatch/search_panel.py`:

```python
"""SearchPanel: Area 2's cell-finding config -- the search constraints that
parameterise a cell producer, plus region seeding and a survey progress readout."""
from __future__ import annotations

from acq4.experiment.slice import SearchConstraints
from acq4.util import Qt


class SearchPanel(Qt.QWidget):
    """The four Area 2 search constraints, a region-seeding button, and a readout.

    Emits `sigConstraintsChanged` with a fresh SearchConstraints on every edit,
    or with None when the widget values do not describe a valid search (an
    operator dragging a spinbox passes through invalid intermediate values, and
    that must not raise on the GUI thread). Region *graphics* are not this
    panel's job: it asks its owner to seed a region and shows how much of the
    result has been surveyed.
    """

    sigConstraintsChanged = Qt.Signal(object)   # SearchConstraints, or None if invalid
    sigAddRegionRequested = Qt.Signal()

    def __init__(self, cameraGetter=None):
        super().__init__()
        self._cameraGetter = cameraGetter or (lambda: None)
        defaults = SearchConstraints()

        # Depths are offsets from the tissue surface, negative being deeper, so
        # the spin boxes read the way the design doc writes them (-20 um to
        # -60 um) rather than as unsigned depths that get subtracted somewhere
        # else.
        self.nearDepthSpin = self._makeSpin(
            defaults.depth_range[0], minimum=-1e-3, maximum=0.0, step=5e-6, suffix="m", decimals=7
        )
        self.farDepthSpin = self._makeSpin(
            defaults.depth_range[1], minimum=-1e-3, maximum=0.0, step=5e-6, suffix="m", decimals=7
        )
        self.minHealthSpin = self._makeSpin(
            defaults.min_health, minimum=0.0, maximum=1.0, step=0.05, suffix="", decimals=2
        )
        self.maxDensitySpin = self._makeSpin(
            defaults.max_cell_density, minimum=1.0, maximum=1e18, step=1e12,
            suffix="/m³", decimals=0,
        )
        self.rescansCheck = Qt.QCheckBox("Rescans allowed")
        self.rescansCheck.setChecked(defaults.rescans_allowed)

        self.addRegionBtn = Qt.QPushButton("Add region here")
        self.addRegionBtn.setToolTip(
            "Add a search region covering roughly 3x3 fields of view around the "
            "camera's current center."
        )
        self.surveyLabel = Qt.QLabel("no region")
        self.errorLabel = Qt.QLabel("")
        self.errorLabel.setStyleSheet("color: red;")

        form = Qt.QFormLayout()
        form.addRow("Depth from surface, near", self.nearDepthSpin)
        form.addRow("Depth from surface, far", self.farDepthSpin)
        form.addRow("Minimum health", self.minHealthSpin)
        form.addRow("Maximum cell density", self.maxDensitySpin)

        layout = Qt.QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.rescansCheck)
        layout.addWidget(self.addRegionBtn)
        layout.addWidget(self.surveyLabel)
        layout.addWidget(self.errorLabel)
        self.setLayout(layout)

        for spin in (self.nearDepthSpin, self.farDepthSpin, self.minHealthSpin, self.maxDensitySpin):
            spin.valueChanged.connect(self._onEdited)
        self.rescansCheck.toggled.connect(self._onEdited)
        self.addRegionBtn.clicked.connect(self.sigAddRegionRequested)

    @staticmethod
    def _makeSpin(value, minimum, maximum, step, suffix, decimals):
        spin = Qt.QDoubleSpinBox()
        spin.setDecimals(decimals)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        if suffix:
            spin.setSuffix(f" {suffix}")
        spin.setValue(value)
        return spin

    def constraints(self) -> SearchConstraints | None:
        """The current widget values as constraints, or None if they are invalid.

        Returning None rather than raising is what lets an operator drag a
        spinbox through an invalid intermediate value without a traceback on
        the GUI thread; the reason lands in errorLabel instead.
        """
        try:
            constraints = SearchConstraints(
                depth_range=(self.nearDepthSpin.value(), self.farDepthSpin.value()),
                min_health=self.minHealthSpin.value(),
                max_cell_density=self.maxDensitySpin.value(),
                rescans_allowed=self.rescansCheck.isChecked(),
            )
        except ValueError as exc:
            self.errorLabel.setText(str(exc))
            return None
        self.errorLabel.setText("")
        return constraints

    def _onEdited(self, *_args) -> None:
        self.sigConstraintsChanged.emit(self.constraints())

    def setSurveyStats(self, total: int, covered: int, percent: float) -> None:
        if total == 0:
            self.surveyLabel.setText("no region")
            return
        self.surveyLabel.setText(f"{covered}/{total} tiles imaged ({percent:.0f}%)")

    def setInteractionLocked(self, locked: bool) -> None:
        """Disable editing while a run is in flight; the readout stays visible.

        The constraints parameterise a producer that is already surveying, so
        editing them mid-run would silently change the search under it.
        """
        for w in (
            self.nearDepthSpin,
            self.farDepthSpin,
            self.minHealthSpin,
            self.maxDensitySpin,
            self.rescansCheck,
            self.addRegionBtn,
        ):
            w.setEnabled(not locked)
```

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_search_panel.py -v
```

Expected: 13 passed. If `test_defaults_match_the_engines_defaults` fails on floating-point representation (a `QDoubleSpinBox` rounds to its `decimals`), fix it by raising `decimals` on the offending spin box, not by loosening the assertion — an operator's default search silently differing from the documented one is the bug this test exists to catch. Note `max_cell_density`'s default is `5e12` with `decimals=0`, which a `QDoubleSpinBox` represents exactly; if the equality still fails there, widen the spin box's range rather than rounding the default.

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/search_panel.py acq4/modules/Autopatch/tests/test_search_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: add Area 2's cell-finding config panel

The four search constraints, a region-seeding request, and a survey readout.
Invalid spinbox values report None and an error line rather than raising on
the GUI thread, and editing locks while a run is in flight.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 11: Wire the slice and producer into the window

Everything above is inert until the window owns a `Slice`, installs a producer at Start, and releases it on teardown. This task also closes the remaining P2a deferral ("no teardown path calls `setCellProducer(None)`") and implements §6b's New-slice lifetime.

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py:38-59` (area boxes), `:86-122` (panel construction), `:124-131` (`_resolvePipette`), `:132-161` (`_onProtocolLoaded`), `:194-219` (`teardown`)
- Modify: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `Slice`, `SearchConstraints`, `make_tile_detector`, `SearchPanel`, `Orchestrator.setCellProducer`/`clearQueue`, `StatusPanel.sigStatusChanged` (Task 8).
- Produces: `AutopatchWindow.slice` (the current `Slice`, or `None`); `AutopatchWindow.newSlice()`; `AutopatchWindow.addRegionHere()`.

- [ ] **Step 1: Add the camera stub and a window helper the new tests need**

`test_window_integration.py` has no window fixture — each test constructs `AutopatchWindow(module=None, protocolDir=str(tmp_path), pipetteSelector=_FakePipetteSelector(), cameraSelector=_FakeCameraSelector())` inline after writing a protocol file — and its `_FakeCameraSelector.getSelectedObj()` returns `None`, so no existing test exercises a camera at all. Every test below needs one. Add these next to the existing stubs, leaving `_FakeCameraSelector` untouched so the tests that rely on a camera-less window keep working:

```python
class _FakeScope:
    """Stands in for a Microscope: records survey moves and reports a surface."""

    def __init__(self):
        self.moves = []

    def setGlobalPosition(self, pos, speed="fast", name=None):
        self.moves.append(tuple(pos))
        return _DoneFuture()

    def findSurfaceDepth(self, imager):
        return 0.0


class _DoneFuture:
    def wait(self, **kwargs):
        return None


class _FakeCamera:
    """Stands in for a Camera: the three calls a cell producer's install needs.

    getBoundary in "roi" mode gives the field a tile covers, globalCenterPosition
    in "roi" mode gives where to seed a region, and scopeDev is the stage the
    detector drives.
    """

    def __init__(self, fov=(10e-6, 10e-6), center=(0.0, 0.0, 0.0)):
        self._fov = fov
        self._center = center
        self.scopeDev = _FakeScope()

    def name(self):
        return "FakeCamera"

    def getBoundary(self, globalCoords=True, mode="sensor"):
        w, h = self._fov
        return self._center[0] - w / 2, self._center[1] - h / 2, w, h

    def globalCenterPosition(self, mode="sensor"):
        return self._center

    def getPixelSize(self):
        return (0.32e-6, 0.32e-6)


class _FakeCameraWithDevice(Qt.QWidget):
    """A camera selector that actually returns a camera, unlike _FakeCameraSelector."""

    def __init__(self, camera=None):
        super().__init__()
        self.camera = camera if camera is not None else _FakeCamera()

    def getSelectedObj(self):
        return self.camera


def _makeWindow(tmp_path, cameraSelector=None):
    """An AutopatchWindow with a loaded no-op protocol, as the tests above build it."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.py", _NOOP_PROTOCOL)
    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
        cameraSelector=cameraSelector if cameraSelector is not None else _FakeCameraWithDevice(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo")
    return win
```

- [ ] **Step 2: Write the failing tests**

Append them to the same file. Each takes `qapp` and `tmp_path`, matching the file's existing signatures.

```python
def test_a_fresh_window_has_no_slice(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    # A slice is a commitment to a piece of tissue under the objective; the
    # window must not invent one before the operator says so.
    assert win.slice is None


def test_new_slice_creates_a_slice_using_the_cameras_field_of_view(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    assert win.slice is not None
    assert win.slice.tileGrid() == [], "a new slice has no regions to survey yet"


def test_new_slice_without_a_camera_reports_rather_than_raising(qapp, tmp_path):
    # _FakeCameraSelector returns None, the camera-less case.
    win = _makeWindow(tmp_path, cameraSelector=_FakeCameraSelector())
    win.newSlice()
    assert win.slice is None
    assert win.searchPanel.errorLabel.text() != ""


def test_add_region_here_seeds_a_multi_tile_region(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    assert len(win.slice.regions) == 1
    assert len(win.slice.tileGrid()) > 1


def test_new_slice_replaces_the_slice_and_its_coverage(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    first = win.slice
    first.markCovered(first.nextTile())

    win.newSlice()

    assert win.slice is not first
    assert win.slice.regions == []
    assert win.slice.coveredTiles == []


def test_new_slice_clears_the_cell_list_and_the_orchestrators_queue(qapp, tmp_path):
    # A Cell is a coordinate in tissue. Swapped tissue makes every one of those
    # coordinates a place not to drive a pipette, so both the panel's list and
    # the orchestrator's separate deque have to let go.
    win = _makeWindow(tmp_path)
    win.cellPanel._onScatterFakeCellsClicked()
    assert win.cellPanel.cellList.count() > 0

    ran = []
    win.orchestrator.protocolFile.run = lambda ctx, **kw: ran.append(ctx.cell)

    win.newSlice()

    assert win.cellPanel.cellList.count() == 0
    win.orchestrator.run_sync()
    assert ran == [], "a cell survived New slice and was patched anyway"


def test_start_installs_a_producer_when_a_slice_has_a_region(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()

    win._onStartRun()

    assert win.orchestrator._cellProducer is not None


def test_start_installs_no_producer_without_a_slice(qapp, tmp_path):
    # No slice means no tissue to survey: the run must be a plain queue drain
    # of whatever the operator seeded by hand, not an error.
    win = _makeWindow(tmp_path)
    win._onStartRun()
    assert win.orchestrator._cellProducer is None


def test_start_installs_no_producer_for_a_slice_with_no_region(qapp, tmp_path):
    # A slice with nowhere to look would have its producer report exhaustion on
    # the first call, so installing one only adds a pointless refill round trip.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win._onStartRun()
    assert win.orchestrator._cellProducer is None


def test_start_clears_a_stale_producer_once_the_slice_is_gone(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    assert win.orchestrator._cellProducer is not None

    win.slice = None
    win._onStartRun()

    assert win.orchestrator._cellProducer is None


def test_teardown_clears_the_producer(qapp, tmp_path):
    # The producer closes over the camera and scope devices; leaving it
    # installed on a released orchestrator keeps them reachable from an object
    # the window has stopped managing.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    orch = win.orchestrator

    win.teardown()

    assert orch._cellProducer is None


def test_loading_a_second_protocol_clears_the_outgoing_producer(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    win._onStartRun()
    outgoing = win.orchestrator

    _write_protocol(str(tmp_path), "second.py", _NOOP_PROTOCOL)
    # refreshFileList is the discovery scan the picker's popup runs; it lists the
    # newly written file without force-reloading the one already loaded.
    win.protocolPanel.refreshFileList()
    win.protocolPanel.fileCombo.setCurrentText("second")

    assert outgoing._cellProducer is None
    assert win.orchestrator is not outgoing


def test_editing_the_constraints_reaches_the_live_slice(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.searchPanel.minHealthSpin.setValue(0.85)
    assert win.slice.constraints.min_health == pytest.approx(0.85)


def test_invalid_constraints_leave_the_slice_alone(qapp, tmp_path):
    win = _makeWindow(tmp_path)
    win.newSlice()
    before = win.slice.constraints
    win.searchPanel.farDepthSpin.setValue(win.searchPanel.nearDepthSpin.value())
    assert win.slice.constraints is before


def test_the_survey_readout_follows_the_slices_coverage(qapp, tmp_path):
    # Coverage advances on the worker thread as tiles are imaged, so the readout
    # is refreshed off the status signal rather than polled.
    win = _makeWindow(tmp_path)
    win.newSlice()
    win.addRegionHere()
    total = len(win.slice.tileGrid())
    win.slice.markCovered(win.slice.nextTile())

    win.statusPanel.sigStatusChanged.emit("surveying")

    assert f"1/{total}" in win.searchPanel.surveyLabel.text()
```

Add `import pytest` to the file if it is not already there. `test_loading_a_second_protocol_clears_the_outgoing_producer` drives the protocol picker (`refreshFileList()` then `fileCombo.setCurrentText(...)`) rather than calling `_onProtocolLoaded` directly, so it exercises the same path an operator does — the path that leaked a live orchestrator in P1.5.

- [ ] **Step 3: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k "slice or producer or constraints or readout"
```

Expected: `AttributeError` on `slice`, `newSlice`, `addRegionHere`, `_onStartRun`, and `searchPanel`.

- [ ] **Step 4: Write the implementation**

In `acq4/modules/Autopatch/Autopatch.py`:

Add the imports:

```python
from acq4.experiment.slice import Slice
from acq4.experiment.tile_detector import make_tile_detector

from .search_panel import SearchPanel
```

Populate Areas 1 and 2, replacing the bare group boxes' emptiness. After `self.statusPanel` is constructed and before `self.cellPanel`:

```python
        # Area 1 holds only New slice for now: region graphics and the progress
        # heatmap are Area 1's remaining content and are not built here.
        self.newSliceBtn = Qt.QPushButton("New slice")
        self.newSliceBtn.setToolTip(
            "Discard the current slice -- its regions, coverage, and queued "
            "cells -- and start a fresh one for newly mounted tissue."
        )
        self.area1Box.layout().addWidget(self.newSliceBtn)

        self.searchPanel = SearchPanel(cameraGetter=self.cameraSelector.getSelectedObj)
        self.area2Box.layout().addWidget(self.searchPanel)
```

Add the slice attribute next to `self._cachedPipette`:

```python
        # The tissue currently under the objective, or None before the operator
        # has started one. A Slice outlives individual runs: it holds the
        # regions, the coverage every producer made from it shares, and the
        # search constraints. Replaced only by newSlice().
        self.slice = None
        # Camera and scope resolved from cameraSelector at the moment Start was
        # last pressed, for the same reason as _cachedPipette: the detector runs
        # on the orchestrator's worker thread and must not read a selector.
        self._cachedCamera = None
        self._cachedScope = None
```

Wire the new controls, alongside the existing `statusPanel.sigInteractionLocked` connection:

```python
        self.newSliceBtn.clicked.connect(self.newSlice)
        self.searchPanel.sigAddRegionRequested.connect(self.addRegionHere)
        self.searchPanel.sigConstraintsChanged.connect(self._onConstraintsChanged)
        self.statusPanel.sigInteractionLocked.connect(self.searchPanel.setInteractionLocked)
        # Coverage advances on the worker thread as the producer images tiles, so
        # the readout is refreshed off a status change rather than polled. Routed
        # through StatusPanel, not connected to the orchestrator directly: the
        # orchestrator is a parentless QObject and a connection from it to this
        # window would give it a reference back, rebuilding the cycle
        # bindOrchestrator/unbindOrchestrator exist to avoid. StatusPanel is in
        # this window's widget tree, so this wiring is made once and never needs
        # re-wiring per protocol load.
        self.statusPanel.sigStatusChanged.connect(self._onRunStatus)
```

Add the slice lifecycle methods:

```python
    def newSlice(self) -> None:
        """Start a fresh slice, discarding the current one and everything on it.

        Regions, coverage, and search constraints go with the old slice, and so
        do the queued cells: a Cell is a coordinate in tissue, and tissue that
        has been swapped makes every one of those coordinates a place not to
        drive a pipette. The per-cell data already written under the old slice
        directory is the durable record; Area 5's list is a working queue.
        """
        camera = self.cameraSelector.getSelectedObj()
        if camera is None:
            self.searchPanel.errorLabel.setText("Select a camera before starting a slice.")
            return
        constraints = self.searchPanel.constraints()
        if constraints is None:
            return
        self.slice = Slice(fov=self._cameraFov(camera), constraints=constraints)
        self.cellPanel.clearCells()
        if self.orchestrator is not None:
            # clearCells() only drops the panel's own bookkeeping; the
            # orchestrator's deque is a separate strong reference to the same
            # cells and would keep handing them to the protocol.
            self.orchestrator.clearQueue()
            self.orchestrator.setCellProducer(None)
        self._refreshSurveyStats()

    def addRegionHere(self) -> None:
        """Add a search region of roughly 3x3 fields of view around the camera center."""
        if self.slice is None:
            self.newSlice()
            if self.slice is None:
                return
        camera = self.cameraSelector.getSelectedObj()
        if camera is None:
            return
        fov_w, fov_h = self._cameraFov(camera)
        # "roi" mode throughout: the field the camera actually images is what a
        # tile covers, and globalCenterPosition defaults to "sensor", which is
        # off-center for a cropped camera ROI.
        cx, cy = camera.globalCenterPosition("roi")[:2]
        w, h = fov_w * 3, fov_h * 3
        self.slice.addRegion(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        self._refreshSurveyStats()

    @staticmethod
    def _cameraFov(camera) -> tuple[float, float]:
        """The camera's imaged field width and height, in global metres."""
        _, _, w, h = camera.getBoundary(globalCoords=True, mode="roi")
        return abs(w), abs(h)

    def _onConstraintsChanged(self, constraints) -> None:
        # None means the spinboxes do not currently describe a valid search
        # (SearchPanel already shows why); leave the live slice on its last
        # good constraints rather than tearing them down mid-edit.
        if constraints is not None and self.slice is not None:
            self.slice.setConstraints(constraints)

    def _refreshSurveyStats(self) -> None:
        if self.slice is None:
            self.searchPanel.setSurveyStats(0, 0, 0.0)
        else:
            self.searchPanel.setSurveyStats(*self.slice.surveyStats())
```

Replace `_resolvePipette` with `_onStartRun`, which snapshots the devices *and* installs the producer — one GUI-thread seam, called through `StatusPanel`'s existing `onStart` hook:

```python
    def _onStartRun(self) -> None:
        """Snapshot GUI-thread-only state and install the cell producer at Start.

        Runs on the GUI thread before the orchestrator's worker thread starts,
        so the in-flight run never reads InterfaceCombo's
        currentIndex()/interfaceMap off-thread. Re-resolved on every Start, so
        the selection and the slice may both change between runs.
        """
        self._cachedPipette = self.pipetteSelector.getSelectedObj()
        self._cachedCamera = self.cameraSelector.getSelectedObj()
        self._cachedScope = None
        if self._cachedCamera is not None:
            self._cachedScope = self._cachedCamera.scopeDev
        self._installCellProducer()

    def _installCellProducer(self) -> None:
        """Give the orchestrator a producer for the current slice, or none.

        Cleared rather than left stale whenever a survey is not possible: no
        slice, no region, or no camera means the run is a plain drain of the
        cells the operator seeded by hand, and a producer left over from a
        previous Start would otherwise keep surveying tissue that is gone.
        """
        if self.orchestrator is None:
            return
        canSurvey = (
            self.slice is not None
            and self.slice.regions
            and self._cachedCamera is not None
            and self._cachedScope is not None
        )
        if not canSurvey:
            self.orchestrator.setCellProducer(None)
            return
        detector = make_tile_detector(
            camera=self._cachedCamera, scope=self._cachedScope, manager=self.manager
        )
        self.orchestrator.setCellProducer(self.slice.makeCellProducer(detector))
```

Point `bindOrchestrator` at the new hook, in `_onProtocolLoaded`:

```python
        self.statusPanel.bindOrchestrator(
            self.orchestrator, self.cellPanel, onStart=self._onStartRun
        )
```

Clear the producer wherever an orchestrator is released, in `_stopAndReleaseOrchestrator` — before `setParent(None)`:

```python
        # The producer closes over the camera and scope devices and over a
        # Slice this window may be about to replace. Leaving it installed on an
        # orchestrator the window has stopped managing keeps all of that
        # reachable from an object nothing is looking after any more.
        orchestrator.setCellProducer(None)
```

Finally, add the slot behind the `sigStatusChanged` connection made in the constructor:

```python
    def _onRunStatus(self, status: str) -> None:
        """Refresh Area 2's survey readout when the run's status moves.

        Coverage advances on the orchestrator's worker thread, but this arrives
        via StatusPanel on the GUI thread, so re-reading the slice here is safe.
        """
        if status in ("surveying", "waiting"):
            self._refreshSurveyStats()
```

Nothing needs disconnecting for this one: `sigStatusChanged` belongs to `self.statusPanel`, a child widget in this window's tree, and it is wired once in the constructor rather than per orchestrator — the same shape as the existing `sigInteractionLocked` → `protocolPanel.setInteractionLocked` connection.

- [ ] **Step 5: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v
```

Expected: all pass, including the pre-existing tests. If a call on `_FakeCamera` or `_FakeScope` turns out to be missing, extend the stub — do not weaken the test, since those calls are exactly what the producer install depends on.

- [ ] **Step 6: Mutation-verify the two clearing behaviours**

(a) The orchestrator's queue must actually be cleared. Remove the `clearQueue()` call from `newSlice`:

```python
        if self.orchestrator is not None:
            self.orchestrator.setCellProducer(None)   # DEFECT: deque still holds the cells
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_new_slice_clears_the_cell_list_and_the_orchestrators_queue -v
```

Expected: FAIL on `assert ran == [], "a cell survived New slice and was patched anyway"`. Revert.

(b) A stale producer must be cleared, not merely left unreplaced. Make `_installCellProducer` return early instead of clearing:

```python
        if not canSurvey:
            return                                     # DEFECT: stale producer survives
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_start_clears_a_stale_producer_once_the_slice_is_gone -v
```

Expected: FAIL on `assert win.orchestrator._cellProducer is None`. Revert.

- [ ] **Step 7: Run the whole Autopatch and engine suites**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ acq4/modules/Autopatch/ acq4/modules/AutomationDebug/ -q
```

Expected: all pass. In particular `test_teardown.py`'s weakref/`gc.disable` regression tests must still pass — the new `Slice` and producer are reachable from the window, and a cycle through them would surface exactly there.

- [ ] **Step 8: Commit**

```bash
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_window_integration.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat: own a Slice in the Autopatch window and install its cell producer

New slice discards the tissue's regions, coverage, and queued cells -- both
the panel's list and the orchestrator's separate deque. Start snapshots the
camera and scope on the GUI thread and installs a producer for the current
slice, clearing a stale one when a survey is no longer possible; every path
that releases an orchestrator now clears its producer too.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 12: Live smoke-test brief

The headless suite cannot reach the detector, the stage moves, the surface search, or `detect_neurons`. Task 9 is verified by an operator at a GUI, and P1.5's experience was that three of its four Criticals lived in exactly the panels CI skips. Write the brief; a human runs it.

**Files:**
- Create: `.superpowers/sdd/p2b-smoke-brief.md` (an untracked working file — `.superpowers/sdd/.gitignore` is `*`, so nothing in that directory can be committed, which is why this task has no commit step for it)

**Interfaces:**
- Consumes: everything.
- Produces: nothing in code.

- [ ] **Step 1: Write the brief**

Create `.superpowers/sdd/p2b-smoke-brief.md`. It must contain, as numbered steps with an explicit expected observation each:

1. **Launch.** `/home/martin/.miniforge3/envs/acq4-gl/bin/python bin/acq4 --config /home/martin/src/acq4/acq4/config/mock/default.cfg -m Autopatch` — `--config` also sets `manager.configDir`, so this runs worktree code against the main checkout's mock config (the config dir is gitignored and absent from every worktree). Expect a clean launch, Areas 1 and 2 populated, zero tracebacks. **Before testing anything param-related, refresh `<configDir>/autopatch_protocols/example_*.py` from this branch** — `install_example_protocols` never overwrites, so a stale on-disk copy silently shadows the bundled one.
2. **New slice with no camera selected.** Expect the Area 2 error line to ask for a camera, and no slice to be created — not a traceback.
3. **New slice with a camera selected.** Expect the readout to read "no region".
4. **Add region here.** Expect the readout to show `0/N tiles imaged (0%)` with N > 1.
5. **Edit each constraint.** Expect no traceback, and dragging the far-depth spinbox through the near-depth value to show a red error line that clears on recovery.
6. **Start.** Expect Area 3 to read `surveying`, Stop and Pause enabled, Next cell disabled, Area 2 and Area 4 locked. Expect the stage to move and the survey readout to advance.
7. **Stop mid-survey.** Expect the run to end promptly, without waiting for the current tile's detection to find something. This is design §3.2's explicit requirement and the reason Task 8 exists.
8. **Pause mid-survey, then resume.** Expect no further tiles to be imaged while paused.
9. **Run to exhaustion** with a small region and `rescans allowed` off. Expect the run to end at `waiting` with the readout at 100%, and the log to show one `Surveying tile at ...` line per tile.
10. **Re-press Start on the exhausted slice.** Expect it to survey nothing new and end promptly — `_producerExhausted` is per-run, but the slice's coverage is not, so the producer reports exhaustion on its first call.
11. **Enable `rescans allowed` and Start again.** Expect exactly one more pass over the tiles, then `waiting`.
12. **Seed cells by hand, then press New slice.** Expect the cell list to empty, and a subsequent Start to patch nothing.
13. **Load a second protocol while a survey is running.** Expect the outgoing run to stop, no second worker thread to touch the pipette, and no log lines from the old orchestrator arriving in the new session's Area 5.
14. **Close the window.** Expect exit code 0 and no segfault — the teardown guard, and now with a `Slice` and producer in the graph.

For each step record VERIFIED / NOT VERIFIED with what was actually observed. Note that screenshots are not available from an agent on this box: Qt renders Wayland-native, `import -window root` fails, and there is no `grim`.

- [ ] **Step 2: Confirm the brief is not committable, and leave it uncommitted**

```bash
git check-ignore -v .superpowers/sdd/p2b-smoke-brief.md
```

Expected: `.superpowers/sdd/.gitignore:1:*	.superpowers/sdd/p2b-smoke-brief.md`. The brief is a working file for the human running it, exactly like `task-11-brief.md` from P1.5. Do not `git add -f` it.

- [ ] **Step 3: Run the full test suite one last time**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/ -q 2>&1 | tail -20
```

Expected: all pass, no new failures against the pre-branch baseline. Record the count. Test output must be pristine: investigate any new warning rather than tolerating it.

---

## Coverage against the spec

| Spec requirement | Task |
|---|---|
| §6b `Slice` owns the regions to search | 3 |
| §6b `Slice` owns coverage, shared by every producer it makes | 3, 4 |
| §6b `Slice` owns the search constraints | 2, 3 |
| §6b `Slice.makeCellProducer()` returns the §3.2 callable | 4 |
| §6b producers are views onto slice state, not owners | 4, 6 |
| §6b New slice discards regions, coverage, constraints, and the cell list | 7, 11 |
| §6b hard-coded binding to the acq4 slice directory | 3 (`Slice.directory`) |
| §6b heatmap backing data | 3 (`surveyStats`, `coveredTiles`); rendering is P2c |
| §6b persistence to `.index` | Deliberately out of scope ("not required for a first cut") |
| §3.2 `producer() -> Sequence \| None`, `[]` vs `None` | 4, 5 |
| §3.2 Stop and Pause honoured between refills | 8 (button gating); the loop behaviour landed in P2a |
| §3.2 `_producerExhausted` is per-run, not a record of a spent slice | 5 (per-producer rescan allowance mirrors it) |
| §7 Area 2 depth range, relative to surface, found per tile | 2, 9, 10 |
| §7 Area 2 minimum health prediction | 5, 10 |
| §7 Area 2 maximum cell density | 5, 10 |
| §7 Area 2 rescans allowed | 5, 10 |
| §7 Area 2 `auto-add`/`+add`/`recycle` button semantics | Parked by §12 as an implementation detail; not built |
| §7 Area 1 New slice | 11 |
| §7 Area 1 ROI graphics, mirror checkbox, heatmap, pinned frames | P2c |
| P2a deferral: no status distinguishes surveying from patching | 7, 8 |
| P2a deferral: `sigCurrentCell` holds the finished cell during a refill | 7 |
| P2a deferral: no teardown path calls `setCellProducer(None)` | 11 |
| P2a deferral: a lazy generator producer raising mid-iteration escapes unwrapped | Not addressed; `CellProducer` returns a concrete `list`, so no producer in this plan is lazy |
| §10 cross-repo `acq4_automation.Cell` expansion | P2c, with the heatmap that forces it |
