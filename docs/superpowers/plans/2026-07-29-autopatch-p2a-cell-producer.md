# Autopatch P2a — Orchestrator cell producer / queue-depth refill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `Orchestrator` an optional cell-producer callback and a queue-depth
target, so the run loop can refill its queue as it drains instead of exiting the
moment the queue is momentarily empty — the engine half of design §3.2's
interleaved find+patch loop.

**Architecture:** `_runLoopBody`'s `while self._queue:` becomes a loop over two
conditions: refill while the queue is below target and the producer has not
declared itself exhausted, otherwise process the next queued cell, and end when
the queue is empty *and* the producer is exhausted. The producer is a plain
callable returning a sequence of new cells (`[]` meaning "made progress, found
nothing — ask again") or `None` (meaning "exhausted, never ask again"). Nothing
about cell processing, dispositions, retries, or the UI model changes. With no
producer configured the loop's observable behavior is byte-for-byte what it is
today.

**Tech Stack:** Python 3.12, PyQt (`acq4.util.Qt`), `acq4.util.task` for
concurrency, pytest + pytest-qt.

## Why this is P2's first task

Design §3.2 describes the interleaved loop as though it exists. It does not:
`acq4/experiment/orchestrator.py:135` is `while self._queue:`, which exits as
soon as the deque is momentarily empty. There is no depth target, no refill
hook, and no outer "regions remain" condition. Areas 1/2 (the survey UI, the
cell-finding config) cannot be built on top of a loop that stops the instant
detection hasn't yet produced a cell, so this engine change gates the rest of P2.

Of the three shapes considered, this plan implements the **refill callback**:
smallest diff, local to one method, headless-testable, and it preserves §3.3's
one-protocol-per-slice cell-bound context, the per-cell disposition model, and
Area 5's cell rows exactly as they are.

**Out of scope, deliberately:** the survey/region producer itself (P2c), the
cell-finding config UI that parameterises it (P2b), and any wall-clock timeout
on `_drive_fsm`'s poll loop (explicitly deferred — do not add one).

## Global Constraints

- Test runner: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- Verify with a hard timeout so a latent hang fails instead of stalling:
  `timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ acq4/modules/Autopatch/ -q`
- **Baseline: 259 tests passing** across `acq4/experiment/` + `acq4/modules/Autopatch/`,
  pristine, no skips, no ignores. Every task must leave it green and growing.
- Concurrency: `check_stop`/`sleep`/`Stopped`/`Event`/`run_in_gui_thread` from
  `acq4.util.task`. Never `time.sleep`/`threading` in production code.
- Logging: `from acq4.logging_config import get_logger`. Never stdlib `logging`.
- `from acq4.util import Qt`. 2-line docstring per new file. No temporal comments —
  describe the code as it is, never "used to", "now", "was changed".
- Engine code (`acq4/experiment/`) is **snake_case**; the `modules/Autopatch/` UI
  layer is camelCase. `Orchestrator`'s existing public methods are camelCase
  (`requestNextCell`, `run_sync` — it is a `QObject` straddling both); match the
  neighbouring members you are editing rather than imposing one style.
- Commit format:
  `git commit --author="Claude (claude) <noreply@anthropic.com>" -m "<type>: <desc>"`
  with a trailing `🤖 Generated with [Claude Code](https://claude.ai/code)` line.
  NEVER `--no-verify`.
- Branch: `claude/autopatch-orchestration-p2-8d7f8f`.

## Invariants that must not break

These are scar tissue. Each one is a bug this codebase has already shipped once.

- **Per-run state must not outlive the run loop it belongs to.** The existing
  `_nextCellRequested` needs clears at five per-exit sites *plus* two `finally`
  blocks, because `_runLoopBody`'s `finally` sits outside its `while` and so
  never fires between cells. `_producerExhausted` is new per-run state and is
  subject to exactly the same hazard. Task 3 is where this is proven.
- **A `FlowSignal` must never be swallowed.** `_processCell` treats
  `FlowSignal` and `Stopped` as pass-through, distinct from the broad
  `except Exception` that wraps bugs in `AbortExperiment`. The refill path must
  do the same, or a producer raising `AbortExperiment` gets double-wrapped.
- **Engine→UI callbacks are emit-only.** No widget mutation from the worker.
- `acq4/modules/Autopatch/tests/test_teardown.py`'s assertions are the exit-segfault
  regression test. **Do not change any assertion in it.** A producer callback is a
  new reference the `Orchestrator` holds; if you find yourself wanting to relax
  that file, stop and report instead.
- Do not add a wall-clock timeout to `_drive_fsm`. Deferred by decision.

## File Structure

| File | Responsibility |
|---|---|
| `acq4/experiment/orchestrator.py` (modify) | The loop change: `cellProducer`/`targetQueueDepth` config, `_refillQueue`, `_producerExhausted` lifecycle. The only production file this plan touches. |
| `acq4/experiment/tests/test_orchestrator_producer.py` (create) | All producer tests. A new file rather than growing `test_orchestrator_loop.py` (already ~470 lines) — the producer is its own concern with its own fixtures. |
| `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` (modify) | §3.2/§3.3 gain the actual contract. **Absolute path — this file lives in the main checkout, is untracked, and is NOT in the worktree.** Nothing to commit for it. |

---

## Task 1: Specify the refill contract in the design doc

Doc-only, and first: the next two tasks implement what this task writes down, and
a reviewer needs the contract to review against. §3.2 currently shows pseudocode
with no producer signature, no exhaustion rule, and no statement of what happens
when detection yields nothing.

**Files:**
- Modify: `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` §3.2, §3.3

**Interfaces:**
- Produces: the prose contract Tasks 2 and 3 implement. No code.

- [ ] **Step 1: Read the two sections and the current loop**

Read §3.1–§3.3 of the design doc, then `acq4/experiment/orchestrator.py:132-162`
(`_runLoopBody`). Confirm for yourself that the pseudocode and the code disagree
in the way this plan's preamble claims — if they do not, stop and report rather
than writing a contract for a problem that isn't there.

- [ ] **Step 2: Replace §3.2's pseudocode with the real contract**

Keep it terse and in the doc's existing voice. It must state, in this order:

1. The loop ends when the queue is empty **and** the producer is exhausted.
   With no producer configured, "exhausted" is the initial condition, so the
   loop is exactly a queue drain.
2. The producer is a plain callable, `producer() -> Sequence[cell] | None`,
   called with no arguments on the worker thread.
3. **`[]` and `None` mean different things.** `[]` is "I made progress and found
   no cells — ask me again" (an imaged tile that happened to be empty). `None`
   is "I am exhausted — never ask again" (every tile in the region is imaged).
   A producer that returns `[]` forever wedges the loop; it is the producer's
   contract to eventually return `None`. `check_stop()` runs between refills, so
   the operator's Stop always ends such a run.
4. Refilling repeats until the queue reaches the depth target or the producer
   exhausts, and **Pause and Stop are honoured between successive refills** —
   imaging a tile is slow, so an operator pressing Stop part-way through filling
   a deep queue must not wait for the whole batch.
5. The depth target is read fresh each pass, so the cell-finding config may
   change it mid-run. It must be at least 1.
6. `Stopped` and `FlowSignal` from the producer propagate untouched; any other
   exception is a bug, surfaced as `error` status and re-raised as
   `AbortExperiment`. There is no cell to attribute it to, so no
   `sigCellFinished` is emitted for it.
7. Why the depth target exists at all, given a serial orchestrator: detection
   yields several cells per z-stack, so the target's real job is "don't image a
   new tile until the queue is nearly drained", and it is the seam a future
   parallel scheduler needs.

- [ ] **Step 3: Add one line to §3.3**

§3.3 is "One protocol per slice." Add that this is unchanged by the producer:
cells arriving mid-run run the same slice protocol as cells seeded before Start,
and the context is still built per cell by the same factory.

- [ ] **Step 4: Remove the "not built" marker**

§3.2 carries a note that the loop is not implemented and is P2's undesigned
engine change. Tasks 2 and 3 build it, so that note goes — but only once this
task's contract text is in place, so the section is never simultaneously
marker-free and contract-free.

Nothing to commit: the file is untracked and outside the worktree. Report the
sections you edited.

---

## Task 2: The producer, the depth target, and the refill

**Files:**
- Modify: `acq4/experiment/orchestrator.py` — `__init__`, `_runLoopBody`; add
  `setCellProducer`, `_refillQueue`
- Create: `acq4/experiment/tests/test_orchestrator_producer.py`

**Interfaces:**
- Consumes: Task 1's contract. Existing `Orchestrator.enqueue(cell)`,
  `_checkPause()`, `_processCell(cell)`, `sigStatus`, `sigCellFinished`.
- Produces, relied on by Task 3 and by P2b/P2c:
  - `Orchestrator(protocolFile, manager=None, contextFactory=None, maxRetries=100, cellProducer=None, targetQueueDepth=1)`
  - `Orchestrator.setCellProducer(producer)` — swap or clear the producer;
    also clears the exhausted flag so a fresh producer is asked again.
  - `Orchestrator.targetQueueDepth` — public int attribute, read fresh each pass.
  - `Orchestrator._producerExhausted` — private bool, per-run.
  - Producer protocol: `producer() -> Sequence[cell] | None`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/experiment/tests/test_orchestrator_producer.py`:

```python
"""Tests for the Orchestrator's cell-producer refill hook: the queue-depth
target, the empty-vs-exhausted distinction, and end-of-run conditions."""
import pytest

from acq4.experiment.orchestrator import Orchestrator


def make_producer(batches):
    """A producer returning each of `batches` in turn, recording its calls.

    Each batch is either a list of cells or None (exhausted). Running past the
    end of `batches` is a broken test setup, not an implicit exhaustion, so it
    fails loudly rather than quietly ending the run.
    """
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        if not batches:
            raise AssertionError(
                "producer called after its last declared batch -- the loop "
                "asked again past exhaustion"
            )
        return batches.pop(0)

    producer.calls = calls
    return producer


def test_producer_fills_an_empty_queue_and_cells_are_processed(make_pf):
    """The whole point: a run started with nothing queued must still work
    cells, by asking the producer for them."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["c1", "c2"], None]))
    orch.run_sync()  # nothing enqueued up front
    assert ran == ["c1", "c2"]


def test_run_ends_when_queue_empty_and_producer_exhausted(make_pf):
    pf = make_pf()
    finished = []
    pf.run = lambda ctx, **kwargs: None
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync()  # must return, not spin
    assert finished == [("c1", "done")]


def test_empty_batch_asks_again_rather_than_ending_the_run(make_pf):
    """An imaged tile with no cells in it returns [] -- "found nothing, ask me
    again" -- which must NOT end the run the way None does. This is the
    distinction the whole survey loop rests on: a barren tile in the middle of
    a region cannot be allowed to stop the experiment."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    producer = make_producer([[], [], ["c1"], None])
    orch = Orchestrator(pf, cellProducer=producer)
    orch.run_sync()
    assert ran == ["c1"]
    assert producer.calls["n"] == 4  # two empty tiles, one productive, then exhausted


def test_queue_is_filled_to_target_depth_before_the_first_cell_runs(make_pf):
    """With a depth target above 1, the loop keeps asking until the queue
    reaches it -- so a producer yielding one cell per tile is asked three times
    before any cell is worked."""
    pf = make_pf()
    callsAtFirstRun = {}

    def run(ctx, **kwargs):
        callsAtFirstRun.setdefault("n", producer.calls["n"])

    pf.run = run
    producer = make_producer([["c1"], ["c2"], ["c3"], None])
    orch = Orchestrator(pf, cellProducer=producer, targetQueueDepth=3)
    orch.run_sync()
    assert callsAtFirstRun["n"] == 3


def test_depth_target_is_read_fresh_so_it_can_change_mid_run(make_pf):
    """The cell-finding config owns this number and an operator may change it
    while a run is in progress, so it must not be snapshotted at start."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        orch.targetQueueDepth = 1  # operator turns it down after the first cell

    pf.run = run
    producer = make_producer([["c1"], ["c2"], ["c3"], None])
    orch = Orchestrator(pf, cellProducer=producer, targetQueueDepth=2)
    orch.run_sync()
    assert ran == ["c1", "c2", "c3"]


def test_no_producer_drains_the_queue_and_ends(make_pf):
    """The unconfigured case -- every existing caller. Behaviour must be
    exactly the pre-producer queue drain, and in particular the loop must end
    rather than spin waiting for a refill that can never come."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert ran == ["c1", "c2"]


def test_producer_supplements_cells_seeded_before_start(make_pf):
    """Seeded cells and produced cells are the same queue: the operator's
    hand-added cells are worked first, then the producer's."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["produced"], None]))
    orch.enqueue("seeded")
    orch.run_sync()
    assert ran == ["seeded", "produced"]


def test_setCellProducer_installs_a_producer_after_construction(make_pf):
    """The UI builds the Orchestrator when a protocol is selected, but the
    producer depends on region/finding config chosen later, so it must be
    installable after the fact."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf)
    orch.setCellProducer(make_producer([["c1"], None]))
    orch.run_sync()
    assert ran == ["c1"]


def test_setCellProducer_none_reverts_to_a_plain_queue_drain(make_pf):
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["never asked"], None]))
    orch.setCellProducer(None)
    orch.enqueue("c1")
    orch.run_sync()
    assert ran == ["c1"]


