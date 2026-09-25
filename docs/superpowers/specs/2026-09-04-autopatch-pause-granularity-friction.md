# Autopatch — pause granularity, and why the checkpoint has no home

Date: 2026-09-04
Status: friction note; §4 implemented, §4.1 provisional and awaiting a rig answer
Related: `2026-07-24-autopatch-p1-5-plain-function-migration.md` (the trade this
note is downstream of)

A record of an architectural friction found while asking how much finer the
Autopatch orchestrator's Pause could be made. The answer is "quite a lot, for
very little code" — but the only place to put the check is a seam that exists
for a different purpose. This note exists so the next person to touch pause,
per-action retry policy, or protocol structure finds the reasoning already
written down rather than rediscovering it.

---

## 1. What pause can and cannot mean here

The orchestrator's pause parks the worker thread. The worker thread is not
where the work happens:

| Operation | Runs on | Worker thread is |
|---|---|---|
| `_move` / `_focus` | motion planner | blocked in `.wait()` |
| `_drive_fsm` | the `PatchPipetteState`'s own `runJob` thread | polling `getState().stateName` |
| `cellfie`, `run_task` | imaging / TaskRunner | blocked in `.wait()` |
| tile survey | imaging | inside `producer()` |

So a pause check placed inside one of those waits pauses the **observer**, not
the rig. Pause can only ever mean *"do not start the next thing"*. Every
question about pause granularity is therefore the same question: **where are
the boundaries at which nothing is in flight?**

This is not a limitation to be engineered around. It is what pause means on a
rig where the hardware states are not themselves pausable — a pipette mid-
approach through tissue has no "hold here" that is safer than finishing.

## 2. The friction

Today there are two pause checks, both in `orchestrator.py`: the run-loop top
(`_runLoopBody`) and the retry-loop top (`_processCell`). Granularity is one
cell.

The boundaries we would want next are the ones *between actions* — between
`go_target` and `patch`, between `patch` and `clean`. The orchestrator cannot
see them. A protocol is a plain `def run(ctx, ...)` that calls action functions
as ordinary Python; its control flow belongs to the protocol author, and the
orchestrator gets control back only when `run()` returns.

The one thing that *is* present at every inter-action boundary is
`ctx.log_action()`. So that is where a checkpoint would go — and
`ctx.log_action()` is a **reporting** seam. It exists to feed Area 5 an
`ActionLogEntry`. Housing a control decision there conflates observation with
control, and rests the whole mechanism on a convention rather than a contract:

- An action that opens no log entry is silently not pausable, with nothing
  anywhere to say so.
- "Every action logs" is true by habit. Nothing enforces it, and nothing would
  fail if it stopped being true — pause would just quietly get coarser.
- The reporting seam now has a reason to be called that has nothing to do with
  reporting, so a future change to logging has to reason about pause.

## 3. Why the architecture is fighting us, and why that is still correct

This is a direct, documented consequence of P1.5. Before that migration the
orchestrator walked a `Protocol` DAG (`_walk`, `_runAction`): it owned a real
per-action boundary, and pause, next-cell, stop, and per-action reporting would
all have had an obvious home there. P1.5 deleted the DAG in favour of plain
functions, and introduced `ctx.log_action()` in the same change **as the
replacement for `sigActionFinished` + `Action.show()`** — that is, purely as the
reporting channel for what the orchestrator had stopped driving.

So `log_action` is the *shadow* of the removed step list. It is at every action
boundary because it inherited that position from the thing that used to own
those boundaries — not because it was ever given the job.

**The trade was right and this note does not propose undoing it.** Protocols
being ordinary readable Python is worth more than orchestrator-owned step
boundaries. What was paid for it is precisely this: the orchestrator can no
longer interpose between an author's statements, so any per-action policy —
pause, and anything like it later — has to be carried by something the author
calls anyway.

## 4. Decision: contain it in a named seam

Do **not** put the pause check inline in `log_action`. Instead:

- `ExecutionContext` gains `checkpoint()`, a named control seam. Headless /
  test-built contexts default it to a no-op, exactly as `next_cell_requested`
  already does; `Orchestrator._processCell` binds it to `_checkPause` alongside
  the existing `next_cell_requested` injection.
