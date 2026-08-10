# Autopatch P2c-3a — Area 1 region graphics

Design for the first slice of Area 1: a global-coordinate view inside the
Autopatch window that shows the Camera module's pinned frames, lets the operator
draw and edit search regions over them, and optionally mirrors those regions into
the Camera window as read-only outlines.

Parent design: `autopatch-orchestration-design.md` §7 Area 1, §9, §10 (P2c).

---

## 1. Why this exists

Regions today are created blind. `SearchPanel`'s "Add region here" seeds a shape
of roughly 3×3 fields of view around the camera's current centre
(`AutopatchWindow.addRegionHere`), and nothing in the interface ever draws it.
The operator cannot see where the region sits, cannot tell whether it covers the
tissue they mean to search, and cannot change it once made. P2c-1 generalised
regions from rectangles to shapes precisely so a cortical layer or an undamaged
corner could be searched — and `PolygonRegion` remains unreachable from the
interface, because no control can produce one.

This phase makes regions visible, drawable, and editable.

## 2. Scope

**In:**

- An Area 1 view: `pg.GraphicsView` + aspect-locked `pg.ViewBox` in global metres.
- Pinned frames from the Camera module mirrored into that view (display only).
- Seeding, moving, resizing, reshaping, and deleting regions — rectangle,
  ellipse, and closed polygon.
- The shape selector and "Add region here", moved out of Area 2 into Area 1.
- A **mirror to Camera** checkbox putting read-only region outlines in the
  Camera window.
- `Slice.setRegions()` — a wholesale swap replacing in-place mutation.
- Moving `newSlice()`'s `HelpfulException` message from Area 2's error line to a
  new instruction band in Area 3.

**Out, deliberately:**

