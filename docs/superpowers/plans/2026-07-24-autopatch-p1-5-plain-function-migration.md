# Autopatch Orchestration — P1.5: Plain-Function Protocol Migration

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Migrate the `acq4/experiment/` engine from the graph/Action-class model
(P0/P0b) to the plain-function protocol model in `autopatch-orchestration-design.md`
§2. Protocols become `.py` files with `def run(ctx, ...)` and an optional `PARAMS`
list. Built-in actions become plain functions. `ExecutionContext` gains
`ctx.log_action()` for UI integration. The `Orchestrator` loop drops its graph walk
and exception-handler dispatch. The P1 UI's Areas 4 and 5 are rewired to match.

**Non-goal:** new capability. Every action that exists today must still work
afterward with the same device calls; this is a model change, not a feature change.

## Architecture decisions

- `ExecutionContext` grows `log_action(name)`, a context manager yielding an
  `ActionLogEntry` with `set_status()` / `set_details_widget()`, plus a public
  `on_log_action` hook the UI layer sets (via the module's context factory).
- `Action` base class, `Protocol` DAG, `Registry`, JSON serialization, and
  `ScriptAction` are **removed**. `.py` protocol files subsume `ScriptAction`.
- Built-in action classes become module-level functions in
  `acq4/experiment/actions/` — **ported 1:1**, preserving each existing body's
  device calls, params, and abort semantics (see Task 5 constraints).
- `ProtocolFile` (`acq4/experiment/protocol_file.py`) wraps a `.py` path: imports
  it, extracts `PARAMS` + `run` + docstring, builds a pyqtgraph Parameter tree.
  `ProtocolDirectory` scans the config dir and reloads on interact.
- `Orchestrator` is **edited, not replaced**: `_processCell` calls
  `protocolFile.run(ctx, **params)` in place of `_walk()`; `_walk`, `_runAction`,
  and `_handleException` are deleted. Everything else — the `_onLoopFinished`
  teardown fix, `maxRetries`, `acq4.logging_config`, pause/stop/next-cell,
  `run_sync`/`run_sync_cell` — is preserved verbatim.
- Per-action UI reporting moves from `sigActionFinished` + `Action.show()` to
  `ctx.log_action()` entry callbacks. `sigCurrentAction(cell, action)` is replaced
  by `sigCurrentCell(cell)`; `sigActionFinished` is removed.
- Exception taxonomy and flow signals are unchanged, plus one addition:
  `ABNORMAL_STATE_EXCEPTIONS` (FSM state name → exception class), which today is
  an inline `if state == "broken"` in `fsm.py`.

## Deliberate scope calls

- **Cell status vocabulary.** `handled` disappears (no handler sub-protocols —
  protocol authors use `try/except`). `done`, `skipped`, `retry`,
  `retry-exhausted`, `error` are preserved, so `maxRetries` stays. This matters
  downstream: `docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md`
  §4 enumerates the terminal set and must have `handled` removed from it once
  this plan lands. That spec's plan should be written **after** this one.
- **Uncaught `OrchestrationError` halts the run** (design §5: "the default-safe
  behavior"), matching how P1 already treats unexpected exceptions — emit
  `error` status + `sigCellFinished(cell, "error")`, then raise `AbortExperiment`.
- **Every landed action is ported**, including the ones absent from the design
  doc's §2.4 "v1 set" (`GoHome`/`GoSearch`/`GoTarget`/`GoAboveTarget`,
  `FocusTip`/`FocusTarget`, `NewPipette`, `FindTip`, `FindSurface`, `Clean`,
  `NewDataDir`). Deleting working, reviewed hardware actions is a regression
  this plan does not take on.
- **`cell_attach` and `nucleus` stay parked** (design §12). They are named in
  §2.4 but were never implemented, and inventing FSM entry/terminal sets for
  them without hardware verification is out of scope here.
- **`prompt()` stays interactive** — it keeps `choices` and returns the clicked
  label (via `acq4.util.PromptUser.prompt`), degrading to log-only when headless.
  Protocols branch on its return value.

**Tech Stack:** Python ≥3.10, `acq4.util.Qt`, `acq4.util.task` (gentletask bridge),
pyqtgraph Parameter trees, pytest.

## Global Constraints
- Test runner: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- Baseline before this plan: **136 passed** across `acq4/experiment/` +
  `acq4/modules/Autopatch/`. Every task ends with that suite green.
- Concurrency: `check_stop`/`sleep`/`Stopped`/`Event` from `acq4.util.task`.
  Never `time.sleep`/`threading`.
- Logging: `from acq4.logging_config import get_logger`. Never stdlib `logging`.
- `from acq4.util import Qt`. 2-line docstring per new file. No temporal comments.
- Commit format:
  `git commit --author="Claude (claude) <noreply@anthropic.com>" -m "<type>: <desc>\n\n🤖 Generated with [Claude Code](https://claude.ai/code)"`
- Branch: off `_reviewed` (the `autopatch-module` branch merged in #556).
  NEVER `--no-verify`.

## Task graph

```
1 (log entry) ─┬─> 5a/5b/5c (action ports) ─┬─> 7 (delete dead engine) ─> 8 (UI: Area 5) ─┐
4 (abnormal)  ─┘                            │                                            │
2 (ProtocolFile) ─┬─> 6 (orchestrator) ─────┘                                            ├─> 11 (mock smoke)
3 (ProtocolDir)  ─┴─> 9 (UI: Area 4) ──────────────────> 10 (example .py protocols) ─────┘
```

Tasks 1–4 are independent and may run in parallel.

---

## Task 1: ActionLogEntry + ctx.log_action()

**Files:**
- Create: `acq4/experiment/log_entry.py`
- Modify: `acq4/experiment/context.py`, `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_log_entry.py`

**Interfaces:**
- `ActionLogEntry(name)` — plain object (not a `QObject`; entries are created on
  the orchestrator's worker thread and must not need Qt affinity):
  - `name: str`, `start_time: float`, `end_time: float | None`,
    `status: str`, `outcome: str | None`, `details_widget: Any`
  - `set_status(message)` → sets `status`, calls `on_status(self)` if set
  - `set_details_widget(widget)` → stores it, calls `on_widget(self, widget)` if set
  - `_finish(exc)` → sets `end_time` and `outcome`: `None`→`"done"`,
    `Stopped`→`"stopped"`, `FlowSignal`→`"done"`, anything else→`"error"`
  - Callbacks `on_status`, `on_widget`, `on_finish` default to `None`; the UI
    layer assigns them from its `on_log_action` hook.
- `ExecutionContext.on_log_action: Callable[[ActionLogEntry], None] | None` — new
  public dataclass field (public because the module's context factory sets it).
- `ExecutionContext.log_action(name)` — `@contextlib.contextmanager`: builds the
  entry, calls `on_log_action(entry)` if set, yields it, and in a `finally`
  calls `entry._finish(exc)`. Exceptions are **never** suppressed. With no hook
  set (headless) the entry is still created; only the UI side-effects are absent.

`start_time`/`end_time` use `time.time()` (wall clock) — the timeline shows these
to an operator alongside `PipetteEventLog` timestamps, so a monotonic clock would
not be comparable.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_log_entry.py` covering:
- entry created with the given `name`, `end_time is None` inside the block
- normal exit → `outcome == "done"`, `end_time is not None`
- `Stopped` raised inside → propagates, `outcome == "stopped"`
- `AdvanceToNextCell` raised inside → propagates, `outcome == "done"`
- `BrokenPipette` raised inside → propagates, `outcome == "error"`
- `set_status()` updates `status`; `set_details_widget()` stores `details_widget`
- `on_log_action` hook receives the entry; a hook that assigns `on_status` sees
  each `set_status` call; a hook that assigns `on_finish` sees the final outcome
- headless (`on_log_action is None`) → block runs, entry still populated

- [ ] **Step 2: Run to verify it fails**

`/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -v`

Expected: `ModuleNotFoundError: No module named 'acq4.experiment.log_entry'`.

- [ ] **Step 3: Implement**

`acq4/experiment/log_entry.py`:
```python
"""ActionLogEntry: a per-action record used by ctx.log_action() to track status,
timing, and the live detail widget for the UI log/timeline view."""
from __future__ import annotations

import time
from typing import Any, Callable

from acq4.util.task import Stopped

from .exceptions import FlowSignal


class ActionLogEntry:
    """Tracks one action's execution: name, status, timing, details widget.

    UI layers attach callbacks (on_status, on_widget, on_finish) to drive
    widgets; in headless mode these are all None and the entry is plain data.
    """

    def __init__(self, name: str):
        self.name = name
        self.start_time: float = time.time()
        self.end_time: float | None = None
        self.status: str = ""
        self.outcome: str | None = None
        self.details_widget: Any = None
        self.on_status: Callable | None = None
        self.on_widget: Callable | None = None
        self.on_finish: Callable | None = None

    def set_status(self, message: str) -> None:
        self.status = message
        if self.on_status is not None:
            self.on_status(self)

    def set_details_widget(self, widget) -> None:
        self.details_widget = widget
        if self.on_widget is not None:
            self.on_widget(self, widget)

    def _finish(self, exc: BaseException | None) -> None:
        self.end_time = time.time()
        if exc is None:
            self.outcome = "done"
        elif isinstance(exc, Stopped):
            self.outcome = "stopped"
        elif isinstance(exc, FlowSignal):
            # Flow signals are control flow, not failure.
            self.outcome = "done"
        else:
            self.outcome = "error"
        if self.on_finish is not None:
            self.on_finish(self)
```

`acq4/experiment/context.py` — add the field and the context manager, keeping the
existing `cell`/`pipette`/`manager`/`log` fields and `_noop_log` as they are.
Update the module docstring (it currently says "handed to every Action's run()
and safeAbort()") to say it is handed to every protocol `run()` and action
function.

```python
    on_log_action: Callable[[ActionLogEntry], None] | None = field(
        default=None, repr=False
    )

    @contextlib.contextmanager
    def log_action(self, name: str):
        """Track one action for the UI: yields an ActionLogEntry, notifies the UI
        hook if attached, and records the outcome on exit. Never suppresses."""
        entry = ActionLogEntry(name)
        if self.on_log_action is not None:
            self.on_log_action(entry)
        exc_seen = None
        try:
            yield entry
        except BaseException as exc:
            exc_seen = exc
            raise
        finally:
            entry._finish(exc_seen)
```

`acq4/experiment/__init__.py` — add `from .log_entry import ActionLogEntry`.

- [ ] **Step 4: Run to verify it passes**

- [ ] **Step 5: Full suite** — `acq4/experiment/ acq4/modules/Autopatch/`, 136 + new.

- [ ] **Step 6: Commit** — `feat: add ActionLogEntry and ctx.log_action() context manager`

---

## Task 2: ProtocolFile — .py file loader

**Files:**
- Create: `acq4/experiment/protocol_file.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_protocol_file.py`

**Interfaces:**
- `ProtocolFile(path)`:
  - `name` — filename stem (set in `__init__`, available before load)
  - `description` — module docstring, stripped, or `""`
  - `params: list[dict]` — the module's `PARAMS`, or `[]`
  - `run: Callable | None` — the module's `run`
  - `param_tree: Parameter | None` — group built from `params`
  - `param_values() -> dict` — current values keyed by param name
  - `load()` — (re-)imports; on success sets everything and
    `is_loaded=True`, `load_error=None`; on failure sets `is_loaded=False`,
    `load_error=<str>` and raises `ProtocolLoadError`
  - `is_loaded: bool`, `load_error: str | None`
- `ProtocolLoadError(Exception)`

**Port two lessons from the `ScriptAction` this replaces** (`actions/script.py`,
being deleted in Task 7):
1. Register the module in `sys.modules` under its unique name **before**
   `exec_module`, and pop it in a `finally` — otherwise a protocol file that uses
   `dataclass`, `pickle`, or any `__module__` introspection fails during exec.
2. Remove any stale `importlib.util.cache_from_source(path)` bytecode before
   loading, so an operator's edit is always picked up by reload-on-interact.

A fresh `uuid4`-based module name per load is what makes reload work; do not
cache modules in `sys.modules` across loads.

`param_values()` returns only names present in `params`; a `run()` keyword with
no `PARAMS` entry keeps its signature default (design §2.5).

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_protocol_file.py` covering:
- valid file: `name`, `description` from docstring, `is_loaded`, `load_error is
  None`, `callable(run)`
- `name` is the filename stem, not the module name
- `PARAMS` → `param_tree`; `param_values()` reflects the declared defaults
- editing the tree (`param_tree.child(n).setValue(7)`) changes `param_values()`
- no `PARAMS` → `params == []`, `param_values() == {}`
- missing `run` → `ProtocolLoadError` matching "run", `is_loaded` False,
  `load_error` set
- syntax error → `ProtocolLoadError`, `load_error` set
- a file raising at import time (e.g. `raise RuntimeError("boom")` at module
  level) → `ProtocolLoadError` wrapping it
- reload after rewriting the file picks up the new `PARAMS` default
- a protocol file that uses `@dataclass` at module level loads (regression for
  the `sys.modules` registration above)
- a successful reload after a failed one clears `load_error` and sets `is_loaded`

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement** — as specced above; `_build_tree` is
  `Parameter.create(name="params", type="group", children=[dict(p) for p in params])`.
  (pyqtgraph accepts either `default` or `value` in a child spec; both yield that
  value from `.value()`, so the design doc's `"default"` style works as written.)

- [ ] **Step 4: Run to verify it passes**

- [ ] **Step 5: Full suite**

- [ ] **Step 6: Commit** — `feat: add ProtocolFile loader (.py file with PARAMS + run())`

---

## Task 3: ProtocolDirectory — config dir scanner

**Files:**
- Create: `acq4/experiment/protocol_directory.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_protocol_directory.py`

**Interfaces:**
- `ProtocolDirectory(path)`:
  - `protocols: dict[str, ProtocolFile]` — name → file, **including failed ones**
    (design §2.6: a broken file is listed with an error indicator, not hidden)
  - `scan()` — discover `.py` files, `load()` each, swallow `ProtocolLoadError`
    (it is recorded on the `ProtocolFile`), and **drop entries whose file no
    longer exists** so a deleted protocol leaves the picker
  - `reload(name)` — reload one by stem; `KeyError` if unknown
  - `reload_all()` — `scan()`
  - `get(name)` — `KeyError` if unknown
  - A missing/non-directory `path` is not an error: `scan()` returns quietly.
  - Skip dunder/private files (`__init__.py`, anything starting with `_`) so a
    protocol dir can hold helper modules without them showing as protocols.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_protocol_directory.py` covering: discovery of
`.py` files; non-`.py` ignored; `_`-prefixed ignored; a bad file recorded (not
raised) alongside a good one; rescan picks up a new file; rescan drops a deleted
file; `get()` returns the `ProtocolFile`; `get()` on a missing name raises
`KeyError`; `scan()` on a nonexistent directory is a no-op.

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run to verify it passes**

- [ ] **Step 5: Full suite**

- [ ] **Step 6: Commit** — `feat: add ProtocolDirectory for config-dir .py protocol scanning`

---

## Task 4: ABNORMAL_STATE_EXCEPTIONS mapping

**Files:**
- Modify: `acq4/experiment/exceptions.py`
- Test: `acq4/experiment/tests/test_exceptions.py`

Today `FsmCompositeAction._checkIfStateIsExceptional` hardcodes
`state == "broken" → BrokenPipette`, and `Fouled` is never raised anywhere. Task
5c needs a shared mapping; extract it here so the action port stays mechanical.

**Interfaces:**
```python
ABNORMAL_STATE_EXCEPTIONS: dict[str, type[OrchestrationError]] = {
    "broken": BrokenPipette,
    "fouled": Fouled,
}


def raise_if_abnormal(state: str, expected, context: str = "") -> None:
    """Raise the mapped OrchestrationError when the FSM lands in an abnormal
    state the caller did not declare as one of its terminals."""
```

`expected` is any container of declared terminal state names. A state in
`expected` never raises — that is how `patch` keeps `broken`/`fouled` as routable
outcomes while `reseal` treats `broken` as an exception (design §4.3).

**Behavior note to preserve:** adding `"fouled"` to the mapping is a real change
— `Fouled` becomes reachable for actions that do *not* declare `fouled` as a
terminal. `PatchAction` declares it, so `patch()` is unaffected; `reseal()` and
`clean()` will now raise `Fouled` where they previously polled forever. That is
the design's intent (§4.3), and it is the only behavior change in this plan.
State names come from `PatchPipetteStateManager`; verify both spellings against
the state classes before committing.

- [ ] **Step 1: Write the failing test** — a state in `expected` never raises;
  `"broken"` not expected → `BrokenPipette`; `"fouled"` not expected → `Fouled`;
  an unmapped state (e.g. `"seal"`) not expected → returns without raising (it is
  an internal hop, not abnormal); the message includes `context`.

- [ ] **Step 2: Run to verify it fails**

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run to verify it passes**

- [ ] **Step 5: Full suite**

- [ ] **Step 6: Commit** — `feat: add ABNORMAL_STATE_EXCEPTIONS state→exception mapping`

---

## Task 5: Port built-in actions to plain functions

Three sub-tasks, each independently committable. **These are ports, not
rewrites.** For every action: copy the existing `run()` body, replace
`self.paramValue("x")` with the function's keyword argument, replace
`self.setState(msg)` with `entry.set_status(msg)`, replace `self.results[k] = v`
with a return value, and wrap the whole body in
`with ctx.log_action("<Name>") as entry:`. Do not "improve" a device call, change
an entry state, or drop a step. If a body looks wrong, flag it and leave it.

Function naming: snake_case of the registered action name (`GoHome` → `go_home`,
`FindTip` → `find_tip`, `NewDataDir` → `new_data_dir`).

Every function is exported from `acq4/experiment/actions/__init__.py` so a
protocol author writes `from acq4.experiment.actions import patch, cellfie`.

### Task 5a: flow, prompt, storage

**Files:**
- Rewrite: `acq4/experiment/actions/flow.py`, `actions/prompt.py`, `actions/storage.py`
- Modify: `acq4/experiment/actions/__init__.py`
- Test: `acq4/experiment/tests/test_actions_flow.py` (replaces `test_flow_actions.py`)

Flow — no `log_action` wrapper (they raise immediately and carry no work):
```python
def next_cell(ctx) -> None:
    raise AdvanceToNextCell("advance to next cell")


def retry_cell(ctx) -> None:
    raise RetryCurrentCell("retry current cell")


def abort(ctx) -> None:
    raise AbortExperiment("abort experiment")
```

Prompt — **keeps** the operator interaction from `PromptAction`:
```python
def prompt(ctx, message: str = "", title: str = "Prompt", choices=("OK",)) -> str:
    """Ask the operator to choose from labeled buttons; returns the clicked label.
    Non-modal and stop-aware. Headless (no UI): logs and returns the first choice."""
```
Accept `choices` as either a sequence or the legacy comma-separated string, so a
protocol can write `choices="Retry,Skip"` or `choices=["Retry", "Skip"]`; empty
→ `["OK"]`. Delegate to `acq4.util.PromptUser.prompt(title, message, choices)`,
`entry.set_status(message)`, and `ctx.log(message)` exactly as the class did.
Headless detection: no `QApplication` instance → return `choices[0]` after
logging (the design's "headless-safe, does not block on a dialog without UI").

Storage — port `NewDataDirAction.run` verbatim, including the walk-up-five-levels
parent search and the `expUnit` info flag; return the created directory instead of
stashing it in `self.results["dir"]`:
```python
def new_data_dir(ctx, level: str = "Cell", set_current: bool = True):
```

- [ ] **Step 1: Write the failing test** — port `test_flow_actions.py` and
  `test_storage.py` assertions to the function API, then add: `prompt` returns the
  clicked label; `prompt` with a comma-separated `choices` string splits it;
  `prompt` headless returns the first choice and logs; `prompt` creates a
  `"Prompt"` log entry; `new_data_dir` returns the directory, honors
  `set_current=False`, and does not nest a `Cell` inside a `Cell`.
- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Full suite** (old class-based tests still pass — nothing deleted yet)
- [ ] **Step 6: Commit** — `refactor: port flow, prompt, and storage actions to plain functions`

### Task 5b: device actions

**Files:**
- Rewrite: `acq4/experiment/actions/device.py`
- Modify: `acq4/experiment/actions/__init__.py`
- Test: `acq4/experiment/tests/test_actions_device.py` (replaces `test_device_actions.py`)

Port **all twelve**, preserving the two shared bases as private helpers:

| Class | Function | Must preserve |
|---|---|---|
| `GoHomeAction` … `GoAboveTargetAction` | `go_home`, `go_search`, `go_approach`, `go_target`, `go_above_target` | `ctx.pipette.pipetteDevice.moveTo(<position>, speed).wait()` — **not** `pipette.moveTo` |
| `FocusTipAction` / `FocusTargetAction` | `focus_tip` / `focus_target` | `pip.focusOnTip` / `pip.focusOnTarget`, `.wait()` |
| `NewPipetteAction` | `new_pipette` | `ctx.pipette.newPipette().wait()`, failure → `OrchestrationError` |
| `FindTipAction` | `find_tip` | moveTo `aboveTarget` → `clampDevice.autoPipetteOffset()` → `pipetteDevice.iterativelyFindTip()`, failure → `OrchestrationError` |
| `FindSurfaceAction` | `find_surface` | `scope.findSurfaceDepth(imager)`, `ValueError` → `OrchestrationError`; **returns the depth** |
| `CellfieAction` | `cellfie` | `focusOnTarget("fast").wait()`, the `height`/`step` params, the `target_z - height/2` z-range, `getCurrentDir().getDir("cellfie", create=True)`, `run_image_sequence(...).wait()`, **then** `ctx.cell.initializeTracker(imager, use_cellpose=True)` |
| `TaskAction` | `run_task` | the `listInterfaces("taskRunnerModule")` + `clampName in mod.docks` search, missing-module → `OrchestrationError`, `timeout or max(30, expected*20)`, `run_in_gui_thread(taskrunner.runSequence, store=...)` |

Keep the module docstring's note that these drive real hardware and are exercised
by live testing, and keep `FindTip`'s and `TaskAction`'s explanatory comments and
the `TODO` about the operator still opening the TaskRunner module.

The plan's earlier draft specified a `goto(ctx, speed)` using `pip.setTarget()` /
`pip.moveTo("target", speed)` and a `cellfie()` that only initialized the tracker.
Both are wrong — `PatchPipette` has no `setTarget`/`moveTo`, and the z-stack save
*is* the cellfie. Ignore that draft.

- [ ] **Step 1: Write the failing test** — port `test_device_actions.py` to the
  function API and extend the fake pipette so each ported function is covered:
  the five named moves pass the right position string; focus dispatches to the
  right method; `find_tip` calls the three steps in order and maps a raise to
  `OrchestrationError`; `find_surface` returns the depth and maps `ValueError`;
  `cellfie` focuses, saves a z-stack over the expected range, then initializes
  the tracker; `run_task` finds the module by clamp name and raises when none
  matches; each function creates a log entry with its expected name.
- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Full suite**
- [ ] **Step 6: Commit** — `refactor: port device actions to plain functions`

### Task 5c: FSM actions

**Files:**
- Create: `acq4/experiment/actions/fsm.py` (from `acq4/experiment/fsm.py`)
- Modify: `acq4/experiment/actions/__init__.py`
- Test: `acq4/experiment/tests/test_actions_fsm.py` (replaces `test_fsm.py`)

One private driver plus three public functions:

```python
def _drive_fsm(ctx, name, entry_state, terminals, entry_config=None,
               poll_interval=0.1) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal)."""


def patch(ctx, **entry_config) -> str: ...     # entry "approach"
def reseal(ctx, **entry_config) -> str: ...    # entry "reseal"
def clean(ctx, **entry_config) -> str: ...     # entry "clean"
```

Preserve from `FsmCompositeAction` exactly:
- entry states: `patch` → **`"approach"`** (not `"cell detect"`), `reseal` →
  `"reseal"`, `clean` → `"clean"`.
- terminal sets: patch `{"whole cell", "cell attached", "bath", "broken",
  "fouled"}`; reseal `{"outside out", "whole cell"}`; clean `{"out"}`.
- `pip.setState(entry_state, **dict(entry_config or {}))` — a fresh dict per
  call, never a shared mutable default.
- the poll loop returns the reached terminal state name, `sleep(poll_interval)`
  between polls.
- **safe abort:** on a cooperative stop, call `pip.getState().stop("orchestration
  abort", wait=True)` — the FSM's own declared fallback state, mirroring
  MultiPatch's Cancel button (`pipetteControl._cancelClicked`). Do **not**
  substitute `pip.setState("bath")`; the existing comment explains why and must
  be carried over. Guard for `ctx.pipette` / `getState()` being `None` as the
  class did.
  **Abort on the `Stopped` path only — not in a bare `finally`.** In the class
  model `safeAbort` was invoked solely by `Orchestrator._runAction`'s
  `except Stopped:` branch, so it did not run on success and did not run when an
  abnormal state raised. A bare `finally` would stop the terminal state's job the
  instant `patch()` succeeded, dropping the pipette out of the whole-cell state
  the protocol just achieved and breaking any recording that follows. Design
  §4.2's illustrative snippet shows a `finally`; that snippet is wrong on this
  point and the class's actual invocation site is the authority.

Add `check_stop()` at the top of each poll iteration (the class relied on
`sleep()` to raise; an explicit `check_stop()` makes a stop between polls
deterministic and is what design §4.2 shows).

`_drive_fsm` runs inside `ctx.log_action(name)` and reports
`entry.set_status(f"driving FSM from {entry_state!r}")` then
`entry.set_status(f"reached {state!r}")`, matching the class's `setState` calls.

- [ ] **Step 1: Write the failing test** — port `test_fsm.py`, plus: each
  function's entry state; each returns its reached terminal; `reseal` on
  `"broken"` raises `BrokenPipette`; `patch` on `"broken"` **returns** `"broken"`
  (declared terminal); `reseal` on `"fouled"` raises `Fouled`; `Stopped` mid-poll
  propagates *and* the abort path called `state.stop(..., wait=True)`;
  `entry_config` reaches `setState` and two calls do not share a dict; a log
  entry is created with the right name.
- [ ] **Step 2: Run to verify it fails**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify it passes**
- [ ] **Step 5: Full suite**
- [ ] **Step 6: Commit** — `refactor: port FSM composite actions to plain functions`

---

## Task 6: Orchestrator — graph walk → direct function call

**Files:**
- Modify: `acq4/experiment/orchestrator.py`
- Modify: `acq4/experiment/tests/test_orchestrator_walk.py` → rename to
  `test_orchestrator_protocol.py`
- Modify: `acq4/experiment/tests/test_orchestrator_loop.py`,
  `test_orchestrator_exceptions.py`

**Edit the existing file. Do not replace it.** Preserve verbatim: the
`acq4.logging_config` logger, `start()`/`_onLoopFinished()` (the exit-segfault
fix — `acq4/modules/Autopatch/tests/test_teardown.py` asserts refcount teardown
against it), `run_sync`/`run_sync_cell`, `pause`/`resume`/`stop`/
`requestNextCell`/`wait`, `_checkPause`, `_runLoopBody`, `enqueue`,
`_defaultContext`, and `maxRetries`. Do not add `sigStatus` emissions to
`pause()`/`resume()` — `_checkPause` already reports paused/running from the
worker thread.

**Changes:**

1. `__init__(self, protocolFile, manager=None, contextFactory=None, maxRetries=100)`
   — the first argument is a `ProtocolFile`; store it as `self.protocolFile`.
2. **Signals:** replace `sigCurrentAction = Qt.Signal(object, object)` with
   `sigCurrentCell = Qt.Signal(object)` (cell, or `None` when idle) and **remove**
   `sigActionFinished`. Per-action reporting now flows through
   `ctx.log_action()`; the orchestrator no longer sees individual actions.
   `_runLoopBody`'s `finally` emits `sigCurrentCell.emit(None)`.
3. Delete `_walk`, `_runAction`, and `_handleException`.
4. `_processCell(cell)` keeps its retry loop and becomes:
   - honor `self._nextCellRequested` before starting (emit `skipped`, return)
   - `self.sigStatus.emit("running")`; `ctx = self._contextFactory(cell)`;
     `self.sigCurrentCell.emit(cell)`
   - `self.protocolFile.run(ctx, **self.protocolFile.param_values())`
   - `except AdvanceToNextCell:` → `sigCellFinished(cell, "skipped")`, return
   - `except RetryCurrentCell:` → `retries += 1`; over `maxRetries` →
     `"retry-exhausted"`, return; else `"retry"` and `continue` (restart the
     protocol for the same cell, in place — do **not** re-queue, which would
     reorder the queue and silently no-op under `run_sync_cell`)
   - `except FlowSignal:` → `raise` (`AbortExperiment` must keep propagating and
     must not be mistaken for a bug by the broad handler below)
   - `except Stopped:` → `raise` (cooperative operator stop; the action's own
     `try/finally` already unwound the device)
   - `except OrchestrationError as exc:` → `logger.exception(...)`,
     `sigStatus("error")`, `sigCellFinished(cell, "error")`, then
     `raise AbortExperiment(...) from exc` — design §5's catch-all safety net:
     an uncaught orchestration error halts the run rather than blazing through
     the remaining cells
   - `except Exception as exc:` → same as above (unchanged from P1)
   - `else:` → `sigCellFinished(cell, "done")`, return
5. `requestNextCell`'s comment must be updated: the request is now honored at
   cell boundaries only (there is no action boundary for the orchestrator to
   check — a running protocol function is opaque to it). A protocol author who
   wants finer granularity checks `ctx` cooperatively. This is a real narrowing
   of behavior versus P1's per-action check; state it in the comment.

**Status vocabulary after this task:** `done`, `skipped`, `retry`,
`retry-exhausted`, `error`. `handled` is gone.

- [ ] **Step 1: Rewrite `test_orchestrator_walk.py` as `test_orchestrator_protocol.py`**

Build `ProtocolFile` fixtures from `tmp_path`, then override `pf.run` with a
sentinel where the test needs to raise. Cover: `run` is called with the ctx;
`param_values()` are passed as kwargs and reflect tree edits; `AdvanceToNextCell`
→ `skipped`; `RetryCurrentCell` → `retry` then re-runs the same cell, and
`maxRetries` exhaustion → `retry-exhausted`; `AbortExperiment` propagates;
`OrchestrationError` → `error` **and** raises `AbortExperiment`; an unexpected
`RuntimeError` → `error` and raises `AbortExperiment`; `Stopped` propagates;
`sigCurrentCell` emits the cell then `None` after the loop; `requestNextCell`
before a cell → `skipped` without calling `run`.

- [ ] **Step 2: Run to see failures**

- [ ] **Step 3: Edit the orchestrator**

- [ ] **Step 4: Adapt the loop and exception tests**

`test_orchestrator_loop.py`: replace `_BlockingAction` with a `ProtocolFile`
whose `run` blocks on an `Event`, keeping each test's actual assertion (queue
order, pause gating, stop propagation, `sigStatus` sequence) intact.

`test_orchestrator_exceptions.py`: the handler-sub-protocol dispatch tests are
testing a feature that no longer exists — delete them, and keep/port anything
asserting flow-signal propagation or the catch-all net. Note in the commit
message which tests were dropped and why. Leave `conftest.py` alone here; Task 7
cleans it.

- [ ] **Step 5: Full suite** — `acq4/experiment/` green. `acq4/modules/Autopatch/`
  will now fail (the panels still use `sigCurrentAction`/`sigActionFinished`, and
  `ProtocolPanel` still loads JSON). Record the failing set in the commit message;
  Tasks 8–10 fix them. Do not paper over them.

- [ ] **Step 6: Commit** — `refactor: replace graph-walk Orchestrator with plain-function protocol call`

---

## Task 7: Remove obsolete engine code

**Delete:**
- `acq4/experiment/action.py`, `protocol.py`, `registry.py`, `fsm.py`
- `acq4/experiment/actions/script.py` (`.py` protocol files subsume it;
  `ScriptError` stays in `exceptions.py` only if something still raises it —
  otherwise remove that class too and its test)
- `acq4/experiment/tests/test_action.py`, `test_registry.py`, `test_protocol.py`,
  `test_serialization.py`, `test_fakes.py`, `test_script_action.py`,
  `test_flow_actions.py`, `test_device_actions.py`, `test_fsm.py`,
  `test_storage.py` (each superseded by a Task 5 test file)

- [ ] **Step 1: Verify nothing outside `acq4/experiment/` imports the old symbols**

```bash
grep -rn "experiment.action\b\|experiment\.protocol\b\|experiment\.registry\|experiment\.fsm\|register_action\|get_action_class\|action_type_name\|Protocol\.load_json\|Protocol\.save_json\|FsmCompositeAction\|PatchAction\|ScriptAction" --include="*.py" . | grep -v "^./acq4/experiment/"
```

Expected hits at this point: `acq4/modules/Autopatch/protocol_panel.py` and
`example_protocols/generate.py` (Tasks 9 and 10). Anything else must be fixed
before deleting.

- [ ] **Step 2: `git rm` the files above**

- [ ] **Step 3: Gut `acq4/experiment/tests/conftest.py`** — drop the Action-class
  fakes, keep (and extend as the Task 5 tests need) the fake-pipette fixture.

- [ ] **Step 4: Update `acq4/experiment/__init__.py`** — export
  `ExecutionContext`, `ActionLogEntry`, `ProtocolFile`, `ProtocolLoadError`,
  `ProtocolDirectory`, `Orchestrator`, `from . import actions`,
  `from . import exceptions`. Remove `Action`, `Protocol`, the registry
  functions, and `from . import fsm`. Update the package docstring — it still
  describes "composable Actions, protocol graphs".

- [ ] **Step 5: Full suite** — `acq4/experiment/` fully green with no skips.

- [ ] **Step 6: Commit** — `chore: remove obsolete Action-class engine (replaced by plain-function model)`

---

## Task 8: UI — Area 5 timeline and details from log entries

**Files:**
- Modify: `acq4/modules/Autopatch/context_factory.py`, `cell_panel.py`,
  `status_panel.py`, `Autopatch.py`
- Modify: `acq4/modules/Autopatch/tests/test_context_factory.py`,
  `test_cell_timeline.py`, `test_cell_log_and_show.py`, `test_cell_panel.py`,
  `test_status_panel.py`

This is the task the earlier draft plan omitted entirely, and without it Area 5
goes dark: `sigActionFinished` was the *only* feed for the executed-path timeline
and `Action.show()` the only feed for the live detail widget.

**Threading is the crux.** `ctx.log_action()` is called from the orchestrator's
worker thread, so `on_log_action` and the entry callbacks all fire off the GUI
thread. They must not touch widgets directly. Follow the pattern already
established by `CellPanel.appendLog`/`sigLogMessage`: the callback emits a Qt
signal and an auto-queued connection marshals it onto the GUI thread.

**`context_factory.make_context_factory`** gains an `onLogAction` parameter and
sets `ExecutionContext.on_log_action`, cell-bound the same way `log` is
(`partial(onLogAction, cell)`), so the panel knows which cell an entry belongs to.

**`CellPanel`:**
- `sigActionEntry = Qt.Signal(object, object, str)` — cell, entry, phase
  (`"started"` / `"status"` / `"finished"`). The `on_log_action` callback assigns
  `entry.on_status` / `entry.on_finish` / `entry.on_widget` and emits this
  signal; GUI-thread slots update `timelineList`, `_timelines`, and
  `showContainer`.
- Timeline rows: a row is appended when an entry starts (design §7 Area 5 wants
  `⏳ running` then `✓ done`), and updated in place with the outcome and
  elapsed time when it finishes. Keep `_timelines[id(cell)]` as the frozen
  replay for a non-current cell, and keep the existing rule that only the
  *selected* cell's rows render live.
- `set_details_widget` replaces `action.show()`: on `on_widget`, if that cell is
  selected, put the widget in `showContainer`; `_clearShowContainer` on entry
  finish and on selection change (the existing "must not linger" rule).
- **A widget created on the worker thread is not safe to parent into the GUI
  tree.** `set_details_widget` is documented as the action handing the UI a live
  widget; an action that builds one must do it via `run_in_gui_thread`. Assert
  this in the test with a widget created on the GUI thread, and note the
  constraint in `log_entry.py`'s `set_details_widget` docstring.
- Replace the `sigCurrentAction` connection with `sigCurrentCell`; the row label
  becomes `f"cell {id(cell)} — running"` and the action name comes from the
  current entry.
- `unbindOrchestrator` must disconnect exactly the set `bindOrchestrator`
  connected — keep them symmetric (there are existing tests asserting no
  dangling connections).

**`StatusPanel`:** `_onCurrentAction(cell, action)` → `_onCurrentCell(cell)`; the
`currentActionLabel` text now comes from the log-entry stream (name + status)
rather than `action.name`. Wire it through the same cell-bound entry signal, or
have `CellPanel` own the entry stream and expose a signal `StatusPanel` consumes
— pick one and keep the disconnect symmetric.

**`Autopatch.py`:** pass `onLogAction=self.cellPanel.onLogAction` into
`make_context_factory`, and keep `teardown()` unchanged apart from any new
connection it must sever. `teardown()`'s guarantees are covered by
`test_teardown.py` — that file must stay green **without modification**; if it
fails, the new wiring introduced a reference cycle and the wiring is wrong.

- [ ] **Step 1: Write the failing tests** — a worker-thread `log_action` reaches
  the timeline on the GUI thread; a started entry appends a running row; a
  finished entry updates that row with its outcome; a non-selected cell's rows
  are recorded but not rendered; selecting a cell replays its rows; a details
  widget appears for the selected cell and is cleared on finish and on selection
  change; `unbindOrchestrator` leaves no connection; `test_teardown.py` still
  passes untouched.
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Full suite** — `acq4/experiment/` + `acq4/modules/Autopatch/`;
  only the Area 4 tests (Task 9) may still fail.
- [ ] **Step 6: Commit** — `feat: drive Autopatch Area 5 timeline and details from ctx.log_action entries`

---

## Task 9: UI — Area 4 protocol selection

**Files:**
- Modify: `acq4/modules/Autopatch/protocol_panel.py`, `Autopatch.py`
- Modify: `acq4/modules/Autopatch/tests/test_protocol_panel.py`,
  `test_protocol_panel_params.py`, `test_window_skeleton.py`,
  `test_window_integration.py`

`ProtocolPanel` today lists `*.json`, calls `Protocol.load_json`, and hand-builds
a mirror param tree from `publicParams` (writing edits back into each node's
`Action.params`). With `ProtocolFile` the entire mirroring layer disappears —
`pf.param_tree` *is* the tree, and `pf.param_values()` is what the orchestrator
passes to `run()`.

**Changes:**
- Hold a `ProtocolDirectory(protocolDir)`; `refreshFileList()` → `scan()` +
  repopulate from `directory.protocols` (sorted by name).
- A protocol that failed to load is listed with an error indicator; selecting it
  shows `load_error` instead of a param tree and does not emit a loaded protocol
  (design §2.6).
- `loadSelected()` → `directory.reload(name)` then `get(name)`;
  `self.paramTree.setParameters(pf.param_tree, showTop=False)`;
  `sigProtocolLoaded.emit(pf)` — the payload is now a `ProtocolFile`.
- Rename the `Refresh` button to **`Reload`** (design §7 Area 4) and keep it
  wired to a rescan; reload-on-interact means the picker also rescans when it is
  opened.
- Add **`Open in editor`**: `os.environ.get("EDITOR")` if set, else
  `xdg-open`, via `subprocess.Popen([editor, pf.path])`. Disabled when nothing
  is selected. Do not block the GUI thread on it.
- `Autopatch.py`: `_onProtocolLoaded(protocolFile)` passes it as the
  orchestrator's first argument. Everything else there stays.

- [ ] **Step 1: Write the failing tests** — picker lists `.py` files sorted; a
  broken file is listed and shows its error without emitting; selecting a good
  file emits a `ProtocolFile` and installs its own param tree; editing the tree
  changes `pf.param_values()` (no mirror layer); `Reload` picks up a file edited
  on disk (new `PARAMS` default appears) and a newly added file; `Open in editor`
  invokes the configured editor with the file path (patched `Popen`) and is
  disabled with no selection.
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Full suite** — everything green except `test_example_protocols.py`
  (Task 10).
- [ ] **Step 6: Commit** — `feat: Autopatch Area 4 lists .py protocols with reload and external editor`

---

## Task 10: Example protocols as .py files

**Files:**
- Delete: `acq4/modules/Autopatch/example_protocols/generate.py`,
  `example_patch.json`, `example_prompt.json`
- Create: `acq4/modules/Autopatch/example_protocols/example_prompt.py`,
  `example_patch.py`
- Modify: `acq4/modules/Autopatch/example_protocols/__init__.py`
- Modify: `acq4/modules/Autopatch/tests/test_example_protocols.py`

`generate.py` existed only to guarantee the shipped JSON round-tripped through
`Protocol.load_json`. Plain `.py` protocols need no generator — delete it.
`install_example_protocols` copies `*.py` instead of `*.json`, and must skip its
own `__init__.py` (and any `_`-prefixed helper) so it never installs the package
machinery as a protocol.

`example_prompt.py` — hardware-free, exercises picker + params + run loop:
```python
"""Ask the operator a yes/no question, then advance to the next cell.
Hardware-free demo protocol."""
from acq4.experiment.actions import next_cell, prompt

PARAMS = [{"name": "message", "type": "str", "default": "Ready to patch this cell?"}]


def run(ctx, message="Ready to patch this cell?"):
    prompt(ctx, message=message)
    next_cell(ctx)
```

`example_patch.py` — the realistic template, and the place the new model actually
pays off: what used to be a graph plus a catch-all handler sub-protocol becomes
readable control flow.
```python
"""Capture a cellfie, move to the approach position, then drive the patch FSM.
Any pipette problem prompts the operator and aborts the run."""
from acq4.experiment.actions import abort, cellfie, go_approach, next_cell, patch, prompt
from acq4.experiment.exceptions import OrchestrationError

PARAMS = [{"name": "speed", "type": "str", "default": "fast"}]


def run(ctx, speed="fast"):
    try:
        cellfie(ctx)
        go_approach(ctx, speed=speed)
        outcome = patch(ctx)
        ctx.log(f"patch outcome: {outcome}")
        next_cell(ctx)
    except OrchestrationError as exc:
        prompt(ctx, message=f"Pipette problem — intervene: {exc}")
        abort(ctx)
```

- [ ] **Step 1: Write the failing tests** — rewrite `test_example_protocols.py`:
  each bundled `.py` loads through `ProtocolFile` (no import error, has `run`,
  `PARAMS` builds a tree); `install_example_protocols` copies both into an empty
  dir, skips `__init__.py`, and never overwrites an existing file of the same
  name; a `ProtocolDirectory` over the installed dir lists exactly the two
  examples; `example_prompt` runs end-to-end through `Orchestrator.run_sync_cell`
  with a headless ctx and finishes the cell as `skipped` (it calls `next_cell`).
- [ ] **Step 2: Run to verify they fail**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run to verify they pass**
- [ ] **Step 5: Full suite** — all of `acq4/experiment/` +
  `acq4/modules/Autopatch/` green, ≥136 tests, **pristine output**.
- [ ] **Step 6: Commit** — `feat: ship example Autopatch protocols as .py files`

---

## Task 11: Live smoke test against config/mock

Not a unit test — the end-to-end check that the migrated stack actually runs.

- [ ] **Step 1: Confirm `Autopatch:` is registered in `config/mock/default.cfg`**
  (that file is gitignored, so a fresh checkout needs the entry re-added — see
  the `Autopatch:` module stanza used in P1).
- [ ] **Step 2: Launch acq4 with the mock config, open Autopatch.** Verify: the
  protocol picker lists `example_prompt` and `example_patch` from
  `<configDir>/autopatch_protocols/`; `Reload` picks up an edit made on disk;
  `Open in editor` launches; selecting a protocol shows its params.
- [ ] **Step 3: Seed cells** ("Scatter fake cells"), select a pipette, run
  `example_prompt` with Start. Verify: the big status indicator moves
  running→waiting, the timeline shows the Prompt entry going running→done, the
  cell row ends `skipped`, and the log pane shows the prompt message.
- [ ] **Step 4: Exercise Stop and Pause/Resume** mid-run; verify the button
  gating still matches `StatusPanel._updateButtons` and no exception reaches the
  log.
- [ ] **Step 5: Close the window and quit acq4.** Verify a clean exit — no
  segfault (this is what `teardown()` + `_onLoopFinished` protect) and no
  traceback in the log.
- [ ] **Step 6: Commit** any fixes found; note in the commit what the smoke test
  caught.

---

## Self-Review

**Spec coverage (design §2–5, §7):**
- Protocol as `.py` with `run(ctx)` + `PARAMS` → Task 2 ✓
- Config-dir scan + reload-on-interact + error indicator → Tasks 3, 9 ✓
- `ctx.log_action()` with `set_status`/`set_details_widget` → Task 1 ✓
- Actions as plain functions using `log_action` → Tasks 5a/5b/5c ✓
- Orchestrator calls `run(ctx, **params)`; flow signals routed; catch-all net
  halts the run → Task 6 ✓
- FSM poll-to-terminal with `try/finally` safe abort → Task 5c ✓
- Abnormal state → mapped exception unless declared terminal → Tasks 4, 5c ✓
- Mid-run conditions handled by plain `try/except` in the protocol (§2.7) →
  demonstrated by Task 10's `example_patch.py` ✓
- Dead Action/Protocol/Registry/Script code removed → Task 7 ✓
- Area 4: `.py` picker, params, Reload, Open in editor → Task 9 ✓
- Area 5: executed-path timeline + live detail widgets, no "pending" steps →
  Task 8 ✓

**Deliberately not covered here:**
- Area 5's "Reuse completed cells" button — its own design spec
  (`2026-07-24-autopatch-reuse-completed-cells-design.md`); needs its terminal-status
  list re-derived after this plan lands (`handled` is removed).
- `cell_attach` / `nucleus` actions, RawState single-state actions, the global
  cross-action abnormal watcher, file-watch auto-reload — design §12 parked items.
- Areas 1/2, the interleaved find+patch loop, Camera integration — P2.
- The §4.4 state-classification table verified against each state's `run()` —
  still open; Task 4's `ABNORMAL_STATE_EXCEPTIONS` spellings must be checked
  against the state classes, but the full table is not audited here.

**Risk notes:**
- Task 6 knowingly leaves `acq4/modules/Autopatch/` red until Task 8/9/10. Any
  worker who "fixes" that by reinstating `sigActionFinished` has broken the
  migration — the plan's whole point is that per-action reporting moves to
  `log_action`.
- Task 8 is the highest-risk task: it crosses the worker/GUI thread boundary and
  touches the object graph that `test_teardown.py` guards. That file must pass
  unmodified.
