# Autopatch — Reuse Completed Cells (Multi-Pass) — Design

Design spec for a user-facing "reuse completed cells" control in the Autopatch
module's Area 5 (`CellPanel`). It lets an operator re-queue already-run cells for
another pass with a *different* protocol — e.g. take GFP cellfies of every cell
in one pass, then load a patch protocol and patch the same cells in a second
pass. Because the *same* `Cell` objects are reused, each cell's tracker /
reference stack carries forward for free (design doc §6).

This is the resolved output of a design interview. It is scoped for a single
implementation plan.

---

## 1. Motivation

The autopatch orchestration design (`autopatch-orchestration-design.md`, §6 and
§7 Area 5) calls for a multi-pass workflow: run one protocol over all cells,
then reuse those same cells for another protocol. Pass 2 inherits pass 1's
reference stacks because the `Cell` object persists in `CellPanel._cells`.

Today that reuse happens *implicitly and indiscriminately*: selecting a protocol
in Area 4 loads it, and every genuine selection change drives
`AutopatchWindow._onProtocolLoaded` (`Autopatch.py:132`) to build a fresh
`Orchestrator`, whereupon `CellPanel.bindOrchestrator` (`cell_panel.py:92-103`)
flushes **every** held cell — completed, abandoned, stopped, or errored — into
the new queue. There is no operator control over which cells carry forward.

This feature replaces that implicit flush-everything with an explicit,
operator-controlled reuse action.

---

## 2. Scope

**In scope**

- Per-cell disposition tracking in `CellPanel`.
- A behavior change to `CellPanel.bindOrchestrator`: on protocol load, flush only
  cells that have never reached a terminal disposition.
- Per-row checkboxes in the cell list for choosing a reuse-set.
- Two buttons in Area 5: "check all completed" and "Reuse checked cells".
- Button gating by run state.
- Clearing a reused cell's timeline/log on reuse.

**Out of scope**

- Area 2's `recycle` button (Area 2 remains a P1 placeholder; a later phase can
  route it to the same reuse operation).
- Expanding the `Cell` class to carry orchestration state (design doc §6). The
  external `acq4_automation.Cell` is left unchanged; disposition is tracked
  UI-side. Deferred until a consumer outside the panel needs it (e.g. P2's slice
  progress heatmap).
- Per-pass segmented history (see §7).

---

## 3. Approach: CellPanel-local disposition tracking

Disposition is tracked in `CellPanel`, not on the `Cell` object and not in the
`Orchestrator`.

Rationale:

- `CellPanel` is already "the authoritative source of truth for seeded cells"
  (`cell_panel.py:167-172`) and already outlives every orchestrator — a fresh
  orchestrator is created and re-bound on each protocol load, but the panel and
  its `_cells` dict persist across passes.
- The `Orchestrator` is recreated per protocol load, so it cannot remember
  pass-1 outcomes into pass 2.
- The `Cell` class lives in the external `acq4_automation` package; adding a
  status field there would be a cross-repo change for a need that is currently
  UI-only. The engine deliberately does not depend on cell disposition today.

---

## 4. Data model

Add to `CellPanel`:

- `self._status: dict[int, str]` — keyed by `id(cell)`, holding the last
  terminal disposition emitted for that cell. Populated in the existing
  `_onCellFinished` handler (`cell_panel.py:304-307`). A cell **absent** from
  this dict is implicitly "queued" (never run to a terminal state).

Disposition vocabulary — the complete set of statuses
`Orchestrator.sigCellFinished` emits, one row per emission site:

| Status | Site | Meaning |
|---|---|---|
| `"done"` | `orchestrator.py:406` | `run()` returned normally: the protocol ran to completion |
| `"skipped"` | `orchestrator.py:296`, `:317` | a Next-cell request consumed at the cell/retry boundary, or `AdvanceToNextCell` propagating out of `run()`. **Abandoned without completing.** |
| `"stopped"` | `orchestrator.py:342` | a cooperative `Stopped`: the operator pressed Stop while this cell was mid-run |
| `"retry-exhausted"` | `orchestrator.py:326` | `maxRetries` blown against a persistently failing cell |
| `"error"` | `orchestrator.py:352`, `:364`, `:398` | an uncaught `OrchestrationError`, an unexpected exception, or a flow signal the protocol raised and then swallowed |
| `"retry"` | `orchestrator.py:328` | transient; superseded by whichever terminal status that cell eventually reaches |

There is no `"handled"` disposition: handler sub-protocols do not exist in the
engine, so nothing emits one.

```
TERMINAL  = {"done", "skipped", "stopped", "retry-exhausted", "error"}
COMPLETED = {"done"}
```

