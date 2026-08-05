# Autopatch P2c-2 — Tissue-motion feedback loop & the New-slice data directory

Date: 2026-08-05
Status: approved, not yet implemented
Predecessor: P2c-1 region shapes (merged, `4a3c82e0b`)

Two independent pieces of P2c, sharing no code. They travel together because
both are narrow and both are headless-testable.

- **Piece A** — the tissue-motion feedback loop the main design doc specifies in
  §3.6. Spans two repositories.
- **Piece B** — **New slice** creating a real Data Manager directory (§7 Area 1),
  plus the Area 2 gate that makes the button discoverable.

This spec resolves several points where §3.6 and §7 disagree with the landed
code. Where they disagree, this document wins and the main design doc is
corrected to match.

---

## Piece A — tissue-motion feedback loop

### A.0 What the signal actually means

Three distinct tracking failures exist, and only one of them is tissue motion.

| Condition | Where | Response |
|---|---|---|
| Re-verify finds no features at all | `Cell.initializeTracker` re-verify path | **Tissue-motion recovery.** Reference stacks are useless: the cell has drifted out of reach or died. |
| Re-verify matches, but far away | `CellTracker._validate_movement` | **Adopt the new position and track from there.** If LK can find the features, we know where the cell is. |
| Tracking fails mid-patch (pipette occluding features, etc.) | `Cell._trackingLoop` / ongoing `updatePosition` | **Nothing.** Already only logs a warning; must never trigger a rescan. |

The third row is an invariant, not an accident: it holds today only because
`_trackingLoop` catches broadly and `updatePosition` returns `False` rather than
raising. It is written down here so a later change cannot quietly break it.

**Cell death is expected to be the most common trigger**, not tissue movement.
A significant physical bump ruins the experiment and nothing here detects it;
small drift and tissue swelling are the common motion cases.

### A.1 acq4-automation changes (branch: `main`)

Three additive changes. No existing caller changes behaviour.

**1. `CellTrackingLost(ValueError)`** — a named exception in
`acq4_automation/feature_tracking/`. Subclassing `ValueError` is deliberate:
`AutomationDebug/autopatch.py:319` already catches `ValueError` from
`initializeTracker` and skips the cell, and that must keep working. The named
class is what lets acq4 distinguish this domain condition from an unrelated
`ValueError` out of the tracker stack.

**2. `Cell.initializeTracker`'s re-verify path raises it**, carrying
`self._tracker.last_result.reason_for_failure`. The current
`raise ValueError("Cell moved too much to treat as tracked")` carries no reason,
because `updatePosition` returns a bare bool and the reason is only logged.
Reading `last_result` at the raise site avoids changing that bool return, which
`_trackingLoop` depends on.

The reason is not decoration: the operator is being asked to authorise a
destructive rescan, and "why do we believe the tissue moved" is the entire basis
for their answer.

**3. `validate_movement: bool = True`** threaded through
`Cell.updatePosition` → `CellTracker.track_next_frame` → `_validate_movement`.
The re-verify call in `initializeTracker` passes `False`; every other caller
keeps the default.

Why the guard stays on everywhere else: `_validate_movement` compares against
`_last_position`, which means it measures two different things depending on when
it runs. During ongoing tracking, frames are seconds apart, a large jump is
implausible, and `Cell.sigPositionChanged` drives pipette targets
(`AutomationDebug/feature_tracking.py` wires it straight to
`_updatePipetteTarget`) — there it is a hardware-safety guard. At re-verify,
`_last_position` can be hours stale and legitimate accumulated drift can exceed
the same threshold, which is a false alarm that would trigger a rescan we do not
want.

A blanket removal of the threshold is explicitly rejected.

### A.2 acq4 engine changes

**`TrackingLost(OrchestrationError)`** in `acq4/experiment/exceptions.py`, with
`typeName = "TrackingLost"`.

**`cellfie()`** (`acq4/experiment/actions/device.py`) catches `CellTrackingLost`
from `ctx.cell.initializeTracker(...)` and calls `ctx.tissue_moved(reason)`.
The precedent for translating a library exception at the action boundary is
`find_surface` in the same module.

**`ExecutionContext.tissue_moved(reason)`** — a bound hook, in the same family as
`log`, `on_log_action`, and `next_cell_requested`.

