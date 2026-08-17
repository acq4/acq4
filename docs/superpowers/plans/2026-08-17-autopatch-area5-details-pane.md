# Autopatch Area 5 Details Pane — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Area 5's detail pane a retained, per-timeline-row record of what each action found, so a finished cell shows its results instead of an empty pane.

**Architecture:** A second engine seam, `ActionLogEntry.set_details(kind, payload)`, carries GUI-free plain data that outlives the action. `CellPanel` retains payloads keyed by `(id(cell), timeline row index)` and mounts them when the operator selects that row; a `kind` → builder registry in a new `details_renderers.py` owns every Qt widget the pane can show. `set_details_widget` keeps its existing contract for genuinely-live widgets.

**Tech Stack:** Python 3, PyQt (via `acq4.util.Qt`), pyqtgraph, numpy, pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-17-autopatch-area5-details-widgets-design.md`. This plan implements phase 1 of its §11 phasing.
- **Payload contract (spec §2):** payloads are plain data only — numpy arrays, strings, numbers, and dicts/lists of those. Never a `Qt` object, a `Cell`, an exception object, or a file handle. `CellPanel` retains them for the session.
- **Ordering invariant (spec §2):** `set_details` must be called before the entry finishes. Actions call it from a `try/finally` **inside** the `with ctx.log_action(...)` block.
- **No widget outlives its action.** `tests/test_teardown.py`'s invariants must keep passing unchanged.
- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Run pytest as `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest`.
- **Commits:** conventional format, `--author="Martin Chase (claude) <outofculture@gmail.com>"`, footer `🤖 Generated with [Claude Code](https://claude.ai/code)`. Never `--no-verify`.
- **Not in this phase:** anything touching `patch`/`reseal`, `MultiPatchLogRecorder`, `PatchPipette`, `MultiPatch`, or the `"test_pulse_history"` kind. Those are phases 2 and 3.

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `acq4/experiment/log_entry.py` | `ActionLogEntry`; gains `set_details` | Modify |
| `acq4/experiment/tests/test_log_entry.py` | seam tests | Modify |
| `acq4/modules/Autopatch/details_renderers.py` | `kind` → widget builders and the registry; the only new Qt in this phase | Create |
| `acq4/modules/Autopatch/tests/test_details_renderers.py` | builder tests | Create |
| `acq4/modules/Autopatch/cell_panel.py` | retention, row navigation, status line | Modify |
| `acq4/modules/Autopatch/tests/test_details_navigation.py` | retention + navigation tests | Create |
| `acq4/experiment/actions/device.py` | `cellfie`, `run_task`, `find_surface` payloads | Modify |
| `acq4/experiment/actions/prompt.py` | `prompt` payload | Modify |
| `acq4/experiment/actions/storage.py` | `new_data_dir` payload | Modify |
| `acq4/modules/TaskRunner/TaskRunner.py` | expose the sequence directory it creates | Modify |
| `acq4/experiment/tests/test_actions_device.py` | payload tests | Modify |
| `acq4/experiment/tests/test_actions_prompt_storage.py` | payload tests | Modify |

`details_renderers.py` is a separate module rather than more methods on `cell_panel.py` because that file is already 868 lines and this phase would add four widget types to it.

---

### Task 1: `ActionLogEntry.set_details`

**Files:**
- Modify: `acq4/experiment/log_entry.py`
- Test: `acq4/experiment/tests/test_log_entry.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ActionLogEntry.set_details(kind: str, payload) -> None`; attributes `details_kind: str | None`, `details_payload: Any`, `on_details: Callable | None` called as `on_details(entry, kind, payload)`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_log_entry.py`:

```python
def test_details_default_to_none():
    action_entry = ActionLogEntry("Patch")
    assert action_entry.details_kind is None
    assert action_entry.details_payload is None


def test_set_details_stores_kind_and_payload():
    action_entry = ActionLogEntry("Patch")
    action_entry.set_details("text", {"lines": ["hello"]})
    assert action_entry.details_kind == "text"
    assert action_entry.details_payload == {"lines": ["hello"]}


def test_on_details_hook_receives_entry_kind_and_payload():
    ctx = ExecutionContext()
    calls = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: calls.append((e, kind, payload))

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        action_entry.set_details("text", {"lines": ["a"]})
    assert calls == [(action_entry, "text", {"lines": ["a"]})]


def test_details_set_in_a_finally_arrive_before_finish():
    # CellPanel resolves an entry to its timeline row through bookkeeping that
    # the entry's finish tears down, so a payload set afterwards has no row to
    # attach to. An action's try/finally inside the `with` is what orders them.
    ctx = ExecutionContext()
    order = []

    def hook(action_entry):
        action_entry.on_details = lambda e, k, p: order.append("details")
        action_entry.on_finish = lambda e: order.append("finish")

    ctx.on_log_action = hook
    with ctx.log_action("Patch") as action_entry:
        try:
            pass
        finally:
            action_entry.set_details("text", {"lines": []})
    assert order == ["details", "finish"]


def test_details_survive_an_error_outcome():
    # An action that gathered data and then failed keeps the data: it is more
    # informative than the traceback, which the row's outcome also carries.
    ctx = ExecutionContext()
    with pytest.raises(BrokenPipette):
        with ctx.log_action("Patch") as action_entry:
            try:
                raise BrokenPipette("tip sheared off")
            finally:
                action_entry.set_details("text", {"lines": ["got this far"]})
    assert action_entry.outcome == "error"
    assert action_entry.details_payload == {"lines": ["got this far"]}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -v -k details`

Expected: FAIL — `AttributeError: 'ActionLogEntry' object has no attribute 'details_kind'` on the first test, and `no attribute 'set_details'` on the rest.

- [ ] **Step 3: Add the attributes**

In `acq4/experiment/log_entry.py`, inside `__init__`, immediately after `self.details_widget: Any = None`:

```python
        # Retained counterpart to details_widget: a GUI-free description of what
        # this action found, which outlives the action (see set_details).
        self.details_kind: str | None = None
        self.details_payload: Any = None
```

and after `self.on_widget: Callable | None = None`:

```python
        self.on_details: Callable | None = None
```

- [ ] **Step 4: Add `set_details`**

In `acq4/experiment/log_entry.py`, immediately after `set_details_widget`:

```python
    def set_details(self, kind: str, payload) -> None:
        """Hand the UI a retained description of what this action found, stored
        and passed to on_details(entry, kind, payload).

        The counterpart to set_details_widget(), and different from it in the one
        way that matters: what is passed here *outlives the action*. CellPanel
        keeps it for the rest of the session so the operator can re-read a
        finished action's results, which is why `payload` must be plain data --
        numpy arrays, strings, numbers, and dicts/lists of those -- and never a
        Qt object, a Cell, an exception, or a file handle. What a payload holds
        is what one action costs in memory for the rest of the run; see
        error_record.describe_exception for the same rule applied to tracebacks.

        `kind` selects how the UI renders the payload. An unrecognized kind
        renders as plain text rather than raising.

        **Must be called before this entry finishes.** CellPanel resolves an
        entry to its timeline row through bookkeeping that the entry's finish
        tears down, so a payload set afterwards has no row to attach to. Actions
        satisfy this by calling from a try/finally *inside* the
        `with ctx.log_action(...)` block, which runs before the context
        manager's __exit__.
        """
        self.details_kind = kind
        self.details_payload = payload
        if self.on_details is not None:
            self.on_details(self, kind, payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_log_entry.py -v`

Expected: PASS, all tests in the file (the pre-existing ones must be unaffected).

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/log_entry.py acq4/experiment/tests/test_log_entry.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): add ActionLogEntry.set_details

The retained counterpart to set_details_widget: a GUI-free payload that
outlives the action, so Area 5 can show a finished action's results rather
than clearing its pane. Documents the plain-data contract and the
before-finish ordering the UI's row bookkeeping depends on.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 2: The renderer registry, with the `text` and `error` builders

**Files:**
- Create: `acq4/modules/Autopatch/details_renderers.py`
- Test: `acq4/modules/Autopatch/tests/test_details_renderers.py`

**Interfaces:**
- Consumes: `acq4.modules.Autopatch.error_display.ErrorBlock(exc_type, exc_message, traceback_text, cell_repr=None)`.
- Produces: `buildDetailsWidget(kind: str, payload) -> Qt.QWidget`; `BUILDERS: dict[str, Callable]`; `buildText(payload)`; `buildError(payload)`; `captioned(widget, lines) -> Qt.QWidget`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_details_renderers.py`:

```python
"""Tests for the kind -> widget builders behind Area 5's detail pane, each
given the plain-data payload an action's set_details() hands over."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_text_builder_renders_each_line_read_only(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {"lines": ["surface at 1.2 mm", "depth ok"]})

    assert widget.isReadOnly()
    assert "surface at 1.2 mm" in widget.toPlainText()
    assert "depth ok" in widget.toPlainText()


def test_text_builder_tolerates_a_missing_lines_key(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {})

    assert widget.toPlainText() == ""


def test_text_builder_stringifies_non_strings(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("text", {"lines": [42, None]})

    assert "42" in widget.toPlainText()
    assert "None" in widget.toPlainText()


def test_error_builder_returns_an_error_block(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget
    from acq4.modules.Autopatch.error_display import ErrorBlock

    widget = buildDetailsWidget(
        "error",
        {
            "exc_type": "BrokenPipette",
            "exc_message": "tip sheared off",
            "traceback_text": "Traceback...\nBrokenPipette: tip sheared off",
            "cell_repr": "<Cell 0x1>",
        },
    )

    assert isinstance(widget, ErrorBlock)
    assert "BrokenPipette" in widget.headlineLabel.text()
    assert "tip sheared off" in widget.headlineLabel.text()
    assert "<Cell 0x1>" in widget.cellLabel.text()


def test_error_builder_tolerates_a_missing_cell_repr(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "error",
        {"exc_type": "E", "exc_message": "m", "traceback_text": "t"},
    )

    assert not widget.cellLabel.isVisible()


def test_unregistered_kind_renders_as_text_rather_than_raising(qapp):
    # A payload crosses a thread boundary out of protocol code. A protocol
    # author's typo must leave the pane usable, not take it down.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("no_such_kind", {"a": 1})

    assert "no_such_kind" in widget.toPlainText()
    assert "'a': 1" in widget.toPlainText()


def test_captioned_puts_the_caption_above_the_widget(qapp):
    from acq4.modules.Autopatch.details_renderers import captioned

    inner = Qt.QLabel("inner")
    wrapper = captioned(inner, ["12 sweeps", "saved to protocol_000"])

    assert wrapper.layout().indexOf(inner) != -1
    caption = wrapper.layout().itemAt(0).widget()
    assert "12 sweeps" in caption.text()
    assert "saved to protocol_000" in caption.text()


def test_captioned_with_no_lines_returns_the_widget_itself(qapp):
    from acq4.modules.Autopatch.details_renderers import captioned

    inner = Qt.QLabel("inner")

    assert captioned(inner, []) is inner
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.details_renderers'`.

- [ ] **Step 3: Create the module**

Create `acq4/modules/Autopatch/details_renderers.py`:

```python
"""Builders for Area 5's detail pane: one per ActionLogEntry.set_details() kind,
turning an action's retained plain-data payload into a widget to mount."""
from __future__ import annotations

from acq4.util import Qt

from .error_display import ErrorBlock


def captioned(widget, lines) -> Qt.QWidget:
    """`widget` under a caption of `lines`, or `widget` itself if there are none.

    Returning the bare widget for an empty caption keeps the pane's widget tree
    as shallow as the payload warrants, rather than wrapping everything in a
    layout that holds an empty label.
    """
    if not lines:
        return widget
    caption = Qt.QLabel("\n".join(str(line) for line in lines))
    caption.setWordWrap(True)
    # Selectable so a directory name or a measured value can be copied out.
    caption.setTextInteractionFlags(Qt.Qt.TextSelectableByMouse)
    wrapper = Qt.QWidget()
    layout = Qt.QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(caption)
    layout.addWidget(widget)
    wrapper.setLayout(layout)
    return wrapper


def buildText(payload) -> Qt.QWidget:
    """Plain lines, read-only and selectable so values can be copied out."""
    view = Qt.QPlainTextEdit("\n".join(str(line) for line in payload.get("lines", ())))
    view.setReadOnly(True)
    return view


def buildError(payload) -> Qt.QWidget:
    """One failed action's traceback. Takes strings, never an exception -- see
    ErrorBlock's own docstring for why."""
    return ErrorBlock(
        payload["exc_type"],
        payload["exc_message"],
        payload["traceback_text"],
        payload.get("cell_repr"),
    )


# kind -> builder, keyed by the string an action passes to set_details(). A
# builder takes only the payload and returns a widget: it never sees a Cell, an
# ActionLogEntry, or the panel, so nothing it builds can retain any of them.
BUILDERS = {
    "text": buildText,
    "error": buildError,
}


def buildDetailsWidget(kind: str, payload) -> Qt.QWidget:
    """The widget for one retained payload.

    An unregistered kind renders as text rather than raising. A payload crosses
    a thread boundary out of protocol code, and a protocol author's typo must
    leave the pane usable instead of taking it down.
    """
    builder = BUILDERS.get(kind)
    if builder is None:
        return buildText(
            {"lines": [f"unrecognized details kind {kind!r}", repr(payload)]}
        )
    return builder(payload)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v`

Expected: PASS, 8 tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/details_renderers.py acq4/modules/Autopatch/tests/test_details_renderers.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): add the details-pane renderer registry

A kind -> widget registry so every widget type Area 5's pane can mount lives
in one module rather than adding four more to cell_panel.py. Builders take
only a payload, so nothing they build can retain a Cell, an entry, or the
panel. An unregistered kind renders as text: a payload comes from protocol
code across a thread boundary, and a typo must not take the pane down.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 3: The `image_stack` and `task_results` builders

**Files:**
- Modify: `acq4/modules/Autopatch/details_renderers.py`
- Test: `acq4/modules/Autopatch/tests/test_details_renderers.py`

**Interfaces:**
- Consumes: `captioned`, `BUILDERS` from Task 2.
- Produces: `buildImageStack(payload)`, `buildTaskResults(payload)`, both registered in `BUILDERS` under `"image_stack"` and `"task_results"`.
- Payload shapes, relied on by Tasks 9 and 10: `"image_stack"` = `{"stack": ndarray, "center_index": int | None, "title": str}`; `"task_results"` = `{"traces": [(t_array, y_array), ...], "sequence_dir": str, "sweep_count": int, "decimation": int, "units": str}`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_renderers.py`:

```python
def test_image_stack_builder_opens_at_the_center_index(qapp):
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    wrapper = buildDetailsWidget(
        "image_stack", {"stack": stack, "center_index": 2, "title": "Cellfie"}
    )

    view = wrapper.findChild(pg.ImageView)
    assert view is not None
    assert view.currentIndex == 2


def test_image_stack_builder_shows_the_title_as_its_caption(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "image_stack",
        {"stack": np.zeros((3, 4, 4)), "center_index": 1, "title": "Cellfie"},
    )

    caption = wrapper.layout().itemAt(0).widget()
    assert "Cellfie" in caption.text()


def test_image_stack_builder_tolerates_a_none_center_index(qapp):
    # A 2D image or a single-frame stack has no meaningful center frame.
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "image_stack", {"stack": np.zeros((4, 4)), "center_index": None, "title": ""}
    )

    # An empty title means captioned() returns the view itself, unwrapped.
    assert isinstance(wrapper, pg.ImageView)
    assert wrapper.currentIndex == 0


