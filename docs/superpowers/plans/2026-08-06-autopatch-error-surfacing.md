# Autopatch §5.1 Error Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an Autopatch run halts, show the operator the actual exception — a one-line headline in Area 3's instruction band, the full traceback in Area 5 with Copy, and a link into acq4's log window — instead of today's empty red band.

**Architecture:** The engine renders every failure to **formatted strings at the moment it fails** (`error_record.describe_exception`) and never hands a live exception to the UI. Two carriers: `ActionLogEntry` gains `exc_type`/`exc_message`/`traceback_text` for the failing action (Area 5's per-cell view), and a new `Orchestrator.sigRunError(RunErrorRecord)` carries the run-level halt (Area 3's band + log link), because a producer failing during a refill has no cell and no entry to hang anything on.

**Tech Stack:** Python 3.12, PyQt (via `acq4.util.Qt`), pytest. No new dependencies.

## Global Constraints

- **Python is `/home/martin/.miniforge3/envs/acq4-gl/bin/python`.** Run tests as `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest ...`. Never bare `python`; never the `acq4-torch` env.
- **Worktree and branch.** Before every `git add`/`git commit`, confirm `git rev-parse --show-toplevel` is `/home/martin/src/acq4/acq4/.claude/worktrees/happy-easley-8b68a0` **and** `git branch --show-current` is `claude/autopatch-error-surfacing`. If either is wrong, stop and report. Never commit to `_staging`/`_reviewed`/`main`.
- **Commit format.** Conventional commit, imperative mood, with the CLAUDE.md footer — use two `-m` flags so the footer actually lands (past branches lost it by using a single-line `-m`):
  ```bash
  git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
      -m "feat: subject line here" \
      -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
  ```
