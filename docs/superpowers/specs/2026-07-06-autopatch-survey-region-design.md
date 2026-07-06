# Autopatch Survey Region — Design

## Problem

`acq4.modules.AutomationDebug.autopatch.Autopatcher._autopatchFindCell` grabs a new
z-stack (and re-finds the surface) wherever the camera currently points in XY.
Nothing moves the stage between stacks, so a demo re-images the same field instead
of surveying a larger area. We want to survey a user-defined rectangular region by
packing the camera's field of view (FOV) across it as a grid, imaging one
unexamined tile per z-stack, and finishing the demo once every tile is imaged.

## Decisions

- **Clear region** removes the ROI entirely and resets imaged-tile progress.
- **Tile overlap** is a configurable absolute distance, default 20 µm, so cells
  straddling a FOV edge are not missed. The step between adjacent tiles is
  `fov - overlap`.
- **No grid overlay** — only the draggable survey rectangle is shown; imaged tiles
  are tracked internally.
- **A survey region is required** before the demo searches for new cells. With no
  region, the search branch stops the demo with an explanatory message instead of
  imaging at the current position.

### The "auto find more cells" checkbox

`autoFindMoreCellsCheck` remains fully functional and is the master switch for
the additional-z-stack (survey) behavior of `_autopatchFindCell`. When unchecked,
the demo works through any pre-queued cells and then stops — it never acquires an
additional z-stack. When checked, an empty queue drives the survey (move to the
next un-imaged tile and detect) until the region is exhausted.

This is already encoded by the existing `_outOfCells`, which returns True (stop)
once the unranked queue is empty, at least one cell has been worked, and the box
is unchecked — so the search branch is never reached and no additional z-stack is
taken. The survey-region checks layer on top of that gate: reaching the search
branch additionally requires a region (else stop) and an un-imaged tile (else
stop). The checkbox and the region are independent controls — checkbox enables
surveying at all; the region bounds where and how long it surveys.

## Architecture

A new `SurveyRegion` object is composed into `AutomationDebugWindow` alongside the
existing `CellDetector`, `MockDataHandler`, `Autopatcher`, and `FeatureTracker`.
The grid math lives in two pure module-level functions so it can be unit-tested
without Qt or hardware; the ROI and camera glue is a thin GUI-thread layer.

### New file: `acq4/modules/AutomationDebug/survey.py`

