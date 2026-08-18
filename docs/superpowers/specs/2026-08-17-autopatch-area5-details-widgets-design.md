# Autopatch Area 5 — action details widgets

Design agreed 2026-08-17. Area 5's detail pane can currently show exactly two
things: the live widget of the action running right now, and the error block of
the cell's most recent failure. Everything else an action produces is discarded.
This builds the pane out: every action may hand back a retained, GUI-free
description of what it found, the timeline becomes the navigator for those
records, and `patch`/`reseal` gain a real electrophysiology log of their own.

## 1. What this builds, and what it does not

Four things:

- **A second engine seam.** `ActionLogEntry.set_details(kind, payload)` beside
  the existing `set_details_widget(widget)`. The widget is for what is live; the
  payload is what survives.
- **Retention and navigation in `CellPanel`.** Payloads keyed by cell and
  timeline row, mounted when the operator selects that row, with a follow-live
  rule for the running action.
- **`MultiPatchLogRecorder`** — the MultiPatch module's event-log writing,
  extracted so Autopatch can record too, with MultiPatch refactored onto it.
- **Details for the actions that have something to say**: `patch`/`reseal` (a
  steady-state resistance plot, live and frozen, plus the FSM's state
  transitions), `cellfie` (the cell's stack), `run_task` (the sequence's
  traces), and one-line records for `prompt`, `new_data_dir`, and
  `find_surface`.

And one thing the pane gains that costs almost nothing: **the status line**.
`set_status()` is write-only today — `CellPanel._onActionEntry` deliberately
ignores the `"status"` phase, so `"driving FSM from 'approach'"` →
`"now in 'seal'"` → `"reached 'whole cell'"` appears nowhere in the UI at all.
It becomes a header label above the mounted widget. The timeline rows are
unchanged: still `⏳ running` then the outcome, per design doc §7.

**Not** built:

- **Reloading a saved record into the pane.** Disk is for post-hoc analysis
  (`tools/autopatch_analysis`), not for repopulating Area 5. A record the
  current session did not produce is not viewable in Area 5, and a restarted
  session starts empty. This was on the table and was declined.
- **Loading a named protocol file into the TaskRunner.** `run_task` keeps its
  contract — the operator loads the sequence into an open TaskRunner module —
  and the `device.py` TODO about that stays open. This pass gives it a results
  view and nothing else.
- **Any MultiPatch UI reflecting Autopatch's recording.** See §5.
- **Live imagery during `cellfie`.** See §8.

## 2. The engine seam — `set_details`

`ActionLogEntry` (`acq4/experiment/log_entry.py`) grows, mirroring the existing
`set_details_widget`/`on_widget` pair exactly:

```python
self.details_kind: str | None = None
self.details_payload: Any = None
self.on_details: Callable | None = None

def set_details(self, kind: str, payload) -> None:
    self.details_kind = kind
    self.details_payload = payload
    if self.on_details is not None:
        self.on_details(self, kind, payload)
```

**The payload contract is GUI-free plain data**: numpy arrays, strings, numbers,
and dicts/lists of those. No `Qt` objects, no `Cell`, no exception objects, no
file handles, no `PatchClampTestPulse`. `CellPanel` retains these for the
session, so what a payload holds is what one action costs in memory for the rest
of the run — the same reasoning that makes
`error_record.describe_exception` reduce an exception to three strings before
`CellPanel` stores it, and the same reference-cycle hazard
`tests/test_teardown.py` exists to guard.

`set_details_widget` keeps its §4.5 contract completely unchanged, including
"the connection must be disconnected when the entry's action ends".

**Ordering invariant.** `set_details` must be called before the entry finishes.
`CellPanel` resolves an entry to its timeline row through `_entryTimelineLoc`,
which `_finishTimelineRow` pops — so a payload arriving after `_finish` has no
row to attach to. Actions satisfy this by calling `set_details` from a
`try/finally` **inside** the `with ctx.log_action(...)` block, which runs before
the context manager's `__exit__`. Both phases are emitted from the same worker
thread to the same receiver, so Qt's queued delivery preserves their order.
This is stated in the method's docstring and pinned by a test.

## 3. Retention and navigation in `CellPanel`

**Retention.** A new store:

```python
# (id(cell), timeline row index) -> (kind, payload)
self._details: dict[tuple[int, int], tuple[str, Any]] = {}
```

Keyed by row rather than by entry, deliberately: the row key is what outlives
the entry, which is the entire point, and it is already the key `_timelines`
uses. It never holds an entry, a cell, or a widget, for the reasons in §2.
Cleared by `clearCells()` and `_onCellsDiscarded()` alongside `_timelines` and
`_logs`, and by `_onReuseCheckedCells()` for a re-queued cell, whose earlier
pass's UI history is not retained (design doc §7).

