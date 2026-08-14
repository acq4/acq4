# Autopatch P2c-3b — Area 1 progress overlay

Design for the second slice of Area 1: cell markers and survey coverage drawn
into the Area 1 view built by P2c-3a, coloured by a switchable source, and
navigable in both directions with Area 5's cell list.

Parent design: `autopatch-orchestration-design.md` §6, §7 Area 1, §10 (P2).
Predecessor: `2026-08-10-autopatch-area1-region-graphics-design.md`.

---

## 1. Why this exists

Area 1 can now draw and shape search regions over the Camera module's pinned
frames, but it shows nothing about what happened in them. The operator's most
likely mistake is a *spatial* one — a region drawn too close to a harp string,
or off the edge of the tissue — and the flat cell list in Area 5 cannot reveal
it. Failures clustering in one corner of a region is exactly the signal that
says "this ground is dead, redraw it", and the control that acts on it is
already in the same view.

That closes a loop: draw regions, survey, see where it went wrong, redraw.

## 2. Resolving §6's deferred `Cell` expansion

§10 makes the progress heatmap the consumer that forces §6's deferred
`acq4_automation.Cell` expansion, "or an explicit decision not to". Neither
answer is right, because §6's premise does not hold.

§6 warns that expansion "would put orchestration state on a cross-repo `QObject`
with three writers (engine, panel, heatmap)". Measured against the code:

- **The overlay is a reader and never a writer.** Three writers become two.
- **The detection score is already on `Cell`.** `_build_cells` sets
  `cell.score = score` (`acq4/experiment/tile_detector.py:83`) as an undeclared
  dynamic attribute, and `CellProducer._isHealthy` reads it back defensively
  with `getattr` (`acq4/experiment/cell_producer.py:118`). One writer, at
  detection, never mutated afterwards.
- **The mutable multi-writer state is already elsewhere and already public.**
  Disposition lives in `CellPanel._status` behind `CellPanel.disposition(cell)`.

So the split is not "orchestration state: on `Cell` or not". It is **by
mutability and provenance**:

| Datum | Owner | Writers | Status |
|---|---|---|---|
| position | `Cell` | tracker | already there |
| detection score | `Cell` | detector, once at birth | already there, **undeclared** |
| disposition | `CellPanel._status` | engine + panel | already there, public |
| coverage | `Slice._covered` | producer | already there, public |
| density | derived from positions | none | free |

A detection score is **provenance** — an immutable fact about how the cell was
found — not orchestration state. §6's objection is defused rather than
overridden, and disposition deliberately does **not** move: `CellPanel`'s
id-keyed, no-strong-references discipline exists because reference cycles are
this module's most-repeated defect, and `tests/test_teardown.py` guards it.

**The decision: declare `score` on `Cell`; move nothing else.**

The alternative of reading `score` with `getattr` and touching no other
repository was rejected: it would leave a load-bearing field undeclared with a
second consumer depending on it, undiscoverable to anyone reading `Cell`. A
third `SliceProgress` read-model joining the sources was also rejected — every
datum above already has exactly one owner and a public accessor, so a joining
object would be a fourth store whose only job is going stale.

## 3. Scope

**In:**

- Cell markers in the Area 1 view, coloured by a switchable source.
- Three colour sources: survey `success`, detection `health`, local `density`.
- Coverage shading showing which planned tissue is still unsurveyed.
- A colour-source selector with a legend.
- Two-way navigation with Area 5: click a marker to select that cell, and a
  "Zoom to cell" button framing Area 1 on the selected one.
- `Cell.score` declared in `acq4_automation`.
- `CellPanel.cells()`, `CellPanel.selectCell()`, `CellPanel.sigCellStateChanged`.

**Out, deliberately:**

- **Time-, pipette-, and depth-based breakdowns of success.** Disambiguating
  whether a run of failures was the tissue, the hour, or the pipette is a
  post-experiment analysis question, not an at-a-glance one.
- **Assigned protocol per cell.** Recorded nowhere today; it is the field §6's
  expansion would have had us invent, and no colour source needs it.
- Editable markers. The overlay is read-only; regions are the editable thing.
- Per-cell z display. This is a plan view; depth is a colour source at most.
- Slice disk persistence, and the pinned-frames workflow. Both still open from
  P2c-3a's §2.

## 4. Components

### 4.1 `acq4/modules/Autopatch/progress_overlay.py` — `ProgressOverlay`

Owns a `pg.ScatterPlotItem` of cell markers and a coverage layer, added into a
`pg.ViewBox` handed to it. It renders a list of `(position, brush, cellId)` and
a list of tile centres, and holds no `Slice`, no `CellPanel`, no orchestrator
and no cells.