def test_target_queue_depth_below_one_is_rejected(make_pf):
    """A target of 0 would make `len(queue) < target` never true, silently
    disabling the producer -- a misconfiguration that looks like a hung
    survey. Fail at construction instead."""
    pf = make_pf()
    with pytest.raises(ValueError):
        Orchestrator(pf, targetQueueDepth=0)
```

- [ ] **Step 2: Run the tests and confirm they fail for the right reason**

```bash
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v
```

Expected: the `cellProducer`/`targetQueueDepth` tests fail with
`TypeError: __init__() got an unexpected keyword argument`, `setCellProducer`
tests with `AttributeError`. `test_no_producer_drains_the_queue_and_ends` should
**pass already** — it pins existing behaviour. If it fails, stop and report.

- [ ] **Step 3: Add the constructor arguments**

In `Orchestrator.__init__`, after the `maxRetries` assignment:

```python
        if targetQueueDepth < 1:
            raise ValueError(
                f"targetQueueDepth must be at least 1, got {targetQueueDepth!r}: "
                f"a target of 0 makes the refill condition unreachable, silently "
                f"disabling the producer"
            )
        # Read fresh on every pass of the run loop rather than snapshotted, so
        # the cell-finding config can retune it while a run is in progress.
        self.targetQueueDepth = targetQueueDepth
        self._cellProducer = cellProducer
        # Per-run: set once the producer reports exhaustion, cleared by
        # _runLoopBody's finally. See setCellProducer for why it is not
        # simply "has the producer ever returned None".
        self._producerExhausted = False
