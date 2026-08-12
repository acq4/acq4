# Autopatch Area 1 Progress Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw cell markers and survey coverage into the Autopatch Area 1 view, coloured by a switchable source, navigable in both directions with Area 5's cell list.

**Architecture:** A `ProgressOverlay` adds a `pg.ScatterPlotItem` and a coverage layer into `RegionPanel`'s existing `ViewBox` — the same relationship `PinnedFrameMirror` already has to that view, so `RegionPanel` learns nothing about cells. Colour sources are pure functions from a plain `ColorContext` to `{cellId: brush}`, testable with no Qt widgets. `AutopatchWindow` does the only join, because it is the only object holding both the `Slice` and the `CellPanel`.

**Tech Stack:** Python, PyQt5 via `acq4.util.Qt`, pyqtgraph, pytest.

**Spec:** `docs/superpowers/specs/2026-08-12-autopatch-area1-progress-overlay-design.md`

## Global Constraints

- **Two repositories.** Task 1 lands in **acq4-automation**; every other task is in **acq4**. Task 1 goes first so `score` is a documented contract before three acq4 tasks read it, but **no acq4 task depends on it at runtime** — Tasks 3-5's colour tests pass plain `scores={}` dicts and never construct a `Cell`, and Task 9 sets `cell.score` dynamically, which works declared or not. Do not wait on a merge.
- **Import paths are asymmetric, and neither worktree sees the other's.** Run from the acq4 worktree, `acq4` resolves there but `acq4_automation` resolves to `/home/martin/src/acq4/acq4-automation` (the **main** checkout). So Task 1's change is invisible to every acq4 test, and is verified only by its own test in acq4-automation. Do not try to assert `Cell.score` from an acq4 test.
- **acq4-automation worktree:** `/home/martin/src/acq4/acq4-automation/.claude/worktrees/autopatch-ui-work-23ed2f`
- **acq4 worktree:** `/home/martin/src/acq4/acq4/.claude/worktrees/area1-progress-overlay`, branch `claude/area1-progress-overlay`. Do **not** work in `/home/martin/src/acq4/acq4` directly — another session shares that checkout and has already committed onto a branch there mid-task.
- **Python:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python` (the `acq4-gl` conda env; `acq4-torch` lacks dependencies this package needs).
- **Never call `Cell.position` on the GUI thread.** It evaluates `max(self._positions)`, iterating a dict the tracking worker writes (`cell.py:239`). Use `cell.initialPosition` for first placement and `sigPositionChanged` payloads for updates.
- **Never store a `Cell` outside `CellPanel._cells`.** Scatter point data and every cache key holds `id(cell)`. Reference cycles are this module's most-repeated defect; `tests/test_teardown.py` guards it.
- **Test output must be pristine.** No stray warnings or prints.
- **Every task ends with a mutation proof:** break the line the test targets, record the failing line number in the commit body, restore it. A mutation that does *not* fail means no delivered test proves that line: record the non-failure, then identify a test that *does* kill it — either written in this task, or in a specifically named later task — before treating the line as proven. Task 9 Step 5 is the one deliberate cross-task case; a non-failure with no named killing test anywhere is a broken test to fix, not a result to record.
- **Asymmetric fixtures at real SI magnitudes.** A swapped-axis mutant survived 324 tests because every fixture was square. Never use equal width and height, and use metres (`1.4e-3`), not `1.0`.

## Test Scaffolding (read before Task 6)

The existing test files do **not** all provide the helpers this plan's test code
calls. Three must be added, each mirroring a convention already in the repo.

**In `acq4/modules/Autopatch/tests/test_cell_panel.py`** — it has a `qapp`
fixture but no panel builder; every test does a local import and constructs
`CellPanel(...)` inline. Add this beside `_buildOnAnotherThread`, mirroring
`test_region_panel.py`, which already has exactly this helper:

```python
def makePanel(**kwargs):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel(**kwargs)
```

**In `acq4/modules/Autopatch/tests/test_window_integration.py`** — the window
fixture is named **`win`**, not `window`, and `_makeCell()` takes no arguments
(it hardcodes `[1e-3, 2e-3, -30e-6]`). Several tests below need cells at
distinct positions, so add beside `_makeCell`:

```python
def _makeCellAt(x, y, z=-30e-6):
    """A Cell at a chosen global position, for tests that care where it is.

    _makeCell()'s fixed position is enough when only identity matters; density
    and navigation need cells that differ in both x and y.
    """
    return Cell(Point([x, y, z], "global"))


def _sliceWithTodoTiles(win):
    """Install a Slice on `win` with one region and nothing yet covered.

    Built directly rather than through win.newSlice()/addRegionHere(), the same
    reason _sliceWithCoveredTiles gives: those size the region off the fake
    camera's micrometre field of view, which cannot expose millimetre-magnitude
    float error. Asymmetric fov and a non-origin position for the same reason.
    """
    slice_ = Slice(fov=(20e-6, 10e-6))
    slice_.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    win.slice = slice_
    return slice_
```

`Slice`, `RectRegion`, `Cell` and `Point` are already imported at that module's
top level. Throughout this plan, window tests take the **`win`** fixture.

---

## File Structure

**acq4-automation:**
- Modify: `acq4_automation/feature_tracking/cell.py` — declare `score`
- Create: `acq4_automation/feature_tracking/test_cell_score.py` — beside the module, matching `test_cell_multiframe_signals.py`

**acq4** (all paths under the worktree):
- Create: `acq4/modules/Autopatch/progress_overlay.py` — `Marker`, `ProgressOverlay`
- Create: `acq4/modules/Autopatch/progress_colors.py` — `ColorContext`, the three colour sources, the legend
- Modify: `acq4/modules/Autopatch/cell_panel.py` — `cells()`, `selectCell()`, `sigCellStateChanged`
- Modify: `acq4/modules/Autopatch/region_panel.py` — the colour-source selector row
- Modify: `acq4/modules/Autopatch/Autopatch.py` — the join, the position cache, teardown
- Create: `acq4/modules/Autopatch/tests/test_progress_overlay.py`
- Create: `acq4/modules/Autopatch/tests/test_progress_colors.py`
- Modify: `acq4/modules/Autopatch/tests/test_cell_panel.py` — the new panel surface

Colours and the overlay's rendering are split from each other because the colour sources are pure and headless while the overlay needs a `ViewBox`; keeping them apart is what lets the colour logic — where every real decision lives — be tested without Qt graphics at all.

---

## Task 1: Declare `Cell.score` (acq4-automation)

**Files:**
- Modify: `acq4_automation/feature_tracking/cell.py:29-35`
- Test: `acq4_automation/feature_tracking/test_cell_score.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Cell.score` — `float | None`, the detector's health prediction in `[0, 1]`, set once at detection, `None` when never scored.

**Why:** `acq4/experiment/tile_detector.py:83` already does `cell.score = score`, and `acq4/experiment/cell_producer.py:118` already reads it with `getattr`. The attribute is load-bearing and undeclared, so nobody reading `Cell` can discover it. This declares what exists; it changes no behaviour.

- [ ] **Step 1: Write the failing test**

Create `acq4_automation/feature_tracking/test_cell_score.py`:

```python
"""Tests that Cell declares the detector's health score.

tile_detector._build_cells sets cell.score on every detected cell and
CellProducer._isHealthy reads it back, but Cell itself never declared the
attribute. The Area 1 progress overlay colours cells by it, so it is a
documented part of Cell's interface rather than a dynamic attribute two
callers happen to agree on.
"""
import pyqtgraph as pg
from coorx import Point

from acq4_automation.feature_tracking.cell import Cell

pg.mkQApp()


def test_score_defaults_to_none():
    """A cell nobody scored reports None, not a missing attribute.

    Every manually-added cell is in this category: only _build_cells scores,
    so "Add from target" and "Scatter fake cells" produce unscored cells and
    the overlay must be able to tell them from badly-scored ones.
    """
    cell = Cell(Point([1.0e-3, 2.0e-3, -30e-6], "global"))

    assert cell.score is None


def test_score_is_assignable():
    """The detector sets score after construction, which is the real usage."""
    cell = Cell(Point([1.0e-3, 2.0e-3, -30e-6], "global"))

    cell.score = 0.87

    assert cell.score == 0.87
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_score.py -v
```

Expected: `test_score_defaults_to_none` FAILS with `AttributeError: 'Cell' object has no attribute 'score'`. `test_score_is_assignable` PASSES already (Python allows the dynamic set) — that is correct and expected; it is a regression guard, not the driving test.

- [ ] **Step 3: Write minimal implementation**

In `acq4_automation/feature_tracking/cell.py`, inside `__init__`, after `self._allow_refresh_reference = True`:

```python
        # The detector's health prediction in [0, 1], set once by
        # tile_detector._build_cells at detection and not changed afterwards;
        # None for a cell no detector scored, which is every cell added by
        # hand. CellProducer._isHealthy gates queuing on it, so no queued cell
        # scores below the run's min_health cutoff.
        self.score = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_score.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Prove nothing else broke**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/ -q