def test_task_results_builder_plots_one_curve_per_sweep(qapp):
    import numpy as np
    import pyqtgraph as pg
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    payload = {
        "traces": [(t, t * 1.0), (t, t * 2.0), (t, t * 3.0)],
        "sequence_dir": "protocol_000",
        "sweep_count": 3,
        "decimation": 1,
        "units": "A",
    }

    wrapper = buildDetailsWidget("task_results", payload)

    plot = wrapper.findChild(pg.PlotWidget)
    assert plot is not None
    assert len(plot.plotItem.listDataItems()) == 3


def test_task_results_caption_reports_sweeps_directory_and_decimation(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [(t, t)],
            "sequence_dir": "protocol_007",
            "sweep_count": 1,
            "decimation": 25,
            "units": "A",
        },
    )

    text = wrapper.layout().itemAt(0).widget().text()
    assert "1" in text
    assert "protocol_007" in text
    assert "25" in text


def test_task_results_caption_omits_decimation_when_undecimated(qapp):
    import numpy as np
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    t = np.linspace(0, 1, 10)
    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [(t, t)],
            "sequence_dir": "protocol_000",
            "sweep_count": 1,
            "decimation": 1,
            "units": "A",
        },
    )

    assert "decimated" not in wrapper.layout().itemAt(0).widget().text()


def test_task_results_builder_tolerates_no_traces(qapp):
    # A sequence stopped before its first sweep completed.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    wrapper = buildDetailsWidget(
        "task_results",
        {
            "traces": [],
            "sequence_dir": "protocol_000",
            "sweep_count": 0,
            "decimation": 1,
            "units": "A",
        },
    )

    assert wrapper is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v -k "image_stack or task_results"`

Expected: FAIL — `buildDetailsWidget` falls through to the unknown-kind text renderer, so `wrapper.findChild(...)` returns `None` and `wrapper.layout()` is `None`.

- [ ] **Step 3: Add the two builders**

In `acq4/modules/Autopatch/details_renderers.py`, add the imports at the top after `from acq4.util import Qt`:

```python
import numpy as np
import pyqtgraph as pg
```

Add both builders after `buildError`:

```python
def buildImageStack(payload) -> Qt.QWidget:
    """A z-stack in a pg.ImageView, opened at the frame the cell was found on.

    setImage jumps to frame 0, which for a cellfie is the top of the stack and
    shows nothing; center_index is the plane the cell actually sits on.
    """
    view = pg.ImageView()
    view.setImage(np.asarray(payload["stack"]), autoRange=True, autoLevels=True)
    centerIndex = payload.get("center_index")
    if centerIndex is not None:
        view.setCurrentIndex(centerIndex)
    title = payload.get("title") or ""
    return captioned(view, [title] if title else [])


def buildTaskResults(payload) -> Qt.QWidget:
    """One TaskRunner sequence's sweeps, coloured over sequence index so the
    order they ran in is readable at a glance."""
    plot = pg.PlotWidget()
    plot.setLabels(left=("primary", payload.get("units") or ""), bottom=("time", "s"))
    traces = list(payload.get("traces", ()))
    for index, (times, values) in enumerate(traces):
        plot.plot(
            np.asarray(times),
            np.asarray(values),
            pen=pg.intColor(index, hues=max(len(traces), 1)),
        )
    lines = [
        f"{payload.get('sweep_count', len(traces))} sweeps"
        f" — saved to {payload.get('sequence_dir') or 'nowhere'}"
    ]
    decimation = payload.get("decimation", 1)
    if decimation > 1:
        # Never silent: the pane says what it is not showing, and the
        # undecimated data is in the saved sequence directory named above.
        lines.append(f"plotted decimated {decimation}x; full data on disk")
    return captioned(plot, lines)