```

and extend the signature:

```python
    def __init__(
        self,
        protocolFile,
        manager=None,
        contextFactory=None,
        maxRetries=100,
        cellProducer=None,
        targetQueueDepth=1,
    ):
```

- [ ] **Step 4: Add `setCellProducer`**

Next to `enqueue`, under the `# ---- queue / context ----` heading:

```python
    def setCellProducer(self, producer):
        """Install (or clear, with None) the callback that refills the queue.

        `producer()` takes no arguments, runs on the worker thread, and returns
        either a sequence of new cells -- possibly empty, meaning "made
        progress, found none here, ask again" -- or None, meaning exhausted.

        Installing a producer clears the exhausted flag: a caller swapping in a
        fresh producer (a new survey region) is declaring there is more to find,
        and would otherwise be ignored for the rest of the run.
        """
        self._cellProducer = producer
        self._producerExhausted = False
```

- [ ] **Step 5: Rewrite the loop and add `_refillQueue`**

Replace `_runLoopBody`'s `while self._queue:` block. Keep the existing
`except Stopped` clause and the existing `finally` body exactly as they are —
Task 3 extends the `finally`, this task must not.

```python
            while True:
                self._checkPause()
                check_stop()
                if self._shouldRefill():
                    self._refillQueue()
                    # Back to the top rather than falling through to a cell:
                    # re-checks the depth target (so a deep queue fills over
                    # several passes) and, more importantly, re-checks pause
                    # and stop between refills. Imaging a tile is slow, so an
                    # operator pressing Stop part-way through filling a deep
                    # queue must not have to wait out the whole batch.
                    continue
                if not self._queue:
                    # Queue empty and nothing left to produce: the run is done.
                    break
                cell = self._queue.popleft()
                self._processCell(cell)
```