- `log_action` *calls* `ctx.checkpoint()` on entry. That is a trigger, not a
  home.

The difference is about five lines and it is the whole point of writing this
down. The responsibility lives somewhere honestly named, findable, and directly
testable; a protocol author who wants an explicit pause point mid-action can
call it; and when the boundary eventually moves (see §5), the trigger moves and
`checkpoint()` does not.

### 4.1 Which boundaries are refusable — provisional

Not every inter-action gap is safe to hold in. Pausing between `patch` and
`clean` leaves the pipette in a resting terminal state. Pausing between
`go_target` and `patch` leaves the tip parked in tissue under the previous
state's pressure. The checkpoint is therefore refusable: `log_action(name,
pausable=False)` withholds the checkpoint and nothing else — the Area 5 entry is
still opened and reported.

As landed, exactly two boundaries refuse: **`patch` and `reseal` at entry**.
Both are reached with the tip committed — parked at the target in tissue, or
holding a cell in whole-cell — so a pause requested during the approach is
carried past them and honoured at the next action, once the FSM has settled at a
declared terminal state. Every other action is pausable, including `clean`
(entered from a resting terminal) and the `only_if_needed` clean-skip.

**This assignment is provisional.** It follows from the one case with a written
argument behind it; the full "which gaps are safe to hold at" question is a rig
question, not a code question, and still needs a human answer. The alternative
shape — gating on the pipette reporting a resting state rather than on a
per-call-site flag — was not built, and remains open if the flag list starts
growing.

### Deliberately excluded

- **Inside `_drive_fsm`'s poll loop.** The FSM keeps running while the observer
  is parked, so pausing there stops appending to `transitions` (losing the state
  walk Area 5 exists to show) and risks the pipette moving *past* a terminal
  state unobserved — on resume the poll sees a state not in `terminals` and
  `raise_if_abnormal` fires. A pause after `reached` is set is the same
  checkpoint §4 already provides.
- **The `PatchPipette` state machine.** It is a device-level machine shared with
  MultiPatch and driven by hand from that UI; wiring an Autopatch run-loop flag
  into it couples a device to one module's queue. And "hold in the current
  state" is unsafe for the states that matter: `approach` is driving through
  tissue, `seal` is ramping suction, and `cell attached` is not a resting state
  on these rigs — it exits via spontaneous break-in or spontaneous detachment,
  so holding there is a gamble, not a pause.
- **Teardown paths** (`_closeCellDataDir`, `_drive_fsm`'s `finally`,
  `_safe_abort`). Pausing during cleanup wedges a run with a device half-
  unwound.
- **Mid-`run_task`.** Between-sweep gaps are part of the recording.

## 5. What would mean this is no longer enough

The containment in §4 holds while pause is the *only* per-action policy the
orchestrator wants. Signals that the boundary needs to become a real declared
thing again — most likely an `@action` decorator owning entry, checkpoint, and
policy together, which restores a thin slice of what `_walk` provided without
bringing back the DAG:

- A second per-action policy appears (per-action retry, timeout, or skip).
- Pause needs to be honoured somewhere an action does not open a log entry.
- "Which actions are pausable" stops being answerable by reading the call sites.

Until one of those lands, the cheap version is the right version.

The recurrence side of this is tracked in `docs/architecture-friction.md` under
*"Give the orchestrator a boundary between a protocol's actions"*, which as of
this note stands at two occurrences: `next_cell_requested` (2026-07-28) and this
one. A third means the refactor is due. This document holds the reasoning; that
file holds the count.

## 6. Also noted while looking

Good property worth not breaking: `_pauseEvent` is gentletask's `Event`, whose
`wait()` is stop-aware — a Stop during a pause raises `Stopped` immediately
rather than wedging. Any new checkpoint inherits this for free, and anything
that replaces the mechanism must preserve it.

Survey pause is honoured at tile boundaries (one `producer()` call images one
tile), which is tens of seconds. Finer would require injecting a checkpoint into
`make_tile_detector`, which is handed no execution context today. Low value;
not pursued.