```

Register both in `BUILDERS`:

```python
BUILDERS = {
    "text": buildText,
    "error": buildError,
    "image_stack": buildImageStack,
    "task_results": buildTaskResults,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v`

Expected: PASS, 15 tests.

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/details_renderers.py acq4/modules/Autopatch/tests/test_details_renderers.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): render image stacks and task-runner results

The cellfie stack opens at the plane the cell sits on rather than frame 0,
which for a cellfie is the top of the stack and shows nothing. Task-runner
sweeps are coloured over sequence index, and the caption names the saved
sequence directory and reports any decimation rather than plotting a
reduced trace silently.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 4: `CellPanel` retains payloads

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_details_navigation.py`

**Interfaces:**
- Consumes: `ActionLogEntry.on_details` (Task 1).
- Produces: `CellPanel._details: dict[tuple[int, int], tuple[str, Any]]`; `CellPanel.detailsFor(cell, rowIndex) -> tuple[str, Any] | None`; `CellPanel._dropDetailsFor(cellId) -> None`. The `"details"` phase string on `sigActionEntry`.

This task retains payloads and nothing more — no widget is mounted from one until Task 5. Retention is independently testable (`detailsFor` is the seam), and splitting it this way keeps this diff free of any half-built mounting path.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_details_navigation.py`:

```python
"""Tests for CellPanel's retention of ActionLogEntry.set_details() payloads and
the timeline-row navigation that mounts them in the detail pane."""
import pytest

from acq4.experiment.log_entry import ActionLogEntry
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentCell = Qt.Signal(object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)

    def pendingCells(self):
        return []


class _FakeManipulator:
    def __init__(self, target):
        self._target = target

    def targetPosition(self):
        return self._target


class _FakePipette:
    def __init__(self, target):
        self.pipetteDevice = _FakeManipulator(target)


@pytest.fixture
def panel(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    return CellPanel(pipetteGetter=lambda: _FakePipette((0, 0, 0)))


def _seed(panel, count=1):
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    for _ in range(count):
        panel.addFromTargetBtn.click()
    return orch.enqueued


def test_payload_is_retained_against_the_entrys_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["saved"]})


def test_payload_survives_the_entry_finishing(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})
    entry._finish(None)

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["saved"]})


def test_payloads_are_retained_per_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)

    first = ActionLogEntry("First")
    panel.onLogAction(cell, first)
    first.set_details("text", {"lines": ["one"]})
    first._finish(None)

    second = ActionLogEntry("Second")
    panel.onLogAction(cell, second)
    second.set_details("text", {"lines": ["two"]})
    second._finish(None)

    assert panel.detailsFor(cell, 0) == ("text", {"lines": ["one"]})
    assert panel.detailsFor(cell, 1) == ("text", {"lines": ["two"]})


def test_payloads_are_retained_for_an_unselected_cell(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(0)  # follow cellA while cellB works

    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cellB, entry)
    entry.set_details("text", {"lines": ["B's stack"]})

    assert panel.detailsFor(cellB, 0) == ("text", {"lines": ["B's stack"]})


def test_clear_cells_drops_retained_payloads(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["saved"]})

    panel.clearCells()

    assert panel._details == {}