The hook needs the failing cell's position to scope the rescan, and takes only a
`reason`. The cell is bound in by the window's context factory the same way `log`
and `on_log_action` already bind theirs (`partial(hook, cell)`), so the action
calling it needs no knowledge of slices or positions.

> **It never returns normally.** Unbound (headless, tests), it raises
> `TrackingLost` — the catch-all safety net then halts the run, which is the safe
> default. Bound, it ends by raising `AdvanceToNextCell` via `ctx.next_cell()`.

One contract with two implementations, so no caller ever branches on whether a
hook is present. The engine keeps no slice knowledge; the orchestrator holds a
plain callable and cannot do any of this itself.

**`Slice.forceRescan(position, isAttempted)`** (`acq4/experiment/slice.py`):

```
here  = [r for r in self._regions if r.overlapsTile(position, self._fov)]
stale = [t for t in self._covered if any(r.overlapsTile(t, self._fov) for r in here)]
```

Then, for each stale tile, de-register its **never-attempted** cells (via the
existing `cellsNearTile`), and drop the stale tiles from `_covered`.

**`isAttempted` is a caller-supplied predicate, and it has to be.** `Slice._cells`
holds `Cell` objects; attempted-ness is orchestration state that lives in
`CellPanel`, not on the cell and not in the engine's slice. Passing a predicate
keeps `Slice` UI-agnostic and makes the behaviour testable with a plain lambda.

`CellPanel` supplies it, backed by a set it records a cell into the first time
that cell appears in **either** `sigCurrentCell` **or** `sigCellFinished`. Both,
not just the latter: a cell interrupted mid-run has been attempted even though no
terminal status was ever emitted for it, and `retry` is emitted mid-flight without
being terminal. "Has the orchestrator ever started work on this cell" is the
question, which sidesteps re-deriving the terminal-status list that the
reuse-completed-cells spec still owes.

This uses only the existing two-method `SearchRegion` contract (`bounds()` +
`overlapsTile()`). That contract is deliberately narrow and documented as "the
only two questions the tiler asks" — **do not add `contains(point)` to widen it.**

- **`here` empty → no-op.** A hand-seeded cell outside every drawn region has no
  coverage to invalidate; hand-added cells are outside the scanner's
  responsibility.
- **Attempted cells stay registered** at their old positions and keep counting
  toward `CellProducer._isCrowded`. This pushes back on §3.6's "cells already
  patched may be found again" hazard, which the prompt currently only warns about
  — but it is **not a guarantee**: `_isCrowded` compares
  `len(cellsNearTile) / tileVolume` against `max_cell_density`, so a tile holding
  one attempted cell under a permissive cap is still re-imaged and that cell
  re-detected. The mitigation is real but density-dependent, and should not be
  described to the operator as a promise.
- **Never-attempted cells are de-registered**, so their tiles become uncrowded,
  get re-imaged, and the cells are re-detected at their current positions. That
  is the entire point of the rescan.

**Cost, and it belongs in `forceRescan`'s docstring:** region-scoping assumes the
motion is *local*, but tissue motion is global. If the slice genuinely shifted,
finished regions are stale too and we are deliberately not re-imaging them. We
accept a stale-coverage risk in finished regions to avoid re-imaging and
double-patching them. Same family as §3.6's existing "Caveat: the regions are
stale too".

**`Orchestrator.clearProducerExhausted()`** — the `_producerExhausted = False`
assignment extracted out of `setCellProducer`, which now calls it. A producer
that already reported exhaustion must be asked again, or the run ends on the
now-refilled queue.

### A.3 What is deliberately NOT built

**No fresh producer, and no re-arming of `_rescanned`.** §3.6 asks for both.
Both are unnecessary, and §3.6 only asks for them because it assumed
`forceRescan` was slice-wide.

`CellProducer` is stateless apart from `_rescanned`, and calls `slice.nextTile()`
fresh on every call. Un-covering region 3's tiles is therefore sufficient on its
own: the **existing** producer starts handing them out again. Nothing to re-arm,
no generation counter, no slice→producer back-reference — which matters, because
`Slice.makeCellProducer()` deliberately keeps no reference to what it hands back,
to stay refcount-freeable rather than needing the cyclic GC.

