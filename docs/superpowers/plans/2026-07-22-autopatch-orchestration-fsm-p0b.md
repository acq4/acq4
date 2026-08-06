# Autopatch Orchestration — P0b: FSM-wrapping + device Actions

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the concrete device-facing Actions to the `acq4/experiment/` engine: composite Actions that drive acq4's `PatchPipette` FSM to a declared terminal state (mapping abnormal states to exceptions), plus `GoTo`/`Cellfie`/`Task` device wrappers. Builds on the P0 core (Action/Protocol/Orchestrator).

**Architecture:** `FsmCompositeAction` drives the FSM via `pip.setState(entry)` then **polls `pip.getState().stateName`** until it reaches one of the action's declared `outcomes` (FSM terminal state names); an abnormal state (`ABNORMAL_STATE_EXCEPTIONS`) that is not a declared outcome raises the mapped `OrchestrationError`. Concrete `PatchAction`/`ResealAction` set `entry_state` + `outcomes`. Device actions wrap `Pipette.moveTo`, `Cell.initializeTracker`, and `Manager.runTask`. All testable headless against small fakes.

**Tech Stack:** Python ≥3.10, `acq4.util.Qt`, `acq4.util.task` (gentletask bridge), pytest.

## Global Constraints
- Test runner: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- Concurrency: import `check_stop`/`sleep`/`Stopped` from `acq4.util.task`; never `time.sleep`/`threading`.
- `from acq4.util import Qt`. 2-line docstring per new file. NEVER `--no-verify`.
- Commit format: `git commit --author="Claude (claude) <noreply@anthropic.com>" -m "<type>: <desc>\n\n🤖 Generated with [Claude Code](https://claude.ai/code)"`
- Branch `autopatch-experiment-engine` (do not switch). No temporal comments.
- **Scope guard:** do NOT modify any file under `acq4/devices/` — P0b wraps existing device APIs, it does not change them. RawState single-state actions are OUT of scope (they need a core statemanager change).

## Deferred (NOT in P0b) — flagged for a later chat
- **RawState actions**: require a public "run one FSM state without auto-advance" method on `PatchPipetteStateManager` (the auto-advance is a `DirectConnection`, so external `job.wait()` races the transition). Core-device change — deferred.
- **Global cross-action abnormal watcher**: P0b detects abnormal states inside the FSM composite's own poll loop (sufficient, since abnormal states only arise while the FSM is being driven). A truly global watcher firing during non-FSM actions is deferred.
- **Real TaskRunner protocol-file → command-dict loading**: `TaskAction` takes a command dict (JSON) directly; loading a saved protocol file headlessly is deferred.
- **Orchestrator wiring of `ctx.pipette`**: the default context factory does not set `pipette`; a deployment/P1 supplies a factory that binds the active pipette. P0b actions are tested by constructing an `ExecutionContext(pipette=<fake>)` directly.

---

### Task B1: FSM composite Action + Patch/Reseal + fake pipette

**Files:**
- Create: `acq4/experiment/fsm.py`
- Modify: `acq4/experiment/tests/conftest.py` (add fake pipette + fixture)
- Modify: `acq4/experiment/actions/__init__.py` (import fsm for registration) — NOTE: `fsm.py` lives at `acq4/experiment/fsm.py`, so add `from .. import fsm` is wrong; instead add the import in `acq4/experiment/__init__.py`. See Step 3.
- Test: `acq4/experiment/tests/test_fsm.py`

**Interfaces:**
- Produces: `FsmCompositeAction(Action)` — class attrs `entry_state: str`, `entry_config: dict = {}`, `poll_interval: float = 0.1`; `run(ctx)` drives+polls the FSM; `safeAbort(ctx)` best-effort `setState("bath")`. `outcomes` (from `Action`) doubles as the terminal FSM state-name set.
- `PatchAction` (registered "Patch"): `entry_state="cell detect"`, `outcomes=("whole cell","cell attached","bath","broken","fouled")`.
- `ResealAction` (registered "Reseal"): `entry_state="reseal"`, `outcomes=("outside out","whole cell")`.
- Test fake: `FakePatchPipette(state_sequence)` with `setState(state, **cfg)` (records to `.setState_calls`) and `getState()` (returns a `FakeStateJob` whose `.stateName` walks `state_sequence`); fixture `fake_pip_factory`.