and add, after `_checkPause`:

```python
    def _shouldRefill(self) -> bool:
        return (
            self._cellProducer is not None
            and not self._producerExhausted
            and len(self._queue) < self.targetQueueDepth
        )

    def _refillQueue(self):
        """Ask the producer for more cells; record exhaustion when it has none."""
        try:
            cells = self._cellProducer()
        except (Stopped, FlowSignal):
            # Same pass-through as _processCell: a cooperative stop is a normal
            # end to the run, and a producer that raises AbortExperiment means
            # it -- neither is a bug to be wrapped by the clause below.
            raise
        except Exception as exc:
            # An unexpected bug in the producer must fail loud rather than
            # quietly ending the survey and letting the run look complete.
            # There is no cell to attribute it to, so no sigCellFinished.
            logger.exception("Cell producer raised while refilling the queue")
            self.sigStatus.emit("error")
            raise AbortExperiment(f"cell producer failed: {exc}") from exc
        if cells is None:
            self._producerExhausted = True
            return
        for cell in cells:
            self.enqueue(cell)
```

- [ ] **Step 6: Run the new tests, then the full suite**

```bash
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ acq4/modules/Autopatch/ -q
```

Expected: all new tests pass; the suite is 259 + 10 = **269 passing**, no skips,
no warnings. If any pre-existing test fails, the loop rewrite changed behaviour
it should not have — report rather than adjusting the old test.