**Pure functions (TDD'd):**

```python
def plan_grid(x0, y0, x1, y1, fov_w, fov_h, overlap) -> list[tuple[float, float]]:
    """Serpentine-ordered tile centers whose union fully covers [x0,x1] x [y0,y1].

    The step between adjacent tiles is `fov - overlap` (an absolute distance).
    The tile count per axis is `n = ceil((extent - fov) / step) + 1` (at least
    1), and the grid is centered over the rectangle so the union of tiles covers
    the whole rect. The outermost tiles may extend past the rect edges — excess
    tissue outside the ROI is acceptable, but no part of the ROI is left
    unimaged. A single tile at the rect center is returned when the rect is
    smaller than one FOV. Rows alternate direction (boustrophedon) to minimize
    stage travel.
    """

def select_next(grid, visited, threshold) -> tuple[float, float] | None:
    """First center in `grid` not within `threshold` of any center in `visited`;
    None when every planned tile is already covered."""
```

Recomputing the grid on every `nextTile` call (rather than freezing it when the
ROI is created) makes the survey tolerant of the user moving or resizing the ROI
mid-run.

**`SurveyRegion` class (GUI-thread glue, manual-test):**

- `__init__(window)` — stores the window, `self._roi = None`, `self._visited = []`.
- `addRegion()` — create a non-rotatable `pg.RectROI` in the Camera window's view
  (global meter coordinates), default centered on the current FOV at ~3x3 tiles;
  add it via `manager.getModule("Camera").window().addItem(...)`; store it.
  Replaces any existing ROI.
- `clearRegion()` — remove the ROI from the view and clear `self._visited`.
- `hasRegion() -> bool` — whether an ROI currently exists.
- `nextTile() -> tuple[float, float] | None` — read ROI bounds and current camera
  FOV, call `plan_grid` then `select_next(grid, self._visited, threshold)`; on a
  hit, append the chosen center to `self._visited` and return it. Runs on the GUI
  thread (reads Qt ROI geometry).
- `reset()` — clear `self._visited` (ROI persists). Called at demo start so a
  re-run re-surveys the same region.

**FOV computation** mirrors the existing `_setTopLeft`/`_setBottomRight`:

```python
region = cam.getParam("region")            # (x, y, w, h) in pixels
xf = cam.globalTransform()
tl = xf.map((region[0], region[1], 0))
br = xf.map((region[0] + region[2], region[1] + region[3], 0))
fov_w, fov_h = abs(br[0] - tl[0]), abs(br[1] - tl[1])
```

`threshold` for `select_next` is half the smaller tile step
(`min(fov_w - overlap, fov_h - overlap) / 2`), so a planned center counts as
"already imaged" only when it coincides with a visited one.

### UI wiring in `AutomationDebugWindow`

Add `self._surveyRegion = SurveyRegion(self)` to the composed objects. Add two
buttons and an overlap spinbox near the autopatch controls, injected the same way
the z-stack depth spinboxes already are:

- "Add survey region" → `self._surveyRegion.addRegion`
- "Clear region" → `self._surveyRegion.clearRegion`
- overlap `pg.SpinBox(value=20e-6, suffix='m', siPrefix=True, step=5e-6,
  bounds=(0, None))` read by `nextTile` as an absolute distance in meters.

### `_autopatchFindCell` integration

In the empty-queue search branch, after the existing `_outOfCells()` gate (which
handles the unchecked-checkbox stop) and before the existing surface/focus/detect
sequence:

```python
region = win._surveyRegion
if not region.hasRegion():
    set_state("Autopatch: add a survey region to search for cells")
    return None
center = run_in_gui_thread(region.nextTile)
if center is None:
    set_state("Autopatch: survey region fully imaged; stopping")
    return None
set_state("Autopatch: moving to next survey tile")
win.scopeDevice.setGlobalPosition(center, name="autopatch survey move").wait()
# ... existing findSurfaceDepth + setFocusDepth + _detectNeuronsZStack ...
```

`setGlobalPosition` is the XY-only move already used by `_autoTarget`, so the
`(cx, cy)` tile center passes straight through. Tile centers are XY only —
`plan_grid`, `select_next`, and `visited` all operate in the XY plane. Anywhere a
full 3D global point is needed from a tile center, Z is taken from the current
focus/stage Z (e.g. `cam.globalCenterPosition()[2]` / `getFocusDepth()`) rather
than being invented. Per-tile surface finding is already done inside
`_detectNeuronsZStack`, so a region spanning uneven tissue works without extra
handling.

`Autopatcher._autopatchDemo` calls `win._surveyRegion.reset()` once at the start
of the run so imaged-tile progress starts fresh while the ROI persists.

## Error handling

- No region when a search is needed → stop the demo cleanly with a `set_state`
  message (not an exception).
- Region fully imaged → stop the demo cleanly with a `set_state` message.
- ROI smaller than one FOV → `plan_grid` returns a single center at the ROI
  center; the survey images once and then reports exhaustion.

## Testing

`acq4/modules/AutomationDebug/tests/test_survey.py`:

- `plan_grid`: single tile when the rect is smaller than one FOV; correct tile
  count and spacing for a known rect/FOV/overlap; serpentine row alternation;
  the union of tiles fully covers the rect (every point of the rect, including
  the corners, lies inside at least one tile) even when the rect is not an exact
  multiple of the step.
- `select_next`: skips centers near visited ones; returns `None` when all planned
  tiles are visited; returns the first tile when nothing is visited.

The ROI creation, overlay, and camera moves are hard to unit-test and are
verified by driving the live UI: add a region, run the demo, confirm the stage
steps through tiles and the demo stops when the region is covered.