This also makes §3.6's "not charged against `rescans_allowed`" literally true
rather than a special case: `_rescanned` is never touched, so the bonus-pass
allowance is neither spent nor refunded. Constructing a fresh producer would have
done the opposite — a fresh `_rescanned = False` re-arms the slice-wide
`resetCoverage()` pass, buying a second full re-survey of every region whenever
`rescans_allowed` is on.

### A.4 The window's hook

Supplied by the Autopatch window through its context factory, since the window is
what owns the `Slice`, the detector, and the orchestrator together.

1. `prompt()` the operator (non-modal and stop-aware; Stop stays available as the
   third answer). "Rescan the slice" is first, and therefore the headless
   default — driving a pipette to a known-stale coordinate is a hardware risk,
   while patching a cell twice is a data-hygiene cost, so the cheaper mistake
   goes first. The message includes the tracker's `reason_for_failure`.
2. On **Rescan the slice**: `slice.forceRescan(cell.position, isAttempted)`,
   `orchestrator.clearQueue()`, `orchestrator.clearProducerExhausted()`. The cell
   comes from the factory binding (A.2); `isAttempted` from `CellPanel`.

   Ordering note: `clearQueue()` runs **after** the operator answers, so a cell
   the operator seeds by hand while the prompt is open is discarded too. Correct
   — it is a coordinate in the same moved tissue — but worth knowing.
3. On **Skip this cell only**: nothing.
4. Both answers end with `ctx.next_cell()`.

**Threading.** The hook runs on the worker thread, mid-cell. Queue and coverage
mutations are single-step rebinds, consistent with the existing deque-atomicity
discipline — no locks, per the check-then-act lessons from P2b. The survey-stats
refresh afterwards is a GUI update and must be marshaled the way coverage updates
already are, not called inline. No producer call can be in flight: refills happen
only between cells with an empty queue, and this runs inside a cell.

### A.5 Corrections to the main design doc

- **§3.6 step 3 is wrong.** "if it is still there, the rescan finds it again as a
  new `Cell`" no longer holds: the lost cell is an attempted cell, so it holds its
  own tile down. Given cell death is the common trigger, not re-finding it is the
  correct behaviour.
- **§3.6's slice-wide `forceRescan()` is superseded** by the region-scoped form.
- **§3.6's `_rescanned` re-arm is superseded** — see A.3.
- **§3.6 does not state the mid-patch invariant** (A.0, third row). It should.

---

## Piece B — New slice creates a Data Manager directory

### B.1 The storage helper

`new_data_dir(ctx, level, set_current)` in `acq4/experiment/actions/storage.py`
already performs exactly the `DataManagerModule.createNewFolder` logic — but it
takes a `ctx`, and **New slice** is an operator click with no run in progress.

Factor its body into **`create_data_dir(manager, level="Cell", set_current=True)`**
in the same module; `new_data_dir` becomes its `ctx.log_action()` wrapper. Both
callers share one implementation. A UI button must not fabricate an execution
context to reach engine logic.

Setting the current directory is load-bearing, not a courtesy: a protocol's own
`new_data_dir(ctx, level="Cell")` picks its parent by walking up from the current
directory, so per-cell data lands under this slice *because* New slice made it
current.

### B.2 `newSlice()` ordering

**Create the directory first.** On failure, nothing is discarded — no cells
cleared, no queue cleared, `self.slice` left exactly as it was. This matches the
discipline `_startSlice()` already establishes for a missing camera or invalid
constraints.

Only on success does `newSlice()` proceed to its existing behaviour: clear the
cell list, detach the producer, clear the queue.

`Slice` gains **`dirHandle`**, set at construction. Slice-scoped state, and the
handle §6b's `setInfo()`/`info()` persistence will need later.

**Directory creation lives in `newSlice()` only, not `_startSlice()`.** The other
caller is `addRegionHere()`, and a button labelled "add region" must not silently
create a directory on disk and repoint where every subsequent write lands. A
`Slice` born from `addRegionHere()` has `dirHandle = None`, which honestly
represents "this tissue was never formally started" — and is not a new hole, since
an operator who never pressed New slice is already writing into whatever the
current directory happens to be.

### B.3 Area 2 gates on a slice existing

Because `dirHandle = None` is reachable only by skipping New slice, the UI should
say so: **Area 2's controls are locked until a slice exists.**

