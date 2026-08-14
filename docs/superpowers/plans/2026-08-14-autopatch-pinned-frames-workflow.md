# Autopatch pinned-frames workflow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sequence the Camera module's pinned frames into the start of a slice — clear the old set behind a prompt, instruct the operator to pin a fresh one — and make the Camera module a precondition of the Autopatch module rather than a possibility every consumer checks for.

**Architecture:** A new `ReferenceImagery` QObject beside the two Area 1 mirrors owns the pinned-frame workflow and publishes one instruction string. `StatusPanel`'s single instruction slot becomes three named, priority-ordered slots so its three writers cannot retract each other. The `Autopatch` module opens the Camera module at startup, and `_cameraWindow()` raises `HelpfulException` instead of returning `None`.

**Tech Stack:** Python 3, PyQt5 via `acq4.util.Qt`, pyqtgraph, pytest.

Spec: `docs/superpowers/specs/2026-08-14-autopatch-pinned-frames-workflow-design.md`

## Global Constraints

- **Python interpreter is `/home/martin/.miniforge3/envs/acq4-gl/bin/python`.** Not `acq4-torch`, which lacks gentletask 0.7.0.
- **Verify you are in the right checkout before committing.** Run `git rev-parse --show-toplevel` and `git branch --show-current`. Expected toplevel: `/home/martin/src/acq4/acq4/.claude/worktrees/minirig-v1-move-names-cd821b`. Expected branch: `claude/autopatch-ui-work-45342d`. A previous implementer committed into the main checkout on the wrong branch; do not repeat it.
- **Commit messages use the project footer.** Use a heredoc, never a single-line `-m`, so the footer survives:
  ```
  🤖 Generated with [Claude Code](https://claude.ai/code)
  ```
  and commit with `--author="Martin Chase (claude) <outofculture@gmail.com>"` and `-c user.email=outofculture@gmail.com`.
- **Test output must be pristine.** No warnings introduced, no skips added.
- **Mutation proof is mandatory for any test whose assertion is about absence** (`== ""`, `is None`, "not called", "still pinned", "unchanged"). Apply the defect, run the test, and **record the line number the failure occurred at**. A mutation that fails at a different line than the assertion has proven nothing. A mutation that does *not* fail is a finding: report it rather than moving on.
- **Every comment's rationale is a claim.** Do not write a justification you have not verified. Six false comments were corrected on a previous branch in this module.
- **Do not use `weakref` to prove a disconnect.** Assert Qt's own `receivers(signal)`. Twice a mandated "remove the disconnect" mutation passed because a nearby `= None` had already broken the cycle refcounting sees.

---

## File Structure

| File | Responsibility | Task |
| --- | --- | --- |
| `acq4/modules/Autopatch/tests/test_window_integration.py` | `_FakeManager` grows a Camera module, matching the guarantee production now makes | 1, 2, 3, 6 |
| `acq4/modules/Autopatch/Autopatch.py` | Delete the mirror warning and modules-changed wiring; open Camera at startup; raise; wire `ReferenceImagery` | 2, 3, 4, 6 |
| `acq4/modules/Autopatch/status_panel.py` | Named instruction slots | 4 |
| `acq4/modules/Autopatch/tests/test_status_panel.py` | Slot priority and isolation | 4 |
| `acq4/modules/Autopatch/reference_imagery.py` | **New.** The pinned-frames workflow: resolve, prompt-and-clear, publish an instruction | 5 |
| `acq4/modules/Autopatch/tests/test_reference_imagery.py` | **New.** Headless unit tests against a fake ImagingCtrl | 5 |
| `acq4/modules/Autopatch/tests/test_teardown.py` | `release()` reached from `teardown()` | 6 |

---

## Task 1: Make the fakes tell production's truth

`_FakeManager` carries no `listModules`/`getModule`, so `_cameraModuleWindow`'s `except Exception: return None` is what 82 `newSlice()`-calling tests actually exercise. Task 3 deletes that fallback. This task makes the default fake supply a Camera module **first**, so the suite is green at every commit.

This is the same defect class as P2b's `restore_depth` and `_FakeCamera`: a fake that reports a state production guarantees cannot happen.

**Files:**
- Modify: `acq4/modules/Autopatch/tests/test_window_integration.py` (`_FakeManager`, ~line 162)

**Interfaces:**
- Consumes: nothing.
- Produces: `_FakeManager.listModules() -> list[str]` returning `["Camera"]`; `_FakeManager.getModule(name) -> SimpleNamespace` with `.window()`; `_FakeManager.cameraWindow` — the fake Camera window, with `getInterfaceForDevice(name) -> SimpleNamespace(imagingCtrl=...)`, `addItem(item, **kwds)`, `removeItem(item)`, and `drawn: list`. `_FakeManager.pinnedFrameSource` — the `_FakePinnedFrameSource` its interface hands out.

- [ ] **Step 1: Read the two existing helpers you are generalising**

Read `_FakePinnedFrameSource` (~line 1770) and `_withPinnedFrameSource` (~line 1782) in `acq4/modules/Autopatch/tests/test_window_integration.py`. The new default must offer the same surface, so tests already calling `_withPinnedFrameSource(win)` keep working when it overrides the default.

- [ ] **Step 2: Write the failing test**

Add to `acq4/modules/Autopatch/tests/test_window_integration.py`, next to the other camera-window-getter tests (~line 2286):

```python
def test_the_default_fake_manager_offers_a_camera_module(win):
    # Production guarantees a Camera module: the Autopatch module opens one at
    # startup. A fake that reports none does not reproduce production, and the
    # None-returning path it stands for is deleted in this branch.
    window = win._cameraWindow()

    assert window is not None
    assert window.getInterfaceForDevice("cam").imagingCtrl is not None
```

