# Autopatch Area 1 — the pinned-frames workflow

Design agreed 2026-08-14. The last unbuilt piece of Area 1: sequencing the
Camera module's pinned frames into the start of a slice, so that the regions an
operator draws are drawn over imagery of the tissue actually under the
objective.

## 1. What this builds, and what it does not

The design doc's §7 Area 1 says imaging is manual in v1: reference imagery is
the Camera module's pinned frames, and Autopatch "optionally **clears pinned
frames** to start, gives the operator **clear instructions**, and **waits until
a fresh set is pinned**."

P2c-3a built the display half — `PinnedFrameMirror` shows those frames in Area
1's view, bound at `_startSlice`. This builds the workflow half:

- **Clearing** the previous slice's frames, behind a confirmation prompt.
- **Instructing** the operator to pin a fresh set, in Area 3's band.
- **Opening** the Camera module if it is not already open, so there is
  somewhere to pin them.

**The "wait" is advisory.** No control is disabled and no run is blocked.
Nothing gates on reference imagery existing; the band says what to do and the
operator decides. This was chosen over gating region drawing and over gating
Start, both of which were on the table.

Out of scope: slice disk persistence via `DirHandle.setInfo()`, the progress
heatmap's remaining cross-repo work, and the live GUI smoke test — all still
open, none of them this.

## 2. `ReferenceImagery`

New file `acq4/modules/Autopatch/reference_imagery.py`.

```python
ReferenceImagery(imagingCtrlGetter, moduleOpener, prompt=None)
```

A `QObject`, unlike the plain `PinnedFrameMirror`/`CameraMirror` classes beside
it, because something listens to it: the band has to re-render when the pinned
set changes. `ProgressOverlay` is a `QObject` for the same reason.

### Surface

| Member | Meaning |
| --- | --- |
| `beginSlice()` | New slice's entry point: open the module, resolve, prompt-and-clear, recompute. |
| `rebind()` | Re-resolve the source, swap the subscription, recompute. |
| `instruction() -> str` | The guidance this component wants shown; `""` for none. |
| `sigInstructionChanged` | Emitted **only when `instruction()` changes value**. |
| `release()` | Disconnect and forget the source. Teardown's call. |

### The three injected seams

Injection is what makes this headless-testable, the same choice P2b made for
the tile detector.

- **`imagingCtrlGetter() -> imagingCtrl | None`** resolves the Camera module's
  `ImagingCtrl` for the selected camera, exactly as `_bindPinnedFrames` does
  today (`window.getInterfaceForDevice(camera.name()).imagingCtrl`, with
  `KeyError`/`AttributeError` meaning "none").
- **`moduleOpener() -> None`** opens the Camera module. This is a deliberate
  `manager.getModule("Camera")` — a *load*, not a lookup. It must **not** go
  through `_cameraModuleWindow`, whose `listModules()` guard exists precisely so
  that a mirror redraw (including the one behind "Add region here") cannot start
  a module as a side effect. Two callers wanting opposite behaviour is why they
  stay two code paths.
- **`prompt(text) -> bool`** defaults to a `QMessageBox.question`, mirroring
  `ImagingCtrl.clearPinnedFramesClicked`'s own confirmation. Injected so no
  headless test can open a modal.

### Why not extend `PinnedFrameMirror`

It already binds the `ImagingCtrl` and knows the frame count, so the
subscription is half-built there. But its docstring stakes out "display only:
it holds no region state and nothing depends on it existing", and that property
is what makes it safe to bind and unbind at will. A modal prompt and a workflow
gate hanging off it would take that away. `ReferenceImagery` subscribes to
`sigPinnedFramesChanged` independently instead; two subscribers to one signal
costs nothing and keeps both classes single-purpose.

## 3. The New slice sequence