```

Expected: no new failures against the pre-existing baseline. Per project memory the feature-tracking suite carries 6 known-failing mock tests and 2 collection errors — record the counts before and after and confirm they match; do not attempt to fix them here.

- [ ] **Step 6: Mutation proof**

Delete the `self.score = None` line, re-run Step 4, and record the failing line number. Expected: `test_score_defaults_to_none` fails with `AttributeError`. Restore the line.

- [ ] **Step 7: Commit**

```bash
git add acq4_automation/feature_tracking/cell.py acq4_automation/feature_tracking/test_cell_score.py
git commit -m "feat: declare the detector's health score on Cell"
```

**This is its own PR in acq4-automation, and blocks nothing here.** See Global Constraints: no acq4 task reads `Cell.score` at runtime, and acq4's tests import `acq4_automation` from the main checkout, so this change is invisible to them either way.

---

## Task 2: `ProgressOverlay` renders markers and coverage

**Files:**
- Create: `acq4/modules/Autopatch/progress_overlay.py`
- Test: `acq4/modules/Autopatch/tests/test_progress_overlay.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Marker` — `NamedTuple(x: float, y: float, brush: object, cellId: int)`
  - `ProgressOverlay(view)` — a `Qt.QObject`
  - `ProgressOverlay.sigMarkerClicked = Qt.Signal(object)` carrying one `cellId` (`int`)
  - `ProgressOverlay.setMarkers(markers: list[Marker]) -> None`
  - `ProgressOverlay.setCoverage(tiles: list[tuple[float, float]], fov: tuple[float, float]) -> None`
  - `ProgressOverlay.clear() -> None`
  - `ProgressOverlay.release() -> None`

A `QObject` rather than the plain class `PinnedFrameMirror` is, because this one has to emit a click.

- [ ] **Step 1: Write the failing test**

Create `acq4/modules/Autopatch/tests/test_progress_overlay.py`:

```python
"""Tests for Area 1's progress overlay: what it draws into the region view,
and what it reports when the operator clicks a cell marker."""

import pyqtgraph as pg
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


# Asymmetric and in metres throughout: a square fixture cannot catch a swapped
# x/y, and a unit-scale one cannot catch a metres/millimetres mixup.
FOV = (220e-6, 170e-6)
POS_A = (1.0e-3, 2.0e-3)
POS_B = (1.4e-3, 2.1e-3)


def makeOverlay():
    from acq4.modules.Autopatch.progress_overlay import ProgressOverlay

    view = pg.ViewBox()
    return ProgressOverlay(view), view


def test_markers_are_drawn_at_their_positions(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()

    overlay.setMarkers([
        Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111),
        Marker(POS_B[0], POS_B[1], pg.mkBrush(220, 40, 40), 222),
    ])

    spots = overlay.scatter.getData()
    assert list(spots[0]) == [POS_A[0], POS_B[0]]
    assert list(spots[1]) == [POS_A[1], POS_B[1]]


def test_setting_markers_replaces_rather_than_appends(qapp):
    """A refresh redraws the whole set, so the second call must not stack."""
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])

    overlay.setMarkers([Marker(POS_B[0], POS_B[1], pg.mkBrush(220, 40, 40), 222)])

    assert len(overlay.scatter.getData()[0]) == 1


def test_marker_carries_its_cell_id_not_the_cell(qapp):
    """Point data holds an id so the scatter never keeps a Cell alive."""
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])

    assert overlay.scatter.points()[0].data() == 111


def test_coverage_draws_one_rect_per_todo_tile(qapp):
    overlay, _view = makeOverlay()

    overlay.setCoverage([POS_A, POS_B], FOV)

    assert len(overlay.coverageItems()) == 2


def test_coverage_rect_spans_one_field_around_the_tile_centre(qapp):
    overlay, _view = makeOverlay()

    overlay.setCoverage([POS_A], FOV)

    rect = overlay.coverageItems()[0].rect()
    assert rect.width() == pytest.approx(FOV[0])
    assert rect.height() == pytest.approx(FOV[1])
    assert rect.center().x() == pytest.approx(POS_A[0])
    assert rect.center().y() == pytest.approx(POS_A[1])


