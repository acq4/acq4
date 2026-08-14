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

And one simplification of landed code that this depends on:

- **The Camera module is opened at startup**, by the `Autopatch` module itself,
  and is thereafter assumed to exist.

**The "wait" is advisory.** No control is disabled and no run is blocked.
Nothing gates on reference imagery existing; the band says what to do and the
operator decides. This was chosen over gating region drawing and over gating
Start, both of which were on the table.

Out of scope: slice disk persistence via `DirHandle.setInfo()`, the progress
heatmap's remaining cross-repo work, and the live GUI smoke test — all still
open, none of them this.

## 1b. The Camera module is a precondition, not a possibility

Everything in Area 1 that touches imagery — both mirrors and now the reference
workflow — was written to treat a closed Camera module as ordinary: resolve to
`None`, do nothing, and in the mirror's case put a message in the band about it.
That was three code paths and one operator-facing warning serving a state the
rig is never meant to be in.

**Instead: `Autopatch.__init__` opens the Camera module** — in the `Module`
class, before `AutopatchWindow(self)` is constructed, so the window can assume
it. A Camera module closed after startup is an error, not a state to degrade
into, and `_cameraWindow()` raises `HelpfulException` when asked for a window
that is not there. `HelpfulException` rather than `RuntimeError` because it is
acq4's operator-facing error type — the same one `create_data_dir` raises for an
unset storage directory — and it surfaces through acq4's existing error dialog
rather than reading as a crash.

Three things are deleted outright:

- The **"Mirror to Camera: no Camera module is open"** instruction, and with it
  `_setRegionInstruction` and the `_regionInstruction` bool.
- **`_onModulesChanged`**, its `sigModulesChanged` connection and its teardown
  disconnect. Its entire job was re-binding the mirrors when a Camera module
  appeared later, which can no longer happen. It also carried a `_tornDown`
  guard for a race it can no longer lose.
- The `except Exception: return None` fallback in `_cameraModuleWindow`.

**Verify before relying on it:** `manager.getModule("Camera")` called from
inside another module's `__init__` re-enters `Manager`'s module loading. This is
assumed to work and must be confirmed against a running app, not reasoned about.
If it does not, the fallback is opening it from `AutopatchWindow`'s first
`showEvent` instead.

## 2. `ReferenceImagery`

New file `acq4/modules/Autopatch/reference_imagery.py`.

```python
ReferenceImagery(imagingCtrlGetter, prompt=None)
```

A `QObject`, unlike the plain `PinnedFrameMirror`/`CameraMirror` classes beside
it, because something listens to it: the band has to re-render when the pinned
set changes. `ProgressOverlay` is a `QObject` for the same reason.

### Surface

| Member | Meaning |
| --- | --- |
| `beginSlice()` | New slice's entry point: resolve, prompt-and-clear, recompute. |
| `rebind()` | Re-resolve the source, swap the subscription, recompute. |
| `instruction() -> str` | The guidance this component wants shown; `""` for none. |
| `sigInstructionChanged` | Emitted **only when `instruction()` changes value**. |
| `release()` | Disconnect and forget the source. Teardown's call. |

### The two injected seams

Injection is what makes this headless-testable, the same choice P2b made for
the tile detector.

- **`imagingCtrlGetter() -> imagingCtrl`** resolves the Camera module's
  `ImagingCtrl` for the selected camera, as `_bindPinnedFrames` does today
  (`window.getInterfaceForDevice(camera.name()).imagingCtrl`). It no longer has
  a "none" answer: a missing Camera window raises `HelpfulException` from
  `_cameraWindow()`, and a Camera module with no interface for the selected
  camera raises one too, naming the camera.
- **`prompt(text) -> bool`** defaults to a `QMessageBox.question`, mirroring
  `ImagingCtrl.clearPinnedFramesClicked`'s own confirmation. Injected so no
  headless test can open a modal.

**Nothing catches these raises.** `beginSlice()` lets them propagate out of
`newSlice()` to acq4's error dialog, which is the agreed handling for a Camera
module closed after startup. Note this is a different decision from the
`storage` slot beside it, which *is* caught and rendered as guidance: an unset
storage directory is a thing the operator has not done yet, while a closed
Camera module is a thing that should not have happened.

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
the Qt event loop; every queued slot dispatches inside it — most consequentially
the `sigCellFinished` queued from the cell still in flight on the tissue this
click just discarded, whose whole suppression dance
(`abandonCellInHand`, and the six review rounds behind it) assumes it lands
outside a half-completed New slice. Running the prompt last means no
intermediate state of `newSlice()` is ever observable from inside a nested
event loop. This project has been bitten repeatedly by a queued signal landing
mid-transaction; opening a nested loop in the middle of one invites the same
class of defect.

Inside `beginSlice()`, in order:

1. `rebind()` — resolve the `ImagingCtrl`, subscribe to
   `sigPinnedFramesChanged`.
2. If `pinnedFrames` is non-empty, `prompt(...)`; on a Yes,
   `source.clearPinnedFrames()`.
3. Recompute the instruction and emit if it changed.

**Declining does not abort New slice.** The slice is already built by the time
this runs; the prompt is about frames alone. **Zero pinned frames means no
prompt at all** — there is nothing to confirm.