- The progress heatmap, and the cross-repo `acq4_automation.Cell` expansion it
  forces (§10's "or an explicit decision not to" is still undecided).
- The pinned-frames *workflow* — clear-to-start, operator instructions, and
  waiting until a fresh set is pinned. Only display lands here.
- Slice disk persistence via `DirHandle.setInfo()`.
- Live camera video in the Area 1 view.
- Editable ROIs in the Camera window. The mirror is one-way.

## 3. Components

### 3.1 `acq4/modules/Autopatch/region_panel.py` — `RegionPanel`

Owns the view and every control that makes or changes a region:

- `pg.GraphicsView` with a `pg.ViewBox`, `setAspectLocked(True)` and autorange
  off — the same construction `CameraWindow.__init__` uses, deliberately a
  *separate* view rather than the Camera module's own.
- A shape selector: Rectangle, Ellipse, Polygon. Item **data** (`"rect"`,
  `"ellipse"`, `"polygon"`), not display text, following the precedent
  `SearchPanel.regionShape()` set.
- "Add region here" — the existing one-click 3×3-field seed, unchanged in
  behaviour, relocated, and now producing a visible ROI in all three shapes.
- "Mirror to Camera" checkbox.
- "Fit to regions" — autorange the view over the regions and pinned frames.

Emits `sigRegionsChanged(list)` carrying the complete region list after any
edit, and `sigAddRegionRequested()` for the seed button (the panel does not know
where the camera is; its owner does).

The panel does not import `Slice` and holds no reference to one. It renders a
list of regions and reports a list of regions; `AutopatchWindow` is what binds
that to the current slice. This is what keeps it testable without a slice, a
camera, or an orchestrator.

### 3.2 Shape ↔ ROI adapters

Pure functions in the same module, no Qt state of their own:

| region | ROI |
|---|---|
| `RectRegion` | `pg.RectROI` |
| `EllipseRegion` | `pg.EllipseROI` |
| `PolygonRegion` | `pg.PolyLineROI(closed=True)` |

`roiForRegion(region) -> pg.ROI` and `regionForRoi(roi) -> SearchRegion`.

The ROIs are pyqtgraph's own, used as shipped: their handles resize them, their
`removable=True` context menu deletes them, and `PolyLineROI.segmentClicked`
inserts a vertex where an edge is clicked while individual handles can be
removed. Reshaping a region to follow a cortical layer therefore costs no code.

Three hazards the adapters own:

- **An ROI dragged past its own origin reports a negative size.**
  `AutomationDebug`'s `SurveyRegion._bounds` documents this already.
  `regionForRoi` normalises so `x0 <= x1` and `y0 <= y1` before constructing.
- **A polygon ROI carries its vertices in local coordinates.** They are mapped
  through the ROI's transform to global metres before `PolygonRegion` sees them.
- **An ROI can be dragged to a shape that is not a region.** `regionForRoi`
  returns `None` there rather than letting `SearchRegion`'s validation raise; see
  §8.

### 3.2.1 The one stock tool that is not adequate

`pg.EllipseROI` ships a **rotate** handle. `EllipseRegion` is the ellipse
inscribed in an axis-aligned box, so a rotated ROI maps back to a region with
the rotation silently dropped — the operator outlines one patch of tissue and
the survey tiles another. The Camera module's `ROIPlotter._addEllipseROI` uses
the stock class quite correctly, because it only reads the pixels under the ROI
and a rotation changes which pixels those are; here the shape has to survive a
round trip through a representation that cannot express rotation. So the handle
is dropped, and nothing else about any ROI is modified.

### 3.3 `PinnedFrameMirror` — Camera to Autopatch

A `pg.ImageItem` belongs to exactly one `QGraphicsScene`, so "pinned frames
display in both places" (§7) cannot mean the same object in two views. The
mirror builds its own `ImageItem` per pinned frame from the same image array and
the same global `QTransform`, preserving relative z-order, and rebuilds when the
Camera module's set changes.

### 3.4 `CameraMirror` — Autopatch to Camera

One read-only `QGraphicsPathItem` per region, added through
`cameraWindow.addItem(item, z=...)` with `setAcceptedMouseButtons(Qt.Qt.NoButton)`
(the idiom acq4 already uses, e.g. `analysis/atlas/AuditoryCortex/CortexROI.py`).
A path item rather than an ROI is what makes it read-only structurally rather
than by policy: there is no handle to grab and no second copy of the region's
state to reconcile.

Absence of a Camera window is normal, not an error — the checkbox is a display
preference, and unchecking it or closing the Camera window removes the items.

## 4. The one shared-file change

`ImagingCtrl.pinnedFrames` is a plain list mutated by `addPinnedFrame` and
`removePinnedFrame` with no notification of any kind
(`acq4/util/imaging/imaging_ctrl.py`). Mirroring requires knowing when it
changes, so `ImagingCtrl` gains an additive `sigPinnedFramesChanged` emitted from
both mutators. The Camera module is unaffected. Polling is the only alternative,
and for a set that changes on operator clicks it is the wrong mechanism.

## 5. Authority, and the threading rule

`Slice` remains authoritative for regions. `RegionPanel` is a view over them.

`Slice` gains `setRegions(regions)`, which **rebinds** `self._regions` to a new
list rather than mutating the existing one. `addRegion` keeps its signature and
is reimplemented on top of the swap. Readers — `tileGrid()`, `forceRescan()` —
snapshot `self._regions` into a local before iterating.

This matters because `CellProducer` reaches `slice.nextTile()` -> `tileGrid()` on
the **worker thread** while ROI edits arrive on the **GUI thread**, and
`tileGrid()` iterates `self._regions` directly. Appending to a list under
iteration is undefined in exactly the way that produces an intermittent, unloggable
wrong answer. The swap makes a reader see either the whole old list or the whole
new one, which is the same "make it one step" discipline `Orchestrator._refillQueue`
already applies to the producer reference.

### 5.1 When editing is allowed

Region editing is enabled when:

    not runLocked or status == "paused"

`runLocked` is `StatusPanel.sigInteractionLocked`, already wired to Areas 2, 4,
and 5. The paused exception is keyed on the **emitted status**, never on the
operator having clicked Pause, and the distinction is load-bearing:

- `_checkPause()` runs at the *top* of `_runLoopBody`, before `_shouldRefill()`.
  Clicking Pause during a survey therefore does not stop the survey — the
  producer goes on imaging tiles for seconds to minutes, reading regions the
  whole time, and the loop only parks at the next iteration.
- But `sigStatus("paused")` is emitted from *inside* `_checkPause`, immediately
  before `_pauseEvent.wait()`. While that status is current the worker is
  blocked there and provably cannot be inside `_refillQueue`.

So the status is a real guarantee where the click is not. `_processCell`'s retry
loop calls `_checkPause()` too, and the same reasoning holds: blocked there is
still not inside a refill.

The atomic swap in §5 is not made redundant by this gate. An edit committed as
the operator presses Resume is still concurrent, and belt-and-braces here costs
three lines.

## 6. Interaction

**Creating: seed, then shape.** Choose a shape and press "Add region here"; an
ROI of that shape appears covering roughly 3×3 fields around the camera centre,
and the operator drags it into place. This is the pattern acq4 already uses for
adding an ROI to a camera-style view — `ROIPlotter._addRectROI`,
`_addEllipseROI`, and `_addPolygonROI` in `modules/Camera/CameraWindow.py` each
seed a default-sized ROI at the view centre and leave shaping to the operator.

Drag-to-draw was considered and rejected on evidence: pyqtgraph offers no
drag-out-a-new-ROI gesture (`ViewBox.RectMode`'s rubber band is a zoom tool, and
there is no ROI-creation helper anywhere in the package), and no other acq4
module has one. Building it would mean custom `mouseDragEvent`/`mouseClickEvent`
handling to invent an idiom that exists nowhere else in the application.

**Editing.** Every region is a live ROI: drag the body to move, handles to
resize, `PolyLineROI`'s segment click to insert a vertex and its handle menu to
remove one, and `removable=True` for pyqtgraph's own right-click Remove. All of
it is stock behaviour. Any of these rebuilds the region list and hands the whole
list to the window.

**Deleting leaves coverage alone.** `Slice._covered` is a flat record of tile
centres already imaged, and it is deliberately not pruned when a region goes
away: tiles that no longer fall in any region simply stop being planned, and a
region redrawn over ground already surveyed should still count as surveyed.
That is the same reasoning that makes coverage shared across producers (§6b).

**Committing.** On `sigRegionChangeFinished`, not on every mouse move. A drag in
progress is not a decision, and `tileGrid()` is O(tiles) per call.

**Seeding.** "Add region here" behaves exactly as it does today, including
creating a slice on demand when none exists — the path that deliberately creates
no directory (§7 Area 1). With Polygon selected it seeds the four corners of the
same box, so the button places a region of a known size whichever shape is
chosen, and a four-vertex seed is the readiest thing to reshape into the outline
actually wanted.

**Sizing.** The Area 1 view must be usable at slice scale, which the current
fixed two-column `QVBoxLayout` will not give it. The left column becomes a
vertical `QSplitter` so Area 1 can be dragged large, the outer layout gives the
left column the greater stretch, the view takes an expanding size policy with a
sensible minimum, and "Fit to regions" exists so recovering a sane viewport is
one click. The `ViewBox` supplies mouse zoom and pan for free.

## 7. New slice, and the instruction band

`newSlice()` currently reports `create_data_dir`'s `HelpfulException` — in
practice "Storage directory has not been set." — through
`searchPanel.setError()`, with a comment saying Area 3's band does not exist yet.
It does now.

`StatusPanel` gains `setInstruction(text)` / `clearInstruction()`, rendering in
the existing band. An instruction is not a `RunErrorRecord`: no traceback, no
Copy, no Show in log. It is cleared by the next successful New slice.

A new slice clears the panel's regions along with everything else, because the
new `Slice` has none.

## 8. Errors and degenerate input

Nothing in this panel raises on the GUI thread. Following the precedent of
`SearchPanel.constraints()` returning `None` rather than throwing while an
operator drags a spin box through invalid values:

- No camera: the existing SearchPanel message stands.
- No slice: drawing controls greyed, matching Area 2's `setSliceReady`.
- Degenerate geometry — an ROI squashed to zero extent in either axis, a polygon
  whose handles have been dragged collinear. `SearchRegion` raises on these, and
  an ROI can be dragged there, so `regionForRoi` returns `None` rather than
  propagating: the ROI stays on screen for the operator to pull back out, and
  contributes no tiles while it is degenerate. This follows
  `SearchPanel.constraints()`, which returns `None` for the same reason — an
  operator dragging a control through invalid intermediate values must not get a
  traceback.
- Camera window absent or closed while mirroring: the mirror becomes a no-op.

## 9. Testing

- **Adapter round-trips, headless**, with **asymmetric fixtures**. P2c-1's
  swapped `rx`/`ry` mutant survived all 324 experiment tests because every
  ellipse fixture used a square bounding box. Every shape test here uses
  distinct width and height, and at real SI magnitudes.
- **Negative-size and past-origin drags** get their own cases.
- **The edit gate gets a test per side** — locked while running, editable while
  paused. P2b established that a one-sided test on a two-sided invariant passes
  happily while the other side is broken.
- **The atomic swap gets a mutation proof**: restore in-place `append`, and the
  concurrent-iteration test must fail. Record the failing line number, not just
  that it failed.
- **Mirror lifetime**: `sigPinnedFramesChanged` and the Camera items must be
  disconnected and removed on `teardown()`, proven with the weakref/`gc.disable`
  pattern already in `tests/test_teardown.py`. Connections outliving their owner
  is this module's most-repeated defect.
- Panel tests follow `tests/test_search_panel.py`; `SearchPanel`'s tests lose
  their `regionShape` coverage to `RegionPanel`'s.

## 10. Open, and deferred on purpose

- **The heatmap's cross-repo dependency** is untouched here and still needs an
  owner decision.
- **Drawing in a panel may prove cramped.** The mitigations in §6 are layout
  ones. If they are not enough in practice, the fallback is moving drawing into
  the Camera window — which is why the Camera mirror is a display concern with
  no state of its own, and why `RegionPanel` renders a region list rather than
  owning a slice. Neither decision has to be revisited to make that move.
