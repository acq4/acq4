# Autopatch P2c-2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the tissue-motion feedback loop between the cell tracker, the slice, and the orchestrator; and make **New slice** create a real Data Manager slice directory with Area 2 gated behind it.

**Architecture:** Two independent pieces sharing no code. Piece A spans two repos: `acq4-automation` gains a named `CellTrackingLost` exception and an opt-out for its movement guard; `acq4` gains a `TrackingLost` orchestration error, a `ctx.tissue_moved()` hook, a region-scoped `Slice.forceRescan()`, and the window glue that prompts the operator. Piece B factors `new_data_dir`'s body into a `manager`-only helper so a UI button can call it, reorders `newSlice()` so a failure discards nothing, and gives `SearchPanel` a second, independent lock reason.

**Tech Stack:** Python 3, PyQt5 via `acq4.util.Qt`, pytest, pyqtgraph, coorx.

**Spec:** `docs/superpowers/specs/2026-08-05-autopatch-p2c-2-tissue-motion-and-slice-dir-design.md`

## Global Constraints

- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Never `acq4-torch`.
- **acq4 test command:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q`
- **Baseline:** 510 tests pass in those two suites at `4a3c82e0b`. Any task ending with fewer than 510 passing has broken something.
- **acq4-automation repo:** `/home/martin/src/acq4/acq4-automation`, used by Tasks 1-3 only. **It is currently checked out on `feature/smooth-vector-field-z`, not `main`.** See Task 1 Step 0; do not resolve this by guessing.
- **Commit author:** `--author="Martin Chase (claude) <outofculture@gmail.com>"` on every commit in both repos.
- **Commit format:** conventional commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`), imperative mood, present tense.
- **Never** use `--no-verify`.
- **Comments are evergreen.** Describe the code as it is; never reference "the old behaviour", "previously", or this migration.
- **Do not widen `SearchRegion`.** Its contract is exactly `bounds()` + `overlapsTile()`. Adding `contains(point)` is explicitly rejected by the spec.
- **Do not replace the closed-form geometry in `search_region.py` with `QPainterPath`.** It was measured wrong: 24 of 225 tiles misreported at SI-metre scale.

---

## File Structure

**acq4-automation** (Tasks 1-3)

| File | Responsibility | Change |
|---|---|---|
| `acq4_automation/feature_tracking/interfaces.py` | Shared vocabulary: results, decisions, enums | Add `CellTrackingLost` |
| `acq4_automation/feature_tracking/__init__.py` | Package export surface | Export `CellTrackingLost` |
| `acq4_automation/feature_tracking/cell_tracker.py` | Tracker base: acquisition + validation | `validate_movement` param on `track_next_frame` |
| `acq4_automation/feature_tracking/cell.py` | `Cell` QObject: tracker lifecycle | `validate_movement` param on `updatePosition`; re-verify raises `CellTrackingLost` |
| `acq4_automation/feature_tracking/test_cell_tracking_lost.py` | **New.** Tests for all three above | Create |

**acq4 engine** (Tasks 4-8)

| File | Responsibility | Change |
|---|---|---|
| `acq4/experiment/exceptions.py` | Orchestration taxonomy | Add `TrackingLost` |
| `acq4/experiment/context.py` | Per-run bundle + flow control | Add `tissue_moved()` method + `tissue_moved_hook` field |
| `acq4/experiment/actions/device.py` | Device-wrapping protocol functions | `cellfie()` translates `CellTrackingLost` |
| `acq4/experiment/slice.py` | Search state for one piece of tissue | Add `forceRescan()`; `dirHandle` (Task 12) |
| `acq4/experiment/orchestrator.py` | Run loop, queue, producer | Extract `clearProducerExhausted()` |

**acq4 UI** (Tasks 9-13)

| File | Responsibility | Change |
|---|---|---|
| `acq4/modules/Autopatch/cell_panel.py` | Area 5: cell rows, timelines, logs | Track the attempted set; expose `isAttempted()` |
| `acq4/modules/Autopatch/context_factory.py` | Builds the per-cell `ExecutionContext` | Bind the `tissueMoved` hook |
| `acq4/modules/Autopatch/Autopatch.py` | The window; owns Slice + Orchestrator | `_onTissueMoved()`; `newSlice()` reorder; slice-ready wiring |
| `acq4/modules/Autopatch/search_panel.py` | Area 2 controls | Two independent lock reasons |
| `acq4/experiment/actions/storage.py` | Managed data directories | Extract `create_data_dir()` |

---

## Piece A - Tissue-motion feedback loop

### Task 1: `CellTrackingLost` exception (acq4-automation)

**Files:**
- Modify: `/home/martin/src/acq4/acq4-automation/acq4_automation/feature_tracking/interfaces.py`
- Modify: `/home/martin/src/acq4/acq4-automation/acq4_automation/feature_tracking/__init__.py`
- Test: `/home/martin/src/acq4/acq4-automation/acq4_automation/feature_tracking/test_cell_tracking_lost.py` (create)

**Interfaces:**
- Produces: `CellTrackingLost(ValueError)` with attribute `reason: str | None`. Importable as `from acq4_automation.feature_tracking import CellTrackingLost`. Tasks 2, 3, and 6 depend on this name and import path.

- [ ] **Step 0: Resolve the branch question before touching anything**

The repo is on `feature/smooth-vector-field-z` with a clean tracked tree (only untracked `best-segmenter` and `cellpose_grid_results.json`). The spec says the work belongs on `main`.

Run:

```bash
cd /home/martin/src/acq4/acq4-automation && git status -sb && git log --oneline -1 main
```

**Stop and ask the operator** which they want: switch this checkout to `main`, or branch off `main` here. Do not switch branches in a repo with active feature work without being told to. Note that `acq4_automation` is installed editable from *this* checkout, so a separate worktree would not be visible to acq4's tests without a `PYTHONPATH` override.

- [ ] **Step 1: Write the failing test**

Create `acq4_automation/feature_tracking/test_cell_tracking_lost.py`:

```python
"""CellTrackingLost: the named exception for a cell the tracker cannot re-find.

Subclassing ValueError is load-bearing, not incidental -- existing callers catch
ValueError from initializeTracker and must keep working.
"""

import pytest

from acq4_automation.feature_tracking import CellTrackingLost


def test_is_a_valueerror():
    # AutomationDebug/autopatch.py catches ValueError from initializeTracker and
    # skips the cell. Narrowing that to a non-ValueError would break it silently.
    assert issubclass(CellTrackingLost, ValueError)


def test_caught_by_a_bare_except_valueerror():
    try:
        raise CellTrackingLost("no features matched")
    except ValueError as exc:
        assert "no features matched" in str(exc)
    else:
        pytest.fail("CellTrackingLost was not caught as a ValueError")


def test_carries_the_tracker_reason():
    exc = CellTrackingLost("cell lost", reason="Too uncertain to track")
    assert exc.reason == "Too uncertain to track"


def test_reason_defaults_to_none():
    assert CellTrackingLost("cell lost").reason is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/martin/src/acq4/acq4-automation && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_tracking_lost.py -v
```

Expected: collection error, `ImportError: cannot import name 'CellTrackingLost'`.

- [ ] **Step 3: Add the exception**

In `interfaces.py`, after the imports and before `class TrackingAction`:

```python
class CellTrackingLost(ValueError):
    """The tracker could not re-find a cell against its own reference stacks.

    Raised only from Cell.initializeTracker's re-verify path, where a failure
    means the reference stacks are useless: the cell has drifted out of reach or
    died. Tracking failures during an ongoing patch -- a pipette occluding the
    features, say -- are a different condition and never raise this.

    Subclasses ValueError so callers that predate the named class keep catching
    it. `reason` carries the tracker's own reason_for_failure, which is what an
    operator being asked to authorise a rescan needs in order to answer.
    """

    def __init__(self, message: str, reason: str | None = None):
        super().__init__(message)
        self.reason = reason
```

In `__init__.py`, add:

```python
from acq4_automation.feature_tracking.interfaces import CellTrackingLost
```

- [ ] **Step 4: Run the test to verify it passes**

Same command as Step 2. Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/martin/src/acq4/acq4-automation && git add acq4_automation/feature_tracking/interfaces.py acq4_automation/feature_tracking/__init__.py acq4_automation/feature_tracking/test_cell_tracking_lost.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add CellTrackingLost for a cell the tracker cannot re-find"
```

---

### Task 2: `validate_movement` opt-out (acq4-automation)

**Files:**
- Modify: `acq4_automation/feature_tracking/cell_tracker.py` (`track_next_frame`)
- Modify: `acq4_automation/feature_tracking/cell.py` (`updatePosition`)
- Test: `acq4_automation/feature_tracking/test_cell_tracking_lost.py` (append)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `CellTracker.track_next_frame(force_refresh=False, feature_radius=None, validate_movement=True)` and `Cell.updatePosition(feature_radius=None, force_refresh=False, validate_movement=True)`. Task 3 calls `updatePosition(..., validate_movement=False)`.

- [ ] **Step 1: Write the failing test**

Append to `test_cell_tracking_lost.py`:

```python
import coorx

