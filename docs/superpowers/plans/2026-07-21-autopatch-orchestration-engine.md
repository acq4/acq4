# Autopatch Orchestration — Core Engine (P0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the device-free core of the experiment-orchestration engine — a composable `Action` model, an outcome-routed protocol graph with JSON persistence, and an `Orchestrator` that runs a protocol over a queue of cells with pause/stop/next-cell and exception-handler routing.

**Architecture:** A new `acq4/experiment/` package. `Action` is a thin `QObject` unit of work that runs synchronously in a worker and returns one of its declared outcomes. A `Protocol` is a directed graph (nodes = Actions, edges keyed by `(node_id, outcome)`, merges allowed) plus exception-handler sub-protocols. The `Orchestrator` walks the graph per cell, routing on outcomes, converting flow actions and exceptional states into control decisions. This phase has **no device integration** — the FSM-wrapping layer and concrete patch Actions come in the P0b plan.

**Tech Stack:** Python ≥3.10, PyQt (via `acq4.util.Qt`), pyqtgraph `Parameter` trees, the `gentletask` concurrency library (via the `acq4.util.task` bridge), pytest + pytest-qt.

## Global Constraints

- **Python interpreter / test runner:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest` (the `acq4-gl` env; `acq4-torch` lacks `gentletask`).
- **Concurrency:** import `check_stop`, `Stopped`, `Event`, `asynch_with_qt_signals` from `acq4.util.task` (never from `gentletask` directly, never `time.sleep`/`threading`). `task.wait(timeout=…)` **raises** `Timeout` on deadline; a returned value means finished; `Stopped` means a stop cascaded in.
- **Qt import:** `from acq4.util import Qt` (never import PyQt directly).
- **File docstrings:** every new file starts with a brief 2-line docstring explaining what it does.
- **Style:** `black`. Match surrounding acq4 conventions.
- **Commits:** conventional-commit format; include `(claude)` in an explicit `--author` for Claude-authored commits. Never `--no-verify`.
- **No temporal comments** ("new", "improved", "recently changed"); comments describe code as-is.

---

## File Structure

```
acq4/experiment/
  __init__.py            # public exports
  context.py             # ExecutionContext dataclass
  action.py              # Action base class
  registry.py            # type-name <-> Action-class registry
  exceptions.py          # exception taxonomy + control-flow signals + abnormal-state map
  protocol.py            # Protocol graph + JSON (de)serialization
  orchestrator.py        # Orchestrator run loop / graph interpreter
  actions/
    __init__.py          # imports concrete actions so they self-register
    flow.py              # GoToNext, RetryCell, Abort flow actions
    prompt.py            # Prompt (operator-instruction) action
    script.py            # Script action (reload-on-run .py)
  tests/
    conftest.py          # fake actions + fixtures
    test_action.py
    test_registry.py
    test_protocol.py
    test_serialization.py
    test_exceptions.py
    test_orchestrator_walk.py
    test_orchestrator_loop.py
    test_orchestrator_exceptions.py
    test_flow_actions.py
    test_script_action.py
```

---

### Task 1: Package scaffold + ExecutionContext

**Files:**
- Create: `acq4/experiment/__init__.py`
- Create: `acq4/experiment/context.py`
- Create: `acq4/experiment/tests/__init__.py`
- Test: `acq4/experiment/tests/test_context.py`

**Interfaces:**
- Produces: `ExecutionContext(cell=None, pipette=None, manager=None, log=<callable>)` — a dataclass passed to every `Action.run()`/`safeAbort()`. `log` is a `Callable[[str], None]` defaulting to a no-op.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_context.py`:
```python
"""Tests for the ExecutionContext passed to Actions."""
from acq4.experiment.context import ExecutionContext


def test_context_defaults():
    ctx = ExecutionContext()
    assert ctx.cell is None
    assert ctx.pipette is None
    assert ctx.manager is None
    # log is callable and a no-op by default
    assert ctx.log("hello") is None


def test_context_fields():
    seen = []
    ctx = ExecutionContext(cell="c", pipette="p", manager="m", log=seen.append)
    assert (ctx.cell, ctx.pipette, ctx.manager) == ("c", "p", "m")
    ctx.log("line")
    assert seen == ["line"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment'`.

- [ ] **Step 3: Create the package files**

Create `acq4/experiment/__init__.py`:
```python
"""acq4 experiment-orchestration engine: composable Actions, protocol graphs,
and an orchestrator that runs a protocol over a queue of cells."""
from .context import ExecutionContext  # noqa: F401
```

Create `acq4/experiment/tests/__init__.py`:
```python
"""Tests for the acq4.experiment package."""
```

Create `acq4/experiment/context.py`:
```python
"""ExecutionContext: the per-run bundle (cell, pipette, manager, log) handed to
every Action's run() and safeAbort()."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


def _noop_log(_message: str) -> None:
    return None


@dataclass
class ExecutionContext:
    cell: Any = None
    pipette: Any = None
    manager: Any = None
    log: Callable[[str], None] = field(default=_noop_log)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_context.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/__init__.py acq4/experiment/context.py acq4/experiment/tests/__init__.py acq4/experiment/tests/test_context.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: scaffold acq4.experiment package with ExecutionContext"
```

---

### Task 2: Action base class

**Files:**
- Create: `acq4/experiment/action.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_action.py`

**Interfaces:**
- Produces: `Action` — `QObject` subclass.
  - Class attrs: `outcomes: tuple[str, ...] = ()`, `paramSpec: tuple[dict, ...] = ()`.
  - Signal: `sigStateChanged = Qt.Signal(object, str)  # self, message`.
  - `__init__(self, name: str | None = None, params: dict | None = None)`.
  - `self.name: str`, `self.params: Parameter` (a `type='group'`), `self.results: dict`.
  - `paramValue(self, name) -> Any`.
  - `setState(self, message: str) -> None` (emits `sigStateChanged`).
  - `run(self, ctx: ExecutionContext) -> str` (raises `NotImplementedError`).
  - `safeAbort(self, ctx: ExecutionContext) -> None` (default no-op).
  - `show(self)` -> widget or `None` (default `None`).

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_action.py`:
```python
"""Tests for the Action base class."""
import pytest

from acq4.experiment.action import Action
from acq4.experiment.context import ExecutionContext


class _Demo(Action):
    outcomes = ("done",)
    paramSpec = (
        {"name": "pressure", "type": "float", "default": 5000.0, "suffix": "Pa"},
    )

    def run(self, ctx):
        self.setState("running demo")
        self.results["p"] = self.paramValue("pressure")
        return "done"


def test_default_name_is_class_name():
    assert _Demo().name == "_Demo"


def test_explicit_name():
    assert _Demo(name="node1").name == "node1"


def test_param_default_and_override():
    assert _Demo().paramValue("pressure") == 5000.0
    assert _Demo(params={"pressure": 1234.0}).paramValue("pressure") == 1234.0


def test_unknown_param_raises():
    with pytest.raises(KeyError):
        _Demo(params={"nope": 1})


def test_run_returns_outcome_and_sets_results():
    a = _Demo()
    assert a.run(ExecutionContext()) == "done"
    assert a.results["p"] == 5000.0


def test_setstate_emits_signal(qtbot):
    a = _Demo()
    with qtbot.waitSignal(a.sigStateChanged, timeout=1000) as blocker:
        a.setState("hi")
    assert blocker.args == [a, "hi"]