`SearchPanel` currently has one writer for its lock —
`statusPanel.sigInteractionLocked`, wired directly. Adding "no slice yet" as a
second reason puts two writers on one boolean, and a run finishing would unlock a
panel with no slice behind it.

So `SearchPanel` holds the two reasons **separately** and derives the effective
lock (`locked or not sliceReady`). The existing signal wire is untouched; the new
state gets its own setter.

Two consequences:

- **Constraints are read at creation time.** `_startSlice()` builds the `Slice`
  from `searchPanel.constraints()`, but Area 2 is locked until New slice — so the
  slice is born with defaults and the operator's edits land afterwards through
  `_onConstraintsChanged`. Verify that handler pushes onto the live slice rather
  than only being read at build time.
- **Start stays unlocked.** Running a protocol over hand-seeded cells with no
  slice is legitimate work; it is the *producer* that needs a slice, not the
  orchestrator. Blocking Start would forbid something real.

### B.4 Decisions taken

- **No confirmation prompt on New slice.** The button is destructive by design and
  is about to become the mandatory first click of every session; friction there is
  friction on the common path. This resolves §7's open decision as "no prompt".
- **New slice does not stop a running orchestrator.** It detaches the producer and
  clears the queue, but the in-flight cell runs to completion: yanking a pipette
  out mid-protocol is its own hazard. Stop remains the operator's tool for that.
  Unchanged from the landed code, restated because it was questioned.

### B.5 Error handling

`manager.getCurrentDir()` raises
`HelpfulException("Storage directory has not been set.")` when the operator has
not chosen one — the likeliest first-use failure of this button.

§5.1's Area 3 instruction band is phased P3 and unbuilt, so this surfaces through
**`searchPanel.setError()`**, the existing Area 1/2 error channel already used for
"Select a camera before starting a slice."

---

## Testing

Headless throughout. `tile_detector.py`'s injected-detector seam is the precedent
for the device-facing parts.

**Piece A**

- `forceRescan`: region-scoped un-covering; attempted cells retained in the
  density record; never-attempted cells de-registered; the empty-`here` no-op;
  overlapping regions. Driven by a lambda `isAttempted`, no UI involved.
- `CellPanel`'s attempted set: a cell seen only via `sigCurrentCell` (interrupted,
  never finished) counts as attempted.
- **At a realistic stage coordinate**, not only at the origin — pure-geometry
  tests written around the origin cannot see coordinate-magnitude float error.
- `tissue_moved`: raises `TrackingLost` unbound; raises `AdvanceToNextCell` bound,
  on **both** prompt answers; rescan side effects occur on one answer and not the
  other.
- `cellfie` translates `CellTrackingLost` and lets unrelated `ValueError`s
  propagate untouched.
- `clearProducerExhausted` lets an exhausted producer be asked again.
- acq4-automation: `validate_movement=False` suppresses the jump guard;
  the default keeps it; `CellTrackingLost` is caught by `except ValueError`.

**Piece B**

- `create_data_dir` called with no `ctx`; `new_data_dir` behaves identically
  through the wrapper.
- `newSlice` with a failing directory creation leaves slice, cells, and queue
  untouched.
- The `SearchPanel` lock at **all four corners** of (run-locked × slice-ready),
  not just the two obvious ones.

**Mutation-test the absence-assertions.** The de-registration test and the
"nothing discarded on failure" test both assert a negative and would pass against
broken code if the fixture cannot reach the distinguishing state. Proof required:
remove the fix or apply the defect, observe the test fail, then restore. This has
caught vacuous tests three times in this project.

Also: no symmetric fixtures where an asymmetric mapping is under test — the
region/tile fixtures must not be square, per the `EllipseRegion` `rx`/`ry` finding.

---

## Out of scope

- Slice persistence via `DirHandle.setInfo()` (§6b — "not required for a first cut").
- Area 1 ROI graphics, the mirror-to-Camera checkbox, the progress heatmap, and
  the cross-repo `acq4_automation.Cell` expansion the heatmap would force.
- §5.1's error surfacing (captured traceback, Area 5 error block, log link).
- Reuse-completed-cells. §3.6's "Open" note — whether reuse should be blocked or
  warned after a motion event — **stays open**, because reuse does not exist yet.