- [ ] **Step 7: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_producer.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "$(printf 'feat: let the orchestrator refill its cell queue from a producer\n\n🤖 Generated with [Claude Code](https://claude.ai/code)')"
```

---

## Task 3: Per-run state hygiene, and the interruption paths

Task 2's loop works. This task proves it is safe against the failure mode this
codebase produces over and over: state that outlives the run loop it belongs to.
`_producerExhausted` is exactly the shape of `_nextCellRequested`, whose leak
needed seven separate clears to close and silently skipped cells until it did.

**Files:**
- Modify: `acq4/experiment/orchestrator.py` — `_runLoopBody`'s `finally`
- Modify: `acq4/experiment/tests/test_orchestrator_producer.py`

**Interfaces:**
- Consumes: everything Task 2 produced.
- Produces: no new API. The guarantee that `_producerExhausted` is False
  whenever a run is not in progress.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_orchestrator_producer.py`. Note the new
imports at the top of the file:

```python
from acq4.util.task import Stopped, Event, sleep
from acq4.experiment.exceptions import AbortExperiment
```

```python
def test_exhaustion_does_not_outlive_the_run(make_pf):
    """The scar-tissue test. A producer that exhausted during one run must not
    leave the orchestrator permanently convinced there is nothing to find: the
    operator draws a second survey region, presses Start, and the new
    producer has to actually be asked. This is the same class of leak as the
    "Next cell" flag surviving its run and silently skipping an unrelated
    cell."""
    pf = make_pf()
    ran = []
    pf.run = lambda ctx, **kwargs: ran.append(ctx.cell)
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    orch.run_sync()
    assert ran == ["c1"]
    assert orch._producerExhausted is False  # cleared on the way out

    second = make_producer([["c2"], None])
    orch.setCellProducer(second)
    orch.run_sync()
    assert ran == ["c1", "c2"]  # the second region was actually surveyed
    assert second.calls["n"] == 2


def test_exhaustion_cleared_when_the_run_ends_by_raising(make_pf):
    """_runLoopBody can leave by raising as well as returning (an
    OrchestrationError from a cell re-raised as AbortExperiment). The clear
    belongs in the finally, not on the return path -- the same mistake that
    left the next-cell flag set on four separate raise paths."""
    pf = make_pf()

    def run(ctx, **kwargs):
        raise AttributeError("an ordinary bug, mid-cell")

    pf.run = run
    orch = Orchestrator(pf, cellProducer=make_producer([["c1"], None]))
    with pytest.raises(AbortExperiment):
        orch.run_sync()
    assert orch._producerExhausted is False


def test_exhaustion_cleared_after_a_cooperative_stop(make_pf):
    """Operator presses Stop after the region is exhausted but while cells
    remain queued, then presses Start again. The remaining cells must be
    worked, and the producer must be re-asked rather than assumed dry."""
    pf = make_pf()
    ran = []

    def run(ctx, **kwargs):
        ran.append(ctx.cell)
        if ctx.cell == "c1":
            raise Stopped("operator pressed stop")

    pf.run = run
    producer = make_producer([["c1", "c2"], None])
    orch = Orchestrator(pf, cellProducer=producer)
    orch.run_sync()  # a cooperative stop ends the run normally
    assert ran == ["c1"]
    assert orch._producerExhausted is False
    assert list(orch._queue) == ["c2"]  # a stop is not a queue drain


def test_producer_exception_surfaces_as_error_and_aborts(make_pf):
    """A bug in the producer (a detection crash, a stage move that throws)
    must not quietly end the survey and let the run report itself complete."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None

    def exploding_producer():
        raise RuntimeError("detection crashed")

    statuses = []
    orch = Orchestrator(pf, cellProducer=exploding_producer)
    orch.sigStatus.connect(statuses.append)
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync()
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert "error" in statuses


def test_producer_stopped_ends_the_run_normally(make_pf):
    """Stop pressed while the producer is imaging a tile: check_stop() inside
    the producer raises Stopped, which is a normal end to the run, not a
    raise the caller must catch."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None

    def stopping_producer():
        raise Stopped("operator pressed stop mid-survey")

    orch = Orchestrator(pf, cellProducer=stopping_producer)
    orch.run_sync()  # must not raise


def test_producer_abort_propagates_without_double_wrapping(make_pf):
    """A producer that raises AbortExperiment means it. It must propagate as
    itself rather than being caught by the broad clause and re-wrapped in a
    second AbortExperiment whose __cause__ is the first."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    sentinel = AbortExperiment("region is unusable")

    def aborting_producer():
        raise sentinel

    orch = Orchestrator(pf, cellProducer=aborting_producer)
    with pytest.raises(AbortExperiment) as excinfo:
        orch.run_sync()
    assert excinfo.value is sentinel


def test_pause_is_honored_before_refilling(make_pf, qtbot):
    """Pause means "start nothing new", and imaging a tile is very much
    something new -- an operator who pauses must not have the stage move to
    another tile underneath them."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    calls = {"n": 0}
    released = Event()

    def slow_producer():
        calls["n"] += 1
        sleep(0.005)  # paces tiles out so pause can land between them
        return [] if not released.is_set() else None

    orch = Orchestrator(pf, cellProducer=slow_producer)
    orch.pause()
    orch.start()
    qtbot.wait(100)
    assert calls["n"] == 0, "producer was asked for a tile while paused"

    orch.resume()
    qtbot.waitUntil(lambda: calls["n"] > 0, timeout=5000)

    released.set()
    orch.wait(timeout=5)


def test_stop_between_tiles_ends_a_barren_survey(make_pf, qtbot):
    """A producer returning [] forever is a wedged survey by construction.
    check_stop() between refills is what makes it interruptible, so the
    operator's Stop must end it."""
    pf = make_pf()
    pf.run = lambda ctx, **kwargs: None
    calls = {"n": 0}

    def barren_producer():
        calls["n"] += 1
        sleep(0.005)
        return []  # never exhausts

    orch = Orchestrator(pf, cellProducer=barren_producer)
    task = orch.start()
    qtbot.waitUntil(lambda: calls["n"] >= 2, timeout=5000)
    orch.stop("test stop")
    task.wait(timeout=5)  # a cooperative stop is a normal end, not a raise
    countAtStop = calls["n"]
    qtbot.wait(100)
    assert calls["n"] == countAtStop  # genuinely stopped asking
    assert orch._producerExhausted is False
```