- [ ] **Step 1: Write the failing test** — create `acq4/experiment/tests/test_fsm.py`:
```python
"""Tests for FSM-wrapping composite Actions (drive PatchPipette FSM to a terminal)."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.fsm import PatchAction, ResealAction, FsmCompositeAction
from acq4.experiment.exceptions import BrokenPipette
from acq4.experiment.registry import get_action_class


def _ctx(pip):
    return ExecutionContext(pipette=pip)


def test_patch_reaches_whole_cell(fake_pip_factory):
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    a = PatchAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "whole cell"
    assert pip.setState_calls[0][0] == "cell detect"


def test_patch_declares_broken_as_outcome(fake_pip_factory):
    # broken IS a declared Patch outcome -> routes as outcome, not exception
    pip = fake_pip_factory(["cell detect", "broken"])
    a = PatchAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "broken"


def test_reseal_reaches_outside_out(fake_pip_factory):
    pip = fake_pip_factory(["reseal", "outside out"])
    a = ResealAction()
    a.poll_interval = 0
    assert a.run(_ctx(pip)) == "outside out"


def test_reseal_broken_raises_exception(fake_pip_factory):
    # broken is NOT a Reseal outcome -> mapped to BrokenPipette
    pip = fake_pip_factory(["reseal", "broken"])
    a = ResealAction()
    a.poll_interval = 0
    with pytest.raises(BrokenPipette):
        a.run(_ctx(pip))


def test_registered():
    assert get_action_class("Patch") is PatchAction
    assert get_action_class("Reseal") is ResealAction


def test_missing_entry_state_raises(fake_pip_factory):
    class Bare(FsmCompositeAction):
        outcomes = ("x",)

    pip = fake_pip_factory([])
    with pytest.raises(ValueError):
        Bare().run(_ctx(pip))


def test_safeabort_retracts_to_bath(fake_pip_factory):
    pip = fake_pip_factory([])
    PatchAction().safeAbort(_ctx(pip))
    assert ("bath", {}) in pip.setState_calls
```

- [ ] **Step 2: Run to verify it fails**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_fsm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.fsm'` (and fixture `fake_pip_factory` missing).

- [ ] **Step 3: Implement**
Create `acq4/experiment/fsm.py`:
```python
"""FSM-wrapping Actions: drive acq4's PatchPipette state machine to a declared
terminal state, mapping unexpected abnormal states to orchestration exceptions."""
from __future__ import annotations

from acq4.util.task import check_stop, sleep

from .action import Action
from .registry import register_action
from .exceptions import ABNORMAL_STATE_EXCEPTIONS


class FsmCompositeAction(Action):
    """Drive the PatchPipette FSM from ``entry_state`` and finish when it reaches one
    of this action's declared ``outcomes`` (FSM terminal state names). The reached
    state name is the outcome the protocol graph routes on.

    If the FSM lands on an abnormal state (see ABNORMAL_STATE_EXCEPTIONS) that is not
    one of the declared outcomes, the mapped OrchestrationError is raised so the
    orchestrator's exception handling takes over. Subclasses set ``entry_state`` and
    ``outcomes`` (and optionally ``entry_config``/``poll_interval``).
    """

    entry_state: str = None
    entry_config: dict = {}
    poll_interval: float = 0.1  # seconds between FSM state polls

    def run(self, ctx) -> str:
        if self.entry_state is None:
            raise ValueError(f"{self.name}: entry_state is not set")
        pip = ctx.pipette
        self.setState(f"driving FSM from {self.entry_state!r}")
        pip.setState(self.entry_state, **self.entry_config)
        while True:
            check_stop()
            state = pip.getState().stateName
            if state in self.outcomes:
                self.setState(f"reached {state!r}")
                self.results["final_state"] = state
                return state
            exc_cls = ABNORMAL_STATE_EXCEPTIONS.get(state)
            if exc_cls is not None:
                raise exc_cls(f"{self.name}: pipette entered {state!r} state")
            sleep(self.poll_interval)

    def safeAbort(self, ctx) -> None:
        pip = getattr(ctx, "pipette", None)
        if pip is None:
            return
        # Best-effort retract to a safe holding state.
        try:
            pip.setState("bath")
        except Exception:
            pass


@register_action(name="Patch")
class PatchAction(FsmCompositeAction):
    """Drive cell detection through sealing/break-in to a resting terminal state."""

    entry_state = "cell detect"
    outcomes = ("whole cell", "cell attached", "bath", "broken", "fouled")


@register_action(name="Reseal")
class ResealAction(FsmCompositeAction):
    """Reseal from whole-cell toward an outside-out patch, else fall back to whole cell."""

    entry_state = "reseal"
    outcomes = ("outside out", "whole cell")
```

