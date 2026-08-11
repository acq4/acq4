# Autopatch Area 1 Region Graphics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Autopatch module an Area 1 view where the operator sees the Camera module's pinned frames, seeds and edits search regions over them in three shapes, and optionally mirrors those regions into the Camera window.

**Take pyqtgraph's tools as they come.** Region creation follows the pattern acq4's own Camera module already uses (`ROIPlotter._addRectROI`/`_addEllipseROI`/`_addPolygonROI`, `CameraWindow.py:509`): a shape control seeds an ROI at a known size and position, and the operator drags, resizes, and reshapes it with pyqtgraph's stock handles. `pg.PolyLineROI` already inserts a vertex where an edge is clicked (`segmentClicked`) and removes handles individually, so outlining a cortical layer needs no code of ours. pyqtgraph offers no drag-out-a-new-ROI gesture and neither does acq4; do not build one. The single deliberate departure is documented in Task 2.

**Architecture:** A new `RegionPanel` owns a `pg.GraphicsView`/`pg.ViewBox` in global metres and renders a list of `SearchRegion` objects as pyqtgraph ROIs, emitting the whole list back on any edit. `AutopatchWindow` is the only thing that knows about both the panel and the `Slice`, and pushes edits into `Slice.setRegions()` — a wholesale list swap, because the cell producer reads regions on the worker thread. Two one-way mirrors (Camera pinned frames in, region outlines out) are display-only objects with no state of their own.

**Tech Stack:** Python 3.12, PyQt via `acq4.util.Qt`, pyqtgraph, pytest.

> **Which pyqtgraph runs:** the `acq4-gl` environment imports pyqtgraph from `site-packages`, *not* from the checkout at `/home/martin/src/acq4/pyqtgraph`. Read the checkout for source if you like, but verify behaviour against the interpreter.

**Spec:** `docs/superpowers/specs/2026-08-10-autopatch-area1-region-graphics-design.md`

## Global Constraints

- Python interpreter is `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Never `acq4-torch`.
- Branch is `claude/autopatch-ui-next-ecbf00`, based on `_reviewed` @ `00c75e269`. Before **every** `git commit`, verify `git rev-parse --show-toplevel` ends in `.claude/worktrees/happy-easley-8b68a0` and `git branch --show-current` is `claude/autopatch-ui-next-ecbf00`. Committing into the main checkout on `_staging` has happened repeatedly and destroys the work.
- Every commit uses the project footer. Use the heredoc form given in each Commit step — a single-line `git commit -m` silently drops the footer, which is how 18 commits on an earlier branch ended up without it.
- Commit author: `--author="Martin Chase (claude) <outofculture@gmail.com>"`.
- Test output must be pristine. No `pytest.ini` ignores, no skips, no warnings introduced.
- All coordinates are global metres. Never pixels, never stage-native units.
- Every geometry fixture must be **asymmetric** — distinct width and height. A square fixture cannot test an axis mapping, which is how a swapped `rx`/`ry` survived 324 tests in P2c-1.
- Comments describe the code as it is. No references to "new", "improved", or what changed.

## File Structure

**Created:**

| path | responsibility |
|---|---|
| `acq4/modules/Autopatch/region_panel.py` | `RegionPanel` widget and the shape↔ROI adapters. |
| `acq4/modules/Autopatch/region_mirrors.py` | `PinnedFrameMirror` (Camera→Autopatch) and `CameraMirror` (Autopatch→Camera). Display only, no region state. |
| `acq4/modules/Autopatch/tests/test_region_adapters.py` | Shape↔ROI round-trips. |
| `acq4/modules/Autopatch/tests/test_region_panel.py` | Panel rendering, edit signals, gating. |
| `acq4/modules/Autopatch/tests/test_region_mirrors.py` | Both mirrors, including teardown. |

**Modified:**

| path | change |
|---|---|
| `acq4/experiment/slice.py` | `setRegions()`; `addRegion` reimplemented on it; readers snapshot. |
| `acq4/util/imaging/imaging_ctrl.py` | Additive `sigPinnedFramesChanged`. |
| `acq4/modules/Autopatch/search_panel.py` | Loses `shapeCombo`, `addRegionBtn`, `sigAddRegionRequested`, `regionShape()`. |
| `acq4/modules/Autopatch/status_panel.py` | `setInstruction()` / `clearInstruction()`. |
| `acq4/modules/Autopatch/Autopatch.py` | Mounts `RegionPanel` in Area 1, splitter layout, wiring, teardown. |
| `acq4/experiment/tests/test_slice.py`, `acq4/modules/Autopatch/tests/test_search_panel.py`, `.../test_status_panel.py`, `.../test_window_integration.py` | Follow the changes above. |

---

### Task 1: `Slice.setRegions()` — the atomic swap

**Files:**
- Modify: `acq4/experiment/slice.py` (`addRegion` at ~line 115, `tileGrid` at ~line 138, `forceRescan` at ~line 220)
- Test: `acq4/experiment/tests/test_slice.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Slice.setRegions(regions: Iterable[SearchRegion]) -> None`. `Slice.addRegion(region)` keeps its existing signature and behaviour.

**Why:** `CellProducer` reaches `slice.nextTile()` → `tileGrid()` on the worker thread while the operator edits regions on the GUI thread, and `tileGrid()` iterates `self._regions` directly. Rebinding the attribute means an in-progress loop keeps iterating the list it started on; mutating it in place means the loop silently skips regions.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_slice.py`:

```python
class _EditsTheSliceMidScan(SearchRegion):
    """A region that replaces its slice's region list from inside the tiler's
    own iteration -- what a GUI-thread setRegions() landing in the middle of a
    worker-thread tileGrid() does.

    Deterministic on purpose: driving this with real threads would reproduce the
    hazard only sometimes, and a test that fails one run in fifty is not a test.
    """

    def __init__(self, slice_, replacement):
        self._slice = slice_
        self._replacement = replacement
        self.calls = 0

    def bounds(self):
        return (0.0, 0.0, 400e-6, 200e-6)

    def overlapsTile(self, center, fov):
        self.calls += 1
        if self.calls == 1:
            self._slice.setRegions(self._replacement)
        return True


def test_an_edit_during_tilegrid_does_not_drop_the_regions_behind_it():
    # The whole point of the swap. With the list mutated in place instead, the
    # for-loop's index walks off the end of a shortened list and every region
    # after the one being scanned is silently dropped from the survey.
    sl = Slice(fov=(100e-6, 50e-6))
    later = RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)
    mutator = _EditsTheSliceMidScan(sl, [])
    sl.setRegions([mutator, later])

    grid = sl.tileGrid()

    laterTiles = [c for c in grid if c[0] > 0.5e-3]
    assert laterTiles, "the region after the edited one was dropped mid-scan"


def test_the_edit_itself_takes_effect_on_the_next_call():
    # The swap must not be a no-op in the other direction: the point of editing
    # regions is that the next tile the producer asks for reflects the edit.
    sl = Slice(fov=(100e-6, 50e-6))
    mutator = _EditsTheSliceMidScan(sl, [])
    sl.setRegions([mutator, RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3)])
    sl.tileGrid()

    assert sl.regions == []
    assert sl.tileGrid() == []


def test_setregions_copies_so_the_callers_list_is_not_live():
    # The panel hands over a list it goes on mutating as the operator draws.
    sl = Slice(fov=(100e-6, 50e-6))
    handed = [RectRegion(0.0, 0.0, 400e-6, 200e-6)]
    sl.setRegions(handed)
    handed.append(RectRegion(1e-3, 1e-3, 1.4e-3, 1.2e-3))

    assert len(sl.regions) == 1


def test_deleting_a_region_leaves_coverage_alone():
    # Coverage records ground already imaged, not ground still wanted. Pruning
    # it when a region goes away would make a region redrawn over surveyed
    # tissue re-image it, and coverage is shared by every producer this slice
    # makes -- it is not a per-region tally.
    sl = Slice(fov=(100e-6, 50e-6))
    sl.setRegions([RectRegion(0.0, 0.0, 400e-6, 200e-6)])
    covered = sl.tileGrid()[0]
    sl.markCovered(covered)

    sl.setRegions([])

    assert sl.tileGrid() == []
    sl.setRegions([RectRegion(0.0, 0.0, 400e-6, 200e-6)])
    assert sl.nextTile() != covered
```

Add `SearchRegion` to the existing `search_region` import at the top of the file if it is not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -k "does_not_drop or takes_effect or copies_so or leaves_coverage" -v`

Expected: FAIL — `AttributeError: 'Slice' object has no attribute 'setRegions'`.

- [ ] **Step 3: Write minimal implementation**

In `acq4/experiment/slice.py`, replace `addRegion` with:

```python
    def setRegions(self, regions) -> None:
        """Replace the regions to survey, in one step. Coverage is untouched.

        Rebinding the attribute rather than mutating the list is what makes this
        safe to call from the GUI thread while a producer is reading regions on
        the worker thread: `tileGrid()` binds its loop to whichever list object
        was current when it started, so a reader sees either the whole old set
        or the whole new one and never a list changing under its own iteration.
        The same "make it one step" discipline `Orchestrator._refillQueue`
        applies to the producer reference.
        """
        self._regions = list(regions)

    def addRegion(self, region: SearchRegion) -> None:
        """Add a shape to survey, in global coordinates. Coverage is untouched.

        Takes a SearchRegion rather than four floats because tissue is not
        rectangular: a slice with a damaged corner, or one cortical layer worth
        searching, is the ordinary reason to outline a region at all. A rectangle
        is `RectRegion(x0, y0, x1, y1)`.
        """
        self.setRegions(self._regions + [region])
```

In `tileGrid()`, bind the list once before the loop:

```python
        grid: list[tuple[float, float]] = []
        fov_w, fov_h = self._fov
        # Bound once: setRegions() can land from the GUI thread while this runs.
        regions = self._regions
        for region in regions:
```

In `forceRescan()`, do the same:

```python
        regions = self._regions
        here = [r for r in regions if r.overlapsTile(xy, self._fov)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/ -q`

Expected: PASS, no failures, no new warnings.

- [ ] **Step 5: Prove the test can fail (mutation)**

Temporarily change `setRegions` to mutate in place:

```python
        self._regions[:] = list(regions)
```

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -k does_not_drop -v`

(`-k mid_scan` selects nothing: "mid_scan" appears only in the helper class name, not in any test function's name.)

Expected: FAIL at the `assert laterTiles` line. **Record the file and line number of the failure in your report** — a mutation that fails at a different line has proven something else. Then revert the mutation and re-run to confirm green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/experiment/slice.py acq4/experiment/tests/test_slice.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: replace a slice's regions in one step

Rebinding the list rather than mutating it lets the GUI thread edit regions
while a producer iterates them on the worker thread.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 2: Shape ↔ ROI adapters

**Files:**
- Create: `acq4/modules/Autopatch/region_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_region_adapters.py`

**Interfaces:**
- Consumes: `acq4.experiment.search_region.{SearchRegion, RectRegion, EllipseRegion, PolygonRegion}`.
- Produces:
  - `roiForRegion(region: SearchRegion) -> pg.ROI`
  - `regionForRoi(roi: pg.ROI) -> SearchRegion | None` — `None` when the ROI has been dragged into a shape that is not a region
  - `REGION_PEN` — the pen every region ROI draws with.
  - `_AxisAlignedEllipseROI(pg.EllipseROI)`

**Why the ellipse subclass — the one place a stock tool is inadequate.** `pg.EllipseROI._addHandles` adds a **rotate** handle. `EllipseRegion` is an ellipse inscribed in an axis-aligned box, so a rotated ROI maps back to a region with the rotation silently dropped: the operator outlines one patch of tissue and the survey tiles another. `ROIPlotter._addEllipseROI` uses the stock class quite correctly, because it only reads the pixels under the ROI and a rotation changes which pixels those are. Here the ROI has to survive a round trip through a shape that cannot express rotation, so the handle has to go. Everything else — `pg.RectROI`, `pg.PolyLineROI`, their handles, their `removable=True` context menu, the `ViewBox`'s pan and zoom — is used exactly as shipped.

- [ ] **Step 1: Write the failing test**

Create `acq4/modules/Autopatch/tests/test_region_adapters.py`:

```python
"""Tests for the mapping between a Slice's SearchRegion shapes and the
pyqtgraph ROIs Area 1 draws them with."""

import pytest

from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


# Deliberately asymmetric, at real SI magnitudes: a square fixture cannot test
# an axis mapping, which is exactly how a swapped rx/ry survived every ellipse
# test in P2c-1.
RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
ELLIPSE = EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
TRIANGLE = PolygonRegion(((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3)))


@pytest.mark.parametrize("region", [RECT, ELLIPSE, TRIANGLE])
def test_a_region_round_trips_through_its_roi(qapp, region):
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    assert regionForRoi(roiForRegion(region)) == region


@pytest.mark.parametrize("region", [RECT, ELLIPSE, TRIANGLE])
def test_the_roi_lands_on_the_regions_own_bounds(qapp, region):
    # Round-tripping equal objects would still pass if both directions shared
    # the same wrong convention (origin vs centre, say). Checking the ROI's own
    # geometry against the region's bounds is what pins the convention.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    roi = roiForRegion(region)
    x0, y0, x1, y1 = region.bounds()
    rect = roi.boundingRect()
    pos = roi.pos()
    assert pos.x() + rect.x() == pytest.approx(x0)
    assert pos.y() + rect.y() == pytest.approx(y0)
    assert rect.width() == pytest.approx(x1 - x0)
    assert rect.height() == pytest.approx(y1 - y0)


def test_a_rect_and_an_ellipse_map_to_different_roi_types(qapp):
    import pyqtgraph as pg

    from acq4.modules.Autopatch.region_panel import roiForRegion

    assert isinstance(roiForRegion(ELLIPSE), pg.EllipseROI)
    assert not isinstance(roiForRegion(RECT), pg.EllipseROI)


def test_an_ellipse_roi_cannot_be_rotated(qapp):
    # EllipseRegion is inscribed in an axis-aligned box, so a rotate handle
    # would let the operator draw a shape that has no region to map back to:
    # regionForRoi reads pos and size and would drop the rotation silently.
    from acq4.modules.Autopatch.region_panel import roiForRegion

    handles = roiForRegion(ELLIPSE).handles
    assert not any(h["type"] == "r" for h in handles)


def test_a_roi_dragged_past_its_own_origin_still_makes_a_region(qapp):
    # An ROI resized past its origin reports a negative size; the region built
    # from it must still describe the box the operator sees on screen.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(RECT)
    roi.setPos((1.4e-3, 2.1e-3))
    roi.setSize((-0.4e-3, -0.1e-3))

    assert regionForRoi(roi) == RECT


@pytest.mark.parametrize("size", [(0.0, 0.1e-3), (0.4e-3, 0.0), (0.0, 0.0)])
def test_an_roi_squashed_flat_reports_no_region(qapp, size):
    # A pg.RectROI can be dragged to zero extent, and SearchRegion raises on
    # that. Raising here would surface as a traceback on the GUI thread from
    # inside a signal handler, mid-drag. One case per axis: a check that only
    # looks at width passes a test that only squashes height.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(RECT)
    roi.setSize(size)

    assert regionForRoi(roi) is None


@pytest.mark.parametrize(
    "points",
    [
        # Three vertices on a line: a bounding box with no extent in one axis.
        [[1.0e-3, 2.0e-3], [1.2e-3, 2.0e-3], [1.4e-3, 2.0e-3]],
        # Two vertices left after the operator removes handles from a triangle.
        [[1.0e-3, 2.0e-3], [1.4e-3, 2.02e-3]],
    ],
)
def test_a_polygon_with_no_area_reports_no_region(qapp, points):
    # The polygon equivalents of a squashed box. Built by construction rather
    # than by calling roi.setPoints() on a triangle: setPoints() reaches
    # clearPoints() -> removeHandle() -> removeSegment(), which calls
    # self.scene().removeItem() and raises AttributeError on an ROI that is not
    # in a scene. Constructing is the path with no such requirement.
    import pyqtgraph as pg

    from acq4.modules.Autopatch.region_panel import regionForRoi

    roi = pg.PolyLineROI(points, closed=True)

    assert regionForRoi(roi) is None


def test_a_moved_polygon_reports_its_vertices_in_global_coordinates(qapp):
    # A PolyLineROI holds its vertices in ROI-local coordinates, so dragging the
    # body moves the shape without touching them. Reading them raw would put the
    # region back where it started and survey the wrong tissue.
    from acq4.modules.Autopatch.region_panel import regionForRoi, roiForRegion

    roi = roiForRegion(TRIANGLE)
    roi.setPos((0.5e-3, 0.25e-3))

    moved = regionForRoi(roi)
    assert moved.vertices == tuple(
        (x + 0.5e-3, y + 0.25e-3) for x, y in TRIANGLE.vertices
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_adapters.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.region_panel'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/modules/Autopatch/region_panel.py`:

```python
"""RegionPanel: Area 1's global-coordinate view of the slice -- the pinned
imagery to draw over, and the search regions drawn on it as editable ROIs."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.experiment.search_region import (
    EllipseRegion,
    PolygonRegion,
    RectRegion,
    SearchRegion,
)

# Yellow at 2px, matching the survey ROI the AutomationDebug bench already
# draws, so the same shape reads the same way in either module.
REGION_PEN = pg.mkPen("y", width=2)


class _AxisAlignedEllipseROI(pg.EllipseROI):
    """A pg.EllipseROI with no rotate handle.

    EllipseRegion is the ellipse inscribed in an axis-aligned bounding box, so
    there is no region for a rotated ROI to map back to: regionForRoi reads the
    ROI's position and size, and a rotation would be dropped without trace --
    the operator would draw one shape and the survey would tile another.
    """

    def _addHandles(self):
        self.addScaleHandle([1.0, 0.5], [0.5, 0.5])
        self.addScaleHandle([0.5, 1.0], [0.5, 0.5])


def roiForRegion(region: SearchRegion) -> pg.ROI:
    """The editable ROI that draws `region`."""
    if isinstance(region, PolygonRegion):
        return pg.PolyLineROI(
            [list(v) for v in region.vertices],
            closed=True,
            pen=REGION_PEN,
            removable=True,
        )
    x0, y0, x1, y1 = region.bounds()
    roiClass = _AxisAlignedEllipseROI if isinstance(region, EllipseRegion) else pg.RectROI
    return roiClass(
        (x0, y0), (x1 - x0, y1 - y0), pen=REGION_PEN, removable=True
    )


def regionForRoi(roi: pg.ROI) -> SearchRegion | None:
    """The region `roi` currently describes, or None if it does not describe one.

    An ROI can be dragged flat, and its handles can be dragged collinear;
    SearchRegion rejects both, since a region with no extent has no tiles. This
    is reached from a Qt signal while the operator is mid-drag, so it reports
    the failure by returning None rather than by raising a traceback out of a
    slot -- the same choice `SearchPanel.constraints()` makes, and for the same
    reason.

    Corner normalization is left to `_BoxRegion.__post_init__`, which already
    orders its corners -- an ROI resized past its own origin reports a negative
    size, and both paths through that hazard should agree by construction rather
    than by two implementations happening to match.
    """
    try:
        if isinstance(roi, pg.PolyLineROI):
            vertices = []
            for _, localPos in roi.getLocalHandlePositions():
                globalPos = roi.mapToParent(localPos)
                vertices.append((globalPos.x(), globalPos.y()))
            return PolygonRegion(tuple(vertices))
        pos = roi.pos()
        size = roi.size()
        x0, y0 = pos.x(), pos.y()
        regionClass = EllipseRegion if isinstance(roi, pg.EllipseROI) else RectRegion
        return regionClass(x0, y0, x0 + size.x(), y0 + size.y())
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_adapters.py -v`

Expected: PASS, all 10 cases.

- [ ] **Step 5: Prove the asymmetry tests bite (mutation)**

Temporarily swap the width and height in `roiForRegion`'s box branch:

```python
    return roiClass((x0, y0), (y1 - y0, x1 - x0), pen=REGION_PEN, removable=True)
```

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_adapters.py -v`

Expected: FAIL in `test_a_region_round_trips_through_its_roi` and `test_the_roi_lands_on_the_regions_own_bounds`. **Record the failing line numbers.** Revert and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/region_panel.py acq4/modules/Autopatch/tests/test_region_adapters.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: map search regions to editable ROIs and back

Rectangles, ellipses, and polygons round-trip through pyqtgraph ROIs. The
ellipse drops its rotate handle, having no rotated region to map back to.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 3: `RegionPanel` — the view and the region list

**Files:**
- Modify: `acq4/modules/Autopatch/region_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_region_panel.py`

**Interfaces:**
- Consumes: `roiForRegion`, `regionForRoi`, `REGION_PEN` from Task 2.
- Produces:
  - `RegionPanel(Qt.QWidget)` with `sigRegionsChanged(object)` (a `list[SearchRegion]`) and `sigAddRegionRequested()`
  - `RegionPanel.setRegions(regions)` — render, **without** re-emitting
  - `RegionPanel.regions() -> list[SearchRegion]`
  - `RegionPanel.regionShape() -> str` — `"rect"` / `"ellipse"` / `"polygon"`
  - `RegionPanel.fitToRegions() -> None`
  - Widgets: `graphicsView`, `view` (the `ViewBox`), `shapeCombo`, `addRegionBtn`, `mirrorCheck`, `fitBtn`

**Note on the no-echo rule:** `setRegions()` is how the window pushes the slice's state *into* the panel. If it re-emitted `sigRegionsChanged`, the window would write straight back into the slice on every refresh — and a New slice that cleared the panel would immediately be told the regions are empty by the panel it just cleared. The panel emits only for edits that originate in it.

- [ ] **Step 1: Write the failing test**

Create `acq4/modules/Autopatch/tests/test_region_panel.py`:

```python
"""Tests for Area 1's region view: what it draws, what it reports back when the
operator edits a region, and what it lets them touch."""

import pytest

from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
OTHER = RectRegion(3.0e-3, 1.0e-3, 3.6e-3, 1.2e-3)
ELLIPSE = EllipseRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)


def makePanel():
    from acq4.modules.Autopatch.region_panel import RegionPanel

    return RegionPanel()


def test_a_fresh_panel_holds_no_regions(qapp):
    assert makePanel().regions() == []


def test_setregions_draws_one_roi_per_region(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    assert len(panel._rois) == 2
    assert panel.regions() == [RECT, OTHER]


def test_setregions_replaces_rather_than_appends(qapp):
    # The window pushes the slice's whole region list on every refresh, so a
    # panel that appended would redraw the same region once per refresh.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    panel.setRegions([ELLIPSE])

    assert len(panel._rois) == 1
    assert panel.regions() == [ELLIPSE]


def test_setregions_does_not_echo_back(qapp):
    # setRegions is how the slice's state reaches the panel. Echoing it would
    # write straight back into the slice, and a New slice that cleared the panel
    # would be told by that panel that its regions are empty.
    panel = makePanel()
    seen = []
    panel.sigRegionsChanged.connect(seen.append)
    panel.setRegions([RECT])

    assert seen == []


def test_dragging_a_region_reports_the_whole_list(qapp):
    # The window replaces the slice's regions wholesale, so an edit to one has
    # to arrive with its neighbours intact rather than on its own.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    seen = []
    panel.sigRegionsChanged.connect(seen.append)

    roi = panel._rois[0]
    # finish=False: setPos's own default (finish=True) already emits
    # sigRegionChangeFinished, which is what a real drag never does mid-gesture
    # (pg.MouseDragHandler always moves with finish=False and fires the signal
    # exactly once, from _moveFinished, on release) -- so the explicit emit
    # below is what stands in for that release.
    roi.setPos((2.0e-3, 5.0e-3), finish=False)
    roi.sigRegionChangeFinished.emit(roi)

    assert len(seen) == 1
    moved, untouched = seen[0]
    # approx, not ==: the ROI's corners survive a subtract-then-re-add at SI
    # magnitudes, so 1.0e-3 + 1.4e-3 - 1.0e-3 is not bit-identical to 1.4e-3.
    assert moved.bounds() == pytest.approx((2.0e-3, 5.0e-3, 2.4e-3, 5.1e-3))
    assert untouched == OTHER


def test_removing_a_region_reports_the_list_without_it(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])
    seen = []
    panel.sigRegionsChanged.connect(seen.append)

    panel._rois[0].sigRemoveRequested.emit(panel._rois[0])

    assert seen == [[OTHER]]
    assert panel.regions() == [OTHER]


def test_a_removed_roi_leaves_the_view(qapp):
    # Dropping it from the list but leaving the item in the scene would keep a
    # deleted region on screen, and keep it alive.
    panel = makePanel()
    panel.setRegions([RECT])
    roi = panel._rois[0]

    roi.sigRemoveRequested.emit(roi)

    assert roi.scene() is None


def test_adding_a_polygon_vertex_reaches_the_reported_region(qapp):
    # Reshaping a polygon is pyqtgraph's own segmentClicked inserting a handle
    # where an edge was clicked -- the mechanism that makes outlining a cortical
    # layer possible without any drawing code of ours. Pinned here because the
    # panel depends on it: a handle added this way has to arrive in the region
    # the panel reports, in global coordinates.
    #
    # segments[0] is the *closing* edge (last vertex back to first), not the
    # first one, so the new vertex lands between the triangle's third and first
    # points. Membership rather than a position is asserted for that reason --
    # pyqtgraph's ordering is its own business as long as handle order,
    # getState()['points'], and shape() agree, which they do.
    triangle = PolygonRegion(
        ((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3))
    )
    panel = makePanel()
    panel.setRegions([triangle])
    roi = panel._rois[0]

    roi.segmentClicked(roi.segments[0], pos=Qt.QPointF(1.2e-3, 2.01e-3))

    reported = panel.regions()[0]
    assert len(reported.vertices) == 4
    assert (1.2e-3, 2.01e-3) in [
        (pytest.approx(x), pytest.approx(y)) for x, y in reported.vertices
    ]


def test_an_roi_squashed_flat_stays_on_screen_but_is_not_reported(qapp):
    # Removing it would delete the operator's work mid-drag; reporting it would
    # hand the slice a region with no tiles. It stays visible and uncounted.
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    panel._rois[0].setSize((0.0, 0.1e-3))

    assert len(panel._rois) == 2
    assert panel.regions() == [OTHER]


def test_fit_to_regions_ignores_a_squashed_roi(qapp):
    # regions() drops it, so fitToRegions must read through regions() rather
    # than the ROI list, or it frames a bounding box it cannot compute.
    panel = makePanel()
    panel.setRegions([RECT])
    panel._rois[0].setSize((0.0, 0.0))
    before = panel.view.viewRange()

    panel.fitToRegions()

    assert panel.view.viewRange() == before


def test_the_shape_selector_offers_all_three_shapes(qapp):
    # PolygonRegion has been implemented and tested since P2c-1 with no control
    # able to produce one; a cortical layer is the reason regions became shapes.
    panel = makePanel()
    shapes = [panel.shapeCombo.itemData(i) for i in range(panel.shapeCombo.count())]

    assert shapes == ["rect", "ellipse", "polygon"]


def test_the_shape_selector_reports_item_data_not_its_label(qapp):
    panel = makePanel()
    panel.shapeCombo.setCurrentIndex(panel.shapeCombo.findData("polygon"))

    assert panel.regionShape() == "polygon"


def test_the_add_region_button_asks_its_owner(qapp):
    # The panel does not know where the camera is pointing; the window does.
    panel = makePanel()
    requests = []
    panel.sigAddRegionRequested.connect(lambda: requests.append(True))

    panel.addRegionBtn.click()

    assert requests == [True]


def test_fit_to_regions_frames_every_region(qapp):
    panel = makePanel()
    panel.setRegions([RECT, OTHER])

    panel.fitToRegions()

    (vx0, vx1), (vy0, vy1) = panel.view.viewRange()
    assert vx0 <= 1.0e-3 and vx1 >= 3.6e-3
    assert vy0 <= 1.0e-3 and vy1 >= 2.1e-3


def test_fit_to_regions_with_nothing_drawn_is_a_no_op(qapp):
    # The button is live before the operator has drawn anything, and autoranging
    # over an empty set is how a view ends up at an unrecoverable scale.
    panel = makePanel()
    before = panel.view.viewRange()

    panel.fitToRegions()

    assert panel.view.viewRange() == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -v`

Expected: FAIL — `ImportError: cannot import name 'RegionPanel'`.

- [ ] **Step 3: Write minimal implementation**

Append to `acq4/modules/Autopatch/region_panel.py`:

```python
class RegionPanel(Qt.QWidget):
    """Area 1's view of the slice: the imagery to draw over, and the search
    regions drawn on it as ROIs the operator can move, resize, and delete.

    Renders a list of regions and reports a list of regions. It holds no Slice
    and never touches one -- the window is what binds the two -- which is what
    lets it be built and tested with no slice, no camera, and no orchestrator,
    and what would let region drawing move into the Camera window later without
    any of this changing.
    """

    # The complete region list after an edit that originated here.
    sigRegionsChanged = Qt.Signal(object)
    sigAddRegionRequested = Qt.Signal()

    def __init__(self):
        super().__init__()
        self._rois: list[pg.ROI] = []

        self.graphicsView = pg.GraphicsView()
        self.graphicsView.setObjectName("Autopatch_regionView")
        self.view = pg.ViewBox()
        self.view.enableAutoRange(x=False, y=False)
        # Tissue is not distorted by the widget's aspect ratio, and a region
        # drawn over a squashed view would not be the region surveyed.
        self.view.setAspectLocked(True)
        self.graphicsView.setCentralItem(self.view)
        # The view is the panel's content, not a strip above its controls: a
        # region spans a slice, and the operator resizes the window to draw.
        self.graphicsView.setSizePolicy(
            Qt.QSizePolicy.Expanding, Qt.QSizePolicy.Expanding
        )
        self.graphicsView.setMinimumSize(300, 300)

        # Item data, not display text, is what regionShape() returns: the window
        # maps it to a region class, and a label is a label.
        self.shapeCombo = Qt.QComboBox()
        for label, key in (
            ("Rectangle", "rect"),
            ("Ellipse", "ellipse"),
            ("Polygon", "polygon"),
        ):
            self.shapeCombo.addItem(label, key)
        self.shapeCombo.setToolTip('The shape "Add region here" seeds.')

        self.addRegionBtn = Qt.QPushButton("Add region here")
        self.addRegionBtn.setToolTip(
            "Add a search region covering roughly 3x3 fields of view around the "
            "camera's current center."
        )
        self.fitBtn = Qt.QPushButton("Fit to regions")
        self.mirrorCheck = Qt.QCheckBox("Mirror to Camera")
        self.mirrorCheck.setToolTip(
            "Draw these regions in the Camera module's view as well. They stay "
            "editable only here."
        )

        controls = Qt.QHBoxLayout()
        controls.addWidget(self.shapeCombo)
        controls.addWidget(self.addRegionBtn)
        controls.addWidget(self.fitBtn)
        controls.addWidget(self.mirrorCheck)
        controls.addStretch()

        layout = Qt.QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self.graphicsView)
        self.setLayout(layout)

        self.addRegionBtn.clicked.connect(self.sigAddRegionRequested)
        self.fitBtn.clicked.connect(self.fitToRegions)

    # ---- regions ----
    def regions(self) -> list[SearchRegion]:
        """The regions currently drawn, in the order they were added.

        An ROI the operator has squashed flat describes no region, and is left
        out rather than reported or raised over: it stays on screen to be pulled
        back into shape, and contributes no tiles until it is.
        """
        return [r for r in (regionForRoi(roi) for roi in self._rois) if r is not None]

    def setRegions(self, regions) -> None:
        """Draw `regions`, replacing whatever is drawn now.

        Deliberately silent: this is how the slice's state reaches the panel, so
        echoing it back would have the window write it straight into the slice
        again, and a New slice that cleared this panel would be told by the
        panel it just cleared that the regions are empty.
        """
        for roi in list(self._rois):
            self._detachRoi(roi)
        for region in regions:
            self._attachRoi(roiForRegion(region))

    def _attachRoi(self, roi: pg.ROI) -> None:
        self._rois.append(roi)
        self.view.addItem(roi)
        roi.sigRegionChangeFinished.connect(self._onRoiEdited)
        roi.sigRemoveRequested.connect(self._onRoiRemoved)

    def _detachRoi(self, roi: pg.ROI) -> None:
        Qt.disconnect(roi.sigRegionChangeFinished, self._onRoiEdited)
        Qt.disconnect(roi.sigRemoveRequested, self._onRoiRemoved)
        self._rois.remove(roi)
        self.view.removeItem(roi)

    def _onRoiEdited(self, _roi) -> None:
        # On sigRegionChangeFinished, not sigRegionChanged: a drag in progress
        # is not a decision, and every emission costs the slice a full retile.
        self.sigRegionsChanged.emit(self.regions())

    def _onRoiRemoved(self, roi) -> None:
        self._detachRoi(roi)
        self.sigRegionsChanged.emit(self.regions())

    # ---- view ----
    def regionShape(self) -> str:
        """The shape key for the next region drawn: rect, ellipse, or polygon."""
        return self.shapeCombo.currentData()

    def fitToRegions(self) -> None:
        """Frame every drawn region.

        With nothing drawn this does nothing: autoranging over an empty set is
        how a view ends up at a scale the operator cannot recover from, and the
        button is live before anything has been drawn.
        """
        bounds = [region.bounds() for region in self.regions()]
        if not bounds:
            return
        x0 = min(b[0] for b in bounds)
        y0 = min(b[1] for b in bounds)
        x1 = max(b[2] for b in bounds)
        y1 = max(b[3] for b in bounds)
        self.view.setRange(
            xRange=(x0, x1), yRange=(y0, y1), padding=0.1
        )