- [ ] **Step 2: Run and confirm the failures**

```bash
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v
```

Expected: the three `_producerExhausted is False` assertions fail (the flag
leaks — nothing clears it yet). The exception-path and pause/stop tests should
already pass from Task 2's `_refillQueue` and loop ordering. **Confirm which
fail before implementing** — if the leak tests pass already, Task 2 clears the
flag somewhere it shouldn't and you must find out where.

- [ ] **Step 3: Clear the flag in the `finally`**

In `_runLoopBody`'s existing `finally`, next to the `_nextCellRequested` clear:

```python
            # Per-run, exactly like the next-cell request above: a producer
            # that exhausted during this run must not leave the orchestrator
            # permanently convinced there is nothing left to find. A later run
            # -- over a new survey region, or over cells still queued after a
            # stop -- has to ask again. Unlike the next-cell flag, this one
            # needs no per-exit clears: it is only ever read by the refill
            # check at the top of this method's own loop, so there is no
            # equivalent of _processCell's inner retry loop running past the
            # reach of this finally.
            self._producerExhausted = False
```

- [ ] **Step 4: Run the new tests, then the full suite**

```bash
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v
timeout 300 /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ acq4/modules/Autopatch/ -q
```

Expected: **277 passing** (259 baseline + 10 from Task 2 + 8 here), no skips, no
warnings.

