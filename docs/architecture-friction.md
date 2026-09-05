<!-- Maintained by the `architecture-friction` agent skill. Humans welcome. -->

# Architecture friction

Places where this codebase's structure made a change harder than it should have
been, and the refactors that would relieve them.

This is **not** a bug tracker or a TODO list. Every entry answers one question:
*what would have made a change we actually made easy?*

- `## <a refactor direction>` — states a direction ("rework device locking so it
  can span threads"), not a specific design and not a place. Under it, one dated
  bullet per time that friction was felt.
- An occurrence may sit under several headings if any of those refactors would
  have relieved it. Its `(slug)` is identical in each, so all copies can be
  found and removed together when one lands.
- `## Unfiled` — raw notes captured mid-work, not yet sorted. An unsorted note
  still beats a forgotten one.
- `## Done` — refactors that landed, with dates, so the same friction doesn't
  get re-logged from scratch.

**Three bullets under one heading means the refactor is due.**

Adding an entry costs one line. Please add them.

## Give the orchestrator a boundary between a protocol's actions

P1.5 traded the `Protocol` DAG (`_walk`/`_runAction`) for plain-function
protocols. Worth it — but the orchestrator lost every per-action boundary with
it, and now regains control only when `run()` returns. Each time it needs to
interpose something mid-cell, that something has to be injected onto
`ExecutionContext` and called by whatever the author happens to run.

- [2026-07-28] (autopatch-next-cell-midpoll) "Next cell" was dropped for the
  whole duration of a cell; had to inject `next_cell_requested` onto ctx and
  poll it from inside actions.fsm, because there is no boundary the orchestrator
  can check at. Still no checkpoint at all for a protocol that never enters an
  FSM-driving action.
- [2026-09-04] (autopatch-pause-checkpoint) Same for Pause. Ended up adding a
  `pausable` flag to `ctx.log_action()` — a *reporting* seam — because opening a
  log entry is the only thing present at every action boundary. Design note:
  `docs/superpowers/specs/2026-09-04-autopatch-pause-granularity-friction.md`.