This is the same relationship `PinnedFrameMirror` already has to that view, and
it is deliberate: `RegionPanel._mirroredImageryBounds` documents that the panel
"renders regions and knows nothing about what else is put in its view", and
refuses a back-reference to the mirror for a bounding box. `RegionPanel` learns
nothing about cells here either.

Markers use `pxMode=True`, against the precedent of acq4's two other scatters
(`Photostim.py:157`, `ScanCanvasItem.py:61`), which both use `pxMode=False`.
Data-unit markers vanish when the view is zoomed out to a whole slice, and
legibility at slice scale is this overlay's entire purpose.

Point data carries `id(cell)`, **never the cell**, so the scatter does not
become a second store keeping cells alive — the constraint every id-keyed dict
in `cell_panel.py` exists to honour.

### 4.2 Colour sources

Named functions mapping a cell's facts to a brush, plus a legend. Selected
through a combo keyed on item **data**, not display text, following
`SearchPanel.regionShape()`.

**`success`** — from `CellPanel.disposition(cell)`. `CellPanel` already draws a
semantic line this must respect rather than flatten: `COMPLETED = {"done"}`,
with a comment insisting `"error"`/`"retry-exhausted"` are failures while
`"stopped"`/`"skipped"` are abandonment.

| disposition | colour |
|---|---|
| `done` | green |
| `error`, `retry-exhausted` | red |
| `skipped`, `stopped` | amber |
| none, but attempted | blue (in flight) |
| none, never attempted | grey (to-do) |

Amber is load-bearing. Collapsing abandonment into red would make an operator's
own Stop look like dead tissue — precisely the misreading this display exists to
prevent.

**`health`** — `cell.score` through a colormap. A cell with `score is None`
draws hollow, so "never scored" is visibly distinct from "scored badly". Every
manually-added cell is in that category, since only `_build_cells` scores.

The colormap spans `[min_health, 1]`, not `[0, 1]`. `CellProducer._isHealthy`
drops every candidate scoring below `constraints.min_health` before it ever
becomes a queued cell, so no drawn cell can score below the cutoff (default
0.5). A `[0, 1]` ramp would spend half its range on values that cannot occur,
which is the difference between "these cells all look alike" and "this corner
scored worse than that one" — the discrimination this source exists for. With
no slice, and so no cutoff, it falls back to `[0, 1]`.

**`density`** — the number of cells within one tile volume of each cell,
normalised against `constraints.max_cell_density`. Normalising to the
producer's own exhaustion threshold is what stops the display and the engine
disagreeing about what "crowded" means.

Computed from the window's own position cache, **not** by reusing
`Slice.cellsNearTile()`, which reads `cell.position` (§6) and carries the
concurrency hazard described there.

### 4.3 Coverage

The **to-do** tiles are painted, not the covered ones: `tileGrid()` minus
`coveredTiles`. An empty overlay then reads correctly as "fully surveyed",
and what is drawn is the set the operator can act on.

Recomputed only on the coverage triggers in §6, because `tileGrid()` is
O(tiles) per call — the same cost that makes region edits commit on
`sigRegionChangeFinished` rather than on every mouse move.

## 5. The data seam

Authority stays where it is; the overlay is a reader. `AutopatchWindow` does the
join, in a `_refreshProgress()` mirroring the existing `_refreshSurveyStats()`:
pull cells, ask the colour source for a brush each, pull coverage, hand two
lists to the overlay. One direction, no caching in the overlay, no third store.

### 5.1 The one cross-repo change

`Cell.__init__` gains `self.score = None`, documented as the detector's health
prediction in `[0, 1]`, set once at detection, immutable afterwards, and `None`
for a cell that was never scored.

That is the whole change. It declares what `tile_detector.py:83` already sets
and `cell_producer.py:118` already reads.

**It does not, however, let acq4 read `cell.score` plainly**, which an earlier
draft of this section claimed. `CellPanel` is duck-typed — its own tests seed
plain `object()` rows, and nothing constrains a row's payload to be a `Cell` —
so `_colorContext` reads `getattr(c, "score", None)`. The declaration's value is
discoverability for anyone reading `Cell`, not a stronger guarantee at the call
site. Nor does the ordering matter: no acq4 code path depends on the attribute
existing, so the two repositories' changes can land in either order.

### 5.2 `CellPanel`'s new surface

`CellPanel` is the disposition owner, and the overlay must not become a second
one.

- **`cells()`** — the cells it knows about, already held in `self._cells` (the
  strong reference that keeps them alive) with no reader today.

  This is why the overlay reads the panel and not the slice: `CellPanel` is the
  **complete** registry and `Slice` is not. `Slice.registerCells()` has exactly
  one production caller (`cell_producer.py:93`), so every cell from "Add from
  target" and "Scatter fake cells" is absent from the slice. Reading the slice
  would silently omit them.