Add the fake + fixture to the END of `acq4/experiment/tests/conftest.py`:
```python
class FakeStateJob:
    """Stand-in for a PatchPipetteState job: exposes .stateName."""

    def __init__(self, name):
        self.stateName = name


class FakePatchPipette:
    """Minimal fake of PatchPipette for FSM-action tests.

    ``state_sequence`` is the list of state names ``getState()`` reports on successive
    polls (simulating the FSM self-driving). ``setState`` records its calls and sets the
    current state to the requested entry state.
    """

    def __init__(self, state_sequence=()):
        self._seq = list(state_sequence)
        self._current = "out"
        self.setState_calls = []

    def setState(self, state, **config):
        self.setState_calls.append((state, config))
        self._current = state
        return FakeStateJob(state)

    def getState(self):
        if self._seq:
            self._current = self._seq.pop(0)
        return FakeStateJob(self._current)


@pytest.fixture
def fake_pip_factory():
    def make(state_sequence):
        return FakePatchPipette(state_sequence)

    return make
```

Add to `acq4/experiment/__init__.py` (so importing the package registers the FSM actions):
```python
from . import fsm  # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_fsm.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Run the full suite**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**
```bash
git add acq4/experiment/fsm.py acq4/experiment/tests/conftest.py acq4/experiment/tests/test_fsm.py acq4/experiment/__init__.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add FSM composite actions (Patch/Reseal) driving the PatchPipette FSM

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task B2: device Actions — GoTo, Cellfie, Task

**Files:**
- Create: `acq4/experiment/actions/device.py`
- Modify: `acq4/experiment/actions/__init__.py` (import device)
- Test: `acq4/experiment/tests/test_device_actions.py`

**Interfaces:**
- Produces:
  - `GoToAction` (registered "GoTo"): `outcomes=("arrived",)`, `paramSpec` has `speed: str = "fast"`. `run()`: `pip.setTarget(cell.position.coordinates)`, then `pip.moveTo("target", speed).wait()`, returns `"arrived"`.
  - `CellfieAction` (registered "Cellfie"): `outcomes=("captured",)`. `run()`: `imager = pip.imagingDevice()`, `cell.initializeTracker(imager, use_cellpose=True)`, returns `"captured"`.
  - `TaskAction` (registered "Task"): `outcomes=("done",)`, `paramSpec` has `command: text = "{}"` (a JSON object string). `run()`: `manager.runTask(json.loads(command or "{}"))`, stores result in `self.results["result"]`, returns `"done"`.

- [ ] **Step 1: Write the failing test** — create `acq4/experiment/tests/test_device_actions.py`:
```python
"""Tests for device-wrapping Actions (GoTo, Cellfie, Task) using small fakes."""
import numpy as np

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.device import GoToAction, CellfieAction, TaskAction
from acq4.experiment.registry import get_action_class


class _FakeFuture:
    def wait(self, *a, **k):
        return None


class _FakePosition:
    def __init__(self, coords):
        self.coordinates = np.asarray(coords, dtype=float)


class _FakeCell:
    def __init__(self, coords=(1e-3, 2e-3, 3e-3)):
        self.position = _FakePosition(coords)
        self.tracker_calls = []

    def initializeTracker(self, imager, **kwargs):
        self.tracker_calls.append((imager, kwargs))


class _FakeCamera:
    pass


class _FakeMovePipette:
    def __init__(self):
        self.target = None
        self.moveTo_calls = []
        self._imager = _FakeCamera()

    def setTarget(self, target):
        self.target = target

    def moveTo(self, position, speed, **kwds):
        self.moveTo_calls.append((position, speed))
        return _FakeFuture()

    def imagingDevice(self):
        return self._imager


class _FakeManager:
    def __init__(self, result="RESULT"):
        self.result = result
        self.runTask_calls = []

    def runTask(self, cmd):
        self.runTask_calls.append(cmd)
        return self.result


def test_goto_moves_to_cell_target():
    pip = _FakeMovePipette()
    cell = _FakeCell((5e-3, 6e-3, 7e-3))
    ctx = ExecutionContext(cell=cell, pipette=pip)
    assert GoToAction().run(ctx) == "arrived"
    assert np.allclose(pip.target, [5e-3, 6e-3, 7e-3])
    assert pip.moveTo_calls == [("target", "fast")]


def test_cellfie_initializes_tracker():
    pip = _FakeMovePipette()
    cell = _FakeCell()
    ctx = ExecutionContext(cell=cell, pipette=pip)
    assert CellfieAction().run(ctx) == "captured"
    assert len(cell.tracker_calls) == 1
    imager, kwargs = cell.tracker_calls[0]
    assert imager is pip._imager
    assert kwargs.get("use_cellpose") is True


def test_task_runs_command_and_returns_done():
    mgr = _FakeManager(result={"trace": [1, 2, 3]})
    ctx = ExecutionContext(manager=mgr)
    a = TaskAction(params={"command": '{"protocol": "seal test"}'})
    assert a.run(ctx) == "done"
    assert mgr.runTask_calls == [{"protocol": "seal test"}]
    assert a.results["result"] == {"trace": [1, 2, 3]}


def test_registered():
    assert get_action_class("GoTo") is GoToAction
    assert get_action_class("Cellfie") is CellfieAction
    assert get_action_class("Task") is TaskAction
```

