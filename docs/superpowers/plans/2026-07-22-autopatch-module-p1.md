# Autopatch Module — P1: Run Window

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `acq4/modules/Autopatch/` — the operator-facing run window (design doc Areas 3/4/5) that loads a JSON/coded `Protocol`, lets the operator edit its public params, drives an `Orchestrator` with Start/Stop/Pause/Next, and shows live status, a cell list, a per-cell executed-path timeline, and a cell-scoped log. No graph editor, no slice/region UI, no cell-finding — cells are seeded manually into the orchestrator's queue.

**Architecture:** A `Module` subclass (`Autopatch`) opens an `AutopatchWindow(QWidget)` composed of small owned widgets, one per design-doc area, mirroring how `AutomationDebugWindow` composes `Autopatcher`/`CellDetector`/etc. rather than one monolithic class:
- `ProtocolPanel` (Area 4) — picks a `*.json` protocol file from a config directory, calls `Protocol.load_json`, renders `protocol.publicParams` as an editable `pyqtgraph.parametertree.ParameterTree` mirror (two-way bound back onto each node's real `Action.params`).
- `StatusPanel` (Area 3) — Start/Stop/Pause/Next buttons, a big status label bound to `Orchestrator.sigStatus`, a current-action line bound to `sigCurrentAction`, and a `Prompt`-aware instruction banner for error states.
- `CellPanel` (Area 5) — a `QListWidget` of enqueued/seeded cells kept in sync with `sigCurrentAction`/`sigCellFinished`, a per-cell executed-path timeline built live from `Action.sigStateChanged`, a log view, a live `show()` mount point, and a "Go to cam" button.
- `context_factory.py` — a free function `make_context_factory(pipetteGetter, manager, log=None)` returning the callable the `Orchestrator` uses to build `ExecutionContext(pipette=pipetteGetter(), cell=cell, manager=manager, log=log)` per cell. This is the fix for the flagged P0b gap: the engine's default context factory does not set `pipette`.

The `Autopatch` `Module` subclass follows `AutomationDebug`'s singleton-raise pattern and is registered the same way (directory-scan import via `acq4/modules/Autopatch/__init__.py` exporting the class; added to a config's `modules:` block to be launchable).

**Tech Stack:** Python ≥3.10, `acq4.util.Qt` (never import PyQt/PySide directly), `pyqtgraph.parametertree`, `pytest` + `pytest-qt` (`qapp` fixture), the P0/P0b engine in `acq4/experiment/` (consumed, not modified).