def test_base_run_not_implemented():
    with pytest.raises(NotImplementedError):
        Action().run(ExecutionContext())


def test_safeabort_and_show_defaults():
    a = _Demo()
    assert a.safeAbort(ExecutionContext()) is None
    assert a.show() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_action.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.action'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/action.py`:
```python
"""Action: the composable unit of orchestration work. Subclasses declare their
possible outcomes and params, and implement run() to do the work synchronously."""
from __future__ import annotations

from typing import Any

from acq4.util import Qt
from pyqtgraph.parametertree import Parameter

from .context import ExecutionContext


class Action(Qt.QObject):
    """A unit of work bound at run time to a cell + pipette via ExecutionContext.

    Subclasses set `outcomes` (the names run() may return) and optionally
    `paramSpec` (a pyqtgraph Parameter config list). run() executes synchronously
    inside an orchestrator worker thread and must return one of `outcomes`.
    """

    outcomes: tuple[str, ...] = ()
    paramSpec: tuple[dict, ...] = ()

    sigStateChanged = Qt.Signal(object, str)  # self, message

    def __init__(self, name: str | None = None, params: dict | None = None):
        Qt.QObject.__init__(self)
        self.name = name or type(self).__name__
        self.params = self._buildParams(params or {})
        self.results: dict[str, Any] = {}

    @classmethod
    def _buildParams(cls, values: dict) -> Parameter:
        children = [dict(spec) for spec in cls.paramSpec]
        group = Parameter.create(name="params", type="group", children=children)
        valid = {spec["name"] for spec in cls.paramSpec}
        for key, val in values.items():
            if key not in valid:
                raise KeyError(f"{cls.__name__} has no param {key!r}")
            group.child(key).setValue(val)
        return group

    def paramValue(self, name: str) -> Any:
        return self.params.child(name).value()

    def setState(self, message: str) -> None:
        self.sigStateChanged.emit(self, message)

    def run(self, ctx: ExecutionContext) -> str:
        raise NotImplementedError

    def safeAbort(self, ctx: ExecutionContext) -> None:
        """Unwind devices to a safe state when the action is stopped. Default no-op."""

    def show(self):
        """Return a live QWidget for this action, or None. Default None."""
        return None
```

Modify `acq4/experiment/__init__.py` to add after the existing import:
```python
from .action import Action  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_action.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/action.py acq4/experiment/__init__.py acq4/experiment/tests/test_action.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Action base class with params, outcomes, and lifecycle"
```

---

### Task 3: Action registry

**Files:**
- Create: `acq4/experiment/registry.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_registry.py`

**Interfaces:**
- Produces:
  - `register_action(cls=None, *, name=None)` — class decorator; registers an `Action` subclass under `name` (default class name) and sets `cls._typeName`.
  - `get_action_class(name: str) -> type[Action]` — raises `KeyError` if unknown.
  - `action_type_name(action: Action) -> str` — the registered name (falls back to class name).

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_registry.py`:
```python
"""Tests for the Action type registry."""
import pytest

from acq4.experiment.action import Action
from acq4.experiment.registry import (
    register_action,
    get_action_class,
    action_type_name,
)


def test_register_and_lookup_by_class_name():
    @register_action
    class Alpha(Action):
        outcomes = ("ok",)

    assert get_action_class("Alpha") is Alpha
    assert action_type_name(Alpha()) == "Alpha"


def test_register_with_explicit_name():
    @register_action(name="custom-beta")
    class Beta(Action):
        outcomes = ("ok",)

    assert get_action_class("custom-beta") is Beta
    assert action_type_name(Beta()) == "custom-beta"


def test_unknown_type_raises():
    with pytest.raises(KeyError):
        get_action_class("does-not-exist")


def test_duplicate_name_different_class_raises():
    @register_action(name="dupe")
    class Gamma(Action):
        outcomes = ("ok",)

    with pytest.raises(ValueError):
        @register_action(name="dupe")
        class Delta(Action):
            outcomes = ("ok",)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.registry'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/registry.py`:
```python
"""Registry mapping serialized type names to Action classes, so protocols can be
(de)serialized by type name."""
from __future__ import annotations

from .action import Action

_REGISTRY: dict[str, type] = {}


def register_action(cls: type | None = None, *, name: str | None = None):
    """Class decorator registering an Action subclass under `name`
    (default: the class name)."""

    def _reg(c):
        key = name or c.__name__
        existing = _REGISTRY.get(key)
        if existing is not None and existing is not c:
            raise ValueError(f"Action type {key!r} already registered")
        _REGISTRY[key] = c
        c._typeName = key
        return c

    return _reg(cls) if cls is not None else _reg


def get_action_class(name: str) -> type:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown action type {name!r}")
    return _REGISTRY[name]


def action_type_name(action: Action) -> str:
    return getattr(type(action), "_typeName", type(action).__name__)
```

Modify `acq4/experiment/__init__.py` to add:
```python
from .registry import register_action, get_action_class, action_type_name  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_registry.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/registry.py acq4/experiment/__init__.py acq4/experiment/tests/test_registry.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Action type registry for protocol serialization"
```

---

### Task 4: Shared test fakes (conftest)

**Files:**
- Create: `acq4/experiment/tests/conftest.py`
- Test: `acq4/experiment/tests/test_fakes.py`

**Interfaces:**
- Produces (fixtures/classes used by later test files):
  - `RecordingAction(Action)` — `outcomes = ("done",)`; `paramSpec` has `next: str = "done"`; `run()` appends its `name` to the shared class list `RecordingAction.ran` and returns the value of the `next` param.
  - `RaisingAction(Action)` — `outcomes = ()`; `paramSpec` has `exc: str = "Exception"`; `run()` raises the `OrchestrationError` subclass whose `typeName` matches `exc`.
  - `StopAction(Action)` — `outcomes = ("done",)`; `run()` raises `Stopped("stopped")`; `safeAbort()` appends its name to `StopAction.aborted`.
  - registered under type names `"Recording"`, `"Raising"`, `"Stop"`.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_fakes.py`:
```python
"""Sanity tests for the shared fake actions in conftest."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import BrokenPipette


def test_recording_action_records_and_returns(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")
    assert a.run(ExecutionContext()) == "done"
    assert recording_cls.ran == ["a"]


def test_recording_action_custom_next(recording_cls):
    a = recording_cls(name="b", params={"next": "left"})
    assert a.run(ExecutionContext()) == "left"


def test_raising_action_raises_mapped_exception(raising_cls):
    a = raising_cls(params={"exc": "BrokenPipette"})
    with pytest.raises(BrokenPipette):
        a.run(ExecutionContext())


def test_stop_action_raises_stopped(stop_cls):
    with pytest.raises(Stopped):
        stop_cls().run(ExecutionContext())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_fakes.py -v`
Expected: FAIL — fixtures `recording_cls`/`raising_cls`/`stop_cls` not found (and `acq4.experiment.exceptions` missing).

> Note: this task depends on Task 5's `exceptions.py`. If executing strictly in order, implement Task 5 first, then return here. The plan lists conftest first because later orchestrator tasks import these fakes; the reviewer may approve them together.

- [ ] **Step 3: Write the conftest**

Create `acq4/experiment/tests/conftest.py`:
```python
"""Shared fake Actions and fixtures for acq4.experiment tests."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.action import Action
from acq4.experiment.registry import register_action
from acq4.experiment import exceptions as exc


