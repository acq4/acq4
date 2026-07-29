# Autopatch P1.5 — API polish from design review

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

Follow-up to `2026-07-24-autopatch-p1-5-plain-function-migration.md`, addressing
review feedback on the plain-function API now that it is in place. Seven changes
across four tasks. All are on branch `claude/autopatch-dev-plan-3c9f6f` (PR #559).

**Baseline:** 234 tests passing across `acq4/experiment/` + `acq4/modules/Autopatch/`,
pristine, no ignores.

## The design doc lives outside this worktree

The governing spec is `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md`
— untracked, in the **main checkout**, not this worktree. Several tasks must edit
it. Use that absolute path.

## Global Constraints
- Test runner: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- Verify with a hard timeout so a latent hang fails instead of stalling:
  `timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ acq4/modules/Autopatch/ -q`
- Concurrency: `check_stop`/`sleep`/`Stopped`/`Event`/`run_in_gui_thread` from
  `acq4.util.task`. Never `time.sleep`/`threading` in production code.
- Logging: `from acq4.logging_config import get_logger`. Never stdlib `logging`.
- `from acq4.util import Qt`. 2-line docstring per new file. No temporal comments.
- Engine code is snake_case; the `modules/Autopatch/` UI layer is camelCase.
  Match the file you are in.
- Commit format:
  `git commit --author="Claude (claude) <noreply@anthropic.com>" -m "<type>: <desc>\n\n🤖 Generated with [Claude Code](https://claude.ai/code)"`
  NEVER `--no-verify`.

## Invariants that must not break
- Engine→UI callbacks are **emit-only**; widget mutation happens on the GUI
  thread via queued connections.
- `CellPanel` never stores an `ActionLogEntry` — only an `int` id. This keeps the
  new closures off the object graph guarding a known exit segfault.
- `acq4/modules/Autopatch/tests/test_teardown.py`'s assertions are that
  segfault's regression test. **Do not change any assertion in it.**
- FSM safe-abort fires on the cooperative-abandon paths only (`Stopped` and
  `AdvanceToNextCell`).

---

## Task 1: Human-readable action names, and rename `entry`

**Files:** `acq4/experiment/actions/{device,fsm,prompt,storage}.py`,
`acq4/experiment/log_entry.py` (docstring only if needed), and every test
asserting a log-entry name.

### 1a. Action display names

`ctx.log_action(name)`'s `name` is **operator-facing**: it is the label of a row
in Area 5's executed-path timeline, rendered as
`f"{name} — ✓ done (1.20s)"`. The current values are class-name leftovers
(`"GoHome"`, `"FindTip"`, `"NewDataDir"`, `"Task"`) — CamelCase abbreviations that
buy nothing for a human reader.

There is **no character limit**: the row lives in a `QListWidget`, which elides
long text on its own. So do not invent one, and do not shorten for its own sake.

Use Title Case noun phrases that name the thing unambiguously. In particular
**"home" alone is ambiguous** — both the stage and the pipette have homes — so
every named-position move says *pipette*:

| Function | Name |
|---|---|
| `go_home` | `Pipette To Home` |
| `go_search` | `Pipette To Search Position` |
| `go_approach` | `Pipette To Approach Position` |
| `go_target` | `Pipette To Target` |
| `go_above_target` | `Pipette To Above Target` |
| `focus_tip` | `Focus On Pipette Tip` |
| `focus_target` | `Focus On Target` |
| `new_pipette` | `New Pipette Calibration` |
| `find_tip` | `Find Pipette Tip` |
| `find_surface` | `Find Sample Surface` |
| `cellfie` | `Cellfie` |
| `run_task` | `Task Runner Sequence` |
| `patch` | `Patch` |
| `reseal` | `Reseal` |
| `clean` | `Clean Pipette` |
| `new_data_dir` | `New Data Directory` |
| `prompt` | `Operator Prompt` |
| `load_preset` (Task 4) | `Load Imaging Preset` |

`Cellfie` stays as-is: it is the lab's own term for the thing, not an
abbreviation. `Patch` and `Reseal` are already plain words.

The two shared helpers (`_move`/`_focus` in `device.py`, `_drive_fsm` in
`fsm.py`) take the name as a parameter, so the callers pass these strings.

**Function names are unchanged.** A protocol author writes `go_home(ctx)` in a
file whose whole subject is one pipette; the display string is where the
disambiguation is needed. Do not rename the functions.

### 1b. `entry` → `action_entry`

`with ctx.log_action(name) as entry:` binds a vague name. Rename the bound
variable to `action_entry` everywhere it appears — production and tests. It is
referenced only a few times per function, so the extra characters cost nothing.

Do **not** rename the class (`ActionLogEntry`), the module (`log_entry.py`), the
`ExecutionContext.on_log_action` hook, or `CellPanel`'s parameters — only the
`as`-bound local and any local variable holding one.

- [ ] **Step 1: Update the tests first**

Several tests assert on entry names (search for `entry.name`, `_entry_names`,
`entries[0].name`, and the literal old strings). Update them to the new strings,
run, and confirm they fail against the current code — that failure is the proof
the names are actually reaching the UI layer and not just sitting in source.

- [ ] **Step 2: Apply the renames**

- [ ] **Step 3: Verify no old name survives**

```bash
grep -rn '"GoHome"\|"GoSearch"\|"GoApproach"\|"GoTarget"\|"GoAboveTarget"\|"FocusTip"\|"FocusTarget"\|"NewPipette"\|"FindTip"\|"FindSurface"\|"Task"\|"NewDataDir"\|"Prompt"\|"Clean"\|as entry:' acq4/
```
Expect no hits. (`"Patch"`, `"Reseal"`, `"Cellfie"` are unchanged and will not
appear in this list.)

- [ ] **Step 4: Full suite, then commit**

`refactor: give action log entries operator-readable names`

---

## Task 2: Flow control becomes part of the context API

**Files:** `acq4/experiment/context.py`, delete
`acq4/experiment/actions/flow.py`, `acq4/experiment/actions/__init__.py`,
`acq4/experiment/actions/fsm.py`, `acq4/experiment/tests/test_actions_flow.py`
(split), the example protocols, and
`/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` §2.4 and §5.

`ExecutionContext` already owns `raise_flow_signal(exc)` — the single
record-then-raise path that makes the swallow-detection net work. Given that,
three module-level functions whose entire body is "call that with one specific
exception" are a pointless indirection. Flow control is a property of the run,
which is what the context *is*.

**New API** (methods on `ExecutionContext`):

```python
ctx.next_cell()    # abandon this cell, advance the queue  -> AdvanceToNextCell
ctx.retry_cell()   # restart this cell's protocol          -> RetryCurrentCell
ctx.abort()        # stop the whole experiment             -> AbortExperiment
```

Each records the signal on `self.pending_flow_signal` and raises it, exactly as
`raise_flow_signal` does now. Preserve the existing messages so log output does
not change.

`raise_flow_signal` becomes **private** (`_raise_flow_signal`) once these three
are its only callers — it is an implementation detail of the swallow net, not
something a protocol author should reach for. Check for other callers before
renaming; `fsm.py`'s poll checkpoint is one, and it should become `ctx.next_cell()`.

Delete `acq4/experiment/actions/flow.py` and drop `next_cell`/`retry_cell`/`abort`
from `actions/__init__.py`. A protocol author no longer imports them at all,
which is the point: `ctx` is already in scope.

`prompt` does **not** move — it is an operator interaction, not flow control.

- [ ] **Step 1: Write the failing tests**

Move the flow-signal tests out of `test_actions_flow.py` into
`acq4/experiment/tests/test_context.py` (they are context behavior now), keeping
what they assert: each method raises its matching signal, and each records it on
`pending_flow_signal` before raising so the orchestrator's swallow net sees it.
Keep the prompt/storage tests where they are, renaming the file if
`test_actions_flow.py` no longer contains flow tests.

Also assert the orchestrator's swallow net still fires for a protocol that
catches `ctx.next_cell()` — that is the behavior this refactor must not lose.

- [ ] **Step 2: Implement, and update every call site**

Both example protocols, `fsm.py`'s poll checkpoint, and any test protocol body
that imports the old functions.

- [ ] **Step 3: Update the design doc**

§2.4's "Flow" bullet currently lists `next_cell(ctx)` / `retry_cell(ctx)` /
`abort(ctx)` as functions in the action palette. Move them out of the palette
into a short note that flow control is on the context, with the new signatures.
§5's example uses `next_cell(ctx)`; update it.

- [ ] **Step 4: Full suite, then commit**

`refactor: move flow control from action functions onto ExecutionContext`

---

## Task 3: `patch` must not treat "cell attached" as terminal

**Files:** `acq4/experiment/actions/fsm.py`,
`acq4/experiment/tests/test_actions_fsm.py`,
`/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` §4.4.

`patch()` currently declares terminals
`{"whole cell", "cell attached", "bath", "broken", "fouled"}`. On these rigs
**auto-break-in always follows `cell attached`**, so it is a transient hop, not a
resting state. Declaring it terminal makes `patch()` return the moment the FSM
touches it — reporting a cell-attached outcome for a cell that was about to
become whole-cell, and handing control back to the protocol mid-transition.

New terminal set: `{"whole cell", "bath", "broken", "fouled"}`.

Note what this does *not* change: `cell attached` is not in
`ABNORMAL_STATE_EXCEPTIONS`, so `raise_if_abnormal` ignores it and the poll loop
simply keeps polling through it — which is the correct treatment for an internal
hop.

- [ ] **Step 1: Write the failing test**

A fake pipette whose state sequence passes *through* `cell attached` on its way
to `whole cell` must have `patch()` return `"whole cell"`, not `"cell attached"`.
Confirm it fails against the current code (it will return `"cell attached"`).

Check whether an existing test asserts the old behavior; if one does, it encodes
the bug and must be corrected, not worked around.

- [ ] **Step 2: Change the terminal set**

- [ ] **Step 3: Update the design doc**

§4.4's state-classification table marks `cell attached` as **terminal** with the
note "patch outcome". Change it to internal, and say why: auto-break-in always
follows it on an automated rig. §12's parked-items list mentions verifying that
table against each state's `run()` — leave that item, this is one entry of it.

- [ ] **Step 4: Full suite, then commit**

`fix: treat cell-attached as an internal FSM hop, not a patch terminal`

---

## Task 4: `load_preset` action, and a realistic `example_patch`

**Files:** `acq4/experiment/actions/device.py`,
`acq4/experiment/actions/__init__.py`,
`acq4/experiment/tests/test_actions_device.py`,
`acq4/modules/Autopatch/example_protocols/example_patch.py`,
`example_prompt.py`, `acq4/modules/Autopatch/tests/test_example_protocols.py`.

### 4a. `load_preset`

Imaging presets are a real, config-driven acq4 feature. Verified API:

- Declared on the **Microscope** device as `config['presets']` — a dict of
  name → per-child-device settings (`Microscope.py:52`).
- Applied by `Microscope.loadPreset(name)` (`Microscope.py:174-185`):
  **synchronous/blocking, returns `None`, and safe to call off the GUI thread**
  — `AutomationDebug/autopatch.py:168,172` already calls it from inside an
  `@asynch_with_qt_signals` worker without wrapping it.
- Reached from a context as `ctx.pipette.scopeDevice()`
  (`Pipette.scopeDevice()`, `pipette.py:260-264`).
- Enumerated as the plain public attribute `scope.presets` — Microscope has
  **no** `listPresets()` (Camera does; Microscope does not). Do not call one.
- `loadPreset` raises a bare `KeyError` for an unknown name.

```python
def load_preset(ctx, preset: str = None) -> None:
    """Apply a configured microscope imaging preset (e.g. "GFP", "brightfield").
    A preset of None is a no-op, so a protocol can leave it unconfigured."""
```

Requirements:
- `preset=None` (or empty) returns immediately **without** opening a log-action
  entry — an unconfigured preset should leave no trace in the operator's
  timeline, not a row saying nothing happened.
- Validate against `scope.presets` and raise `OrchestrationError` naming the
  action and listing the available preset names. A bare `KeyError` from a device
  is exactly the kind of unhandled exception that halts a run with a useless
  message; `OrchestrationError` is the catchable, self-describing form. Follow
  the `f"{action_entry.name}: ..."` message convention the other device actions
  use.
- Everything else follows the established port pattern:
  `with ctx.log_action("Load Imaging Preset") as action_entry:`, a
  `set_status` naming the preset.

Test with a fake scope exposing `presets` and recording `loadPreset` calls:
the preset is applied; `None` is a no-op that creates **no** log entry; an
unknown name raises `OrchestrationError` whose message names both the action and
the available presets.

### 4b. `example_patch.py`

The `speed` param goes: the approach move is always `"fast"` in practice, so it
was a knob nobody turns. Replace it with the two presets an automated run
genuinely switches between — matching what `AutomationDebug/autopatch.py:168,172`
does today (`GFP` for the cellfie, `brightfield` for patching):

```python
PARAMS = [
    {"name": "cellfie_preset", "type": "str", "default": ""},
    {"name": "patch_preset", "type": "str", "default": ""},
]


def run(ctx, cellfie_preset="", patch_preset=""):
    load_preset(ctx, cellfie_preset)
    cellfie(ctx)
    load_preset(ctx, patch_preset)
    go_approach(ctx)
    outcome = patch(ctx)
    ctx.log(f"patch outcome: {outcome}")
    if outcome != "whole cell":
        prompt(ctx, message=f"Patch ended in {outcome!r} — intervene if needed")
        return
    run_task(ctx)
```

Notes for the implementer:
- An empty-string default means both `load_preset` calls are no-ops out of the
  box, so the protocol runs on `config/mock`, which defines **no** presets at
  all. That is why the default must not be a real preset name.
- `run_task(ctx)` runs the sequence already loaded in an open TaskRunner module
  and raises `OrchestrationError` if it cannot find one. Say so in the module
  docstring — that docstring is **operator-facing** (`ProtocolFile.description`
  surfaces it in the picker), so it must state the prerequisite plainly.
- Only `"whole cell"` counts as success now that Task 3 removes
  `cell attached` from the terminal set. `"bath"` means no cell was caught;
  `"broken"`/`"fouled"` mean the pipette needs attention.
- Keep the comment explaining why `patch()`'s result is checked by outcome
  rather than `try/except OrchestrationError` (broken/fouled are declared
  terminals of `patch`, so they return rather than raise — unlike
  `reseal`/`clean`, which do raise).

### 4c. Protocols do not end with `next_cell`

Both examples currently end by advancing the queue explicitly. That is wrong in
two ways:

1. **It is redundant.** `Orchestrator._processCell`'s `else:` branch already
   emits `sigCellFinished(cell, "done")` and returns, and `_runLoopBody`'s
   `while self._queue:` pops the next cell. Advancing is the default.
2. **It mislabels the cell.** `next_cell()` raises `AdvanceToNextCell`, which the
   orchestrator reports as **`"skipped"`** — the disposition meaning *abandoned
   without completing*. A protocol that ran to completion is `"done"`.

`test_example_protocols.py` currently asserts the `"skipped"` outcome, so it
encodes this bug; fix the assertion to `"done"` rather than working around it.

Remove the trailing `ctx.next_cell()` from both examples. `ctx.next_cell()`
remains the right call for genuine early abandonment mid-protocol (and
`example_patch`'s non-whole-cell branch uses a plain `return`, which is the same
thing without the mislabelling).

This distinction matters downstream: the reuse-completed-cells design keys its
`COMPLETED` set off these dispositions, so a protocol that reports `"skipped"`
when it succeeded would land in the wrong bucket.

- [ ] **Step 1: Write the failing tests** (`load_preset`'s three cases; both
  examples still load and run; `example_prompt` now finishes `"done"` not
  `"skipped"`)
- [ ] **Step 2: Implement**
- [ ] **Step 3: Full suite, then commit**

`feat: add load_preset action and make example_patch preset-driven`

---

## Self-Review

- Operator-facing names, no arbitrary abbreviation, no invented char limit → Task 1a ✓
- `entry` → `action_entry` → Task 1b ✓
- "home" disambiguated as pipette → Task 1a ✓
- Flow control on the context, separate actions removed → Task 2 ✓
- `cell attached` no longer a patch terminal → Task 3 ✓
- `load_preset` action, presets replace the useless `speed` param, taskrunner on
  success → Task 4a/4b ✓
- Protocols no longer end with `next_cell`; the mislabelled-disposition bug and
  its wrong test assertion fixed → Task 4c ✓

**Ordering:** Tasks 1 and 3 are independent. Task 2 touches the example
protocols, and Task 4 rewrites them — run 2 before 4 to avoid a conflict.
Task 4 depends on Task 3 (the success outcome is `"whole cell"` only) and on
Task 1 (the new action's display name follows the new convention).

Suggested order: **1 → 3 → 2 → 4**.