```

Add `from acq4.util import Qt` to the imports at the top of the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -v`

Expected: PASS, all 13 cases.

- [ ] **Step 5: Prove the no-echo test bites (mutation)**

Temporarily add `self.sigRegionsChanged.emit(self.regions())` as the last line of `setRegions`.

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -k echo -v`

Expected: FAIL at `assert seen == []`. **Record the failing line number.** Revert and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/region_panel.py acq4/modules/Autopatch/tests/test_region_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: draw a slice's search regions in Area 1

RegionPanel renders a region list as editable ROIs in a global-coordinate
view and reports the whole list back on any edit made in it.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 4: The editing gate

**Files:**
- Modify: `acq4/modules/Autopatch/region_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_region_panel.py`

**Interfaces:**
- Consumes: `RegionPanel` from Task 3.
- Produces:
  - `RegionPanel.setInteractionLocked(locked: bool)`
  - `RegionPanel.setSliceReady(ready: bool)`
  - `RegionPanel.setRunStatus(status: str)`

**The rule:** editing is enabled when `sliceReady and (not runLocked or status == "paused")`.

**Why the status and not the click:** `Orchestrator._checkPause()` runs at the *top* of `_runLoopBody`, before `_shouldRefill()`. Clicking Pause during a survey does not stop the survey — the producer goes on imaging tiles for seconds to minutes, reading `slice._regions` throughout, and the loop parks only at the next iteration. But `sigStatus("paused")` is emitted from *inside* `_checkPause`, immediately before `_pauseEvent.wait()`, so while that status is current the worker is blocked there and cannot be inside `_refillQueue`. The status is a guarantee; the click is not.

The three locks are kept as three separate flags for the same reason `SearchPanel` keeps `_runLocked` and `_sliceReady` apart: no writer can see another's condition, so collapsing them into one boolean lets a run ending unlock a panel that still has no slice behind it.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_region_panel.py`:

```python
def test_a_panel_with_no_slice_cannot_be_drawn_on(qapp):
    # New slice is what makes Area 1 usable, and greyed-out controls are how the
    # operator is told so -- the same treatment Area 2 already gets.
    panel = makePanel()

    assert not panel.addRegionBtn.isEnabled()
    assert not panel.shapeCombo.isEnabled()


def test_a_slice_makes_the_controls_live(qapp):
    panel = makePanel()
    panel.setSliceReady(True)

    assert panel.addRegionBtn.isEnabled()
    assert panel.shapeCombo.isEnabled()


def test_a_running_run_locks_editing(qapp):
    # The regions parameterise a search already underway on the worker thread.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([RECT])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")

    assert not panel.addRegionBtn.isEnabled()
    assert not panel._rois[0].translatable
    assert not panel._rois[0].resizable
    assert not panel._rois[0].removable


def test_a_paused_run_unlocks_editing(qapp):
    # The other side of the same invariant. A one-sided test on a two-sided
    # invariant passes happily while the other side is broken -- which is how
    # CellPanel's flush regressed in both directions across P2b's reviews.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([RECT])
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRunStatus("paused")

    assert panel.addRegionBtn.isEnabled()
    assert panel._rois[0].translatable
    assert panel._rois[0].resizable
    assert panel._rois[0].removable


def test_surveying_locks_editing_even_though_pause_was_pressed(qapp):
    # "surveying" is what a run reports while the producer images tiles, and a
    # Pause pressed during one does not park the loop until that refill is done.
    # Unlocking on anything short of the emitted "paused" would let an edit land
    # while the producer is reading regions.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("surveying")

    assert not panel.addRegionBtn.isEnabled()


def test_resuming_from_paused_locks_editing_again(qapp):
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setRegions([RECT])
    panel.setInteractionLocked(True)
    panel.setRunStatus("paused")
    panel.setRunStatus("running")

    assert not panel.addRegionBtn.isEnabled()
    assert not panel._rois[0].translatable


def test_regions_drawn_while_locked_are_still_shown(qapp):
    # Locking is about editing, not about hiding: the operator watching a run
    # must still see what is being surveyed.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRegions([RECT, OTHER])

    assert len(panel._rois) == 2
    assert panel.regions() == [RECT, OTHER]


def test_a_region_added_while_locked_is_locked_too(qapp):
    # setRegions builds fresh ROIs, which default to editable; a gate applied
    # only on the transition would leave them draggable mid-run.
    panel = makePanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    panel.setRunStatus("running")
    panel.setRegions([RECT])

    assert not panel._rois[0].translatable
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -k "slice or lock or paused or surveying or resuming" -v`

Expected: FAIL — `AttributeError: 'RegionPanel' object has no attribute 'setSliceReady'`.

- [ ] **Step 3: Write minimal implementation**

In `RegionPanel.__init__`, before the connections:

```python
        # The three independent reasons editing can be off, kept apart because
        # no writer can see another's condition: collapsing them into one
        # boolean would let a run ending unlock a panel that still has no slice
        # behind it. Same split SearchPanel already makes.
        self._runLocked = False
        self._sliceReady = False
        self._runStatus = None
```

and call `self._applyLock()` at the end of `__init__`, after the connections.

Add to `RegionPanel`:

```python
    def setInteractionLocked(self, locked: bool) -> None:
        """Disable editing while a run is in flight; the regions stay visible.

        The operator watching a run must still see what is being surveyed, so
        this is about editing, not about hiding.
        """
        self._runLocked = locked
        self._applyLock()

    def setSliceReady(self, ready: bool) -> None:
        """Whether a slice exists for these regions to belong to.

        New slice is what makes Area 1 usable, and the greyed-out controls are
        how the operator is told that it is the first step.
        """
        self._sliceReady = ready
        self._applyLock()

    def setRunStatus(self, status: str) -> None:
        """The bound run's last reported status.

        Only "paused" matters here, and only the *emitted* status will do.
        Orchestrator._checkPause() runs at the top of the run loop, before the
        refill check, so a Pause clicked during a survey does not stop that
        survey -- the producer goes on imaging tiles and reading regions for as
        long as it takes, and the loop parks at the next iteration. But
        sigStatus("paused") is emitted from inside _checkPause, immediately
        before it blocks, so while that status is current the worker is parked
        there and cannot be inside a refill. That is what makes editing safe.
        """
        self._runStatus = status
        self._applyLock()

    def _editable(self) -> bool:
        if not self._sliceReady:
            return False
        return not self._runLocked or self._runStatus == "paused"

    def _applyLock(self) -> None:
        editable = self._editable()
        self.addRegionBtn.setEnabled(editable)
        self.shapeCombo.setEnabled(editable)
        for roi in self._rois:
            self._applyRoiLock(roi)

    def _applyRoiLock(self, roi: pg.ROI) -> None:
        """Make one ROI match the current gate.

        Every affordance, not just the drag: leaving the handles live would let
        a locked region be resized, and leaving `removable` on would let it be
        deleted from the context menu.
        """
        editable = self._editable()
        roi.translatable = editable
        roi.resizable = editable
        roi.removable = editable
        for handle in roi.getHandles():
            handle.setVisible(editable)
```

Panning and zooming stay live in every state: the `ViewBox` is untouched by the gate, because looking at what is being surveyed is not editing it.

And apply the lock to each ROI as it is attached, in `_attachRoi`, after `self.view.addItem(roi)`:

```python
        self._applyRoiLock(roi)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -q`

Expected: PASS, once one earlier test is updated — a panel with no slice being inert is the intended behaviour, so `test_the_add_region_button_asks_its_owner` (Task 3) needs `panel.setSliceReady(True)` before the click. The rest of Task 3's tests drive `setRegions()` and `_rois` directly and are unaffected, since rendering is never gated.

- [ ] **Step 5: Prove both sides of the gate bite (mutation)**

Mutation A — drop the paused exception: `return not self._runLocked`.
Run: `... -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -k paused -v` → expect FAIL in `test_a_paused_run_unlocks_editing`.

Mutation B — widen it to any non-running status: `return not self._runLocked or self._runStatus != "running"`.
Run: `... -m pytest acq4/modules/Autopatch/tests/test_region_panel.py -k surveying -v` → expect FAIL in `test_surveying_locks_editing_even_though_pause_was_pressed`.

**Record the failing line number for each.** Revert both and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/region_panel.py acq4/modules/Autopatch/tests/test_region_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: allow region edits only when the run is parked

Editing needs a slice, and during a run it needs the emitted "paused"
status -- the point at which the worker is provably not reading regions.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 5: Pinned frames from the Camera module

**Files:**
- Modify: `acq4/util/imaging/imaging_ctrl.py` (`addPinnedFrame` ~line 274, `removePinnedFrame` ~line 286)
- Create: `acq4/modules/Autopatch/region_mirrors.py`
- Test: `acq4/modules/Autopatch/tests/test_region_mirrors.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `ImagingCtrl.sigPinnedFramesChanged` — `Qt.Signal()`, emitted by `addPinnedFrame` and `removePinnedFrame`.
  - `PinnedFrameMirror(view)` with `bind(imagingCtrl)`, `unbind()`, `refresh()`, and `items` (the mirrored `pg.ImageItem`s, in the order drawn).

**Why a copy and not the same item:** a `pg.ImageItem` belongs to exactly one `QGraphicsScene`. "Pinned frames display in both places" therefore cannot mean the same object in two views — the mirror builds its own item per pinned frame from the same image array and the same global transform.

- [ ] **Step 1: Write the failing test**

Create `acq4/modules/Autopatch/tests/test_region_mirrors.py`:

```python
"""Tests for Area 1's two one-way mirrors: the Camera module's pinned frames
coming in, and region outlines going out."""

import gc
import weakref