def test_clear_removes_markers_and_coverage(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    overlay.setCoverage([POS_A], FOV)

    overlay.clear()

    assert len(overlay.scatter.getData()[0]) == 0
    assert overlay.coverageItems() == []


def test_release_takes_every_item_out_of_the_view(qapp):
    """The view outlives the overlay, so release must leave nothing behind.

    The coverage items are captured *before* release, because release empties
    the list they are read from: iterating the emptied list afterwards proves
    nothing, and would pass for an implementation that dropped its references
    without ever taking the items out of the view.
    """
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    overlay.setCoverage([POS_A], FOV)
    coverage = overlay.coverageItems()
    assert coverage, "fixture must actually put coverage items in the view"

    overlay.release()

    assert overlay.scatter not in view.addedItems
    assert not any(item in view.addedItems for item in coverage)


def test_clicking_a_marker_reports_its_cell_id(qapp):
    from acq4.modules.Autopatch.progress_overlay import Marker

    overlay, _view = makeOverlay()
    overlay.setMarkers([Marker(POS_A[0], POS_A[1], pg.mkBrush(0, 180, 0), 111)])
    seen = []
    overlay.sigMarkerClicked.connect(seen.append)

    overlay.scatter.sigClicked.emit(overlay.scatter, [overlay.scatter.points()[0]], None)

    assert seen == [111]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/martin/src/acq4/acq4/.claude/worktrees/area1-progress-overlay
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_overlay.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.progress_overlay'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/modules/Autopatch/progress_overlay.py`:

```python
"""Area 1's progress overlay: cell markers and survey coverage drawn into the
region view. Renders lists it is handed and holds no slice, panel, or cells."""

from typing import NamedTuple

import pyqtgraph as pg

from acq4.util import Qt

# Under the region ROIs and over the mirrored pinned frames, so a marker never
# hides the handle the operator needs to grab. PinnedFrameMirror preserves the
# Camera module's own z-order, which is negative, so both layers sit above it.
_COVERAGE_Z = -50
_MARKER_Z = -40

# Markers keep a constant screen size, against the precedent of acq4's other
# two scatters (Photostim, ScanCanvasItem), which both use pxMode=False.
# Data-unit markers vanish when the view is zoomed out to a whole slice, and
# legibility at slice scale is this overlay's entire purpose.
_MARKER_SIZE_PX = 11

_COVERAGE_PEN = pg.mkPen(150, 150, 150, 90)
_COVERAGE_BRUSH = pg.mkBrush(150, 150, 150, 40)


class Marker(NamedTuple):
    """One cell's dot: where it is, how it is coloured, and which cell it is.

    `cellId` is `id(cell)`, never the cell: the scatter must not be a second
    store keeping a Cell alive past CellPanel._cells.
    """

    x: float
    y: float
    brush: object
    cellId: int


class ProgressOverlay(Qt.QObject):
    """Cell markers and to-do coverage in a ViewBox owned by someone else.

    A QObject, unlike the plain PinnedFrameMirror/CameraMirror classes beside
    it, because this layer reports clicks back out.
    """

    # Carries one id(cell). The window maps it back through CellPanel; this
    # object never resolves an id to a cell itself.
    sigMarkerClicked = Qt.Signal(object)

    def __init__(self, view):
        super().__init__()
        self._view = view
        self._coverageItems = []

        self.scatter = pg.ScatterPlotItem(
            pxMode=True, size=_MARKER_SIZE_PX, pen=pg.mkPen(0, 0, 0, 120)
        )
        # addItem() before setZValue(): ViewBox.addItem() raises an item's z to
        # view.zValue()+1 when it is lower, so setting z first collapses it.
        # The same ordering PinnedFrameMirror.refresh() documents.
        self._view.addItem(self.scatter)
        self.scatter.setZValue(_MARKER_Z)
        self.scatter.sigClicked.connect(self._onScatterClicked)

    def setMarkers(self, markers) -> None:
        """Draw exactly `markers`, replacing whatever was drawn before."""
        self.scatter.setData(
            x=[m.x for m in markers],
            y=[m.y for m in markers],
            brush=[m.brush for m in markers],
            data=[m.cellId for m in markers],
        )

    def setCoverage(self, tiles, fov) -> None:
        """Shade one field-sized rect at each of `tiles`, replacing the last set.

        The caller passes the *to-do* tiles, not the covered ones, so an empty
        overlay reads as "fully surveyed" and what is drawn is the actionable
        set.
        """
        self._clearCoverage()
        fovW, fovH = fov
        for cx, cy in tiles:
            item = Qt.QGraphicsRectItem(
                cx - fovW / 2.0, cy - fovH / 2.0, fovW, fovH
            )
            item.setPen(_COVERAGE_PEN)
            item.setBrush(_COVERAGE_BRUSH)
            # Shading is a backdrop, not a target: a click must reach the
            # region ROI or the marker above it, never this.
            item.setAcceptedMouseButtons(Qt.Qt.NoButton)
            self._view.addItem(item)
            item.setZValue(_COVERAGE_Z)
            self._coverageItems.append(item)

    def coverageItems(self) -> list:
        return list(self._coverageItems)

    def clear(self) -> None:
        """Draw nothing, while staying attached to the view."""
        self.setMarkers([])
        self._clearCoverage()

    def release(self) -> None:
        """Take every item back out of a view that outlives this overlay."""
        Qt.disconnect(self.scatter.sigClicked, self._onScatterClicked)
        self._clearCoverage()
        self._view.removeItem(self.scatter)

    def _clearCoverage(self) -> None:
        for item in self._coverageItems:
            self._view.removeItem(item)
        self._coverageItems = []

    def _onScatterClicked(self, _plot, points, _event) -> None:
        if not len(points):
            return
        # The topmost point only. A click landing on overlapping markers is one
        # selection, and Area 5 has one current row.
        self.sigMarkerClicked.emit(points[0].data())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_overlay.py -v
```

Expected: 8 passed, no warnings.

- [ ] **Step 5: Mutation proof**

Change `_clearCoverage`'s body to `pass`. Re-run. Expected: `test_setting_markers_replaces_rather_than_appends` still passes (different layer) but `test_clear_removes_markers_and_coverage` and `test_release_takes_every_item_out_of_the_view` FAIL. Record the line numbers. Restore.

Then change `self.sigMarkerClicked.emit(points[0].data())` to emit `points[0]`. Expected: `test_clicking_a_marker_reports_its_cell_id` FAILS. Record and restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/progress_overlay.py acq4/modules/Autopatch/tests/test_progress_overlay.py
git commit -m "feat: add Area 1's progress overlay renderer"
```

---

## Task 3: The `success` colour source

**Files:**
- Create: `acq4/modules/Autopatch/progress_colors.py`
- Test: `acq4/modules/Autopatch/tests/test_progress_colors.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `ColorContext` — a dataclass with fields `cellIds: list[int]`, `positions: dict[int, tuple[float, float]]`, `dispositions: dict[int, str | None]`, `attempted: set[int]`, `scores: dict[int, float | None]`, `fov: tuple[float, float] | None`, `tileVolume: float | None`, `maxCellDensity: float | None`, `minHealth: float | None`
  - `successBrushes(ctx) -> dict[int, object]`
  - `COLOR_SOURCES` — an ordered list of `(label, key, function)` tuples; this task seeds it with the one entry `("Survey outcome", "success", successBrushes)`
  - `legendFor(key, ctx) -> list[tuple[str, object]]` — `(label, brush)` pairs

Every colour source takes the whole context and returns a brush per cell, rather than being called once per cell, because `density` needs the whole set to compute a neighbourhood at all.

- [ ] **Step 1: Write the failing test**

Create `acq4/modules/Autopatch/tests/test_progress_colors.py`:

```python
"""Tests for the progress overlay's colour sources — the mapping from a cell's
recorded facts to the brush that makes a bad search region obvious at a glance."""

import pytest


def makeContext(**overrides):
    from acq4.modules.Autopatch.progress_colors import ColorContext

    base = dict(
        cellIds=[],
        positions={},
        dispositions={},
        attempted=set(),
        scores={},
        fov=(220e-6, 170e-6),
        tileVolume=None,
        maxCellDensity=None,
        minHealth=None,
    )
    base.update(overrides)
    return ColorContext(**base)


def test_done_and_error_get_different_brushes():
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(
        cellIds=[1, 2],
        dispositions={1: "done", 2: "error"},
        attempted={1, 2},
    )

    brushes = successBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_abandonment_is_not_coloured_as_failure():
    """CellPanel's own COMPLETED comment insists "stopped"/"skipped" are
    abandonment while "error"/"retry-exhausted" are failures. Collapsing them
    would make an operator's own Stop look like dead tissue, which is the
    misreading this whole display exists to prevent.
    """
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(
        cellIds=[1, 2, 3, 4],
        dispositions={
            1: "error",
            2: "retry-exhausted",
            3: "stopped",
            4: "skipped",
        },
        attempted={1, 2, 3, 4},
    )

    brushes = successBrushes(ctx)

    assert brushes[1].color() == brushes[2].color()
    assert brushes[3].color() == brushes[4].color()
    assert brushes[1].color() != brushes[3].color()


def test_attempted_but_unfinished_differs_from_never_attempted():
    """A cell in flight is not a to-do cell; the operator is watching it."""
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ctx = makeContext(cellIds=[1, 2], dispositions={}, attempted={1})

    brushes = successBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_every_terminal_disposition_is_mapped():
    """A disposition falling through to a default is a silent lie about a cell."""
    from acq4.modules.Autopatch.cell_panel import TERMINAL
    from acq4.modules.Autopatch.progress_colors import successBrushes

    ids = list(range(len(TERMINAL)))
    ctx = makeContext(
        cellIds=ids,
        dispositions=dict(zip(ids, sorted(TERMINAL))),
        attempted=set(ids),
    )

    brushes = successBrushes(ctx)

    assert set(brushes) == set(ids)


def test_success_legend_names_every_colour_it_can_draw():
    from acq4.modules.Autopatch.progress_colors import legendFor

    labels = [label for label, _brush in legendFor("success", makeContext())]

    assert labels == ["Patched", "Failed", "Abandoned", "In flight", "To do"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v
```

Expected: all FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.progress_colors'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/modules/Autopatch/progress_colors.py`:

```python
"""Colour sources for Area 1's progress overlay: pure mappings from the facts
recorded about a cell to the brush it is drawn with, plus their legends."""

from dataclasses import dataclass

import pyqtgraph as pg

_GREEN = (0, 170, 60)
_RED = (215, 45, 45)
_AMBER = (230, 160, 30)
_BLUE = (60, 130, 230)
_GREY = (140, 140, 140)

# Failure and abandonment are deliberately distinct: CellPanel's COMPLETED
# comment draws the same line, and an operator's own Stop must not read as dead
# tissue.
_FAILED = frozenset({"error", "retry-exhausted"})
_ABANDONED = frozenset({"stopped", "skipped"})


@dataclass
class ColorContext:
    """Everything a colour source may read, gathered by the window.

    Keyed by id(cell) throughout, and holding no cells: the same discipline
    every id-keyed dict in cell_panel.py follows.

    `fov`, `tileVolume`, `maxCellDensity` and `minHealth` are None when no
    slice exists, which is an ordinary state -- cells can be added by hand
    before a slice does.
    """

    cellIds: list
    positions: dict
    dispositions: dict
    attempted: set
    scores: dict
    fov: tuple | None
    tileVolume: float | None
    maxCellDensity: float | None
    minHealth: float | None


def successBrushes(ctx) -> dict:
    """One brush per cell, by what the run made of it."""
    brushes = {}
    for cellId in ctx.cellIds:
        disposition = ctx.dispositions.get(cellId)
        if disposition == "done":
            color = _GREEN
        elif disposition in _FAILED:
            color = _RED
        elif disposition in _ABANDONED:
            color = _AMBER
        elif cellId in ctx.attempted:
            color = _BLUE
        else:
            color = _GREY
        brushes[cellId] = pg.mkBrush(*color)
    return brushes


def _successLegend(_ctx) -> list:
    return [
        ("Patched", pg.mkBrush(*_GREEN)),
        ("Failed", pg.mkBrush(*_RED)),
        ("Abandoned", pg.mkBrush(*_AMBER)),
        ("In flight", pg.mkBrush(*_BLUE)),
        ("To do", pg.mkBrush(*_GREY)),
    ]


# (label, key, brush function). Key is what the combo carries as item data and
# what legendFor takes, following SearchPanel.regionShape()'s precedent of
# keying on data rather than display text.
COLOR_SOURCES = [
    ("Survey outcome", "success", successBrushes),
]

_LEGENDS = {
    "success": _successLegend,
}


def brushesFor(key, ctx) -> dict:
    """The brushes for colour source `key`."""
    for _label, sourceKey, func in COLOR_SOURCES:
        if sourceKey == key:
            return func(ctx)
    raise KeyError(f"no such colour source: {key!r}")


def legendFor(key, ctx) -> list:
    """(label, brush) pairs naming what colour source `key` can draw."""
    return _LEGENDS[key](ctx)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Mutation proof**

Add `"stopped"` to `_FAILED` and remove it from `_ABANDONED`. Expected: `test_abandonment_is_not_coloured_as_failure` FAILS. Record the line. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/progress_colors.py acq4/modules/Autopatch/tests/test_progress_colors.py
git commit -m "feat: colour progress markers by survey outcome"
```

---

## Task 4: The `health` colour source

**Blocked by Task 1** (needs `Cell.score` declared and merged).

**Files:**
- Modify: `acq4/modules/Autopatch/progress_colors.py`
- Test: `acq4/modules/Autopatch/tests/test_progress_colors.py`

**Interfaces:**
- Consumes: `ColorContext`, `COLOR_SOURCES`, `_LEGENDS` from Task 3.
- Produces: `healthBrushes(ctx) -> dict[int, object]`; a second entry in `COLOR_SOURCES`, `("Detection health", "health", healthBrushes)`.

**The load-bearing detail:** the ramp spans `[minHealth, 1]`, not `[0, 1]`. `CellProducer._isHealthy` (`cell_producer.py:118`) drops every candidate below `constraints.min_health` before it becomes a cell, so no drawn cell can score below the cutoff (default 0.5). A `[0, 1]` ramp would spend half its range on impossible values — the difference between "these all look alike" and "this corner scored worse".

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_progress_colors.py`:

```python
def test_unscored_cells_are_visibly_distinct_from_scored_ones():
    """score is None means "nobody scored this", not "scored badly". Every
    hand-added cell is unscored, since only _build_cells scores.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: None, 2: 0.5}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_health_ramp_is_anchored_at_the_cutoff_not_at_zero():
    """Two cells scoring 0.6 and 0.9 against a 0.5 cutoff must look different.

    This is the test that kills a [0, 1] ramp, and the mutant a reader would
    not suspect: both values are perfectly legal [0, 1] scores, and a [0, 1]
    ramp renders them nearly identical because it spends half its range below
    the cutoff on scores that cannot occur.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    anchored = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.6, 2: 0.9}, minHealth=0.5)
    )
    full = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.6, 2: 0.9}, minHealth=None)
    )

    anchoredGap = abs(anchored[1].color().green() - anchored[2].color().green())
    fullGap = abs(full[1].color().green() - full[2].color().green())
    assert anchoredGap > fullGap