@register_action(name="Recording")
class RecordingAction(Action):
    """Records that it ran (by name) and returns the value of its `next` param."""

    outcomes = ("done", "left", "right")
    paramSpec = ({"name": "next", "type": "str", "default": "done"},)
    ran: list = []

    def run(self, ctx):
        RecordingAction.ran.append(self.name)
        return self.paramValue("next")


@register_action(name="Raising")
class RaisingAction(Action):
    """Raises the OrchestrationError subclass whose typeName matches `exc`."""

    outcomes = ()
    paramSpec = ({"name": "exc", "type": "str", "default": "Exception"},)

    def run(self, ctx):
        name = self.paramValue("exc")
        for cls in _orchestration_error_subclasses():
            if cls.typeName == name:
                raise cls(f"raised {name}")
        raise exc.OrchestrationError(f"raised {name}")


@register_action(name="Stop")
class StopAction(Action):
    """Simulates a cooperative stop mid-action and records the safeAbort call."""

    outcomes = ("done",)
    aborted: list = []

    def run(self, ctx):
        raise Stopped("stopped")

    def safeAbort(self, ctx):
        StopAction.aborted.append(self.name)


def _orchestration_error_subclasses():
    seen = [exc.OrchestrationError]
    stack = [exc.OrchestrationError]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in seen:
                seen.append(sub)
                stack.append(sub)
    return seen


@pytest.fixture
def recording_cls():
    return RecordingAction


@pytest.fixture
def raising_cls():
    return RaisingAction


@pytest.fixture
def stop_cls():
    return StopAction
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_fakes.py -v`
Expected: PASS (4 passed). (Requires Task 5's `exceptions.py`.)

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/tests/conftest.py acq4/experiment/tests/test_fakes.py
git commit --author="Claude <noreply@anthropic.com>" -m "test: add shared fake Actions and fixtures for experiment tests"
```

---

### Task 5: Exception taxonomy + control-flow signals

**Files:**
- Create: `acq4/experiment/exceptions.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_exceptions.py`

**Interfaces:**
- Produces:
  - `OrchestrationError(Exception)` with class attr `typeName = "Exception"`.
  - Subclasses: `BrokenPipette` (`"BrokenPipette"`), `Fouled` (`"Fouled"`), `Uncleanable` (`"Uncleanable"`), `NoSolution` (`"NoSolution"`), `ScriptError` (`"ScriptError"`).
  - `FlowSignal(Exception)` base; `AdvanceToNextCell`, `RetryCurrentCell`, `AbortExperiment` subclasses.
  - `ABNORMAL_STATE_EXCEPTIONS: dict[str, type[OrchestrationError]]` = `{"broken": BrokenPipette, "fouled": Fouled}` (consumed by the P0b FSM watcher).

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_exceptions.py`:
```python
"""Tests for the orchestration exception taxonomy and control-flow signals."""
from acq4.experiment import exceptions as exc


def test_base_typename():
    assert exc.OrchestrationError.typeName == "Exception"


def test_subclass_typenames():
    assert exc.BrokenPipette.typeName == "BrokenPipette"
    assert exc.Fouled.typeName == "Fouled"
    assert exc.Uncleanable.typeName == "Uncleanable"
    assert exc.NoSolution.typeName == "NoSolution"
    assert exc.ScriptError.typeName == "ScriptError"


def test_subclasses_are_orchestration_errors():
    for cls in (exc.BrokenPipette, exc.Fouled, exc.Uncleanable,
                exc.NoSolution, exc.ScriptError):
        assert issubclass(cls, exc.OrchestrationError)


def test_flow_signals_are_not_orchestration_errors():
    for cls in (exc.AdvanceToNextCell, exc.RetryCurrentCell, exc.AbortExperiment):
        assert issubclass(cls, exc.FlowSignal)
        assert not issubclass(cls, exc.OrchestrationError)


def test_abnormal_state_map():
    assert exc.ABNORMAL_STATE_EXCEPTIONS["broken"] is exc.BrokenPipette
    assert exc.ABNORMAL_STATE_EXCEPTIONS["fouled"] is exc.Fouled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.exceptions'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/exceptions.py`:
```python
"""Exception taxonomy for exceptional states routed to handlers, plus control-flow
signals raised by flow actions and consumed by the orchestrator loop."""
from __future__ import annotations


class OrchestrationError(Exception):
    """Base for exceptional states routed to exception handlers.

    `typeName` is the key used to look up a handler; unmatched types fall back to
    the catch-all 'Exception' handler.
    """

    typeName = "Exception"


class BrokenPipette(OrchestrationError):
    typeName = "BrokenPipette"


class Fouled(OrchestrationError):
    typeName = "Fouled"


class Uncleanable(OrchestrationError):
    typeName = "Uncleanable"


class NoSolution(OrchestrationError):
    typeName = "NoSolution"


class ScriptError(OrchestrationError):
    typeName = "ScriptError"


class FlowSignal(Exception):
    """Base for control-flow signals raised by flow actions."""


class AdvanceToNextCell(FlowSignal):
    """Abandon the current cell and move to the next queued cell."""


class RetryCurrentCell(FlowSignal):
    """Restart the protocol from the top for the current cell."""


class AbortExperiment(FlowSignal):
    """Stop the whole experiment."""


# Maps an abnormal FSM state name to an exception class. Consumed by the FSM
# watcher in the P0b plan; defined here so the taxonomy lives in one place.
ABNORMAL_STATE_EXCEPTIONS: dict[str, type[OrchestrationError]] = {
    "broken": BrokenPipette,
    "fouled": Fouled,
}
```

Modify `acq4/experiment/__init__.py` to add:
```python
from . import exceptions  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_exceptions.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/exceptions.py acq4/experiment/__init__.py acq4/experiment/tests/test_exceptions.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add orchestration exception taxonomy and control-flow signals"
```

---

### Task 6: Protocol graph model

**Files:**
- Create: `acq4/experiment/protocol.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_protocol.py`

**Interfaces:**
- Produces: `Protocol`
  - `__init__(self, nodes=None, edges=None, entry=None, publicParams=None, exceptionHandlers=None)`.
    - `nodes: dict[str, Action]`, `edges: dict[tuple[str, str], str]`, `entry: str | None`, `publicParams: list[dict]`, `exceptionHandlers: dict[str, Protocol]`.
  - `next_node(self, node_id: str, outcome: str) -> str | None`.
  - `handler_for(self, exc_type_name: str) -> Protocol | None` (falls back to the `"Exception"` handler).
  - (serialization methods added in Task 7.)

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_protocol.py`:
```python
"""Tests for the Protocol graph model (routing and handler lookup)."""
from acq4.experiment.protocol import Protocol


def test_next_node_follows_edge(recording_cls):
    a, b = recording_cls(name="a"), recording_cls(name="b")
    p = Protocol(nodes={"a": a, "b": b},
                 edges={("a", "done"): "b"},
                 entry="a")
    assert p.next_node("a", "done") == "b"


def test_next_node_missing_edge_returns_none(recording_cls):
    p = Protocol(nodes={"a": recording_cls(name="a")}, edges={}, entry="a")
    assert p.next_node("a", "done") is None


def test_edges_can_merge(recording_cls):
    # two outcomes route to the same downstream node
    p = Protocol(
        nodes={"a": recording_cls(name="a"), "c": recording_cls(name="c")},
        edges={("a", "left"): "c", ("a", "right"): "c"},
        entry="a",
    )
    assert p.next_node("a", "left") == "c"
    assert p.next_node("a", "right") == "c"