from acq4_automation.feature_tracking.cell_tracker import CellTracker
from acq4_automation.feature_tracking.interfaces import TrackingResult


class _StubTracker(CellTracker):
    """A CellTracker with acquisition and matching stubbed out.

    Only the movement-validation branch of track_next_frame is under test, so
    everything upstream of it returns a fixed successful result.
    """

    def __init__(self, result_position, last_position, movement_threshold):
        super().__init__(movement_threshold=movement_threshold)
        self._last_position = coorx.Point(last_position, "global")
        self._forced_result = TrackingResult(
            success=True,
            position=coorx.Point(result_position, "global"),
            offset=None,
            uncertainty=0.1,
            tracker_type="stub",
        )

    def _acquire_images(self, position, single):
        raise AssertionError("the stub must not acquire")

    def _track_single_frame(self):
        return self._forced_result

    def next_action(self):
        from acq4_automation.feature_tracking.interfaces import (
            TrackingAction,
            TrackingDecision,
        )

        return TrackingDecision(
            action=TrackingAction.SINGLE_FRAME, reason="stubbed"
        )


def _far_apart_tracker():
    # 500 um apart with a 50 um threshold: unambiguously over, at a realistic
    # stage coordinate rather than at the origin.
    return _StubTracker(
        result_position=(1e-3 + 500e-6, 2e-3, 0.0),
        last_position=(1e-3, 2e-3, 0.0),
        movement_threshold=50e-6,
    )


def test_movement_guard_rejects_a_far_jump_by_default():
    with pytest.raises(ValueError, match="moved too much"):
        _far_apart_tracker().track_next_frame()


def test_movement_guard_can_be_bypassed():
    # Re-verify re-establishes the baseline rather than continuing a track: if
    # the features matched, we know where the cell is, at any distance.
    result = _far_apart_tracker().track_next_frame(validate_movement=False)
    assert result.success


def test_bypassing_the_guard_still_updates_tracking_state():
    # The adopted position has to become the new baseline, or the next frame is
    # measured against a stale one and trips the guard that was just bypassed.
    tracker = _far_apart_tracker()
    tracker.track_next_frame(validate_movement=False)
    assert tracker.position.coordinates[0] == pytest.approx(1e-3 + 500e-6)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/martin/src/acq4/acq4-automation && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_tracking_lost.py -v -k movement
```

Expected: `test_movement_guard_rejects_a_far_jump_by_default` passes (existing behaviour), the other two FAIL with `TypeError: track_next_frame() got an unexpected keyword argument 'validate_movement'`.

If `test_movement_guard_rejects_a_far_jump_by_default` does *not* pass, the stub is not reaching `_validate_movement` and the other two tests would be vacuous. Fix the stub before continuing.

- [ ] **Step 3: Thread the parameter through**

In `cell_tracker.py`, change the signature:

```python
    def track_next_frame(
        self,
        force_refresh: bool = False,
        feature_radius: Optional[float] = None,
        validate_movement: bool = True,
    ) -> TrackingResult:
```

Add to its docstring's Parameters section:

```
        validate_movement : bool
            Whether to enforce the jump limit against the last tracked position.
            True for ongoing tracking, where frames are seconds apart and a large
            jump is implausible -- and where sigPositionChanged drives pipette
            targets, so a spuriously confident match is a hardware risk. False
            when re-establishing a baseline after a gap, where legitimate
            accumulated drift can exceed the same threshold.
```

Change the validation call:

```python
        # validate movement
        self.tracking_results.append(result)
        if validate_movement and result.success and result.position is not None:
            self._validate_movement(result)
```

In `cell.py`, change `updatePosition`:

```python
    def updatePosition(self, feature_radius=None, force_refresh=False, validate_movement=True):