def test_the_cutoff_score_sits_at_the_bottom_of_the_ramp():
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: 0.5, 2: 1.0}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()


def test_health_falls_back_to_a_zero_to_one_ramp_with_no_slice():
    """No slice means no constraints, and so no cutoff to anchor to.

    Asserts the fallback ramp's *shape*, not merely that a brush came back:
    across [0, 1], scores of 0.0 and 0.5 are half the range apart and must
    differ. Under a 0.5-anchored ramp both clamp to the bottom and collapse to
    the same colour, so this is the assertion that tells the two ramps apart.
    """
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    brushes = healthBrushes(
        makeContext(cellIds=[1, 2], scores={1: 0.0, 2: 0.5}, minHealth=None)
    )

    assert brushes[1].color() != brushes[2].color()


def test_a_score_outside_the_ramp_is_clamped_not_raised():
    """Nothing queued can produce one; this guards a future detector."""
    from acq4.modules.Autopatch.progress_colors import healthBrushes

    ctx = makeContext(cellIds=[1, 2], scores={1: -0.5, 2: 1.5}, minHealth=0.5)

    brushes = healthBrushes(ctx)

    assert brushes[1].color() != brushes[2].color()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v -k health or unscored or cutoff or clamped
```

Use the quoted form to avoid shell word-splitting:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v -k "health or unscored or cutoff or clamped"
```

Expected: FAIL with `ImportError: cannot import name 'healthBrushes'`.

- [ ] **Step 3: Write minimal implementation**

In `acq4/modules/Autopatch/progress_colors.py`, add after `_successLegend`:

```python
# Hollow, so "never scored" reads as absence rather than as a low score.
_UNSCORED_BRUSH = pg.mkBrush(0, 0, 0, 0)

# Dim violet to bright green across the scored range. Endpoints differ in every
# channel so no single-channel comparison can mistake one end for the other.
_HEALTH_CMAP = pg.ColorMap([0.0, 1.0], [(90, 50, 140, 255), (60, 225, 120, 255)])


def healthBrushes(ctx) -> dict:
    """One brush per cell, by the detector's health score.

    The ramp spans [min_health, 1], not [0, 1]: CellProducer._isHealthy drops
    every candidate below the cutoff before it becomes a cell, so a [0, 1] ramp
    would spend half its range on scores that cannot occur and render the
    cells that do occur nearly identical. With no slice there is no cutoff, so
    it falls back to [0, 1].
    """
    low = 0.0 if ctx.minHealth is None else float(ctx.minHealth)
    # A cutoff of exactly 1.0 would leave the ramp no width at all.
    span = 1.0 - low
    brushes = {}
    for cellId in ctx.cellIds:
        score = ctx.scores.get(cellId)
        if score is None:
            brushes[cellId] = _UNSCORED_BRUSH
            continue
        fraction = 0.0 if span <= 0 else (float(score) - low) / span
        fraction = min(1.0, max(0.0, fraction))
        brushes[cellId] = pg.mkBrush(_HEALTH_CMAP.map(fraction, mode="qcolor"))
    return brushes


def _healthLegend(ctx) -> list:
    low = 0.0 if ctx.minHealth is None else float(ctx.minHealth)
    return [
        (f"{low:.2f} (cutoff)", pg.mkBrush(_HEALTH_CMAP.map(0.0, mode="qcolor"))),
        ("1.00", pg.mkBrush(_HEALTH_CMAP.map(1.0, mode="qcolor"))),
        ("Unscored", _UNSCORED_BRUSH),
    ]
```

Then extend the two registries:

```python
COLOR_SOURCES = [
    ("Survey outcome", "success", successBrushes),
    ("Detection health", "health", healthBrushes),
]

_LEGENDS = {
    "success": _successLegend,
    "health": _healthLegend,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Mutation proof**

Replace `low = 0.0 if ctx.minHealth is None else float(ctx.minHealth)` with `low = 0.0`. Expected: `test_health_ramp_is_anchored_at_the_cutoff_not_at_zero` FAILS. Record the line. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/progress_colors.py acq4/modules/Autopatch/tests/test_progress_colors.py
git commit -m "feat: colour progress markers by detection health"
```

---

## Task 5: The `density` colour source

**Files:**
- Modify: `acq4/modules/Autopatch/progress_colors.py`
- Test: `acq4/modules/Autopatch/tests/test_progress_colors.py`

**Interfaces:**
- Consumes: `ColorContext`, `COLOR_SOURCES`, `_LEGENDS`.
- Produces: `densityBrushes(ctx) -> dict[int, object]`; a third `COLOR_SOURCES` entry `("Local density", "density", densityBrushes)`.

**Match the engine exactly.** `CellProducer._isCrowded` (`cell_producer.py:123`) computes `len(slice.cellsNearTile(tile)) / slice.tileVolume() >= constraints.max_cell_density`, and `Slice.cellsNearTile` counts cells within `±fov/2` in **x and y only** (`slice.py:333`). So this source counts neighbours in the same XY window, divides by the same `tileVolume`, and normalises by the same cap — which is what stops the display and the engine disagreeing about "crowded". It reads `ctx.positions`, **never** `Slice.cellsNearTile()`, which calls the thread-unsafe `cell.position`.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_progress_colors.py`:

```python
def test_a_crowded_neighbourhood_differs_from_a_lonely_one():
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    # Three cells within one field of each other, and one far away.
    ctx = makeContext(
        cellIds=[1, 2, 3, 9],
        positions={
            1: (1.0e-3, 2.0e-3),
            2: (1.00002e-3, 2.00002e-3),
            3: (1.00004e-3, 2.00004e-3),
            9: (5.0e-3, 4.0e-3),
        },
        tileVolume=220e-6 * 170e-6 * 40e-6,
        maxCellDensity=5e12,
    )

    brushes = densityBrushes(ctx)

    assert brushes[1].color() != brushes[9].color()


def test_density_counts_neighbours_in_the_same_xy_window_as_the_engine():
    """Slice.cellsNearTile uses a +/- fov/2 box in x and y and ignores z, and
    the producer divides that count by tileVolume. Matching it is what keeps
    the display and the density cap from disagreeing about "crowded".
    """
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    fov = (220e-6, 170e-6)
    # Just inside the window in x, and just outside it.
    inside = (1.0e-3 + fov[0] / 2 * 0.9, 2.0e-3)
    outside = (1.0e-3 + fov[0] / 2 * 1.1, 2.0e-3)

    withInside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: inside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )
    withOutside = densityBrushes(
        makeContext(
            cellIds=[1, 2],
            positions={1: (1.0e-3, 2.0e-3), 2: outside},
            fov=fov,
            tileVolume=fov[0] * fov[1] * 40e-6,
            maxCellDensity=5e12,
        )
    )

    assert withInside[1].color() != withOutside[1].color()


def test_density_falls_back_to_a_raw_count_with_no_slice():
    """No slice means no tileVolume and no cap to normalise against.

    Asserts the raw scale still *ranks*, rather than merely that every cell got
    a brush: two neighbours must colour differently from a lonely cell. A
    fallback that returned one flat colour would satisfy a keys-only assertion
    while telling the operator nothing.
    """
    from acq4.modules.Autopatch.progress_colors import densityBrushes

    ctx = makeContext(
        cellIds=[1, 2, 9],
        positions={
            1: (1.0e-3, 2.0e-3),
            2: (1.00002e-3, 2.00002e-3),
            9: (5.0e-3, 4.0e-3),
        },
        tileVolume=None,
        maxCellDensity=None,
    )

    brushes = densityBrushes(ctx)

    assert brushes[1].color() != brushes[9].color()


def test_density_legend_says_when_it_is_unnormalised():
    from acq4.modules.Autopatch.progress_colors import legendFor

    normalised = legendFor(
        "density", makeContext(tileVolume=1.0e-12, maxCellDensity=5e12)
    )
    raw = legendFor("density", makeContext(tileVolume=None, maxCellDensity=None))

    assert [label for label, _b in normalised] != [label for label, _b in raw]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v -k density
```

Expected: FAIL with `ImportError: cannot import name 'densityBrushes'`.

- [ ] **Step 3: Write minimal implementation**

Add to `acq4/modules/Autopatch/progress_colors.py`:

```python
# Sparse to crowded. Deliberately not the success source's red: switching
# sources must not make a crowded neighbourhood read as a failed cell.
_DENSITY_CMAP = pg.ColorMap([0.0, 1.0], [(70, 110, 200, 255), (240, 140, 20, 255)])

# The count a raw, unnormalised scale saturates at, used only when there is no
# slice to supply tileVolume and the density cap. Ten cells inside one field is
# already crowded tissue by the default cap's standard.
_RAW_DENSITY_FULL_SCALE = 10.0