import numpy as np
import pyqtgraph as pg
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class FakeImagingCtrl(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl: a list of pinned image
    items and the signal that says it changed."""

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self):
        super().__init__()
        self.pinnedFrames = []

    def pin(self, item):
        item.setZValue(-10000 + len(self.pinnedFrames))
        self.pinnedFrames.append(item)
        self.sigPinnedFramesChanged.emit()

    def unpin(self, item):
        self.pinnedFrames.remove(item)
        self.sigPinnedFramesChanged.emit()


def makeFrameItem(value, x, y):
    # Asymmetric image on purpose: a transposed copy of a square array is
    # indistinguishable from the original.
    item = pg.ImageItem(np.full((4, 7), value, dtype=float))
    transform = Qt.QTransform()
    transform.translate(x, y)
    transform.scale(1e-6, 2e-6)
    item.setTransform(transform)
    return item


def makeMirror():
    from acq4.modules.Autopatch.region_mirrors import PinnedFrameMirror

    view = pg.ViewBox()
    return PinnedFrameMirror(view), view


def test_binding_shows_the_frames_already_pinned(qapp):
    # The operator pins frames before opening Autopatch as often as after.
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))
    mirror, _view = makeMirror()

    mirror.bind(source)

    assert len(mirror.items) == 1


def test_a_frame_pinned_later_appears(qapp):
    source = FakeImagingCtrl()
    mirror, _view = makeMirror()
    mirror.bind(source)

    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))

    assert len(mirror.items) == 1


def test_a_frame_unpinned_disappears(qapp):
    source = FakeImagingCtrl()
    item = makeFrameItem(1.0, 1e-3, 2e-3)
    source.pin(item)
    mirror, _view = makeMirror()
    mirror.bind(source)

    source.unpin(item)

    assert mirror.items == []


def test_the_mirrored_item_carries_the_same_pixels_and_placement(qapp):
    # A mirror that showed the right image in the wrong place would have the
    # operator draw regions over tissue that is somewhere else.
    source = FakeImagingCtrl()
    original = makeFrameItem(3.0, 1e-3, 2e-3)
    source.pin(original)
    mirror, _view = makeMirror()
    mirror.bind(source)

    copy = mirror.items[0]
    assert np.array_equal(copy.image, original.image)
    assert copy.transform() == original.transform()
    assert copy.zValue() == original.zValue()


def test_the_mirrored_item_is_a_distinct_object_in_this_view(qapp):
    # An ImageItem lives in exactly one scene, so re-adding the Camera module's
    # own item would take it out of the Camera module's view.
    source = FakeImagingCtrl()
    original = makeFrameItem(3.0, 1e-3, 2e-3)
    source.pin(original)
    mirror, view = makeMirror()
    mirror.bind(source)

    assert mirror.items[0] is not original
    assert mirror.items[0] in view.addedItems


def test_unbinding_clears_the_view_and_stops_listening(qapp):
    source = FakeImagingCtrl()
    source.pin(makeFrameItem(1.0, 1e-3, 2e-3))
    mirror, _view = makeMirror()
    mirror.bind(source)

    mirror.unbind()
    source.pin(makeFrameItem(2.0, 3e-3, 4e-3))

    assert mirror.items == []


def test_unbinding_releases_the_source(qapp):
    # A connection outliving its owner is this module's most-repeated defect:
    # a mirror still listening after teardown draws into a dead view.
    source = FakeImagingCtrl()
    mirror, _view = makeMirror()
    mirror.bind(source)
    ref = weakref.ref(source)

    mirror.unbind()
    del source
    gc.disable()
    try:
        assert ref() is None
    finally:
        gc.enable()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_mirrors.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.region_mirrors'`.

- [ ] **Step 3: Write minimal implementation**

In `acq4/util/imaging/imaging_ctrl.py`, add to the signal block at the top of `ImagingCtrl`:

```python
    sigPinnedFramesChanged = Qt.Signal()  # a frame was pinned or unpinned
```

Emit it as the last statement of `addPinnedFrame` and of `removePinnedFrame`:

```python
        self.sigPinnedFramesChanged.emit()
```

Create `acq4/modules/Autopatch/region_mirrors.py`:

```python
"""The two one-way mirrors either side of Area 1's view: the Camera module's
pinned frames coming in, and read-only region outlines going out."""

from __future__ import annotations

import pyqtgraph as pg

from acq4.util import Qt


class PinnedFrameMirror:
    """Shows the Camera module's pinned frames in another view.

    A pg.ImageItem belongs to exactly one QGraphicsScene, so displaying the
    pinned frames in both places cannot mean showing the same objects twice --
    adding the Camera module's own items here would take them out of the Camera
    module's view. This builds its own item per pinned frame instead, from the
    same image array and the same global transform.

    Display only: it holds no region state and nothing depends on it existing.
    """

    def __init__(self, view):
        self._view = view
        self._source = None
        self.items: list[pg.ImageItem] = []

    def bind(self, imagingCtrl) -> None:
        """Mirror `imagingCtrl`'s pinned frames, replacing any current binding.

        Draws what is already pinned rather than waiting for the next change:
        pinning frames before opening this window is as ordinary as after.
        """
        self.unbind()
        self._source = imagingCtrl
        imagingCtrl.sigPinnedFramesChanged.connect(self.refresh)
        self.refresh()

    def unbind(self) -> None:
        """Stop mirroring and take the copies out of the view."""
        if self._source is not None:
            Qt.disconnect(self._source.sigPinnedFramesChanged, self.refresh)
            self._source = None
        self._clearItems()

    def refresh(self) -> None:
        """Rebuild the mirrored items from the source's current set.

        Rebuilding wholesale rather than diffing: the set is a handful of frames
        changed by operator clicks, and a diff would be state to keep correct
        for no measurable gain.
        """
        self._clearItems()
        if self._source is None:
            return
        for original in self._source.pinnedFrames:
            copy = pg.ImageItem(original.image)
            copy.setTransform(original.transform())
            copy.setZValue(original.zValue())
            self._view.addItem(copy)
            self.items.append(copy)

    def _clearItems(self) -> None:
        for item in self.items:
            self._view.removeItem(item)
        self.items = []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_mirrors.py acq4/util -q`

Expected: PASS.

- [ ] **Step 5: Prove the release test bites (mutation)**

Temporarily remove the `Qt.disconnect(...)` line from `unbind`.

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_mirrors.py -k releases -v`

Expected: FAIL at `assert ref() is None`. **Record the failing line number.** Revert and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/util/imaging/imaging_ctrl.py acq4/modules/Autopatch/region_mirrors.py acq4/modules/Autopatch/tests/test_region_mirrors.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: mirror the Camera module's pinned frames into another view

ImagingCtrl announces pins and unpins, and PinnedFrameMirror redraws its own
copies -- an ImageItem belongs to only one scene.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 6: Region outlines in the Camera window

**Files:**
- Modify: `acq4/modules/Autopatch/region_mirrors.py`
- Test: `acq4/modules/Autopatch/tests/test_region_mirrors.py`

**Interfaces:**
- Consumes: `SearchRegion` subclasses; `REGION_PEN` from Task 2.
- Produces: `CameraMirror(cameraWindowGetter)` with `setEnabled(bool)`, `setRegions(regions)`, `clear()`, and `items` (the `QGraphicsPathItem`s currently in the Camera window).

`cameraWindowGetter` is a zero-argument callable returning the Camera window or `None`. A missing Camera module is ordinary, not an error: the checkbox is a display preference.

**On using `QPainterPath` here:** P2c-1 replaced `QPainterPath.intersects()` with closed-form geometry because Qt's path clipper has absolute tolerances that misreport tiles at SI-metre magnitudes. That finding is about *deciding overlap*. Drawing an outline asks Qt no questions, so a path is the right tool here — and this comment exists so a later reader does not think the two contradict.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_region_mirrors.py`:

```python
from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion

RECT = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)
ELLIPSE = EllipseRegion(3.0e-3, 1.0e-3, 3.6e-3, 1.2e-3)
TRIANGLE = PolygonRegion(((1.0e-3, 2.0e-3), (1.4e-3, 2.02e-3), (1.1e-3, 2.1e-3)))


class FakeCameraWindow:
    """Stands in for the Camera module's window: the addItem/removeItem pair
    Autopatch reaches it through."""

    def __init__(self):
        self.items = []

    def addItem(self, item, pos=(0, 0), scale=(1, 1), z=None, **kwds):
        self.items.append(item)
        if z is not None:
            item.setZValue(z)

    def removeItem(self, item):
        self.items.remove(item)


def makeCameraMirror(window):
    from acq4.modules.Autopatch.region_mirrors import CameraMirror

    return CameraMirror(lambda: window)


def test_disabled_by_default_nothing_reaches_the_camera(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)

    mirror.setRegions([RECT, ELLIPSE])

    assert window.items == []


def test_enabling_draws_the_regions_already_set(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setRegions([RECT, ELLIPSE])

    mirror.setEnabled(True)

    assert len(window.items) == 2


def test_regions_set_while_enabled_are_drawn(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)

    mirror.setRegions([RECT, ELLIPSE, TRIANGLE])

    assert len(window.items) == 3


def test_disabling_takes_them_out_again(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    mirror.setEnabled(False)

    assert window.items == []


def test_the_outlines_cannot_be_grabbed(qapp):
    # Autopatch is the only place a region is edited. A mirrored outline that
    # accepted a mouse press would be a second, silent editing surface.
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    assert window.items[0].acceptedMouseButtons() == Qt.Qt.NoButton


@pytest.mark.parametrize(
    "region,expected",
    [(RECT, (1.0e-3, 2.0e-3, 0.4e-3, 0.1e-3)), (ELLIPSE, (3.0e-3, 1.0e-3, 0.6e-3, 0.2e-3))],
)
def test_an_outline_lands_on_its_regions_bounds(qapp, region, expected):
    # Asymmetric bounds on both shapes: a square outline cannot catch a width
    # and height that have been swapped.
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([region])

    rect = window.items[0].path().boundingRect()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == pytest.approx(expected)


def test_a_polygon_outline_has_a_vertex_per_vertex(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([TRIANGLE])

    path = window.items[0].path()
    drawn = {(path.elementAt(i).x, path.elementAt(i).y) for i in range(path.elementCount())}
    for vertex in TRIANGLE.vertices:
        assert any(
            abs(x - vertex[0]) < 1e-12 and abs(y - vertex[1]) < 1e-12 for x, y in drawn
        )


def test_no_camera_window_is_not_an_error(qapp):
    # A rig with the Camera module unloaded is ordinary; the checkbox is a
    # display preference, not a requirement.
    from acq4.modules.Autopatch.region_mirrors import CameraMirror

    mirror = CameraMirror(lambda: None)
    mirror.setEnabled(True)
    mirror.setRegions([RECT])

    assert mirror.items == []


def test_clear_removes_everything_it_put_there(qapp):
    window = FakeCameraWindow()
    mirror = makeCameraMirror(window)
    mirror.setEnabled(True)
    mirror.setRegions([RECT, ELLIPSE])

    mirror.clear()

    assert window.items == []
    assert mirror.items == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_region_mirrors.py -k camera -v`

Expected: FAIL — `ImportError: cannot import name 'CameraMirror'`.

- [ ] **Step 3: Write minimal implementation**

Append to `acq4/modules/Autopatch/region_mirrors.py`:

```python
from acq4.experiment.search_region import EllipseRegion, PolygonRegion

from .region_panel import REGION_PEN

# Above the camera frame image so an outline is visible over tissue, below the
# pipette target and its arrows at z=5000 so those stay on top -- the same band
# the AutomationDebug survey ROI sits in.
_MIRROR_Z = 4000


def _pathForRegion(region) -> Qt.QPainterPath:
    """The outline of `region`, in global metres.

    A QPainterPath is the right tool for drawing an outline even though P2c-1
    removed QPainterPath from the *overlap* test: that finding is about asking
    Qt to decide whether a rect and a shape intersect, where its clipper's
    absolute tolerances misreport tiles at SI-metre magnitudes. Drawing asks Qt
    no such question.
    """
    path = Qt.QPainterPath()
    if isinstance(region, PolygonRegion):
        first = region.vertices[0]
        path.moveTo(first[0], first[1])
        for x, y in region.vertices[1:]:
            path.lineTo(x, y)
        path.closeSubpath()
        return path
    x0, y0, x1, y1 = region.bounds()
    rect = Qt.QRectF(x0, y0, x1 - x0, y1 - y0)
    if isinstance(region, EllipseRegion):
        path.addEllipse(rect)
    else:
        path.addRect(rect)
    return path


class CameraMirror:
    """Draws read-only outlines of Autopatch's regions in the Camera window.

    Outlines are QGraphicsPathItems, not ROIs, and that is what makes them
    read-only structurally rather than by policy: there is no handle to grab and
    no second copy of a region's state to reconcile. Autopatch stays the only
    place a region is edited.

    Holds no region state of its own -- it is told what to draw. A Camera module
    that is not loaded is ordinary, not an error: this is a display preference.
    """

    def __init__(self, cameraWindowGetter):
        self._cameraWindow = cameraWindowGetter
        self._enabled = False
        self._regions = []
        self.items = []

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._redraw()

    def setRegions(self, regions) -> None:
        self._regions = list(regions)
        self._redraw()

    def clear(self) -> None:
        """Take every outline out of the Camera window.

        Separate from setEnabled(False) because teardown has to remove them
        without changing what the operator asked for.
        """
        window = self._cameraWindow()
        for item in self.items:
            if window is not None:
                window.removeItem(item)
        self.items = []

    def _redraw(self) -> None:
        self.clear()
        if not self._enabled:
            return
        window = self._cameraWindow()
        if window is None:
            return
        for region in self._regions:
            item = Qt.QGraphicsPathItem(_pathForRegion(region))
            item.setPen(REGION_PEN)
            item.setAcceptedMouseButtons(Qt.Qt.NoButton)
            window.addItem(item, z=_MIRROR_Z)
            self.items.append(item)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/region_mirrors.py acq4/modules/Autopatch/tests/test_region_mirrors.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: show Autopatch's regions in the Camera window

Read-only path outlines, so Autopatch stays the only place a region can be
edited and there is no second copy of its state to reconcile.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 7: Mount Area 1 in the window

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py`
- Modify: `acq4/modules/Autopatch/search_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`
- Test: `acq4/modules/Autopatch/tests/test_search_panel.py`

**Interfaces:**
- Consumes: `RegionPanel` (Tasks 3–4), `PinnedFrameMirror` (Task 5), `CameraMirror` (Task 6), `Slice.setRegions` (Task 1).
- Produces: `AutopatchWindow.regionPanel`, `AutopatchWindow._onRegionsEdited(regions)`, `AutopatchWindow._cameraWindow()`.

**This task owns every call site of the controls it moves.** Derived from `git grep`, not from memory — a breaking API change whose signature-owning task does not own all its callers leaves a red tree at an intermediate commit, which is what happened in P2c-1.

`SearchPanel` loses: `sigAddRegionRequested` (line 32), `shapeCombo` (95–102), `addRegionBtn` (104–109), the `"Region shape"` form row (118), the `addRegionBtn` layout add (123), the `addRegionBtn.clicked` connection (136), `regionShape()` (179–181), and both entries in `_applyLock` (241–242).

`test_search_panel.py` loses the cases at lines 214–216, 242–243, 269, 276–277 and 287–288 — every assertion about `addRegionBtn`, `shapeCombo`, `regionShape`, or `sigAddRegionRequested`. Their coverage now lives in `test_region_panel.py`.

`test_window_integration.py` needs three edits, and the ~20 `win.addRegionHere()` calls are unaffected because that method keeps its name and behaviour:

- `test_add_region_here_builds_the_shape_area_2_selects` (~line 688) — rename to `..._the_shape_area_1_selects`, retarget to `win.regionPanel.shapeCombo`, and drop its now-false opening comment ("Until Area 1 can draw ROIs, this selector is the only way to seed a non-rectangular region").
- `test_area_2_is_locked_until_a_slice_exists` (~line 1417) — it asserts on `win.searchPanel.addRegionBtn`, which no longer exists. Point it at a control Area 2 still owns (`win.searchPanel.nearDepthSpin`), and add the Area 1 equivalent from the new tests below.
- `test_new_slice_reports_a_missing_storage_directory_in_area_2` (~line 1402) — leave it alone here; Task 9 rewrites it.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_window_integration.py`, following that file's existing fixture conventions for building a window with a fake camera:

These use the `win` fixture that file already defines (`_makeWindow(tmp_path)` — a window with a loaded no-op protocol, a camera-backed selector, and a manager over a real temporary directory):

```python
def test_a_new_slice_leaves_area_1_empty_and_live(win):
    # A Slice is fresh tissue with no regions, and Area 1 has to say so: an
    # outline left from the last slice is a coordinate the operator might trust.
    win.addRegionHere()
    assert win.regionPanel.regions()

    win.newSlice()

    assert win.regionPanel.regions() == []
    assert win.regionPanel.addRegionBtn.isEnabled()


def test_seeding_a_region_draws_it_in_area_1(win):
    win.addRegionHere()

    assert len(win.regionPanel.regions()) == 1
    assert win.regionPanel.regions() == win.slice.regions


def test_add_region_here_seeds_a_polygon_when_area_1_asks_for_one(win):
    # PolygonRegion has had no control able to produce it since P2c-1.
    from acq4.experiment.search_region import PolygonRegion

    win.newSlice()
    win.regionPanel.shapeCombo.setCurrentIndex(
        win.regionPanel.shapeCombo.findData("polygon")
    )

    win.addRegionHere()

    region = win.slice.regions[0]
    assert isinstance(region, PolygonRegion)
    # Four corners of the same 3x3-field box the other two shapes get, so the
    # button places a region of a known size whichever shape is selected.
    assert len(region.vertices) == 4
    assert len(win.slice.tileGrid()) > 1


def test_editing_a_region_in_area_1_reaches_the_slice(win):
    win.newSlice()
    edited = RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)

    win.regionPanel.sigRegionsChanged.emit([edited])

    assert win.slice.regions == [edited]


def test_editing_a_region_refreshes_the_survey_readout(win):
    # The readout counts tiles over the regions, so an edit that did not refresh
    # it would go on reporting the survey's size for a region that is gone.
    win.newSlice()
    win.addRegionHere()
    before = win.searchPanel.surveyLabel.text()

    win.regionPanel.sigRegionsChanged.emit(
        [RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)]
    )

    assert win.searchPanel.surveyLabel.text() != before


def test_a_region_edit_with_no_slice_is_ignored(win):
    # Area 1's controls are gated on a slice existing, but a signal is not a
    # permission check, and a traceback on the GUI thread is not a second line
    # of defence.
    assert win.slice is None

    win.regionPanel.sigRegionsChanged.emit([])

    assert win.slice is None


def test_area_1_is_locked_until_a_slice_exists(win):
    assert not win.regionPanel.addRegionBtn.isEnabled()

    win.newSlice()

    assert win.regionPanel.addRegionBtn.isEnabled()


def test_a_running_run_locks_area_1(win):
    win.newSlice()

    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("running")

    assert not win.regionPanel.addRegionBtn.isEnabled()


def test_a_paused_run_unlocks_area_1(win):
    # The other side of the gate, wired through the same two window-level
    # connections rather than by calling the panel directly.
    win.newSlice()
    win.statusPanel.sigInteractionLocked.emit(True)
    win.statusPanel.sigStatusChanged.emit("running")

    win.statusPanel.sigStatusChanged.emit("paused")

    assert win.regionPanel.addRegionBtn.isEnabled()


def test_the_mirror_checkbox_drives_the_camera_mirror(win):
    win.newSlice()
    win.addRegionHere()

    win.regionPanel.mirrorCheck.setChecked(True)

    assert win._cameraMirror._enabled
    assert win._cameraMirror._regions == win.slice.regions


def test_teardown_takes_the_mirrored_outlines_out_of_the_camera_window(win):
    # A camera window has to be supplied for this to test anything: _FakeManager
    # has no Camera module, so _cameraWindow() returns None and the mirror holds
    # nothing whether or not teardown clears it. Asserting an empty list against
    # a mirror that was never able to draw is asserting a default.
    drawn = []
    fakeCameraWindow = SimpleNamespace(
        addItem=lambda item, **kwds: drawn.append(item),
        removeItem=drawn.remove,
    )
    win._cameraMirror._cameraWindow = lambda: fakeCameraWindow
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    assert drawn, "nothing was mirrored, so teardown has nothing to prove"

    win.teardown()

    assert drawn == []
```

The pinned-frame mirror's teardown is proven in Task 6 (`test_unbinding_releases_the_source`), where a source exists to release; there is no imaging control behind `_FakeManager` for it to have bound here.

`RectRegion` is already imported at the top of that file. There is no Camera module behind `_FakeManager`, so `_cameraWindow()` returns `None` and the Camera mirror's `items` stay empty in these tests — which is why the mirror's drawing is tested against a fake window in Task 7 and only its *wiring* is tested here.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -k "area_1 or mirror or seeds" -v`

Expected: FAIL — `AttributeError: 'AutopatchWindow' object has no attribute 'regionPanel'`.

- [ ] **Step 3: Strip the moved controls out of `SearchPanel`**

Apply every deletion listed in the Interfaces block above to `acq4/modules/Autopatch/search_panel.py`, and update its module docstring to drop "region seeding":

```python
"""SearchPanel: Area 2's cell-finding config -- the search constraints that
parameterise a cell producer, and a survey progress readout."""
```

Delete the corresponding cases from `test_search_panel.py`.

- [ ] **Step 4: Write the window integration**

In `acq4/modules/Autopatch/Autopatch.py`:

Imports:

```python
from acq4.experiment.search_region import EllipseRegion, PolygonRegion, RectRegion

from .region_mirrors import CameraMirror, PinnedFrameMirror
from .region_panel import RegionPanel
```

In `__init__`, replace the Area 1 block (the comment and `newSliceBtn` block) with:

```python
        self.newSliceBtn = Qt.QPushButton("New slice")
        self.newSliceBtn.setToolTip(
            "Discard the current slice -- its regions, coverage, and queued "
            "cells -- and start a fresh one for newly mounted tissue."
        )
        self.regionPanel = RegionPanel()
        self.area1Box.layout().addWidget(self.newSliceBtn)
        self.area1Box.layout().addWidget(self.regionPanel)

        self._pinnedFrameMirror = PinnedFrameMirror(self.regionPanel.view)
        self._cameraMirror = CameraMirror(self._cameraWindow)
```

Replace the left-column layout so Area 1 can be dragged large — a region spans a slice, and a fixed-height box makes drawing one an exercise in patience:

```python
        leftCol = Qt.QSplitter(Qt.Qt.Vertical)
        leftCol.addWidget(self.area1Box)
        leftCol.addWidget(self.area2Box)
        # Area 1 is the view; Area 2 is four spin boxes and a readout.
        leftCol.setStretchFactor(0, 3)
        leftCol.setStretchFactor(1, 1)

        rightCol = Qt.QVBoxLayout()
        rightCol.addWidget(self.area3Box)
        rightCol.addWidget(self.area4Box)
        rightCol.addWidget(self.area5Box)
        rightColWidget = Qt.QWidget()
        rightColWidget.setLayout(rightCol)

        outer = Qt.QHBoxLayout()
        outer.addWidget(leftCol, 2)
        outer.addWidget(rightColWidget, 1)
        self.setLayout(outer)
```

Wiring, beside the existing connections:

```python
        self.regionPanel.sigAddRegionRequested.connect(self.addRegionHere)
        self.regionPanel.sigRegionsChanged.connect(self._onRegionsEdited)
        self.regionPanel.mirrorCheck.toggled.connect(self._cameraMirror.setEnabled)
        self.statusPanel.sigInteractionLocked.connect(
            self.regionPanel.setInteractionLocked
        )
        self.statusPanel.sigStatusChanged.connect(self.regionPanel.setRunStatus)
```

Delete the old `self.searchPanel.sigAddRegionRequested.connect(self.addRegionHere)` line.

Add the new methods:

```python
    def _cameraWindow(self):
        """The Camera module's window, or None if there is not one.

        Not having one is ordinary -- a rig with the module unloaded, or a
        headless test -- and both mirrors treat it as nothing to do rather than
        as a failure.
        """
        if self.manager is None:
            return None
        try:
            return self.manager.getModule("Camera").window()
        except Exception:
            return None

    def _onRegionsEdited(self, regions) -> None:
        """Take Area 1's edited region list as the slice's regions.

        A wholesale swap, which is what makes this safe to do while a producer
        may be reading regions on the worker thread (see Slice.setRegions).

        A signal is not a permission check: Area 1's controls are gated on a
        slice existing, but arriving here without one must not raise on the GUI
        thread.
        """
        if self.slice is None:
            return
        self.slice.setRegions(regions)
        self._cameraMirror.setRegions(regions)
        self._refreshSurveyStats()
```

In `_startSlice`, after `self.searchPanel.setSliceReady(True)`:

```python
        self.regionPanel.setSliceReady(True)
        # A fresh Slice has no regions, and an outline left from the last one is
        # a coordinate on tissue that may no longer be there.
        self.regionPanel.setRegions([])
        self._cameraMirror.setRegions([])
        self._bindPinnedFrames(camera)
```

and add:

```python
    def _bindPinnedFrames(self, camera) -> None:
        """Mirror `camera`'s pinned frames into Area 1's view.

        Bound here rather than at construction because this is the first point
        at which a camera is known to be selected, and both routes into a slice
        pass through it.
        """
        window = self._cameraWindow()
        if window is None:
            return
        try:
            imagingCtrl = window.getInterfaceForDevice(camera.name()).imagingCtrl
        except (KeyError, AttributeError):
            return
        self._pinnedFrameMirror.bind(imagingCtrl)
```

In `addRegionHere`, replace the `regionClass` selection and the `addRegion` call:

```python
        shape = self.regionPanel.regionShape()
        x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        if shape == "polygon":
            # The same box, as a polygon: the button places a region of a known
            # size, and the shape selector says what kind. A four-vertex seed is
            # also the readiest thing to reshape into the outline actually
            # wanted, which is the point of choosing polygon at all.
            region = PolygonRegion(((x0, y0), (x1, y0), (x1, y1), (x0, y1)))
        else:
            regionClass = EllipseRegion if shape == "ellipse" else RectRegion
            region = regionClass(x0, y0, x1, y1)
        self.slice.addRegion(region)
        self.regionPanel.setRegions(self.slice.regions)
        self._cameraMirror.setRegions(self.slice.regions)
        self._refreshSurveyStats()
```

In `newSlice`, after `self.cellPanel.clearCells()`:

```python
        self.regionPanel.setRegions([])
        self._cameraMirror.setRegions([])
```

In `teardown`, before the existing orchestrator release:

```python
        self._pinnedFrameMirror.unbind()
        self._cameraMirror.clear()
```

- [ ] **Step 5: Run the whole suite**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ acq4/experiment/tests/ -q`

Expected: PASS, no failures, no warnings. If anything in `test_window_integration.py` or `test_teardown.py` still references `searchPanel.shapeCombo` or `searchPanel.addRegionBtn`, fix it here — this task owns those call sites.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/search_panel.py acq4/modules/Autopatch/tests/
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat!: give Area 1 the region view and its controls

The shape selector and "Add region here" move from Area 2 to Area 1, where
the regions they make are now drawn, edited, and mirrored.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

### Task 8: New slice's instruction band

**Files:**
- Modify: `acq4/modules/Autopatch/status_panel.py`
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`newSlice`'s `except HelpfulException`)
- Test: `acq4/modules/Autopatch/tests/test_status_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `StatusPanel._updateErrorBand`, `AutopatchWindow.newSlice`.
- Produces: `StatusPanel.setInstruction(text: str)`, `StatusPanel.clearInstruction()`, `StatusPanel.instruction() -> str`.

**Why:** `newSlice()` currently reports `create_data_dir`'s `HelpfulException` — in practice `"Storage directory has not been set."`, the likeliest first-use failure of the button — through `searchPanel.setError()`, with a comment saying Area 3's band does not exist yet. It does. An instruction is not a `RunErrorRecord`: it gets no traceback, no Copy, and no Show-in-log, because there is nothing in the log to show.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_status_panel.py`:

That file builds its records with a local `_record(exc_type="RuntimeError", message="boom", cell_repr="'c1'")` helper (~line 415), and imports `StatusPanel` **inside each test function** rather than at module level. Follow that convention — open each test below with `from acq4.modules.Autopatch.status_panel import StatusPanel`.

```python
def test_an_instruction_shows_in_the_band(qapp):
    panel = StatusPanel()

    panel.setInstruction("Storage directory has not been set.")

    assert panel.instructionLabel.isVisible()
    assert panel.instructionLabel.text() == "Storage directory has not been set."


def test_an_instruction_offers_no_log_link(qapp):
    # Show in log narrows the log to a run's records. An instruction is
    # guidance about a click that never started a run, so there is nothing
    # there to show and a button that led nowhere would be worse than none.
    panel = StatusPanel()

    panel.setInstruction("Storage directory has not been set.")

    assert not panel.showInLogBtn.isVisible()


def test_clearing_an_instruction_empties_the_band(qapp):
    panel = StatusPanel()
    panel.setInstruction("Storage directory has not been set.")

    panel.clearInstruction()

    assert panel.instruction() == ""
    assert not panel.instructionLabel.isVisible()


def test_a_run_error_still_wins_the_band(qapp):
    # A failure that halted a run is about tissue and a pipette in it; guidance
    # about a button is not. The error is the more urgent of the two and must
    # not be displaced by a stale instruction.
    panel = StatusPanel()
    record = _record()
    panel.setInstruction("Storage directory has not been set.")

    panel._onRunError(record)

    assert record.exc_message in panel.instructionLabel.text()
    assert panel.showInLogBtn.isVisible()


def test_the_instruction_comes_back_once_the_error_clears(qapp):
    # The band holds two independent things. Whatever the instruction asked for
    # has not been done in the meantime, so it is held rather than overwritten.
    panel = StatusPanel()
    panel.setInstruction("Storage directory has not been set.")
    panel._onRunError(_record())

    panel.clearError()

    assert panel.instructionLabel.text() == "Storage directory has not been set."
    assert not panel.showInLogBtn.isVisible()
```

In `test_window_integration.py`, rewrite the existing
`test_new_slice_reports_a_missing_storage_directory_in_area_2` (~line 1402) — it asserts the message lands in Area 2's error label, which is the behaviour this task moves:

```python
def test_new_slice_reports_a_missing_storage_directory_as_an_instruction(win):
    # The likeliest first use of New slice is by an operator who has not chosen
    # a storage directory. They get an instruction in Area 3, and Area 2's error
    # line -- which is about the search constraints -- stays out of it.
    from acq4.util.HelpfulException import HelpfulException

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()

    assert "Storage directory" in win.statusPanel.instruction()
    assert "Storage directory" not in win.searchPanel.errorLabel.text()


def test_a_successful_new_slice_retracts_the_instruction(win):
    # The instruction says what to do next; once it has been done it is a lie.
    from acq4.util.HelpfulException import HelpfulException

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    original = win.manager.getCurrentDir
    win.manager.getCurrentDir = boom
    win.newSlice()
    assert win.statusPanel.instruction() != ""

    win.manager.getCurrentDir = original
    win.newSlice()

    assert win.statusPanel.instruction() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -k instruction -v`

Expected: FAIL — `AttributeError: 'StatusPanel' object has no attribute 'setInstruction'`.

- [ ] **Step 3: Write minimal implementation**

In `StatusPanel.__init__`, beside `self._lastError`:

```python
        # Operator guidance about a control, as opposed to a failure that halted
        # a run. Held separately from _lastError so neither erases the other:
        # they have different writers, and neither can see the other's
        # condition.
        self._instruction = ""
```

Add:

```python
    def setInstruction(self, text: str) -> None:
        """Show operator guidance in the band -- what to do, not what broke.

        For a control that could not proceed, `AutopatchWindow.newSlice()` with
        no storage directory chosen being the case this exists for. An
        instruction is deliberately not a RunErrorRecord: no traceback, no Copy,
        and no Show in log, because no run happened and there is nothing in the
        log to show.
        """
        self._instruction = text
        self._updateErrorBand()

    def clearInstruction(self) -> None:
        self._instruction = ""
        self._updateErrorBand()

    def instruction(self) -> str:
        """The guidance currently showing, or an empty string."""
        return self._instruction
```

Rewrite `_updateErrorBand`:

```python
    def _updateErrorBand(self) -> None:
        """Render whichever of the two the band is carrying, the error first.

        A failure that halted a run is about tissue and a pipette in it;
        guidance about a button is not. The instruction is still held and comes
        back once the error is cleared, since whatever it asked for has not been
        done in the meantime.
        """
        record = self._lastError
        if record is not None:
            self.instructionLabel.setText(f"{record.exc_type}: {record.exc_message}")
        else:
            self.instructionLabel.setText(self._instruction)
        showing = record is not None or bool(self._instruction)
        self.instructionLabel.setVisible(showing)
        self.showInLogBtn.setVisible(record is not None)
```

In `Autopatch.py`'s `newSlice`, replace the `except HelpfulException` body:

```python
        except HelpfulException as exc:
            # Guidance, not a failure report: the operator has not chosen a
            # storage directory, and Area 3's band is where instructions go.
            # Narrowed to HelpfulException so a genuine programming error (a
            # missing manager, say) propagates instead of being reported as
            # storage guidance.
            self.statusPanel.setInstruction(str(exc))
            return
```

and clear it on the success path, immediately after `self.statusPanel.clearError()`:

```python
        self.statusPanel.clearInstruction()
```

- [ ] **Step 4: Run the whole suite**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ acq4/experiment/tests/ -q`

Expected: PASS.

- [ ] **Step 5: Prove the precedence test bites (mutation)**

Temporarily reverse the precedence in `_updateErrorBand` so the instruction wins when both are set.

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -k wins -v`

Expected: FAIL in `test_a_run_error_still_wins_the_band`. **Record the failing line number.** Revert and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/status_panel.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'MSG'
feat: instruct the operator when New slice has nowhere to write

A storage directory that was never chosen is guidance, so it lands in Area
3's band without a traceback or a log link.

🤖 Generated with [Claude Code](https://claude.ai/code)
MSG
```

---

## Final verification

- [ ] Run the full repo suite: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4 -q`. Expected: green, with the Autopatch and experiment counts above their pre-branch numbers (677 in the touched suites, 1127 repo-wide as of `00c75e269`). No skips, no new warnings.
- [ ] `git log --format='%an %s' _reviewed..HEAD` — every commit authored `Martin Chase (claude)`, and `git log --format=%B _reviewed..HEAD | grep -c "Generated with"` equals the commit count.
- [ ] Grep the new tests for vacuous assertions: `git grep -n "is False\|== \[\]\|is None" -- 'acq4/modules/Autopatch/tests/test_region*'`. For each, name what primed the state. An assertion whose expected value equals the default is vacuous by construction — six of these were caught on one earlier branch.
- [ ] Live smoke test, which the headless suite structurally cannot reach:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python bin/acq4 --config /home/martin/src/acq4/acq4/config/mock/default.cfg -m Autopatch
```

  Check: New slice enables Area 1; seed a rectangle, an ellipse, and a polygon with "Add region here" and confirm each is tiled by the survey readout; drag and resize one; click a polygon edge to add a vertex and drag it, then confirm the survey retiles to the new outline; check that an ellipse offers no rotate handle; right-click Remove; tick Mirror to Camera and confirm outlines appear in the Camera window and cannot be grabbed there; pin a frame in the Camera module and confirm it appears in Area 1; start a run and confirm Area 1 locks, pause it and confirm it unlocks; close the window and confirm exit code 0 with no segfault.
