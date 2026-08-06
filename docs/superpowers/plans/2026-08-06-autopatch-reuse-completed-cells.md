# Autopatch — Reuse Completed Cells (Multi-Pass) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Area 5 an operator-controlled multi-pass workflow — record each cell's terminal disposition, let the operator check a set of already-run cells, and re-queue those same `Cell` objects for another pass with a different protocol.

**Architecture:** Everything lands in `acq4/modules/Autopatch/cell_panel.py`, plus two wiring lines in `Autopatch.py`. `CellPanel` gains `_status: dict[int, str]` (id(cell) -> last terminal disposition, recorded in `_onCellFinished`), user-checkable rows, two buttons ("Check all completed", "Reuse checked cells"), and a `setInteractionLocked()` gate driven by `StatusPanel.sigInteractionLocked`. No engine (`acq4/experiment/`) change and no `acq4_automation` change.

**Tech Stack:** Python >=3.10, PyQt via `acq4.util.Qt`, pytest (+ the module-scoped `qapp` fixture already in the Autopatch test suite).

## Global Constraints

- **Worktree / git root:** `/home/martin/src/acq4/acq4/.claude/worktrees/autopatch-reuse-cells`, branch `claude/autopatch-feature-work-d23ccb`. Before any `git add`/`git commit`, confirm **both** `git rev-parse --show-toplevel` and `git branch --show-current`. Never commit into the main checkout (`/home/martin/src/acq4/acq4`), which sits on `_reviewed`.
- **Python interpreter / test runner:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v` (the `acq4-gl` env; `acq4-torch` lacks `gentletask`).
- **Qt import:** `from acq4.util import Qt`. Never import PyQt directly.
- **Style:** `black`. Match the surrounding conventions in `cell_panel.py`, which documents *why* in long comments — keep that density.
- **Comments** describe the code as it is. No temporal comments ("new", "now", "recently changed", "used to").
- **Commits:** conventional-commit format, one per task step-5. Use:
  `git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F <message-file>` with a body ending in the footer `🤖 Generated with [Claude Code](https://claude.ai/code)`. Write the message to a file so the footer survives — do **not** use single-line `-m`. **NEVER** `--no-verify`.
- **TDD, strictly:** write the failing test, run it and *see* it fail for the stated reason, implement the minimum, re-run, commit.
- **Mutation-test requirement.** Any test whose assertion is about *absence* or about a value that could already be trivially correct (`is None`, `== []`, `is False`, `not in`) must be proven non-vacuous: apply the defect (delete the guard being tested), observe the test fail, restore, observe it pass. Tasks below say which tests this applies to. This project has been bitten by vacuous assertions four times; the proof is not optional.
- **Two distinct string vocabularies, never crossed.** Cell dispositions (`done`/`skipped`/`stopped`/`retry-exhausted`/`error`/`retry`) come from `Orchestrator.sigCellFinished`. Action outcomes (`done`/`error`/`stopped`/`abandoned`) come from `ActionLogEntry.outcome` and drive `CellPanel._OUTCOME_GLYPHS`. This plan touches only the former.

## What is already built (do NOT re-implement)

The source spec (`docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md`) predates P2a/P2b/P2c. Two of its sections are obsolete:

- **Spec §1 and §5 ("selective flush on protocol load") are already done, by different and better means.** `bindOrchestrator` no longer flushes `self._cells`; it flushes `self._awaitingEnqueue`, the list of cells still *owed* an enqueue. A cell that has finished is never in that list. `test_a_finished_cell_is_not_flushed_into_a_later_orchestrator` (`acq4/modules/Autopatch/tests/test_cell_panel.py`) already guards it.
- **Implementing spec §5 as written would be a regression.** Gating the flush on `self._status.get(id(cell)) not in TERMINAL` would re-widen it to cells the panel only ever learned about from an orchestrator announcement — driving a pipette to a coordinate in discarded tissue, which is exactly the "too wide" direction that cost P2b two review rounds. **Do not touch `bindOrchestrator`'s flush loop.**

Spec §4's disposition vocabulary was re-verified against `acq4/experiment/orchestrator.py` on 2026-08-06 and is unchanged; the line numbers in the spec table have drifted but every status and site still matches.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `acq4/modules/Autopatch/cell_panel.py` | Area 5: cell queue, rows, timeline/log, and now disposition tracking + the reuse operation | Modify: `__init__`, `addCell`, `_onCellFinished`, `clearCells`, `_onCellsDiscarded`; add module constants, two buttons, `setInteractionLocked`, `_updateReuseButtons`, `_onCheckAllCompleted`, `_onReuseCheckedCells` |
| `acq4/modules/Autopatch/Autopatch.py` | Window: owns the panels and wires them together | Modify: one connection in `AutopatchWindow.__init__` |
| `acq4/modules/Autopatch/tests/test_cell_panel.py` | CellPanel unit tests | Add tests (Tasks 1–5) |
| `acq4/modules/Autopatch/tests/test_status_panel.py` | StatusPanel gating tests | Add the error-then-waiting ordering test (Task 6) |
| `acq4/modules/Autopatch/tests/test_window_integration.py` | Window-level integration | Add the multi-pass integration test + the wiring test (Tasks 5, 7) |
| `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` | Design doc (lives in the **main checkout**, untracked by design) | Correct §7 Area 5's now-false flush parenthetical (Task 8) |
| `docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md` | The source spec | Mark §1/§5 as built-by-other-means; record the three decisions taken here (Task 8) |

## Decisions taken before planning (do not re-litigate)

1. **Gating source: `StatusPanel.sigInteractionLocked`**, not a third `Orchestrator.sigStatus` connection in `CellPanel` (which is what spec §6.3 proposed). It is a permanent widget-tree connection needing no bind/unbind discipline, already routed to `ProtocolPanel` and `SearchPanel` for exactly this job, already emits `True` for `running`/`surveying`/`paused`, and already emits `False` on unbind. This removes spec §6.3's dangling-connection hazard entirely.
2. **Reuse must NOT clear `_attempted`.** `isAttempted()` means "the orchestrator has ever started work here" and is `Slice.forceRescan`'s predicate plus `discardCells`' skip rule. Clearing it on reuse would make a reused cell eligible for silent row-removal on the next rescan and drop it from the density record. A reused cell stays attempted forever.
3. **Reuse acts only on cells with a TERMINAL disposition.** Spec §8 notes a never-run cell "needs no reuse" but does not forbid it; nothing stops an operator checking a still-queued row and pressing the button, which would enqueue it a second time and run it twice. Reuse therefore skips any checked cell whose recorded disposition is not in `TERMINAL`, leaving its row text alone, and unchecks it so the operator sees the set cleared.

---

### Task 1: Record each cell's terminal disposition

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` (module constants after `_SCATTER_RADIUS`; `__init__`; `_onCellFinished`; `clearCells`; `_onCellsDiscarded`)
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: module-level `TERMINAL: frozenset[str]` and `COMPLETED: frozenset[str]` in `cell_panel.py`; `CellPanel._status: dict[int, str]`; `CellPanel.disposition(cell) -> str | None` returning the recorded terminal disposition, or `None` for a cell that has never reached one. Tasks 3, 4 and 5 use `disposition()` and both constants.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_cell_panel.py`:

```python
@pytest.mark.parametrize("status", ["done", "skipped", "stopped", "retry-exhausted", "error"])
def test_a_terminal_disposition_is_recorded(qapp, status):
    """Every status Orchestrator.sigCellFinished reports as terminal must be
    retrievable afterward: it is what "check all completed" and the reuse
    operation select on."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, status)

    assert panel.disposition(cell) == status


def test_a_never_run_cell_has_no_disposition(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    assert panel.disposition(cell) is None


def test_the_transient_retry_status_is_not_recorded_as_a_disposition(qapp):
    """"retry" is emitted mid-flight (Orchestrator._processCell) and is
    superseded by whatever terminal status the cell eventually reaches.
    Recorded as a disposition it would survive an interrupted run and read as
    though the cell had finished in a state named "retry"."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, "retry")

    assert panel.disposition(cell) is None


def test_a_retry_does_not_erase_an_earlier_terminal_disposition(qapp):
    """A cell reused for a second pass keeps its pass-1 disposition until the
    new pass reports its own terminal one; a transient "retry" in between must
    not blank it."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")

    panel._onCellFinished(cell, "retry")

    assert panel.disposition(cell) == "done"


def test_a_later_terminal_disposition_replaces_an_earlier_one(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "error")

    panel._onCellFinished(cell, "done")

    assert panel.disposition(cell) == "done"


def test_clear_cells_forgets_recorded_dispositions(qapp):
    """Left behind, a stale id would report a brand-new cell at a reused memory
    address as already completed, offering it up to "check all completed" --
    the same hazard _awaitingEnqueue and _attempted are cleared for."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")

    panel.clearCells()

    assert panel.disposition(cell) is None


def test_discard_cells_forgets_a_discarded_cells_disposition(qapp):
    """discardCells() drops the same per-cell stores clearCells() drops, scoped
    to a subset; a disposition left behind is the same stale-id hazard."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    # Recorded directly rather than through _onCellFinished: that marks the
    # cell attempted, and discardCells() never touches an attempted cell.
    panel._status[id(cell)] = "done"

    panel.discardCells([cell])

    assert panel.disposition(cell) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k "disposition or transient_retry"
```

Expected: every one FAILS with `AttributeError: 'CellPanel' object has no attribute 'disposition'` (and the `_status` one with `no attribute '_status'`).

- [ ] **Step 3: Implement**

In `cell_panel.py`, after the `_SCATTER_RADIUS` constant:

```python
# The dispositions Orchestrator.sigCellFinished reports for a cell that has
# finished a pass, in any state. "retry" is deliberately absent: it is emitted
# mid-flight and superseded by whichever of these the cell eventually reaches.
# A separate string space from ActionLogEntry.outcome (see _OUTCOME_GLYPHS),
# which describes one action rather than one cell.
TERMINAL = frozenset({"done", "skipped", "stopped", "retry-exhausted", "error"})
# The subset "Check all completed" ticks: only "done" means the protocol ran to
# completion. "error" and "retry-exhausted" are failures, and "stopped" and
# "skipped" are abandonment -- offering any of them up as a completion would
# re-queue cells that never did the work. Each is a manual opt-in instead.
COMPLETED = frozenset({"done"})
```

In `__init__`, beside `self._attempted`:

```python
        # id(cell) -> the last TERMINAL disposition sigCellFinished reported for
        # that cell; a cell absent from this dict has never finished a pass.
        # Distinct from self._attempted, which only answers whether work ever
        # started: a cell interrupted mid-run is attempted with no disposition,
        # and a cell re-queued for another pass keeps being attempted while its
        # disposition is cleared. Holds ids and plain strings, never cells, for
        # the same reason _attempted does.
        self._status: dict[int, str] = {}
```

In `_onCellFinished`, after `self._attempted.add(id(cell))`:

```python
        if status in TERMINAL:
            self._status[id(cell)] = status
```

Add the accessor beside `isAttempted`:

```python
    def disposition(self, cell) -> str | None:
        """The last terminal disposition reported for `cell`, or None if it has
        never finished a pass.

        None covers three cases the callers treat alike: never run, still
        running, and re-queued for another pass by reuseCheckedCells().
        """
        return self._status.get(id(cell))
```

In `clearCells`, beside `self._attempted.clear()`:

```python
        self._status.clear()
```

In `_onCellsDiscarded`, beside `self._attempted.discard(cellId)`:

```python
            self._status.pop(cellId, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v
```

Expected: all PASS, including the pre-existing tests. Output must be pristine.

- [ ] **Step 5: Prove the absence-assertions are not vacuous**

Three tests assert `is None`, which is `_status`'s default and therefore vacuous unless proven otherwise. For each, apply the defect, run, observe the failure, then restore:

| Test | Defect to apply | Must fail with |
|---|---|---|
| `test_the_transient_retry_status_is_not_recorded_as_a_disposition` | change the guard to `if status in TERMINAL or status == "retry":` | `assert 'retry' is None` |
| `test_clear_cells_forgets_recorded_dispositions` | delete `self._status.clear()` from `clearCells` | `assert 'done' is None` |
| `test_discard_cells_forgets_a_discarded_cells_disposition` | delete `self._status.pop(cellId, None)` from `_onCellsDiscarded` | `assert 'done' is None` |

Record the three observed failure messages in the task report. If any of them *passes* against its defect, the test is vacuous and must be rewritten before proceeding.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_panel.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F /tmp/msg.txt
```

with `/tmp/msg.txt`:

```
feat: record each cell's terminal disposition in Area 5

The reuse operation and "Check all completed" both select on which state a
cell finished its last pass in, which nothing tracked: _attempted only
answers whether work ever started. Cleared alongside _attempted on both the
whole-panel and per-cell teardown paths, so a recycled id() cannot report a
new cell as already completed.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 2: Make cell rows user-checkable

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` (`addCell`)
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: every row created by `addCell` carries `Qt.Qt.ItemIsUserCheckable` and starts `Qt.Qt.Unchecked`. Tasks 3, 4 and 5 read and write `item.checkState()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_new_row_is_checkable_and_starts_unchecked(qapp):
    """The checkbox is how an operator picks a reuse set; a row that starts
    checked would offer up cells nobody selected."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    panel.addCell(object())

    item = panel.cellList.item(0)
    assert bool(item.flags() & Qt.Qt.ItemIsUserCheckable)
    assert item.checkState() == Qt.Qt.Unchecked


def test_checking_a_row_does_not_change_the_inspected_cell(qapp):
    """Checking for reuse and selecting for inspection are independent
    gestures, so an operator can read one cell's log while a different set is
    checked (spec 6.1)."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    inspected = object()
    other = object()
    panel.addCell(inspected)
    panel.addCell(other)
    panel.cellList.setCurrentItem(panel._rows[id(inspected)])

    panel._rows[id(other)].setCheckState(Qt.Qt.Checked)

    assert panel.cellList.currentItem() is panel._rows[id(inspected)]
    assert panel._rows[id(inspected)].checkState() == Qt.Qt.Unchecked


def test_a_rows_check_state_survives_a_status_update(qapp):
    """_onCellFinished/_onCurrentCell call setText() on the same item; that must
    not disturb a check the operator has already made."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel._onCellFinished(cell, "done")

    assert panel._rows[id(cell)].checkState() == Qt.Qt.Checked
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k "checkable or checking_a_row or check_state_survives"
```

Expected: `test_a_new_row_is_checkable_and_starts_unchecked` FAILS on `assert bool(item.flags() & ...)` — a plain `QListWidgetItem` is not user-checkable and `checkState()` is not `Unchecked` until a check state is set. The other two may already pass; they are regression cover for Tasks 3–4.

- [ ] **Step 3: Implement**

In `addCell`, replace the item construction:

```python
        item = Qt.QListWidgetItem(f"cell {id(cell)} — queued")
        # Checkable so the operator can pick a set of already-run cells for
        # another pass (reuseCheckedCells()). Independent of selection, which
        # is what drives the timeline/log views: one cell can be inspected
        # while a different set is checked.
        item.setFlags(item.flags() | Qt.Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Qt.Unchecked)
        item.setData(Qt.Qt.UserRole, cell)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

Message:

```
feat: make Area 5's cell rows checkable

The checkbox is how an operator picks which already-run cells to re-queue
for another pass. Independent of selection, so one cell's log stays readable
while a different set is checked.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 3: "Check all completed" button

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` (button row in `__init__`; new `_onCheckAllCompleted`, `_updateCheckAllButton`, `_hasCompletedCell`; call the refresh from `_onCellFinished` and `clearCells` only — **not** from `addCell` (a cell with no disposition cannot change the completed set) and **not** from `_onCellsDiscarded` (see the note in Step 3))
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: `TERMINAL`/`COMPLETED` and `CellPanel.disposition(cell)` from Task 1; checkable rows from Task 2.
- Produces: `CellPanel.checkAllCompletedBtn` (a `Qt.QPushButton` labelled `"Check all completed"`) and `CellPanel._updateCheckAllButton()`. Task 4 adds a second button to the same row; Task 5 calls the same refresh helper pattern.

This button carries **no** run-state gate: ticking checkboxes mid-run is harmless because the reuse operation itself (Task 4) is what refuses to act during a run.

- [ ] **Step 1: Write the failing tests**

```python
def test_check_all_completed_checks_only_done_rows(qapp):
    """COMPLETED holds "done" alone. Every other terminal disposition is a
    manual opt-in, and "skipped" most of all: its name invites being read as a
    completion when it means the protocol abandoned the cell."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cells = {}
    for status in ("done", "skipped", "stopped", "retry-exhausted", "error"):
        cell = object()
        cells[status] = cell
        panel.addCell(cell)
        panel._onCellFinished(cell, status)
    neverRun = object()
    panel.addCell(neverRun)

    panel.checkAllCompletedBtn.click()

    assert panel._rows[id(cells["done"])].checkState() == Qt.Qt.Checked
    for status in ("skipped", "stopped", "retry-exhausted", "error"):
        assert panel._rows[id(cells[status])].checkState() == Qt.Qt.Unchecked, status
    assert panel._rows[id(neverRun)].checkState() == Qt.Qt.Unchecked


def test_check_all_completed_leaves_an_already_checked_row_checked(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.checkAllCompletedBtn.click()

    assert panel._rows[id(cell)].checkState() == Qt.Qt.Checked


def test_check_all_completed_is_disabled_with_nothing_completed(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "error")

    assert not panel.checkAllCompletedBtn.isEnabled()


def test_check_all_completed_enables_once_a_cell_completes(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)

    panel._onCellFinished(cell, "done")

    assert panel.checkAllCompletedBtn.isEnabled()


def test_check_all_completed_disables_again_once_the_panel_is_cleared(qapp):
    """The button must not stay enabled over a selection that no longer exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    assert panel.checkAllCompletedBtn.isEnabled()

    panel.clearCells()

    assert not panel.checkAllCompletedBtn.isEnabled()
```

**Do not add a `discardCells` variant of that test, and do not refresh this button from `_onCellsDiscarded`.** A rescan cannot change the completed set: `_onCellsDiscarded` skips any cell `isAttempted()` reports, and `_onCellFinished` marks a cell attempted *before* it can record a disposition — so no cell that owns a disposition is ever reachable by that loop. A test for it would have to prime `_status` directly, i.e. test a state production cannot produce.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k check_all
```

Expected: all FAIL with `AttributeError: 'CellPanel' object has no attribute 'checkAllCompletedBtn'`.

- [ ] **Step 3: Implement**

In `__init__`, extend the button row:

```python
        self.addFromTargetBtn = Qt.QPushButton("Add from target")
        self.scatterFakeCellsBtn = Qt.QPushButton("Scatter fake cells")
        self.checkAllCompletedBtn = Qt.QPushButton("Check all completed")
        self.addFromTargetBtn.clicked.connect(self._onAddFromTargetClicked)
        self.scatterFakeCellsBtn.clicked.connect(self._onScatterFakeCellsClicked)
        self.checkAllCompletedBtn.clicked.connect(self._onCheckAllCompleted)

        btnRow = Qt.QHBoxLayout()
        btnRow.addWidget(self.addFromTargetBtn)
        btnRow.addWidget(self.scatterFakeCellsBtn)
        btnRow.addWidget(self.checkAllCompletedBtn)
```

At the end of `__init__`, after the existing `connect` calls, seed the button's state (no cells yet, so it starts disabled):

```python
        self._updateCheckAllButton()
```

Add the handler and the refresh helper, after `disposition()`:

```python
    def _onCheckAllCompleted(self) -> None:
        """Tick every row whose cell ran its protocol to completion.

        A convenience for the common "reuse everything that worked" case; it
        only ever checks, never unchecks, so it composes with a selection the
        operator has already started making by hand.
        """
        for index in range(self.cellList.count()):
            item = self.cellList.item(index)
            if self.disposition(item.data(Qt.Qt.UserRole)) in COMPLETED:
                item.setCheckState(Qt.Qt.Checked)

    def _updateCheckAllButton(self) -> None:
        self.checkAllCompletedBtn.setEnabled(self._hasCompletedCell())

    def _hasCompletedCell(self) -> bool:
        return any(status in COMPLETED for status in self._status.values())
```

Call the refresh at the two places the completed set can change, each as the last statement of the method: the end of `_onCellFinished` and the end of `clearCells`. The same one line in each:

```python
        self._updateCheckAllButton()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v
```

Expected: all PASS.

- [ ] **Step 5: Prove the "only done" rule is not vacuous**

`test_check_all_completed_checks_only_done_rows` asserts four rows stay `Unchecked`, which is their default. Apply the defect `if self.disposition(...) in TERMINAL:` (i.e. `TERMINAL` in place of `COMPLETED`), run the test, and observe it fail on the `skipped` row. Restore and re-run. Record the failure message in the task report.

- [ ] **Step 6: Commit**

```
feat: add Area 5's "Check all completed" button

Ticks every row whose protocol ran to completion, for the common
reuse-everything-that-worked case. Only "done" qualifies: "skipped" and
"stopped" are abandonment and "error"/"retry-exhausted" are failures, so each
of those stays a manual opt-in.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 4: "Reuse checked cells" button, its gate, and the reuse operation

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py` (button row; `bindOrchestrator`; `unbindOrchestrator`; new `setInteractionLocked`, `_onReuseCheckedCells`, `_updateReuseButton`, `_checkedCells`)
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: `TERMINAL`/`COMPLETED`, `disposition()` (Task 1), checkable rows (Task 2), `_updateCheckAllButton()` (Task 3).
- Produces: `CellPanel.reuseCheckedCellsBtn` (`Qt.QPushButton`, label `"Reuse checked cells"`) and `CellPanel.setInteractionLocked(locked: bool) -> None`. Task 5 connects `StatusPanel.sigInteractionLocked` to that method.

The button and its gate ship in one task deliberately: an intermediate commit with a reuse button that is pressable mid-run would double-drive a pipette.

- [ ] **Step 1: Write the failing tests**

```python
def test_reuse_enqueues_the_same_cell_objects_in_list_order(qapp):
    """Reuse re-queues the *same* Cell objects, which is what carries each
    cell's tracker/reference stack into the next pass (design doc 6)."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    first, second, skipMe = object(), object(), object()
    for cell in (first, skipMe, second):
        panel.addCell(cell)
        panel._onCellFinished(cell, "done")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(first)].setCheckState(Qt.Qt.Checked)
    panel._rows[id(second)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [first, second]


def test_reuse_resets_the_row_to_queued_and_clears_its_history(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._timelines[id(cell)] = ["patch — ✓ done (1.00s)"]
    panel._logs[id(cell)] = ["pass 1 log line"]
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel._rows[id(cell)].text() == f"cell {id(cell)} — queued"
    assert panel._timelines[id(cell)] == []
    assert panel._logs[id(cell)] == []
    assert panel.disposition(cell) is None
    assert panel._rows[id(cell)].checkState() == Qt.Qt.Unchecked


def test_reuse_keeps_the_cell_attempted(qapp):
    """isAttempted() is Slice.forceRescan's predicate and discardCells()' skip
    rule: it means work has started here at some point, which reuse does not
    undo. Cleared, a reused cell would be silently dropped from Area 5 by the
    next rescan and removed from the density record."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel.isAttempted(cell) is True


def test_reuse_never_re_enqueues_a_cell_that_has_not_finished_a_pass(qapp):
    """Nothing stops an operator checking a still-queued row. That cell is
    already in the orchestrator's queue, so enqueuing it again would run it
    twice against the same tissue."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    queued, finished = object(), object()
    panel.addCell(queued)
    panel.addCell(finished)
    panel._onCellFinished(finished, "done")
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(queued)].setCheckState(Qt.Qt.Checked)
    panel._rows[id(finished)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [finished]
    assert panel._rows[id(queued)].text() == f"cell {id(queued)} — queued"
    assert panel._rows[id(queued)].checkState() == Qt.Qt.Unchecked


def test_reuse_leaves_unchecked_cells_alone(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    reused, untouched = object(), object()
    for cell in (reused, untouched):
        panel.addCell(cell)
        panel._onCellFinished(cell, "done")
    panel._logs[id(untouched)] = ["keep me"]
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel._rows[id(reused)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert orch.enqueued == [reused]
    assert panel.disposition(untouched) == "done"
    assert panel._logs[id(untouched)] == ["keep me"]
    assert panel._rows[id(untouched)].text() == f"cell {id(untouched)} — done"


def test_reuse_clears_the_detail_views_of_the_inspected_cell(qapp):
    """Spec 8: stale pass-1 timeline/log content must not linger in the pane
    for a cell that is now queued for pass 2."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._timelines[id(cell)] = ["patch — ✓ done (1.00s)"]
    panel._logs[id(cell)] = ["pass 1 log line"]
    panel._onCellFinished(cell, "done")
    panel.cellList.setCurrentItem(panel._rows[id(cell)])
    assert panel.timelineList.count() == 1
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.reuseCheckedCellsBtn.click()

    assert panel.timelineList.count() == 0
    assert panel.logView.toPlainText() == ""


def test_reuse_is_disabled_without_an_orchestrator(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_with_nothing_checked(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_enabled_once_bound_idle_and_checked(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())

    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    assert panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_while_a_run_is_in_flight(qapp):
    """"Start nothing new" at action boundaries, and never re-queue a cell the
    orchestrator may be working on right now."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)

    panel.setInteractionLocked(True)

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_re_enables_when_the_run_unlocks(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    panel.setInteractionLocked(True)

    panel.setInteractionLocked(False)

    assert panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_once_the_last_checked_row_is_discarded(qapp):
    """A rescan takes rows away with takeItem(), which emits no itemChanged --
    so nothing else re-evaluates the gate, and the button would stay enabled
    over a selection that no longer exists."""
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._status[id(cell)] = "done"
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    assert panel.reuseCheckedCellsBtn.isEnabled()

    panel.discardCells([cell])

    assert not panel.reuseCheckedCellsBtn.isEnabled()


def test_reuse_is_disabled_again_after_unbinding(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    cell = object()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.bindOrchestrator(_FakeOrchestrator())
    panel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
    assert panel.reuseCheckedCellsBtn.isEnabled()

    panel.unbindOrchestrator()

    assert not panel.reuseCheckedCellsBtn.isEnabled()
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k reuse
```

Expected: all FAIL with `AttributeError: 'CellPanel' object has no attribute 'reuseCheckedCellsBtn'` (the two lock tests additionally on `setInteractionLocked`).

- [ ] **Step 3: Implement**

In `__init__`, add the second button and the lock field. Place `self._interactionLocked = False` beside `self._orchestrator = None` at the top:

```python
        # Whether a run is in flight, as reported by StatusPanel.
        # sigInteractionLocked (wired in AutopatchWindow.__init__). Re-queuing a
        # cell mid-run could hand the orchestrator a cell it is working on right
        # now, so the reuse button is gated on this being False.
        self._interactionLocked = False
```

and in the button row:

```python
        self.reuseCheckedCellsBtn = Qt.QPushButton("Reuse checked cells")
        self.reuseCheckedCellsBtn.clicked.connect(self._onReuseCheckedCells)
        ...
        btnRow.addWidget(self.reuseCheckedCellsBtn)
```

Refresh gating whenever a check state changes — with the other `connect` calls at the end of `__init__`:

```python
        # setCheckState() (and setText(), harmlessly) emits itemChanged, which
        # is the only signal a QListWidget offers for "a row's checkbox moved".
        self.cellList.itemChanged.connect(self._onItemChanged)
        self._updateReuseButton()
```

Add, after `_onCheckAllCompleted`:

```python
    def _onItemChanged(self, _item) -> None:
        self._updateReuseButton()

    def setInteractionLocked(self, locked: bool) -> None:
        """Whether a run is in flight, so re-queuing must wait.

        Connected to StatusPanel.sigInteractionLocked rather than reading the
        orchestrator's sigStatus directly: that connection is made once in the
        window's constructor and never needs re-wiring per protocol load, so it
        cannot leave a bound orchestrator wired into a panel that has stopped
        tracking it -- the same reasoning ProtocolPanel.setInteractionLocked and
        SearchPanel.setInteractionLocked are wired this way for.
        """
        self._interactionLocked = locked
        self._updateReuseButton()

    def _updateReuseButton(self) -> None:
        enabled = (
            self._orchestrator is not None
            and not self._interactionLocked
            and any(self._checkedCells())
        )
        self.reuseCheckedCellsBtn.setEnabled(enabled)

    def _checkedCells(self) -> list:
        """The cells whose rows are ticked, in list order -- which is the order
        they will be patched in once re-queued."""
        return [
            self.cellList.item(index).data(Qt.Qt.UserRole)
            for index in range(self.cellList.count())
            if self.cellList.item(index).checkState() == Qt.Qt.Checked
        ]

    def _onReuseCheckedCells(self) -> None:
        """Re-queue the checked cells for another pass with the current protocol.

        The *same* Cell objects go back into the queue, so each one's tracker
        and reference stack carry into the next pass (design doc 6) -- which is
        what makes "cellfie everything, then patch everything" work. Their rows
        already exist, so this never calls addCell(), and it never records
        anything in _awaitingEnqueue: an orchestrator is bound (the button is
        gated on it), so the enqueue happens here and now, exactly once each.

        A checked cell that has not finished a pass is skipped rather than
        enqueued: it is still sitting in the orchestrator's queue, so a second
        enqueue would run it twice over the same tissue.
        """
        inspected = self._currentSelectedCell()
        reinspect = False
        for cell in self._checkedCells():
            item = self._rows[id(cell)]
            item.setCheckState(Qt.Qt.Unchecked)
            if self.disposition(cell) not in TERMINAL:
                continue
            self._orchestrator.enqueue(cell)
            item.setText(f"cell {id(cell)} — queued")
            # Pass 2 starts with a fresh timeline and log for this cell;
            # earlier-pass UI history is not retained. The tracker and
            # reference stack live on the Cell itself, not in these dicts, so
            # the cell's physical continuity is untouched.
            self._timelines[id(cell)] = []
            self._logs[id(cell)] = []
            # Queued again, so no longer holding a finished disposition. Note
            # _attempted is deliberately NOT cleared: work has started at this
            # coordinate at some point, which is what isAttempted() reports and
            # what keeps a rescan from silently dropping this row.
            self._status.pop(id(cell), None)
            if cell is inspected:
                reinspect = True
        if reinspect:
            self.timelineList.clear()
            self._timelineItems.clear()
            self.logView.clear()
        self._updateCheckAllButton()
        self._updateReuseButton()
```

In `bindOrchestrator`, at the very end (after the flush loop):

```python
        self._updateReuseButton()
```

In `unbindOrchestrator`, after `self._orchestrator = None`:

```python
        self._updateReuseButton()
```

And at the end of both `_onCellsDiscarded` (after its `for` loop) and `clearCells` — removing rows changes which cells are checked, and `takeItem()` emits no `itemChanged`, so nothing else re-evaluates the gate. Unlike the check-all button, this one genuinely needs the `_onCellsDiscarded` call: an operator can tick a never-run queued row, and a rescan discards exactly those:

```python
        self._updateReuseButton()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v
```

Expected: all PASS — the whole Autopatch suite, not just this file, since `bindOrchestrator`/`unbindOrchestrator` are touched.

- [ ] **Step 5: Prove the two absence-assertions are not vacuous**

| Test | Defect to apply | Must fail with |
|---|---|---|
| `test_reuse_never_re_enqueues_a_cell_that_has_not_finished_a_pass` | delete the `if self.disposition(cell) not in TERMINAL: continue` guard | `assert [queued, finished] == [finished]` (order per list position) |
| `test_reuse_keeps_the_cell_attempted` | add `self._attempted.discard(id(cell))` beside the `_status.pop` | `assert False is True` |
| `test_reuse_is_disabled_once_the_last_checked_row_is_discarded` | delete the `_updateReuseButton()` call from `_onCellsDiscarded` | `assert not True` |

Record both observed failures in the task report.

- [ ] **Step 6: Commit**

```
feat: add Area 5's "Reuse checked cells" multi-pass control

Re-queues the checked cells -- the same Cell objects, so each one's tracker
and reference stack carry forward -- and resets their rows to queued with a
fresh timeline and log. Gated on an orchestrator being bound, the run being
idle, and at least one row checked; a checked cell that never finished a pass
is skipped rather than enqueued a second time.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 5: Cover the run lock from StatusPanel to CellPanel

**Files:**
- Test only: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `CellPanel.setInteractionLocked(locked: bool)` from Task 4; `StatusPanel.sigInteractionLocked` (already exists, emits `True` for `running`/`surveying`/`paused` and `False` on unbind).
- Produces: nothing new.

**The implementation line already landed.** Task 4's review found that shipping the reuse button without its gate wired was the exact hazard this plan bundled button-and-gate together to avoid — so the one-line `connect` was pulled forward into Task 4's fix commit `49d012e4a`. Step 3 below is therefore already done; verify it is present rather than adding it again, and expect Step 1's test to **pass** on first run. That makes Step 2's defect-injection proof the real deliverable of this task: without it, a test that passed immediately is no evidence of anything.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_window_integration.py`:

```python
def test_a_run_in_flight_locks_area_5s_reuse_button(qapp, tmp_path):
    """The reuse gate rides StatusPanel.sigInteractionLocked, the same signal
    Areas 2 and 4 lock on -- a permanent widget-tree connection, so no protocol
    load or teardown can leave it wired to a stale orchestrator."""
    win = _makeWindow(tmp_path)
    try:
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.cellPanel._onCellFinished(cell, "done")
        win.cellPanel._rows[id(cell)].setCheckState(Qt.Qt.Checked)
        assert win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("running")
        assert not win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("surveying")
        assert not win.cellPanel.reuseCheckedCellsBtn.isEnabled()

        win.orchestrator.sigStatus.emit("waiting")
        assert win.cellPanel.reuseCheckedCellsBtn.isEnabled()
    finally:
        win.teardown()
```

- [ ] **Step 2: Run the test, then prove it is a real guard**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k locks_area_5
```

Expected: PASS, because the wiring landed in `49d012e4a`. A test that passes on first run proves nothing on its own, so prove it guards the wiring: **comment out** the `self.statusPanel.sigInteractionLocked.connect(self.cellPanel.setInteractionLocked)` line in `AutopatchWindow.__init__`, run the test, and observe it FAIL on the first `assert not ...isEnabled()` — with the lock unrouted the button stays enabled through `running`. Restore the line, re-run, observe PASS. Record both observed outcomes in the task report.

- [ ] **Step 3: Confirm the implementation is present**

Verify this line exists in `AutopatchWindow.__init__` beside the other two `sigInteractionLocked` connections. Do not add a second copy:

```python
        self.statusPanel.sigInteractionLocked.connect(self.cellPanel.setInteractionLocked)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v
```

Expected: all PASS, including `test_teardown.py` — this is a bound-method connection from a panel in the window's widget tree, not a closure over the window, so it must not introduce a reference cycle.

- [ ] **Step 5: Commit**

```
test: cover the run lock reaching Area 5's reuse button

Drives the real chain -- orchestrator status to StatusPanel to
sigInteractionLocked to CellPanel -- rather than calling the setter directly,
so the window's one-line wiring cannot be dropped without a test noticing.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 6: Prove Start comes back after a run that ends in error

**Files:**
- Test only: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `_makeWindow`, `_write_protocol` (existing helpers in that file).
- Produces: nothing.

Spec §6.4 requires this and no test covers it. `StatusPanel._updateButtons` disables Start on `"error"` and enables it on `"waiting"`; `Orchestrator._processCell` emits `"error"` and `_runLoopBody`'s `finally` then emits `"waiting"`. Start therefore comes back **only because of the emission order**, which is exactly the kind of thing that holds by inspection and breaks silently. `test_error_enables_only_stop` asserts the opposite for a bare `"error"` and must keep passing — it tests the mid-run state, this tests the post-run state.

- [ ] **Step 1: Write the failing test**

```python
_RAISING_PROTOCOL = '''
def run(ctx):
    raise RuntimeError("protocol blew up")
'''


def test_start_is_enabled_again_after_a_run_that_ends_in_error(qapp, tmp_path):
    """An operator whose run died must be able to press Start again -- e.g.
    after reusing the cells it never got to. That works only because
    _runLoopBody's finally emits "waiting" *after* _processCell emits "error",
    and "error" on its own disables Start. Asserted through the real
    orchestrator rather than a synthetic sigStatus("waiting").
    """
    from acq4.experiment.exceptions import AbortExperiment

    _write_protocol(tmp_path, "boom.py", _RAISING_PROTOCOL)
    win = _makeWindow(tmp_path)
    try:
        win.protocolPanel.fileCombo.setCurrentText("boom")
        win.cellPanel.addCell(_makeCell())

        with pytest.raises(AbortExperiment):
            win.orchestrator.run_sync()

        assert win.statusPanel.startBtn.isEnabled()
    finally:
        win.teardown()
```

- [ ] **Step 2: Run the test**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k ends_in_error
```

If it FAILS, the emission order does not hold and Start is stuck disabled after an error — stop and report; that is a real bug in `Orchestrator`/`StatusPanel` and fixing it is a separate task, not part of this one.

If it PASSES first time, that is the expected outcome: this task's deliverable is the **guard**, not a behavior change. Confirm it is a genuine guard by Step 3 before committing.

- [ ] **Step 3: Prove the test is a real guard, not a tautology**

Apply this defect to `acq4/modules/Autopatch/status_panel.py` — make `"waiting"` no longer re-enable Start, by changing `_updateButtons`'s idle test to exclude it (e.g. treat `"waiting"` like `"error"`). Run the test and observe it FAIL on `assert win.statusPanel.startBtn.isEnabled()`. Restore the file, re-run, observe PASS. Record both observations in the task report.

The helper's protocol combo entry is `"boom"` (`ProtocolDirectory` keys protocols by filename stem); if `setCurrentText` does not load it, check `win.protocolPanel.protocolFile.name` and fix the test's selection call rather than renaming the file.

- [ ] **Step 4: Commit**

```
test: assert Start returns after a run that ends in error

Start comes back only because _runLoopBody's finally emits "waiting" after
_processCell emits "error", and "error" alone disables it. That ordering held
by inspection only, and it is what lets an operator restart after reusing the
cells a failed run never reached.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 7: End-to-end multi-pass integration test

**Files:**
- Test only: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5, plus `_makeWindow`, `_write_protocol`, `_makeCell`.
- Produces: nothing.

- [ ] **Step 1: Write the failing test**

```python
_PASS_MARKING_PROTOCOL = '''
def run(ctx):
    seen = getattr(ctx.cell, "passes_seen", None)
    if seen is None:
        seen = []
        ctx.cell.passes_seen = seen
    seen.append(PASS_NAME)
'''


def test_reused_cells_run_a_second_protocol_as_the_same_objects(qapp, tmp_path):
    """The multi-pass workflow end to end: cellfie every cell in pass 1, load a
    patch protocol, reuse the same cells for pass 2. Identity is the whole
    point -- the same Cell object is what carries its tracker and reference
    stack into pass 2 (design doc 6), which is why this asserts on `is` and on
    state accumulated on the cell itself, not on positions.
    """
    _write_protocol(tmp_path, "pass1.py", _PASS_MARKING_PROTOCOL.replace("PASS_NAME", '"one"'))
    _write_protocol(tmp_path, "pass2.py", _PASS_MARKING_PROTOCOL.replace("PASS_NAME", '"two"'))
    win = _makeWindow(tmp_path)
    try:
        win.protocolPanel.fileCombo.setCurrentText("pass1")
        cell = _makeCell()
        win.cellPanel.addCell(cell)
        win.orchestrator.enqueue(cell)

        win.orchestrator.run_sync()

        assert cell.passes_seen == ["one"]
        assert win.cellPanel.disposition(cell) == "done"

        # Loading pass 2 must not silently re-run the completed cell: the reuse
        # button is the deliberate gate.
        win.protocolPanel.fileCombo.setCurrentText("pass2")
        assert win.orchestrator.pendingCells() == []

        win.cellPanel.checkAllCompletedBtn.click()
        win.cellPanel.reuseCheckedCellsBtn.click()

        assert win.orchestrator.pendingCells() == [cell]
        assert win.cellPanel._rows[id(cell)].text() == f"cell {id(cell)} — queued"

        win.orchestrator.run_sync()

        # Same object, so pass 1's accumulated state came along -- this is what
        # makes pass 2 inherit pass 1's reference stack for free.
        assert cell.passes_seen == ["one", "two"]
        assert win.cellPanel.disposition(cell) == "done"
        assert win.cellPanel.isAttempted(cell) is True
    finally:
        win.teardown()
```

- [ ] **Step 2: Run the test**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k same_objects
```

Expected: PASS, given Tasks 1–5. If `assert win.orchestrator.pendingCells() == []` fails, the flush is too wide and something in this branch regressed `bindOrchestrator` — stop and report rather than adjusting the assertion.

- [ ] **Step 3: Run the full suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ acq4/experiment/tests/ -v
```

Expected: all PASS, output pristine. Record the total count in the task report.

- [ ] **Step 4: Commit**

```
test: cover the multi-pass reuse workflow end to end

Run a protocol to done, load a second one, check all completed, reuse, and run
again -- asserting the same Cell object is what pass 2 receives, since that
identity is what carries each cell's tracker and reference stack forward.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

### Task 8: Correct the design doc and the source spec

**Files:**
- Modify: `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` (§7 Area 5) — **note the absolute path: this file lives in the main checkout and is deliberately untracked, so it is edited in place, not in this worktree, and it is not part of any commit.**
- Modify: `docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md` (§1, §4, §5, §6.3, §8) — in **this worktree**, and committed.

**Interfaces:** none.

- [ ] **Step 1: Correct the design doc's now-false claims**

In `§7 Area 5`, the **Reuse completed cells** bullet ends with a parenthetical that is now wrong twice over — the feature is built, and the flush it describes was replaced by P2b/P2c. Replace:

> *(Not built; designed in `docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md`. Until it lands, binding a newly loaded protocol flushes **every** held cell into it indiscriminately, completed ones included.)*

with:

> *(Built; plan at `docs/superpowers/plans/2026-08-06-autopatch-reuse-completed-cells.md`. The operator picks the reuse set with per-row checkboxes, with **Check all completed** as the shortcut for every `done` cell. Reuse is refused while a run is in flight, and a checked cell that has not finished a pass is skipped rather than queued twice. A reused cell stays `isAttempted()`: work has started at that coordinate, which is what keeps a rescan from silently dropping its row.)*

In the same section's **Disposition vocabulary** bullet, the `TERMINAL` line claims it is "what 'already run' means for the flush-on-load decision", which is not how the flush works. Replace that sub-bullet with:

> - `TERMINAL = {"done", "skipped", "stopped", "retry-exhausted", "error"}` — what "has finished a pass" means. A cell with one of these is what **Reuse checked cells** will re-queue; a cell without one is still queued and is skipped by reuse. The flush-on-load decision is a separate mechanism: `CellPanel` flushes `_awaitingEnqueue` (cells still *owed* an enqueue), not everything it holds.

- [ ] **Step 2: Mark the spec's obsolete sections**

In `docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md`, add immediately below the title:

```markdown
> **Status (2026-08-06): implemented**, with three sections superseded by code
> that landed after this spec was written. Plan:
> `docs/superpowers/plans/2026-08-06-autopatch-reuse-completed-cells.md`.
>
> - **§1 and §5 are obsolete.** The indiscriminate flush they describe was
>   already replaced by P2b/P2c's `_awaitingEnqueue` mechanism, which enqueues
>   only cells still *owed* a run. Implementing §5's `TERMINAL` check would
>   re-widen the flush to announced cells and drive a pipette into discarded
>   tissue. `bindOrchestrator` was left untouched.
> - **§6.3 was superseded.** Gating rides `StatusPanel.sigInteractionLocked`
>   (a permanent widget-tree connection) rather than a third
>   `Orchestrator.sigStatus` connection in `CellPanel`, which removes the
>   dangling-connection hazard §6.3 reasons about.
> - **§4's vocabulary was re-verified** against `acq4/experiment/orchestrator.py`
>   and is unchanged; only the line numbers in its table have drifted.
> - **§8 gained a case it was missing:** a checked cell that has *not* finished a
>   pass is skipped by reuse rather than enqueued, since it is still in the
>   orchestrator's queue and a second enqueue would run it twice.
> - **Reuse does not clear `_attempted`** (a store that postdates this spec):
>   that flag is `Slice.forceRescan`'s predicate, so clearing it would let the
>   next rescan silently drop a reused cell's row and remove it from the
>   density record.
```

- [ ] **Step 3: Verify no stale cross-references remain**

```bash
git grep -n "flushes every\|indiscriminate\|Not built" -- docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md
grep -n "Not built; designed in" /home/martin/src/acq4/acq4/autopatch-orchestration-design.md
```

Expected: the first may still match inside §1/§5 (now explicitly marked obsolete by the banner — that is fine; the sections are kept as the historical record). The second must return **nothing** for the Reuse bullet.

- [ ] **Step 4: Commit**

Only the spec is committed; the design doc is untracked in the main checkout.

```bash
git rev-parse --show-toplevel && git branch --show-current
git add docs/superpowers/specs/2026-07-24-autopatch-reuse-completed-cells-design.md
```

```
docs: record what superseded the reuse-completed-cells spec

Two of its sections were overtaken by P2b/P2c before the feature was built:
the indiscriminate flush it set out to replace was already gone, and the
gating connection it specified had a better route. Both kept as the
historical record, with the delta stated up front.

🤖 Generated with [Claude Code](https://claude.ai/code)
```

---

## Final verification

- [ ] Full touched-suite run, output pristine:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ acq4/experiment/tests/ -v
```

- [ ] `black --check acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/Autopatch.py`
- [ ] `git log --oneline _reviewed..HEAD` shows one commit per task, each with the `🤖 Generated with` footer (`git log --format=%B _reviewed..HEAD | grep -c "Generated with"` equals the commit count).
- [ ] No `_status` read anywhere outside `cell_panel.py` (`git grep -n "_status\b" -- acq4/modules/Autopatch | grep -v cell_panel`) — the disposition store is panel-private; `disposition()` is the accessor.
- [ ] Every mutation-test proof from Tasks 1, 3, 4 and 6 is recorded in the ledger with its observed failure message.

## Deliberately out of scope

- Area 2's `recycle` button (still a P1 placeholder; a later phase can route it to the same operation).
- Expanding `acq4_automation.Cell` to carry orchestration state (design doc §6) — still deferred until a consumer outside the panel needs it.
- Per-pass segmented timeline/log history: reuse clears both, per spec §7.
- §3.6's open question of whether reuse should be blocked after a tissue-motion event.