- [ ] **Step 2: Run to verify it fails**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_device_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.actions.device'`.

- [ ] **Step 3: Implement**
Create `acq4/experiment/actions/device.py`:
```python
"""Device-wrapping Actions: move the pipette to a cell (GoTo), capture the cell
tracker reference stack (Cellfie), and run a TaskRunner command (Task)."""
from __future__ import annotations

import json

from ..action import Action
from ..registry import register_action


@register_action(name="GoTo")
class GoToAction(Action):
    """Move the pipette to the current cell's position (planned move to target)."""

    outcomes = ("arrived",)
    paramSpec = ({"name": "speed", "type": "str", "default": "fast"},)

    def run(self, ctx):
        pip = ctx.pipette
        pip.setTarget(ctx.cell.position.coordinates)
        pip.moveTo("target", self.paramValue("speed")).wait()
        return "arrived"


@register_action(name="Cellfie")
class CellfieAction(Action):
    """Capture the cell tracker's reference stack (the "cellfie")."""

    outcomes = ("captured",)

    def run(self, ctx):
        imager = ctx.pipette.imagingDevice()
        ctx.cell.initializeTracker(imager, use_cellpose=True)
        return "captured"


@register_action(name="Task")
class TaskAction(Action):
    """Run a TaskRunner command (a JSON object in the `command` param) headless via
    Manager.runTask. Loading a saved protocol file into a command dict is a later
    concern; this action takes the command directly."""

    outcomes = ("done",)
    paramSpec = ({"name": "command", "type": "text", "default": "{}"},)

    def run(self, ctx):
        command = json.loads(self.paramValue("command") or "{}")
        self.results["result"] = ctx.manager.runTask(command)
        return "done"
```

Add to `acq4/experiment/actions/__init__.py`:
```python
from . import device  # noqa: F401
```

- [ ] **Step 4: Run to verify it passes**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_device_actions.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite**
Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**
```bash
git add acq4/experiment/actions/device.py acq4/experiment/actions/__init__.py acq4/experiment/tests/test_device_actions.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add device actions (GoTo, Cellfie, Task)

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Self-Review
- FSM composite (poll-to-terminal + abnormal→exception) → B1, matches design §4.2/§4.3 (abnormal detection folded into the poll loop). ✓
- Patch declares broken/fouled as outcomes (route normally); Reseal does not (broken→exception) → B1 tests cover both. ✓
- Device actions GoTo/Cellfie/Task wrap real APIs (`setTarget`/`moveTo`, `initializeTracker`, `runTask`) → B2, tested via fakes. ✓
- RawState / global watcher / protocol-file loading / orchestrator pipette-binding → explicitly deferred + flagged. ✓
- No `acq4/devices/` files touched. ✓
- Type consistency: `FsmCompositeAction.entry_state`/`outcomes`/`poll_interval`/`entry_config`; action type names Patch/Reseal/GoTo/Cellfie/Task; `ExecutionContext(cell,pipette,manager,log)` used consistently. ✓