`onLogAction` assigns one more callback beside the three it already assigns:

```python
entry.on_details = lambda e, kind, payload: self.sigActionEntry.emit(cell, e, "details")
```

The payload is read off the entry in the slot rather than carried through the
signal, matching how the `"widget"` phase already reads `entry.details_widget` —
`sigActionEntry`'s signature does not change.

**Navigation.** `timelineList` gains a `currentItemChanged` handler. Selecting a
row mounts, in order of preference: the live details widget if that row's action
is still running; else that row's retained payload rendered per §4; else nothing.
The status line above it shows that row's status text — live for a running
action, last-known for a finished one.

**A failed action's error becomes a payload.** The `finished` phase already
reads `exc_type`/`exc_message`/`traceback_text` off the entry; it now also
records them as `_details[(cellId, index)] = ("error", {...})`, so the row
renders through the same registry as everything else and `ErrorBlock` becomes
one more builder. `self._cellErrors` and the public `errorText(cell)` are
**unchanged** — they answer "which cell failed", which is a different question
from "what did this row do", and `tests/test_teardown.py` asserts against
`errorText`. An action that fails *and* set a payload keeps the payload: the
data it gathered before failing is more informative than the traceback, which
the log and the row's outcome glyph both still carry.

Two rules preserve what already shipped:

- **Selecting a cell auto-selects a row** rather than leaving the pane blank:
  the running action if there is one, else the most recent failed action, else
  the last row. So "select a failed cell, see its traceback" keeps working —
  `_showErrorBlock`'s cell-level mount becomes an ordinary row rendering reached
  by that auto-selection.
- **Following live** uses the auto-scroll rule. While the selected row is the
  last row, a newly started action moves the selection to it. The moment the
  operator selects an earlier row, following stops — until they select the last
  row again, which resumes it. This is what design doc §7's "selecting the
  current cell follows it live" means once rows are individually selectable.