def _neighbourCount(cellId, ctx) -> int:
    """Cells inside `cellId`'s own field-sized xy window, including itself.

    The same window Slice.cellsNearTile uses -- +/- fov/2 in x and y, with no z
    term -- so this count is the one the density cap is expressed in.
    """
    here = ctx.positions.get(cellId)
    if here is None or ctx.fov is None:
        return 0
    fovW, fovH = ctx.fov
    count = 0
    for otherId in ctx.cellIds:
        there = ctx.positions.get(otherId)
        if there is None:
            continue
        if abs(there[0] - here[0]) <= fovW / 2 and abs(there[1] - here[1]) <= fovH / 2:
            count += 1
    return count


def densityBrushes(ctx) -> dict:
    """One brush per cell, by how crowded its own neighbourhood is.

    Normalised against constraints.max_cell_density so the colour means "how
    close is this neighbourhood to the cap the producer would skip a tile
    for". Reads ctx.positions rather than Slice.cellsNearTile(), which calls
    the thread-unsafe Cell.position.
    """
    normalised = ctx.tileVolume not in (None, 0) and ctx.maxCellDensity not in (None, 0)
    brushes = {}
    for cellId in ctx.cellIds:
        count = _neighbourCount(cellId, ctx)
        if normalised:
            fraction = (count / ctx.tileVolume) / ctx.maxCellDensity
        else:
            fraction = count / _RAW_DENSITY_FULL_SCALE
        fraction = min(1.0, max(0.0, fraction))
        brushes[cellId] = pg.mkBrush(_DENSITY_CMAP.map(fraction, mode="qcolor"))
    return brushes


def _densityLegend(ctx) -> list:
    normalised = ctx.tileVolume not in (None, 0) and ctx.maxCellDensity not in (None, 0)
    top = "At the density cap" if normalised else f"{int(_RAW_DENSITY_FULL_SCALE)}+ per field"
    return [
        ("Sparse", pg.mkBrush(_DENSITY_CMAP.map(0.0, mode="qcolor"))),
        (top, pg.mkBrush(_DENSITY_CMAP.map(1.0, mode="qcolor"))),
    ]
```

Extend the registries:

```python
COLOR_SOURCES = [
    ("Survey outcome", "success", successBrushes),
    ("Detection health", "health", healthBrushes),
    ("Local density", "density", densityBrushes),
]