def test_handler_for_exact_and_fallback():
    catch_all = Protocol(entry="h")
    specific = Protocol(entry="hb")
    p = Protocol(exceptionHandlers={"Exception": catch_all,
                                    "BrokenPipette": specific})
    assert p.handler_for("BrokenPipette") is specific
    assert p.handler_for("Fouled") is catch_all  # falls back to catch-all


def test_handler_for_none_when_no_handlers():
    assert Protocol().handler_for("Exception") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.protocol'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/protocol.py`:
```python
"""Protocol: an outcome-routed directed graph of Actions, with exception-handler
sub-protocols. Serialization is added alongside JSON I/O."""
from __future__ import annotations

from .action import Action


class Protocol:
    """A directed graph of Actions.

    nodes:  {node_id: Action}
    edges:  {(node_id, outcome): target_node_id}   -- merges (many->one) allowed
    entry:  node_id of the first action, or None
    publicParams: [{"node": id, "param": name, "public": public_name}, ...]
    exceptionHandlers: {typeName: Protocol}         -- each handler is a sub-Protocol
    """

    version = 1

    def __init__(self, nodes=None, edges=None, entry=None,
                 publicParams=None, exceptionHandlers=None):
        self.nodes: dict[str, Action] = dict(nodes or {})
        self.edges: dict[tuple[str, str], str] = dict(edges or {})
        self.entry: str | None = entry
        self.publicParams: list[dict] = list(publicParams or [])
        self.exceptionHandlers: dict[str, "Protocol"] = dict(exceptionHandlers or {})

    def next_node(self, node_id: str, outcome: str) -> str | None:
        """The node reached by `outcome` from `node_id`, or None if the branch ends."""
        return self.edges.get((node_id, outcome))

    def handler_for(self, exc_type_name: str) -> "Protocol | None":
        """Handler protocol for an exception type, falling back to the catch-all."""
        return self.exceptionHandlers.get(exc_type_name) or self.exceptionHandlers.get(
            "Exception"
        )
```

Modify `acq4/experiment/__init__.py` to add:
```python
from .protocol import Protocol  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_protocol.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/protocol.py acq4/experiment/__init__.py acq4/experiment/tests/test_protocol.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Protocol graph model with outcome routing and handler lookup"
```

---

### Task 7: Protocol JSON serialization

**Files:**
- Modify: `acq4/experiment/protocol.py`
- Test: `acq4/experiment/tests/test_serialization.py`

**Interfaces:**
- Produces (added to `Protocol`):
  - `to_dict(self) -> dict` — `{"version", "entry", "nodes": {id: {"type", "params"}}, "edges": [{"from","outcome","to"}], "publicParams": [...], "exceptionHandlers": {typeName: <dict>}}`.
  - `from_dict(cls, data) -> Protocol` — rebuilds Actions via `get_action_class`.
  - `save_json(self, path)` / `load_json(cls, path)`.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_serialization.py`:
```python
"""Tests for Protocol JSON (de)serialization round-trips."""
from acq4.experiment.protocol import Protocol


def _sample_protocol(recording_cls):
    a = recording_cls(name="a", params={"next": "left"})
    b = recording_cls(name="b")
    handler = Protocol(
        nodes={"h": recording_cls(name="h")}, edges={}, entry="h"
    )
    return Protocol(
        nodes={"a": a, "b": b},
        edges={("a", "left"): "b"},
        entry="a",
        publicParams=[{"node": "a", "param": "next", "public": "First branch"}],
        exceptionHandlers={"Exception": handler},
    )


def test_to_dict_shape(recording_cls):
    d = _sample_protocol(recording_cls).to_dict()
    assert d["version"] == 1
    assert d["entry"] == "a"
    assert d["nodes"]["a"] == {"type": "Recording", "params": {"next": "left"}}
    assert {"from": "a", "outcome": "left", "to": "b"} in d["edges"]
    assert d["publicParams"][0]["public"] == "First branch"
    assert d["exceptionHandlers"]["Exception"]["entry"] == "h"


def test_round_trip_in_memory(recording_cls):
    p = _sample_protocol(recording_cls)
    p2 = Protocol.from_dict(p.to_dict())
    assert p2.entry == "a"
    assert p2.next_node("a", "left") == "b"
    assert p2.nodes["a"].paramValue("next") == "left"
    assert p2.publicParams == p.publicParams
    assert p2.handler_for("Exception").entry == "h"


def test_round_trip_json_file(tmp_path, recording_cls):
    p = _sample_protocol(recording_cls)
    path = tmp_path / "proto.json"
    p.save_json(str(path))
    loaded = Protocol.load_json(str(path))
    assert loaded.next_node("a", "left") == "b"
    assert loaded.nodes["b"].name == "b"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_serialization.py -v`
Expected: FAIL — `AttributeError: 'Protocol' object has no attribute 'to_dict'`.

- [ ] **Step 3: Write minimal implementation**

In `acq4/experiment/protocol.py`, add imports at the top (after the `Action` import):
```python
import json