- **Never retain a live exception, traceback, or `ActionLogEntry` anywhere in the UI layer.** An exception holds its traceback, which holds every frame, which holds those frames' locals — image stacks, device handles, the execution context. `CellPanel`'s stores hold `id(...)` keys and plain strings for exactly this reason (see `cell_panel.py`'s `_entryTimelineLoc` comment and `tests/test_teardown.py`). Store formatted text only.
- **Mutation-test every test whose assertion is about absence or about a value that could already be trivially correct** (`is None`, `== []`, `is False`, "nothing was mounted"). Apply the defect — delete the guard, make the branch unconditional — run the test, and confirm it *fails* before moving on. Three vacuous tests shipped on this project's earlier branches; all three read fine and all three were caught only this way. Each such step below says explicitly what mutation to apply.
- **Comments must be evergreen and must not carry unsound safety arguments.** Do not write "recent change"/"was previously" prose. If you justify thread-safety, justify what actually holds.
- The design doc is `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` — **outside this worktree and gitignored**. Task 7 edits it. Do not `git add` it.

## Background the implementer needs

Read these before starting; they are why the plan looks the way it does.

1. **Every orchestrator halt already logs and already emits `"error"`, but the status does not stick.** Measured on the landed code with a throwaway probe (a protocol that raises `RuntimeError("boom")`, one cell, `run_sync()`):

   ```
   statuses: ['running', 'running', 'error', 'waiting']
   ```

   `Orchestrator._runLoopBody`'s `finally` emits `"waiting"` unconditionally, and `AbortExperiment` is a `FlowSignal`, so it is *not* caught by that method's `except Stopped` — it propagates straight through the `finally`. `StatusPanel._onStatus` currently does `self.instructionLabel.setVisible(status == "error")`, so the band is shown and hidden within the same run. **Writing §5.1's headline into that widget without changing its visibility rule would still render nothing.** Band visibility must key off *having a last-error record*, not off the transient status. Task 5 does that; Task 3 pins the status sequence with a regression test so a later reader does not "simplify" it back.

2. **There are four halt sites**, all in `acq4/experiment/orchestrator.py`, and all already shaped `sigStatus.emit("error")` → `_reportFinished(cell, "error")` → `raise AbortExperiment(...) from exc`:
   - `_refillQueue`, producer raised — **no cell**.
   - `_processCell`, `except OrchestrationError as exc`.
   - `_processCell`, `except Exception as exc`.
   - `_processCell`, the swallowed-flow-signal branch in the `else` clause (the local is named `signal`, not `exc`).

3. **`ActionLogEntry._finish(exc)` already receives the exception and drops it** after mapping it to `self.outcome`. It is called from `ExecutionContext.log_action`'s `finally`, on the worker thread, and it fires `on_finish` — which `CellPanel.onLogAction` has wired to `sigActionEntry(cell, entry, "finished")`. So the UI already gets a GUI-thread delivery at exactly the right moment; it just has nothing to read.

4. **Area 5's `showContainer` is cleared on cell-selection change** (`_onCellSelectionChanged` calls `_clearShowContainer()`). So an error block mounted only at `"finished"` time would vanish the moment the operator clicks another cell and would never come back. The block must be re-renderable from a per-cell store, like the timeline and log already are.

## File Structure

| File | Responsibility |
| --- | --- |
| `acq4/experiment/error_record.py` (**new**) | `describe_exception()` and the frozen `RunErrorRecord`. The one place an exception becomes text, shared by both carriers so the two renderings cannot diverge. |
| `acq4/experiment/log_entry.py` (modify) | `ActionLogEntry` captures `exc_type`/`exc_message`/`traceback_text`, errors only. |
| `acq4/experiment/orchestrator.py` (modify) | `sigRunError` signal + `_reportRunError()` helper called at all four halt sites. |
| `acq4/modules/Autopatch/status_panel.py` (modify) | Area 3: last-error record, band headline, band visibility, Show-in-log button. |
| `acq4/modules/Autopatch/cell_panel.py` (modify) | Area 5: per-cell error store and the error block (traceback + Copy + Show in log + cell token). |
| `acq4/experiment/tests/test_error_record.py` (**new**) | Task 1's tests. |
| `acq4/modules/Autopatch/tests/test_cell_error_block.py` (**new**) | Task 6's tests. |

Existing test files extended: `acq4/experiment/tests/test_log_entry.py`, `acq4/experiment/tests/test_orchestrator_exceptions.py`, `acq4/modules/Autopatch/tests/test_status_panel.py`, `acq4/modules/Autopatch/tests/test_teardown.py`.

**Out of scope, decided by the owner:** the New-slice `HelpfulException("Storage directory has not been set.")` instruction path (§7 Area 1). This plan covers run halts only.

---

### Task 1: `error_record.py` — turning an exception into retainable text

**Files:**
- Create: `acq4/experiment/error_record.py`
- Test: `acq4/experiment/tests/test_error_record.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `describe_exception(exc: BaseException) -> tuple[str, str, str]` returning `(exc_type, exc_message, traceback_text)`.
  - `RunErrorRecord` — frozen dataclass with fields `exc_type: str`, `exc_message: str`, `traceback_text: str`, `cell_repr: str | None = None`, and classmethod `RunErrorRecord.from_exception(exc: BaseException, cell=None) -> RunErrorRecord`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_error_record.py`:

```python
"""Tests for error_record: an exception rendered to retainable text, and the
run-level record the orchestrator emits when a run halts."""
import gc
import weakref

from acq4.experiment.error_record import RunErrorRecord, describe_exception


def _raise_and_describe():
    """Raise, catch, and describe -- in a frame that has returned by the time
    the caller inspects the result, so nothing this frame held is still live."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        return describe_exception(exc), weakref.ref(exc)


def test_describe_exception_renders_type_message_and_traceback():
    (exc_type, message, tb_text), _ref = _raise_and_describe()
    assert exc_type == "ValueError"
    assert message == "boom"
    assert "ValueError: boom" in tb_text
    assert "_raise_and_describe" in tb_text


def test_describe_exception_includes_the_cause_chain():
    # Every orchestrator halt is `raise AbortExperiment(...) from exc`, so the
    # frames that explain the failure are in the cause, not the wrapper.
    try:
        try:
            raise KeyError("inner-detail")
        except KeyError as inner:
            raise RuntimeError("outer-wrapper") from inner
    except RuntimeError as exc:
        _type, _message, tb_text = describe_exception(exc)
    assert "inner-detail" in tb_text
    assert "outer-wrapper" in tb_text
    assert "direct cause" in tb_text


def test_describe_exception_keeps_no_reference_to_the_exception():
    # The property the whole module exists for: a retained rendering must not
    # pin the exception, its traceback, its frames, or those frames' locals.
    (_type, _message, _tb), ref = _raise_and_describe()
    gc.disable()
    try:
        assert ref() is None, "describe_exception is keeping the exception alive"
    finally:
        gc.enable()


def test_record_from_exception_carries_the_cell_token():
    class _Cell:
        def __repr__(self):
            return "<Cell at (1, 2, 3)>"

    try:
        raise ValueError("boom")
    except ValueError as exc:
        record = RunErrorRecord.from_exception(exc, _Cell())
    assert record.exc_type == "ValueError"
    assert record.exc_message == "boom"
    assert record.cell_repr == "<Cell at (1, 2, 3)>"


def test_record_has_no_cell_token_when_there_is_no_cell():
    # A producer raising during a refill is attributed to no cell -- which is
    # why the run-level record exists at all, instead of living only on the
    # failing action's log entry.
    try:
        raise ValueError("boom")
    except ValueError as exc:
        record = RunErrorRecord.from_exception(exc)
    assert record.cell_repr is None


def test_record_is_frozen():
    record = RunErrorRecord("ValueError", "boom", "traceback text")
    try:
        record.exc_type = "OtherError"
    except Exception as exc:
        assert type(exc).__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("RunErrorRecord should be immutable")
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_error_record.py -v
```

Expected: every test fails at collection with `ModuleNotFoundError: No module named 'acq4.experiment.error_record'`.

- [ ] **Step 3: Write the implementation**

Create `acq4/experiment/error_record.py`:

```python
"""Renders a failure to retainable text: the shared rendering behind the
per-action log entry's error fields and the orchestrator's run-level report."""
from __future__ import annotations

import traceback
from dataclasses import dataclass


def describe_exception(exc: BaseException) -> tuple[str, str, str]:
    """Render `exc` to `(type name, message, traceback text)`.

    Text, never the exception itself. Both callers retain what they are given
    for the length of a session -- a finished ActionLogEntry stays in CellPanel's
    per-cell stores, and the run-level record stays in StatusPanel until the next
    run -- and a live exception holds its traceback, which holds every frame,
    which holds those frames' locals: image stacks, device handles, the execution
    context. Formatting here is what stops one failure from pinning a run's worth
    of memory, and keeps this out of the reference-cycle class of bug Autopatch's
    deterministic teardown path exists to avoid.

    The traceback text follows the `__cause__` chain, which is where the frames
    that explain anything live: an orchestrator halt is raised as
    `AbortExperiment(...) from exc`, and the wrapper's own frames say only that
    the orchestrator gave up.
    """
    return (
        type(exc).__name__,
        str(exc),
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    )


@dataclass(frozen=True)
class RunErrorRecord:
    """What halted a run, as plain data -- the payload of Orchestrator.sigRunError.

    `cell_repr` is the same token the orchestrator's own log messages carry
    ("...while processing cell %r"), so the operator can paste it into the log
    window's search: teleprox's LogViewer has no select-a-record API, so the UI's
    log link narrows the view but cannot anchor to the entry. None when the
    failure belongs to no cell -- a producer raising during a refill emits no
    sigCellFinished and opens no log_action, so there is neither a cell nor an
    entry to attribute it to.
    """

    exc_type: str
    exc_message: str
    traceback_text: str
    cell_repr: str | None = None

    @classmethod
    def from_exception(cls, exc: BaseException, cell=None) -> "RunErrorRecord":
        exc_type, exc_message, traceback_text = describe_exception(exc)
        return cls(
            exc_type,
            exc_message,
            traceback_text,
            None if cell is None else repr(cell),
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_error_record.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Mutation-prove the two absence assertions**

Both `test_describe_exception_keeps_no_reference_to_the_exception` and `test_record_has_no_cell_token_when_there_is_no_cell` assert a value that is already the default, so each must be shown able to fail.

Mutation A — make the record pin the exception. Temporarily add a non-field attribute assignment in `from_exception` and have the helper return the record:

```python
        record = cls(exc_type, exc_message, traceback_text,
                     None if cell is None else repr(cell))
        object.__setattr__(record, "_exc", exc)   # MUTANT
        return record
```
and temporarily change `_raise_and_describe` to `return RunErrorRecord.from_exception(exc), weakref.ref(exc)`.
Run the weakref test. Expected: **FAIL** with "describe_exception is keeping the exception alive". Revert both edits.

Mutation B — make the cell token unconditional: change `None if cell is None else repr(cell)` to `repr(cell)`.
Run `test_record_has_no_cell_token_when_there_is_no_cell`. Expected: **FAIL** (`'None' is not None`). Revert.

Re-run the file and confirm 6 passed before committing.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/experiment/error_record.py acq4/experiment/tests/test_error_record.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: render a failure to retainable text for the UI" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 2: `ActionLogEntry` captures the failure, errors only

**Files:**
- Modify: `acq4/experiment/log_entry.py`
- Test: `acq4/experiment/tests/test_log_entry.py` (append)

**Interfaces:**
- Consumes: `describe_exception` from Task 1.
- Produces: `ActionLogEntry.exc_type: str | None`, `.exc_message: str | None`, `.traceback_text: str | None` — all `None` until `_finish()` runs, and populated **only** when `outcome == "error"`. All three are set **before** `on_finish` fires, because the UI slot on the far end of that callback reads them.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_log_entry.py`:

```python
def test_error_outcome_captures_type_message_and_traceback():
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as action_entry:
            raise BrokenPipette("tip sheared off")
    assert action_entry.outcome == "error"
    assert action_entry.exc_type == "BrokenPipette"
    assert action_entry.exc_message == "tip sheared off"
    assert "BrokenPipette: tip sheared off" in action_entry.traceback_text
    assert "test_error_outcome_captures" in action_entry.traceback_text


def test_successful_action_captures_nothing():
    ctx = ExecutionContext()
    with ctx.log_action("Patch") as action_entry:
        pass
    assert action_entry.exc_type is None
    assert action_entry.exc_message is None
    assert action_entry.traceback_text is None


def test_stopped_captures_nothing():
    # An operator-initiated stop is ordinary control flow; a traceback for it
    # would fill Area 5's pane with noise.
    ctx = ExecutionContext()
    with pytest.raises(Stopped):
        with ctx.log_action("Patch") as action_entry:
            raise Stopped()
    assert action_entry.outcome == "stopped"
    assert action_entry.exc_type is None
    assert action_entry.traceback_text is None


def test_flow_signal_captures_nothing():
    ctx = ExecutionContext()
    with pytest.raises(AdvanceToNextCell):
        with ctx.log_action("Patch") as action_entry:
            raise AdvanceToNextCell("next")
    assert action_entry.outcome == "abandoned"
    assert action_entry.exc_type is None
    assert action_entry.traceback_text is None


def test_error_fields_are_populated_before_on_finish_fires():
    # CellPanel's "finished" slot renders the error block straight from these
    # fields, and it is reached through on_finish -- so an ordering where
    # on_finish runs first would hand the UI an entry with nothing on it.
    seen = {}
    entry = ActionLogEntry("Patch")
    entry.on_finish = lambda e: seen.update(
        exc_type=e.exc_type, traceback_text=e.traceback_text
    )
    try:
        raise BrokenPipette("tip sheared off")
    except BrokenPipette as exc:
        entry._finish(exc)
    assert seen["exc_type"] == "BrokenPipette"
    assert "tip sheared off" in seen["traceback_text"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -v
```

Expected: `test_error_outcome_captures_type_message_and_traceback`, `test_error_fields_are_populated_before_on_finish_fires` FAIL with `AttributeError: 'ActionLogEntry' object has no attribute 'exc_type'`. The three "captures nothing" tests **also** fail with `AttributeError` — they are not yet vacuous, because the attribute does not exist at all. They become vacuous the moment it does, which is what Step 5 addresses.

- [ ] **Step 3: Write the implementation**

In `acq4/experiment/log_entry.py`, add the import at the top (after `from acq4.util.task import Stopped`):

```python
from .error_record import describe_exception
from .exceptions import FlowSignal
```

In `__init__`, after `self.details_widget: Any = None`:

```python
        # Populated by _finish() for an error outcome only, and never with the
        # exception itself -- see error_record.describe_exception. A finished
        # entry is retained for the session in CellPanel's per-cell stores, so
        # what it holds is what one failure costs in memory.
        self.exc_type: str | None = None
        self.exc_message: str | None = None
        self.traceback_text: str | None = None
```

In `_finish`, replace the final `else:` branch and the `on_finish` call:

```python
        else:
            self.outcome = "error"
            self.exc_type, self.exc_message, self.traceback_text = describe_exception(exc)
        # Set before on_finish, not after: the UI's "finished" slot renders the
        # error block straight from these fields, and it is reached through this
        # callback.
        if self.on_finish is not None:
            self.on_finish(self)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -v
```

Expected: all pass (the file's existing tests plus the 5 new ones).

- [ ] **Step 5: Mutation-prove the three "captures nothing" tests**

They now assert `None` against a field whose initial value is `None`, which is the exact shape that has shipped vacuous three times on this project. Apply the defect: make the capture unconditional by moving it out of the `else:` branch to the end of the `if/elif/else` chain, so every outcome captures:

```python
        self.exc_type, self.exc_message, self.traceback_text = (
            describe_exception(exc) if exc is not None else (None, None, None)
        )   # MUTANT -- runs for stopped/abandoned too
```

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -k "stopped_captures or flow_signal_captures" -v
```

Expected: **both FAIL**. (`test_successful_action_captures_nothing` will still pass under this mutant — `exc is None` there — which is correct and is why the other two carry the proof.) Revert the mutation and re-run the whole file green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/experiment/log_entry.py acq4/experiment/tests/test_log_entry.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: record a failing action's exception text on its log entry" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 3: `Orchestrator.sigRunError` at every halt site

**Files:**
- Modify: `acq4/experiment/orchestrator.py`
- Test: `acq4/experiment/tests/test_orchestrator_exceptions.py` (append)

**Interfaces:**
- Consumes: `RunErrorRecord` from Task 1.
- Produces: `Orchestrator.sigRunError = Qt.Signal(object)`, carrying one `RunErrorRecord`, emitted **immediately before** the existing `sigStatus.emit("error")` at each of the four halt sites. Private helper `Orchestrator._reportRunError(exc: BaseException, cell=None) -> None` emits both.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_orchestrator_exceptions.py`:

```python
def _record_signals(orch):
    """Collect sigRunError payloads and sigStatus values into one ordered list,
    so a test can assert not just what was emitted but in what order."""
    events = []
    orch.sigRunError.connect(lambda rec: events.append(("error-record", rec)))
    orch.sigStatus.connect(lambda status: events.append(("status", status)))
    return events


def test_unexpected_exception_reports_a_run_error_record(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert len(records) == 1
    assert records[0].exc_type == "RuntimeError"
    assert records[0].exc_message == "boom"
    assert "RuntimeError: boom" in records[0].traceback_text
    assert records[0].cell_repr == "'c1'"


def test_orchestration_error_reports_a_run_error_record(make_pf):
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(BrokenPipette("tip gone"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["BrokenPipette"]
    assert records[0].exc_message == "tip gone"


def test_run_error_is_reported_before_the_error_status(make_pf):
    # A slot reacting to "error" must already have the record to render.
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    flattened = [
        payload if kind == "status" else "error-record" for kind, payload in events
    ]
    assert flattened == ["running", "error-record", "error"]


def test_swallowed_flow_signal_reports_the_signal_as_the_error(make_pf):
    # A protocol that catches its own ctx.next_cell() is a bug; the record must
    # name the signal, since that is what the halt is about.
    pf = make_pf()

    def swallowing_run(ctx, **kwargs):
        try:
            ctx.next_cell()
        except AdvanceToNextCell:
            pass

    pf.run = swallowing_run
    orch = Orchestrator(pf, contextFactory=lambda cell: ExecutionContext(cell=cell))
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync_cell("c1")
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["AdvanceToNextCell"]
    assert records[0].cell_repr == "'c1'"


def test_producer_failure_reports_a_run_error_record_with_no_cell(make_pf):
    # A producer raising during a refill is attributed to no cell -- the case
    # the run-level record exists for.
    pf = make_pf()
    orch = Orchestrator(pf)

    def exploding_producer():
        raise RuntimeError("camera is unplugged")

    orch.setCellProducer(exploding_producer)
    events = _record_signals(orch)
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    records = [payload for kind, payload in events if kind == "error-record"]
    assert [r.exc_type for r in records] == ["RuntimeError"]
    assert records[0].exc_message == "camera is unplugged"
    assert records[0].cell_repr is None


def test_the_error_status_does_not_stick_after_a_halt(make_pf):
    # Measured, not assumed: _runLoopBody's finally emits "waiting"
    # unconditionally, and AbortExperiment is a FlowSignal so it propagates
    # straight through. This is why StatusPanel's error band keys off having a
    # last-error record rather than off sigStatus("error") -- gating visibility
    # on the status would show the band and hide it within the same run.
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    statuses = []
    orch.sigStatus.connect(statuses.append)
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    assert statuses == ["running", "running", "error", "waiting"]
```

Add the imports this needs to the top of the file:

```python
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AbortExperiment, AdvanceToNextCell, BrokenPipette, RetryCurrentCell
```

`test_run_error_is_reported_before_the_error_status` asserts the exact emission order for a single cell run through `run_sync_cell` (which has no `_runLoopBody` around it, hence no trailing `"waiting"`). If the leading `"running"` count differs from one on your run, print `flattened` and match what the orchestrator actually emits — the assertion that matters is that `"error-record"` is immediately followed by `"error"`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_exceptions.py -v
```

Expected: the five `sigRunError` tests FAIL with `AttributeError: 'Orchestrator' object has no attribute 'sigRunError'`. `test_the_error_status_does_not_stick_after_a_halt` **passes already** — it pins existing behaviour deliberately, as the regression net for Task 5.

- [ ] **Step 3: Write the implementation**

In `acq4/experiment/orchestrator.py`, add to the imports:

```python
from .error_record import RunErrorRecord
```

Add the signal beside the existing three:

```python
    sigRunError = Qt.Signal(object)            # RunErrorRecord for the halt
```

Add the helper immediately above `_reportFinished`:

```python
    def _reportRunError(self, exc: BaseException, cell=None) -> None:
        """Publish the failure that is about to halt this run, then set status.

        Called at every halt site, immediately before the AbortExperiment that
        wraps `exc`. Carries a RunErrorRecord -- plain formatted strings -- so
        nothing downstream can retain the exception and the frames behind it
        (see error_record.describe_exception).

        `exc` is the original failure rather than the AbortExperiment wrapper:
        the wrapper does not exist yet here, and its own frames would say only
        that the orchestrator gave up. The chain is preserved anyway, since
        the wrapper is raised `from exc`.

        Not every failure has a cell -- a producer raising during a refill is
        attributed to none, and there is no log entry for it either. That is why
        this is a run-level report and not simply more fields on ActionLogEntry.

        Emitted before sigStatus so a slot reacting to "error" already has the
        record. Both are queued to the GUI thread in emit order, so a receiver
        cannot observe the status without the record that explains it.
        """
        self.sigRunError.emit(RunErrorRecord.from_exception(exc, cell))
        self.sigStatus.emit("error")
```

Now replace each halt site's bare status emit. In `_refillQueue`'s `except Exception as exc:` branch:

```python
            logger.exception("Cell producer raised while refilling the queue")
            self._reportRunError(exc)
            raise AbortExperiment(f"cell producer failed: {exc}") from exc
```

In `_processCell`'s `except OrchestrationError as exc:` branch, replace `self.sigStatus.emit("error")` with `self._reportRunError(exc, cell)`. Same in `except Exception as exc:`. In the swallowed-flow-signal branch inside `else:`, replace `self.sigStatus.emit("error")` with `self._reportRunError(signal, cell)`.

Leave every `logger.exception(...)`/`logger.error(...)` call and every `_reportFinished(cell, "error")` exactly as they are — the UI and the log must stay two renderings of one failure, and nothing new is logged for the UI's benefit.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/ -v
```

Expected: all pass. Confirm `grep -n 'sigStatus.emit("error")' acq4/experiment/orchestrator.py` returns **only** the line inside `_reportRunError`.

- [ ] **Step 5: Mutation-prove the no-cell assertion**

`test_producer_failure_reports_a_run_error_record_with_no_cell` asserts `cell_repr is None`, which is the field's default. Apply the defect: in `_refillQueue`, change `self._reportRunError(exc)` to `self._reportRunError(exc, "some-cell")`.

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_exceptions.py -k producer_failure -v
```

Expected: **FAIL**. Revert and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_exceptions.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: report the exception that halts a run on sigRunError" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 4: `error_display.py` — the shared log link and error block widget

Both Area 3 and Area 5 need a "Show in log" button, and Area 5 needs the traceback view. One module owns how a failure looks in Autopatch, so the two areas cannot drift apart.

**Files:**
- Create: `acq4/modules/Autopatch/error_display.py`
- Test: `acq4/modules/Autopatch/tests/test_error_display.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (it takes plain strings).
- Produces:
  - `showInLog() -> None` — raises acq4's log window.
  - `ErrorBlock(exc_type: str, exc_message: str, traceback_text: str, cell_repr: str | None = None)` — a `Qt.QWidget` with attributes `headlineLabel`, `cellLabel`, `tracebackView` (a read-only `QPlainTextEdit`), `copyBtn`, `showInLogBtn`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_error_display.py`:

```python
"""Tests for Autopatch's shared error presentation: the log-window link and the
Area 5 error block."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_show_in_log_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch import error_display

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr(
        "acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow()
    )
    error_display.showInLog()
    assert raised == [True]


def test_error_block_shows_headline_traceback_and_cell_token(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock(
        "BrokenPipette", "tip sheared off", "Traceback...\nBrokenPipette: tip sheared off\n",
        "<Cell at (1, 2, 3)>",
    )
    assert block.headlineLabel.text() == "BrokenPipette: tip sheared off"
    assert "BrokenPipette: tip sheared off" in block.tracebackView.toPlainText()
    assert "<Cell at (1, 2, 3)>" in block.cellLabel.text()
    assert block.cellLabel.isVisible() or not block.isVisible()


def test_error_block_hides_the_cell_row_when_there_is_no_cell(qapp):
    # A producer failure has no cell token to paste into the log search; an
    # empty row would read as "cell: (blank)" rather than as "not applicable".
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock("RuntimeError", "camera unplugged", "Traceback...\n")
    assert block.cellLabel.isVisibleTo(block) is False


def test_error_block_traceback_is_read_only_and_selectable(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    block = ErrorBlock("RuntimeError", "boom", "Traceback...\n")
    assert block.tracebackView.isReadOnly() is True


def test_copy_button_puts_the_traceback_on_the_clipboard(qapp):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    traceback_text = "Traceback (most recent call last):\n  RuntimeError: boom\n"
    block = ErrorBlock("RuntimeError", "boom", traceback_text)
    Qt.QApplication.clipboard().clear()
    block.copyBtn.click()
    assert Qt.QApplication.clipboard().text() == traceback_text


def test_show_in_log_button_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr(
        "acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow()
    )
    block = ErrorBlock("RuntimeError", "boom", "Traceback...\n")
    block.showInLogBtn.click()
    assert raised == [True]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_error_display.py -v
```

Expected: all fail with `ImportError`/`ModuleNotFoundError` for `acq4.modules.Autopatch.error_display`.

- [ ] **Step 3: Write the implementation**

Create `acq4/modules/Autopatch/error_display.py`:

```python
"""Shared presentation for a failure in Autopatch: the link into acq4's log
window, and Area 5's error block (headline, cell token, traceback, Copy)."""
from __future__ import annotations

from acq4.util import Qt


def showInLog() -> None:
    """Raise acq4's log window so the operator can read the failure in context.

    Imported at call time rather than at module import: get_log_window()
    constructs the window on first use, and importing this module must not be
    what brings a top-level window into existence (tests import it headless).
    ErrorDialog.logClicked is the existing precedent for this hand-off.

    The link narrows the operator's view; it cannot anchor to the failing
    record, because teleprox's LogViewer exposes no select-a-record API. What
    makes the entry findable is the cell token the orchestrator's own messages
    carry -- ErrorBlock shows the same token so it can be pasted into the log
    window's search.
    """
    from acq4.util.LogWindow import get_log_window

    get_log_window().raise_window()


class ErrorBlock(Qt.QWidget):
    """Area 5's rendering of one failure, built from stored text.

    Takes strings, never an exception or an ActionLogEntry: this widget lives in
    the GUI tree for as long as the operator leaves the cell selected, and the
    panel that builds it must not become the thing keeping a traceback's frames
    alive (see acq4.experiment.error_record.describe_exception).
    """

    def __init__(
        self,
        exc_type: str,
        exc_message: str,
        traceback_text: str,
        cell_repr: str | None = None,
    ):
        super().__init__()
        self._tracebackText = traceback_text

        self.headlineLabel = Qt.QLabel(f"{exc_type}: {exc_message}")
        self.headlineLabel.setStyleSheet("color: red; font-weight: bold;")
        self.headlineLabel.setWordWrap(True)

        # Selectable so the token can be copied into the log window's search
        # box, which is the only way to reach the matching record.
        self.cellLabel = Qt.QLabel(f"while processing cell {cell_repr}")
        self.cellLabel.setTextInteractionFlags(Qt.Qt.TextSelectableByMouse)
        self.cellLabel.setVisible(cell_repr is not None)

        self.tracebackView = Qt.QPlainTextEdit(traceback_text)
        self.tracebackView.setReadOnly(True)
        font = Qt.QFont("monospace")
        font.setStyleHint(Qt.QFont.Monospace)
        self.tracebackView.setFont(font)

        self.copyBtn = Qt.QPushButton("Copy")
        self.showInLogBtn = Qt.QPushButton("Show in log")
        self.copyBtn.clicked.connect(self._onCopyClicked)
        self.showInLogBtn.clicked.connect(self._onShowInLogClicked)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.copyBtn)
        btnRow.addWidget(self.showInLogBtn)
        btnRow.addStretch()

        layout = Qt.QVBoxLayout()
        layout.addWidget(self.headlineLabel)
        layout.addWidget(self.cellLabel)
        layout.addWidget(self.tracebackView)
        layout.addLayout(btnRow)
        self.setLayout(layout)

    def _onCopyClicked(self) -> None:
        # Qt's clicked signal carries a `checked` bool, which setText would
        # otherwise receive as the clipboard contents.
        Qt.QApplication.clipboard().setText(self._tracebackText)

    def _onShowInLogClicked(self) -> None:
        showInLog()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_error_display.py -v
```

Expected: 6 passed. If `Qt.QFont` is not re-exported by `acq4.util.Qt`, check with
`grep -n "QFont" acq4/util/Qt.py` and import it from the underlying binding the same way that module does for other classes.

- [ ] **Step 5: Mutation-prove the hidden-cell-row assertion**

`test_error_block_hides_the_cell_row_when_there_is_no_cell` asserts a visibility that could be false for unrelated reasons (an unshown widget). Apply the defect: change `self.cellLabel.setVisible(cell_repr is not None)` to `self.cellLabel.setVisible(True)`.

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_error_display.py -k hides_the_cell_row -v
```

Expected: **FAIL**. Revert. If it *passes* under the mutant, `isVisibleTo` is answering about the un-shown parent rather than the flag — replace the assertion with `assert block.cellLabel.isHidden() is True` and re-run the mutation until it genuinely distinguishes the two.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/error_display.py acq4/modules/Autopatch/tests/test_error_display.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: add Autopatch's shared error block and log link" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 5: Area 3's instruction band finally says something

**Files:**
- Modify: `acq4/modules/Autopatch/status_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_status_panel.py` (append, plus one edit to `_FakeOrchestrator`)

**Interfaces:**
- Consumes: `Orchestrator.sigRunError` (Task 3), `error_display.showInLog` (Task 4).
- Produces: `StatusPanel.lastError() -> RunErrorRecord | None`, `StatusPanel.showInLogBtn`. The band (`instructionLabel`) and that button are visible **iff** `lastError()` is not None.

- [ ] **Step 1: Write the failing tests**

First extend the existing fake at the top of `acq4/modules/Autopatch/tests/test_status_panel.py` — add the signal to `_FakeOrchestrator`:

```python
class _FakeOrchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)
    sigCurrentCell = Qt.Signal(object)
    sigRunError = Qt.Signal(object)
```

Then append:

```python
def _record(exc_type="RuntimeError", message="boom", cell_repr="'c1'"):
    from acq4.experiment.error_record import RunErrorRecord

    return RunErrorRecord(exc_type, message, "Traceback...\n", cell_repr)


def test_error_band_shows_the_headline(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record("BrokenPipette", "tip sheared off"))
    assert panel.instructionLabel.text() == "BrokenPipette: tip sheared off"
    assert panel.lastError().exc_type == "BrokenPipette"


def test_error_band_survives_the_waiting_status_that_follows_a_halt(qapp):
    # The regression this whole area needed: Orchestrator._runLoopBody's finally
    # emits "waiting" straight behind the "error" (pinned by
    # test_the_error_status_does_not_stick_after_a_halt), so a band gated on the
    # status is shown and hidden within the same run and the operator sees
    # nothing. Visibility keys off having a record instead.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.show()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    orch.sigStatus.emit("error")
    orch.sigStatus.emit("waiting")
    assert panel.instructionLabel.isVisibleTo(panel) is True
    assert panel.instructionLabel.text() == "RuntimeError: boom"
    assert panel.showInLogBtn.isVisibleTo(panel) is True
    panel.hide()


def test_band_is_hidden_with_no_error(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigStatus.emit("running")
    assert panel.lastError() is None
    assert panel.instructionLabel.isVisibleTo(panel) is False
    assert panel.showInLogBtn.isVisibleTo(panel) is False


def test_starting_a_new_run_clears_the_previous_error(qapp):
    # The band is a headline for the run that is showing, not a scar.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    orch.sigStatus.emit("waiting")
    panel.startBtn.click()
    assert panel.lastError() is None
    assert panel.instructionLabel.text() == ""
    assert panel.instructionLabel.isVisibleTo(panel) is False
    assert orch.started == 1


def test_unbinding_clears_the_error_and_stops_listening(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    panel.unbindOrchestrator()
    assert panel.lastError() is None
    # The outgoing orchestrator must no longer be able to write into this panel.
    orch.sigRunError.emit(_record("KeyError", "late arrival"))
    assert panel.lastError() is None
    assert panel.instructionLabel.text() == ""


def test_show_in_log_button_raises_the_log_window(qapp, monkeypatch):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    raised = []

    class _FakeLogWindow:
        def raise_window(self):
            raised.append(True)

    monkeypatch.setattr("acq4.util.LogWindow.get_log_window", lambda: _FakeLogWindow())
    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch, _FakeEntrySource())
    orch.sigRunError.emit(_record())
    panel.showInLogBtn.click()
    assert raised == [True]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v
```

Expected: the six new tests fail — `AttributeError: 'StatusPanel' object has no attribute 'lastError'` / `showInLogBtn`.

- [ ] **Step 3: Write the implementation**

In `acq4/modules/Autopatch/status_panel.py`, add the import:

```python
from .error_display import showInLog
```

In `__init__`, after `self._currentStatus = None`:

```python
        # The RunErrorRecord for the failure that halted the last run, or None.
        # A run-level record rather than only the failing action's log entry: a
        # producer raising during a refill has no cell and opens no log_action,
        # so there would be nothing to hang the band's headline on.
        self._lastError = None
```

After the `instructionLabel` construction, replace the `setVisible(False)` line and add the button:

```python
        self.instructionLabel = Qt.QLabel("")
        self.instructionLabel.setStyleSheet("color: red; font-weight: bold;")
        self.instructionLabel.setWordWrap(True)
        self.showInLogBtn = Qt.QPushButton("Show in log")
        self.showInLogBtn.clicked.connect(self._onShowInLogClicked)
```

Replace `layout.addWidget(self.instructionLabel)` with a row:

```python
        errorRow = Qt.QHBoxLayout()
        errorRow.addWidget(self.instructionLabel)
        errorRow.addWidget(self.showInLogBtn)
        errorRow.addStretch()
```

and `layout.addLayout(errorRow)` in its place. Then, just before the existing `self._updateButtons()` at the end of `__init__`, add `self._updateErrorBand()`.

In `bindOrchestrator`, after `orchestrator.sigCurrentCell.connect(self._onCurrentCell)`:

```python
        orchestrator.sigRunError.connect(self._onRunError)
```

and clear the record where the other per-binding state is reset — replace `self._currentStatus = None` in that method with:

```python
        self._currentStatus = None
        self._lastError = None
        self._updateErrorBand()
```

In `unbindOrchestrator`, add the matching disconnect beside the others:

```python
        Qt.disconnect(self._orchestrator.sigRunError, self._onRunError)
```

and, alongside `self._currentStatus = None` in that method:

```python
        self._lastError = None
        self._updateErrorBand()
```

In `_onStatus`, **delete** the line `self.instructionLabel.setVisible(status == "error")`. Leave the rest of the method as it is. Add a comment in its place:

```python
    def _onStatus(self, status: str) -> None:
        self.statusLabel.setText(status)
        # The band is deliberately not gated on status == "error": a halt emits
        # "error" and then "waiting" from the run loop's own finally, so a band
        # keyed on the status would be shown and hidden within the same run.
        # _onRunError drives it instead, and it clears when the next run starts.
        self._currentStatus = status
```

Add the new methods after `_onPauseClicked`:

```python
    def _onRunError(self, record) -> None:
        self._lastError = record
        self._updateErrorBand()

    def lastError(self):
        """The RunErrorRecord for the failure that halted the last run, or None.

        The window's own error surfacing reads this rather than re-deriving the
        failure: the orchestrator is a parentless QObject, and a second consumer
        connecting to it directly would give it another reference back and
        rebuild the cycle bindOrchestrator/unbindOrchestrator exist to avoid.
        """
        return self._lastError

    def _updateErrorBand(self) -> None:
        record = self._lastError
        self.instructionLabel.setText(
            "" if record is None else f"{record.exc_type}: {record.exc_message}"
        )
        self.instructionLabel.setVisible(record is not None)
        self.showInLogBtn.setVisible(record is not None)

    def _onShowInLogClicked(self) -> None:
        showInLog()
```

Finally, in `_onStartClicked`, clear the previous run's error before starting:

```python
    def _onStartClicked(self) -> None:
        # The band is a headline for the run that is showing, not a scar: a new
        # run supersedes whatever halted the last one.
        self._lastError = None
        self._updateErrorBand()
        if self._onStart is not None:
            self._onStart()
        self._orchestrator.start()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v
```

Expected: all pass, including the file's pre-existing tests.

- [ ] **Step 5: Mutation-prove the band regression and the hidden-band assertions**

Mutation A — restore the old gating. Add `self.instructionLabel.setVisible(status == "error")` back into `_onStatus`.

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -k survives_the_waiting_status -v
```

Expected: **FAIL** — this is the whole point of the task, so it must be seen to fail. Revert.

Mutation B — `test_band_is_hidden_with_no_error` and `test_unbinding_clears_the_error_and_stops_listening` both assert an already-default state. For B1, change `_updateErrorBand`'s `setVisible(record is not None)` to `setVisible(True)` and confirm `test_band_is_hidden_with_no_error` **FAILS**. For B2, delete the `Qt.disconnect(self._orchestrator.sigRunError, self._onRunError)` line and confirm `test_unbinding_clears_the_error_and_stops_listening` **FAILS** on the late-arrival emit. Revert both and re-run green.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/status_panel.py acq4/modules/Autopatch/tests/test_status_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: show the halting error in Area 3's instruction band" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 6: Area 5's per-cell error block

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_cell_error_block.py` (create)

**Interfaces:**
- Consumes: `ActionLogEntry.exc_type`/`.exc_message`/`.traceback_text` (Task 2), `error_display.ErrorBlock` (Task 4).
- Produces: `CellPanel.errorText(cell) -> tuple[str, str, str] | None` — the stored `(exc_type, exc_message, traceback_text)` for that cell's most recent failed action, or None.

**Design notes the implementer must not lose:**
- The store holds `id(cell)` keys and plain strings, **never the entry**. An `ActionLogEntry`'s `on_status`/`on_widget`/`on_finish` callbacks close over this panel, so a panel that kept an entry would form a reference cycle only the cyclic GC could break — the exact failure mode `tests/test_teardown.py` exists to prevent.
- The block must be re-mountable, because `_onCellSelectionChanged` clears `showContainer` on every selection change. Mounting it only at `"finished"` time would lose it the first time the operator clicks another cell.
- A new pass for a cell supersedes its stored error: `_onCurrentCell` drops it. A cell that fails, is reused, and then succeeds must not still show the old traceback.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_cell_error_block.py`:

```python
"""Tests for Area 5's error block: a failed action's traceback, stored per cell
so it survives a selection change, and dropped when that cell starts a new pass."""
import gc
import weakref

import pytest

from acq4.experiment.exceptions import BrokenPipette
from acq4.experiment.log_entry import ActionLogEntry
from acq4.modules.Autopatch.error_display import ErrorBlock
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


@pytest.fixture
def panel(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel()


def _finish_with_error(panel, cell, name="Patch", message="tip sheared off"):
    """Drive one action for `cell` all the way to a failed finish, the way a
    real run does: the panel wires the entry's callbacks in onLogAction()."""
    entry = ActionLogEntry(name)
    panel.onLogAction(cell, entry)
    try:
        raise BrokenPipette(message)
    except BrokenPipette as exc:
        entry._finish(exc)
    return entry


def _mounted_blocks(panel):
    layout = panel.showContainer.layout()
    return [
        layout.itemAt(i).widget()
        for i in range(layout.count())
        if isinstance(layout.itemAt(i).widget(), ErrorBlock)
    ]


def test_failed_action_mounts_an_error_block_for_the_selected_cell(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    blocks = _mounted_blocks(panel)
    assert len(blocks) == 1
    assert blocks[0].headlineLabel.text() == "BrokenPipette: tip sheared off"
    assert "BrokenPipette: tip sheared off" in blocks[0].tracebackView.toPlainText()


def test_error_block_survives_switching_cells_and_back(panel):
    # showContainer is cleared on every selection change, so a block mounted
    # only at finish time would be gone for good the first time the operator
    # looks at another cell.
    first, second = object(), object()
    panel.addCell(first)
    panel.addCell(second)
    panel.cellList.setCurrentItem(panel._rows[id(first)])
    _finish_with_error(panel, first)
    panel.cellList.setCurrentItem(panel._rows[id(second)])
    assert _mounted_blocks(panel) == []
    panel.cellList.setCurrentItem(panel._rows[id(first)])
    blocks = _mounted_blocks(panel)
    assert len(blocks) == 1
    assert blocks[0].headlineLabel.text() == "BrokenPipette: tip sheared off"


def test_successful_action_mounts_no_error_block(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(None)
    assert _mounted_blocks(panel) == []
    assert panel.errorText(cell) is None


def test_a_new_pass_clears_the_cells_stored_error(panel):
    # A cell that failed, was reused, and then ran again must not still be
    # showing the previous pass's traceback.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    assert panel.errorText(cell) is not None
    panel._onCurrentCell(cell)
    assert panel.errorText(cell) is None
    assert _mounted_blocks(panel) == []


def test_a_later_failure_supersedes_the_earlier_one(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell, name="Patch", message="first failure")
    _finish_with_error(panel, cell, name="Clean", message="second failure")
    exc_type, message, _tb = panel.errorText(cell)
    assert (exc_type, message) == ("BrokenPipette", "second failure")
    assert len(_mounted_blocks(panel)) == 1


def test_error_block_is_not_mounted_for_an_unselected_cell(panel):
    first, second = object(), object()
    panel.addCell(first)
    panel.addCell(second)
    panel.cellList.setCurrentItem(panel._rows[id(second)])
    _finish_with_error(panel, first)
    assert _mounted_blocks(panel) == []
    assert panel.errorText(first) is not None


def test_clear_cells_drops_the_error_store(panel):
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    panel.clearCells()
    assert panel.errorText(cell) is None
    assert _mounted_blocks(panel) == []


def test_discarding_a_cell_drops_its_stored_error(panel):
    # A rescan removing an unattempted row must not leave its traceback behind,
    # keyed by an id() that a future object could reuse.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    _finish_with_error(panel, cell)
    assert panel.isAttempted(cell) is False
    panel._onCellsDiscarded([cell])
    assert panel.errorText(cell) is None


def test_panel_keeps_no_reference_to_the_failed_entry(panel):
    # An entry's on_finish closes over this panel; a panel holding the entry
    # back would form a cycle only the cyclic GC could break. See
    # tests/test_teardown.py for why this module must not have any.
    cell = object()
    panel.addCell(cell)
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    entry = _finish_with_error(panel, cell)
    ref = weakref.ref(entry)
    del entry
    gc.disable()
    try:
        assert ref() is None, "CellPanel is keeping the failed entry alive"
    finally:
        gc.enable()
    assert panel.errorText(cell) is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_error_block.py -v
```

Expected: `AttributeError: 'CellPanel' object has no attribute 'errorText'` on most; the "mounts no block" ones fail on the same missing method.

- [ ] **Step 3: Write the implementation**

In `acq4/modules/Autopatch/cell_panel.py`, add the import:

```python
from .error_display import ErrorBlock
```

In `__init__`, beside the other per-cell stores (after `self._logs: dict[int, list[str]] = {}`):

```python
        # id(cell) -> (exc_type, exc_message, traceback_text) for the most
        # recent action of that cell's that failed. Ids and plain strings,
        # never the entry and never the exception: an ActionLogEntry's
        # on_finish closes over this panel, and an exception holds its
        # traceback's frames and their locals -- either one retained here is
        # the reference-cycle failure this module's teardown path exists to
        # avoid (see tests/test_teardown.py, and
        # acq4.experiment.error_record.describe_exception).
        self._cellErrors: dict[int, tuple[str, str, str]] = {}
```

Add a public reader next to `disposition()`:

```python
    def errorText(self, cell) -> tuple[str, str, str] | None:
        """(exc_type, exc_message, traceback_text) for `cell`'s most recent
        failed action, or None if it has none. Cleared when that cell starts a
        new pass -- a cell that failed, was reused, and then succeeded is not
        still a failure."""
        return self._cellErrors.get(id(cell))
```

In `_onActionEntry`, extend the `"finished"` branch:

```python
        elif phase == "finished":
            self._finishTimelineRow(cell, entry)
            if cell is self._currentSelectedCell() and self._shownEntryId == id(entry):
                self._clearShowContainer()
                self._shownEntryId = None
            if entry.outcome == "error":
                self._cellErrors[id(cell)] = (
                    entry.exc_type,
                    entry.exc_message,
                    entry.traceback_text,
                )
                if cell is self._currentSelectedCell():
                    self._showErrorBlock(cell)
```

Add the mount helper next to `_clearShowContainer`:

```python
    def _showErrorBlock(self, cell) -> None:
        """Mount the stored error block for `cell` in the details container.

        Built fresh from the stored text on every mount rather than kept as a
        widget: _onCellSelectionChanged clears showContainer on every selection
        change, so a retained widget would be reparented away and would also be
        one more thing to drop on teardown.
        """
        stored = self._cellErrors.get(id(cell))
        if stored is None:
            return
        exc_type, exc_message, traceback_text = stored
        self._clearShowContainer()
        self._shownEntryId = None
        self.showContainer.layout().addWidget(
            ErrorBlock(exc_type, exc_message, traceback_text, repr(cell))
        )
```

In `_onCurrentCell`, after `self._attempted.add(id(cell))`:

```python
        # A new pass supersedes the last one's failure: the traceback for a
        # cell that has just been re-queued describes a run that is over.
        if self._cellErrors.pop(id(cell), None) is not None:
            if cell is self._currentSelectedCell():
                self._clearShowContainer()
                self._shownEntryId = None
```

In `_onCellSelectionChanged`, at the very end (after the log lines are appended):

```python
        self._showErrorBlock(cell)
```

In `clearCells`, beside the other `.clear()` calls:

```python
        self._cellErrors.clear()
```

In `_onCellsDiscarded`, in the **removal** branch only (after `self._logs.pop(cellId, None)`):

```python
            self._cellErrors.pop(cellId, None)
```

Not in the `isAttempted` early-`continue` branch: that row survives as the session record, and its traceback is part of that record.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_error_block.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Mutation-prove the four absence assertions**

- **A — `test_successful_action_mounts_no_error_block`.** Change the `"finished"` guard from `if entry.outcome == "error":` to `if True:`. Expected: **FAIL** (it will raise or mount a block built from `None` strings). Revert.
- **B — `test_a_new_pass_clears_the_cells_stored_error`.** Delete the `self._cellErrors.pop(...)` block from `_onCurrentCell`. Expected: **FAIL**. Revert.
- **C — `test_clear_cells_drops_the_error_store` and `test_discarding_a_cell_drops_its_stored_error`.** Delete `self._cellErrors.clear()` from `clearCells`, then the `pop` from `_onCellsDiscarded`. Expected: **each FAILS in turn**. Revert.
- **D — `test_panel_keeps_no_reference_to_the_failed_entry`.** Store the entry too: `self._cellErrors[id(cell)] = (entry.exc_type, entry.exc_message, entry.traceback_text, entry)` and adjust the unpack. Expected: **FAIL** with "CellPanel is keeping the failed entry alive". Revert.

Re-run the file green after every revert.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_error_block.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "feat: show a failed action's traceback in Area 5" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 7: Teardown proof, whole-suite green, and the design doc

**Files:**
- Modify: `acq4/modules/Autopatch/tests/test_teardown.py` (append one test)
- Modify: `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` — **outside this worktree, gitignored, do NOT `git add` it**

- [ ] **Step 1: Write the failing teardown test**

The new `sigRunError` connection is one more edge from a parentless `QObject` (the orchestrator) into the window's panels. `unbindOrchestrator` disconnects it (Task 5), and this proves the whole graph is still reclaimable by plain refcounting.

Append to `acq4/modules/Autopatch/tests/test_teardown.py`. It mirrors the file's
existing `test_teardown_frees_...by_refcounting` proof exactly — same `gc.disable()`
discipline, same fixtures, same helpers (`_write_protocol`, `_FakePipetteSelector`,
`_FakeCameraSelector`) — but runs a protocol that *fails*, so both new stores are
populated before the weakref assertions:

```python
_FAILING_PROTOCOL = """
def run(ctx, **kwargs):
    with ctx.log_action("Boom"):
        raise RuntimeError("protocol blew up")
"""


def test_teardown_frees_everything_after_a_run_error(qapp, tmp_path):
    """A halted run leaves a RunErrorRecord in StatusPanel and traceback text in
    CellPanel. Neither may keep the orchestrator, the cell, or the window alive.

    Both stores hold plain strings by construction, so this is the guard against
    a later change that "helpfully" retains the exception or the ActionLogEntry
    instead -- either of which would put a traceback's frames, and their locals,
    behind a reference only the cyclic GC could reclaim.
    """
    from acq4.experiment.exceptions import AbortExperiment
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "boom.py", _FAILING_PROTOCOL)

    gc.disable()
    try:
        win = AutopatchWindow(
            module=None,
            protocolDir=str(tmp_path),
            pipetteSelector=_FakePipetteSelector(target=(1e-3, 2e-3, 3e-3)),
            cameraSelector=_FakeCameraSelector(),
        )
        win.protocolPanel.fileCombo.setCurrentText("boom")
        win.cellPanel.addFromTargetBtn.click()
        seededCell = list(win.cellPanel._cells.values())[0]
        win.cellPanel.cellList.setCurrentRow(0)

        orchestrator = win.orchestrator
        assert orchestrator is not None

        with pytest.raises(AbortExperiment):
            orchestrator.run_sync_cell(seededCell)

        # Both halves of the surfacing actually populated -- otherwise the
        # refcounting proof below would be proving nothing about them.
        assert win.statusPanel.lastError().exc_type == "RuntimeError"
        assert win.cellPanel.errorText(seededCell)[1] == "protocol blew up"
        # And still no per-entry bookkeeping held onto the entry itself.
        assert win.cellPanel._entryTimelineLoc == {}
        assert win.cellPanel._timelineItems == {}

        orchestrator_ref = weakref.ref(orchestrator)
        cell_ref = weakref.ref(seededCell)
        window_ref = weakref.ref(win)
        statusPanel_ref = weakref.ref(win.statusPanel)
        cellPanel_ref = weakref.ref(win.cellPanel)

        win.teardown()
        assert win.statusPanel._orchestrator is None
        assert win.cellPanel._orchestrator is None

        del orchestrator, seededCell
        win.close()
        del win
        # No gc.collect() -- pure refcounting only, since gc is disabled.

        assert orchestrator_ref() is None, "orchestrator should be freed by refcounting alone"
        assert cell_ref() is None, "seeded cell should be freed by refcounting alone"
        assert window_ref() is None, "window should be freed by refcounting alone"
        assert statusPanel_ref() is None, "StatusPanel should be freed by refcounting alone"
        assert cellPanel_ref() is None, "CellPanel should be freed by refcounting alone"
    finally:
        gc.enable()
```

Before writing it, read the existing proof test in that file and confirm the helper
names and the `AutopatchWindow(...)` keyword arguments above still match it verbatim;
if the file has diverged, follow the file, not this plan.

- [ ] **Step 2: Run it and verify it passes** (it should pass if Tasks 5 and 6 are correct — this is a guard, not a red test)

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_teardown.py -v
```

Expected: all pass. **If it fails, that is a real defect in Task 5 or 6 — fix the panel, not the test.**

- [ ] **Step 3: Mutation-prove it**

Delete `Qt.disconnect(self._orchestrator.sigRunError, self._onRunError)` from `StatusPanel.unbindOrchestrator`. Expected: **FAIL**. Revert.

- [ ] **Step 4: Run every touched suite plus the repo-wide suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/ acq4/modules/Autopatch/tests/ -v
```

Expected: all pass, no errors, no warnings introduced by this branch. Then:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/ -q
```

Record the totals. Compare against the pre-branch baseline captured by running the same command on `origin/_reviewed` if anything looks off. **Test output must be pristine** — investigate any new warning, do not filter it.

- [ ] **Step 5: Commit the teardown test**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/tests/test_teardown.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" \
    -m "test: prove a halted run leaves the window teardown-clean" \
    -m "🤖 Generated with [Claude Code](https://claude.ai/code)"
```

- [ ] **Step 6: Correct the design doc**

Edit `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` (gitignored, outside the worktree — edit it, do not commit it).

In **§5.1**, add the two corrections the landed code forced:

1. Under "Not every error has a cell", record the transport: the run-level record travels on **`Orchestrator.sigRunError(RunErrorRecord)`**, emitted immediately before each existing `sigStatus("error")` at all four halt sites. Not a widened `sigStatus`, and not a `lastError()` the panel reads when it sees the status — a worker-writes/GUI-reads check-then-act is the bug class this project has logged three times.
2. Add a paragraph: **the band cannot key off `sigStatus("error")`.** Measured on the landed engine, a halting run emits `['running', 'running', 'error', 'waiting']` — `_runLoopBody`'s `finally` emits `"waiting"` unconditionally and `AbortExperiment` is a `FlowSignal`, so it propagates straight through. `StatusPanel.instructionLabel` was gated on `status == "error"`, so it was shown and hidden within the same run; writing the headline into it would still have rendered nothing. Visibility keys off having a `RunErrorRecord`, cleared when the next run starts. Pinned by `test_the_error_status_does_not_stick_after_a_halt`.

In **§10 P3**, mark §5.1's error detail as built, leaving the rest of the P3 line (ROI mirroring, prompt intervention flows, heatmap refinements, follow-live detail widgets, Area 5's Go-to cam button, §8's log merge) as still outstanding. Note that the **New-slice `HelpfulException` instruction path (§7 Area 1) is explicitly not included** and travels with the rest of Area 1.

- [ ] **Step 7: Open the PR**

```bash
git push -u origin claude/autopatch-error-surfacing
gh pr create --base _reviewed --title "feat: surface a halted run's error to the operator" --body "$(cat <<'BODY'
Implements design §5.1. When a run halts, the operator now sees the actual exception instead of an empty red band.

- `acq4/experiment/error_record.py` — `describe_exception()` + the frozen `RunErrorRecord`. Formatted text only; a weakref test proves nothing retains the exception, its traceback, or those frames' locals.
- `ActionLogEntry` records `exc_type`/`exc_message`/`traceback_text` for `error` outcomes only, set before `on_finish` fires.
- `Orchestrator.sigRunError(RunErrorRecord)` at all four halt sites (producer refill, `OrchestrationError`, unexpected exception, swallowed flow signal), emitted immediately before the existing `sigStatus("error")`.
- Area 3's instruction band shows `"{type}: {message}"` with a **Show in log** button.
- Area 5 shows the failing action's traceback with **Copy** and the cell token, stored per cell so it survives a selection change and dropped when that cell starts a new pass.

**Finding that changed the design:** the band could never have worked as specified. A halting run emits `['running', 'running', 'error', 'waiting']` — `_runLoopBody`'s `finally` emits `"waiting"` unconditionally, and `AbortExperiment` is a `FlowSignal` so it propagates straight through — and `instructionLabel` was gated on `status == "error"`. Visibility now keys off having a last-error record. Pinned by `test_the_error_status_does_not_stick_after_a_halt`.

**Out of scope, by decision:** the New-slice `HelpfulException("Storage directory has not been set.")` instruction path (§7 Area 1) travels with the rest of Area 1.

**Not reachable headless:** that the band and block actually render legibly at the window's real geometry, and that **Show in log** raises acq4's real log window rather than the fake the tests inject.

🤖 Generated with [Claude Code](https://claude.ai/code)
BODY
)"
```

---

## Definition of done

- `acq4/experiment/tests/` and `acq4/modules/Autopatch/tests/` fully green, output pristine.
- Every mutation named in Steps 5 of Tasks 1–6 and Step 3 of Task 7 was applied, seen to fail, and reverted.
- `grep -n 'sigStatus.emit("error")' acq4/experiment/orchestrator.py` returns exactly one line, inside `_reportRunError`.
- No live exception, traceback object, or `ActionLogEntry` is retained anywhere in `acq4/modules/Autopatch/`.
- Design doc §5.1 and §10 updated in the main checkout (not committed).
- PR open against `_reviewed`.