`beginSlice()` is called **last** in `AutopatchWindow.newSlice()` — after
`_startSlice()`, after `cellPanel.clearCells()`, after the band clears, after
the orchestrator detach/`clearQueue()`/`abandonCellInHand()`, and after
`_refreshSurveyStats()`.

**This ordering is load-bearing.** The prompt is modal; a modal dialog re-enters
the Qt event loop; every queued slot dispatches inside it. That includes
`_onModulesChanged` announcing the module we just opened, and any
`sigCellFinished` queued from the cell still in flight on the discarded tissue.
Running the prompt last means no half-completed New slice is ever observable
from inside a nested event loop. This project has been bitten repeatedly by a
queued signal landing mid-transaction; opening a nested loop in the middle of
one invites the same class of defect.

Inside `beginSlice()`, in order:

1. `moduleOpener()`.
2. `rebind()` — resolve the `ImagingCtrl`, subscribe to
   `sigPinnedFramesChanged`.
3. If the source resolved and its `pinnedFrames` is non-empty, `prompt(...)`;
   on a Yes, `source.clearPinnedFrames()`.
4. Recompute the instruction and emit if it changed.

**Declining does not abort New slice.** The slice is already built by the time
this runs; the prompt is about frames alone. **Zero pinned frames means no
prompt at all** — there is nothing to confirm.

`_tornDown` already blocks this path: `newSlice()` returns early from
`_canStartSlice()`, so `beginSlice()` is never reached on a torn-down window.

## 4. The instruction, and named slots in `StatusPanel`

Area 3's band currently holds one instruction string, with a `_regionInstruction`
bool on the window answering "may I retract what is up?". A third writer makes
that a three-way ownership problem — the "state outliving what it belongs to"
shape that has cost this project five review rounds elsewhere. Replace it with
slots.

```python
StatusPanel.setInstruction(source: str, text: str)   # "" clears that slot only
StatusPanel.instruction() -> str                     # unchanged meaning
```

Priority is a module-level constant; the first non-empty slot renders:

| Rank | Source | Message | Why here |
| --- | --- | --- | --- |
| 1 | `storage` | `str(HelpfulException)` — "Storage directory has not been set." | New slice could not complete at all. |
| 2 | `imagery` | "Pin reference frames of this slice in the Camera module." | The slice exists but has no reference imagery. |
| 3 | `mirror` | "Mirror to Camera: no Camera module is open. The outlines will appear if one is opened." | A display preference. |

A `RunErrorRecord` still outranks all three, unchanged: a failure that halted a
run is about tissue and a pipette in it, and guidance about a button is not.

`instruction()` keeps returning *the text now showing*, so the existing test
reads are unaffected. The four production `setInstruction`/`clearInstruction`
call sites and the `setInstruction` calls in `test_status_panel.py` take the
source argument. `_regionInstruction` is deleted: it existed only to answer "may
I retract this?", which slots answer structurally.

**One deliberate behaviour change falls out of this.** `newSlice()`'s success
path today calls `clearInstruction()`, wiping whatever the band held. Under
slots it clears the `storage` slot alone — the one whose condition New slice
has just resolved. The `mirror` slot survives, correctly: New slice does not
change whether a Camera module is open, so retracting that message would have
been a lie. In practice the message goes anyway, because `beginSlice()` opens
the Camera module and `_onModulesChanged` re-runs the mirror handler.

### What `imagery` says, and when

State-driven, not event-driven. The slot's text is a pure function of the
current state, recomputed on every `sigPinnedFramesChanged` and on every
`rebind()`:

- No slice → `""`.
- Slice, source resolved, zero frames pinned → the pin-frames instruction.
- Slice, source resolved, one or more frames pinned → `""`.
- Slice, **no source resolved** → "Open the Camera module to pin reference
  frames for this slice." Now the exception rather than the norm, since
  `beginSlice()` opens it; this covers a rig with no Camera module configured,
  a selected camera the Camera module has no interface for, and a `getModule`
  that raised.