_LEGENDS = {
    "success": _successLegend,
    "health": _healthLegend,
    "density": _densityLegend,
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_progress_colors.py -v
```

Expected: 14 passed.

- [ ] **Step 5: Mutation proof**

In `_neighbourCount`, change `abs(there[1] - here[1]) <= fovH / 2` to use `fovW / 2`. Expected: `test_density_counts_neighbours_in_the_same_xy_window_as_the_engine` FAILS — this is exactly the swapped-axis mutant that survived 324 tests when fixtures were square, which is why `FOV` is asymmetric. Record the line. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/progress_colors.py acq4/modules/Autopatch/tests/test_progress_colors.py
git commit -m "feat: colour progress markers by local cell density"
```

---

## Task 6: `CellPanel` reports its cells and announces state changes

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` — add methods near `disposition()` (line 458); emit in `addCell` (395), `_onCellFinished` (757), `_onReuseCheckedCells` (536), `_onCellsDiscarded` (324)
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `CellPanel.cells() -> list` — every cell the panel knows about
  - `CellPanel.sigCellStateChanged = Qt.Signal()` — carries nothing; a "re-read me" nudge

**Why the panel and not the slice:** `CellPanel` is the complete registry. `Slice.registerCells()` has one production caller (`cell_producer.py:93`), so every cell from "Add from target" and "Scatter fake cells" is absent from the slice. An overlay reading the slice would silently omit them.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_cell_panel.py`. Match the file's existing fixtures and cell stubs; if it builds panels through a local helper, use it rather than constructing `CellPanel()` inline.

```python
def test_cells_reports_every_cell_the_panel_knows(qapp):
    panel = makePanel()
    first, second = object(), object()

    panel.addCell(first)
    panel.addCell(second)

    assert panel.cells() == [first, second]


def test_cells_includes_a_hand_added_cell_absent_from_any_slice(qapp):
    """The overlay reads this, not Slice._cells, because registerCells() has
    one production caller and hand-added cells never reach it. Reading the
    slice instead would silently omit every "Add from target" cell.
    """
    panel = makePanel()
    handAdded = object()

    panel.addCell(handAdded)

    assert handAdded in panel.cells()


def test_adding_a_cell_announces_a_state_change(qapp):
    panel = makePanel()
    seen = []
    panel.sigCellStateChanged.connect(lambda: seen.append(True))

    panel.addCell(object())

    assert seen == [True]


def test_a_finished_cell_announces_a_state_change(qapp):
    panel = makePanel()
    cell = object()
    panel.addCell(cell)
    seen = []
    panel.sigCellStateChanged.connect(lambda: seen.append(True))

    panel._onCellFinished(cell, "done")

    assert seen == [True]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k "cells_reports or hand_added or announces"
```

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'cells'` and `... 'sigCellStateChanged'`.

- [ ] **Step 3: Write minimal implementation**

Add the signal beside the existing ones near line 48:

```python
    # Emitted whenever a cell's row or disposition changes, so a view over this
    # panel's state -- Area 1's progress overlay -- knows to re-read it. Carries
    # nothing on purpose: pushing the state would give that view a second copy
    # to keep in sync, and this panel's whole discipline is having exactly one.
    sigCellStateChanged = Qt.Signal()
```

Add the reader beside `disposition()`:

```python
    def cells(self) -> list:
        """Every cell this panel knows about, in the order they were added.

        This panel is the complete registry: Slice.registerCells() is reached
        only from CellProducer, so cells seeded by hand ("Add from target",
        "Scatter fake cells") live here and nowhere else.
        """
        return list(self._cells.values())
```

Emit at the end of `addCell` (after `self._cells[id(cell)] = cell`), and at the end of `_onCellFinished`, `_onReuseCheckedCells`, and `_onCellsDiscarded`:

```python
        self.sigCellStateChanged.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v
```

Expected: all pass, including the file's pre-existing tests.

- [ ] **Step 5: Mutation proof**

Change `cells()` to `return list(self._rows.values())`. Expected: `test_cells_reports_every_cell_the_panel_knows` FAILS (it returns list items, not cells). Record the line. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_panel.py
git commit -m "feat: let CellPanel report its cells and announce state changes"
```

---

## Task 7: `CellPanel.selectCell()`

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` — near `_onCellSelectionChanged` (line 779)
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: `CellPanel.cells()` from Task 6.
- Produces: `CellPanel.selectCell(cell) -> None` — makes that cell's row current; a no-op for a cell with no row.

- [ ] **Step 1: Write the failing test**

```python
def test_select_cell_makes_that_row_current(qapp):
    panel = makePanel()
    first, second = object(), object()
    panel.addCell(first)
    panel.addCell(second)

    panel.selectCell(second)

    assert panel.cellList.currentItem().data(Qt.Qt.UserRole) is second


def test_select_cell_ignores_a_cell_with_no_row(qapp):
    """Area 1 can report a click for a cell the panel has already discarded.

    Two halves, both required: a stale click must not raise out of a Qt slot,
    and it must not silently move the operator's current selection either.
    """
    panel = makePanel()
    known = object()
    panel.addCell(known)
    panel.selectCell(known)

    panel.selectCell(object())

    assert panel.cellList.currentItem().data(Qt.Qt.UserRole) is known
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k select_cell
```

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'selectCell'`.

- [ ] **Step 3: Write minimal implementation**

```python
    def selectCell(self, cell) -> None:
        """Make `cell`'s row current, so Area 5 shows its timeline and log.

        A no-op for a cell with no row. Area 1's overlay can report a click for
        a cell a rescan has since discarded, and raising out of a Qt slot over
        a stale selection is not an option.
        """
        item = self._rows.get(id(cell))
        if item is None:
            return
        self.cellList.setCurrentItem(item)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v
```

Expected: all pass.

- [ ] **Step 5: Mutation proof**

Remove the `if item is None: return` guard. Expected: `test_select_cell_ignores_a_cell_with_no_row` FAILS with a `TypeError` from `setCurrentItem(None)`. Record the line. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_panel.py
git commit -m "feat: let Area 5's cell list be selected from outside"
```

---

## Task 8: The colour-source selector in `RegionPanel`

**Files:**
- Modify: `acq4/modules/Autopatch/region_panel.py:145-180` (controls row) and add accessors near `regionShape()` (line 319)
- Test: `acq4/modules/Autopatch/tests/test_region_panel.py`

**Interfaces:**
- Consumes: `COLOR_SOURCES` from Task 5.
- Produces:
  - `RegionPanel.colorCombo` — a `QComboBox` carrying each source's key as item data
  - `RegionPanel.colorSource() -> str` — the selected key
  - `RegionPanel.sigColorSourceChanged = Qt.Signal(object)` — the new key
  - `RegionPanel.setLegend(entries: list[tuple[str, object]]) -> None`

The selector belongs to `RegionPanel` because it is a control in Area 1's control row, and `RegionPanel` already owns that row. It stays ignorant of cells: it reports a key string and renders `(label, brush)` pairs it is handed.

- [ ] **Step 1: Write the failing test**

```python
def test_colour_source_combo_carries_keys_as_item_data(qapp):
    """Item data, not display text, for the same reason regionShape() does:
    the window maps a key to a colour function, and a label is a label."""
    from acq4.modules.Autopatch.progress_colors import COLOR_SOURCES

    panel = makePanel()

    keys = [
        panel.colorCombo.itemData(i) for i in range(panel.colorCombo.count())
    ]
    assert keys == [key for _label, key, _func in COLOR_SOURCES]


def test_colour_source_reports_the_selection(qapp):
    panel = makePanel()

    panel.colorCombo.setCurrentIndex(1)

    assert panel.colorSource() == panel.colorCombo.itemData(1)


def test_changing_the_colour_source_announces_the_new_key(qapp):
    panel = makePanel()
    seen = []
    panel.sigColorSourceChanged.connect(seen.append)

    panel.colorCombo.setCurrentIndex(1)

    assert seen == [panel.colorCombo.itemData(1)]


def test_legend_renders_one_entry_per_pair(qapp):
    import pyqtgraph as pg

    panel = makePanel()

    panel.setLegend([("Patched", pg.mkBrush(0, 170, 60)), ("Failed", pg.mkBrush(215, 45, 45))])

    assert panel.legendLabels() == ["Patched", "Failed"]


def test_setting_a_legend_replaces_the_last_one(qapp):
    import pyqtgraph as pg

    panel = makePanel()
    panel.setLegend([("Patched", pg.mkBrush(0, 170, 60))])

    panel.setLegend([("Sparse", pg.mkBrush(70, 110, 200))])

    assert panel.legendLabels() == ["Sparse"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -v -k "colour or legend"
```

Expected: FAIL with `AttributeError: 'RegionPanel' object has no attribute 'colorCombo'`.

- [ ] **Step 3: Write minimal implementation**

Add the signal beside the existing two (line 115):

```python
    sigColorSourceChanged = Qt.Signal(object)
```

In `__init__`, after `self.mirrorCheck` is built:

```python
        # Item data, not display text, the same contract regionShape() keeps.
        self.colorCombo = Qt.QComboBox()
        for label, key, _func in COLOR_SOURCES:
            self.colorCombo.addItem(label, key)
        self.colorCombo.setToolTip("What the cell markers are coloured by.")

        # A row of swatch+label pairs rebuilt whenever the source changes. The
        # panel renders pairs it is handed and never computes a colour itself.
        self.legendRow = Qt.QHBoxLayout()
```

Add to the controls layout, before `controls.addStretch()`:

```python
        controls.addWidget(self.colorCombo)
```

Add the legend row to the outer layout, between the controls and the view:

```python
        layout.addLayout(self.legendRow)
```

Connect at the bottom of `__init__`:

```python
        self.colorCombo.currentIndexChanged.connect(
            lambda _index: self.sigColorSourceChanged.emit(self.colorSource())
        )
```

Add the accessors near `regionShape()`:

```python
    def colorSource(self) -> str:
        """The key of the selected colour source."""
        return self.colorCombo.currentData()

    def setLegend(self, entries) -> None:
        """Show one swatch and label per (label, brush) pair, replacing the last set."""
        while self.legendRow.count():
            item = self.legendRow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        for label, brush in entries:
            swatch = Qt.QLabel()
            swatch.setFixedSize(12, 12)
            swatch.setAutoFillBackground(True)
            palette = swatch.palette()
            palette.setColor(swatch.backgroundRole(), brush.color())
            swatch.setPalette(palette)
            self.legendRow.addWidget(swatch)
            self.legendRow.addWidget(Qt.QLabel(label))
        self.legendRow.addStretch()

    def legendLabels(self) -> list:
        """The legend's text labels, in order. For tests and for the operator's
        own sanity check that the swatches say what they mean."""
        labels = []
        for i in range(self.legendRow.count()):
            widget = self.legendRow.itemAt(i).widget()
            if isinstance(widget, Qt.QLabel) and widget.text():
                labels.append(widget.text())
        return labels
```

Add the import at the top of the module:

```python
from .progress_colors import COLOR_SOURCES
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -v
```

Expected: all pass, including the file's pre-existing tests.

- [ ] **Step 5: Mutation proof**

Change `self.colorCombo.addItem(label, key)` to `addItem(label)` (no data). Expected: `test_colour_source_combo_carries_keys_as_item_data` FAILS. Record the line. Restore.

Then remove the `while self.legendRow.count()` clearing loop. Expected: `test_setting_a_legend_replaces_the_last_one` FAILS. Record and restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/region_panel.py acq4/modules/Autopatch/tests/test_region_panel.py
git commit -m "feat: add Area 1's colour-source selector and legend"
```

---

## Task 9: The window join — build the context and refresh

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` — construct beside `PinnedFrameMirror` (line 117); wire beside the existing panel connections (168-199); add `_refreshProgress` beside `_refreshSurveyStats` (line 572)
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `ProgressOverlay`, `Marker` (Task 2); `ColorContext`, `brushesFor`, `legendFor` (Tasks 3-5); `CellPanel.cells()`, `sigCellStateChanged` (Task 6); `RegionPanel.colorSource()`, `setLegend()`, `sigColorSourceChanged` (Task 8).
- Produces:
  - `AutopatchWindow._progressOverlay` — the `ProgressOverlay`
  - `AutopatchWindow._cellPositions: dict[int, tuple[float, float]]`
  - `AutopatchWindow._refreshProgress() -> None`
  - `AutopatchWindow._colorContext() -> ColorContext`

**The position rule:** first placement reads `cell.initialPosition`; updates arrive as `sigPositionChanged` payloads (Task 10). Never `cell.position`.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_window_integration.py`, following the file's existing window fixture (it already builds a window and registers a slice around line 1238):

```python
def test_a_seeded_cell_gets_a_marker(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)

    win.cellPanel.addCell(cell)

    assert len(win._progressOverlay.scatter.getData()[0]) == 1


def test_marker_position_comes_from_initial_position_not_position(qapp, win):
    """cell.position evaluates max(self._positions), iterating a dict the
    tracking worker writes. initialPosition is assigned once and never
    mutated, so it is the only safe read on the GUI thread.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)

    win.cellPanel.addCell(cell)

    x, y = win._progressOverlay.scatter.getData()
    assert x[0] == pytest.approx(1.0e-3)
    assert y[0] == pytest.approx(2.0e-3)


def test_a_finished_cell_is_recoloured(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    win.cellPanel._onCellFinished(cell, "done")

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    assert after != before


def test_changing_the_colour_source_recolours_without_a_run(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    cell.score = 0.9
    win.cellPanel.addCell(cell)
    before = win._progressOverlay.scatter.points()[0].brush().color().name()

    index = [k for _l, k, _f in COLOR_SOURCES].index("health")
    win.regionPanel.colorCombo.setCurrentIndex(index)

    after = win._progressOverlay.scatter.points()[0].brush().color().name()
    assert after != before


def test_the_legend_follows_the_colour_source(qapp, win):
    index = [k for _l, k, _f in COLOR_SOURCES].index("density")
    win.regionPanel.colorCombo.setCurrentIndex(index)

    assert win.regionPanel.legendLabels() == ["Sparse", "At the density cap"]


def test_coverage_draws_the_todo_tiles_not_the_covered_ones(qapp, win):
    _sliceWithTodoTiles(win)
    grid = win.slice.tileGrid()
    win.slice.markCovered(grid[0])

    win._onRunStatus("waiting")

    assert len(win._progressOverlay.coverageItems()) == len(grid) - 1
```

These use the `win` fixture and the `_makeCellAt` / `_sliceWithTodoTiles` helpers from the Test Scaffolding section above. Add those helpers first if an earlier task has not already.

- [ ] **Step 2: Run test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k "marker or recolour or legend_follows or todo_tiles"
```

Expected: FAIL with `AttributeError: 'AutopatchWindow' object has no attribute '_progressOverlay'`.

- [ ] **Step 3: Write minimal implementation**

Imports at the top of `Autopatch.py`:

```python
from .progress_colors import ColorContext, brushesFor, legendFor
from .progress_overlay import Marker, ProgressOverlay
```

In `__init__`, after `self._pinnedFrameMirror = PinnedFrameMirror(self.regionPanel.view)`:

```python
        self._progressOverlay = ProgressOverlay(self.regionPanel.view)
        # id(cell) -> the last (x, y) global position known for it. Seeded from
        # cell.initialPosition and updated from sigPositionChanged payloads:
        # cell.position evaluates max(self._positions), which iterates a dict
        # the tracking worker writes, so reading it here is an intermittent
        # RuntimeError. Ids and plain tuples, never cells, for the same reason
        # every dict in cell_panel.py holds ids.
        self._cellPositions: dict[int, tuple] = {}
```

Wire beside the other panel connections:

```python
        self.cellPanel.sigCellStateChanged.connect(self._onCellStateChanged)
        self.regionPanel.sigColorSourceChanged.connect(
            lambda _key: self._refreshProgress()
        )
```

Add the methods beside `_refreshSurveyStats`:

```python
    def _onCellStateChanged(self) -> None:
        """Re-read the cell panel after a row or disposition changed."""
        self._syncCellPositions()
        self._refreshProgress()

    def _syncCellPositions(self) -> None:
        """Seed a position for every cell that has none, and drop the departed.

        Reads cell.initialPosition, which __init__ assigns once and nothing
        mutates. Live updates arrive through sigPositionChanged instead.
        """
        known = set()
        for cell in self.cellPanel.cells():
            cellId = id(cell)
            known.add(cellId)
            if cellId not in self._cellPositions:
                position = getattr(cell, "initialPosition", None)
                if position is not None:
                    self._cellPositions[cellId] = (position[0], position[1])
        for departed in set(self._cellPositions) - known:
            del self._cellPositions[departed]

    def _colorContext(self) -> ColorContext:
        """Everything the colour sources may read, gathered in one pass.

        The slice-derived fields are None when there is no slice, which is
        ordinary: cells can be seeded by hand before one exists.
        """
        cells = self.cellPanel.cells()
        constraints = None if self.slice is None else self.slice.constraints
        return ColorContext(
            cellIds=[id(c) for c in cells],
            positions=dict(self._cellPositions),
            dispositions={id(c): self.cellPanel.disposition(c) for c in cells},
            attempted={id(c) for c in cells if self.cellPanel.isAttempted(c)},
            # getattr, not c.score, despite Task 1 declaring the attribute:
            # CellPanel accepts anything as a cell -- its own tests seed plain
            # object() rows -- so this window cannot assume every row's payload
            # is a Cell. This is a deliberate departure from the spec's §5.1
            # wording ("read cell.score plainly"), which was written about the
            # cross-repo dependency rather than about the panel's stub-tolerance.
            scores={id(c): getattr(c, "score", None) for c in cells},
            fov=None if self.slice is None else self.slice.fov,
            tileVolume=None if self.slice is None else self.slice.tileVolume(),
            maxCellDensity=None if constraints is None else constraints.max_cell_density,
            minHealth=None if constraints is None else constraints.min_health,
        )

    def _refreshProgress(self) -> None:
        """Redraw Area 1's markers and legend from current state."""
        if self._tornDown:
            return
        ctx = self._colorContext()
        key = self.regionPanel.colorSource()
        brushes = brushesFor(key, ctx)
        self._progressOverlay.setMarkers([
            Marker(
                self._cellPositions[cellId][0],
                self._cellPositions[cellId][1],
                brushes[cellId],
                cellId,
            )
            for cellId in ctx.cellIds
            if cellId in self._cellPositions
        ])
        self.regionPanel.setLegend(legendFor(key, ctx))

    def _refreshCoverage(self) -> None:
        """Shade the tiles still to be surveyed."""
        if self._tornDown or self.slice is None:
            self._progressOverlay.setCoverage([], (0.0, 0.0))
            return
        covered = set(self.slice.coveredTiles())
        todo = [tile for tile in self.slice.tileGrid() if tile not in covered]
        self._progressOverlay.setCoverage(todo, self.slice.fov)
```

Call both from `_onRunStatus`, beside the existing survey-stats refresh:

```python
        if status in ("surveying", "waiting"):
            self._refreshSurveyStats()
            self._refreshCoverage()
            self._refreshProgress()
```

`Slice` exposes its field of view as `self._fov`; if there is no public `fov` property, add one beside `constraints` in `acq4/experiment/slice.py`:

```python
    @property
    def fov(self) -> tuple[float, float]:
        """The imaged field's (width, height) in global metres."""
        return self._fov
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v
```

Expected: all pass.

- [ ] **Step 5: Mutation proof**

In `_syncCellPositions`, change `getattr(cell, "initialPosition", None)` to `cell.position`. Expected: `test_marker_position_comes_from_initial_position_not_position` still passes on a freshly-built cell (both agree at construction) — **this mutation does not fail, and that is the finding**. Add the concurrency test from Task 10 Step 1 before treating this line as proven, then re-run this mutation and confirm it fails there. Record both results.

Then change `todo = [tile for tile in ... if tile not in covered]` to `todo = list(self.slice.tileGrid())`. Expected: `test_coverage_draws_the_todo_tiles_not_the_covered_ones` FAILS. Record and restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/Autopatch.py acq4/experiment/slice.py acq4/modules/Autopatch/tests/test_window_integration.py
git commit -m "feat: join cell state and coverage into Area 1's overlay"
```

---

## Task 10: Live positions and connection lifetime

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` — `_syncCellPositions`, `teardown` (line 741)
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`, `acq4/modules/Autopatch/tests/test_teardown.py`

**Interfaces:**
- Consumes: `_cellPositions`, `_refreshProgress` (Task 9).
- Produces: `AutopatchWindow._onCellMoved(position) -> None`; `_releaseCellPositionConnections() -> None`.

**Why this task is separate:** it is the one that pays the module's most-repeated defect — connections outliving their owner. Task 9's mutation proof is explicitly incomplete without the concurrency test written here.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_tracked_cell_marker_follows_its_position_signal(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)

    cell.sigPositionChanged.emit(Point([1.4e-3, 2.1e-3, -30e-6], "global"))

    x, y = win._progressOverlay.scatter.getData()
    assert x[0] == pytest.approx(1.4e-3)
    assert y[0] == pytest.approx(2.1e-3)


def test_refresh_never_iterates_the_tracked_positions_dict(qapp, win):
    """Cell.position does max(self._positions) while the tracking worker
    inserts into it. This proves the overlay path does not go near it: a
    _positions that raises on iteration must not break a refresh.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)

    class Exploding(dict):
        def __iter__(self):
            raise RuntimeError("dictionary changed size during iteration")

        def keys(self):
            raise RuntimeError("dictionary changed size during iteration")

    cell._positions = Exploding(cell._positions)

    win._refreshProgress()

    assert len(win._progressOverlay.scatter.getData()[0]) == 1


def test_teardown_disconnects_every_cell_position_connection(qapp, win):
    """Qt's own receivers() count, not merely that an object was collectable:
    P2c-3a found a mandated mutation that did not fail because a nearby
    `= None` had already broken the cycle refcounting could see.
    """
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)
    assert cell.receivers(cell.sigPositionChanged) == 1

    win.teardown()

    assert cell.receivers(cell.sigPositionChanged) == 0


def test_discarding_a_cell_disconnects_it(qapp, win):
    cell = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    win.cellPanel.addCell(cell)

    win.cellPanel.discardCells([cell])

    assert cell.receivers(cell.sigPositionChanged) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k "follows_its_position or never_iterates or disconnects"
```

Expected: `follows_its_position` FAILS (marker does not move), `disconnects` FAILS (`receivers` is 0 before teardown, so the first assert fails).

- [ ] **Step 3: Write minimal implementation**

Track the connected cells. In `__init__`, beside `_cellPositions`:

```python
        # id(cell) -> the cell, for the sigPositionChanged connections this
        # window made and must sever. A strong reference is unavoidable to
        # disconnect, and is safe: CellPanel._cells already holds every one of
        # these for its own lifetime, so this adds no lifetime, only a handle.
        self._positionConnected: dict[int, object] = {}
```

Extend `_syncCellPositions` to connect and disconnect:

```python
        for cell in self.cellPanel.cells():
            cellId = id(cell)
            known.add(cellId)
            if cellId not in self._cellPositions:
                position = getattr(cell, "initialPosition", None)
                if position is not None:
                    self._cellPositions[cellId] = (position[0], position[1])
            signal = getattr(cell, "sigPositionChanged", None)
            if signal is not None and cellId not in self._positionConnected:
                signal.connect(self._onCellMoved)
                self._positionConnected[cellId] = cell
        for departed in set(self._cellPositions) - known:
            del self._cellPositions[departed]
        for departed in set(self._positionConnected) - known:
            self._disconnectCellPosition(departed)
```

Add the handler and the releases:

```python
    def _onCellMoved(self, position) -> None:
        """Record a tracked cell's new position and redraw its marker.

        The payload carries the position, so nothing here reads
        Cell.position or the _positions dict behind it. Qt routes this from
        the tracking worker onto the GUI thread by queued connection.
        """
        if self._tornDown:
            return
        cell = self.sender()
        if cell is None:
            return
        self._cellPositions[id(cell)] = (position[0], position[1])
        self._refreshProgress()

    def _disconnectCellPosition(self, cellId) -> None:
        cell = self._positionConnected.pop(cellId, None)
        if cell is None:
            return
        Qt.disconnect(cell.sigPositionChanged, self._onCellMoved)

    def _releaseCellPositionConnections(self) -> None:
        """Sever every sigPositionChanged connection this window made."""
        for cellId in list(self._positionConnected):
            self._disconnectCellPosition(cellId)
        self._cellPositions.clear()
```

Call it from `teardown`, in the same `finally` block that releases the mirrors and for the same reason — a cell outlives this window through `CellPanel._cells`:

```python
            self._releaseCellPositionConnections()
```

Also call `_syncCellPositions()` from the `sigCellsDiscarded` path so a discarded cell is disconnected: it already runs through `_onCellStateChanged` if Task 6 emitted `sigCellStateChanged` from `_onCellsDiscarded`. Verify that ordering — the emit must come *after* the rows are removed, or `cells()` still reports the discarded cell and it stays connected.

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py acq4/modules/Autopatch/tests/test_teardown.py -v
```

Expected: all pass.

- [ ] **Step 5: Mutation proof**

Remove the `self._releaseCellPositionConnections()` call from `teardown`. Expected: `test_teardown_disconnects_every_cell_position_connection` FAILS on the post-teardown assert. Record the line. Restore.

Now re-run Task 9's incomplete mutation: change `getattr(cell, "initialPosition", None)` to `cell.position` in `_syncCellPositions`. Expected: `test_refresh_never_iterates_the_tracked_positions_dict` FAILS with the `RuntimeError`. Record the line — this is what makes Task 9's line proven. Restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_window_integration.py acq4/modules/Autopatch/tests/test_teardown.py
git commit -m "feat: follow tracked cells in Area 1 and sever the connections on teardown"
```

---

## Task 11: Navigation both ways

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` — wire the click; `acq4/modules/Autopatch/cell_panel.py` — the Zoom-to-cell button beside the existing four (line 148-161)
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`, `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: `ProgressOverlay.sigMarkerClicked` (Task 2), `CellPanel.selectCell` (Task 7), `RegionPanel.setViewport` (already built, `region_panel.py:346`), `_cellPositions` (Task 9).
- Produces: `CellPanel.zoomToCellBtn`, `CellPanel.sigZoomToCellRequested = Qt.Signal(object)`; `AutopatchWindow._onMarkerClicked(cellId)`, `_onZoomToCell(cell)`.

- [ ] **Step 1: Write the failing tests**

In `test_cell_panel.py`:

```python
def test_zoom_button_requests_the_selected_cell(qapp):
    panel = makePanel()
    cell = object()
    panel.addCell(cell)
    panel.selectCell(cell)
    seen = []
    panel.sigZoomToCellRequested.connect(seen.append)

    panel.zoomToCellBtn.click()

    assert seen == [cell]


def test_zoom_button_does_nothing_with_no_selection(qapp):
    panel = makePanel()
    seen = []
    panel.sigZoomToCellRequested.connect(seen.append)

    panel.zoomToCellBtn.click()

    assert seen == []
```

In `test_window_integration.py`:

```python
def test_clicking_a_marker_selects_that_cell_in_area_5(qapp, win):
    first = _makeCellAt(1.0e-3, 2.0e-3, -30e-6)
    second = _makeCellAt(1.4e-3, 2.1e-3, -30e-6)
    win.cellPanel.addCell(first)
    win.cellPanel.addCell(second)

    win._progressOverlay.sigMarkerClicked.emit(id(second))

    assert win.cellPanel.cellList.currentItem().data(Qt.Qt.UserRole) is second


def test_a_stale_marker_click_is_ignored(qapp, win):
    """A rescan can discard a cell between the draw and the click.

    Seeds and selects a real cell first: asserting `currentItem() is None` on an
    empty list would be trivially true and would pass for an implementation that
    cleared the selection, or one that raised and was swallowed. The invariant is
    that a stale id neither raises nor moves the operator off the row they chose.
    """
    known = _makeCellAt(1.0e-3, 2.0e-3)
    win.cellPanel.addCell(known)
    win.cellPanel.selectCell(known)

    win._progressOverlay.sigMarkerClicked.emit(123456)

    assert win.cellPanel.cellList.currentItem().data(Qt.Qt.UserRole) is known


def test_zoom_to_cell_frames_area_1_on_it(qapp, win):
    _sliceWithTodoTiles(win)
    cell = _makeCellAt(1.4e-3, 2.1e-3, -30e-6)
    win.cellPanel.addCell(cell)
    win.cellPanel.selectCell(cell)

    win.cellPanel.zoomToCellBtn.click()

    xRange, yRange = win.regionPanel.view.viewRange()
    assert sum(xRange) / 2 == pytest.approx(1.4e-3, rel=1e-6)
    assert sum(yRange) / 2 == pytest.approx(2.1e-3, rel=1e-6)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py acq4/modules/Autopatch/tests/test_window_integration.py -v -k "zoom or marker_click or stale_marker"
```

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'zoomToCellBtn'`.

- [ ] **Step 3: Write minimal implementation**

In `cell_panel.py`, add the signal beside the others:

```python
    # Carries the selected cell, for Area 1 to frame its view on. The panel
    # knows nothing about views or spans; the window owns that.
    sigZoomToCellRequested = Qt.Signal(object)
```

Add the button beside the existing four and into `btnRow`:

```python
        self.zoomToCellBtn = Qt.QPushButton("Zoom to cell")
        self.zoomToCellBtn.setToolTip(
            "Frame Area 1's view on the selected cell's position."
        )
        self.zoomToCellBtn.clicked.connect(self._onZoomToCellClicked)
```

```python
        btnRow.addWidget(self.zoomToCellBtn)
```

And the handler:

```python
    def _onZoomToCellClicked(self) -> None:
        item = self.cellList.currentItem()
        if item is None:
            return
        cell = item.data(Qt.Qt.UserRole)
        if cell is None:
            return
        self.sigZoomToCellRequested.emit(cell)
```

In `Autopatch.py`, wire both directions beside the other connections:

```python
        self._progressOverlay.sigMarkerClicked.connect(self._onMarkerClicked)
        self.cellPanel.sigZoomToCellRequested.connect(self._onZoomToCell)
```

And the handlers, beside `_refreshProgress`:

```python
    def _onMarkerClicked(self, cellId) -> None:
        """Select the clicked marker's cell in Area 5.

        Resolves the id through the cell panel rather than holding cells here:
        a marker drawn before a rescan can be clicked after it, and the panel
        is the only thing that knows whether that cell still has a row.
        """
        if self._tornDown:
            return
        for cell in self.cellPanel.cells():
            if id(cell) == cellId:
                self.cellPanel.selectCell(cell)
                return

    def _onZoomToCell(self, cell) -> None:
        """Frame Area 1 on `cell`, across the same 3x3 fields "Add region
        here" seeds, so the two controls agree on what "around here" means."""
        if self._tornDown:
            return
        position = self._cellPositions.get(id(cell))
        if position is None or self.slice is None:
            return
        fovW, fovH = self.slice.fov
        self.regionPanel.setViewport(position, (3 * fovW, 3 * fovH))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v
```

Expected: all pass.

- [ ] **Step 5: Mutation proof**

Remove the `if item is None: return` guard from `_onZoomToCellClicked`. Expected: `test_zoom_button_does_nothing_with_no_selection` FAILS. Record the line. Restore.

Then change `_onMarkerClicked`'s loop to call `selectCell` unconditionally on the first cell. Expected: `test_clicking_a_marker_selects_that_cell_in_area_5` FAILS (it selects `first`, not `second`). Record and restore.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/
git commit -m "feat: navigate between Area 1's markers and Area 5's cell list"
```

---

## Task 12: Full-suite verification and the PR

**Files:** none changed.

- [ ] **Step 1: Run the Autopatch and experiment suites**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ acq4/experiment/ -q
```

Expected: all pass, output pristine.

- [ ] **Step 2: Run the whole repo suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest -q
```

Expected: no new failures against the branch point. Record both counts. Known pre-existing and **not** to be fixed here: `acq4/devices/Stage/tests/test_mockstage_move.py` aborts the process intermittently when run alone (documented in PR #578's "Not done").

- [ ] **Step 3: Confirm the branch carries only this work**

```bash
git log --oneline 97c818883..HEAD
```

Expected: the spec commit plus Tasks 2-11. If a commit from another session appears, stop — the shared checkout leaked again, and the fix is a fresh branch off the last good commit, never a force-move.

- [ ] **Step 4: Open the PR**

Body must state plainly:
- The §6 `Cell` resolution and why the premise did not hold.
- That the acq4-automation `Cell.score` PR must merge first.
- **That the live GUI smoke test has not been run** — markers over real tissue, colour legibility at slice scale, and both navigation directions need a human at a screen.
- The mutation-proof findings, including Task 9's mutation that only failed once Task 10's concurrency test existed.

---

## Self-Review

**Spec coverage:** §4.1 `ProgressOverlay` → Task 2. §4.2 colour sources → Tasks 3-5. §4.3 coverage → Tasks 2, 9. §5.1 `Cell.score` → Task 1. §5.2 `CellPanel` surface → Tasks 6, 7. §6 refresh/threading → Tasks 9, 10. §6.2 lifetime → Task 10. §7 navigation → Task 11. §8 framing → verified by Task 9's coverage test and unchanged `fitToRegions` behaviour. §9 degenerate input → Tasks 3-5 (no slice, unscored, clamped), Task 7 (stale cell), Task 11 (stale click). §10 testing → distributed, with the mutation discipline in Global Constraints. §11's open items are out of scope by the spec's own statement.

**Type consistency:** `Marker(x, y, brush, cellId)` is constructed in Task 9 exactly as defined in Task 2. `ColorContext`'s nine fields are defined in Task 3 and populated in Task 9's `_colorContext()`; `fov`, `tileVolume`, `maxCellDensity`, `minHealth` are the only nullable ones, and every source handles them. `brushesFor(key, ctx)` and `legendFor(key, ctx)` share one signature. `colorSource()` returns the same key strings `COLOR_SOURCES` carries.

**One gap this review found and fixed:** Task 9's `_colorContext` needs `Slice.fov`, which `Slice` does not expose — it holds `self._fov`. Task 9 Step 3 now adds that property. Task 5's `_neighbourCount` and Task 11's `_onZoomToCell` both depend on it.