- `TERMINAL` — a cell that finished a pass in any of these states is *not*
  auto-flushed on the next protocol load; it waits for an explicit reuse.
  `"stopped"` belongs here even though the cell did not finish: silently
  re-running a cell the operator deliberately interrupted is exactly the
  indiscriminate behavior §1 exists to remove.
- `COMPLETED` — the set that "check all completed" ticks. It holds `"done"`
  alone, so the button means precisely *every cell whose protocol ran to
  completion*. Every other terminal disposition is a manual opt-in, each for its
  own reason:
  - `"error"` signals an aborted run, possibly a bug.
  - `"retry-exhausted"` is a *persistent* failure (`orchestrator.py:320-327`),
    not a completion. The rationale for excluding `"error"` applies verbatim.
  - `"stopped"` and `"skipped"` are both abandonment — the protocol never
    reached its end. `"skipped"` in particular is what `ctx.next_cell()` reports
    (`orchestrator.py:317`): the protocol, or the operator's Next-cell press,
    explicitly giving up on this cell. A protocol that runs to completion
    reports `"done"`, never `"skipped"` — neither bundled example protocol ends
    in a flow-control call, and none should. **`"skipped"` therefore does not
    belong in `COMPLETED`**: ticking it under "check all completed" would offer
    up cells that never did the work as though they had. If some future protocol
    ends by abandoning its cell, the thing to fix is that protocol, not this set.

The transient `"retry"` status (`orchestrator.py:328`) is not terminal and is
never stored as a final disposition — it is superseded by the eventual terminal
status for that cell.

---

## 5. Behavior change: selective flush on protocol load

`CellPanel.bindOrchestrator` currently flushes all `self._cells` into the newly
bound orchestrator:

```python
for cell in self._cells.values():
    orchestrator.enqueue(cell)
```

Change it to flush only cells whose recorded status is **non-terminal** (i.e.
`id(cell) not in self._status`, or its status is not in `TERMINAL`):

```python
for cell in self._cells.values():
    if self._status.get(id(cell)) not in TERMINAL:
        orchestrator.enqueue(cell)
```

Effects:

- Loading a pass-2 protocol no longer silently re-runs completed cells; the
  reuse button is the deliberate gate.
- Cells seeded-but-never-run still auto-enqueue, so the normal pre-seed workflow
  ("seed cells, then load a protocol, then Start") is unchanged.

---

## 6. UI — Area 5 (`CellPanel`)

### 6.1 Per-row checkboxes

Each cell row (`QListWidgetItem`) is made user-checkable
(`item.setFlags(item.flags() | Qt.Qt.ItemIsUserCheckable)` with an initial
`setCheckState(Qt.Qt.Unchecked)`) when created in `addCell`.

Clicking a row still selects it for inspection via the existing
`currentItemChanged` → `_onCellSelectionChanged` path; toggling the checkbox is
an independent gesture. So the operator can inspect one cell's log while a
different set of cells is checked for reuse.

### 6.2 Buttons

Two buttons are added to the existing button row (`cell_panel.py:68-75`),
alongside "Add from target" and "Scatter fake cells":

- **"check all completed"** — sets check state to checked for every row whose
  `self._status[id(cell)] ∈ COMPLETED`; leaves `skipped`, `stopped`,
  `retry-exhausted`, `error`, and never-run rows unchecked. A convenience for the
  common "reuse everything that worked" case.
- **"Reuse checked cells"** — for each checked cell, in list order:
  1. `self._orchestrator.enqueue(cell)` — the *same* `Cell` object.
  2. Reset the row text to `f"cell {id(cell)} — queued"`.
  3. Clear that cell's inspection history: `self._timelines[id(cell)] = []`,
     `self._logs[id(cell)] = []`.
  4. Reset disposition: `self._status.pop(id(cell), None)`.
  5. Uncheck the row.

  If the currently-inspected (selected) cell was among those reused, clear the
  timeline/log views so the stale pass-1 content does not linger.

### 6.3 Gating

"Reuse checked cells" is enabled only when **all** hold:

- an orchestrator is bound (a protocol is loaded), and
- the run is idle/waiting — not `running` or `paused` ("start nothing new"; also
  avoids re-queuing a cell that is currently being processed), and
- at least one row is checked.

To observe run state, `CellPanel.bindOrchestrator` additionally connects to
`Orchestrator.sigStatus`. `CellPanel.unbindOrchestrator` (`cell_panel.py:105-123`)
must disconnect it in the same change: that method disconnects exactly what
`bindOrchestrator` connects, 1-for-1, and both the rebind path (selecting a
different protocol) and window teardown go through it. A third connection with no
matching `Qt.disconnect` leaves a live orchestrator wired into a panel that has
stopped tracking it — the dangling-connection shape `test_teardown.py` guards
against. The panel caches the latest status string and re-evaluates button
enablement on status change and on checkbox toggle.