```

and its call through:

```python
            result = self._tracker.track_next_frame(
                force_refresh=force_refresh,
                feature_radius=feature_radius,
                validate_movement=validate_movement,
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/martin/src/acq4/acq4-automation && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/ -q
```

Expected: all pass, including the pre-existing tracking tests.

- [ ] **Step 5: Commit**

```bash
cd /home/martin/src/acq4/acq4-automation && git add acq4_automation/feature_tracking/cell_tracker.py acq4_automation/feature_tracking/cell.py acq4_automation/feature_tracking/test_cell_tracking_lost.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: let a caller bypass the tracker's jump guard when re-baselining"
```

---

### Task 3: `initializeTracker` raises `CellTrackingLost` (acq4-automation)

**Files:**
- Modify: `acq4_automation/feature_tracking/cell.py` (`initializeTracker`)
- Test: `acq4_automation/feature_tracking/test_cell_tracking_lost.py` (append)

**Interfaces:**
- Consumes: `CellTrackingLost` (Task 1), `validate_movement` (Task 2).
- Produces: `Cell.initializeTracker` raises `CellTrackingLost` with `reason` set from `tracker.last_result.reason_for_failure`. Signature is **unchanged**. Task 6 catches this.

- [ ] **Step 1: Write the failing test**

Append to `test_cell_tracking_lost.py`:

```python
from acq4_automation.feature_tracking.cell import Cell


class _ReVerifyTracker:
    """Stands in for an already-initialized tracker on a Cell.

    Records how updatePosition's work was requested, so the re-verify path's
    contract can be asserted without any acquisition.
    """

    def __init__(self, succeed, reason=None):
        self._succeed = succeed
        self.position = coorx.Point((1e-3, 2e-3, 0.0), "global")
        self.last_result = TrackingResult(
            success=succeed,
            position=self.position if succeed else None,
            offset=None,
            uncertainty=0.1,
            tracker_type="stub",
            reason_for_failure=reason,
        )
        self.calls = []
        self.allow_refresh_reference = True

    def next_action(self):
        from acq4_automation.feature_tracking.interfaces import (
            TrackingAction,
            TrackingDecision,
        )

        return TrackingDecision(
            action=TrackingAction.SINGLE_FRAME, reason="stubbed"
        )

    def track_next_frame(self, force_refresh=False, feature_radius=None, validate_movement=True):
        self.calls.append(
            {"force_refresh": force_refresh, "validate_movement": validate_movement}
        )
        return self.last_result


def _cell_with_tracker(tracker):
    cell = Cell(coorx.Point((1e-3, 2e-3, 0.0), "global"))
    cell._tracker = tracker
    return cell


def test_reverify_failure_raises_celltrackinglost_with_the_reason():
    tracker = _ReVerifyTracker(succeed=False, reason="All object stacks failed to match")
    cell = _cell_with_tracker(tracker)
    with pytest.raises(CellTrackingLost) as caught:
        cell.initializeTracker(imager=None)
    assert caught.value.reason == "All object stacks failed to match"


def test_reverify_bypasses_the_movement_guard():
    # If the features matched, we adopt the new position at any distance.
    tracker = _ReVerifyTracker(succeed=True)
    _cell_with_tracker(tracker).initializeTracker(imager=None)
    assert tracker.calls[0]["validate_movement"] is False


def test_reverify_success_does_not_raise():
    tracker = _ReVerifyTracker(succeed=True)
    _cell_with_tracker(tracker).initializeTracker(imager=None)


def test_reverify_failure_is_still_catchable_as_valueerror():
    tracker = _ReVerifyTracker(succeed=False, reason="no features")
    cell = _cell_with_tracker(tracker)
    with pytest.raises(ValueError):
        cell.initializeTracker(imager=None)


def test_missing_reason_is_tolerated():
    # A tracker that failed without recording a reason must still raise, not
    # blow up reaching for the attribute.
    tracker = _ReVerifyTracker(succeed=False, reason=None)
    cell = _cell_with_tracker(tracker)
    with pytest.raises(CellTrackingLost) as caught:
        cell.initializeTracker(imager=None)
    assert caught.value.reason is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/martin/src/acq4/acq4-automation && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_tracking_lost.py -v -k reverify
```

Expected: `test_reverify_failure_raises_celltrackinglost_with_the_reason` FAILS (plain `ValueError`, not `CellTrackingLost`), `test_reverify_bypasses_the_movement_guard` FAILS (`validate_movement` is `True`).

- [ ] **Step 3: Change the re-verify path**

In `cell.py`, add the import:

```python
from acq4_automation.feature_tracking.interfaces import CellTrackingLost
```

Replace the `elif` branch of `initializeTracker`:

```python
        elif not self.updatePosition(
            feature_radius=feature_radius,
            force_refresh=force_refresh,
            # Re-verify re-establishes the baseline rather than continuing a
            # track. _last_position may be hours stale here, so legitimate
            # accumulated drift would trip a guard that exists to catch
            # implausible frame-to-frame jumps. If the features matched at all,
            # we know where the cell is and track from there.
            validate_movement=False,
        ):
            last = getattr(self._tracker, "last_result", None)
            reason = getattr(last, "reason_for_failure", None)
            raise CellTrackingLost(
                f"Cell moved too much to treat as tracked: {reason}", reason=reason
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd /home/martin/src/acq4/acq4-automation && /home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/ -q
```

Expected: all pass.

- [ ] **Step 5: Mutation-test the bypass assertion**

`test_reverify_bypasses_the_movement_guard` asserts a value that could be trivially already-correct. Prove it is not vacuous:

1. Change `validate_movement=False` back to `validate_movement=True` in `initializeTracker`.
2. Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4_automation/feature_tracking/test_cell_tracking_lost.py -k bypasses -v`
3. **Expected: FAIL.** If it passes, the stub is not recording the call and the test proves nothing.
4. Restore `validate_movement=False`. Re-run: PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/martin/src/acq4/acq4-automation && git add acq4_automation/feature_tracking/cell.py acq4_automation/feature_tracking/test_cell_tracking_lost.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: raise CellTrackingLost with the tracker's reason on a failed re-verify"
```

---

### Task 4: `TrackingLost` orchestration error (acq4)

**Files:**
- Modify: `acq4/experiment/exceptions.py`
- Test: `acq4/experiment/tests/test_exceptions.py`

**Interfaces:**
- Produces: `acq4.experiment.exceptions.TrackingLost(OrchestrationError)`, `typeName = "TrackingLost"`. Tasks 5 and 6 import it.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_exceptions.py`:

```python
def test_tracking_lost_is_an_orchestration_error():
    from acq4.experiment.exceptions import OrchestrationError, TrackingLost

    # Routed by the taxonomy, not surfaced as an unexpected bug: a cell the
    # tracker cannot re-find is a domain condition with a defined response.
    assert issubclass(TrackingLost, OrchestrationError)
    assert TrackingLost.typeName == "TrackingLost"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_exceptions.py -v -k tracking_lost
```

Expected: FAIL, `ImportError: cannot import name 'TrackingLost'`.

- [ ] **Step 3: Add the exception**

In `acq4/experiment/exceptions.py`, after `class NoSolution`:

```python
class TrackingLost(OrchestrationError):
    """The cell tracker could not re-find a cell against its reference stacks.

    Deliberately not in ABNORMAL_STATE_EXCEPTIONS: this is not a pipette FSM
    state, it is what a re-verify reports. Reaching the orchestrator uncaught
    halts the run, which is the right default wherever no tissue-motion hook is
    bound to handle it (see ExecutionContext.tissue_moved).
    """

    typeName = "TrackingLost"
```

- [ ] **Step 4: Run the test to verify it passes**

Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/exceptions.py acq4/experiment/tests/test_exceptions.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add TrackingLost to the orchestration exception taxonomy"
```

---

### Task 5: `ctx.tissue_moved()` hook (acq4)

**Files:**
- Modify: `acq4/experiment/context.py`
- Test: `acq4/experiment/tests/test_context.py`

**Interfaces:**
- Consumes: `TrackingLost` (Task 4).
- Produces:
  - `ExecutionContext.tissue_moved_hook: Callable[[ExecutionContext, str], None] | None = None` — a field.
  - `ExecutionContext.tissue_moved(reason: str) -> NoReturn` — a **method**. Never returns normally.
  - The hook is invoked as `hook(ctx, reason)`. Task 10 binds `partial(window._onTissueMoved, cell)`, so the window's handler signature is `(cell, ctx, reason)`.

**Why a method plus a field, rather than a plain callable field like `log`:** the hook needs the context in order to prompt and to call `ctx.next_cell()`. Storing a `partial` that closes over the context would make the context reference itself — a cycle reclaimable only by the cyclic GC, which is exactly the failure mode Autopatch's deterministic teardown exists to avoid. Passing `self` at call time costs nothing and stores nothing.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_context.py`:

```python
def test_tissue_moved_raises_trackinglost_when_no_hook_is_bound():
    # Headless and in tests there is no window to prompt, so a re-find failure
    # is the plain error it is and the catch-all halts the run. Safe default.
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import TrackingLost

    ctx = ExecutionContext()
    with pytest.raises(TrackingLost, match="no features"):
        ctx.tissue_moved("no features")


def test_tissue_moved_passes_the_context_and_reason_to_the_hook():
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import AdvanceToNextCell

    seen = []

    def hook(ctx, reason):
        seen.append((ctx, reason))
        ctx.next_cell()

    ctx = ExecutionContext(tissue_moved_hook=hook)
    with pytest.raises(AdvanceToNextCell):
        ctx.tissue_moved("tissue drifted")
    assert seen == [(ctx, "tissue drifted")]


def test_tissue_moved_never_returns_normally_even_if_the_hook_does():
    # The contract is that this call does not come back. A hook that forgets to
    # end the cell must not leave the protocol running against a stale
    # coordinate; falling through to the safe default is what stops that.
    from acq4.experiment.context import ExecutionContext
    from acq4.experiment.exceptions import TrackingLost

    ctx = ExecutionContext(tissue_moved_hook=lambda ctx, reason: None)
    with pytest.raises(TrackingLost):
        ctx.tissue_moved("hook returned")


def test_tissue_moved_hook_is_not_stored_as_a_bound_partial():
    # A hook closing over the context would make the context reference itself.
    # Assert the field holds exactly what was passed in.
    from acq4.experiment.context import ExecutionContext

    def hook(ctx, reason):
        ctx.next_cell()

    ctx = ExecutionContext(tissue_moved_hook=hook)
    assert ctx.tissue_moved_hook is hook
```

Ensure `import pytest` is present at the top of the file.

- [ ] **Step 2: Run the test to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_context.py -v -k tissue_moved
```

Expected: all four FAIL with `TypeError: __init__() got an unexpected keyword argument 'tissue_moved_hook'` or `AttributeError: 'ExecutionContext' object has no attribute 'tissue_moved'`.

- [ ] **Step 3: Add the field and the method**

In `acq4/experiment/context.py`, extend the import:

```python
from .exceptions import (
    AbortExperiment,
    AdvanceToNextCell,
    FlowSignal,
    RetryCurrentCell,
    TrackingLost,
)
```

Add the field after `next_cell_requested`:

```python
    # Supplied by the Autopatch window's context factory: the capability to
    # react to a cell the tracker could not re-find. Called as hook(ctx, reason)
    # -- the context is passed at call time rather than bound into the hook,
    # because a stored closure over this object would make it reference itself,
    # and a cycle here is only reclaimable by the cyclic GC. The engine holds no
    # slice knowledge; this is how the window lends it some.
    tissue_moved_hook: Callable[[Any, str], None] | None = field(
        default=None, repr=False
    )
```

Add the method next to `next_cell`/`retry_cell`/`abort`:

```python
    def tissue_moved(self, reason: str) -> None:
        """Report that the tracker could not re-find this cell. Never returns.

        With a hook bound, the window prompts the operator and ends the cell,
        which leaves this call by way of a FlowSignal. With no hook -- headless,
        or a context built directly by a test -- a re-find failure is the plain
        TrackingLost error it is, and the orchestrator's catch-all halts the run.

        The fall-through raise is not dead code: a hook that returns instead of
        ending the cell would otherwise let the protocol carry on against a
        coordinate we have just established is stale.
        """
        if self.tissue_moved_hook is not None:
            self.tissue_moved_hook(self, reason)
        raise TrackingLost(reason)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_context.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/context.py acq4/experiment/tests/test_context.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add the tissue_moved hook to ExecutionContext"
```

---

### Task 6: `cellfie()` translates `CellTrackingLost` (acq4)

**Files:**
- Modify: `acq4/experiment/actions/device.py` (`cellfie`)
- Test: `acq4/experiment/tests/test_actions_device.py`

**Interfaces:**
- Consumes: `CellTrackingLost` (Task 1), `ctx.tissue_moved` (Task 5).
- Produces: no new names. `cellfie` gains one `try/except`.

The precedent for translating a library exception at the action boundary is `find_surface`, in this same module.

- [ ] **Step 1: Write the failing test**

The existing `test_actions_device.py` has a fake cell with `initializeTracker` (around line 170). Append:

```python
def test_cellfie_routes_a_lost_cell_to_the_tissue_moved_hook(monkeypatch, tmp_path):
    from acq4_automation.feature_tracking import CellTrackingLost

    from acq4.experiment.actions.device import cellfie
    from acq4.experiment.exceptions import AdvanceToNextCell

    seen = []

    def hook(ctx, reason):
        seen.append(reason)
        ctx.next_cell()

    ctx = _cellfie_context(monkeypatch, tmp_path, tissue_moved_hook=hook)
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features matched")

    with pytest.raises(AdvanceToNextCell):
        cellfie(ctx)
    assert seen == ["no features matched"]


def test_cellfie_lets_an_unrelated_valueerror_propagate(monkeypatch, tmp_path):
    # Only the named class is tissue motion. A bare ValueError out of the
    # tracker stack is a bug, and classifying it as motion would trigger a
    # destructive rescan whose prompt defaults to "Rescan".
    from acq4.experiment.actions.device import cellfie

    called = []
    ctx = _cellfie_context(
        monkeypatch, tmp_path, tissue_moved_hook=lambda c, r: called.append(r)
    )
    ctx.cell.tracker_error = ValueError("something else entirely")

    with pytest.raises(ValueError, match="something else entirely"):
        cellfie(ctx)
    assert called == []


def test_cellfie_with_no_hook_raises_trackinglost(monkeypatch, tmp_path):
    from acq4_automation.feature_tracking import CellTrackingLost

    from acq4.experiment.actions.device import cellfie
    from acq4.experiment.exceptions import TrackingLost

    ctx = _cellfie_context(monkeypatch, tmp_path)
    ctx.cell.tracker_error = CellTrackingLost("lost", reason="no features")

    with pytest.raises(TrackingLost):
        cellfie(ctx)
```

Add a `_cellfie_context` helper alongside the existing device-test fakes. Follow the file's established fake style; the fake cell's `initializeTracker` must raise `self.tracker_error` when set:

```python
def _cellfie_context(monkeypatch, tmp_path, tissue_moved_hook=None):
    """An ExecutionContext wired for cellfie with the z-stack save stubbed out.

    cellfie's imaging is real-hardware work; only its tracker-initialization
    tail is under test here.
    """
    monkeypatch.setattr(
        "acq4.experiment.actions.device.run_image_sequence",
        lambda *a, **k: _ImmediateFuture(),
    )
    return ExecutionContext(
        cell=_TrackerFakeCell(),
        pipette=_CellfieFakePipette(),
        manager=_FakeManager(tmp_path),
        tissue_moved_hook=tissue_moved_hook,
    )
```

Build `_TrackerFakeCell`, `_CellfieFakePipette`, `_FakeManager`, and `_ImmediateFuture` from the fakes already in this file — reuse them where they exist rather than duplicating. `_TrackerFakeCell.initializeTracker` is:

```python
    def initializeTracker(self, imager, use_cellpose=False):
        self.tracker_calls.append((imager, use_cellpose))
        if self.tracker_error is not None:
            raise self.tracker_error
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -v -k cellfie
```

Expected: the two hook tests FAIL (`CellTrackingLost` propagates uncaught); `test_cellfie_lets_an_unrelated_valueerror_propagate` passes already.

- [ ] **Step 3: Translate at the boundary**

In `acq4/experiment/actions/device.py`, add the import:

```python
from acq4_automation.feature_tracking import CellTrackingLost
```

Replace the last line of `cellfie`:

```python
        # Initialize the tracker reference used to follow the cell during patching.
        try:
            ctx.cell.initializeTracker(imager, use_cellpose=True)
        except CellTrackingLost as exc:
            # The tracker could not re-find this cell against its own reference
            # stacks, so the stacks are useless: the cell has drifted out of
            # reach or died. That is a question about the tissue, not about this
            # action, and the window is what can answer it. Never returns.
            ctx.tissue_moved(exc.reason or str(exc))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/actions/device.py acq4/experiment/tests/test_actions_device.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: route a lost cell from cellfie to the tissue-moved hook"
```

---

### Task 7: `Slice.forceRescan()` (acq4)

**Files:**
- Modify: `acq4/experiment/slice.py`
- Test: `acq4/experiment/tests/test_slice.py`

**Interfaces:**
- Produces: `Slice.forceRescan(position, isAttempted) -> int`.
  - `position`: an indexable global coordinate; only `[0]` and `[1]` are read, so a `coorx.Point` and a plain tuple both work.
  - `isAttempted`: `Callable[[cell], bool]`. Task 9 supplies `CellPanel.isAttempted`.
  - Returns the number of tiles un-covered. Tasks 10 and its tests use the count.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_slice.py`:

```python
class _PositionedCell:
    """A stand-in for acq4_automation's Cell: a position is all Slice reads."""

    def __init__(self, position):
        self.position = position


def _two_region_slice():
    """A slice with two well-separated regions at realistic stage coordinates.

    Deliberately not at the origin, and deliberately not square: a symmetric
    fixture cannot test an asymmetric mapping, and origin-centred geometry
    cannot see coordinate-magnitude float error.
    """
    s = Slice(fov=(20e-6, 10e-6))
    s.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    s.addRegion(RectRegion(5e-3, 7e-3, 5e-3 + 60e-6, 7e-3 + 30e-6))
    return s


def test_force_rescan_uncovers_only_the_region_holding_the_position():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    covered_before = len(s.coveredTiles)

    uncovered = s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert uncovered > 0
    remaining = s.coveredTiles
    assert len(remaining) == covered_before - uncovered
    # Every surviving covered tile belongs to the far region.
    far = s.regions[1]
    assert all(far.overlapsTile(t, (20e-6, 10e-6)) for t in remaining)


def test_force_rescan_outside_every_region_is_a_no_op():
    # A hand-seeded cell outside every drawn region has no coverage to
    # invalidate; hand-added cells are outside the scanner's responsibility.
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    before = list(s.coveredTiles)

    assert s.forceRescan((9e-3, 9e-3), lambda cell: False) == 0
    assert s.coveredTiles == before


def test_force_rescan_deregisters_only_never_attempted_cells():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    tile = s.tileGrid()[0]
    attempted = _PositionedCell((tile[0], tile[1], -30e-6))
    fresh = _PositionedCell((tile[0], tile[1], -35e-6))
    s.registerCells([attempted, fresh])

    s.forceRescan(tile, lambda cell: cell is attempted)

    near = s.cellsNearTile(tile)
    assert attempted in near
    assert fresh not in near


def test_force_rescan_leaves_cells_in_untouched_regions_registered():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    far_tile = [t for t in s.tileGrid() if t[0] > 4e-3][0]
    far_cell = _PositionedCell((far_tile[0], far_tile[1], -30e-6))
    s.registerCells([far_cell])

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert far_cell in s.cellsNearTile(far_tile)


def test_force_rescan_does_not_touch_regions_or_constraints():
    s = _two_region_slice()
    for tile in s.tileGrid():
        s.markCovered(tile)
    regions_before = s.regions
    constraints_before = s.constraints

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert s.regions == regions_before
    assert s.constraints is constraints_before


def test_force_rescan_uncovers_every_overlapping_region():
    # Overlapping regions both hold the position, so both must be re-imaged.
    s = Slice(fov=(20e-6, 10e-6))
    s.addRegion(RectRegion(1e-3, 2e-3, 1e-3 + 60e-6, 2e-3 + 30e-6))
    s.addRegion(RectRegion(1e-3 + 20e-6, 2e-3, 1e-3 + 80e-6, 2e-3 + 30e-6))
    for tile in s.tileGrid():
        s.markCovered(tile)

    s.forceRescan((1e-3 + 30e-6, 2e-3 + 15e-6), lambda cell: False)

    assert s.coveredTiles == []
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v -k force_rescan
```

Expected: all FAIL with `AttributeError: 'Slice' object has no attribute 'forceRescan'`.

- [ ] **Step 3: Implement**

In `acq4/experiment/slice.py`, add after `resetCoverage`:

```python
    def forceRescan(self, position, isAttempted) -> int:
        """Re-open the region(s) around `position` for imaging. Returns tiles freed.

        The response to the tracker losing a cell: the coordinates around it are
        no longer trustworthy, so the coverage record claiming that ground was
        already searched has to go, and the cells found there have to be
        rediscovered where they actually are now.

        Scoped to the region(s) the position falls in, not the whole slice. An
        operator working through their third region should not pay to re-image
        the two they finished, and re-imaging a finished region is also a chance
        to re-detect and re-patch cells already dealt with.

        The cost of that scoping, deliberately accepted: tissue motion is global,
        while this treats it as local. If the slice genuinely shifted, finished
        regions are stale too and are not re-imaged here. That is the right
        trade for settling, drift, and swelling -- motion small relative to a
        region -- and the wrong one for a slice that was physically bumped, where
        the tool is New slice rather than a rescan. Nothing here can tell those
        two cases apart.

        `isAttempted` decides which cells survive. Attempted cells stay
        registered at their old positions -- near enough, since the motion is
        small -- so they keep counting toward the density cap and the rescan is
        less likely to resurface a cell already worked. Never-attempted cells are
        dropped so their tiles can come back uncrowded and be found again where
        they now are. The predicate is a parameter because attempted-ness is
        orchestration state held by the UI, not something a slice can know.

        A position inside no region frees nothing: a hand-seeded cell was never
        part of the survey, so there is no coverage of it to invalidate.
        """
        here = [r for r in self._regions if r.overlapsTile(position, self._fov)]
        if not here:
            return 0
        stale = [
            t
            for t in self._covered
            if any(r.overlapsTile(t, self._fov) for r in here)
        ]
        if not stale:
            return 0
        drop = set()
        for tile in stale:
            for cell in self.cellsNearTile(tile):
                if not isAttempted(cell):
                    drop.add(id(cell))
        self._cells = [c for c in self._cells if id(c) not in drop]
        staleIds = {id(t) for t in stale}
        self._covered = [t for t in self._covered if id(t) not in staleIds]
        return len(stale)
```

**Note on the identity filter:** `stale` holds the very tuple objects that are in `self._covered`, so filtering by `id()` removes exactly those and cannot accidentally drop an equal-valued tile from another region. Do not rewrite this as a value comparison.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -q
```

Expected: all pass.

- [ ] **Step 5: Mutation-test the two absence assertions**

`test_force_rescan_deregisters_only_never_attempted_cells` and `test_force_rescan_leaves_cells_in_untouched_regions_registered` both assert something is *absent* or *unchanged*, and would pass against broken code if the fixture never reaches the distinguishing state.

For each, apply the defect, confirm the test fails, then restore:

1. Replace `if not isAttempted(cell)` with `if True` — run `-k deregisters`. **Expected FAIL** (the attempted cell is dropped too). Restore.
2. Replace `here = [...]` with `here = list(self._regions)` — run `-k untouched_regions`. **Expected FAIL** (the far region's cell is dropped). Restore.
3. Re-run the full file: all pass.

If either mutant passes, the test is vacuous — fix the fixture before continuing.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/slice.py acq4/experiment/tests/test_slice.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: add region-scoped Slice.forceRescan for a moved slice"
```

---

### Task 8: `Orchestrator.clearProducerExhausted()` (acq4)

**Files:**
- Modify: `acq4/experiment/orchestrator.py`
- Test: `acq4/experiment/tests/test_orchestrator_producer.py`

**Interfaces:**
- Produces: `Orchestrator.clearProducerExhausted() -> None`. `setCellProducer` calls it. Task 10 calls it directly.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_orchestrator_producer.py`, following the file's existing fixture style:

```python
def test_clear_producer_exhausted_lets_an_exhausted_producer_be_asked_again():
    # A producer that reported exhaustion is never asked again for the rest of
    # the run. After a forced rescan there are uncovered tiles once more, so the
    # flag has to be cleared or the loop ends on a queue the producer could
    # have refilled.
    orch = Orchestrator()
    orch.setCellProducer(lambda: None)
    orch._producerExhausted = True

    orch.clearProducerExhausted()

    assert orch._producerExhausted is False
    assert orch._shouldRefill() is True


def test_set_cell_producer_still_clears_exhaustion():
    # The extraction must not move behaviour off setCellProducer, which existing
    # callers rely on.
    orch = Orchestrator()
    orch._producerExhausted = True
    orch.setCellProducer(lambda: [])
    assert orch._producerExhausted is False
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -v -k producer_exhausted
```

Expected: the first FAILS with `AttributeError: 'Orchestrator' object has no attribute 'clearProducerExhausted'`; the second passes.

- [ ] **Step 3: Extract the method**

In `acq4/experiment/orchestrator.py`, add next to `setCellProducer`:

```python
    def clearProducerExhausted(self) -> None:
        """Ask the producer again, even though it already reported exhaustion.

        The flag is a per-run cache of "there is nothing left to find". Anything
        that puts uncovered tiles back on the slice -- installing a producer, or
        a forced rescan after the tissue moved -- invalidates it, and leaving it
        set ends the run on a queue that could have been refilled.
        """
        self._producerExhausted = False
```

and change `setCellProducer`'s body to use it:

```python
        self._cellProducer = producer
        self.clearProducerExhausted()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_producer.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_producer.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "refactor: extract clearProducerExhausted from setCellProducer"
```

---

### Task 9: `CellPanel` tracks which cells were attempted (acq4)

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Produces: `CellPanel.isAttempted(cell) -> bool`. Task 7's `forceRescan` takes this as its predicate; Task 10 passes it.

**Definition:** a cell is *attempted* once the orchestrator has started work on it — recorded from **both** `sigCurrentCell` and `sigCellFinished`. Both, not just the latter: a cell interrupted mid-run may never emit a terminal status, and `retry` is emitted mid-flight without being terminal. Asking "has work started" avoids re-deriving the terminal-status list, which the reuse-completed-cells spec still owes.

- [ ] **Step 1: Write the failing test**

Append to `acq4/modules/Autopatch/tests/test_cell_panel.py`, matching the file's existing panel/orchestrator fixture style:

```python
def test_a_queued_cell_is_not_attempted(qapp):
    panel = CellPanel()
    cell = _makeCell()
    panel.addCell(cell)
    assert panel.isAttempted(cell) is False


def test_a_running_cell_is_attempted(qapp):
    # A cell interrupted mid-run may never emit a terminal status, so starting
    # work on it -- not finishing -- is what marks it.
    panel = CellPanel()
    cell = _makeCell()
    panel.addCell(cell)
    panel._onCurrentCell(cell)
    assert panel.isAttempted(cell) is True


def test_a_finished_cell_is_attempted(qapp):
    panel = CellPanel()
    cell = _makeCell()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    assert panel.isAttempted(cell) is True


def test_a_cell_finished_without_ever_being_current_is_attempted(qapp):
    # Orchestrator._processCell can emit "skipped" without sigCurrentCell ever
    # firing for that cell.
    panel = CellPanel()
    cell = _makeCell()
    panel._onCellFinished(cell, "skipped")
    assert panel.isAttempted(cell) is True


def test_a_none_current_cell_does_not_crash_or_mark_anything(qapp):
    panel = CellPanel()
    panel._onCurrentCell(None)
    assert panel.isAttempted(None) is False


def test_clear_cells_forgets_the_attempted_set(qapp):
    # Left behind, a stale id would report a brand-new cell at a reused memory
    # address as already attempted -- the same hazard _awaitingEnqueue is
    # cleared for.
    panel = CellPanel()
    cell = _makeCell()
    panel.addCell(cell)
    panel._onCellFinished(cell, "done")
    panel.clearCells()
    assert panel.isAttempted(cell) is False
```

Use the file's existing helper for building a `Cell` (`_makeCell` or equivalent) and its existing `qapp` fixture rather than introducing new ones.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v -k attempted
```

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'isAttempted'`.

- [ ] **Step 3: Implement**

In `CellPanel.__init__`, alongside the other per-cell stores:

```python
        # Cells the orchestrator has started work on, by id. Recorded from both
        # sigCurrentCell and sigCellFinished: a cell interrupted mid-run may
        # never emit a terminal status, and "retry" is emitted mid-flight
        # without being terminal, so "has work started" is the reliable question
        # and does not depend on the terminal-status vocabulary.
        #
        # Holds ids, never cells: this panel must not be the thing keeping a
        # Cell alive beyond self._cells, and must not add a second store to keep
        # in sync with it on teardown.
        self._attempted = set()
```

In `_onCurrentCell`, after the `if cell is None: return` guard:

```python
        self._attempted.add(id(cell))
```

At the top of `_onCellFinished`:

```python
        self._attempted.add(id(cell))
```

Add the accessor next to the other public panel methods:

```python
    def isAttempted(self, cell) -> bool:
        """Whether the orchestrator has ever started work on `cell`.

        Slice.forceRescan takes this as its predicate: attempted cells stay
        registered in the density record through a rescan, never-attempted ones
        are dropped so they can be found again where they now are.
        """
        return id(cell) in self._attempted
```

In `clearCells`, alongside the other `.clear()` calls:

```python
        self._attempted.clear()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -q
```

Expected: all pass.

- [ ] **Step 5: Mutation-test the negative assertions**

`test_a_queued_cell_is_not_attempted` and `test_clear_cells_forgets_the_attempted_set` both assert `False`, which is also what a permanently-empty set returns.

1. Make `isAttempted` `return True`. Run `-k attempted`. **Expected: both negative tests FAIL.** Restore.
2. Remove `self._attempted.clear()` from `clearCells`. Run `-k clear_cells_forgets`. **Expected: FAIL.** Restore.
3. Re-run: all pass.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_panel.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: track which cells the orchestrator has attempted"
```

---

### Task 10: Wire the window's tissue-moved handler (acq4)

**Files:**
- Modify: `acq4/modules/Autopatch/context_factory.py`
- Modify: `acq4/modules/Autopatch/Autopatch.py`
- Test: `acq4/modules/Autopatch/tests/test_context_factory.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `ctx.tissue_moved_hook` (Task 5), `Slice.forceRescan` (Task 7), `Orchestrator.clearProducerExhausted` (Task 8), `CellPanel.isAttempted` (Task 9).
- Produces:
  - `make_context_factory(pipetteGetter, manager, log=None, onLogAction=None, tissueMoved=None)` — binds `partial(tissueMoved, cell)`, so the hook is called as `tissueMoved(cell, ctx, reason)`.
  - `AutopatchWindow._onTissueMoved(cell, ctx, reason) -> None`.

- [ ] **Step 1: Write the failing context-factory test**

Append to `acq4/modules/Autopatch/tests/test_context_factory.py`:

```python
def test_tissue_moved_hook_is_bound_per_cell():
    seen = []
    factory = make_context_factory(
        pipetteGetter=lambda: None,
        manager=None,
        tissueMoved=lambda cell, ctx, reason: seen.append((cell, reason)),
    )
    cell = object()
    ctx = factory(cell)
    ctx.tissue_moved_hook(ctx, "drifted")
    assert seen == [(cell, "drifted")]


def test_no_tissue_moved_hook_leaves_the_context_on_its_safe_default():
    factory = make_context_factory(pipetteGetter=lambda: None, manager=None)
    assert factory(object()).tissue_moved_hook is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_context_factory.py -v -k tissue_moved
```

Expected: FAIL, `TypeError: make_context_factory() got an unexpected keyword argument 'tissueMoved'`.

- [ ] **Step 3: Bind the hook in the factory**

In `acq4/modules/Autopatch/context_factory.py`, add the parameter and the binding:

```python
def make_context_factory(
    pipetteGetter: Callable[[], object],
    manager,
    log: Callable[[object, str], None] | None = None,
    onLogAction: Callable[[object, object], None] | None = None,
    tissueMoved: Callable[[object, object, str], None] | None = None,
) -> Callable[[object], ExecutionContext]:
```

inside `_factory`, before the `return`:

```python
        if tissueMoved is not None:
            # Only the cell is bound in. ExecutionContext.tissue_moved passes
            # itself at call time, so the context is never captured in a closure
            # it also owns -- that would be a self-reference the cyclic GC alone
            # could break.
            kwargs["tissue_moved_hook"] = partial(tissueMoved, cell)
```

- [ ] **Step 4: Run it to verify it passes**

Same command as Step 2. Expected: PASS.

- [ ] **Step 5: Write the failing window test**

Append to `acq4/modules/Autopatch/tests/test_window_integration.py`, using that file's existing window fixture:

```python
def test_tissue_moved_rescans_and_clears_the_queue_on_the_first_answer(win, monkeypatch):
    monkeypatch.setattr(
        "acq4.modules.Autopatch.Autopatch.prompt",
        lambda ctx, **kw: "Rescan the slice",
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert slice_.coveredTiles == []
    assert win.orchestrator.pendingCells() == []
    assert win.orchestrator._producerExhausted is False


def test_tissue_moved_leaves_everything_alone_on_the_second_answer(win, monkeypatch):
    monkeypatch.setattr(
        "acq4.modules.Autopatch.Autopatch.prompt",
        lambda ctx, **kw: "Skip this cell only",
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    coveredBefore = list(slice_.coveredTiles)
    pendingBefore = win.orchestrator.pendingCells()

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert slice_.coveredTiles == coveredBefore
    assert win.orchestrator.pendingCells() == pendingBefore


def test_tissue_moved_ends_the_cell_on_both_answers(win, monkeypatch):
    for answer in ("Rescan the slice", "Skip this cell only"):
        monkeypatch.setattr(
            "acq4.modules.Autopatch.Autopatch.prompt", lambda ctx, **kw: answer
        )
        _slice, cell, ctx = _sliceWithCoveredTiles(win)
        with pytest.raises(AdvanceToNextCell):
            win._onTissueMoved(cell, ctx, "no features")


def test_tissue_moved_keeps_attempted_cells_in_the_density_record(win, monkeypatch):
    monkeypatch.setattr(
        "acq4.modules.Autopatch.Autopatch.prompt",
        lambda ctx, **kw: "Rescan the slice",
    )
    slice_, cell, ctx = _sliceWithCoveredTiles(win)
    tile = slice_.tileGrid()[0]
    win.cellPanel._onCellFinished(cell, "done")
    slice_.registerCells([cell])

    with pytest.raises(AdvanceToNextCell):
        win._onTissueMoved(cell, ctx, "no features")

    assert cell in slice_.cellsNearTile(tile)
```

Write `_sliceWithCoveredTiles(win)` as a module-level helper in that file: install a `Slice` on `win` with one region at a realistic, non-square stage coordinate, mark every tile covered, seed one cell positioned inside the first tile, enqueue a second cell on the orchestrator, and return `(slice, cell, ExecutionContext(cell=cell))`. Reuse the file's existing slice/orchestrator setup helpers where they exist.

- [ ] **Step 6: Run it to verify it fails**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k tissue_moved
```

Expected: FAIL with `AttributeError: 'AutopatchWindow' object has no attribute '_onTissueMoved'`.

- [ ] **Step 7: Implement the handler**

In `acq4/modules/Autopatch/Autopatch.py`, add the import:

```python
from acq4.experiment.actions.prompt import prompt
```

Add the handler next to the other slice methods:

```python
    def _onTissueMoved(self, cell, ctx, reason: str) -> None:
        """ExecutionContext.tissue_moved, cell-bound by the context factory.

        Runs on the orchestrator's worker thread, mid-cell. Never returns: both
        answers end the cell.

        The operator decides, because a rescan is destructive in its own way --
        it re-images ground already searched and can re-detect cells already
        worked. "Rescan the slice" is offered first and is therefore what a
        headless run picks: driving a pipette to a coordinate known to be stale
        is a hardware risk, while patching a cell twice is a data-hygiene cost,
        so the cheaper mistake goes first.
        """
        pending = len(self.orchestrator.pendingCells()) if self.orchestrator else 0
        answer = prompt(
            ctx,
            message=(
                f"Cell tracking could not re-find this cell ({reason}).\n"
                "The tissue may have moved. Rescanning discards the "
                f"{pending} cell(s) still queued and re-images this region; "
                "cells already patched may be found again."
            ),
            title="Tissue may have moved",
            choices=("Rescan the slice", "Skip this cell only"),
        )
        if answer == "Rescan the slice":
            if self.slice is not None:
                self.slice.forceRescan(cell.position, self.cellPanel.isAttempted)
            if self.orchestrator is not None:
                # After the answer, not before: a cell the operator seeds by hand
                # while the prompt is open is a coordinate in the same moved
                # tissue and goes with the rest.
                self.orchestrator.clearQueue()
                self.orchestrator.clearProducerExhausted()
        # Area 2's survey readout is deliberately not refreshed here: this is the
        # worker thread, and _refreshSurveyStats touches widgets. The next status
        # change routes through _onRunStatus on the GUI thread and picks it up.
        ctx.next_cell()
```

Wire the factory in `_onProtocolLoaded` (or wherever `make_context_factory` is currently called) by adding:

```python
            tissueMoved=self._onTissueMoved,
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests -q
```

Expected: all pass.

- [ ] **Step 9: Confirm teardown still frees the graph**

The new hook adds a window-to-context edge. `test_teardown.py` exists to catch exactly this.

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_teardown.py -q
```

Expected: all pass. If a weakref test now fails, the hook is being stored somewhere it closes over the context — revisit Step 3.

- [ ] **Step 10: Commit**

```bash
git add acq4/modules/Autopatch/context_factory.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_context_factory.py acq4/modules/Autopatch/tests/test_window_integration.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: prompt and rescan when the tracker loses a cell"
```

---

## Piece B - New slice creates a Data Manager directory

### Task 11: Extract `create_data_dir()` (acq4)

**Files:**
- Modify: `acq4/experiment/actions/storage.py`
- Test: `acq4/experiment/tests/test_actions_prompt_storage.py`

**Interfaces:**
- Produces: `create_data_dir(manager, level="Cell", set_current=True)` returning the created `DirHandle`. `new_data_dir(ctx, ...)` becomes its `ctx.log_action()` wrapper. Task 12 calls `create_data_dir`.

- [ ] **Step 1: Write the failing test**

Append to `acq4/experiment/tests/test_actions_prompt_storage.py`, reusing that file's existing fake manager:

```python
def test_create_data_dir_needs_no_context(tmp_path):
    # A UI button has no run and no ExecutionContext, and must not fabricate one
    # to reach engine logic.
    from acq4.experiment.actions.storage import create_data_dir

    man = _FakeManager(tmp_path)
    created = create_data_dir(man, level="Slice")

    assert created.info()["dirType"] == "Slice"
    assert man.getCurrentDir() is created


def test_create_data_dir_can_leave_the_current_dir_alone(tmp_path):
    from acq4.experiment.actions.storage import create_data_dir

    man = _FakeManager(tmp_path)
    before = man.getCurrentDir()
    created = create_data_dir(man, level="Slice", set_current=False)

    assert created is not before
    assert man.getCurrentDir() is before


def test_new_data_dir_still_behaves_identically_through_the_wrapper(tmp_path):
    # The action keeps its log_action wrapper and its behaviour; only the body
    # moved.
    from acq4.experiment.actions.storage import new_data_dir

    entries = []
    ctx = ExecutionContext(
        manager=_FakeManager(tmp_path), on_log_action=entries.append
    )
    created = new_data_dir(ctx, level="Slice")

    assert created.info()["dirType"] == "Slice"
    assert [e.name for e in entries] == ["New Data Directory"]
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_prompt_storage.py -v -k create_data_dir
```

Expected: FAIL, `ImportError: cannot import name 'create_data_dir'`.

- [ ] **Step 3: Extract the body**

Rewrite `acq4/experiment/actions/storage.py` so the whole existing body of `new_data_dir` — unchanged apart from `ctx.manager` becoming the `manager` parameter — lives in `create_data_dir`, and the action wraps it:

```python
"""Storage protocol function: create managed data directories for an experiment
run, and the manager-only helper a UI button can call without a run."""
from __future__ import annotations

import time


def create_data_dir(manager, level: str = "Cell", set_current: bool = True):
    """Create a new managed data directory of a given type ("level") under the
    current storage directory and (by default) make it current. Returns the
    created directory.

    Mirrors the non-GUI logic of DataManagerModule.createNewFolder: for a typed
    level the parent is chosen by walking up the tree so a directory is not
    nested inside another of the same type. The special level "Folder" makes an
    untyped "NewFolder" under the current directory.

    Takes a manager rather than an ExecutionContext so that both a protocol
    action and an operator's button can call it. Autopatch's New slice is a
    click with no run in progress, and a UI button must not have to fabricate a
    context to reach engine logic.
    """
    cdir = manager.getCurrentDir()
    if not cdir.isManaged():
        cdir.createIndex()
    if level == "Folder":
        new_dir = cdir.mkdir("NewFolder", autoIncrement=True)
        new_dir.setInfo({})
    else:
        spec = manager.folderTypesConfig()[level]
        name = time.strftime(spec["name"])
        # Walk up to avoid nesting a directory inside one of the same type.
        parent = cdir
        check_dir = cdir
        for _ in range(5):
            if not check_dir.isManaged():
                break
            if check_dir.info().get("dirType") == level:
                parent = check_dir.parent()
                break
            check_dir = check_dir.parent()
        new_dir = parent.mkdir(name, autoIncrement=True)
        info = {"dirType": level}
        if spec.get("experimentalUnit", False):
            info["expUnit"] = True
        new_dir.setInfo(info)
    if set_current:
        manager.setCurrentDir(new_dir)
    return new_dir


def new_data_dir(ctx, level: str = "Cell", set_current: bool = True):
    """Create a new managed data directory for this run and report it to the UI.

    The protocol-facing wrapper around create_data_dir: same behaviour, plus the
    log_action entry that puts it in Area 5's timeline.
    """
    with ctx.log_action("New Data Directory"):
        return create_data_dir(ctx.manager, level=level, set_current=set_current)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_prompt_storage.py -q
```

Expected: all pass, including the pre-existing `new_data_dir` tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/actions/storage.py acq4/experiment/tests/test_actions_prompt_storage.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "refactor: extract create_data_dir so a UI button needs no context"
```

---

### Task 12: `newSlice()` creates the slice directory (acq4)

**Files:**
- Modify: `acq4/experiment/slice.py` (`__init__`)
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`newSlice`)
- Test: `acq4/experiment/tests/test_slice.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: `create_data_dir` (Task 11).
- Produces: `Slice(fov, constraints=None, overlap=0.0, dirHandle=None)` with a `dirHandle` attribute.

- [ ] **Step 1: Write the failing Slice test**

Append to `acq4/experiment/tests/test_slice.py`:

```python
def test_slice_holds_its_data_directory():
    handle = object()
    assert Slice(fov=(20e-6, 10e-6), dirHandle=handle).dirHandle is handle


def test_slice_without_a_data_directory_is_valid():
    # A slice created implicitly by "Add region here" was never formally started
    # and honestly has no directory.
    assert Slice(fov=(20e-6, 10e-6)).dirHandle is None
```

- [ ] **Step 2: Run to verify it fails, then implement**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_slice.py -v -k data_directory
```

Expected: FAIL, `TypeError: __init__() got an unexpected keyword argument 'dirHandle'`.

In `Slice.__init__`, add the parameter and attribute:

```python
    def __init__(self, fov, constraints=None, overlap=0.0, dirHandle=None):
```

```python
        # The Data Manager directory this slice's data is written under, or None
        # for a slice that came into existence to hold a region rather than by
        # way of New slice. The handle is also what a later change would call
        # setInfo()/info() on to persist regions and coverage.
        self.dirHandle = dirHandle
```

Re-run: PASS.

- [ ] **Step 3: Write the failing window tests**

Append to `acq4/modules/Autopatch/tests/test_window_integration.py`:

```python
def test_new_slice_creates_a_slice_directory_and_makes_it_current(win):
    win.newSlice()
    assert win.slice.dirHandle is not None
    assert win.slice.dirHandle.info()["dirType"] == "Slice"
    assert win.manager.getCurrentDir() is win.slice.dirHandle


def test_new_slice_discards_nothing_when_the_directory_cannot_be_made(win):
    # Create the directory first, discard only on success: a failure that has
    # already thrown away the operator's cells is worse than the failure.
    from acq4.util.debug import HelpfulException

    oldSlice = win.slice
    cell = _makeCell()
    win.cellPanel.addCell(cell)
    win.orchestrator.enqueue(cell)

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()

    assert win.slice is oldSlice
    assert win.cellPanel.isAttempted(cell) is False
    assert win.orchestrator.pendingCells() == [cell]


def test_new_slice_reports_a_missing_storage_directory_in_area_2(win):
    from acq4.util.debug import HelpfulException

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()

    assert "Storage directory" in win.searchPanel.errorLabel.text()


def test_add_region_here_does_not_create_a_directory(win):
    # A button labelled "add region" must not silently repoint where every
    # subsequent write lands.
    win.addRegionHere()
    assert win.slice.dirHandle is None
```

- [ ] **Step 4: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v -k "new_slice or add_region_here"
```

Expected: the directory tests FAIL (`dirHandle` is `None`).

- [ ] **Step 5: Implement**

In `Autopatch.py`, add the import:

```python
from acq4.experiment.actions.storage import create_data_dir
```

Rewrite `newSlice`, keeping the existing docstring and adding the directory paragraph:

```python
    def newSlice(self) -> None:
        """Start a fresh slice, discarding the current one and everything on it.

        [keep the existing docstring body verbatim, then add:]

        The slice directory is created before anything is discarded. Creating it
        is the step that can fail -- an operator who has not chosen a storage
        directory is the likeliest first use of this button -- and a failure that
        has already thrown away their cells is worse than the failure itself.
        """
        try:
            dirHandle = create_data_dir(self.manager, level="Slice")
        except Exception as exc:
            # Area 3's instruction band does not exist yet, so this goes where
            # the operator already reads "Select a camera before starting a
            # slice".
            self.searchPanel.setError(str(exc))
            return
        if not self._startSlice(dirHandle=dirHandle):
            return
        self.cellPanel.clearCells()
        if self.orchestrator is not None:
            # [keep the existing comments and both calls verbatim]
            self.orchestrator.setCellProducer(None)
            self.orchestrator.clearQueue()
        self._refreshSurveyStats()
```

Give `_startSlice` the pass-through parameter, leaving its docstring's existing reasoning intact and adding a line for the new argument:

```python
    def _startSlice(self, dirHandle=None) -> bool:
```

```python
        self.slice = Slice(
            fov=self._cameraFov(camera), constraints=constraints, dirHandle=dirHandle
        )
```

`addRegionHere()`'s existing call stays `self._startSlice()`, which is what leaves its implicit slice with no directory.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests -q
```

Expected: all pass. The window fixture's fake manager may need `folderTypesConfig()` to include a `Slice` entry — add it there rather than special-casing production code.

- [ ] **Step 7: Mutation-test the "discards nothing" assertion**

It asserts state is *unchanged*, which is also true if the fixture never had that state.

1. Move the `create_data_dir` call to *after* `self.cellPanel.clearCells()`.
2. Run `-k discards_nothing`. **Expected: FAIL** — the cell is gone.
3. Restore. Re-run: PASS.

- [ ] **Step 8: Commit**

```bash
git add acq4/experiment/slice.py acq4/modules/Autopatch/Autopatch.py acq4/experiment/tests/test_slice.py acq4/modules/Autopatch/tests/test_window_integration.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: create a Slice data directory when the operator starts a slice"
```

---

### Task 13: Gate Area 2 on a slice existing (acq4)

**Files:**
- Modify: `acq4/modules/Autopatch/search_panel.py`
- Modify: `acq4/modules/Autopatch/Autopatch.py`
- Test: `acq4/modules/Autopatch/tests/test_search_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Produces: `SearchPanel.setSliceReady(ready: bool) -> None`. `setInteractionLocked` keeps its existing signature and its existing signal wiring.

**The hazard:** `setInteractionLocked` currently has exactly one writer, `statusPanel.sigInteractionLocked`. Adding "no slice yet" as a second reason to be locked would let a run finishing unlock a panel with no slice behind it. The two reasons are therefore stored separately and the effective lock derived from both.

- [ ] **Step 1: Write the failing test — all four corners**

Append to `acq4/modules/Autopatch/tests/test_search_panel.py`:

```python
def _controls(panel):
    return (
        panel.nearDepthSpin,
        panel.farDepthSpin,
        panel.minHealthSpin,
        panel.maxDensitySpin,
        panel.rescansCheck,
        panel.addRegionBtn,
        panel.shapeCombo,
    )


def test_locked_when_no_slice_and_not_running(qapp):
    panel = SearchPanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(False)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_locked_when_no_slice_and_running(qapp):
    panel = SearchPanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(True)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_locked_when_slice_ready_but_running(qapp):
    panel = SearchPanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(True)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_unlocked_only_when_slice_ready_and_not_running(qapp):
    panel = SearchPanel()
    panel.setSliceReady(True)
    panel.setInteractionLocked(False)
    assert all(w.isEnabled() for w in _controls(panel))


def test_a_run_ending_does_not_unlock_a_panel_with_no_slice(qapp):
    # The two-writers bug this design exists to prevent: sigInteractionLocked
    # firing False at the end of a run must not override slice-readiness.
    panel = SearchPanel()
    panel.setSliceReady(False)
    panel.setInteractionLocked(True)
    panel.setInteractionLocked(False)
    assert all(not w.isEnabled() for w in _controls(panel))


def test_a_panel_starts_locked_before_any_slice_exists(qapp):
    assert all(not w.isEnabled() for w in _controls(SearchPanel()))
```

- [ ] **Step 2: Run to verify they fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_search_panel.py -v -k "locked or slice_ready or unlocked"
```

Expected: FAIL with `AttributeError: 'SearchPanel' object has no attribute 'setSliceReady'`.

- [ ] **Step 3: Implement the derived lock**

In `SearchPanel.__init__`, alongside the two error strings:

```python
        # The two independent reasons this panel can be locked, kept apart for
        # the same reason the two error strings are: neither writer can see the
        # other's condition, so collapsing them into one boolean would let a run
        # ending unlock a panel that still has no slice behind it. A panel with
        # no slice starts locked -- New slice is what makes Area 2 usable, and
        # the greyed-out controls are how the operator is told so.
        self._runLocked = False
        self._sliceReady = False
```

Rename the existing body and derive:

```python
    def setInteractionLocked(self, locked: bool) -> None:
        """Disable editing while a run is in flight; the readout stays visible.

        The constraints parameterise a producer that is already surveying, so
        editing them mid-run would silently change the search under it.
        """
        self._runLocked = locked
        self._applyLock()

    def setSliceReady(self, ready: bool) -> None:
        """Whether a slice exists for these controls to configure.

        Area 2 parameterises a search over a slice, so with no slice there is
        nothing for these values to mean; New slice is the button that makes
        them live.
        """
        self._sliceReady = ready
        self._applyLock()

    def _applyLock(self) -> None:
        locked = self._runLocked or not self._sliceReady
        for w in (
            self.nearDepthSpin,
            self.farDepthSpin,
            self.minHealthSpin,
            self.maxDensitySpin,
            self.rescansCheck,
            self.addRegionBtn,
            self.shapeCombo,
        ):
            w.setEnabled(not locked)
```

Call `self._applyLock()` at the end of `__init__` so a fresh panel starts locked.

- [ ] **Step 4: Run to verify they pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_search_panel.py -q
```

Expected: all pass. Existing `setInteractionLocked` tests may now need a `setSliceReady(True)` first — that is the new behaviour, so update them.

- [ ] **Step 5: Wire it in the window**

In `Autopatch.py`, after `self.slice = Slice(...)` in `_startSlice`:

```python
        self.searchPanel.setSliceReady(True)
```

Append the window test to `test_window_integration.py`:

```python
def test_area_2_is_locked_until_a_slice_exists(win):
    assert not win.searchPanel.addRegionBtn.isEnabled()
    win.newSlice()
    assert win.searchPanel.addRegionBtn.isEnabled()
```

**Note:** `addRegionHere()` starts with `if self.slice is None and not self._startSlice()`. With Area 2 locked, that path is unreachable from the UI, but leave the guard — it is cheap, and it keeps the method correct if called directly.

- [ ] **Step 6: Run the whole suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -q
```

Expected: all pass, and **more than 510** tests.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/search_panel.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_search_panel.py acq4/modules/Autopatch/tests/test_window_integration.py && git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "feat: lock Area 2 until the operator starts a slice"
```

---

### Task 14: Correct the design doc

**Files:**
- Modify: `/home/martin/src/acq4/acq4/autopatch-orchestration-design.md` (untracked in the main checkout, not in this worktree)

The spec's section A.5 lists four corrections §3.6 needs. Making them keeps the design doc from teaching the next reader something the code no longer does.

- [ ] **Step 1: Apply the four corrections**

In §3.6:

1. Replace the slice-wide `Slice.forceRescan()` description with the region-scoped form, including the local-motion caveat.
2. Delete the claim that the producer's `_rescanned` allowance is re-armed; state that the existing producer is reused and `_rescanned` is untouched, which is what makes "not charged against `rescans_allowed`" literal.
3. Rewrite step 3: the lost cell is an attempted cell and holds its own tile, so a rescan does **not** re-find it. Note that cell death is the expected common trigger.
4. Add the mid-patch invariant: tracking failures during a patch (pipette occlusion) never reach this path and must never trigger a rescan.

In §7 Area 1, record that New slice creates the directory before discarding anything, and that §7's "prompt when completed cells are present" open decision is resolved as **no prompt**.

- [ ] **Step 2: Commit**

The design doc is untracked in git. Do not `git add` it. Confirm with the operator whether they want it committed.

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| A.0 mid-patch invariant | 14 (documented; holds by construction — no code change) |
| A.1.1 `CellTrackingLost` | 1 |
| A.1.2 re-verify raises with reason | 3 |
| A.1.3 `validate_movement` | 2 |
| A.2 `TrackingLost` | 4 |
| A.2 `cellfie` translation | 6 |
| A.2 `ExecutionContext.tissue_moved` | 5 |
| A.2 `Slice.forceRescan` | 7 |
| A.2 `clearProducerExhausted` | 8 |
| A.3 no fresh producer / no re-arm | 7, 8 (by omission; asserted in Task 8) |
| A.4 window hook, prompt, ordering, threading | 10 |
| A.5 design-doc corrections | 14 |
| B.1 `create_data_dir` | 11 |
| B.2 `newSlice` ordering, `dirHandle` | 12 |
| B.3 Area 2 gate | 13 |
| B.4 no prompt, orchestrator not stopped | 12 (no code; `newSlice` keeps its existing behaviour) |
| B.5 `searchPanel.setError` | 12 |
| `CellPanel` attempted set | 9 |

No gaps.

**Type consistency:** `forceRescan(position, isAttempted) -> int` is defined in Task 7 and called in Task 10 with `(cell.position, self.cellPanel.isAttempted)`; `isAttempted(cell) -> bool` is defined in Task 9. `tissue_moved_hook` is called as `hook(ctx, reason)` in Task 5 and bound as `partial(tissueMoved, cell)` in Task 10, giving the window handler `(cell, ctx, reason)` — which is the signature Task 10 implements. `create_data_dir(manager, level, set_current)` is defined in Task 11 and called in Task 12 as `create_data_dir(self.manager, level="Slice")`.

**Ordering:** Tasks 1-3 are the only cross-repo work and must land before Task 6, which imports `CellTrackingLost`. Task 6 also needs Task 5. Task 10 needs 5, 7, 8, and 9. Task 12 needs 11. Task 13 is independent of Piece A entirely and could be done first if the acq4-automation branch question blocks.