def test_discarding_an_unattempted_cell_drops_its_payloads(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(0)
    entryA = ActionLogEntry("A")
    panel.onLogAction(cellA, entryA)
    entryA.set_details("text", {"lines": ["A"]})
    entryB = ActionLogEntry("B")
    panel.onLogAction(cellB, entryB)
    entryB.set_details("text", {"lines": ["B"]})

    panel._onCellsDiscarded([cellA])

    assert panel.detailsFor(cellA, 0) is None
    assert panel.detailsFor(cellB, 0) == ("text", {"lines": ["B"]})


def test_reuse_clears_the_cells_payloads(panel):
    # Pass 2 starts with a fresh timeline and log; retained details are that
    # same earlier-pass UI history and must go with them.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["pass 1"]})
    entry._finish(None)
    panel._onCellFinished(cell, "done")

    panel.cellList.item(0).setCheckState(Qt.Qt.Checked)
    panel.reuseCheckedCellsBtn.click()

    assert panel.detailsFor(cell, 0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v`

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'detailsFor'`.

- [ ] **Step 3: Add the store, the accessor, and the drop helper**

In `acq4/modules/Autopatch/cell_panel.py`, in `__init__` immediately after the `self._logs: dict[int, list[str]] = {}` line:

```python
        # (id(cell), timeline row index) -> (kind, payload) from that action's
        # ActionLogEntry.set_details(). Keyed by row rather than by entry
        # because the row key is what outlives the entry, which is the whole
        # point of retaining anything; it is also the key self._timelines
        # already uses. Holds only plain data -- never an entry, a cell, or a
        # widget -- so nothing here can form the reference cycle
        # tests/test_teardown.py exists to prevent (see set_details' docstring).
        self._details: dict[tuple[int, int], tuple[str, object]] = {}
```

Add these methods immediately after `errorText`:

```python
    def detailsFor(self, cell, rowIndex: int):
        """The (kind, payload) an action retained for `cell`'s row `rowIndex`,
        or None if that row's action retained nothing."""
        return self._details.get((id(cell), rowIndex))

    def _dropDetailsFor(self, cellId: int) -> None:
        """Forget every retained payload belonging to `cellId`.

        Scans rather than indexing by cell: the keys are (cell, row) pairs, and
        a per-cell index would be a second store to keep in sync with this one
        on all three of the paths that drop rows.
        """
        for key in [k for k in self._details if k[0] == cellId]:
            del self._details[key]
```

- [ ] **Step 4: Wire the `on_details` callback and the `"details"` phase**

In `onLogAction`, after the `entry.on_finish = ...` assignment:

```python
        entry.on_details = lambda e, kind, payload: self.sigActionEntry.emit(
            cell, e, "details"
        )
```

Extend `onLogAction`'s docstring by appending to the paragraph that lists the callbacks:

```python
        on_details is assigned here for the same reason and marshaled the same
        way; like the others it closes over `self` and `cell` only, and the
        payload is read back off the entry in the slot rather than carried
        through the signal, so sigActionEntry's signature is unchanged.
```

In `_onActionEntry`, add a branch before the trailing `"status"` comment:

```python
        elif phase == "details":
            # Stored only; mounting it is Task 5's job, once rows are
            # individually selectable and there is a notion of "the selected
            # row" to mount into.
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None:
                self._details[loc] = (entry.details_kind, entry.details_payload)
```

- [ ] **Step 5: Drop payloads wherever rows are dropped**

In `clearCells`, beside `self._timelines.clear()`:

```python
        self._details.clear()
```

In `_onCellsDiscarded`, in the branch that removes a never-attempted cell, beside `self._timelines.pop(cellId, None)`:

```python
            self._dropDetailsFor(cellId)
```

In `_onReuseCheckedCells`, beside `self._logs[id(cell)] = []`:

```python
            # Earlier-pass details are that pass's UI history, cleared with the
            # timeline and log for the same reason (design doc §7).
            self._dropDetailsFor(id(cell))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py acq4/modules/Autopatch/tests -v`

Expected: PASS, including every pre-existing Autopatch test.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_details_navigation.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): retain action details payloads per timeline row

Keyed by (cell, row) rather than by entry: the row key is what outlives the
entry, which is the point of retaining anything, and it is the key the
timeline store already uses. Holds only plain data, so nothing retained can
form the panel<->entry cycle the teardown tests guard against. Dropped
wherever rows are dropped -- clearCells, a rescan's discard, and reuse.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 5: Selecting a timeline row mounts its details

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_details_navigation.py`

**Interfaces:**
- Consumes: `detailsFor`, `_details`, `_isSelectedRow` (Task 4); `buildDetailsWidget` (Tasks 2–3).
- Produces: `CellPanel._liveWidgets: dict[int, Any]`; a real `CellPanel._mountSelectedRow()`; `CellPanel._onTimelineSelectionChanged(current, previous)`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_navigation.py`:

```python
def _mounted(panel):
    layout = panel.showContainer.layout()
    return [layout.itemAt(i).widget() for i in range(layout.count())]


def test_selecting_a_finished_row_mounts_its_payload(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["the cellfie stack"]})
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert len(_mounted(panel)) == 1
    assert "the cellfie stack" in _mounted(panel)[0].toPlainText()


def test_selecting_a_different_row_swaps_the_mounted_payload(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    first = ActionLogEntry("First")
    panel.onLogAction(cell, first)
    first.set_details("text", {"lines": ["one"]})
    first._finish(None)
    second = ActionLogEntry("Second")
    panel.onLogAction(cell, second)
    second.set_details("text", {"lines": ["two"]})
    second._finish(None)

    panel.timelineList.setCurrentRow(0)
    assert "one" in _mounted(panel)[0].toPlainText()

    panel.timelineList.setCurrentRow(1)
    assert "two" in _mounted(panel)[0].toPlainText()


def test_selecting_a_row_with_no_payload_leaves_the_pane_empty(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cell, entry)
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert _mounted(panel) == []


def test_a_live_widget_is_remounted_when_its_row_is_reselected(panel):
    # Navigating away clears the container, which reparents the live widget out.
    # Coming back must put the same widget back, not a dead one.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    finished = ActionLogEntry("Earlier")
    panel.onLogAction(cell, finished)
    finished._finish(None)

    live = ActionLogEntry("Patch")
    panel.onLogAction(cell, live)
    liveWidget = Qt.QLabel("live plot")
    live.set_details_widget(liveWidget)
    assert liveWidget in _mounted(panel)

    panel.timelineList.setCurrentRow(0)
    assert liveWidget not in _mounted(panel)

    panel.timelineList.setCurrentRow(1)
    assert liveWidget in _mounted(panel)


def test_a_finished_entrys_live_widget_is_forgotten(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_details_widget(Qt.QLabel("live plot"))
    entry._finish(None)

    assert panel._liveWidgets == {}


def test_a_payload_arriving_for_the_selected_row_mounts_immediately(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    panel.timelineList.setCurrentRow(0)

    entry.set_details("text", {"lines": ["just arrived"]})

    assert "just arrived" in _mounted(panel)[0].toPlainText()


def test_a_payload_replaces_the_live_widget_on_the_same_row(panel):
    # patch()'s finally sets its payload while its live plot is still mounted.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    liveWidget = Qt.QLabel("live plot")
    entry.set_details_widget(liveWidget)
    panel.timelineList.setCurrentRow(0)
    assert liveWidget in _mounted(panel)

    entry.set_details("text", {"lines": ["frozen"]})

    assert liveWidget not in _mounted(panel)
    assert "frozen" in _mounted(panel)[0].toPlainText()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v -k "selecting or live or arriving"`

Expected: FAIL — `_mounted(panel)` is `[]` where a payload was expected, since `_mountSelectedRow` is still the Task 4 placeholder and `timelineList` has no selection handler.

Task 5 also adds `_isSelectedRow`, used by the `"details"` branch Task 4 left storage-only and by Task 7's status line:

```python
    def _isSelectedRow(self, loc) -> bool:
        """Whether (cellId, rowIndex) is the row the operator is looking at."""
        cellId, index = loc
        cell = self._currentSelectedCell()
        return (
            cell is not None
            and id(cell) == cellId
            and self.timelineList.currentRow() == index
        )
```

and extends Task 4's `"details"` branch to mount a payload that arrives for the row already being watched:

```python
        elif phase == "details":
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None:
                self._details[loc] = (entry.details_kind, entry.details_payload)
                if self._isSelectedRow(loc):
                    self._mountSelectedRow()
```

- [ ] **Step 3: Add the live-widget store**

In `acq4/modules/Autopatch/cell_panel.py`, in `__init__` immediately after the `self._timelineItems` block:

```python
        # id(entry) -> the live widget that entry handed over via
        # set_details_widget(), held only while that entry's action is in
        # flight and dropped the moment it finishes.
        #
        # Required for row navigation rather than merely convenient: selecting
        # another row clears showContainer, which reparents the live widget out
        # of the GUI tree, and without a reference here Python would collect it
        # before the operator could select its row again. Dropping it on finish
        # is what keeps the module's "no widget outlives its action" invariant
        # (see tests/test_teardown.py).
        self._liveWidgets: dict[int, object] = {}
```

- [ ] **Step 4: Add `_mountSelectedRow` and connect the selection**

Add after `_clearShowContainer`:

```python
    def _mountSelectedRow(self) -> None:
        """Show whatever the currently selected timeline row has to show.

        Preference order: that row's live widget if its action is still in
        flight, else its retained payload, else nothing. A live action's widget
        wins because it is still being updated; the payload only exists once the
        action has something final to say.
        """
        self._clearShowContainer()
        self._shownEntryId = None
        cell = self._currentSelectedCell()
        index = self.timelineList.currentRow()
        if cell is None or index < 0:
            return
        loc = (id(cell), index)
        for entryId, entryLoc in self._entryTimelineLoc.items():
            if entryLoc == loc and entryId in self._liveWidgets:
                self.showContainer.layout().addWidget(self._liveWidgets[entryId])
                self._shownEntryId = entryId
                return
        stored = self._details.get(loc)
        if stored is None:
            return
        kind, payload = stored
        self.showContainer.layout().addWidget(buildDetailsWidget(kind, payload))

    def _onTimelineSelectionChanged(self, _current, _previous) -> None:
        self._mountSelectedRow()
```

Add the import at the top of the file, beside the existing `from .error_display import ErrorBlock`:

```python
from .details_renderers import buildDetailsWidget
```

Connect the signal in `__init__`, beside `self.cellList.currentItemChanged.connect(...)`:

```python
        self.timelineList.currentItemChanged.connect(self._onTimelineSelectionChanged)
```

- [ ] **Step 5: Route the `"widget"` and `"finished"` phases through the store**

In `_onActionEntry`, replace the `"widget"` branch with:

```python
        elif phase == "widget":
            widget = entry.details_widget
            if widget is None:
                self._liveWidgets.pop(id(entry), None)
            else:
                self._liveWidgets[id(entry)] = widget
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None and self._isSelectedRow(loc):
                self._mountSelectedRow()
```

In the `"finished"` branch, add the live-widget drop as its first statement, before the existing `self._finishTimelineRow(cell, entry)` call:

```python
            self._liveWidgets.pop(id(entry), None)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests -v`

Expected: PASS. `test_cell_log_and_show.py`'s existing tests must all still pass — they rely on a followed cell's newly appended row being the selected one, which Task 6 makes explicit but which already holds here because `timelineList`'s first appended item becomes current automatically.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_details_navigation.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): mount a timeline row's details when it is selected

The pane could previously show only the running action's widget or the
cell's last error. Rows are now individually selectable, mounting the row's
live widget if its action is in flight and its retained payload otherwise.

Live widgets are held by entry id while in flight, which navigation
requires rather than merely benefits from: leaving a row reparents the
widget out of the tree, and without a held reference it would be collected
before the operator could come back to it. Dropped on finish, so no widget
outlives its action.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 6: Auto-select a row, and follow the running action

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_details_navigation.py`

**Interfaces:**
- Consumes: `_mountSelectedRow` (Task 5).
- Produces: `CellPanel._isFollowingLastRow() -> bool`; `CellPanel._autoSelectRow(cellId) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_navigation.py`:

```python
def test_a_new_row_is_followed_while_the_last_row_is_selected(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    first = ActionLogEntry("First")
    panel.onLogAction(cell, first)
    first._finish(None)
    assert panel.timelineList.currentRow() == 0

    second = ActionLogEntry("Second")
    panel.onLogAction(cell, second)

    assert panel.timelineList.currentRow() == 1


def test_selecting_an_earlier_row_stops_following(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cell, entry)
        entry._finish(None)

    panel.timelineList.setCurrentRow(0)  # operator navigates back

    third = ActionLogEntry("Third")
    panel.onLogAction(cell, third)

    assert panel.timelineList.currentRow() == 0


def test_returning_to_the_last_row_resumes_following(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cell, entry)
        entry._finish(None)
    panel.timelineList.setCurrentRow(0)
    third = ActionLogEntry("Third")
    panel.onLogAction(cell, third)
    third._finish(None)
    assert panel.timelineList.currentRow() == 0

    panel.timelineList.setCurrentRow(panel.timelineList.count() - 1)

    fourth = ActionLogEntry("Fourth")
    panel.onLogAction(cell, fourth)

    assert panel.timelineList.currentRow() == panel.timelineList.count() - 1


def test_selecting_a_cell_auto_selects_its_running_row(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)  # look at B so A's rows build unrendered
    done = ActionLogEntry("Done")
    panel.onLogAction(cellA, done)
    done._finish(None)
    running = ActionLogEntry("Running")
    panel.onLogAction(cellA, running)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 1
    assert "running" in panel.timelineList.item(1).text()


def test_selecting_a_cell_auto_selects_its_failed_row(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)
    failed = ActionLogEntry("Patch")
    panel.onLogAction(cellA, failed)
    failed._finish(RuntimeError("boom"))
    later = ActionLogEntry("Pipette To Home")
    panel.onLogAction(cellA, later)
    later._finish(None)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 0


def test_selecting_a_cell_auto_selects_the_last_row_when_nothing_stands_out(panel):
    cellA, cellB = _seed(panel, 2)
    panel.cellList.setCurrentRow(1)
    for name in ("First", "Second"):
        entry = ActionLogEntry(name)
        panel.onLogAction(cellA, entry)
        entry._finish(None)

    panel.cellList.setCurrentRow(0)

    assert panel.timelineList.currentRow() == 1


def test_selecting_a_cell_with_no_rows_selects_nothing(panel):
    cellA, cellB = _seed(panel, 2)
    entry = ActionLogEntry("First")
    panel.onLogAction(cellA, entry)
    entry._finish(None)
    panel.cellList.setCurrentRow(0)

    panel.cellList.setCurrentRow(1)

    assert panel.timelineList.currentRow() == -1
    assert _mounted(panel) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v -k "following or auto_select"`

Expected: FAIL — new rows do not move the selection, and switching cells leaves `currentRow()` at whatever Qt's own first-item default produced.

- [ ] **Step 3: Add the follow-live check and the auto-select rule**

In `acq4/modules/Autopatch/cell_panel.py`, add after `_onTimelineSelectionChanged`:

```python
    def _isFollowingLastRow(self) -> bool:
        """Whether the operator is watching the newest row rather than reading
        back through earlier ones.

        The auto-scroll rule: while the last row is selected, a new action's row
        takes the selection with it; once the operator selects an earlier row,
        it does not, until they return to the last row. A timeline with no
        selection at all counts as following, so the first row of a freshly
        followed cell is shown rather than requiring a click.
        """
        count = self.timelineList.count()
        return count == 0 or self.timelineList.currentRow() in (-1, count - 1)

    def _autoSelectRow(self, cellId: int) -> None:
        """Select the row worth looking at for the cell just selected: the
        action still running, else the most recent one that failed, else the
        last one.

        Without this, switching to a cell would leave the pane blank until the
        operator clicked a row -- and, for a failed cell, would lose the
        traceback that used to mount on cell selection alone.
        """
        count = self.timelineList.count()
        if count == 0:
            self.timelineList.setCurrentRow(-1)
            return
        running = {
            index
            for entryId, (locCellId, index) in self._entryTimelineLoc.items()
            if locCellId == cellId
        }
        if running:
            self.timelineList.setCurrentRow(max(running))
            return
        failed = [
            index
            for (storeCellId, index), (kind, _payload) in self._details.items()
            if storeCellId == cellId and kind == "error"
        ]
        self.timelineList.setCurrentRow(max(failed) if failed else count - 1)
```

- [ ] **Step 4: Follow on append, and auto-select on cell switch**

In `_appendTimelineRow`, replace the `if cell is self._currentSelectedCell():` block with:

```python
        if cell is self._currentSelectedCell():
            following = self._isFollowingLastRow()
            item = Qt.QListWidgetItem(text)
            self.timelineList.addItem(item)
            self._timelineItems[id(entry)] = item
            if following:
                self.timelineList.setCurrentItem(item)
```

In `_onCellSelectionChanged`, replace the trailing `self._showErrorBlock(cell)` call with:

```python
        self._autoSelectRow(cellId)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests -v`

Expected: PASS. Note `test_cell_error_block.py` will still fail on the tests that assert an `ErrorBlock` mounts, because errors do not become payloads until Task 8 — if any fail here, they are the ones Task 8 fixes; every other test must pass.

If `test_cell_error_block.py` failures appear, record which and proceed; do not weaken `_autoSelectRow` to accommodate them.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_details_navigation.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): follow the running action, and auto-select a row per cell

Row selection needs a default, or switching cells leaves the pane blank
until the operator clicks. Selecting a cell now selects its running action,
else its most recent failure, else its last row -- which is also what keeps
"select a failed cell, see the traceback" working now that the pane is
driven by rows.

New rows take the selection only while the last row is already selected, so
reading back through an earlier action is not yanked away by the next one.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 7: The status line

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_details_navigation.py`

**Interfaces:**
- Consumes: `_isSelectedRow`, `_mountSelectedRow` (Tasks 4–5).
- Produces: `CellPanel.statusLabel: Qt.QLabel`; `CellPanel._statuses: dict[tuple[int, int], str]`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_navigation.py`:

```python
def test_status_shows_for_the_selected_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)

    entry.set_status("driving FSM from 'approach'")

    assert "driving FSM from 'approach'" in panel.statusLabel.text()


def test_status_updates_in_place_as_the_action_progresses(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)

    entry.set_status("now in 'seal'")
    entry.set_status("reached 'whole cell'")

    assert "reached 'whole cell'" in panel.statusLabel.text()
    assert "now in 'seal'" not in panel.statusLabel.text()


def test_status_is_not_shown_for_an_unselected_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    earlier = ActionLogEntry("Earlier")
    panel.onLogAction(cell, earlier)
    earlier.set_status("earlier status")
    earlier._finish(None)
    later = ActionLogEntry("Later")
    panel.onLogAction(cell, later)
    later.set_status("later status")

    panel.timelineList.setCurrentRow(0)

    assert "earlier status" in panel.statusLabel.text()
    assert "later status" not in panel.statusLabel.text()


def test_last_status_is_retained_after_the_action_finishes(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Cellfie")
    panel.onLogAction(cell, entry)
    entry.set_status("saving cellfie z-stack")
    entry._finish(None)

    panel.timelineList.setCurrentRow(0)

    assert "saving cellfie z-stack" in panel.statusLabel.text()


def test_status_clears_for_a_row_that_never_reported_one(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    withStatus = ActionLogEntry("With")
    panel.onLogAction(cell, withStatus)
    withStatus.set_status("something")
    withStatus._finish(None)
    withoutStatus = ActionLogEntry("Without")
    panel.onLogAction(cell, withoutStatus)
    withoutStatus._finish(None)

    panel.timelineList.setCurrentRow(1)

    assert panel.statusLabel.text() == ""


def test_clear_cells_drops_retained_statuses(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_status("something")

    panel.clearCells()

    assert panel._statuses == {}
    assert panel.statusLabel.text() == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v -k status`

Expected: FAIL with `AttributeError: 'CellPanel' object has no attribute 'statusLabel'`.

- [ ] **Step 3: Add the store and the label**

In `acq4/modules/Autopatch/cell_panel.py`, in `__init__` after the `self._details` block:

```python
        # (id(cell), timeline row index) -> that action's most recent
        # set_status() text. Retained alongside the payload so a finished row
        # still says what it was doing when it ended; a row absent from here
        # never reported a status.
        self._statuses: dict[tuple[int, int], str] = {}
```

Create the label beside `self.showContainer`:

```python
        # Header above the mounted details widget, carrying the selected
        # action's set_status() text -- which nothing displayed before this,
        # so every FSM state-transition message was thrown away. The timeline
        # rows deliberately do not show it (design doc §7).
        self.statusLabel = Qt.QLabel()
        self.statusLabel.setWordWrap(True)
```

Add it to the layout immediately before `layout.addWidget(self.showContainer)`:

```python
        layout.addWidget(self.statusLabel)
```

- [ ] **Step 4: Record and render the status**

In `_onActionEntry`, replace the trailing `"status"` comment block with a real branch:

```python
        elif phase == "status":
            # Recorded and shown in the pane's header, but deliberately NOT in
            # the timeline row: rows show "running" then the outcome and
            # nothing else (design doc §7).
            loc = self._entryTimelineLoc.get(id(entry))
            if loc is not None:
                self._statuses[loc] = entry.status
                if self._isSelectedRow(loc):
                    self.statusLabel.setText(entry.status)
```

In `_mountSelectedRow`, set the label from the store. Replace its opening lines:

```python
        self._clearShowContainer()
        self._shownEntryId = None
        cell = self._currentSelectedCell()
        index = self.timelineList.currentRow()
        if cell is None or index < 0:
            self.statusLabel.setText("")
            return
        loc = (id(cell), index)
        self.statusLabel.setText(self._statuses.get(loc, ""))
```

In `clearCells`, beside `self._details.clear()`:

```python
        self._statuses.clear()
        self.statusLabel.setText("")
```

In `_dropDetailsFor`, extend it to drop statuses too, and rename its docstring accordingly:

```python
    def _dropDetailsFor(self, cellId: int) -> None:
        """Forget every retained payload and status belonging to `cellId`.

        Scans rather than indexing by cell: the keys are (cell, row) pairs, and
        a per-cell index would be a second store to keep in sync with these two
        on all three of the paths that drop rows.
        """
        for key in [k for k in self._details if k[0] == cellId]:
            del self._details[key]
        for key in [k for k in self._statuses if k[0] == cellId]:
            del self._statuses[key]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v`

Expected: PASS on every status test.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_details_navigation.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): show the selected action's status in the detail pane

set_status() was write-only: the panel ignored the "status" phase outright,
so "driving FSM from 'approach'" -> "now in 'seal'" -> "reached 'whole
cell'" appeared nowhere in the UI at all. It now heads the detail pane, and
the last status is retained so a finished row still says what it was doing
when it ended. Timeline rows are unchanged, per design doc §7.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 8: A failed action's error becomes a row payload

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_details_navigation.py`

**Interfaces:**
- Consumes: `_details` (Task 4), the `"error"` builder (Task 2), `_autoSelectRow` (Task 6).
- Produces: nothing new. `errorText(cell)` and `_cellErrors` keep their existing signatures and meanings.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_navigation.py`:

```python
def test_a_failed_action_records_an_error_payload_on_its_row(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "error"
    assert payload["exc_type"] == "RuntimeError"
    assert payload["exc_message"] == "boom"
    assert "RuntimeError: boom" in payload["traceback_text"]
    assert payload["cell_repr"] == repr(cell)


def test_a_failed_actions_row_mounts_an_error_block(panel):
    from acq4.modules.Autopatch.error_display import ErrorBlock

    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    panel.timelineList.setCurrentRow(0)

    assert isinstance(_mounted(panel)[0], ErrorBlock)


def test_a_failed_action_that_set_a_payload_keeps_the_payload(panel):
    # The data it gathered before dying beats the traceback, which the log and
    # the row's outcome glyph both still carry.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry.set_details("text", {"lines": ["got this far"]})
    entry._finish(RuntimeError("boom"))

    kind, payload = panel.detailsFor(cell, 0)
    assert kind == "text"
    assert payload == {"lines": ["got this far"]}


def test_error_text_still_answers_which_cell_failed(panel):
    # _cellErrors and errorText() are a different question from "what did this
    # row do", and tests/test_teardown.py asserts against errorText.
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(RuntimeError("boom"))

    assert panel.errorText(cell)[0] == "RuntimeError"
    assert panel.errorText(cell)[1] == "boom"


def test_a_successful_action_records_no_error_payload(panel):
    (cell,) = _seed(panel)
    panel.cellList.setCurrentRow(0)
    entry = ActionLogEntry("Patch")
    panel.onLogAction(cell, entry)
    entry._finish(None)

    assert panel.detailsFor(cell, 0) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_navigation.py -v -k "failed or error_text"`

Expected: FAIL — `detailsFor(cell, 0)` returns `None` for a failed action.

- [ ] **Step 3: Record the error as a payload**

In `_onActionEntry`'s `"finished"` branch, the row location must be read **before** `_finishTimelineRow` runs, because that method pops `_entryTimelineLoc`. Replace the whole branch with:

```python
        elif phase == "finished":
            self._liveWidgets.pop(id(entry), None)
            # Read before _finishTimelineRow: that method pops this entry's
            # location, and the error payload below needs the row it names.
            loc = self._entryTimelineLoc.get(id(entry))
            self._finishTimelineRow(cell, entry)
            if entry.outcome == "error":
                self._cellErrors[id(cell)] = (
                    entry.exc_type,
                    entry.exc_message,
                    entry.traceback_text,
                )
                # An action that gathered data before failing keeps that data:
                # it says more than the traceback, which the log and this row's
                # own outcome glyph both still carry.
                if loc is not None and loc not in self._details:
                    self._details[loc] = (
                        "error",
                        {
                            "exc_type": entry.exc_type,
                            "exc_message": entry.exc_message,
                            "traceback_text": entry.traceback_text,
                            "cell_repr": repr(cell),
                        },
                    )
            if cell is self._currentSelectedCell():
                self._mountSelectedRow()
```

- [ ] **Step 4: Retire the cell-level error mount**

Delete the `_showErrorBlock` method entirely — `_autoSelectRow` reaches the same block through the failed row, and `_onReuseCheckedCells`/`_onCurrentCell` already clear `_cellErrors` on their own. Verify no callers remain:

Run: `grep -rn "_showErrorBlock" acq4/`

Expected: no output.

If `acq4/modules/Autopatch/tests/test_cell_error_block.py` calls it directly, update those tests to select the failed row and assert on the mounted widget instead, matching `test_a_failed_actions_row_mounts_an_error_block` above.

- [ ] **Step 5: Run the full Autopatch and experiment suites**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests acq4/experiment/tests -v`

Expected: PASS, all tests including `test_teardown.py` and `test_cell_error_block.py`.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
refactor(autopatch): make a failed action's error an ordinary row payload

ErrorBlock becomes one more renderer instead of a cell-level special case,
reached through the failed row that _autoSelectRow picks. _cellErrors and
errorText() are untouched: "which cell failed" is a different question from
"what did this row do", and the teardown tests assert against errorText.

An action that gathered data and then failed keeps its payload -- that data
says more than the traceback, which the log and the row's outcome glyph both
still carry. The row location is read before _finishTimelineRow, which pops
the bookkeeping the payload key comes from.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 9: `cellfie` retains its stack

**Files:**
- Modify: `acq4/experiment/actions/device.py`
- Test: `acq4/experiment/tests/test_actions_device.py`

**Interfaces:**
- Consumes: `set_details` (Task 1); the `"image_stack"` payload shape (Task 3).
- Produces: `device._trackerStack(cell) -> np.ndarray | None`.

- [ ] **Step 1: Write the failing tests**

In `acq4/experiment/tests/test_actions_device.py`, give `FakeCell` a tracker. Add to its `__init__`:

```python
        self.tracker_stack = None
```

and at the end of `initializeTracker`, after the error check:

```python
        if self.tracker_stack is not None:
            self._tracker = _FakeTracker(self.tracker_stack)
```

Add the supporting fakes above `FakeCell`:

```python
class _FakeObjectStack:
    def __init__(self, data):
        self.data = data


class _FakeMotionEstimator:
    def __init__(self, data):
        self.original_object_stack = _FakeObjectStack(data)


class _FakeTracker:
    """Stands in for the acq4_automation tracker cellfie initializes: exposes
    the one attribute chain the details payload reads."""

    def __init__(self, data):
        self.motion_estimator = _FakeMotionEstimator(data)
```

Append the tests:

```python
def test_cellfie_retains_the_trackers_stack_as_an_image_stack_payload(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    import numpy as np

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = np.arange(5 * 4 * 3, dtype=float).reshape(5, 4, 3)
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "image_stack"
    # Rows/cols swapped so it displays in the same orientation as the Camera
    # module, matching AutomationDebug's own cell stack view.
    assert payload["stack"].shape == (5, 3, 4)
    assert payload["center_index"] == 2
    assert payload["title"] == "Cellfie"


def test_cellfie_center_index_is_none_for_a_single_frame_stack(ctx, pip, monkeypatch):
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    import numpy as np

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = np.zeros((1, 4, 3))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert details[0][1]["center_index"] is None


def test_cellfie_sets_no_payload_when_the_tracker_exposes_no_stack(ctx, pip, monkeypatch):
    # A cell whose tracker did not expose a stack must not make cellfie raise
    # out of the orchestrator's worker thread over a display concern.
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    ctx.cell.tracker_stack = None
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    cellfie(ctx)

    assert details == []


def test_cellfie_sets_no_payload_when_the_cell_is_lost(monkeypatch, tmp_path):
    # tissue_moved never returns, so there is nothing to retain -- the accepted
    # gap in the spec's §8.
    pytest.importorskip("acq4_automation", reason=_CELLFIE_SKIP_REASON)
    from acq4_automation.feature_tracking import CellTrackingLost

    monkeypatch.setattr(device_mod, "run_image_sequence", lambda *a, **k: _Waitable())
    cell = FakeCell()
    cell.tracker_error = CellTrackingLost("gone")
    details = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: details.append(kind)

    ctx = ExecutionContext(
        cell=cell,
        pipette=FakePipette(),
        manager=FakeManager(),
        tissue_moved_hook=lambda c, reason: (_ for _ in ()).throw(AdvanceToNextCell(reason)),
    )
    ctx.on_log_action = hook

    with pytest.raises(AdvanceToNextCell):
        cellfie(ctx)

    assert details == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -v -k "retains_the_trackers or center_index or no_payload"`

Expected: FAIL — `assert len(details) == 1` fails with `details == []`, since `cellfie` sets no payload yet.

- [ ] **Step 3: Add the stack reader and the payload**

In `acq4/experiment/actions/device.py`, add the import at the top beside the existing imports:

```python
import numpy as np
```

Add the helper above `cellfie`:

```python
def _trackerStack(cell):
    """The 3D stack a cell's tracker holds, oriented for display, or None.

    Reads the same attribute chain AutomationDebug's cell stack view does, and
    swaps rows/cols the same way so the stack displays in the same orientation
    as the Camera module. Returns None rather than raising for a cell whose
    tracker never exposed one: this feeds a display payload, and an action must
    not fail on the orchestrator's worker thread over what the pane can show.
    """
    tracker = getattr(cell, "_tracker", None)
    if tracker is None:
        return None
    try:
        stack = tracker.motion_estimator.original_object_stack.data
    except Exception:
        return None
    if stack is None:
        return None
    stack = np.asarray(stack)
    if stack.ndim >= 2:
        stack = np.swapaxes(stack, -2, -1)
    return stack
```

In `cellfie`, replace the tracker-initialization `try/except` block's success path so the payload is set after it. The block becomes:

```python
        # Initialize the tracker reference used to follow the cell during patching.
        try:
            ctx.cell.initializeTracker(
                imager,
                use_cellpose=True,
                deformation_tolerance=DEFORMATION_TOLERANCE,
                segmenter=segmenter_path(),
            )
        except CellTrackingLost as exc:
            # The tracker could not re-find this cell against its own reference
            # stacks, so the stacks are useless: the cell has drifted out of
            # reach or died. That is a question about the tissue, not about this
            # action, and the window is what can answer it. Never returns, so
            # there is no stack to retain for the pane.
            ctx.tissue_moved(exc.reason or str(exc))
        # Retained for Area 5: the cube around the cell, which is what an
        # operator reads to judge a cellfie. The full acquired z-stack stays on
        # disk in the cellfie/ directory saved above.
        stack = _trackerStack(ctx.cell)
        if stack is not None:
            action_entry.set_details(
                "image_stack",
                {
                    "stack": stack,
                    "center_index": (
                        stack.shape[0] // 2
                        if stack.ndim >= 3 and stack.shape[0] > 1
                        else None
                    ),
                    "title": "Cellfie",
                },
            )
```

Update `cellfie`'s docstring by appending one line to it:

```python
    Retains the tracker's cropped object stack as this action's Area 5 details.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add acq4/experiment/actions/device.py acq4/experiment/tests/test_actions_device.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): retain the cellfie stack for Area 5

The cube around the cell that the tracker already holds -- the same data
AutomationDebug's cell view shows, with the same rows/cols swap so it
displays in the Camera module's orientation. Already in memory on the Cell,
so retaining it costs the pane nothing, and the full acquired z-stack stays
on disk where run_image_sequence put it.

Reads defensively and sets no payload when there is no stack: a display
concern must not fail an action on the orchestrator's worker thread. A
cellfie that loses the cell never returns from tissue_moved, so it retains
nothing -- the accepted gap in the spec's §8.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 10: `run_task` shows and retains its sweeps

**Files:**
- Modify: `acq4/experiment/actions/device.py`
- Modify: `acq4/modules/TaskRunner/TaskRunner.py:611-672`
- Test: `acq4/experiment/tests/test_actions_device.py`

**Interfaces:**
- Consumes: `set_details` (Task 1); the `"task_results"` payload shape (Task 3).
- Produces: `device._decimate(times, values, maxPoints=_MAX_TRACE_POINTS) -> tuple[np.ndarray, np.ndarray, int]`; module constant `_MAX_TRACE_POINTS = 4000`; `TaskRunner.lastSequenceDir: DirHandle | None`.

**Why `TaskRunner` is touched.** `runSequence` creates its storage directory as a local `dh` and never exposes it, so there is no way to ask the module afterwards where a sequence was saved. The payload's caption would silently read "saved to nowhere" on every real run. Two lines on `TaskRunner` fix that honestly; the alternative — captioning it with `currentTask.name()` — names the task rather than the auto-incremented directory that was actually created, which is the kind of almost-right label that misleads later.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_actions_device.py`:

```python
class _FakeMetaArray:
    """Stands in for a clamp device's task result: indexable by channel name,
    with an xvals('Time') axis, the shape MultiClamp's task GUI reads."""

    def __init__(self, times, primary):
        self._times = times
        self._primary = primary

    def __getitem__(self, key):
        assert key == "primary"
        return self._primary

    def xvals(self, axis):
        assert axis == "Time"
        return self._times


def _sequence_frame(clampName, times, primary, params=None):
    return {"result": {clampName: _FakeMetaArray(times, primary)}, "params": params or {}}


def test_decimate_leaves_a_short_trace_alone():
    import numpy as np

    t = np.linspace(0, 1, 100)
    times, values, factor = device_mod._decimate(t, t * 2.0, maxPoints=4000)

    assert factor == 1
    assert len(times) == 100
    assert np.array_equal(values, t * 2.0)


def test_decimate_reduces_a_long_trace_and_reports_the_factor():
    import numpy as np

    t = np.linspace(0, 1, 40000)
    times, values, factor = device_mod._decimate(t, t, maxPoints=4000)

    assert factor == 10
    assert len(times) == len(values) == 4000


def test_run_task_retains_each_sweep_as_a_task_results_payload(ctx, pip, monkeypatch):
    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    t = np.linspace(0, 1, 10)
    module.frames = [
        _sequence_frame(clampName, t, t * 1.0),
        _sequence_frame(clampName, t, t * 2.0),
    ]

    run_task(ctx)

    assert len(details) == 1
    kind, payload = details[0]
    assert kind == "task_results"
    assert payload["sweep_count"] == 2
    assert len(payload["traces"]) == 2
    assert payload["decimation"] == 1
    assert np.array_equal(payload["traces"][1][1], t * 2.0)


def test_run_task_payload_names_the_sequence_directory(ctx, pip, monkeypatch):
    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    module.sequence_dir_name = "protocol_003"
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    module.frames = []

    run_task(ctx)

    assert details[0][1]["sequence_dir"] == "protocol_003"


def test_run_task_retains_nothing_but_still_reports_when_no_sweeps_arrive(ctx, pip, monkeypatch):
    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    module.frames = []

    run_task(ctx)

    assert details[0][1]["sweep_count"] == 0
    assert details[0][1]["traces"] == []


def test_run_task_retains_its_sweeps_even_when_the_sequence_raises(ctx, pip, monkeypatch):
    import numpy as np

    clampName = pip.clampDevice.name()
    module = FakeTaskRunnerModule({clampName: object()})
    module.run_error = RuntimeError("amplifier fell over")
    ctx.manager.modules["TaskRunner"] = module
    monkeypatch.setattr(device_mod, "run_in_gui_thread", lambda fn, *a, **k: fn(*a, **k))
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )
    t = np.linspace(0, 1, 10)
    module.frames = [_sequence_frame(clampName, t, t)]

    with pytest.raises(RuntimeError):
        run_task(ctx)

    assert details[0][1]["sweep_count"] == 1
```

Extend `FakeTaskRunnerModule` so it can emit frames and fail. Replace it with:

```python
class FakeTaskRunnerModule(Qt.QObject):
    sigNewFrame = Qt.Signal(object)

    def __init__(self, docks, period=1.0, totalParams=5):
        super().__init__()
        self.docks = docks
        self.sequenceInfo = {"period": period, "totalParams": totalParams}
        self.run_calls = []
        self.run_error = None
        # Frames the run emits, standing in for the real module's per-sweep
        # sigNewFrame; and the directory handle run_task reads the saved
        # sequence's name off, mirroring TaskRunner.lastSequenceDir.
        self.frames = []
        self.lastSequenceDir = _FakeSequenceDir("protocol_000")

    def runSequence(self, store=True):
        self.run_calls.append(store)
        for frame in self.frames:
            self.sigNewFrame.emit(frame)
        return _Waitable(self.run_error)


class _FakeSequenceDir:
    def __init__(self, name):
        self._name = name

    def shortName(self):
        return self._name
```

and add `from acq4.util import Qt` to the file's imports. In `test_run_task_payload_names_the_sequence_directory`, replace `module.sequence_dir_name = "protocol_003"` with `module.lastSequenceDir = _FakeSequenceDir("protocol_003")`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -v -k "decimate or run_task"`

Expected: FAIL — `AttributeError: module 'acq4.experiment.actions.device' has no attribute '_decimate'`, and `details == []` for the payload tests.

- [ ] **Step 3: Add the decimation helper**

In `acq4/experiment/actions/device.py`, add the constant near the top after the imports:

```python
# Retained trace length per sweep. More than a plot's pixel width, and small
# enough that a 20-sweep sequence costs the pane well under a megabyte per cell
# rather than the 16 MB the undecimated sweeps would. The full data is in the
# saved ProtocolSequence directory either way.
_MAX_TRACE_POINTS = 4000
```

and the helper above `run_task`:

```python
def _decimate(times, values, maxPoints: int = _MAX_TRACE_POINTS):
    """(times, values, factor) reduced to at most `maxPoints` samples.

    A factor of 1 means nothing was dropped. The factor is returned rather than
    swallowed so the pane can say what it is not showing.
    """
    times = np.asarray(times)
    values = np.asarray(values)
    if len(values) <= maxPoints:
        return times, values, 1
    factor = int(np.ceil(len(values) / maxPoints))
    return times[::factor], values[::factor], factor
```

- [ ] **Step 4: Collect sweeps and retain them in `run_task`**

Replace `run_task`'s body from the `info = taskrunner.sequenceInfo` line onward:

```python
        info = taskrunner.sequenceInfo
        expected_duration = info["period"] * info["totalParams"]
        timeout = timeout or max(30, expected_duration * 20)
        clampName = ctx.pipette.clampDevice.name()
        traces = []
        decimation = 1

        def onNewFrame(frame):
            """Collect one sweep's clamp trace. Reads the result the way
            MultiClamp's own task GUI does: result['primary'] against
            result.xvals('Time')."""
            nonlocal decimation
            result = frame.get("result", {}).get(clampName)
            if result is None:
                return
            try:
                times, values, factor = _decimate(
                    result.xvals("Time"), result["primary"]
                )
            except Exception:
                # A device whose result is not shaped like a clamp recording is
                # not a reason to fail the sequence; the data is saved on disk
                # regardless of whether the pane can plot it.
                return
            traces.append((times, values))
            decimation = max(decimation, factor)

        # Queued by default, so sweeps arriving on the task thread do not touch
        # this action's collection from there.
        taskrunner.sigNewFrame.connect(onNewFrame)
        action_entry.set_status("running task runner sequence")
        try:
            run_in_gui_thread(taskrunner.runSequence, store=store).wait(timeout=timeout)
        finally:
            Qt.disconnect(taskrunner.sigNewFrame, onNewFrame)
            if decimation > 1:
                ctx.log(
                    f"{action_entry.name}: plotting sweeps decimated {decimation}x; "
                    f"full data saved on disk"
                )
            action_entry.set_details(
                "task_results",
                {
                    "traces": traces,
                    "sequence_dir": _sequenceDirName(taskrunner),
                    "sweep_count": len(traces),
                    "decimation": decimation,
                    "units": "A",
                },
            )
```

Add `from acq4.util import Qt` to the file's imports, and this helper beside `_decimate`:

```python
def _sequenceDirName(taskrunner) -> str:
    """The short name of the directory the sequence saved into, or "" if it did
    not save one (store=False, or a run that never got that far)."""
    sequenceDir = getattr(taskrunner, "lastSequenceDir", None)
    return "" if sequenceDir is None else sequenceDir.shortName()
```

- [ ] **Step 5: Expose the sequence directory on `TaskRunner`**

`runSequence` creates its storage directory as a local and never exposes it, so `_sequenceDirName` has nothing to read. In `acq4/modules/TaskRunner/TaskRunner.py`, add to `__init__` beside `self.currentTask = None` (line 131):

```python
        # The directory the most recent stored sequence saved into, so a caller
        # driving runSequence() can report where the data went. None until a
        # sequence runs with store=True.
        self.lastSequenceDir = None
```

In `runSequence`, immediately after the `dh = storeDirHandle.mkdir(name, autoIncrement=True, info=info)` line, add:

```python
                self.lastSequenceDir = dh
```

and in the `else` branch that sets `dh = None`, add:

```python
                self.lastSequenceDir = None
```

`shortName()` is inherited by `DirHandle` from `FileHandle` (`acq4/util/DataManager/dot_index.py:84`), so `_sequenceDirName` works against the real handle.

- [ ] **Step 6: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_device.py -v`

Expected: PASS, all tests in the file.

Then confirm `TaskRunner` still imports, since it has real device imports:

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "import acq4.modules.TaskRunner.TaskRunner as t; print(t.TaskRunner)"`

Expected: prints the class with no import error.

- [ ] **Step 7: Commit**

```bash
git add acq4/experiment/actions/device.py acq4/modules/TaskRunner/TaskRunner.py acq4/experiment/tests/test_actions_device.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): retain the task-runner sequence's sweeps for Area 5

Collects each sweep's clamp trace off sigNewFrame, reading it the way
MultiClamp's own task GUI does, and retains them as this action's details.
Set from a finally, so a sequence that fails partway still shows what it
managed to record.

Traces are decimated to 4000 points -- more than a plot's pixel width, and
enough to keep 20 sweeps well under a megabyte per cell instead of 16 -- with
the factor reported through ctx.log and carried in the payload rather than
reduced silently. The undecimated data is in the saved sequence directory.

TaskRunner gains lastSequenceDir so the payload can name that directory:
runSequence created it as a local and exposed it nowhere, so the caption had
nothing truthful to say about where the data went.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 11: `prompt`, `new_data_dir`, and `find_surface` retain their one fact

**Files:**
- Modify: `acq4/experiment/actions/prompt.py`
- Modify: `acq4/experiment/actions/storage.py`
- Modify: `acq4/experiment/actions/device.py`
- Test: `acq4/experiment/tests/test_actions_prompt_storage.py`
- Test: `acq4/experiment/tests/test_actions_device.py`

**Interfaces:**
- Consumes: `set_details` (Task 1); the `"text"` payload shape (Task 2).
- Produces: nothing new. All three keep their existing return values.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_actions_prompt_storage.py`:

```python
def test_prompt_retains_the_message_and_the_clicked_label(monkeypatch):
    from acq4.experiment.actions import prompt as prompt_mod
    from acq4.experiment.actions.prompt import prompt
    from acq4.experiment.context import ExecutionContext

    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: False)
    monkeypatch.setattr(prompt_mod, "prompt_user", lambda title, message, labels: "Retry")
    ctx = ExecutionContext()
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    assert prompt(ctx, message="Replace the pipette", choices=("Retry", "Skip")) == "Retry"

    assert details == [
        ("text", {"lines": ["Replace the pipette", "operator chose: Retry"]})
    ]


def test_prompt_retains_the_default_choice_when_headless(monkeypatch):
    from acq4.experiment.actions import prompt as prompt_mod
    from acq4.experiment.actions.prompt import prompt
    from acq4.experiment.context import ExecutionContext

    monkeypatch.setattr(prompt_mod, "_is_headless", lambda: True)
    ctx = ExecutionContext()
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    prompt(ctx, message="carry on", choices=("OK", "Cancel"))

    assert details[0][1]["lines"][1] == "operator chose: OK"


def test_new_data_dir_retains_the_directory_it_created():
    from acq4.experiment.actions.storage import new_data_dir
    from acq4.experiment.context import ExecutionContext

    class _Dir:
        def __init__(self, name):
            self._name = name

        def name(self):
            return self._name

        def isManaged(self):
            return True

        def info(self):
            return {"dirType": "Slice"}

        def mkdir(self, name, autoIncrement=False, info=None):
            return _Dir(f"/data/{name}")

        def parent(self):
            return self

        def setInfo(self, info):
            return None

    class _Manager:
        def __init__(self):
            self.current = _Dir("/data/slice_000")
            self.set_calls = []

        def getCurrentDir(self):
            return self.current

        def folderTypesConfig(self):
            return {"Cell": {"name": "cell_000"}}

        def setCurrentDir(self, d):
            self.set_calls.append(d)

    ctx = ExecutionContext(manager=_Manager())
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    created = new_data_dir(ctx, level="Cell")

    assert details == [("text", {"lines": [f"created {created.name()}"]})]
```

Append to `acq4/experiment/tests/test_actions_device.py`:

```python
def test_find_surface_retains_the_detected_depth(ctx, pip):
    pip.scope.surface_depth = -1.2e-3
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    depth = find_surface(ctx)

    assert depth == -1.2e-3
    kind, payload = details[0]
    assert kind == "text"
    assert "surface" in payload["lines"][0]
    assert "1.2 mm" in payload["lines"][0]


def test_find_surface_retains_nothing_when_detection_fails(ctx, pip):
    pip.scope.surface_error = ValueError("no surface found")
    details = []
    ctx.on_log_action = lambda e: setattr(
        e, "on_details", lambda entry, kind, payload: details.append((kind, payload))
    )

    with pytest.raises(OrchestrationError):
        find_surface(ctx)

    assert details == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_prompt_storage.py acq4/experiment/tests/test_actions_device.py -v -k "retains"`

Expected: FAIL — `details == []` for all four, since none of the three actions sets a payload.

- [ ] **Step 3: `prompt`**

In `acq4/experiment/actions/prompt.py`, replace the body of the `with` block:

```python
    with ctx.log_action("Operator Prompt") as action_entry:
        action_entry.set_status(message)
        ctx.log(message)
        # Bound to a local rather than returned directly, so the choice can be
        # retained for Area 5 before this entry finishes -- a payload set after
        # the block exits has no timeline row to attach to (see set_details).
        chosen = labels[0] if _is_headless() else prompt_user(title, message, labels)
        action_entry.set_details(
            "text", {"lines": [message, f"operator chose: {chosen}"]}
        )
        return chosen
```

- [ ] **Step 4: `new_data_dir`**

In `acq4/experiment/actions/storage.py`, replace `new_data_dir`'s body:

```python
    with ctx.log_action("New Data Directory") as action_entry:
        new_dir = create_data_dir(ctx.manager, level=level, set_current=set_current)
        action_entry.set_details("text", {"lines": [f"created {new_dir.name()}"]})
        return new_dir
```

- [ ] **Step 5: `find_surface`**

In `acq4/experiment/actions/device.py`, replace `find_surface`'s body from the `try` onward:

```python
        try:
            depth = scope.findSurfaceDepth(imager)
        except ValueError as e:
            raise OrchestrationError(f"{action_entry.name}: {e}") from e
        action_entry.set_details(
            "text", {"lines": [f"surface detected at {pg.siFormat(depth, suffix='m')}"]}
        )
        return depth
```

Add the import at the top of `device.py`:

```python
import pyqtgraph as pg
```

- [ ] **Step 6: Run the full experiment suite**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests -v`

Expected: PASS, all tests.

- [ ] **Step 7: Commit**

```bash
git add acq4/experiment/actions/prompt.py acq4/experiment/actions/storage.py acq4/experiment/actions/device.py acq4/experiment/tests/
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): retain the one fact prompt, new_data_dir, and find_surface produce

Which label the operator clicked, which directory was created, and the
detected surface depth -- each a fact worth being able to re-read off a
finished row rather than only finding in the log.

prompt binds its choice to a local before returning, because a payload set
after the log_action block exits has no timeline row to attach to.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 12: Verify the phase end to end

**Files:** none modified.

- [ ] **Step 1: Run the complete affected suites**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests -v`

Expected: PASS with no failures, no errors, and no new warnings. Test output must be pristine.

- [ ] **Step 2: Confirm nothing outside this phase's scope changed**

Run: `git diff --stat <phase-1-base>..HEAD -- acq4/ tools/`, where `<phase-1-base>` is the commit recorded in `.superpowers/sdd/progress.md` as this phase's starting point — not `cc291fe8e`, which predates the spec and plan commits.

Expected: changes confined to `acq4/experiment/log_entry.py`, `acq4/experiment/actions/{device,prompt,storage}.py`, `acq4/experiment/tests/`, `acq4/modules/Autopatch/{cell_panel,details_renderers}.py`, `acq4/modules/Autopatch/tests/`, and the two added lines in `acq4/modules/TaskRunner/TaskRunner.py`. Nothing under `acq4/devices/`, `acq4/modules/MultiPatch/`, `acq4/filetypes/`, or `tools/`.

- [ ] **Step 3: Report**

State which tasks landed, the final test count, and any test you had to modify rather than add — naming it and why.

---

## Self-Review Notes

**Spec coverage for phase 1.** §2 → Task 1. §3 retention → Task 4; navigation → Tasks 5–6; error-as-payload → Task 8; the `errorText` carve-out → Task 8. §4 registry and builders → Tasks 2–3 (the `"test_pulse_history"` row is phase 3). §8 `cellfie` → Task 9; `run_task` → Task 10; `prompt`/`new_data_dir`/`find_surface` → Task 11. §1's status line → Task 7. §9 threading is honored by construction in Tasks 4–5 and asserted by the pre-existing `test_log_action_entries_marshal_from_the_worker_thread_to_the_gui_thread`. §10's phase-1 items are distributed across the tasks that create the behavior.

**Deliberately deferred to phases 2–3:** §5, §6, §7, and §8's `patch`/`reseal`.

**Known test edits, not additions:** Task 8 may need to rewrite parts of `test_cell_error_block.py`, since `_showErrorBlock` is deleted and the error block is now reached through a row. Task 10 rewrites `FakeTaskRunnerModule` to emit frames. Task 9 extends `FakeCell` with a tracker. Each is called out in its task.

**One addition beyond the spec, and why.** Task 10 adds `TaskRunner.lastSequenceDir` (two lines). The spec's §8 says the `run_task` payload "carries" the saved sequence directory's name, but `runSequence` creates that directory as a local and exposes it nowhere — so the payload could not honestly carry it. Captioning with `currentTask.name()` instead would name the task rather than the auto-incremented directory actually created, which is worse than saying nothing.

**Verified against the code while planning:** `shortName()` is inherited by `DirHandle` from `FileHandle` (`acq4/util/DataManager/dot_index.py:84`); a clamp task result is read as `result['primary']` against `result.xvals('Time')` (`acq4/devices/MultiClamp/taskGUI.py:336`); `CellPanel.errorText` has exactly one consumer, `tests/test_teardown.py:351`; and `FakeCell` in `test_actions_device.py` has no `_tracker`, which is why Task 9's stack reader must tolerate its absence.