"check all completed" is enabled whenever ≥1 cell is in a `COMPLETED` state.

### 6.4 Running a pass

Re-queuing does not start a run. After pressing "Reuse checked cells", the
operator presses **Start** (Area 3 / `StatusPanel`) to run the current protocol
over the freshly-queued cells.

`StatusPanel` re-enables Start once a prior run reaches `waiting`:
`_updateButtons` enables Start for `None`/`"waiting"` (`status_panel.py:166-167`),
and `Orchestrator._runLoopBody`'s `finally` emits `"waiting"` on every exit path
(`orchestrator.py:222-242`). That holds by inspection, but it hangs on emission
*order*, not on a final state: the failure path emits `"error"`
(`orchestrator.py:351`) and only then `"waiting"` from the `finally`, and
`"error"` on its own disables Start (`status_panel.py:172-173`). So the
implementation must assert the ordering in a test — drive a run to `error`
through the real signal path and assert Start ends up enabled — rather than
assuming the terminal `"waiting"` wins.

---

## 7. Pass history: cleared on reuse

When a cell is reused, its timeline and log (`_timelines`/`_logs` for that
`id(cell)`) are cleared; pass 2 starts with a fresh timeline/log for that cell.
Earlier-pass UI history is **not** retained.

The cell's physical continuity is unaffected: the tracker / reference stack lives
on the persistent `Cell` object, not in the panel's log dicts, so pass 2 still
inherits pass 1's reference stack.

This simplifies the note in `autopatch-orchestration-design.md` §7 (Area 5, the
"Reuse completed cells" bullet, lines 404-411), which contemplates keeping
per-pass timeline/log segments. That line is updated to reflect clear-on-reuse.

---

## 8. Edge cases

- **No protocol loaded** — no orchestrator bound; "Reuse checked cells" disabled.
- **Nothing checked** — "Reuse checked cells" disabled (gated on ≥1 checked).
- **Run active** — both the reuse action and re-queuing are disabled while
  `running`/`paused`.
- **Currently-inspected cell reused** — its detail views (timeline/log) are
  cleared so stale content does not persist.
- **Cell never run, still queued** — not shown as "completed"; excluded from
  "check all completed"; already auto-enqueued on protocol load, so no reuse
  needed.

---

## 9. Testing (TDD)

Against the existing `config/mock` rig and `acq4_automation` mock
tracking/data. Test output must be pristine; error dispositions are asserted,
not printed.

**Unit (`CellPanel`)**

- `_onCellFinished` records each terminal status into `_status` keyed by
  `id(cell)`.
- "check all completed" checks exactly the `COMPLETED` rows; leaves `skipped`,
  `stopped`, `retry-exhausted`, `error`, and never-run rows unchecked. Cover
  `skipped` explicitly — it is the one status whose name invites being read as a
  completion.
- "Reuse checked cells" enqueues each checked `Cell` into the bound orchestrator,
  resets its row text to "queued", clears its `_timelines`/`_logs`, pops its
  `_status`, and unchecks it.
- `bindOrchestrator` flushes only non-terminal cells: a `done` cell is **not**
  re-enqueued on rebind; a never-run (queued) cell **is**.
- Button gating: "Reuse checked cells" disabled with no orchestrator, while
  `running`/`paused`, and with nothing checked; enabled otherwise.
- Start is enabled again after a run that ends in `error`, driven through the
  real `"error"`-then-`"waiting"` emission order rather than a single synthetic
  `sigStatus("waiting")` (§6.4).
- `unbindOrchestrator` leaves no `sigStatus` connection behind: rebinding to a
  second orchestrator must not let the first one still drive this panel's gating.

**Integration (mock rig)**

- Seed cells → run a cellfie protocol to `done` → load a patch protocol →
  "check all completed" + "Reuse checked cells" → Start → assert the *same*
  `Cell` objects are processed in pass 2 and each cell's reference stack from
  pass 1 is intact.

**Regression**

- Update any existing `CellPanel` test asserting the old flush-all behavior of
  `bindOrchestrator`.

---

## 10. Files touched

- `acq4/modules/Autopatch/cell_panel.py` — status dict, checkboxes, two buttons,
  reuse handler, selective-flush change, `sigStatus` subscription, gating.
- `acq4/modules/Autopatch/tests/` — new unit + integration tests; update
  flush-all regression test.
- `autopatch-orchestration-design.md` — amend §7 Area 5: clear-on-reuse (§7
  above), the selective-flush behavior (§5), the disposition vocabulary (Area 5
  still describes "Completed" as `done / handled` and the reset status as
  *waiting*; §4 above is the real set, and a cell row's reset text is
  `queued`).

No changes to `acq4/experiment/` (engine) or the external `acq4_automation`
package.