- **`selectCell(cell)`** — make that cell's row current, for Area 1 → Area 5
  navigation. The panel connects `cellList.currentItemChanged` internally today
  and emits nothing outward.

- **`sigCellStateChanged`** — emitted wherever `_status`, `_rows`, or
  `_attempted` change: `addCell`, `_onCurrentCell`, `_onCellFinished`,
  `_onReuseCheckedCells`, `_onCellsDiscarded`. It carries nothing; it is a
  "re-read me" nudge, following the existing `_refreshSurveyStats()` pull rather
  than pushing state the panel would then hold two copies of.

  **`_onCurrentCell` is the fifth site and was originally missed**, which made
  one of §4.2's five colours unreachable. It sets `_attempted` — the only state
  the in-flight blue keys on — but emitted only through its internal `addCell`
  call, which fires just for a cell that has no row yet. For the ordinary case,
  an already-seeded cell, the orchestrator's announcement changed `_attempted`
  and told nobody, so the marker for the cell being patched right now stayed
  grey ("to do") until some unrelated refresh happened to fire — and often until
  the cell finished and recoloured green, red, or amber. A colour the design
  promises must have a path that reaches the screen; the emit sites are that
  path, so any writer of state a colour reads belongs in this list.

  The resulting double emit on the no-row path is accepted rather than guarded:
  the signal is a payload-free nudge, so a duplicate costs one redundant redraw
  and `_onCellFinished` already has the same shape.

## 6. Refresh, threading, and the position read

Every refresh lands on the GUI thread.

| Trigger | Refreshes | Precedent |
|---|---|---|
| run status → `surveying`/`waiting` | coverage | `_onRunStatus`, verbatim |
| `CellPanel.sigCellStateChanged` | markers | new |
| `Cell.sigPositionChanged` | that marker | exists |
| colour-source selector | markers | — |
| New slice | clears both | existing teardown path |

### 6.1 Never call `Cell.position` from the overlay path

`Cell.position` evaluates `max(self._positions)`, which iterates that dict,
while the tracking worker inserts `self._positions[ptime.time()] = ...`
(`cell.py:239`). A GUI-thread read concurrent with that insert raises
`RuntimeError: dictionary changed size during iteration`. So:

- **First placement** reads `cell.initialPosition` — assigned once in
  `__init__` and never mutated, safe from any thread.
- **Updates** come from `sigPositionChanged`, which already carries the new
  global position as its payload (`cell.py:240`). The window caches that
  payload keyed by `id(cell)` and never touches `_positions`.

The signal makes the safe path also the cheap one, which is what keeps the
cross-repo diff at the single declared `score` with no thread-safety change to
`Cell`.

`Slice.cellsNearTile()` has the same unsafe read from the producer's worker
thread (`slice.py:333`). It is pre-existing, out of scope here, and filed
separately; §4.2 routes around it rather than depending on it.

### 6.2 Lifetime

Connections outliving their owner is this module's most-repeated defect, and
P2c-3a found a mandated mutation that **did not fail** because a nearby
`= None` had already broken the cycle refcounting could see. So:

- The window disconnects every `sigPositionChanged` it made — on `teardown()`,
  on New slice, and on `sigCellsDiscarded`.
- The position cache is cleared alongside, since `id()` keys are only safe
  while `CellPanel._cells` holds the referents alive.
- Tests assert Qt's own **`receivers(signal)` going N → 0**, not merely that an
  object was collectable.

Connection volume is one per known cell; in practice only a tracked cell emits,
and only the cell being patched tracks, so most never fire. If it proves heavy
the fallback is connecting on `sigCurrentCell` alone. Not pre-optimised.

## 7. Navigation

**Area 5 → Area 1.** A "Zoom to cell" button frames Area 1 on the selected
cell through the already-built `RegionPanel.setViewport(center, span)`, with a
span of 3×3 fields of view — the same 3×3-field size "Add region here" seeds,
so the two controls agree on what "around here" means.

**Area 1 → Area 5.** `ScatterPlotItem.sigClicked` gives the clicked points;
their data carries `id(cell)`, which the window maps back through `CellPanel`
to call `selectCell(cell)`.

## 8. Framing

Adding the scatter to the view enrolls the markers in `fitToRegions()`
automatically, because `_mirroredImageryBounds` frames everything in the view
that is not a region ROI. **The scatter must therefore be excluded from that
union, and the reasoning that said otherwise was wrong.**