- [ ] **Step 3: Run it and watch it fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_the_default_fake_manager_offers_a_camera_module -v
```

Expected: FAIL — `assert None is not None`, because `_FakeManager` has no `listModules` and `_cameraModuleWindow` swallows the `AttributeError`.

- [ ] **Step 4: Move `_FakePinnedFrameSource` above `_FakeManager`**

`_FakeManager` is defined at ~line 162 and `_FakePinnedFrameSource` at ~line 1770. Python resolves the name at call time, not definition time, so this move is not strictly required — but the file reads top-down and a fake referenced by the manager belongs above it. Cut the class and paste it immediately above `_FAKE_FOLDER_TYPES`/`_FakeManager`:

```python
class _FakePinnedFrameSource(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl."""

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self):
        super().__init__()
        self.pinnedFrames = []
```

- [ ] **Step 5: Give `_FakeManager` a Camera module**

Replace `_FakeManager`'s docstring and `__init__`, and add the three methods. The existing `getCurrentDir`/`setCurrentDir`/`folderTypesConfig` are unchanged:

```python
class _FakeManager(Qt.QObject):
    """Stands in for Manager: backed by a real DirHandle (on tmp_path) so
    create_data_dir's mkdir/setInfo calls land on an actual directory, the way
    they would through the real Manager AutopatchWindow otherwise gets from
    its module.

    Offers a Camera module by default, because the Autopatch module opens one
    at startup and everything in Area 1 is written to assume it. A fake that
    reported none would stand for a state production rules out.

    A QObject because the real Manager is one. Nothing in Autopatch listens to
    sigModulesChanged any more, but the real Manager still carries it.
    """

    sigModulesChanged = Qt.Signal()

    def __init__(self, root_dir):
        super().__init__()
        self._current_dir = root_dir
        self.drawn = []
        self.pinnedFrameSource = _FakePinnedFrameSource()
        self.cameraWindow = SimpleNamespace(
            getInterfaceForDevice=lambda name: SimpleNamespace(
                imagingCtrl=self.pinnedFrameSource
            ),
            addItem=lambda item, **kwds: self.drawn.append(item),
            removeItem=self.drawn.remove,
        )

    def listModules(self):
        return ["Camera", "Data Manager"]

    def getModule(self, name):
        if name != "Camera":
            raise KeyError(name)
        return SimpleNamespace(window=lambda: self.cameraWindow)

    def getCurrentDir(self):
        return self._current_dir

    def setCurrentDir(self, d):
        self._current_dir = d

    def folderTypesConfig(self):
        return _FOLDER_TYPES
```

- [ ] **Step 6: Run the new test**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_the_default_fake_manager_offers_a_camera_module -v
```

Expected: PASS.

- [ ] **Step 7: Run the whole Autopatch suite and fix the fallout**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ -q
```

Tests that previously ran with **no** Camera module now run with one. Expect failures in tests asserting nothing was mirrored or drawn. For each failure decide, and say which in the commit message:

- A test whose *subject* is the absent Camera module (`test_ticking_the_mirror_with_no_camera_module_open_says_so`, `test_the_message_goes_once_a_camera_module_is_open`, `test_the_camera_window_getter_does_not_load_the_camera_module`) — **leave failing and note it**; Tasks 2 and 3 delete them. Do not delete them here; a task that deletes a test whose feature still exists is unreviewable.
- Any other test — the fake changed under it, so **fix the test**, not the fake.

If more than three tests outside that set fail, stop and report rather than patching broadly.

- [ ] **Step 8: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/tests/test_window_integration.py
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
test(autopatch): give the fake manager a Camera module

Production guarantees one from startup, so a fake reporting none stands for
a state that cannot happen -- and it is what the deleted None-returning
getter path was actually exercising across 82 tests.

Three tests about the absent-Camera-module case are left failing; they are
deleted with the features they cover in the next two commits.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 2: Delete the mirror warning and the modules-changed wiring

The "no Camera module is open" message and the whole `sigModulesChanged` apparatus exist to handle a Camera module arriving late. Task 3 makes that impossible. Delete them first, so Task 3 never has to reason about dead branches.

`_setRegionInstruction` **survives** — `_onRegionsEdited` uses it for `RegionTooLarge`. Only `_regionInstruction`, the bool that arbitrated between it and `newSlice()`, goes; Task 4 replaces that arbitration with slots.

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`__init__` ~177 and ~193-201, `_onMirrorToggled` ~277, `_onModulesChanged` ~296, `_setRegionInstruction` ~356, `teardown` ~985)
- Modify: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: Task 1's `_FakeManager`.
- Produces: `AutopatchWindow._setRegionInstruction(text: str) -> None`, now writing straight through with no ownership flag. `AutopatchWindow._onModulesChanged` no longer exists.

- [ ] **Step 1: Delete the tests of the deleted features, and rewrite the two that survive**

Delete these four from `acq4/modules/Autopatch/tests/test_window_integration.py` outright — each tests a feature this task removes. The first two cover the warning; the second two cover `_onModulesChanged` re-resolving a Camera module that arrives late, which cannot happen once the Autopatch module opens one at startup:

- `test_ticking_the_mirror_with_no_camera_module_open_says_so` (~line 2340)
- `test_the_message_goes_once_a_camera_module_is_open` (~line 2348)
- `test_outlines_appear_when_the_camera_module_is_opened_after_the_tick` (~line 2217)
- `test_pinned_frames_bind_when_the_camera_module_is_opened_after_the_slice` (~line 2245)

Then delete the `_cameraModuleAppears` helper (~line 2200) — with those two tests gone its remaining caller is `test_no_outlines_appear_when_the_checkbox_is_not_ticked`, which this step rewrites to stop using it. Confirm with `grep -n "_cameraModuleAppears" acq4/modules/Autopatch/tests/test_window_integration.py` returning nothing when you are done.

Rewrite `test_no_outlines_appear_when_the_checkbox_is_not_ticked`, whose point survives — an unticked box mirrors nothing — but whose mechanism (announcing a module) does not:

```python
def test_no_outlines_appear_when_the_checkbox_is_not_ticked(win):
    # A region is not a reason to start mirroring something the operator never
    # asked to mirror.
    win.newSlice()

    win.addRegionHere()

    assert win.manager.drawn == []
```

**Do not replace them with a test asserting the message is gone.** `instruction() == ""` is the band's state before anything ever wrote to it, so such a test passes against code that never had the feature — the "asserting a default is asserting nothing" trap in the Global Constraints. Deleting a feature does not require a test that it stays deleted.

Keep `test_unticking_the_mirror_retracts_the_message` but rewrite it, since there is no longer a message to retract — it now asserts something that can actually fail:

```python
def test_unticking_the_mirror_takes_the_outlines_down(win):
    win.newSlice()
    win.addRegionHere()
    win.regionPanel.mirrorCheck.setChecked(True)
    assert win.manager.drawn != []

    win.regionPanel.mirrorCheck.setChecked(False)

    assert win.manager.drawn == []
```

- [ ] **Step 2: Run the rewritten test and watch it pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -k "unticking_the_mirror" -v
```

Expected: PASS. It asserts outlines appear and then go, which Task 1's fake Camera window already makes reachable — this rewrite is not driving new behaviour, it is replacing an assertion about a deleted message with one about the mirror's actual job.

Prove it can fail before moving on: temporarily comment out `self._cameraMirror.setEnabled(enabled)` in `_onMirrorToggled`, run it, **record the failing line number**, and restore.

- [ ] **Step 3: Strip `_onMirrorToggled` to its job**

Replace `_onMirrorToggled` (~line 277) entirely:

```python
    def _onMirrorToggled(self, enabled: bool) -> None:
        """Turn the outline mirror on or off."""
        self._cameraMirror.setEnabled(enabled)
```

- [ ] **Step 4: Delete `_onModulesChanged` and its wiring**

Delete the whole `_onModulesChanged` method (~line 296 through the line before `_onRegionsEdited`).

In `__init__` (~line 193), delete these six lines including the comment:

```python
        if self.manager is not None:
            # Both Area 1 mirrors resolve the Camera module through
            # ... (comment continues)
            self.manager.sigModulesChanged.connect(self._onModulesChanged)
```

In `teardown()` (~line 985), delete the disconnect and rewrite the comment above it, which explains an ordering that no longer has two sides:

```python
            # In a finally because these are the releases that reach *outside*
            # this window: a raise while stopping the orchestrator would
            # otherwise leave the Camera module holding this session's outlines
            # and its imaging control still connected to a dead mirror.
            self._pinnedFrameMirror.unbind()
            self._cameraMirror.clear()
            self._releaseCellPositionConnections()
            self._progressOverlay.release()
```

- [ ] **Step 5: Drop the ownership flag**

Delete `self._regionInstruction = False` from `__init__` (~line 177), and replace `_setRegionInstruction` (~line 356):

```python
    def _setRegionInstruction(self, text: str) -> None:
        """Put Area 1's guidance in Area 3's band, or retract it.

        Area 1 has one guidance slot: a later message replaces an earlier one.
        """
        self.statusPanel.setInstruction(text)
```

Note this is deliberately a half-step: it writes through to the single-slot band and would now clobber `newSlice()`'s storage message. Task 4 closes that, and no test between here and there covers the collision.

- [ ] **Step 6: Delete the two remaining flag reads**

Search for the flag and remove both assignments left in `newSlice()`:

```bash
grep -n "_regionInstruction" acq4/modules/Autopatch/Autopatch.py
```

Expected after editing: no matches. In `newSlice()` these two lines go (~512 and ~524), each with the comment above it that explains the flag:

```python
            self._regionInstruction = False
```

- [ ] **Step 7: Run the suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ -q
```

Expected: all pass except `test_the_camera_window_getter_does_not_load_the_camera_module`, which Task 3 deletes.

- [ ] **Step 8: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_window_integration.py
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
refactor(autopatch): drop the late-Camera-module apparatus

The mirror's "no Camera module is open" warning, _onModulesChanged and its
sigModulesChanged wiring all served a module arriving after the window. The
Autopatch module now opens one at startup, so that cannot happen.

_setRegionInstruction survives for its RegionTooLarge caller; only the
_regionInstruction ownership bool goes, and named slots replace what it did.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 3: The Camera module is a precondition

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`_cameraModuleWindow` ~247, `Autopatch.__init__` ~1006)
- Modify: `acq4/modules/Autopatch/tests/test_window_integration.py`

**Interfaces:**
- Consumes: Task 1's `_FakeManager`.
- Produces: `AutopatchWindow._cameraModuleWindow(manager)` raises `HelpfulException` instead of returning `None`; `AutopatchWindow._cameraWindow()` likewise. Callers no longer check for `None`.

- [ ] **Step 1: Write the failing tests**

Replace `test_the_camera_window_getter_does_not_load_the_camera_module` (~line 2306) with:

```python
def test_the_camera_window_getter_raises_when_the_module_is_closed(win):
    # The Autopatch module opens the Camera module at startup. One closed
    # afterwards is an error, not a state to degrade into -- a blank Area 1
    # with regions being drawn over nothing is worse than a raise.
    win.manager.listModules = lambda: ["Data Manager"]

    with pytest.raises(HelpfulException, match="Camera"):
        win._cameraWindow()


def test_the_camera_window_getter_raises_when_the_module_has_no_window(win):
    win.manager.getModule = lambda name: SimpleNamespace(window=lambda: None)

    with pytest.raises(HelpfulException, match="Camera"):
        win._cameraWindow()
```

Add the import at the top of the file if absent:

```python
from acq4.util.HelpfulException import HelpfulException
```

- [ ] **Step 2: Run them and watch them fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -k "camera_window_getter" -v
```

Expected: both FAIL with `DID NOT RAISE`.

- [ ] **Step 3: Make the getter raise**

Replace `_cameraModuleWindow` (~line 247):

```python
    @staticmethod
    def _cameraModuleWindow(manager):
        """The Camera module's window under `manager`.

        Raises rather than answering None: the Autopatch module opens the
        Camera module at startup (see Autopatch.__init__), so a missing one
        means it was closed underneath a running session. Degrading quietly
        would leave Area 1 blank while the operator went on drawing regions
        over nothing and the survey went on imaging tiles they could not see.

        HelpfulException rather than RuntimeError because this is acq4's
        operator-facing error type -- the same one create_data_dir raises for
        an unset storage directory -- and it reaches the error dialog reading
        as an instruction rather than as a crash.

        Static, taking the manager as an argument, so that the Camera mirror
        can be handed a getter that holds no reference to this window -- see
        where it is constructed.
        """
        if manager is None:
            raise HelpfulException(
                "Autopatch needs a Manager to find the Camera module."
            )
        if "Camera" not in manager.listModules():
            raise HelpfulException(
                "The Camera module is not open. Autopatch opens it at startup "
                "and needs it for reference imagery; reopen it and try again."
            )
        window = manager.getModule("Camera").window()
        if window is None:
            raise HelpfulException("The Camera module has no window.")
        return window
```

- [ ] **Step 4: Run them and watch them pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -k "camera_window_getter" -v
```

Expected: PASS.

- [ ] **Step 5: Open the Camera module at startup**

In `Autopatch.__init__` (~line 1006), open it before the window is built, so the window may assume it:

```python
    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        if Autopatch._instance is not None:
            Autopatch._instance.ui.raise_()
            Autopatch._instance.ui.activateWindow()
            Qt.QTimer.singleShot(0, self.quit)
            return
        Autopatch._instance = self
        # Before the window, which assumes it: Area 1 mirrors the Camera
        # module's pinned frames and puts region outlines back into its view,
        # and getModule() loads a module that is not already open. Making it
        # this module's responsibility is what lets every consumer downstream
        # treat a missing Camera module as an error rather than a case.
        manager.getModule("Camera")
        self.ui = AutopatchWindow(self)
        manager.declareInterface(name, ["autopatchModule"], self)
        self.ui.show()
```

- [ ] **Step 6: Mutation proof**

Remove the `if "Camera" not in manager.listModules():` block from `_cameraModuleWindow`. Run:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_the_camera_window_getter_raises_when_the_module_is_closed -v
```

Expected: FAIL. **Record the line number of the failure** and confirm it is the `pytest.raises` line, not an incidental `KeyError` from the fake's `getModule`. Restore the block.

- [ ] **Step 7: Run the suite**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ -q
```

Expected: all pass. If a test fails because it constructs a window with `manager=None`, that window never calls the getter unless a mirror is used — fix the test by giving it a manager, not by restoring the `None` return.

- [ ] **Step 8: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/test_window_integration.py
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
feat(autopatch): open the Camera module at startup and require it

The Autopatch module opens Camera before building its window, so Area 1 can
assume the imagery it mirrors exists. A module closed afterwards raises
HelpfulException instead of leaving Area 1 blank while regions are drawn
over nothing.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 4: Named instruction slots

Three writers share Area 3's band: `storage` (`newSlice`), `region` (`_onRegionsEdited`'s `RegionTooLarge`), and — from Task 6 — `imagery`. They are not mutually exclusive: `create_data_dir` can fail with the previous slice still installed.

**Files:**
- Modify: `acq4/modules/Autopatch/status_panel.py` (~line 41, ~195-230)
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`_setRegionInstruction`, `newSlice`)
- Modify: `acq4/modules/Autopatch/tests/test_status_panel.py` (~535-600)

**Interfaces:**
- Consumes: Task 2's flag-free `_setRegionInstruction`.
- Produces: `StatusPanel.setInstruction(source: str, text: str) -> None` — `""` clears that source only. `StatusPanel.instruction() -> str` unchanged: the text now showing. `StatusPanel.clearInstruction()` is **gone**. Valid sources are the module constant `INSTRUCTION_SOURCES = ("storage", "region", "imagery")`, highest priority first.

- [ ] **Step 1: Write the failing tests**

Add to `acq4/modules/Autopatch/tests/test_status_panel.py`, after `test_the_instruction_comes_back_once_the_error_clears`:

```python
def test_a_higher_priority_source_wins_the_band(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    panel.setInstruction("imagery", "Pin reference frames.")
    panel.setInstruction("storage", "Storage directory has not been set.")

    assert panel.instruction() == "Storage directory has not been set."


def test_clearing_one_source_does_not_erase_another(qapp):
    # The property the whole change exists for. newSlice() can fail at
    # create_data_dir with the previous slice still installed, so the storage
    # message and the imagery instruction can want the band at the same time,
    # and whichever cleared last must not take the other down with it.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("imagery", "Pin reference frames.")
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel.setInstruction("storage", "")

    assert panel.instruction() == "Pin reference frames."


def test_a_lower_priority_source_does_not_displace_a_higher_one(qapp):
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()
    panel.setInstruction("storage", "Storage directory has not been set.")

    panel.setInstruction("imagery", "Pin reference frames.")

    assert panel.instruction() == "Storage directory has not been set."


def test_an_unknown_source_is_a_programming_error(qapp):
    # A typo'd source would otherwise write into a slot nothing ever renders,
    # failing silently and looking exactly like a band that was not updated.
    from acq4.modules.Autopatch.status_panel import StatusPanel

    panel = StatusPanel()

    with pytest.raises(ValueError, match="pinned"):
        panel.setInstruction("pinned", "Pin reference frames.")
```

Add `import pytest` at the top of the file if absent.

Then update the five existing instruction tests (~535-600) to the new signature: `panel.setInstruction("storage", "Storage directory has not been set.")`, and in `test_clearing_an_instruction_empties_the_band` replace `panel.clearInstruction()` with `panel.setInstruction("storage", "")`.

- [ ] **Step 2: Run them and watch them fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v
```

Expected: the four new tests FAIL with `TypeError: setInstruction() takes 2 positional arguments but 3 were given`; the five updated ones fail the same way.

- [ ] **Step 3: Add the slots**

In `acq4/modules/Autopatch/status_panel.py`, add above `class StatusPanel`:

```python
# Area 3's band carries one instruction at a time, but three independent
# writers can each have something to say: an unchosen storage directory, a
# region edit refused for being too large, and a slice with no reference
# imagery pinned. They are not mutually exclusive -- newSlice() can fail at
# create_data_dir with the previous slice still installed -- so each holds its
# own slot and the first non-empty one in this order renders.
#
# storage first: New slice could not complete at all. region next: a refused
# edit answers something the operator did a moment ago. imagery last: a
# standing condition that will still hold once they have read the other two.
INSTRUCTION_SOURCES = ("storage", "region", "imagery")
```

Replace the `self._instruction = ""` line in `__init__` (~line 41), keeping the comment above it:

```python
        self._instructions = {source: "" for source in INSTRUCTION_SOURCES}
```

- [ ] **Step 4: Replace the three methods**

Replace `setInstruction`, `clearInstruction` and `instruction` (~lines 195-213):

```python
    def setInstruction(self, source: str, text: str) -> None:
        """Show operator guidance in the band -- what to do, not what broke.

        `text` of "" retracts this source's message and only this source's:
        the writers cannot see each other's conditions, so one deciding the
        band is now empty would be speaking for the other two.

        An instruction is deliberately not a RunErrorRecord: no traceback, no
        Copy, and no Show in log, because no run happened and there is nothing
        in the log to show.
        """
        if source not in self._instructions:
            raise ValueError(
                f"{source!r} is not an instruction source; "
                f"expected one of {INSTRUCTION_SOURCES}"
            )
        self._instructions[source] = text
        self._updateErrorBand()

    def instruction(self) -> str:
        """The guidance currently showing, or an empty string."""
        for source in INSTRUCTION_SOURCES:
            if self._instructions[source]:
                return self._instructions[source]
        return ""
```

Replace the two `self._instruction` reads in `_updateErrorBand` (~lines 227-228):

```python
        record = self._lastError
        showing = self.instruction()
        if record is not None:
            self.instructionLabel.setText(f"{record.exc_type}: {record.exc_message}")
        else:
            self.instructionLabel.setText(showing)
        self.instructionLabel.setVisible(record is not None or bool(showing))
        self.showInLogBtn.setVisible(record is not None)
```

- [ ] **Step 5: Run the panel tests**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py -v
```

Expected: all PASS.

- [ ] **Step 6: Update the two window call sites**

In `acq4/modules/Autopatch/Autopatch.py`, `_setRegionInstruction`:

```python
    def _setRegionInstruction(self, text: str) -> None:
        """Put Area 1's guidance in Area 3's band, or retract it.

        Area 1 has one guidance slot: a later message replaces an earlier one.
        """
        self.statusPanel.setInstruction("region", text)
```

In `newSlice()`, the storage handler (~line 513) — the comment above it referring to the deleted flag must go too:

```python
        except HelpfulException as exc:
            # Guidance, not a failure report: the operator has not chosen a
            # storage directory, and Area 3's band is where instructions go.
            # Narrowed to HelpfulException so a genuine programming error (a
            # missing manager, say) propagates instead of being reported as
            # storage guidance.
            self.statusPanel.setInstruction("storage", str(exc))
            return
```

and the success path (~line 526), whose blanket `clearInstruction()` becomes a single-slot clear:

```python
        # Whichever handler filled the band, what it was about went with the
        # tissue just discarded. The storage slot alone: this is the condition
        # New slice has just resolved, and the imagery slot is recomputed from
        # state moments later by ReferenceImagery.
        self.statusPanel.setInstruction("storage", "")
        self.statusPanel.setInstruction("region", "")
```

- [ ] **Step 7: Restore the test Task 2 had to delete**

Task 2 removed the `_regionInstruction` ownership bool, which broke `test_a_refused_edit_does_not_erase_the_storage_instruction` — a landed test covering exactly the property this task's slots restore. Task 2 deleted it rather than patch around a collision it was told not to fix. **Put it back verbatim**, in `acq4/modules/Autopatch/tests/test_window_integration.py`, next to the other refused-edit tests:

```python
def test_a_refused_edit_does_not_erase_the_storage_instruction(win):
    """Area 3's band has two Area 1 writers with different conditions, and
    neither can see the other's. A region edit retracting its own refusal must
    not also retract newSlice()'s "choose a storage directory", which is still
    just as true as it was."""
    from acq4.util.HelpfulException import HelpfulException

    win.addRegionHere()  # a slice, without going through create_data_dir

    def boom(*a, **k):
        raise HelpfulException("Storage directory has not been set.")

    win.manager.getCurrentDir = boom
    win.newSlice()
    assert "Storage directory" in win.statusPanel.instruction()

    win.regionPanel.sigRegionsChanged.emit([RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)])

    assert "Storage directory" in win.statusPanel.instruction()
```

Run it:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py::test_a_refused_edit_does_not_erase_the_storage_instruction -v
```

Expected: PASS, because `storage` outranks `region` and clearing the `region` slot no longer touches the `storage` one. If it fails, the slots are wrong — this test is the reason they exist.

- [ ] **Step 8: Mutation proof**

In `setInstruction`, replace `self._instructions[source] = text` with `self._instructions = {s: "" for s in INSTRUCTION_SOURCES}; self._instructions[source] = text` — the single-slot behaviour this task replaces. Run:

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_status_panel.py::test_clearing_one_source_does_not_erase_another -v
```

Expected: FAIL. **Record the failing line number** and confirm it is the final `assert`. Restore.

- [ ] **Step 9: Run the suite and commit**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ -q
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/status_panel.py acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
refactor(autopatch): give Area 3's band named instruction slots

Three writers share one band and cannot see each other's conditions, so a
writer clearing it was speaking for the others. Each now holds its own slot
and the highest-priority non-empty one renders.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 5: `ReferenceImagery`

Headless and unwired. Task 6 mounts it.

**Files:**
- Create: `acq4/modules/Autopatch/reference_imagery.py`
- Create: `acq4/modules/Autopatch/tests/test_reference_imagery.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ReferenceImagery(imagingCtrlGetter, prompt=None)` with `beginSlice() -> None`, `rebind() -> None`, `instruction() -> str`, `release() -> None`, and `sigInstructionChanged = Qt.Signal(str)` carrying the new text. Module constant `PIN_FRAMES_INSTRUCTION: str`.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/Autopatch/tests/test_reference_imagery.py`:

```python
"""Tests for ReferenceImagery: the pinned-frames workflow that starts a slice."""
from __future__ import annotations

import pytest

from acq4.util import Qt
from acq4.util.HelpfulException import HelpfulException


class _FakeImagingCtrl(Qt.QObject):
    """Stands in for the Camera module's ImagingCtrl.

    clearPinnedFrames() genuinely empties the list and emits, because the real
    one does (via removePinnedFrame): a fake that skipped either would hide a
    missing recompute in the code under test.
    """

    sigPinnedFramesChanged = Qt.Signal()

    def __init__(self, frames=()):
        super().__init__()
        self.pinnedFrames = list(frames)

    def clearPinnedFrames(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()

    def pin(self, frame="frame"):
        self.pinnedFrames.append(frame)
        self.sigPinnedFramesChanged.emit()

    def unpinAll(self):
        self.pinnedFrames = []
        self.sigPinnedFramesChanged.emit()


def _imagery(source, answer=True):
    from acq4.modules.Autopatch.reference_imagery import ReferenceImagery

    asked = []

    def prompt(text):
        asked.append(text)
        return answer

    return ReferenceImagery(lambda: source, prompt=prompt), asked


def test_nothing_pinned_means_no_prompt(qapp):
    source = _FakeImagingCtrl()
    imagery, asked = _imagery(source)

    imagery.beginSlice()

    assert asked == []


def test_a_yes_clears_the_pinned_frames(qapp):
    source = _FakeImagingCtrl(["a", "b"])
    imagery, asked = _imagery(source, answer=True)

    imagery.beginSlice()

    assert len(asked) == 1
    assert source.pinnedFrames == []


def test_a_no_leaves_the_pinned_frames(qapp):
    source = _FakeImagingCtrl(["a", "b"])
    imagery, asked = _imagery(source, answer=False)

    imagery.beginSlice()

    assert len(asked) == 1
    assert source.pinnedFrames == ["a", "b"]


def test_an_empty_slice_asks_for_frames(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    imagery.beginSlice()

    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION


def test_there_is_no_instruction_before_a_slice(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    assert imagery.instruction() == ""


def test_pinning_a_frame_retracts_the_instruction(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)
    imagery.beginSlice()

    source.pin()

    assert imagery.instruction() == ""


def test_unpinning_the_last_frame_brings_it_back(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    assert imagery.instruction() == ""

    source.unpinAll()

    assert imagery.instruction() == PIN_FRAMES_INSTRUCTION


def test_the_signal_carries_only_real_changes(qapp):
    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    seen = []
    imagery.sigInstructionChanged.connect(seen.append)

    source.pin("b")

    assert seen == []


def test_the_signal_reports_the_new_text(qapp):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    source = _FakeImagingCtrl(["a"])
    imagery, _ = _imagery(source, answer=False)
    imagery.beginSlice()
    seen = []
    imagery.sigInstructionChanged.connect(seen.append)

    source.unpinAll()

    assert seen == [PIN_FRAMES_INSTRUCTION]


def test_a_closed_camera_module_propagates(qapp):
    from acq4.modules.Autopatch.reference_imagery import ReferenceImagery

    def getter():
        raise HelpfulException("The Camera module is not open.")

    imagery = ReferenceImagery(getter, prompt=lambda text: True)

    with pytest.raises(HelpfulException, match="Camera"):
        imagery.beginSlice()


def test_release_disconnects_from_the_source(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)
    imagery.beginSlice()
    assert source.receivers(source.sigPinnedFramesChanged) == 1

    imagery.release()

    assert source.receivers(source.sigPinnedFramesChanged) == 0


def test_rebinding_does_not_stack_connections(qapp):
    source = _FakeImagingCtrl()
    imagery, _ = _imagery(source)

    imagery.rebind()
    imagery.rebind()

    assert source.receivers(source.sigPinnedFramesChanged) == 1
```

- [ ] **Step 2: Run them and watch them fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_reference_imagery.py -v
```

Expected: every test FAILS at collection or import with `ModuleNotFoundError: acq4.modules.Autopatch.reference_imagery`.

- [ ] **Step 3: Write the module**

Create `acq4/modules/Autopatch/reference_imagery.py`:

```python
"""ReferenceImagery: the pinned-frames workflow that opens a slice -- clear the
previous slice's frames, then ask the operator to pin a fresh set."""
from __future__ import annotations

from acq4.util import Qt

PIN_FRAMES_INSTRUCTION = (
    "Pin reference frames of this slice in the Camera module."
)

_CLEAR_PROMPT = (
    "Clear the pinned frames from the previous slice?\n\n"
    "They are imagery of tissue that is no longer under the objective, and "
    "regions for this slice will be drawn over them."
)


def _askToClear(text: str) -> bool:
    """Default prompt: the same confirmation ImagingCtrl uses for its own
    Clear button, so clearing frames asks the same way wherever it starts."""
    answer = Qt.QMessageBox.question(
        None, "Clear pinned frames?", text,
        Qt.QMessageBox.Ok | Qt.QMessageBox.Cancel,
    )
    return answer == Qt.QMessageBox.Ok


class ReferenceImagery(Qt.QObject):
    """Sequences the Camera module's pinned frames into the start of a slice.

    A QObject, unlike the plain PinnedFrameMirror/CameraMirror classes beside
    it, because something listens to it: Area 3's band re-renders whenever the
    pinned set changes.

    The wait for a fresh set is advisory. Nothing here disables a control or
    blocks a run -- the band says what to do and the operator decides.
    """

    # The instruction this component wants shown, or "". Carries the text so a
    # listener need not call back to ask.
    sigInstructionChanged = Qt.Signal(str)

    def __init__(self, imagingCtrlGetter, prompt=None):
        super().__init__()
        self._getter = imagingCtrlGetter
        self._prompt = prompt if prompt is not None else _askToClear
        self._source = None
        self._instruction = ""
        # No slice yet, and the instruction is about a slice that has none of
        # its own imagery -- not about the window having just opened.
        self._sliceActive = False

    def beginSlice(self) -> None:
        """New slice's entry point: bind, offer to clear, then recompute.

        Whatever the getter raises propagates. A Camera module closed after
        startup is an error rather than a state to degrade into, and the
        operator sees acq4's error dialog -- deliberately unlike the storage
        slot beside it in the band, which is caught and rendered as guidance
        because an unset storage directory is a thing not yet done.
        """
        self._sliceActive = True
        self.rebind()
        if self._source.pinnedFrames and self._prompt(_CLEAR_PROMPT):
            # Emits sigPinnedFramesChanged, so the recompute below is
            # belt-and-braces rather than the only path.
            self._source.clearPinnedFrames()
        self._refresh()

    def rebind(self) -> None:
        """Re-resolve the imaging control and move the subscription to it.

        Re-resolved per slice because the operator may have changed the
        selected camera since the last one.
        """
        self._disconnect()
        self._source = self._getter()
        self._source.sigPinnedFramesChanged.connect(self._refresh)
        self._refresh()

    def instruction(self) -> str:
        """The guidance this component wants shown, or ""."""
        return self._instruction

    def release(self) -> None:
        """Stop listening. Teardown's call.

        Tolerant of a source Qt has already destroyed, exactly as
        PinnedFrameMirror.unbind() is: Qt.disconnect swallows a dead
        connection's RuntimeError, but the signal is read off the source
        before it can be handed over, and that read raises through a wrapper
        whose C++ object is gone. A raise here would abandon the rest of
        AutopatchWindow.teardown().
        """
        self._disconnect()
        self._sliceActive = False

    def _disconnect(self) -> None:
        source, self._source = self._source, None
        if source is not None:
            try:
                Qt.disconnect(source.sigPinnedFramesChanged, self._refresh)
            except RuntimeError:
                pass

    def _refresh(self) -> None:
        """Recompute the instruction from current state, announcing a change.

        A pure function of state rather than of the event that got us here, so
        pinning the first frame and unpinning the last both fall out without
        either being handled: the band shows the instruction exactly while a
        slice has no reference imagery.
        """
        text = ""
        if self._sliceActive and self._source is not None:
            if not self._source.pinnedFrames:
                text = PIN_FRAMES_INSTRUCTION
        if text != self._instruction:
            self._instruction = text
            self.sigInstructionChanged.emit(text)
```

- [ ] **Step 4: Run them and watch them pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_reference_imagery.py -v
```

Expected: all PASS.

- [ ] **Step 5: Mutation proofs**

Three, each restored before the next:

1. In `_refresh`, replace `if text != self._instruction:` with `if True:`. Run `test_the_signal_carries_only_real_changes`. Expected FAIL at its `assert seen == []`. **Record the line.**
2. In `beginSlice`, drop the `self._source.pinnedFrames and` guard so it always prompts. Run `test_nothing_pinned_means_no_prompt`. Expected FAIL at `assert asked == []`. **Record the line.**
3. In `_disconnect`, delete the `Qt.disconnect(...)` call, leaving the `source, self._source = self._source, None` line. Run `test_release_disconnects_from_the_source`. Expected FAIL at the `receivers(...) == 0` assertion. **Record the line.** This is the mutation that has silently passed twice before on this module when written with weakrefs; if it passes here, stop and report.

- [ ] **Step 6: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/reference_imagery.py acq4/modules/Autopatch/tests/test_reference_imagery.py
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
feat(autopatch): add the pinned-frames workflow

ReferenceImagery offers to clear the previous slice's frames and publishes
an instruction while a slice has no reference imagery. The instruction is a
pure function of state, so pinning the first frame and unpinning the last
need no handling of their own.

Unwired; the window mounts it next.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 6: Mount it in the window

**Files:**
- Modify: `acq4/modules/Autopatch/Autopatch.py` (`__init__`, `_startSlice`, `newSlice`, `teardown`)
- Modify: `acq4/modules/Autopatch/tests/test_window_integration.py`
- Modify: `acq4/modules/Autopatch/tests/test_teardown.py`

**Interfaces:**
- Consumes: Task 5's `ReferenceImagery`; Task 4's `setInstruction(source, text)`; Task 1's `_FakeManager.pinnedFrameSource`.
- Produces: `AutopatchWindow._referenceImagery`; `AutopatchWindow._imagingCtrl()` returning the selected camera's `ImagingCtrl`.

- [ ] **Step 1: Write the failing tests**

Add to `acq4/modules/Autopatch/tests/test_window_integration.py`, near the other pinned-frame tests:

```python
def test_new_slice_offers_to_clear_the_pinned_frames(win, monkeypatch):
    win.manager.pinnedFrameSource.pinnedFrames = ["old"]
    asked = []
    monkeypatch.setattr(
        win._referenceImagery, "_prompt", lambda text: asked.append(text) or True
    )

    win.newSlice()

    assert len(asked) == 1
    assert win.manager.pinnedFrameSource.pinnedFrames == []


def test_declining_leaves_the_pinned_frames(win, monkeypatch):
    win.manager.pinnedFrameSource.pinnedFrames = ["old"]
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: False)

    win.newSlice()

    assert win.manager.pinnedFrameSource.pinnedFrames == ["old"]


def test_a_slice_with_no_imagery_asks_for_frames(win, monkeypatch):
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)

    win.newSlice()

    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION


def test_pinning_a_frame_clears_the_band(win, monkeypatch):
    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)
    win.newSlice()

    win.manager.pinnedFrameSource.pinnedFrames.append("fresh")
    win.manager.pinnedFrameSource.sigPinnedFramesChanged.emit()

    assert win.statusPanel.instruction() == ""


def test_a_storage_failure_outranks_the_imagery_instruction(win, monkeypatch):
    # Both slots filled at once, which is reachable because create_data_dir can
    # fail with the previous slice still installed.
    from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION

    monkeypatch.setattr(win._referenceImagery, "_prompt", lambda text: True)
    win.newSlice()
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION

    def boom(manager, level):
        raise HelpfulException("Storage directory has not been set.")

    monkeypatch.setattr(
        "acq4.modules.Autopatch.Autopatch.create_data_dir", boom
    )
    win.newSlice()

    assert "Storage directory" in win.statusPanel.instruction()
```

Add to `acq4/modules/Autopatch/tests/test_teardown.py`:

```python
def test_teardown_releases_the_reference_imagery(win):
    win.newSlice()
    source = win.manager.pinnedFrameSource
    assert source.receivers(source.sigPinnedFramesChanged) > 0

    win.teardown()

    assert source.receivers(source.sigPinnedFramesChanged) == 0
```

Read the top of `test_teardown.py` first and follow whatever window fixture it already uses; if it builds windows itself rather than via a `win` fixture, match that.

- [ ] **Step 2: Run them and watch them fail**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_window_integration.py -k "pinned_frames or asks_for_frames or clears_the_band or outranks" acq4/modules/Autopatch/tests/test_teardown.py -v
```

Expected: FAIL with `AttributeError: 'AutopatchWindow' object has no attribute '_referenceImagery'`.

- [ ] **Step 3: Construct it**

In `AutopatchWindow.__init__`, immediately after `self._pinnedFrameMirror = PinnedFrameMirror(self.regionPanel.view)` (~line 119):

```python
        self._referenceImagery = ReferenceImagery(self._imagingCtrl)
        self._referenceImagery.sigInstructionChanged.connect(
            self._onImageryInstruction
        )
```

Add the import beside the other panel imports:

```python
from .reference_imagery import ReferenceImagery
```

- [ ] **Step 4: Add the resolver and the band handler**

Add both methods next to `_bindPinnedFrames`:

```python
    def _imagingCtrl(self):
        """The selected camera's imaging control in the Camera module.

        Raises rather than answering None, for the same reason _cameraWindow
        does: a Camera module without an interface for the camera Autopatch is
        driving cannot show the operator what they are outlining.
        """
        window = self._cameraWindow()
        camera = self.cameraSelector.getSelectedObj()
        try:
            return window.getInterfaceForDevice(camera.name()).imagingCtrl
        except (KeyError, AttributeError):
            raise HelpfulException(
                f"The Camera module has no imaging interface for "
                f"{camera.name()!r}."
            )

    def _onImageryInstruction(self, text: str) -> None:
        self.statusPanel.setInstruction("imagery", text)
```

- [ ] **Step 5: Rebind per slice, and begin last**

In `_startSlice()`, beside the existing `self._bindPinnedFrames(camera)` (~line 438):

```python
        self._bindPinnedFrames(camera)
        # Re-resolved per slice for the same reason the mirror is: the operator
        # may have changed the selected camera since the last one.
        self._referenceImagery.rebind()
```

At the very end of `newSlice()`, after `self._refreshSurveyStats()`:

```python
        # Last, and deliberately: the prompt inside is modal, a modal dialog
        # re-enters the Qt event loop, and every queued slot dispatches inside
        # it -- including the sigCellFinished from the cell still in flight on
        # the tissue this click just discarded, whose suppression assumes it
        # lands outside a half-completed New slice.
        self._referenceImagery.beginSlice()
```

- [ ] **Step 6: Release in teardown**

In `teardown()`'s `finally`, beside the other outward-reaching releases:

```python
            self._pinnedFrameMirror.unbind()
            self._referenceImagery.release()
            self._cameraMirror.clear()
```

- [ ] **Step 7: Update the two tests this task changes the answer for**

This task makes every successful `newSlice()` put `PIN_FRAMES_INSTRUCTION` in the band, because the default fake pins no frames. Two landed tests assert the band is *empty* after one, and they are this task's to own — the plan's rule is that the task changing a behaviour owns every site that reads it.

Both become stronger, not weaker. `storage` and `region` both outrank `imagery`, so seeing the imagery text is proof the higher slot is empty — a better assertion than `== ""`, which could not tell an empty slot from an empty band.

In `test_the_storage_message_goes_once_a_directory_is_chosen` (~line 1480), replace the final assertion:

```python
    win.manager.getCurrentDir = original
    win.newSlice()

    # storage outranks imagery, so the imagery instruction showing is proof the
    # storage slot is empty -- not merely that the band is.
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION
```

In `test_the_next_good_edit_retracts_the_refusal` (~line 2077), replace the first of the two final assertions the same way:

```python
    win.regionPanel.sigRegionsChanged.emit([RectRegion(1.0e-3, 2.0e-3, 1.4e-3, 2.1e-3)])

    # region outranks imagery: the imagery instruction showing proves the
    # refusal was retracted.
    assert win.statusPanel.instruction() == PIN_FRAMES_INSTRUCTION
    assert len(win.slice.regions) == 1
```

Add the import at the top of the test file:

```python
from acq4.modules.Autopatch.reference_imagery import PIN_FRAMES_INSTRUCTION
```

- [ ] **Step 8: Run them and watch them pass**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ -q
```

Expected: all PASS. If any *other* test asserts an empty band after `newSlice()`, it is the same case — fix it the same way and name it in the commit message. If more than these two turn up, stop and report; the plan expected exactly two.

- [ ] **Step 9: Mutation proofs**

Two, restored between:

1. Move `self._referenceImagery.beginSlice()` from the end of `newSlice()` to immediately after `if not self._startSlice(dirHandle=dirHandle): return`. Run the full Autopatch suite. **Record whether anything fails.** If nothing does, that is the finding to report: the ordering is a reasoned safeguard with no test able to distinguish it, and it should be recorded as such in the PR rather than presented as covered.
2. Delete `self._referenceImagery.release()` from `teardown()`. Run `test_teardown_releases_the_reference_imagery`. Expected FAIL at the `receivers(...) == 0` assertion. **Record the line.**

- [ ] **Step 10: Commit**

```bash
git rev-parse --show-toplevel && git branch --show-current
git add acq4/modules/Autopatch/Autopatch.py acq4/modules/Autopatch/tests/
git -c user.email=outofculture@gmail.com commit --author="Martin Chase (claude) <outofculture@gmail.com>" -F - <<'EOF'
feat(autopatch): run the pinned-frames workflow from New slice

New slice offers to clear the previous slice's frames and Area 3's band asks
for a fresh set until one is pinned. beginSlice() goes last in newSlice()
because its prompt is modal and would otherwise re-enter the event loop
mid-transaction.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
```

---

## Task 7: Whole-branch verification and the PR

**Files:** none changed.

- [ ] **Step 1: Autopatch and experiment suites**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/ acq4/experiment/ -q
```

Expected: all pass, output pristine. Record the count.

- [ ] **Step 2: Whole repo**

```bash
/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest -q
```

Expected: no new failures against the branch point. Known pre-existing and **not** to be fixed here: `acq4/devices/Stage/tests/test_mockstage_move.py` aborts the process intermittently when run alone.

- [ ] **Step 3: Confirm the branch carries only this work**

```bash
git log --oneline fd8aff832..HEAD
```

Expected: the six task commits and nothing else. A commit from another session means the shared checkout leaked; the fix is a fresh branch off the last good commit, never a force-move.

- [ ] **Step 4: Check no dead references survive**

```bash
grep -rn "_regionInstruction\|_onModulesChanged\|clearInstruction" acq4/
```

Expected: no matches.

- [ ] **Step 5: Open the PR**

Base `_reviewed` on `origin/acq4`. The body must state plainly:

- **The live GUI smoke test has not been run**, and specifically that `manager.getModule("Camera")` from inside `Autopatch.__init__` re-enters `Manager`'s module loading and is **assumed, not verified**. If it misbehaves, the fallback is `AutopatchWindow`'s first `showEvent`.
- That a rig whose Camera module is named something other than `"Camera"` now gets a `HelpfulException` where it previously got a blank Area 1.
- Every mutation-proof result, **including the failing line numbers**, and any mutation that did not fail — particularly Task 6's ordering mutation, which may well not be detectable by any test.
- The `_FakeManager` change and why it is the more honest fake.

---

## Self-Review

**Spec coverage.** §1 advisory-only → no gating exists in any task. §1b → Tasks 2 (warning, `_onModulesChanged`) and 3 (startup open, raise). §2 `ReferenceImagery` and its two seams → Task 5. §3 New slice sequence and prompt-last → Task 6 Steps 5, 8. §4 slots, priority, the `region` writer, the single-slot clear on success → Task 4. §5 threading (nothing to do — single-threaded) and `release()` → Tasks 5, 6. §6 testing: honest fake → Task 5 Step 1; slot isolation → Task 4; window integration → Task 6; `_FakeManager` → Task 1; mutation discipline → Global Constraints and every task's proof step. §7 open items are out of scope by the spec's own statement.

**Type consistency.** `setInstruction(source, text)` is defined in Task 4 and called with `"region"`/`"storage"` there and `"imagery"` in Task 6. `INSTRUCTION_SOURCES` is the same tuple in both. `ReferenceImagery(imagingCtrlGetter, prompt=None)` is constructed in Task 6 exactly as defined in Task 5, with `_imagingCtrl` matching the `getter()` signature. `PIN_FRAMES_INSTRUCTION` is imported by name in Tasks 5 and 6. `_FakeManager.pinnedFrameSource` is produced in Task 1 and consumed in Task 6.

**Gaps this review found and fixed.** (1) Task 4 originally left `newSlice()`'s success path clearing only `storage`, stranding a `region` message from before the tissue was discarded — it now clears both. (2) Task 1's Step 7 originally said "fix any failing test"; it now names the three tests that must be left failing, because a task that deletes a test whose feature still exists cannot be reviewed on its own.

**Two more found in the pre-flight scan, after the plan was first committed.** (3) Task 6 changes what `instruction()` returns after every successful `newSlice()`, breaking two landed tests the plan never mentioned; Task 6 Step 7 now owns them, and the replacement assertions are stronger than the ones they replace — `storage` and `region` both outrank `imagery`, so the imagery text showing proves the higher slot is empty. (4) Task 2 originally mandated a test asserting `instruction() == ""`, which is the band's state before any feature existed; it is deleted rather than replaced.

**One risk the plan cannot remove.** Task 6's prompt-last ordering may have no test that can distinguish it — its mutation step is written to treat that as a finding to report rather than a step to pass.