from .registry import get_action_class, action_type_name
```

Add these methods to the `Protocol` class (after `handler_for`):
```python
    # ---- serialization ----
    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "entry": self.entry,
            "nodes": {
                nid: {"type": action_type_name(a), "params": _param_values(a)}
                for nid, a in self.nodes.items()
            },
            "edges": [
                {"from": f, "outcome": o, "to": t}
                for (f, o), t in self.edges.items()
            ],
            "publicParams": self.publicParams,
            "exceptionHandlers": {
                k: p.to_dict() for k, p in self.exceptionHandlers.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Protocol":
        nodes = {}
        for nid, ndata in data.get("nodes", {}).items():
            action_cls = get_action_class(ndata["type"])
            nodes[nid] = action_cls(name=nid, params=ndata.get("params", {}))
        edges = {(e["from"], e["outcome"]): e["to"] for e in data.get("edges", [])}
        handlers = {
            k: cls.from_dict(v) for k, v in data.get("exceptionHandlers", {}).items()
        }
        return cls(
            nodes=nodes,
            edges=edges,
            entry=data.get("entry"),
            publicParams=data.get("publicParams", []),
            exceptionHandlers=handlers,
        )

    def save_json(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @classmethod
    def load_json(cls, path: str) -> "Protocol":
        with open(path) as fh:
            return cls.from_dict(json.load(fh))
```

Add this module-level helper at the bottom of `protocol.py`:
```python
def _param_values(action: Action) -> dict:
    return {
        spec["name"]: action.paramValue(spec["name"])
        for spec in type(action).paramSpec
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_serialization.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/protocol.py acq4/experiment/tests/test_serialization.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Protocol JSON serialization round-trip"
```

---

### Task 8: Orchestrator graph walk + outcome routing

**Files:**
- Create: `acq4/experiment/orchestrator.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_orchestrator_walk.py`

**Interfaces:**
- Produces: `Orchestrator(Qt.QObject)`
  - `__init__(self, protocol: Protocol, manager=None, contextFactory=None)`. `contextFactory(cell) -> ExecutionContext`; default builds `ExecutionContext(cell=cell, manager=manager)`.
  - Signals: `sigStatus = Qt.Signal(str)`, `sigCurrentAction = Qt.Signal(object, object)  # cell, action`, `sigCellFinished = Qt.Signal(object, str)  # cell, status`.
  - `enqueue(self, cell)`.
  - `run_sync(self)` — runs the queue loop inline (deterministic; for tests + headless).
  - Internal (relied on by later tasks): `_walk(self, cell, protocol, node_id)`, `_runAction(self, action, ctx) -> str`, `_processCell(self, cell)`, `_handleException(self, exc, cell) -> str`, `_checkPause(self)`.

This task implements `_walk` + `_runAction` + a minimal `_processCell` (no exception handling yet — that is Task 10) so a straight-line protocol runs.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_orchestrator_walk.py`:
```python
"""Tests for the Orchestrator graph walk and outcome routing (single cell)."""
import pytest

from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator


def test_walk_straight_line(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")       # returns "done"
    b = recording_cls(name="b")       # returns "done"
    p = Protocol(nodes={"a": a, "b": b},
                 edges={("a", "done"): "b"}, entry="a")
    Orchestrator(p).run_sync_cell("cell1")
    assert recording_cls.ran == ["a", "b"]


def test_walk_branches_on_outcome(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a", params={"next": "left"})   # returns "left"
    left = recording_cls(name="left")
    right = recording_cls(name="right")
    p = Protocol(nodes={"a": a, "left": left, "right": right},
                 edges={("a", "left"): "left", ("a", "right"): "right"},
                 entry="a")
    Orchestrator(p).run_sync_cell("cell1")
    assert recording_cls.ran == ["a", "left"]


def test_unknown_outcome_raises(recording_cls):
    a = recording_cls(name="a", params={"next": "bogus-not-in-outcomes"})
    # 'bogus-not-in-outcomes' is not in RecordingAction.outcomes
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    with pytest.raises(ValueError):
        Orchestrator(p).run_sync_cell("cell1")


def test_current_action_signal_emitted(qtbot, recording_cls):
    a = recording_cls(name="a")
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    orch = Orchestrator(p)
    with qtbot.waitSignal(orch.sigCurrentAction, timeout=1000) as blocker:
        orch.run_sync_cell("cell1")
    assert blocker.args[0] == "cell1"
    assert blocker.args[1] is a
```

> `run_sync_cell(cell)` is a thin test/headless entry that runs one cell through the protocol; it wraps `_processCell`.

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_walk.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.orchestrator'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/orchestrator.py`:
```python
"""Orchestrator: runs a Protocol over a queue of cells, serially, routing on each
action's outcome and converting flow signals / exceptional states into control."""
from __future__ import annotations

from collections import deque

from acq4.util import Qt
from acq4.util.task import Stopped, Event, check_stop

from .context import ExecutionContext
from .exceptions import (
    OrchestrationError,
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
)


class Orchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)                 # "running"/"waiting"/"paused"/"error"
    sigCurrentAction = Qt.Signal(object, object)   # cell, action (None,None when idle)
    sigCellFinished = Qt.Signal(object, str)   # cell, status

    def __init__(self, protocol, manager=None, contextFactory=None):
        Qt.QObject.__init__(self)
        self.protocol = protocol
        self.manager = manager
        self._queue = deque()
        self._pauseEvent = Event()
        self._pauseEvent.set()  # set == running
        self._nextCellRequested = False
        self._contextFactory = contextFactory or self._defaultContext

    # ---- queue / context ----
    def enqueue(self, cell):
        self._queue.append(cell)

    def _defaultContext(self, cell) -> ExecutionContext:
        return ExecutionContext(cell=cell, manager=self.manager)

    # ---- test / headless entry points ----
    def run_sync_cell(self, cell):
        """Run a single cell through the protocol inline. Used by tests/headless."""
        self._nextCellRequested = False
        self._processCell(cell)

    # ---- graph walk ----
    def _checkPause(self):
        if not self._pauseEvent.is_set():
            self.sigStatus.emit("paused")
            self._pauseEvent.wait()
            self.sigStatus.emit("running")

    def _runAction(self, action, ctx) -> str:
        try:
            result = action.run(ctx)
        except Stopped:
            action.safeAbort(ctx)
            raise
        if result not in action.outcomes:
            raise ValueError(
                f"{action.name} returned unknown outcome {result!r}; "
                f"expected one of {action.outcomes}"
            )
        return result

    def _walk(self, cell, protocol, node_id):
        """Walk `protocol` from `node_id`, routing on outcomes. Raises FlowSignal
        or OrchestrationError up to the caller."""
        while node_id is not None:
            self._checkPause()
            check_stop()
            if self._nextCellRequested:
                raise AdvanceToNextCell("next cell requested")
            action = protocol.nodes[node_id]
            ctx = self._contextFactory(cell)
            self.sigCurrentAction.emit(cell, action)
            outcome = self._runAction(action, ctx)
            node_id = protocol.next_node(node_id, outcome)

    def _processCell(self, cell):
        """Run the main protocol for one cell (no exception handling yet)."""
        self._walk(cell, self.protocol, self.protocol.entry)
        self.sigCellFinished.emit(cell, "done")
```

Modify `acq4/experiment/__init__.py` to add:
```python
from .orchestrator import Orchestrator  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_walk.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/__init__.py acq4/experiment/tests/test_orchestrator_walk.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Orchestrator graph walk with outcome routing"
```

---

### Task 9: Orchestrator queue loop + pause / stop / next-cell

**Files:**
- Modify: `acq4/experiment/orchestrator.py`
- Test: `acq4/experiment/tests/test_orchestrator_loop.py`

**Interfaces:**
- Produces (added to `Orchestrator`):
  - `run_sync(self)` — runs the whole queue inline (deterministic).
  - `start(self)` — launches the queue loop in a `QtFriendlyTask` (async); stores it as `self._task`; returns the task.
  - `pause(self)` / `resume(self)` — clear/set the pause event and emit status.
  - `stop(self, reason="stopped by operator")` — stops the async task if running.
  - `requestNextCell(self)` — sets the next-cell flag; `_walk` raises `AdvanceToNextCell` at the next boundary.
  - `wait(self, timeout=None)` — waits on the async task (raises if none running).
  - `_runLoopBody(self)` — the loop: pops cells, calls `_processCell`, emits status; `AdvanceToNextCell` from `_walk` marks the cell "skipped".

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_orchestrator_loop.py`:
```python
"""Tests for the Orchestrator queue loop, pause/resume, stop, and next-cell."""
import pytest

from acq4.util.task import Stopped, Event
from acq4.experiment.action import Action
from acq4.experiment.registry import register_action
from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator


def test_run_sync_processes_whole_queue(recording_cls):
    recording_cls.ran.clear()
    p = Protocol(nodes={"a": recording_cls(name="a")}, edges={}, entry="a")
    orch = Orchestrator(p)
    orch.enqueue("c1")
    orch.enqueue("c2")
    orch.run_sync()
    assert recording_cls.ran == ["a", "a"]  # ran once per cell


def test_requestnextcell_skips_current(recording_cls):
    recording_cls.ran.clear()
    a = recording_cls(name="a")
    p = Protocol(nodes={"a": a}, edges={}, entry="a")
    orch = Orchestrator(p)
    finished = []
    orch.sigCellFinished.connect(lambda cell, status: finished.append((cell, status)))
    orch.enqueue("c1")
    orch.requestNextCell()  # before running: first boundary check skips c1
    orch.run_sync()
    assert recording_cls.ran == []            # action never ran
    assert finished == [("c1", "skipped")]


def test_pause_resume_toggle_status():
    p = Protocol()
    orch = Orchestrator(p)
    statuses = []
    orch.sigStatus.connect(statuses.append)
    orch.pause()
    assert orch._pauseEvent.is_set() is False
    orch.resume()
    assert orch._pauseEvent.is_set() is True
    assert "paused" in statuses and "running" in statuses


@register_action(name="Blocking")
class _BlockingAction(Action):
    """Blocks on a shared Event until released, so the async loop can be stopped
    mid-action. `gate` is set by the test; `started` signals arrival."""

    outcomes = ("done",)
    gate: Event = None
    started: Event = None
    aborted: list = []

    def run(self, ctx):
        if _BlockingAction.started is not None:
            _BlockingAction.started.set()
        if _BlockingAction.gate is not None:
            _BlockingAction.gate.wait()  # stop-aware; raises Stopped on stop()
        return "done"

    def safeAbort(self, ctx):
        _BlockingAction.aborted.append(self.name)


def test_stop_aborts_running_action(qtbot):
    _BlockingAction.gate = Event()       # never set -> run() blocks
    _BlockingAction.started = Event()
    _BlockingAction.aborted = []
    p = Protocol(nodes={"a": _BlockingAction(name="a")}, edges={}, entry="a")
    orch = Orchestrator(p)
    orch.enqueue("c1")
    task = orch.start()
    _BlockingAction.started.wait()       # wait until the action is running
    orch.stop("test stop")
    with pytest.raises(Stopped):
        task.wait(timeout=5)
    assert _BlockingAction.aborted == ["a"]  # safeAbort ran on stop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_loop.py -v`
Expected: FAIL — `AttributeError: 'Orchestrator' object has no attribute 'run_sync'`.

- [ ] **Step 3: Write minimal implementation**

In `acq4/experiment/orchestrator.py`, add to the imports at the top:
```python
from acq4.util.task import asynch_with_qt_signals
```

Add these methods to `Orchestrator` (after `run_sync_cell`):
```python
    # ---- controls ----
    def start(self):
        """Launch the queue loop asynchronously; returns the launched task."""
        self._task = asynch_with_qt_signals(self._runLoopBody)()
        return self._task

    def run_sync(self):
        """Run the whole queue inline (deterministic; for tests / headless)."""
        self._runLoopBody()

    def pause(self):
        self._pauseEvent.clear()
        self.sigStatus.emit("paused")

    def resume(self):
        self._pauseEvent.set()
        self.sigStatus.emit("running")

    def stop(self, reason: str = "stopped by operator"):
        task = getattr(self, "_task", None)
        if task is not None and not task.is_done:
            task.stop(reason)

    def requestNextCell(self):
        self._nextCellRequested = True

    def wait(self, timeout=None):
        task = getattr(self, "_task", None)
        if task is None:
            raise RuntimeError("Orchestrator was not started; nothing to wait on")
        return task.wait(timeout=timeout)

    # ---- loop body ----
    def _runLoopBody(self):
        self.sigStatus.emit("running")
        try:
            while self._queue:
                self._checkPause()
                check_stop()
                cell = self._queue.popleft()
                self._nextCellRequested = False
                self._processCell(cell)
        finally:
            self.sigCurrentAction.emit(None, None)
            self.sigStatus.emit("waiting")
```

Replace the existing `_processCell` method with this version (adds `AdvanceToNextCell` handling; exception handling comes in Task 10):
```python
    def _processCell(self, cell):
        """Run the main protocol for one cell, honoring a next-cell request."""
        try:
            self._walk(cell, self.protocol, self.protocol.entry)
        except AdvanceToNextCell:
            self.sigCellFinished.emit(cell, "skipped")
            return
        self.sigCellFinished.emit(cell, "done")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_loop.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the whole suite so far**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/ -v`
Expected: PASS (all green). Fix any regression before committing.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_loop.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Orchestrator queue loop with pause/stop/next-cell"
```

---

### Task 10: Exception dispatch to handler sub-protocols

**Files:**
- Modify: `acq4/experiment/orchestrator.py`
- Test: `acq4/experiment/tests/test_orchestrator_exceptions.py`

**Interfaces:**
- Produces (added to `Orchestrator`):
  - `_handleException(self, exc, cell) -> str` — runs the matching handler sub-protocol; returns `"retry"` (handler ended in `RetryCurrentCell`) or `"advance"` (handler ended in `AdvanceToNextCell`, ran to completion, or had no handler-provided flow action); re-raises `AbortExperiment` when the handler aborts or when there is no handler.
  - `_processCell` updated: catches `OrchestrationError` → `_handleException`; on `"retry"` loops; catches top-level `RetryCurrentCell`/`AdvanceToNextCell` from the main protocol.
  - Behavior: an `OrchestrationError` with **no matching handler and no catch-all** raises `AbortExperiment` (the run loop stops). This realizes the "catch-all `Exception → full stop`" safety net when a protocol ships without handlers.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_orchestrator_exceptions.py`:
```python
"""Tests for exception dispatch to handler sub-protocols."""
import pytest

from acq4.experiment.protocol import Protocol
from acq4.experiment.orchestrator import Orchestrator
from acq4.experiment.exceptions import AbortExperiment


def test_no_handler_aborts(raising_cls):
    p = Protocol(nodes={"a": raising_cls(params={"exc": "BrokenPipette"})},
                 edges={}, entry="a")
    with pytest.raises(AbortExperiment):
        Orchestrator(p).run_sync_cell("c1")


def test_handler_advance(recording_cls, raising_cls):
    recording_cls.ran.clear()
    # main: a raises BrokenPipette. handler: h1 (Recording) -> GoToNext.
    from acq4.experiment.actions.flow import GoToNextAction
    handler = Protocol(
        nodes={"h1": recording_cls(name="h1"), "adv": GoToNextAction(name="adv")},
        edges={("h1", "done"): "adv"},
        entry="h1",
    )
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "BrokenPipette"})},
        edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    finished = []
    orch = Orchestrator(p)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert recording_cls.ran == ["h1"]        # handler ran
    assert finished == [("c1", "handled")]


def test_handler_retry_then_success(recording_cls):
    from acq4.experiment.action import Action
    from acq4.experiment.registry import register_action
    from acq4.experiment.exceptions import BrokenPipette
    from acq4.experiment.actions.flow import RetryCellAction

    @register_action(name="FailOnce")
    class FailOnce(Action):
        outcomes = ("done",)
        calls = {"n": 0}

        def run(self, ctx):
            FailOnce.calls["n"] += 1
            if FailOnce.calls["n"] == 1:
                raise BrokenPipette("first attempt fails")
            return "done"

    FailOnce.calls["n"] = 0
    handler = Protocol(nodes={"r": RetryCellAction(name="r")}, edges={}, entry="r")
    p = Protocol(
        nodes={"a": FailOnce(name="a")}, edges={}, entry="a",
        exceptionHandlers={"BrokenPipette": handler},
    )
    finished = []
    orch = Orchestrator(p)
    orch.sigCellFinished.connect(lambda c, s: finished.append((c, s)))
    orch.run_sync_cell("c1")
    assert FailOnce.calls["n"] == 2           # failed once, retried, succeeded
    assert finished == [("c1", "done")]


def test_catchall_handler_used_for_unmapped(raising_cls, recording_cls):
    from acq4.experiment.actions.flow import GoToNextAction
    recording_cls.ran.clear()
    handler = Protocol(
        nodes={"h": recording_cls(name="h"), "adv": GoToNextAction(name="adv")},
        edges={("h", "done"): "adv"}, entry="h",
    )
    # raises Fouled; only a catch-all "Exception" handler exists
    p = Protocol(
        nodes={"a": raising_cls(name="a", params={"exc": "Fouled"})},
        edges={}, entry="a",
        exceptionHandlers={"Exception": handler},
    )
    Orchestrator(p).run_sync_cell("c1")
    assert recording_cls.ran == ["h"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.actions'` (flow actions come in Task 11) **and** `_handleException` missing.

> This task and Task 11 are mutually dependent (exception tests use flow actions; flow tests use the orchestrator). Implement Task 11's `actions/flow.py` first, then this task, then run both test files. The reviewer may gate them together.

- [ ] **Step 3: Write minimal implementation**

In `acq4/experiment/orchestrator.py`, replace the `_processCell` method with this version:
```python
    def _processCell(self, cell):
        """Run the main protocol for one cell, dispatching exceptional states to
        handler sub-protocols. RetryCurrentCell loops; AdvanceToNextCell skips."""
        while True:
            try:
                self._walk(cell, self.protocol, self.protocol.entry)
            except AdvanceToNextCell:
                self.sigCellFinished.emit(cell, "skipped")
                return
            except RetryCurrentCell:
                self.sigCellFinished.emit(cell, "retry")
                continue
            except OrchestrationError as exc:
                self.sigStatus.emit("error")
                disposition = self._handleException(exc, cell)
                if disposition == "retry":
                    continue
                self.sigCellFinished.emit(cell, "handled")
                return
            else:
                self.sigCellFinished.emit(cell, "done")
                return

    def _handleException(self, exc, cell) -> str:
        """Run the matching handler sub-protocol. Returns 'retry' or 'advance';
        raises AbortExperiment when the handler aborts or none matches."""
        handler = self.protocol.handler_for(exc.typeName)
        if handler is None or handler.entry is None:
            raise AbortExperiment(f"unhandled {exc.typeName}: {exc}")
        try:
            self._walk(cell, handler, handler.entry)
        except AdvanceToNextCell:
            return "advance"
        except RetryCurrentCell:
            return "retry"
        return "advance"  # handler ran to completion without a flow action
```

- [ ] **Step 4: Run test to verify it passes** (after Task 11's flow actions exist)

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_orchestrator_exceptions.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/orchestrator.py acq4/experiment/tests/test_orchestrator_exceptions.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add exception-handler dispatch with retry/advance/abort"
```

---

### Task 11: Flow actions + Prompt action

**Files:**
- Create: `acq4/experiment/actions/__init__.py`
- Create: `acq4/experiment/actions/flow.py`
- Create: `acq4/experiment/actions/prompt.py`
- Modify: `acq4/experiment/__init__.py`
- Test: `acq4/experiment/tests/test_flow_actions.py`

**Interfaces:**
- Produces:
  - `GoToNextAction(Action)` — registered `"GoToNext"`; `run()` raises `AdvanceToNextCell`.
  - `RetryCellAction(Action)` — registered `"RetryCell"`; `run()` raises `RetryCurrentCell`.
  - `AbortAction(Action)` — registered `"Abort"`; `run()` raises `AbortExperiment`.
  - `PromptAction(Action)` — registered `"Prompt"`; `paramSpec` has `message: str`; `outcomes = ("acknowledged",)`; `run()` calls `ctx.log(message)`, emits `setState(message)`, and returns `"acknowledged"`. (Headless-safe: no blocking dialog in P0; a real operator-blocking widget arrives with the UI phase.)

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_flow_actions.py`:
```python
"""Tests for flow actions (GoToNext/RetryCell/Abort) and the Prompt action."""
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.flow import (
    GoToNextAction,
    RetryCellAction,
    AbortAction,
)
from acq4.experiment.actions.prompt import PromptAction
from acq4.experiment.exceptions import (
    AdvanceToNextCell,
    RetryCurrentCell,
    AbortExperiment,
)
from acq4.experiment.registry import get_action_class


def test_gotonext_raises_advance():
    with pytest.raises(AdvanceToNextCell):
        GoToNextAction().run(ExecutionContext())


def test_retrycell_raises_retry():
    with pytest.raises(RetryCurrentCell):
        RetryCellAction().run(ExecutionContext())


def test_abort_raises_abort():
    with pytest.raises(AbortExperiment):
        AbortAction().run(ExecutionContext())


def test_flow_actions_registered():
    assert get_action_class("GoToNext") is GoToNextAction
    assert get_action_class("RetryCell") is RetryCellAction
    assert get_action_class("Abort") is AbortAction


def test_prompt_logs_and_acknowledges():
    logged = []
    ctx = ExecutionContext(log=logged.append)
    a = PromptAction(params={"message": "Swap the pipette, then continue."})
    assert a.run(ctx) == "acknowledged"
    assert logged == ["Swap the pipette, then continue."]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_flow_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.actions'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/actions/__init__.py`:
```python
"""Concrete built-in Actions. Importing this package registers each action type."""
from . import flow  # noqa: F401
from . import prompt  # noqa: F401
```

Create `acq4/experiment/actions/flow.py`:
```python
"""Flow-control actions: they carry no work, only signal the orchestrator to
advance, retry, or abort by raising the matching control-flow signal."""
from __future__ import annotations

from ..action import Action
from ..registry import register_action
from ..exceptions import AdvanceToNextCell, RetryCurrentCell, AbortExperiment


@register_action(name="GoToNext")
class GoToNextAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise AdvanceToNextCell(f"{self.name}: advance to next cell")


@register_action(name="RetryCell")
class RetryCellAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise RetryCurrentCell(f"{self.name}: retry current cell")


@register_action(name="Abort")
class AbortAction(Action):
    outcomes = ()

    def run(self, ctx):
        raise AbortExperiment(f"{self.name}: abort experiment")
```

Create `acq4/experiment/actions/prompt.py`:
```python
"""Prompt action: surfaces operator instructions via the log/status. In this
device-free phase it does not block on a dialog; the UI phase adds an
operator-blocking widget."""
from __future__ import annotations

from ..action import Action
from ..registry import register_action


@register_action(name="Prompt")
class PromptAction(Action):
    outcomes = ("acknowledged",)
    paramSpec = ({"name": "message", "type": "str", "default": ""},)

    def run(self, ctx):
        message = self.paramValue("message")
        self.setState(message)
        ctx.log(message)
        return "acknowledged"
```

Modify `acq4/experiment/__init__.py` to add (so importing the package registers built-in actions):
```python
from . import actions  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_flow_actions.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/actions/ acq4/experiment/__init__.py acq4/experiment/tests/test_flow_actions.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add flow actions and Prompt action"
```

---

### Task 12: Script action (reload-on-run)

**Files:**
- Create: `acq4/experiment/actions/script.py`
- Modify: `acq4/experiment/actions/__init__.py`
- Test: `acq4/experiment/tests/test_script_action.py`

**Interfaces:**
- Produces: `ScriptAction(Action)` — registered `"Script"`.
  - `paramSpec`: `path: str` (filesystem path to a `.py` file).
  - `outcomes = ("done",)` in the base, but the loaded action's outcomes govern routing — `ScriptAction.run()` **delegates** to the loaded action and returns its outcome. (The editor reads the loaded action's declared outcomes; here we pass the outcome through.)
  - Loads the `.py` **fresh on every `run()`** via `importlib`, finds the single `Action` subclass defined in it, instantiates it, and calls its `run(ctx)`.
  - On import/exec error or if the file does not define exactly one `Action` subclass, raises `ScriptError`.

- [ ] **Step 1: Write the failing test**

Create `acq4/experiment/tests/test_script_action.py`:
```python
"""Tests for the Script action (reload-on-run .py files)."""
import textwrap
import pytest

from acq4.experiment.context import ExecutionContext
from acq4.experiment.actions.script import ScriptAction
from acq4.experiment.exceptions import ScriptError


def _write(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


def test_script_runs_loaded_action(tmp_path):
    path = _write(tmp_path, "good.py", """
        from acq4.experiment.action import Action

        class MyAction(Action):
            outcomes = ("ok",)
            def run(self, ctx):
                ctx.log("script ran")
                return "ok"
    """)
    logged = []
    a = ScriptAction(params={"path": path})
    assert a.run(ExecutionContext(log=logged.append)) == "ok"
    assert logged == ["script ran"]


def test_script_reloads_on_each_run(tmp_path):
    path = _write(tmp_path, "mut.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("v1",)
            def run(self, ctx): return "v1"
    """)
    a = ScriptAction(params={"path": path})
    assert a.run(ExecutionContext()) == "v1"
    # edit the file; a fresh run must pick up the change
    _write(tmp_path, "mut.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("v2",)
            def run(self, ctx): return "v2"
    """)
    assert a.run(ExecutionContext()) == "v2"


def test_import_error_becomes_scripterror(tmp_path):
    path = _write(tmp_path, "bad.py", "this is not valid python !!!")
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())


def test_no_action_subclass_raises(tmp_path):
    path = _write(tmp_path, "empty.py", "x = 1\n")
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())


def test_multiple_action_subclasses_raises(tmp_path):
    path = _write(tmp_path, "two.py", """
        from acq4.experiment.action import Action
        class A(Action):
            outcomes = ("ok",)
            def run(self, ctx): return "ok"
        class B(Action):
            outcomes = ("ok",)
            def run(self, ctx): return "ok"
    """)
    with pytest.raises(ScriptError):
        ScriptAction(params={"path": path}).run(ExecutionContext())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_script_action.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acq4.experiment.actions.script'`.

- [ ] **Step 3: Write minimal implementation**

Create `acq4/experiment/actions/script.py`:
```python
"""Script action: loads a .py file fresh on every run and delegates to the single
Action subclass it defines. Import/exec failures surface as ScriptError."""
from __future__ import annotations

import importlib.util
import uuid

from ..action import Action
from ..registry import register_action
from ..exceptions import ScriptError


@register_action(name="Script")
class ScriptAction(Action):
    outcomes = ("done",)
    paramSpec = ({"name": "path", "type": "str", "default": ""},)

    def run(self, ctx):
        action = self._loadAction()
        return action.run(ctx)

    def _loadAction(self) -> Action:
        path = self.paramValue("path")
        # Unique module name each load so edits are always picked up fresh.
        mod_name = f"_acq4_experiment_script_{uuid.uuid4().hex}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise ScriptError(f"Cannot load script at {path!r}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except ScriptError:
            raise
        except Exception as e:  # import/exec errors -> exception state
            raise ScriptError(f"Error loading script {path!r}: {e}") from e

        candidates = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type)
            and issubclass(obj, Action)
            and obj is not Action
            and obj.__module__ == module.__name__
        ]
        if len(candidates) != 1:
            raise ScriptError(
                f"Script {path!r} must define exactly one Action subclass; "
                f"found {len(candidates)}"
            )
        return candidates[0]()
```

Modify `acq4/experiment/actions/__init__.py` to add:
```python
from . import script  # noqa: F401
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_script_action.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Run the full engine suite**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/ -v`
Expected: PASS (all green).

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/actions/script.py acq4/experiment/actions/__init__.py acq4/experiment/tests/test_script_action.py
git commit --author="Claude <noreply@anthropic.com>" -m "feat: add Script action with reload-on-run and ScriptError handling"
```

---

## Deferred to later plans (not in P0)

- **P0b — FSM-wrapping + concrete patch actions:** `FsmCompositeAction` (entry state + declared terminal set, watches `PatchPipetteStateManager.sigStateChanged`), `FsmRawAction` (single state via `allowNextState=False`), the global state watcher that raises `ABNORMAL_STATE_EXCEPTIONS` unless the current action declared the state as an expected outcome, and concrete `Patch`/`Reseal`/`Clean`/`Cellfie`/`GoTo`/`Task` actions. Needs fake pipette + fake state-manager fixtures. Includes verifying the §4.4 state-classification table against each state's `run()`.
- **Operator Resume flow** (re-entry choice + optional recovery sub-plan) — belongs with the UI (P1), since it is operator-driven; the engine hooks (`AdvanceToNextCell`/`RetryCurrentCell` + re-seeding the queue) already exist.
- **P1–P4 UI** — main window (5 areas), interleaved find+patch loop, slice/region workflow, Camera integration, graph editor, polish. Each gets its own plan once the engine is in place.

---

## Self-Review

**Spec coverage (against the design doc §2–3, §5):**
- Action model (params/run/safeAbort/show/results/outcomes/signals) → Task 2. ✓
- Registry for type-name (de)serialization → Task 3. ✓
- Outcome-routed DAG with merges → Task 6 (`test_edges_can_merge`). ✓
- JSON persistence + public-param passthrough → Task 7. ✓
- Exception taxonomy + control-flow + abnormal-state map → Task 5. ✓
- Serial orchestrator loop, one protocol per slice → Tasks 8–9. ✓
- Pause = start-nothing-new at action boundaries → Task 8 (`_checkPause` in `_walk`) + Task 9 controls. ✓
- Stop → `safeAbort` → Task 9 (`test_stop_aborts_running_action`). ✓
- Next cell → Task 9 (`test_requestnextcell_skips_current`). ✓
- Exception handlers end in flow actions; catch-all `Exception → full stop` → Task 10 (`test_no_handler_aborts`, `test_handler_advance`, `test_handler_retry_then_success`, `test_catchall_handler_used_for_unmapped`). ✓
- Flow actions + operator Prompt → Task 11. ✓
- Script action reload-on-run + ScriptError → Task 12. ✓
- FSM wrapping (design §4) → explicitly deferred to P0b with rationale. ✓ (scoped out, not missed)

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — every code and test step contains complete content. ✓

**Type consistency:** `ExecutionContext(cell,pipette,manager,log)`, `Action.outcomes/paramSpec/paramValue/setState/run/safeAbort/show`, `register_action/get_action_class/action_type_name/_typeName`, `Protocol(nodes,edges,entry,publicParams,exceptionHandlers)/next_node/handler_for/to_dict/from_dict/save_json/load_json`, `Orchestrator(protocol,manager,contextFactory)/enqueue/run_sync/run_sync_cell/start/pause/resume/stop/requestNextCell/wait/_walk/_runAction/_processCell/_handleException/_checkPause`, exception names, and action type names (`Recording`/`Raising`/`Stop`/`Blocking`/`GoToNext`/`RetryCell`/`Abort`/`Prompt`/`Script`) are used consistently across tasks. ✓

**Cross-task dependency note:** Tasks 4↔5 and 10↔11 are mutually dependent; each dependency is called out inline with the recommended implementation order (5 before 4; 11 before 10).