The argument that failed: cell positions come from tiles in `tileGrid()`, which
only yields tiles inside regions, so every cell sits within the regions plus
half a field of overhang — well inside the 10% padding `fitToRegions` applies.
That is true of a marker's *position* and irrelevant to its *bounding rect*.
With `pxMode=True` the markers keep a constant pixel size, so
`ScatterPlotItem.boundingRect()` carries a pixel halo converted into view units
**at the current zoom** — and the fresh viewport this button exists to recover
from spans about a metre. Measured on a 300 × 200 µm region 1 mm from the
origin: fitting with no markers gives 360 × 270 µm, and fitting with a single
marker gives **27 m × 20 m**, centred near global (0, 0). It converges over
three or four presses, so the inflation is worst in exactly the state
`fitToRegions`' own docstring describes as its reason for existing.

A second failure has the same root: with nothing else in the view, an *empty*
scatter makes `_mirroredImageryBounds` return a **null** `QRectF` rather than
`None`, so `fitToRegions`' `if rect is None: return` guard stops firing and
pressing Fit on an empty Area 1 recentres the view on global (0, 0) instead of
doing nothing.

So the panel does need a way to be told which items frame and which do not —
the `excludeFromFraming` registration this section originally rejected — plus a
null-rect check. The panel still learns nothing about *what* the excluded item
is, which is what keeps §4.1's ignorance intact.

Every pre-existing fit test builds a bare `RegionPanel`, which has no overlay,
so none of them can observe either defect; the window-level test §10 mandates
is the only thing that can.

## 9. Errors and degenerate input

Nothing here raises on the GUI thread, following
`SearchPanel.constraints()`'s precedent.

- **No slice** — no coverage to draw, and no `SearchConstraints`, so `density`
  falls back to a raw count scale and `health` to a `[0, 1]` ramp, each saying
  so in the legend. Markers still draw: manually-added cells exist before any
  slice does.

  Note that `max_cell_density` and `min_health` are never absent *given* a
  slice — both are dataclass fields with defaults, and `__post_init__` rejects a
  non-positive density and an out-of-range health outright. The missing slice is
  the only case to handle, not a missing field.
- **No cells** — an empty scatter, not a hidden one, so the legend stays
  meaningful.
- **`score is None`** — hollow marker, never an exception (§4.2).
- **A `score` outside `[min_health, 1]`** — clamped for colouring, never
  raising. Nothing in the queued path can produce one, so this is a guard
  against a future detector, not a case that occurs today.
- **A cell with no cached position** — skipped for that refresh. It gains one on
  its next `sigPositionChanged`.

## 10. Testing

- **Colour sources headless**, with **asymmetric fixtures at real SI
  magnitudes**. P2c-1's swapped `rx`/`ry` mutant survived all 324 experiment
  tests because every ellipse fixture used a square bounding box.
- **A case per disposition** — all five terminal values, plus attempted-but-
  unfinished and never-attempted. A one-sided test on a multi-valued mapping
  passes happily while a branch is wrong.
- **`density` normalisation** against a known `max_cell_density`, and the raw
  count fallback with no slice.
- **The `health` ramp is anchored at `min_health`, not 0.** Two cells scoring
  0.6 and 0.9 against a 0.5 cutoff must get visibly different brushes; a `[0, 1]`
  ramp is the mutant this test kills, and it is one a reader would not suspect
  because both values are legal `[0, 1]` scores. Includes the `[0, 1]` fallback
  with no slice, so the two ranges cannot be conflated.
- **The registry choice gets a test**: a manually-added cell (absent from
  `Slice._cells`) must still get a marker. This is the defect reading the slice
  instead of the panel would cause.
- **`fitToRegions` union unchanged** with markers present.
- **Teardown** asserts `receivers(signal)` N → 0 for every
  `sigPositionChanged` the window connected, with the weakref/`gc.disable`
  pattern in `tests/test_teardown.py`.
- **The position path gets a concurrency test**: markers refresh while a fake
  tracker writes `_positions`, proving the overlay path never iterates it.
- Panel tests follow `tests/test_region_panel.py`.
- Every task carries a mutation proof recording the line the failure landed on.

## 11. Open, and deferred on purpose

- **Still open for Area 1** from P2c-3a: the pinned-frames *workflow*
  (clear-to-start, instruct, wait for a fresh set), and slice disk persistence
  via `DirHandle.setInfo()`.
- **The live GUI smoke test needs a human at a screen** — markers over real
  tissue, the colour sources legible at slice scale, and both navigation
  directions. P2c-3a shipped unverified against the rig and this will too.
- **`pxMode=True` is a legibility bet.** If markers prove too coarse when
  zoomed in to a single field, the fallback is a size that scales between
  bounds rather than switching to data units.