- [ ] **Step 5: Confirm the teardown regression test is untouched**

```bash
git diff --stat acq4/modules/Autopatch/tests/test_teardown.py
```

Expected: empty. The `Orchestrator` now holds a producer reference; if that
introduced a cycle, `test_teardown.py` fails rather than needing edits. If it
does fail, report it — do not relax an assertion.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_producer.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "$(printf 'fix: keep producer exhaustion from outliving its run loop\n\n🤖 Generated with [Claude Code](https://claude.ai/code)')"
```

---

## Self-Review

**Contract coverage** — every numbered clause of Task 1's contract has a test:

| Contract clause | Test |
|---|---|
| 1. Ends when queue empty **and** producer exhausted | `test_run_ends_when_queue_empty_and_producer_exhausted`, `test_no_producer_drains_the_queue_and_ends` |
| 2. `producer() -> Sequence \| None`, no args | `test_producer_fills_an_empty_queue_and_cells_are_processed` |
| 3. `[]` asks again, `None` exhausts | `test_empty_batch_asks_again_rather_than_ending_the_run` |
| 4. Fills to target; Pause/Stop honoured between refills | `test_queue_is_filled_to_target_depth_before_the_first_cell_runs`, `test_pause_is_honored_before_refilling`, `test_stop_between_tiles_ends_a_barren_survey` |
| 5. Depth read fresh, min 1 | `test_depth_target_is_read_fresh_so_it_can_change_mid_run`, `test_target_queue_depth_below_one_is_rejected` |
| 6. `Stopped`/`FlowSignal` pass through; other exceptions abort | `test_producer_stopped_ends_the_run_normally`, `test_producer_abort_propagates_without_double_wrapping`, `test_producer_exception_surfaces_as_error_and_aborts` |
| 7. Rationale for the target (prose only) | n/a — doc |

**Landmine coverage** — checked against the bug classes this branch produced:

- *Per-run state outliving its loop* → Task 3 Steps 1/3, three tests covering
  the return, raise, and cooperative-stop exits. This is the plan's main risk
  and gets its own task and its own reviewer gate.
- *Flow signal swallowed* → `_refillQueue`'s `except (Stopped, FlowSignal): raise`
  mirrors `_processCell`, tested by `test_producer_abort_propagates_without_double_wrapping`.
- *Shared mutable state read by the worker* → `targetQueueDepth` is a plain int
  read fresh (atomic; deliberately not snapshotted, and tested as such). The
  producer *callable* is swappable via `setCellProducer`, which clears the
  exhausted flag so a swap can't leave incoherent state. The producer's own
  internal state (ROI geometry, visited tiles) is P2c's problem and is called
  out there, not here.
- *Reference cycles across the worker/GUI boundary* → Task 3 Step 5 verifies
  `test_teardown.py` still passes unmodified with the new producer reference.
- *Disposition vocabulary drift* → no new dispositions. A producer failure emits
  `error` **status** and no `sigCellFinished`, since no cell is implicated.

**Type consistency** — `cellProducer` (constructor kwarg) / `setCellProducer`
(method) / `_cellProducer` (attribute) / `targetQueueDepth` (public attribute
and kwarg, same spelling in both) / `_producerExhausted` / `_shouldRefill` /
`_refillQueue`. Used identically in every task. `make_producer` is defined once
at the top of the test file and used by both tasks' tests.

**Deliberately not here:** the survey/region producer (P2c), the cell-finding
config UI (P2b), Area 1's ROI ownership, the progress heatmap, and any
`_drive_fsm` timeout. Task 2's `setCellProducer` is the seam P2b/P2c attach to.

**Ordering:** 1 → 2 → 3, strictly. Task 1 writes the contract the other two are
reviewed against; Task 3's tests assume Task 2's API exists.