`_tornDown` already blocks this path: `newSlice()` returns early from
`_canStartSlice()`, so `beginSlice()` is never reached on a torn-down window.

## 4. The instruction, and named slots in `StatusPanel`

Area 3's band currently holds one instruction string, with a `_regionInstruction`
bool on the window answering "may I retract what is up?". Replace it with slots.

**Slots are still needed even though §1b deletes one of the writers.** With the
mirror message gone the band has two: `storage` and `imagery`. They are not
mutually exclusive. `newSlice()` can fail at `create_data_dir` **with the
previous slice still installed** — so the storage message goes up while a slice
exists whose frames may all have been unpinned, which is exactly when the
imagery message wants the band too. A single string plus an ownership bool
cannot hold both, and which one wins would depend on click order.

```python
StatusPanel.setInstruction(source: str, text: str)   # "" clears that slot only
StatusPanel.instruction() -> str                     # unchanged meaning
```

Priority is a module-level constant; the first non-empty slot renders:

| Rank | Source | Message | Why here |
| --- | --- | --- | --- |
| 1 | `storage` | `str(HelpfulException)` — "Storage directory has not been set." | New slice could not complete at all. |
| 2 | `imagery` | "Pin reference frames of this slice in the Camera module." | The slice exists but has no reference imagery. |

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
has just resolved — and leaves `imagery` to `ReferenceImagery`, which
recomputes it from state moments later in `beginSlice()`. A blanket wipe would
have raced that recompute for no reason.

### What `imagery` says, and when

State-driven, not event-driven. The slot's text is a pure function of the
current state, recomputed on every `sigPinnedFramesChanged` and on every
`rebind()`:

- No slice → `""`.
- Slice, zero frames pinned → the pin-frames instruction.
- Slice, one or more frames pinned → `""`.

There is no "no source" case: per §1b the Camera module is a precondition, and
failing to resolve one raises rather than producing a third message.

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

The window calls `rebind()` from `_startSlice()`, beside `_bindPinnedFrames` —
the only remaining caller, now that `_onModulesChanged` is deleted. Both need
re-resolving for the same reason: the operator may have changed the selected
camera between slices.

## 6. Testing

### `ReferenceImagery`, headless

Against a fake `ImagingCtrl`: a `QObject` with `sigPinnedFramesChanged`, a
`pinnedFrames` list, and a `clearPinnedFrames()` that **genuinely empties the
list and emits**. An honest fake is not optional here — P2b's `restore_depth`
and `_FakeCamera` defects both survived because the fake agreed with the code
and neither matched the device. A `clearPinnedFrames()` that does not emit
would hide a missing recompute.

Prompt stub is parameterised True/False.

Cases: no prompt when nothing is pinned; prompt then clear on Yes; prompt then
**frames still pinned** on No; instruction appears at zero frames and retracts
on the first pin; instruction returns when the last frame is unpinned;
`sigInstructionChanged` emitted only on an actual change; a getter that raises
`HelpfulException` propagates out of `beginSlice()`; `release()` disconnects.

### `StatusPanel` slots

Priority order across both sources, and — the property the change exists for —
that setting or clearing one source does not disturb another's message. The
case that motivates it gets its own test: `storage` set while `imagery` is
also non-empty, which is reachable because `create_data_dir` can fail with the
previous slice still installed. Errors still outrank instructions.

### Window integration

New slice prompts and clears; declining leaves the frames; the instruction
appears and retracts as frames are pinned and unpinned; `teardown()` releases.

**`_FakeManager` has to change, and this is the largest test cost of §1b.** It
carries no `listModules`/`getModule` today — tests that need a Camera window
monkeypatch them in, and everything else relies on `_cameraModuleWindow`'s
`except Exception: return None`. With that fallback deleted, the default fake
must supply a Camera module with a working `getInterfaceForDevice`. That is the
more honest fake regardless: production now guarantees a Camera module, and a
fake that reports none does not reproduce production — the same defect class as
P2b's `restore_depth` and `_FakeCamera`.

Its `sigModulesChanged` signal stays (harmless, and the real `Manager` has one)
but nothing in Autopatch listens to it any more. The two tests asserting the
"no Camera module is open" mirror warning are deleted with the warning; the
test that asserts `_cameraModuleWindow` does **not** load an unopened module is
deleted with the guard, and replaced by one asserting the raise.

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
  wording, the band's legibility, and above all whether `getModule("Camera")`
  from inside `Autopatch.__init__` actually works (§1b). P2c-3a and the
  progress overlay both shipped unverified against the rig and this will too,
  but that one assumption is worth a deliberate check.
- **"Fresh" is enforced only by the clear.** An operator who declines the
  prompt keeps frames of the previous slice, and the instruction stays retracted
  because frames are pinned. Nothing tracks which slice a frame was taken on.
  Making that distinction real would mean stamping frames at pin time in the
  Camera module, which is a change to shared code for a case the operator has
  explicitly opted into.
- **`"Camera"` stays hard-coded** as the module name, matching
  `_cameraModuleWindow`. A rig that names its Camera module something else
  already does not get the outline mirror either — though under §1b that rig
  now gets a `HelpfulException` where it previously got a blank Area 1, which
  is arguably the better outcome and definitely the louder one.