## Global Constraints
- Test runner: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest <path> -v`
- `from acq4.util import Qt` everywhere; never `import PyQt5`/`PySide2` directly.
- 2-line docstring at the top of every new file. Never `--no-verify`.
- Commit format (Task 1 only, per the run instructions for this plan):
  ```
  git add <files>
  git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: scaffold Autopatch module window (5-area skeleton)

  🤖 Generated with [Claude Code](https://claude.ai/code)"
  ```
  Later tasks (2+) follow the same `--author`/commit-message convention with a type/description matching that task.
- Branch `autopatch-module` (already created; do not switch).
- **Do NOT modify** `acq4/devices/` or `acq4/experiment/`. This plan consumes the engine's existing public API (`Orchestrator`, `Protocol`, `Action`, `ExecutionContext`, `registry`, `fsm`, `actions/`) as read in this run. If a task discovers the engine truly needs a change, stop and record it under "Open questions for the human" instead of editing it.
- Follow the `AutomationDebug` module conventions: `Qt.importTemplate` only if a `.ui` file is used (this plan uses **programmatic layout**, see Task 1 rationale); `InterfaceCombo` for device pickers; `getManager()` from `acq4.Manager` (or `acq4.getManager` per module) for manager access; `manager.declareInterface(name, [...], self)` in the `Module.__init__`.
- Every new widget file lives under `acq4/modules/Autopatch/`; tests live under `acq4/modules/Autopatch/tests/`.

## Out of scope for P1 (design doc phasing, §11)
- **Area 1** (slice & region demarcation, pinned-frame workflow, progress heatmap).
- **Area 2** (cell-finding config, auto-add/+add/recycle buttons).
- The **interleaved find+patch loop** (design doc §3.2) — P1's orchestrator queue is seeded manually, not by on-demand survey/detection.
- The **graph editor** (§8) — protocols are authored externally (hand-built JSON or a small Python script using the registered Action classes) and only *loaded*, never edited, in P1.
- **Camera module mirroring** (§10) — no ROI mirroring, no pinned-frame display integration.
- The **Resume re-entry flow** (§3.5: retry-vs-next-cell choice + recovery sub-plan picker) — P1's Resume is the raw `Orchestrator.resume()` call; the richer operator flow is P4 polish.

---

### Task 1: Module skeleton + window scaffold (5-area placeholder)

**Files:**
- Create: `acq4/modules/Autopatch/__init__.py`
- Create: `acq4/modules/Autopatch/Autopatch.py`
- Create: `acq4/modules/Autopatch/tests/__init__.py`
- Create: `acq4/modules/Autopatch/tests/test_window_skeleton.py`

**Interfaces:**
- Produces: `AutopatchWindow(Qt.QWidget)` — `__init__(self, module)`; attributes `self.area1Box`, `self.area2Box`, `self.area3Box`, `self.area4Box`, `self.area5Box` (each a `Qt.QGroupBox`, empty placeholders in this task, titled per the design doc's area names). Produces `Autopatch(Module)` — `moduleDisplayName = "Autopatch"`, `moduleCategory = "Utilities"`, singleton-raise `__init__(self, manager, name, config)`, `quit(self, fromUi=False)`.
- Rationale for **programmatic layout over a `.ui` file**: `AutomationDebugWindow` uses `window.ui` (a Designer file) because it has ~40 widgets; P1's skeleton has 5 group boxes and each area's real content arrives in later tasks as owned sub-widgets (`ProtocolPanel`, etc.) that lay out themselves. A hand-built `.ui` would need to be re-edited every later task for no benefit at this stage — plain `Qt.QVBoxLayout`/`QGroupBox` calls are simpler to extend task-by-task. (Flagged under Open Questions in case the human prefers a `.ui` file for Designer-based editing later.)

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/__init__.py` (empty) and `acq4/modules/Autopatch/tests/test_window_skeleton.py`:

```python
"""Tests that AutopatchWindow constructs and exposes the five design-doc areas
as labeled placeholder group boxes."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    """A QApplication is required to instantiate any QWidget."""
    return Qt.QApplication.instance() or Qt.QApplication([])


def test_window_constructs_with_five_area_boxes(qapp):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    win = AutopatchWindow(module=None)

    assert isinstance(win.area1Box, Qt.QGroupBox)
    assert isinstance(win.area2Box, Qt.QGroupBox)
    assert isinstance(win.area3Box, Qt.QGroupBox)
    assert isinstance(win.area4Box, Qt.QGroupBox)
    assert isinstance(win.area5Box, Qt.QGroupBox)


def test_area_titles_name_their_design_doc_role(qapp):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    win = AutopatchWindow(module=None)

    assert "slice" in win.area1Box.title().lower()
    assert "cell" in win.area2Box.title().lower() and "find" in win.area2Box.title().lower()
    assert "status" in win.area3Box.title().lower() or "action" in win.area3Box.title().lower()
    assert "protocol" in win.area4Box.title().lower()
    assert "cell" in win.area5Box.title().lower()


def test_window_has_a_title(qapp):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    win = AutopatchWindow(module=None)
    assert win.windowTitle() == "Autopatch"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_skeleton.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch'`

- [ ] **Step 3: Write the minimal implementation** — create `acq4/modules/Autopatch/Autopatch.py`:

```python
"""Autopatch module: the operator-facing run window for the experiment
orchestration engine (acq4/experiment/). See autopatch-orchestration-design.md."""
from __future__ import annotations

import os

from acq4.modules.Module import Module
from acq4.util import Qt


class AutopatchWindow(Qt.QWidget):
    """The Autopatch run window: five labeled areas per the design doc.

    This task only builds empty placeholder group boxes; later tasks add each
    area's real content (protocol selection, status/controls, cell list).
    """

    def __init__(self, module: "Autopatch | None" = None):
        super().__init__()
        self.module = module
        self.setWindowTitle("Autopatch")

        self.area1Box = Qt.QGroupBox("Area 1 — Slice && region")
        self.area2Box = Qt.QGroupBox("Area 2 — Cell finding")
        self.area3Box = Qt.QGroupBox("Area 3 — Status && actions")
        self.area4Box = Qt.QGroupBox("Area 4 — Protocol && params")
        self.area5Box = Qt.QGroupBox("Area 5 — Current cell")

        for box in (self.area1Box, self.area2Box, self.area3Box, self.area4Box, self.area5Box):
            box.setLayout(Qt.QVBoxLayout())

        topRow = Qt.QHBoxLayout()
        topRow.addWidget(self.area1Box)
        topRow.addWidget(self.area2Box)

        bottomRow = Qt.QHBoxLayout()
        bottomRow.addWidget(self.area3Box)
        bottomRow.addWidget(self.area4Box)
        bottomRow.addWidget(self.area5Box)

        outer = Qt.QVBoxLayout()
        outer.addLayout(topRow)
        outer.addLayout(bottomRow)
        self.setLayout(outer)


class Autopatch(Module):
    moduleDisplayName = "Autopatch"
    moduleCategory = "Utilities"
    _instance = None

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        if Autopatch._instance is not None:
            Autopatch._instance.ui.raise_()
            Autopatch._instance.ui.activateWindow()
            Qt.QTimer.singleShot(0, self.quit)
            return
        Autopatch._instance = self
        self.ui = AutopatchWindow(self)
        manager.declareInterface(name, ["autopatchModule"], self)
        self.ui.show()

    def window(self):
        return self.ui

    def quit(self, fromUi=False):
        if Autopatch._instance is self:
            Autopatch._instance = None
        if hasattr(self, "ui") and not fromUi:
            self.ui.close()
        super().quit()
```

- [ ] **Step 4: Create the package `__init__.py`** — `acq4/modules/Autopatch/__init__.py`:

```python
"""Autopatch module package: exports the Autopatch Module subclass so acq4's
module-discovery scan (acq4.modules.importBuiltinClasses) can find it."""
from .Autopatch import Autopatch
```

- [ ] **Step 5: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_skeleton.py -v`
Expected: 3 passed

- [ ] **Step 6: Confirm the module imports cleanly standalone**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "import acq4.modules.Autopatch; print(acq4.modules.Autopatch.Autopatch)"`
Expected: prints `<class 'acq4.modules.Autopatch.Autopatch.Autopatch'>` with no errors.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/__init__.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/__init__.py acq4/modules/Autopatch/tests/test_window_skeleton.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: scaffold Autopatch module window (5-area skeleton)

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 2: Protocol file picker + `Protocol.load_json` wiring (Area 4, load-only)

**Files:**
- Create: `acq4/modules/Autopatch/protocol_panel.py`
- Modify: `acq4/modules/Autopatch/Autopatch.py` (mount `ProtocolPanel` into `area4Box`)
- Test: `acq4/modules/Autopatch/tests/test_protocol_panel.py`

**Interfaces:**
- Consumes: `acq4.experiment.protocol.Protocol.load_json(path) -> Protocol` (Task 1 read, unchanged).
- Produces: `ProtocolPanel(Qt.QWidget)` — `__init__(self, protocolDir: str)` (required; the panel itself has no notion of a default location — see below); `self.fileCombo: Qt.QComboBox` (populated with `*.json` basenames found in `protocolDir`); `self.reloadBtn`, `self.loadBtn: Qt.QPushButton`; `self.protocol: Protocol | None`; signal `sigProtocolLoaded = Qt.Signal(object)` (emits the loaded `Protocol`); method `refreshFileList(self)`; method `loadSelected(self) -> Protocol` (raises the same exception `Protocol.load_json` raises on bad JSON — the panel does not swallow load errors, it surfaces them so the caller/human sees the failure). Creates `protocolDir` on disk (`os.makedirs(..., exist_ok=True)`) if missing, so the combo box never crashes on a not-yet-existing directory — it just starts empty.
- The *default* location (`os.path.join(module.manager.configDir, "protocols", "autopatch")`) is computed by `AutopatchWindow`, not by `ProtocolPanel` itself (see Step 5) — this keeps `ProtocolPanel` unit-testable with a plain `tmp_path`, independent of any `Manager`. (Exact location flagged under Open Questions — no naming convention exists yet for Autopatch protocol JSON files.)

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_protocol_panel.py`:

```python
"""Tests for ProtocolPanel: listing/loading Protocol JSON files from a directory."""
import json
import os

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _write_protocol(path, name):
    # A minimal valid Protocol: one GoToNext flow node as entry, no edges needed.
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoToNext", "params": {}}},
        "edges": [],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_refresh_lists_json_files_in_dir(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol(tmp_path, "demo.json")
    _write_protocol(tmp_path, "other.json")
    (tmp_path / "not_a_protocol.txt").write_text("ignore me")

    panel = ProtocolPanel(protocolDir=str(tmp_path))

    items = {panel.fileCombo.itemText(i) for i in range(panel.fileCombo.count())}
    assert items == {"demo.json", "other.json"}


def test_load_selected_emits_protocol(qapp, tmp_path):
    from acq4.experiment.protocol import Protocol
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")

    received = []
    panel.sigProtocolLoaded.connect(received.append)
    result = panel.loadSelected()

    assert isinstance(result, Protocol)
    assert result.entry == "n1"
    assert len(received) == 1 and received[0] is result
    assert panel.protocol is result


def test_missing_dir_starts_empty_not_crashing(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    missing = str(tmp_path / "does_not_exist_yet")
    panel = ProtocolPanel(protocolDir=missing)

    assert panel.fileCombo.count() == 0
    assert os.path.isdir(missing)  # created for future drops
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_protocol_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.protocol_panel'`

- [ ] **Step 3: Write minimal implementation** — create `acq4/modules/Autopatch/protocol_panel.py`:

```python
"""ProtocolPanel: Area 4's protocol picker — lists *.json protocol files in a
directory and loads the selected one via Protocol.load_json."""
from __future__ import annotations

import os

from acq4.experiment.protocol import Protocol
from acq4.util import Qt


class ProtocolPanel(Qt.QWidget):
    sigProtocolLoaded = Qt.Signal(object)  # Protocol

    def __init__(self, protocolDir: str):
        super().__init__()
        self.protocolDir = protocolDir
        os.makedirs(self.protocolDir, exist_ok=True)
        self.protocol: Protocol | None = None

        self.fileCombo = Qt.QComboBox()
        self.reloadBtn = Qt.QPushButton("Refresh")
        self.loadBtn = Qt.QPushButton("Load")

        row = Qt.QHBoxLayout()
        row.addWidget(self.fileCombo)
        row.addWidget(self.reloadBtn)
        row.addWidget(self.loadBtn)
        self.setLayout(row)

        self.reloadBtn.clicked.connect(self.refreshFileList)
        self.loadBtn.clicked.connect(self.loadSelected)

        self.refreshFileList()

    def refreshFileList(self) -> None:
        current = self.fileCombo.currentText()
        self.fileCombo.clear()
        names = sorted(f for f in os.listdir(self.protocolDir) if f.endswith(".json"))
        self.fileCombo.addItems(names)
        if current in names:
            self.fileCombo.setCurrentText(current)

    def loadSelected(self) -> Protocol:
        name = self.fileCombo.currentText()
        path = os.path.join(self.protocolDir, name)
        self.protocol = Protocol.load_json(path)
        self.sigProtocolLoaded.emit(self.protocol)
        return self.protocol
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_protocol_panel.py -v`
Expected: 3 passed

- [ ] **Step 5: Mount into the window, injecting `protocolDir` instead of calling the global `getManager()`** — `Module.__init__` (see `acq4/modules/Module.py`) already receives a real `manager` instance and stores it as `self.manager`, so `Autopatch` (the `Module` subclass) always has one; `AutopatchWindow` should accept it explicitly rather than reaching for the process-global `getManager()` singleton itself, which is what keeps the window constructible in a plain `qapp` test with no live `Manager`. Modify `acq4/modules/Autopatch/Autopatch.py`:

```python
# add import near the top
from .protocol_panel import ProtocolPanel
```

Replace `AutopatchWindow.__init__` (from Task 1) in full with:

```python
    def __init__(self, module: "Autopatch | None" = None, protocolDir: str | None = None):
        super().__init__()
        self.module = module
        self.manager = module.manager if module is not None else None
        self.setWindowTitle("Autopatch")

        self.area1Box = Qt.QGroupBox("Area 1 — Slice && region")
        self.area2Box = Qt.QGroupBox("Area 2 — Cell finding")
        self.area3Box = Qt.QGroupBox("Area 3 — Status && actions")
        self.area4Box = Qt.QGroupBox("Area 4 — Protocol && params")
        self.area5Box = Qt.QGroupBox("Area 5 — Current cell")

        for box in (self.area1Box, self.area2Box, self.area3Box, self.area4Box, self.area5Box):
            box.setLayout(Qt.QVBoxLayout())

        topRow = Qt.QHBoxLayout()
        topRow.addWidget(self.area1Box)
        topRow.addWidget(self.area2Box)

        bottomRow = Qt.QHBoxLayout()
        bottomRow.addWidget(self.area3Box)
        bottomRow.addWidget(self.area4Box)
        bottomRow.addWidget(self.area5Box)

        outer = Qt.QVBoxLayout()
        outer.addLayout(topRow)
        outer.addLayout(bottomRow)
        self.setLayout(outer)

        if protocolDir is None:
            if self.manager is None:
                raise ValueError(
                    "AutopatchWindow needs a `module` (for module.manager.configDir) "
                    "or an explicit `protocolDir`"
                )
            protocolDir = os.path.join(self.manager.configDir, "protocols", "autopatch")
        self.protocolPanel = ProtocolPanel(protocolDir=protocolDir)
        self.area4Box.layout().addWidget(self.protocolPanel)
```

- [ ] **Step 6: Update Task 1's tests to pass an explicit `protocolDir`** — now that `module=None` requires one, modify `acq4/modules/Autopatch/tests/test_window_skeleton.py`: add a `tmp_path` parameter to each test function and change every `AutopatchWindow(module=None)` call to `AutopatchWindow(module=None, protocolDir=str(tmp_path))`, e.g.:

```python
def test_window_constructs_with_five_area_boxes(qapp, tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    win = AutopatchWindow(module=None, protocolDir=str(tmp_path))

    assert isinstance(win.area1Box, Qt.QGroupBox)
    assert isinstance(win.area2Box, Qt.QGroupBox)
    assert isinstance(win.area3Box, Qt.QGroupBox)
    assert isinstance(win.area4Box, Qt.QGroupBox)
    assert isinstance(win.area5Box, Qt.QGroupBox)
```

Apply the same `tmp_path` + `protocolDir=str(tmp_path)` change to `test_area_titles_name_their_design_doc_role` and `test_window_has_a_title`.

- [ ] **Step 7: Run the full Autopatch test dir to confirm no regression**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v`
Expected: all pass (Task 1's 3 tests + Task 2's 3 tests).

- [ ] **Step 8: Commit**

```bash
git add acq4/modules/Autopatch/protocol_panel.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_protocol_panel.py acq4/modules/Autopatch/tests/test_window_skeleton.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add Autopatch protocol file picker (Area 4 load-only)

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 3: Public-params `ParameterTree` mirror (Area 4 params)

**Files:**
- Modify: `acq4/modules/Autopatch/protocol_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_protocol_panel_params.py`

**Interfaces:**
- Consumes: `Protocol.publicParams` (`[{"node": id, "param": name, "public": public_name}, ...]`), `Action.params` (a pyqtgraph `Parameter` group), `Action.paramValue(name)`.
- Produces: `ProtocolPanel._rebuildParamTree(self) -> None` — builds a fresh top-level `Parameter` group named `"params"` with one child per `publicParams` entry (`name=public_name`, `type=`/`value=` mirrored from the source node's param), stores it as `self.paramsRoot: Parameter` and displays it in `self.paramTree: ParameterTree` (a `pyqtgraph.parametertree.ParameterTree` widget, constructed in `__init__`) mounted below the file-picker row; two-way bound so editing the mirror pushes the new value onto `protocol.nodes[node].params.child(param)` via `sigValueChanged`. Called by `loadSelected()` every time a protocol loads.

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_protocol_panel_params.py`:

```python
"""Tests that ProtocolPanel renders a protocol's publicParams as an editable
ParameterTree mirror, two-way bound onto the underlying Action params."""
import json
import os

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _write_protocol_with_public_param(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoHome", "params": {"speed": "slow"}}},
        "edges": [],
        "publicParams": [{"node": "n1", "param": "speed", "public": "Approach speed"}],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_param_tree_has_one_child_per_public_param(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_public_param(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")
    panel.loadSelected()

    names = [c.name() for c in panel.paramsRoot.children()]
    assert names == ["Approach speed"]
    assert panel.paramsRoot.child("Approach speed").value() == "slow"


def test_editing_mirror_pushes_value_to_underlying_action_param(qapp, tmp_path):
    from acq4.modules.Autopatch.protocol_panel import ProtocolPanel

    _write_protocol_with_public_param(tmp_path, "demo.json")
    panel = ProtocolPanel(protocolDir=str(tmp_path))
    panel.fileCombo.setCurrentText("demo.json")
    panel.loadSelected()

    panel.paramsRoot.child("Approach speed").setValue("fast")

    assert panel.protocol.nodes["n1"].paramValue("speed") == "fast"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_protocol_panel_params.py -v`
Expected: FAIL with `AttributeError: 'ProtocolPanel' object has no attribute 'paramTree'`

- [ ] **Step 3: Implement** — modify `acq4/modules/Autopatch/protocol_panel.py`, add imports:

```python
from pyqtgraph.parametertree import Parameter, ParameterTree
```

add to `__init__` (after the file-picker `row` layout is set):

```python
        self.paramTree = ParameterTree(showHeader=False)
        self.paramsRoot = None
        outer = Qt.QVBoxLayout()
        outer.addLayout(row)
        outer.addWidget(self.paramTree)
        self.setLayout(outer)
```

(replacing the earlier `self.setLayout(row)` call), and add a method + call it from `loadSelected`:

```python
    def loadSelected(self) -> Protocol:
        name = self.fileCombo.currentText()
        path = os.path.join(self.protocolDir, name)
        self.protocol = Protocol.load_json(path)
        self._rebuildParamTree()
        self.sigProtocolLoaded.emit(self.protocol)
        return self.protocol

    def _rebuildParamTree(self) -> None:
        children = []
        for entry in self.protocol.publicParams:
            action = self.protocol.nodes[entry["node"]]
            srcParam = action.params.child(entry["param"])
            children.append(
                dict(
                    name=entry["public"],
                    type=srcParam.type(),
                    value=srcParam.value(),
                )
            )
        root = Parameter.create(name="params", type="group", children=children)
        for entry in self.protocol.publicParams:
            action = self.protocol.nodes[entry["node"]]
            mirror = root.child(entry["public"])
            mirror.sigValueChanged.connect(
                lambda param, val, node=entry["node"], pname=entry["param"]: (
                    self.protocol.nodes[node].params.child(pname).setValue(val)
                )
            )
        self.paramsRoot = root
        self.paramTree.setParameters(root, showTop=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_protocol_panel_params.py -v`
Expected: 2 passed

- [ ] **Step 5: Re-run the full Autopatch test dir**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v`
Expected: all pass, no regressions in Tasks 1-2's tests.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/protocol_panel.py acq4/modules/Autopatch/tests/test_protocol_panel_params.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: render protocol public params as an editable ParameterTree mirror

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 4: Context factory binding the selected pipette

**Files:**
- Create: `acq4/modules/Autopatch/context_factory.py`
- Test: `acq4/modules/Autopatch/tests/test_context_factory.py`

**Interfaces:**
- Consumes: `acq4.experiment.context.ExecutionContext` (fields `cell`, `pipette`, `manager`, `log`).
- Produces: `make_context_factory(pipetteGetter, manager, log=None) -> Callable[[cell], ExecutionContext]`. `pipetteGetter` is a zero-arg callable returning the currently-selected pipette device (or `None`); `log` is an optional `Callable[[str], None]`, defaulting to a no-op like `ExecutionContext`'s own default. This is a **plain function**, independent of any UI widget, so it is unit-testable headless and is the fix for the P0b-flagged gap ("the engine's DEFAULT context factory does NOT set pipette").

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_context_factory.py`:

```python
"""Tests for make_context_factory: builds an Orchestrator contextFactory that
binds the currently-selected pipette (fixing the P0b context-factory gap)."""
from acq4.experiment.context import ExecutionContext


def test_factory_binds_pipette_cell_and_manager():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    pip = object()
    manager = object()
    factory = make_context_factory(pipetteGetter=lambda: pip, manager=manager)

    cell = object()
    ctx = factory(cell)

    assert isinstance(ctx, ExecutionContext)
    assert ctx.pipette is pip
    assert ctx.cell is cell
    assert ctx.manager is manager


def test_factory_rereads_pipette_getter_each_call():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    pips = [object(), object()]
    factory = make_context_factory(pipetteGetter=lambda: pips.pop(0), manager=None)

    first = factory(object())
    second = factory(object())

    assert first.pipette is not second.pipette


def test_factory_forwards_log_callable():
    from acq4.modules.Autopatch.context_factory import make_context_factory

    messages = []
    factory = make_context_factory(
        pipetteGetter=lambda: None, manager=None, log=messages.append
    )

    ctx = factory(object())
    ctx.log("hello")

    assert messages == ["hello"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_context_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.context_factory'`

- [ ] **Step 3: Implement** — create `acq4/modules/Autopatch/context_factory.py`:

```python
"""context_factory: builds the Orchestrator's per-cell ExecutionContext factory,
binding the operator-selected pipette (the engine's default factory does not)."""
from __future__ import annotations

from typing import Callable

from acq4.experiment.context import ExecutionContext


def make_context_factory(
    pipetteGetter: Callable[[], object],
    manager,
    log: Callable[[str], None] | None = None,
) -> Callable[[object], ExecutionContext]:
    def _factory(cell) -> ExecutionContext:
        kwargs = dict(cell=cell, pipette=pipetteGetter(), manager=manager)
        if log is not None:
            kwargs["log"] = log
        return ExecutionContext(**kwargs)

    return _factory
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_context_factory.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/context_factory.py acq4/modules/Autopatch/tests/test_context_factory.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add pipette-binding context factory for the Autopatch orchestrator

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 5: StatusPanel — Start/Stop/Pause/Next + status indicator (Area 3)

**Files:**
- Create: `acq4/modules/Autopatch/status_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_status_panel.py`

**Interfaces:**
- Consumes: `Orchestrator` (`.sigStatus(str)`, `.sigCurrentAction(cell, action)`, `.start()`, `.pause()`, `.resume()`, `.stop()`, `.requestNextCell()`).
- Produces: `StatusPanel(Qt.QWidget)` — `__init__(self)`; `self.startBtn/self.stopBtn/self.pauseBtn/self.nextBtn: Qt.QPushButton`; `self.statusLabel: Qt.QLabel` (big font via `setStyleSheet`); `self.currentActionLabel: Qt.QLabel`; `self.instructionLabel: Qt.QLabel` (hidden unless status is "error"); method `bindOrchestrator(self, orchestrator: Orchestrator) -> None` — connects buttons to the orchestrator's controls and the orchestrator's signals to the labels; disconnects any previously-bound orchestrator first (so re-binding after loading a new protocol doesn't double-fire).

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_status_panel.py`:

```python
"""Tests for StatusPanel: Start/Stop/Pause/Next wired to an Orchestrator, and
sigStatus/sigCurrentAction reflected in the status + current-action labels."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigStatus = Qt.Signal(str)
    sigCurrentAction = Qt.Signal(object, object)

    def __init__(self):
        super().__init__()
        self.started = self.stopped = self.paused = self.resumed = self.nexted = 0

    def start(self):
        self.started += 1

    def stop(self, reason=""):
        self.stopped += 1

    def pause(self):
        self.paused += 1

    def resume(self):
        self.resumed += 1

    def requestNextCell(self):
        self.nexted += 1


def test_buttons_drive_the_bound_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.startBtn.click()
    panel.pauseBtn.click()
    panel.stopBtn.click()
    panel.nextBtn.click()

    assert orch.started == 1
    assert orch.paused == 1
    assert orch.stopped == 1
    assert orch.nexted == 1


def test_status_signal_updates_label(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    orch.sigStatus.emit("running")
    assert "running" in panel.statusLabel.text().lower()

    orch.sigStatus.emit("error")
    assert "error" in panel.statusLabel.text().lower()
    assert panel.instructionLabel.isVisible()


def test_current_action_signal_updates_label(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    class _Cell:
        def __repr__(self):
            return "cell-1"

    class _Action:
        name = "Patch"

    panel = StatusPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    orch.sigCurrentAction.emit(_Cell(), _Action())
    assert "Patch" in panel.currentActionLabel.text()
    assert "cell-1" in panel.currentActionLabel.text()

    orch.sigCurrentAction.emit(None, None)
    assert panel.currentActionLabel.text() == ""


def test_rebinding_disconnects_previous_orchestrator(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    orch1 = _FakeOrchestrator()
    orch2 = _FakeOrchestrator()
    panel.bindOrchestrator(orch1)
    panel.bindOrchestrator(orch2)

    panel.startBtn.click()

    assert orch2.started == 1
    assert orch1.started == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.status_panel'`

- [ ] **Step 3: Implement** — create `acq4/modules/Autopatch/status_panel.py`:

```python
"""StatusPanel: Area 3's global controls (Start/Stop/Pause/Next) and the big
Running/Waiting/Paused/Error status indicator bound to an Orchestrator."""
from __future__ import annotations

from acq4.util import Qt


class StatusPanel(Qt.QWidget):
    def __init__(self):
        super().__init__()
        self._orchestrator = None

        self.startBtn = Qt.QPushButton("Start")
        self.stopBtn = Qt.QPushButton("Stop")
        self.pauseBtn = Qt.QPushButton("Pause")
        self.nextBtn = Qt.QPushButton("Next cell")

        self.statusLabel = Qt.QLabel("idle")
        self.statusLabel.setStyleSheet("font-size: 20pt; font-weight: bold;")
        self.currentActionLabel = Qt.QLabel("")
        self.instructionLabel = Qt.QLabel("")
        self.instructionLabel.setStyleSheet("color: red; font-weight: bold;")
        self.instructionLabel.setVisible(False)

        btnRow = Qt.QHBoxLayout()
        for b in (self.startBtn, self.stopBtn, self.pauseBtn, self.nextBtn):
            btnRow.addWidget(b)

        layout = Qt.QVBoxLayout()
        layout.addLayout(btnRow)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.currentActionLabel)
        layout.addWidget(self.instructionLabel)
        self.setLayout(layout)

    def bindOrchestrator(self, orchestrator) -> None:
        if self._orchestrator is not None:
            Qt.disconnect(self.startBtn.clicked, self._orchestrator.start)
            Qt.disconnect(self.stopBtn.clicked, self._orchestrator.stop)
            Qt.disconnect(self.pauseBtn.clicked, self._orchestrator.pause)
            Qt.disconnect(self.nextBtn.clicked, self._orchestrator.requestNextCell)
            Qt.disconnect(self._orchestrator.sigStatus, self._onStatus)
            Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)

        self._orchestrator = orchestrator
        self.startBtn.clicked.connect(orchestrator.start)
        self.stopBtn.clicked.connect(orchestrator.stop)
        self.pauseBtn.clicked.connect(orchestrator.pause)
        self.nextBtn.clicked.connect(orchestrator.requestNextCell)
        orchestrator.sigStatus.connect(self._onStatus)
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)

    def _onStatus(self, status: str) -> None:
        self.statusLabel.setText(status)
        self.instructionLabel.setVisible(status == "error")

    def _onCurrentAction(self, cell, action) -> None:
        if action is None:
            self.currentActionLabel.setText("")
            return
        self.currentActionLabel.setText(f"{action.name} — {cell!r}")
```

Note: `pauseBtn` in this task is a plain "Pause" click; toggling it back to "Resume" after a pause is a UX nicety left for a follow-up polish task, not required by this task's tests.

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/status_panel.py acq4/modules/Autopatch/tests/test_status_panel.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add StatusPanel with Start/Stop/Pause/Next and status indicator

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 6: CellPanel — cell list seeded manually, driven by orchestrator signals (Area 5, list only)

> **SUPERSEDED (human decision, applied 2026-07-22):** the x/y/z-`QLineEdit` seeding mechanism below (Open Question #2's proposal) was dropped before implementation. The actually-built `CellPanel` seeds via **two** buttons instead: `self.addFromTargetBtn` ("Add from target") — builds `Cell(Point(pipetteGetter().targetPosition(), "global"))` from the injected `pipetteGetter` callable (a no-op if it resolves to `None`); and `self.scatterFakeCellsBtn` ("Scatter fake cells") — enqueues 3-5 `Cell`s at random offsets (±40µm) around `cameraGetter().globalCenterPosition()` (a no-op if it resolves to `None`). `CellPanel.__init__(self, pipetteGetter=None, cameraGetter=None)` takes both getters as optional injected callables, mirroring `make_context_factory`'s pipette-getter pattern, so the panel stays unit-testable with plain fakes. See `acq4/modules/Autopatch/cell_panel.py` and `acq4/modules/Autopatch/tests/test_cell_panel.py` for the implementation actually shipped. The rest of this task's description (list/signal wiring) still applies as written.

**Files:**
- Create: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_cell_panel.py`

**Interfaces:**
- Consumes: `Orchestrator.enqueue(cell)`, `.sigCurrentAction(cell, action)`, `.sigCellFinished(cell, status)`.
- Produces: `CellPanel(Qt.QWidget)` — `self.cellList: Qt.QListWidget`; `self.addCellBtn: Qt.QPushButton`; `self.positionEdit` fields (`xEdit`/`yEdit`/`zEdit`, plain `Qt.QLineEdit`, meters as float text — the crudest possible manual seeding UI, see Open Questions); method `bindOrchestrator(self, orchestrator)`; method `addCell(self, cell) -> None` (appends a `QListWidgetItem` storing the cell via `Qt.Qt.UserRole`, initial label `f"cell {id(cell)} — queued"`); slot `_onCurrentAction(cell, action)` updates that cell's row text to `"... — running: {action.name}"`; slot `_onCellFinished(cell, status)` updates to `"... — {status}"`. `self.addCellBtn.clicked` builds a `Cell(Point((x, y, z), "global"))` (imported from `acq4_automation.feature_tracking.cell`) from the three edits, calls `self.orchestrator.enqueue(cell)` and `self.addCell(cell)`.
- **(Superseded, see note above)**

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_cell_panel.py`:

```python
"""Tests for CellPanel: a manually-seeded cell queue kept in sync with the
Orchestrator's sigCurrentAction/sigCellFinished signals."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentAction = Qt.Signal(object, object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)


def test_add_cell_button_enqueues_and_lists(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.xEdit.setText("1e-3")
    panel.yEdit.setText("2e-3")
    panel.zEdit.setText("3e-3")
    panel.addCellBtn.click()

    assert len(orch.enqueued) == 1
    assert panel.cellList.count() == 1
    assert "queued" in panel.cellList.item(0).text()


def test_current_action_updates_row(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.xEdit.setText("0")
    panel.yEdit.setText("0")
    panel.zEdit.setText("0")
    panel.addCellBtn.click()
    cell = orch.enqueued[0]

    class _Action:
        name = "Patch"

    orch.sigCurrentAction.emit(cell, _Action())
    assert "running: Patch" in panel.cellList.item(0).text()


def test_cell_finished_updates_row(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)

    panel.xEdit.setText("0")
    panel.yEdit.setText("0")
    panel.zEdit.setText("0")
    panel.addCellBtn.click()
    cell = orch.enqueued[0]

    orch.sigCellFinished.emit(cell, "done")
    assert "done" in panel.cellList.item(0).text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'acq4.modules.Autopatch.cell_panel'`

- [ ] **Step 3: Implement** — create `acq4/modules/Autopatch/cell_panel.py`:

```python
"""CellPanel: Area 5's manually-seeded cell queue and its list view, kept in
sync with the Orchestrator's per-cell lifecycle signals."""
from __future__ import annotations

from coorx import Point

from acq4_automation.feature_tracking.cell import Cell
from acq4.util import Qt


class CellPanel(Qt.QWidget):
    def __init__(self):
        super().__init__()
        self._orchestrator = None
        self._rows: dict[int, Qt.QListWidgetItem] = {}

        self.cellList = Qt.QListWidget()

        self.xEdit = Qt.QLineEdit("0")
        self.yEdit = Qt.QLineEdit("0")
        self.zEdit = Qt.QLineEdit("0")
        self.addCellBtn = Qt.QPushButton("Add cell")
        self.addCellBtn.clicked.connect(self._onAddCellClicked)

        posRow = Qt.QHBoxLayout()
        for label, edit in (("x", self.xEdit), ("y", self.yEdit), ("z", self.zEdit)):
            posRow.addWidget(Qt.QLabel(label))
            posRow.addWidget(edit)
        posRow.addWidget(self.addCellBtn)

        layout = Qt.QVBoxLayout()
        layout.addLayout(posRow)
        layout.addWidget(self.cellList)
        self.setLayout(layout)

    def bindOrchestrator(self, orchestrator) -> None:
        if self._orchestrator is not None:
            Qt.disconnect(self._orchestrator.sigCurrentAction, self._onCurrentAction)
            Qt.disconnect(self._orchestrator.sigCellFinished, self._onCellFinished)
        self._orchestrator = orchestrator
        orchestrator.sigCurrentAction.connect(self._onCurrentAction)
        orchestrator.sigCellFinished.connect(self._onCellFinished)

    def _onAddCellClicked(self) -> None:
        position = Point(
            (float(self.xEdit.text()), float(self.yEdit.text()), float(self.zEdit.text())),
            "global",
        )
        cell = Cell(position)
        self._orchestrator.enqueue(cell)
        self.addCell(cell)

    def addCell(self, cell) -> None:
        item = Qt.QListWidgetItem(f"cell {id(cell)} — queued")
        item.setData(Qt.Qt.UserRole, cell)
        self.cellList.addItem(item)
        self._rows[id(cell)] = item

    def _onCurrentAction(self, cell, action) -> None:
        if cell is None:
            return
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — running: {action.name}")

    def _onCellFinished(self, cell, status: str) -> None:
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — {status}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_panel.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_panel.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add CellPanel manual cell queue driven by orchestrator signals

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 7: Per-cell executed-path timeline (Area 5)

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_cell_timeline.py`

**Interfaces:**
- Consumes: `Action.sigStateChanged(self, msg: str)`.
- Produces: `CellPanel.timelineList: Qt.QListWidget` (shown for the currently-selected cell in `cellList`); `CellPanel._timelines: dict[int, list[str]]` (cell id -> ordered list of timeline line strings, so a finished cell's timeline is preserved and redisplayed on reselect); connecting to a new action's `sigStateChanged` happens in `_onCurrentAction` (which now also disconnects from the previous action, if any, to avoid stale connections); `cellList.currentItemChanged` swaps `timelineList`'s contents to the selected cell's stored timeline.
- **Known gap (see Open Questions):** the orchestrator does not emit the action's resolved *outcome* string on a signal — only free-text `sigStateChanged` messages and, for `FsmCompositeAction`, `action.results["final_state"]` (not all Action subclasses populate `results`). This task's timeline therefore records `sigStateChanged` messages verbatim (e.g. "reached 'whole cell'" already reads as an outcome for FSM actions) rather than inventing a structured outcome field the engine doesn't expose.

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_cell_timeline.py`:

```python
"""Tests for CellPanel's per-cell executed-path timeline, built live from
Action.sigStateChanged as the orchestrator drives each cell."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentAction = Qt.Signal(object, object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)


class _FakeAction(Qt.QObject):
    sigStateChanged = Qt.Signal(object, str)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def setState(self, msg):
        self.sigStateChanged.emit(self, msg)


def test_timeline_appends_a_line_per_state_change(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addCellBtn.click()  # x/y/z default to "0"
    cell = orch.enqueued[0]

    action = _FakeAction("Patch")
    orch.sigCurrentAction.emit(cell, action)
    action.setState("driving FSM from 'approach'")
    action.setState("reached 'whole cell'")

    panel.cellList.setCurrentRow(0)
    lines = [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())]
    assert lines == [
        "Patch: driving FSM from 'approach'",
        "Patch: reached 'whole cell'",
    ]


def test_timeline_preserved_across_cell_switch(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addCellBtn.click()
    cellA = orch.enqueued[0]
    panel.xEdit.setText("1")
    panel.addCellBtn.click()
    cellB = orch.enqueued[1]

    actionA = _FakeAction("Patch")
    orch.sigCurrentAction.emit(cellA, actionA)
    actionA.setState("hello A")

    actionB = _FakeAction("Patch")
    orch.sigCurrentAction.emit(cellB, actionB)
    actionB.setState("hello B")

    panel.cellList.setCurrentRow(0)
    assert [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())] == [
        "Patch: hello A"
    ]

    panel.cellList.setCurrentRow(1)
    assert [panel.timelineList.item(i).text() for i in range(panel.timelineList.count())] == [
        "Patch: hello B"
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_timeline.py -v`
Expected: FAIL — `AttributeError: 'CellPanel' object has no attribute 'timelineList'`

- [ ] **Step 3: Implement** — modify `acq4/modules/Autopatch/cell_panel.py`. Add `self.timelineList = Qt.QListWidget()` next to `self.cellList` in `__init__` and lay both out side by side; add `self._timelines: dict[int, list[str]] = {}` and `self._currentActionConn = None`; wire `self.cellList.currentItemChanged.connect(self._onCellSelectionChanged)`. Update `addCell`/`_onCurrentAction`:

```python
    def addCell(self, cell) -> None:
        item = Qt.QListWidgetItem(f"cell {id(cell)} — queued")
        item.setData(Qt.Qt.UserRole, cell)
        self.cellList.addItem(item)
        self._rows[id(cell)] = item
        self._timelines[id(cell)] = []

    def _onCurrentAction(self, cell, action) -> None:
        if self._currentActionConn is not None:
            Qt.disconnect(*self._currentActionConn)
            self._currentActionConn = None
        if cell is None:
            return
        item = self._rows.get(id(cell))
        if item is not None:
            item.setText(f"cell {id(cell)} — running: {action.name}")

        def _onState(_action, msg, cell=cell, action=action):
            line = f"{action.name}: {msg}"
            self._timelines[id(cell)].append(line)
            if self.cellList.currentItem() is self._rows.get(id(cell)):
                self.timelineList.addItem(line)

        action.sigStateChanged.connect(_onState)
        self._currentActionConn = (action.sigStateChanged, _onState)

    def _onCellSelectionChanged(self, current, _previous) -> None:
        self.timelineList.clear()
        if current is None:
            return
        cell = current.data(Qt.Qt.UserRole)
        for line in self._timelines.get(id(cell), []):
            self.timelineList.addItem(line)
```

Update `__init__`'s layout to place `self.timelineList` beside `self.cellList` (e.g. a `Qt.QHBoxLayout` row containing both, added below `posRow`), and connect the selection signal after `self.cellList` exists:

```python
        listsRow = Qt.QHBoxLayout()
        listsRow.addWidget(self.cellList)
        listsRow.addWidget(self.timelineList)

        layout = Qt.QVBoxLayout()
        layout.addLayout(posRow)
        layout.addLayout(listsRow)
        self.setLayout(layout)

        self.cellList.currentItemChanged.connect(self._onCellSelectionChanged)
```

(replacing the earlier `layout.addWidget(self.cellList)` line from Task 6).

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_timeline.py acq4/modules/Autopatch/tests/test_cell_panel.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_timeline.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add per-cell executed-path timeline built from Action.sigStateChanged

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 8: Cell-scoped log view + live `show()` widget mount (Area 5)

**Files:**
- Modify: `acq4/modules/Autopatch/cell_panel.py`
- Test: `acq4/modules/Autopatch/tests/test_cell_log_and_show.py`

**Interfaces:**
- Consumes: `ExecutionContext.log` (the callable this panel's owner should pass into `make_context_factory(..., log=panel.appendLog)`), `Action.show() -> QWidget | None`.
- Produces: `CellPanel.logView: Qt.QPlainTextEdit` (read-only); method `appendLog(self, message: str) -> None` (appends a line — this is what gets passed as the context factory's `log=` callable so `ctx.log(...)` calls from Actions land here); `CellPanel.showContainer: Qt.QWidget` with a `Qt.QVBoxLayout` that `_onCurrentAction` swaps to `action.show()`'s widget (or clears it if `show()` returns `None`) **only when the action's cell is the currently-selected row** (mirrors the design doc's "renders in this pane when following the current cell").

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_cell_log_and_show.py`:

```python
"""Tests for CellPanel's log view (ctx.log sink) and live show()-widget mount,
both scoped to the currently-followed (selected) cell."""
import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeOrchestrator(Qt.QObject):
    sigCurrentAction = Qt.Signal(object, object)
    sigCellFinished = Qt.Signal(object, str)

    def __init__(self):
        super().__init__()
        self.enqueued = []

    def enqueue(self, cell):
        self.enqueued.append(cell)


class _FakeAction(Qt.QObject):
    sigStateChanged = Qt.Signal(object, str)

    def __init__(self, name, widget=None):
        super().__init__()
        self.name = name
        self._widget = widget

    def show(self):
        return self._widget


def test_append_log_shows_in_log_view(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    panel.appendLog("hello world")

    assert "hello world" in panel.logView.toPlainText()


def test_show_widget_mounted_for_selected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addCellBtn.click()
    cell = orch.enqueued[0]
    panel.cellList.setCurrentRow(0)

    liveWidget = Qt.QLabel("live plot")
    action = _FakeAction("Patch", widget=liveWidget)
    orch.sigCurrentAction.emit(cell, action)

    assert panel.showContainer.layout().indexOf(liveWidget) != -1


def test_show_widget_not_mounted_for_unselected_cell(qapp):
    from acq4.modules.Autopatch.cell_panel import CellPanel

    panel = CellPanel()
    orch = _FakeOrchestrator()
    panel.bindOrchestrator(orch)
    panel.addCellBtn.click()
    panel.xEdit.setText("1")
    panel.addCellBtn.click()
    cellA, cellB = orch.enqueued
    panel.cellList.setCurrentRow(0)  # follow cellA

    liveWidget = Qt.QLabel("live plot for B")
    action = _FakeAction("Patch", widget=liveWidget)
    orch.sigCurrentAction.emit(cellB, action)  # B is running, but A is selected

    assert panel.showContainer.layout().indexOf(liveWidget) == -1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_log_and_show.py -v`
Expected: FAIL — `AttributeError: 'CellPanel' object has no attribute 'logView'`

- [ ] **Step 3: Implement** — modify `acq4/modules/Autopatch/cell_panel.py`. Add to `__init__`:

```python
        self.logView = Qt.QPlainTextEdit()
        self.logView.setReadOnly(True)

        self.showContainer = Qt.QWidget()
        self.showContainer.setLayout(Qt.QVBoxLayout())
```

and lay them out (e.g. add both below `listsRow` in the outer `layout`). Add `appendLog` and extend `_onCurrentAction`:

```python
    def appendLog(self, message: str) -> None:
        self.logView.appendPlainText(message)

    def _currentSelectedCell(self):
        item = self.cellList.currentItem()
        return None if item is None else item.data(Qt.Qt.UserRole)
```

and in `_onCurrentAction`, after the existing timeline-wiring block, add:

```python
        showLayout = self.showContainer.layout()
        while showLayout.count():
            child = showLayout.takeAt(0)
            if child.widget() is not None:
                child.widget().setParent(None)
        if cell is self._currentSelectedCell():
            widget = action.show()
            if widget is not None:
                showLayout.addWidget(widget)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_cell_log_and_show.py -v`
Expected: 3 passed

- [ ] **Step 5: Full Autopatch suite regression check**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/Autopatch/cell_panel.py acq4/modules/Autopatch/tests/test_cell_log_and_show.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: add cell-scoped log view and live show()-widget mount to CellPanel

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

### Task 9: Wire the window end-to-end (Orchestrator construction on protocol load)

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py`
- Test: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1-8, plus `acq4.experiment.orchestrator.Orchestrator(protocol, manager=None, contextFactory=None)`.
- Produces: `AutopatchWindow.__init__` gains two more constructor params, `pipetteSelector=None` (production default: a real `InterfaceCombo(types=['pipette'])`; tests inject a fake `Qt.QWidget` with a `getSelectedObj()` method, avoiding the global `getManager()` call `InterfaceCombo` makes internally). `AutopatchWindow` now mounts `StatusPanel` into `area3Box`, `CellPanel` into `area5Box`, and `self.pipetteSelector` into `area4Box` alongside `ProtocolPanel`. On `ProtocolPanel.sigProtocolLoaded`, builds a fresh `Orchestrator(protocol, manager=self.manager, contextFactory=make_context_factory(self.pipetteSelector.getSelectedObj, self.manager, log=self.cellPanel.appendLog))` (using `self.manager` set in Task 2 from `module.manager`, never a fresh `getManager()` call) and calls `self.statusPanel.bindOrchestrator(orch)` + `self.cellPanel.bindOrchestrator(orch)`; stores it as `self.orchestrator`.

- [ ] **Step 1: Write the failing test** — create `acq4/modules/Autopatch/tests/test_window_integration.py`. This test uses fakes (not a real running `Manager`/real devices — see Open Questions for the config/mock-vs-fakes tradeoff) to keep it fast and headless:

```python
"""Integration test: loading a protocol builds and binds a fresh Orchestrator
to the window's StatusPanel and CellPanel."""
import json
import os

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakePipetteSelector(Qt.QWidget):
    """Stands in for InterfaceCombo so the test never triggers its internal
    getManager() call."""

    def getSelectedObj(self):
        return None


def _write_protocol(path, name):
    data = {
        "version": 1,
        "entry": "n1",
        "nodes": {"n1": {"type": "GoToNext", "params": {}}},
        "edges": [],
        "publicParams": [],
        "exceptionHandlers": {},
    }
    with open(os.path.join(path, name), "w") as fh:
        json.dump(data, fh)


def test_loading_a_protocol_builds_and_binds_an_orchestrator(qapp, tmp_path):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    _write_protocol(tmp_path, "demo.json")

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakePipetteSelector(),
    )
    win.protocolPanel.fileCombo.setCurrentText("demo.json")
    win.protocolPanel.loadSelected()

    assert win.orchestrator is not None
    assert win.orchestrator.protocol is win.protocolPanel.protocol
    # StatusPanel/CellPanel are bound: clicking Start reaches the real orchestrator.
    win.statusPanel.startBtn.click()
    win.orchestrator.wait(timeout=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v`
Expected: FAIL — `TypeError: AutopatchWindow.__init__() got an unexpected keyword argument 'pipetteSelector'`

- [ ] **Step 3: Implement** — modify `acq4/modules/Autopatch/Autopatch.py`. Add imports:

```python
from acq4.experiment.orchestrator import Orchestrator
from acq4.util.InterfaceCombo import InterfaceCombo
from .cell_panel import CellPanel
from .context_factory import make_context_factory
from .status_panel import StatusPanel
```

Replace `AutopatchWindow.__init__` (from Task 2) in full with:

```python
    def __init__(
        self,
        module: "Autopatch | None" = None,
        protocolDir: str | None = None,
        pipetteSelector=None,
    ):
        super().__init__()
        self.module = module
        self.manager = module.manager if module is not None else None
        self.setWindowTitle("Autopatch")

        self.area1Box = Qt.QGroupBox("Area 1 — Slice && region")
        self.area2Box = Qt.QGroupBox("Area 2 — Cell finding")
        self.area3Box = Qt.QGroupBox("Area 3 — Status && actions")
        self.area4Box = Qt.QGroupBox("Area 4 — Protocol && params")
        self.area5Box = Qt.QGroupBox("Area 5 — Current cell")

        for box in (self.area1Box, self.area2Box, self.area3Box, self.area4Box, self.area5Box):
            box.setLayout(Qt.QVBoxLayout())

        topRow = Qt.QHBoxLayout()
        topRow.addWidget(self.area1Box)
        topRow.addWidget(self.area2Box)

        bottomRow = Qt.QHBoxLayout()
        bottomRow.addWidget(self.area3Box)
        bottomRow.addWidget(self.area4Box)
        bottomRow.addWidget(self.area5Box)

        outer = Qt.QVBoxLayout()
        outer.addLayout(topRow)
        outer.addLayout(bottomRow)
        self.setLayout(outer)

        if protocolDir is None:
            if self.manager is None:
                raise ValueError(
                    "AutopatchWindow needs a `module` (for module.manager.configDir) "
                    "or an explicit `protocolDir`"
                )
            protocolDir = os.path.join(self.manager.configDir, "protocols", "autopatch")
        self.protocolPanel = ProtocolPanel(protocolDir=protocolDir)
        self.area4Box.layout().addWidget(self.protocolPanel)

        self.pipetteSelector = pipetteSelector if pipetteSelector is not None else InterfaceCombo(types=['pipette'])
        self.area4Box.layout().addWidget(self.pipetteSelector)

        self.statusPanel = StatusPanel()
        self.area3Box.layout().addWidget(self.statusPanel)

        self.cellPanel = CellPanel()
        self.area5Box.layout().addWidget(self.cellPanel)

        self.orchestrator = None
        self.protocolPanel.sigProtocolLoaded.connect(self._onProtocolLoaded)

    def _onProtocolLoaded(self, protocol) -> None:
        contextFactory = make_context_factory(
            pipetteGetter=self.pipetteSelector.getSelectedObj,
            manager=self.manager,
            log=self.cellPanel.appendLog,
        )
        self.orchestrator = Orchestrator(
            protocol, manager=self.manager, contextFactory=contextFactory
        )
        self.statusPanel.bindOrchestrator(self.orchestrator)
        self.cellPanel.bindOrchestrator(self.orchestrator)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -v`
Expected: 1 passed

- [ ] **Step 5: Full Autopatch suite regression check**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/ -v`
Expected: all pass, no regressions across Tasks 1-9.

- [ ] **Step 6: Register the module so it is launchable**, following the `AutomationDebug` entry — modify a config's `modules:` block (e.g. `config/mock/default.cfg`, whichever config the human uses for manual smoke-testing; do not edit `config/default.cfg`'s real-rig entries without confirming which config is the right one — see Open Questions) by adding:

```
    Autopatch:
        module: 'Autopatch'
```

This step is a manual/config change, not part of the automated test suite — confirm the target config file with the human before editing, since this plan's engine-only reading pass did not establish which config P1 should register against.

- [ ] **Step 7: Commit**

```bash
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_window_integration.py
git commit --author="Claude (claude) <noreply@anthropic.com>" -m "feat: wire Autopatch window end-to-end (protocol load builds+binds Orchestrator)

🤖 Generated with [Claude Code](https://claude.ai/code)"
```

---

## Open questions for the human

1. **RESOLVED (human decision, applied 2026-07-22):** window shows Areas 3/4/5 with a prominent status indicator; Areas 1/2 stay empty placeholders for P1 (no top-row/bottom-row redesign needed beyond that).
2. **RESOLVED (human decision, applied 2026-07-22):** manual x/y/z entry is dropped. Area 5 seeding implements BOTH (a) an "Add from target" button that captures the selected pipette's current target (`pipette.targetPosition()`) as a new `Cell` and enqueues it (mirrors `AutomationDebug`'s target-handling path), and (b) a "Scatter fake cells" demo button that enqueues 3-5 `Cell`s at random offsets near `cameraDevice.globalCenterPosition()`, for quick demos without detection. Both use `acq4_automation.feature_tracking.cell.Cell(position)` (a `coorx.Point`).
3. **RESOLVED (human decision, applied 2026-07-22):** protocol JSON storage is `<configDir>/autopatch_protocols/` (flat, not nested under `protocols/autopatch/`), resolved from `getManager().configDir` (the same base `AutomationDebug` uses for config). The protocol picker defaults to listing `*.json` there, with a file dialog fallback.
4. **RESOLVED (human decision, applied 2026-07-22):** register `Autopatch:` only in the mock config (`config/mock/...`) for now, not the real rig's `config/default.cfg`.
5. **RESOLVED (human decision, applied 2026-07-22):** P1 tests use fakes/coded protocols exclusively (no `config/mock` boot). A real-`Manager`-against-`config/mock` integration test is deferred until Area 1/2 (P2) gives the workflow something realistic to exercise end-to-end.
6. **RESOLVED (human decision, applied 2026-07-22):** `Orchestrator` now emits `sigActionFinished = Qt.Signal(object, object, str)  # cell, action, outcome` immediately after each action resolves to an outcome in `_walk` (before routing to the next node). Additive change to `acq4/experiment/orchestrator.py`, covered by `test_action_finished_signal_emitted_with_cell_action_outcome` in `acq4/experiment/tests/test_orchestrator_walk.py`. Committed as `a35079038`. Area 5's timeline (Task 7) consumes this signal directly — structured `action -> outcome` rows — instead of scraping `Action.sigStateChanged` text.
7. **RESOLVED (human decision, applied 2026-07-22):** Pause is a bare toggle (`orchestrator.pause()`/`resume()`); the richer Resume re-entry flow (§3.5: retry-vs-next-cell choice, recovery sub-plan picker) is deferred to P4 polish.
8. **RESOLVED (human decision, applied 2026-07-22):** programmatic layout confirmed for all of P1; no `.ui` file.