`_shownEntryId` keeps its existing job unchanged: it is what lets an inner
entry's `"finished"` phase avoid tearing down an outer entry's still-live widget
(`prompt()` opening inside `cellfie`'s still-open entry). Nesting needs nothing
new from the payload store — each entry has its own row.

## 4. `details_renderers.py`

New module `acq4/modules/Autopatch/details_renderers.py`: a `kind` → builder
registry, so every `Qt` widget type the pane can mount lives in one focused
place instead of adding four more to `cell_panel.py` (already 868 lines).
Builders are plain functions taking a payload and returning a widget. They never
see a `Cell`, an entry, or the panel.

| kind | payload | rendered as |
| --- | --- | --- |
| `"test_pulse_history"` | `history` (a `TEST_PULSE_NUMPY_DTYPE` array), `transitions` (list of `(time, state)`), `entry_state`, `reached`, `log_file` | MultiPatch's `PlotWidget` with its mode combo visible, beside a transition list |
| `"image_stack"` | `stack` (3D array), `center_index`, `title` | `pg.ImageView`, opened at `center_index` |
| `"task_results"` | `traces` (list of `(t, y)` arrays), `sequence_dir`, `sweep_count`, `decimation`, `units` | `pg.PlotWidget`, one curve per sweep |
| `"text"` | `lines` (list of strings) | read-only text |
| `"error"` | `exc_type`, `exc_message`, `traceback_text`, `cell_repr` | the existing `ErrorBlock` |

An unregistered kind renders as its `repr` in the `"text"` renderer rather than
raising: a payload is data crossing a thread boundary from protocol code, and a
protocol author's typo must not take down the pane.

**The frozen Rss plot reuses MultiPatch's `PlotWidget`,** per design doc §4.5's
"reuse, do not reimplement". Its `newTestPulse(tp, history)` currently requires
a `tp` for the current-value label; it gains tolerance for `tp=None`, which
suppresses that label and plots the history alone. That is the whole change to
it, and it buys the field dropdown: because the payload retains the entire
structured array, the frozen plot can switch between `ss resistance`,
`peak resistance`, `holding current`, `holding potential`, `time constant`, and
`capacitance` with no extra data.

**The mode combo is hidden live and shown frozen.** The live plot calls
`hideHeader()` — Autopatch picks the mode, and design doc §4.5 says the operator
does not need the combo while an action is driving. The frozen plot leaves it
visible, since re-reading a finished attempt through a different field is
precisely what it is for. The `'test pulse'` and `'tp analysis'` modes are
removed from the frozen combo: both need an actual `PatchClampTestPulse`, which
§2's payload contract excludes.

## 5. `MultiPatchLogRecorder`

New module `acq4/util/multipatch_log_recorder.py`.

**Not an attribute of `PatchPipette`.** A recorder owns a file handle and a
directory lifetime; a device outlives both. More decisively, one attribute means
one recorder per pipette — which is exactly the collision to avoid, since
Autopatch and MultiPatch must be able to record the same pipette independently.
**Not in `acq4/filetypes/`** either: that package registers `FileType` *readers*
for DataManager, and its `MultiPatchLog.py` is already over 1100 lines.

```python
recorder = MultiPatchLogRecorder(
    directory,                      # DirHandle to write into
    pipettes=(pip,),                # one or more PatchPipettes to observe
    microscope=None,                # optional; records surface_depth_changed
    record_full_test_pulses=True,   # Autopatch's default
    initial_records=(),             # replayed into the fresh file
)
recorder.record(event)              # module-level records (e.g. patch profiles)
recorder.testPulseAnalysis()        # structured array of what this recorder saw
recorder.stop()
```

Carried over from `MultiPatchWindow` unchanged, because the log viewer and
`tools/autopatch_analysis` both have to keep reading the result:

- One `MultiPatch_NNN.log` per recorder, via
  `directory.createFile('MultiPatch.log', autoIncrement=True)`, opened `'ab'`.
- One JSON record per line through `ACQ4JSONEncoder`, flushed per batch.
- `full_test_pulse` diverted into a `TestPulses_NNN.hdf5` at group
  `test_pulses/{device}`, with the event's field rewritten to
  `"<relpath>:<h5path>"` relative to the log file's directory — the form
  `MultiPatchLogData.process` resolves with `loc.split(":")[0]` and
  `os.path.join(os.path.dirname(filename), ...)`.
- The patch-profile snapshot (`buildPatchProfilesParameters().getValues()`)
  written at start. For a per-action Autopatch recorder this records the profile
  in force for that attempt, which is worth having.

**Deliberately left in `MultiPatchWindow`:** `eventHistory`, the Reset button,
and `resetHistory()`. That last one is the important one — it calls
`clampDevice.resetTestPulseHistory()`, and a recorder that did the same would
let Autopatch starting a recorder wipe the history MultiPatch is plotting. **The
recorder owns a file and an HDF5 stack; it never touches device state.**
MultiPatch's `writeRecords(self.eventHistory)` on record-start is preserved
through `initial_records`.

**MultiPatch is refactored onto it**: `recordToggled` constructs a single
recorder over all its pipettes, its microscope, and its profile records —
its current single-file behavior — and `stop()`s it when toggled off.
`recordTestPulsesToggled` becomes that recorder's `record_full_test_pulses`
option. One implementation means "identical behavior, so the viewer still
renders it" holds by construction rather than by inspection.

**MultiPatch's UI shows nothing about other recorders.** No registry, no
indicator, no discovery seam. Its buttons control its own recorder and nothing
else, and are entirely orthogonal to Autopatch. Two parallel logs over one
pipette is an accepted outcome, not a problem to solve.

## 6. `PatchPipette.requestFullTestPulseData`

`emitFullTestPulseData(emit: bool)` sets a bare boolean `_emitTestPulseData`.
With two independent recorders, whichever stops last wins: Autopatch stopping
its recorder would silence MultiPatch's full-test-pulse capture, and vice versa.

It has exactly one caller (`multipatch.py:632`), so the boolean setter is
replaced outright rather than wrapped:

```python
def requestFullTestPulseData(self, token) -> None:
    self._fullTestPulseSubscribers.add(token)

def releaseFullTestPulseData(self, token) -> None:
    self._fullTestPulseSubscribers.discard(token)
```

with `_testPulseFinished` testing `bool(self._fullTestPulseSubscribers)`. Each
recorder holds its own token, so neither can silence the other. The subscriber
set holds tokens, not recorders, so it never keeps a recorder alive; a recorder
releases its token in `stop()`.

## 7. The log format — dropping the trailing comma

`writeRecords` writes `json.dumps(rec) + b",\n"`, producing not-quite-JSONL with
a trailing comma on every line. The recorder writes clean JSONL instead.

**This breaks neither reader, verified.** Both use
`line.rstrip(b",\r\n")` — `MultiPatchLog.py:232` and
`autopatch_log.py:76` — which is a *character-set* strip, not a suffix strip, so
it already yields the same bytes for `{...},\n`, `{...},\r\n`, `{...}\n`, and
`{...}`. Existing logs with commas keep parsing, new logs without them parse
identically, and no reader change is required. A test pins both forms so the
tolerance is guaranteed rather than incidental.

One unrelated repair while in the area: `MultiPatchLog.py:232` has no blank-line
guard, where `autopatch_log.py:77` does. It is latent rather than triggered
today — a file ending in a newline yields no trailing empty line when iterated —
but the two readers should agree, so the guard is added.

## 8. Per-action behavior

**`patch(ctx, record_events=True, record_full_test_pulses=True, **entry_config)`
and `reseal(...)`.** `_drive_fsm` gains a `record` parameter; `clean` passes
`False` and is otherwise untouched — there is nothing an operator reads off a
clean (design doc §4.5), and it needs no log of its own. The new named
parameters are consumed by `_drive_fsm` and never reach `pip.setState`, so
`entry_config` keeps working as it does. A protocol may pass them through to its
own author-facing options.

On entry, through `run_in_gui_thread`: construct the recorder in
`ctx.manager.getCurrentDir()`; construct `PlotWidget(mode='ss resistance')`,
call `hideHeader()` (Autopatch picks the mode), wire
`clampDevice.sigTestPulseFinished` to `newTestPulse` with a **default (queued)**
connection — `PatchPipetteState` uses an explicit `DirectConnection` on that
same signal, which is right for a state machine and wrong for a widget — and
`set_details_widget(widget)`.

During: the poll loop's existing `state != last_state` branch also appends
`(time, state)` to a local list. No new polling.

On exit, in a `try/finally` inside the `with` block so it runs before `_finish`
(§2) and on every path including `Stopped` and `AdvanceToNextCell`: disconnect
the plot from the device, `recorder.stop()`, and
`set_details("test_pulse_history", ...)`. Because it is a `finally`, a failed,
stopped, or abandoned patch gets its plot and its transition list too — which is
when an operator most wants them.

**The payload's history comes from the recorder, not from
`clampDevice.testPulseHistory()`.** Slicing the device's history by the action's
time window looks simpler and is wrong: `approach.py:251` calls
`resetTestPulseHistory()` inside the approach state, and `patch()` enters at
approach, so the device's history is truncated mid-span on every attempt.
`PatchPipette` line 237 resets it as well. The recorder accumulates the
`test_pulse` events it observes and is immune to both.

**`cellfie(ctx, ...)`.** No live widget. The cropped object stack does not exist
until `initializeTracker` returns, and the status line ("focusing on target for
cellfie" → "saving cellfie z-stack") reports progress honestly in the meantime.
After the tracker initializes:

```python
action_entry.set_details("image_stack", {
    "stack": np.swapaxes(np.asarray(stack), -2, -1),
    "center_index": stack.shape[0] // 2 if stack.ndim >= 3 and stack.shape[0] > 1 else None,
    "title": "Cellfie",
})
```

The stack is the tracker's `motion_estimator.original_object_stack.data` — the
cube around the cell, exactly what `AutomationDebug._cellInitialStack` shows,
including its axis swap so orientation matches the Camera module. It is already
in memory on the `Cell`, so retaining a reference to the array costs the pane
nothing, and the full acquired z-stack stays on disk in `cellfie/` where
`run_image_sequence` already put it.

**Accepted gap:** a cellfie whose tracker init raises `CellTrackingLost` calls
`ctx.tissue_moved`, which never returns, so no payload is set. That row shows
its status line and an `abandoned` outcome with no stack. The full frames are
still on disk; reading them back is the reloading feature §1 declines.

**`run_task(ctx, ...)`.** Live: a `pg.PlotWidget` fed from
`taskrunner.sigNewFrame` (queued), plotting `frame['result'][clampName]['primary']`
against `result.xvals('Time')` — the accessor `MultiClamp/taskGUI.py:336` uses —
coloured over sequence index. On exit, `set_details("task_results", ...)`.

**Retention is capped, and the cap is logged.** A 20-sweep sequence at 100k
samples per sweep is 16 MB per cell, so retained traces are decimated to ~4000
points each — more than a plot's pixel width — with the decimation factor
recorded in the payload and reported through `ctx.log()`. The undecimated data
is in the saved `ProtocolSequence` directory, whose name the payload also
carries.

**`prompt`, `new_data_dir`, `find_surface`.** `set_details("text", {"lines": [...]})`
with, respectively: the message and the label the operator clicked (available as
`prompt_user`'s return, so the call moves into a local before the `with` block
ends); the created directory's name; and the detected depth via `pg.siFormat`.

## 9. Threading and lifetime

Every rule here already exists in this module; nothing new is introduced.

- **Payloads cross threads as data.** Actions run on the orchestrator's worker
  thread. `set_details` emits `sigActionEntry`, and Qt's automatic queued
  connection marshals it onto the GUI thread — the same discipline
  `appendLog`, `onLogAction`, and `discardCells` already follow.
- **Widgets are built on the GUI thread**, via `run_in_gui_thread`, per
  `set_details_widget`'s docstring. That covers the recorder too: it is a
  `QObject` whose `sigNewEvent` connections must be queued from device and
  state-machine threads, which requires it to live on the GUI thread — the same
  affinity MultiPatch's window already gives it.
- **No widget outlives its action.** The `finished` phase drops the live widget
  exactly as it does today; only data is retained. `test_teardown.py`'s
  invariants hold as written, and no payload can form a panel↔entry cycle
  because a payload holds neither.
- **The recorder is always stopped**, from the same `finally` that sets the
  payload, so no file handle or `full_test_pulse` subscription outlives the
  action that opened it.

## 10. Testing

Headless, in the existing suites:

- `ActionLogEntry.set_details` — callback firing, and the ordering invariant
  that a payload set after `_finish` is not attributable to a row (§2).
- `CellPanel` — payload keying by `(cell, row)`; clearing across `clearCells`,
  `discardCells`, and reuse; row selection mounting the right thing in the right
  order of preference; the auto-selected row on cell selection for running,
  failed, and finished cells; the follow-live rule, including that it stops when
  an earlier row is selected and resumes at the last row; a failed action's error
  recorded as an `"error"` payload while `errorText(cell)` keeps its existing
  answer; and an action that both fails and set a payload keeping the payload.
- `details_renderers` — each builder against a synthetic payload under the
  `qapp` fixture, plus the unregistered-kind fallback.
- `PatchPipette` — `requestFullTestPulseData` refcounting: two tokens, one
  released, data still flowing.
- `MultiPatchLogRecorder` — a **golden-output test**: drive a fake pipette
  through a fixed event sequence and assert the recorder's bytes match a
  reference implementation of the current `writeRecords` held in the test. This
  is the actual safety net for "identical behavior", because MultiPatch's only
  existing test file (`tests/test_logfile.py`) covers `IrregularTimeSeries` and
  nothing in the logging path at all.
- Round-trips through both readers — `MultiPatchLogData` and
  `tools/autopatch_analysis`'s parser — for a recorder-written file, and an
  explicit test that comma-free and legacy comma-terminated lines parse
  identically (§7).
- `PlotWidget.newTestPulse(None, history)` plots without raising and suppresses
  the label.

Live-only, per `actions/device.py`'s module docstring convention: the real
device wiring in `patch`, `reseal`, and `run_task`, which drive hardware and are
exercised by live testing rather than the headless suite.

## 11. Phasing

This spec covers more ground than one landable change, and the two halves are
separable — the recorder is only reached by `patch`/`reseal`'s payload, and
nothing else in the pane depends on it. The implementation plan runs in three
phases, each of which leaves the tree working and testable:

1. **The pane** (§2, §3, §4 minus the test-pulse renderer, §8's `cellfie`,
   `run_task`, `prompt`, `new_data_dir`, `find_surface`, and the status line).
   Delivers navigable per-row details, the cellfie stack, and the task-runner
   results — visible value with no changes outside `acq4/experiment` and
   `acq4/modules/Autopatch`.
2. **The recorder** (§5, §6, §7, and MultiPatch's refactor onto it). Touches
   `PatchPipette`, `MultiPatch`, and the log format; lands behind the
   golden-output test before anything depends on it.
3. **The FSM details** (§8's `patch`/`reseal`, and §4's test-pulse renderer),
   which joins the two.

Phase 2 is the one carrying regression risk to code outside this feature, which
is why it lands on its own rather than folded into phase 3.

## 12. Open, and deliberately deferred

- **Recording spans only FSM actions.** With one recorder per `patch`/`reseal`
  call, `cellfie` and `run_task` fall outside any recording window. The recorder
  is a reusable object with options, so extending it to those actions is a
  configuration change rather than new mechanism, but it is not this pass.
- **`clean` records nothing** — no recorder, no details widget.
- **Loading a named protocol file into the TaskRunner** — `device.py:196`'s TODO
  stays open.
- **Reloading saved records into Area 5**, and with it viewing a past session's
  cells. Declined in §1.
- **Merging `PipetteEventLog` and system-log lines into the pane** remains P3
  (design doc §8), untouched by this.
- **The `'test pulse'` and `'tp analysis'` plot modes on frozen plots**, which
  would require retaining `PatchClampTestPulse` recordings and so are out under
  §2's payload contract.