Retracting on the first pin and returning if the operator unpins everything
both fall out of this for free. Deriving the text from state rather than from
an event also dodges the failure the error-surfacing branch measured, where a
band gated on a transient status was shown and hidden inside one run.

## 5. Threading and lifetime

**Single-threaded.** `sigPinnedFramesChanged` is emitted on the GUI thread by
operator clicks in the Camera module. No producer, orchestrator or worker
thread touches any of this, and no cross-thread hazard applies.

`release()` is called from `AutopatchWindow.teardown()` and must tolerate a
source Qt has already destroyed. `Qt.disconnect` (which is `pg.disconnect`)
swallows a dead connection's
`RuntimeError`, but the signal is read off the source *before* it can be handed
over, and that read raises through a wrapper whose C++ object is gone — the
hazard `PinnedFrameMirror.unbind()` documents. A raise here would abandon the
rest of `teardown()`, leaving every other panel wired to an orchestrator that
has just been stopped.

The window also calls `rebind()` wherever it already calls `_bindPinnedFrames`:
`_startSlice()` and `_onModulesChanged()`. The latter is what makes the
"no Camera module" instruction retract by itself when one is opened.

## 6. Testing

### `ReferenceImagery`, headless

Against a fake `ImagingCtrl`: a `QObject` with `sigPinnedFramesChanged`, a
`pinnedFrames` list, and a `clearPinnedFrames()` that **genuinely empties the
list and emits**. An honest fake is not optional here — P2b's `restore_depth`
and `_FakeCamera` defects both survived because the fake agreed with the code
and neither matched the device. A `clearPinnedFrames()` that does not emit
would hide a missing recompute.

Fake opener records its calls; prompt stub is parameterised True/False.

Cases: opener called on `beginSlice`; no prompt when nothing is pinned; prompt
then clear on Yes; prompt then **frames still pinned** on No; instruction
appears at zero frames and retracts on the first pin; instruction returns when
the last frame is unpinned; the no-source text; `sigInstructionChanged` emitted
only on an actual change; `release()` disconnects.

### `StatusPanel` slots

Priority order across all three sources, and — the property the change exists
for — that setting or clearing one source does not disturb another's message.
Errors still outrank instructions.

### Window integration

New slice opens the Camera module, prompts, and clears; declining leaves the
frames; the instruction appears and retracts as frames are pinned and unpinned;
`teardown()` releases.

The release test asserts Qt's own `receivers(signal)` rather than a weakref.
Twice now a mandated "remove the disconnect" mutation has passed because a
nearby `= None` had already broken the cycle refcounting sees, so the weakref
proof proved nothing.

### Mutation discipline

Every test whose assertion is about absence (`== ""`, `is None`, "not called",
"still pinned") gets a mutation proof, and the proof must record **the line
number the failure occurred at** — two mandated mutations on the
error-surfacing branch were defective, one failing a step before its assertion
and one not failing at all, and only reading the failure output caught either.

## 7. Open, and deliberately deferred

- **Still open for Area 1** after this: slice disk persistence via
  `DirHandle.setInfo()`, and the progress heatmap's cross-repo
  `acq4_automation.Cell` expansion.
- **The live GUI smoke test still needs a human at a screen** — the prompt's
  wording, the band's legibility, and whether opening the Camera module from
  New slice feels helpful or intrusive on a real rig. P2c-3a and the progress
  overlay both shipped unverified against the rig and this will too.
- **"Fresh" is enforced only by the clear.** An operator who declines the
  prompt keeps frames of the previous slice, and the instruction stays retracted
  because frames are pinned. Nothing tracks which slice a frame was taken on.
  Making that distinction real would mean stamping frames at pin time in the
  Camera module, which is a change to shared code for a case the operator has
  explicitly opted into.
- **`"Camera"` stays hard-coded** as the module name, matching
  `_cameraModuleWindow`. A rig that names its Camera module something else
  already does not get the outline mirror either.
