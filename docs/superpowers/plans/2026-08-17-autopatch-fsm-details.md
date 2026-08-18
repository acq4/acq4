# Autopatch FSM Details — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `patch` and `reseal` a steady-state resistance plot in Area 5 — live while the FSM drives, frozen and re-readable afterwards — plus the list of pipette states the FSM actually walked, and an event log of their own on disk.

**Architecture:** `_drive_fsm` opens a `MultiPatchLogRecorder` and MultiPatch's `PlotWidget` on entry, records state transitions from the poll loop it already has, and in a `finally` inside its `log_action` block stops the recorder and retains its accumulated test-pulse analysis as a `"test_pulse_history"` payload. The frozen plot reuses the same `PlotWidget`, taught to tolerate `tp=None`. `clean` opts out of all of it.

**Tech Stack:** Python 3, PyQt (via `acq4.util.Qt`), pyqtgraph, numpy, pytest.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-17-autopatch-area5-details-widgets-design.md` §4 (the `"test_pulse_history"` row), §8's `patch`/`reseal`. This plan implements phase 3 of its §11 phasing.
- **Depends on both earlier phases.** Phase 1 supplies `ActionLogEntry.set_details`, `CellPanel`'s retention and row navigation, and the `BUILDERS` registry. Phase 2 supplies `MultiPatchLogRecorder` and `testPulseAnalysis()`. Do not start this until both have landed.
- **`clean` gets nothing** — no recorder, no plot, no payload. There is nothing an operator reads off a clean (design doc §4.5).
- **Payload contract (spec §2):** plain data only. In particular the payload must **never** hold a `PatchClampTestPulse`, which is why the `'test pulse'` and `'tp analysis'` plot modes are unavailable on a frozen plot.
- **Widgets are built on the GUI thread** via `run_in_gui_thread`; the action function runs on the orchestrator's worker thread.
- **The live plot's device connection must be queued and must be severed when the action ends** (design doc §4.5). `PatchPipetteState` connects to `sigTestPulseFinished` with an explicit `DirectConnection`, which is right for a state machine and wrong for a widget.
- **Python interpreter:** `/home/martin/.miniforge3/envs/acq4-gl/bin/python`. Run pytest as `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest`.
- **Commits:** conventional format, `--author="Martin Chase (claude) <outofculture@gmail.com>"`, footer `🤖 Generated with [Claude Code](https://claude.ai/code)`. Never `--no-verify`.

## File Structure

| File | Responsibility | Action |
| --- | --- | --- |
| `acq4/modules/MultiPatch/pipetteControl.py` | `PlotWidget.newTestPulse` tolerating `tp=None` | Modify |
| `acq4/modules/MultiPatch/tests/test_plot_widget_frozen.py` | that tolerance | Create |
| `acq4/modules/Autopatch/details_renderers.py` | the `"test_pulse_history"` builder | Modify |
| `acq4/modules/Autopatch/tests/test_details_renderers.py` | that builder | Modify |
| `acq4/experiment/actions/fsm.py` | transition capture, the recorder, the payload, the live plot | Modify |
| `acq4/experiment/tests/test_actions_fsm.py` | all of the above | Modify |

---

### Task 1: `PlotWidget.newTestPulse` tolerates `tp=None`

**Files:**
- Modify: `acq4/modules/MultiPatch/pipetteControl.py:444-472`
- Test: `acq4/modules/MultiPatch/tests/test_plot_widget_frozen.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `PlotWidget.newTestPulse(tp: PatchClampTestPulse | None, history)` accepts `None` for `tp` in every analysis mode; `PlotWidget.setFrozen(frozen: bool) -> None`, which trims the mode combo to the modes a history alone can serve.

- [ ] **Step 1: Write the failing tests**

Create `acq4/modules/MultiPatch/tests/test_plot_widget_frozen.py`:

```python
"""Tests for PlotWidget's frozen mode: plotting a retained test-pulse history
with no live PatchClampTestPulse to read a current value from.

Autopatch's Area 5 reuses this widget for a finished action's plot (design doc
§4.5, "reuse, do not reimplement"), and its retained payload deliberately holds
no PatchClampTestPulse -- so tp is None there."""
import numpy as np
import pytest

from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


def _history(count=5):
    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(1e6, 1e9, count)
    history["access_resistance"] = np.linspace(1e6, 2e7, count)
    history["baseline_current"] = np.linspace(-1e-10, 1e-10, count)
    history["baseline_potential"] = np.linspace(-0.07, -0.06, count)
    history["time_constant"] = np.linspace(1e-4, 1e-3, count)
    history["capacitance"] = np.linspace(1e-12, 5e-12, count)
    return history


@pytest.mark.parametrize(
    "mode",
    [
        "ss resistance",
        "peak resistance",
        "holding current",
        "holding potential",
        "time constant",
        "capacitance",
    ],
)
def test_analysis_modes_plot_a_history_with_no_test_pulse(qapp, mode):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode=mode)

    widget.newTestPulse(None, _history())

    assert len(widget.plot.plotItem.listDataItems()) == 1


def test_the_current_value_label_is_blank_with_no_test_pulse(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.newTestPulse(None, _history())

    assert widget.tpLabel.toPlainText() == ""


def test_an_empty_history_plots_nothing_and_does_not_raise(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.newTestPulse(None, _history(count=0))

    assert widget.plot.plotItem.listDataItems() == []


def test_test_pulse_modes_clear_rather_than_raise_with_no_test_pulse(qapp):
    # 'test pulse' and 'tp analysis' need the recording itself, which a frozen
    # payload deliberately does not retain. They must degrade, not crash.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    for mode in ("test pulse", "tp analysis"):
        widget = PlotWidget(mode=mode)
        widget.newTestPulse(None, _history())
        assert widget.plot.plotItem.listDataItems() == []


def test_set_frozen_removes_the_modes_a_history_cannot_serve(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="ss resistance")

    widget.setFrozen(True)

    items = [widget.modeCombo.itemText(i) for i in range(widget.modeCombo.count())]
    assert "test pulse" not in items
    assert "tp analysis" not in items
    assert "ss resistance" in items
    assert "capacitance" in items


def test_set_frozen_keeps_the_current_mode_selected(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    widget = PlotWidget(mode="capacitance")

    widget.setFrozen(True)

    assert widget.modeCombo.currentText() == "capacitance"
    assert widget.mode == "capacitance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/MultiPatch/tests/test_plot_widget_frozen.py -v`

Expected: FAIL — `AttributeError: 'NoneType' object has no attribute 'analysis'` in the analysis-mode tests, `'NoneType' object has no attribute 'plot'` for `tp analysis`, and `no attribute 'setFrozen'`.

- [ ] **Step 3: Make `newTestPulse` tolerate `tp=None`**

In `acq4/modules/MultiPatch/pipetteControl.py`, replace `newTestPulse` (lines 444-472) with:

```python
    def newTestPulse(self, tp: PatchClampTestPulse | None, history):
        """Update the plot from the latest test pulse and the history behind it.

        `tp` may be None, which is how Autopatch's Area 5 reuses this widget for
        a finished action: its retained payload holds the history but no
        PatchClampTestPulse, since a recording is not plain data (see
        ActionLogEntry.set_details). With no `tp` the analysis modes plot the
        history and leave the current-value label blank, and the two modes that
        need the recording itself clear instead.
        """
        if self._analysisLabel is not None:
            self.plot.plotItem.vb.removeItem(self._analysisLabel)
            self._analysisLabel = None
        if self.mode == 'test pulse':
            self.plot.clear()
            if tp is not None:
                self._plotTestPulse(tp)
        elif self.mode == 'tp analysis':
            self.plot.clear()
            if tp is not None:
                tp.plot(self.plot, label=False)
                self._analysisLabel = tp.label_for_plot(self.plot.plotItem)
        else:
            analysis_by_mode = {
                'ss resistance': ('steady_state_resistance', u'Ω'),
                'peak resistance': ('access_resistance', u'Ω'),
                'holding current': ('baseline_current', 'A'),
                'holding potential': ('baseline_potential', 'V'),
                'time constant': ('time_constant', 's'),
                'capacitance': ('capacitance', 'F'),
            }
            key, units = analysis_by_mode[self.mode]
            if len(history['event_time']) > 0:
                self.plot.plot(history['event_time'] - history['event_time'][0], history[key], clear=True)
            if tp is None:
                # No live value to report; the plot is the whole story.
                self.tpLabel.setPlainText("")
            else:
                val = tp.analysis[key]
                if val is None:
                    val = np.nan
                self.tpLabel.setPlainText(pg.siFormat(val, suffix=units))
```

- [ ] **Step 4: Add `setFrozen`**

Add after `hideHeader` in the same class:

```python
    # Modes that need the PatchClampTestPulse recording itself, rather than just
    # the analysis history. Unavailable to a caller plotting a retained history.
    _LIVE_ONLY_MODES = ('test pulse', 'tp analysis')

    def setFrozen(self, frozen: bool) -> None:
        """Restrict the mode combo to what a retained history can serve.

        Autopatch's frozen plots keep the combo visible -- re-reading a finished
        attempt through a different field is what it is for -- but must not offer
        the two modes that need a recording nobody retained.
        """
        if not frozen:
            return
        with pg.SignalBlock(self.modeCombo.currentIndexChanged, self.modeComboChanged):
            current = self.mode
            for mode in self._LIVE_ONLY_MODES:
                index = self.modeCombo.findText(mode)
                if index >= 0:
                    self.modeCombo.removeItem(index)
            self.modeCombo.setText(current)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/MultiPatch/tests -v`

Expected: PASS, 11 new tests plus every pre-existing MultiPatch test.

- [ ] **Step 6: Commit**

```bash
git add acq4/modules/MultiPatch/pipetteControl.py acq4/modules/MultiPatch/tests/test_plot_widget_frozen.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(multipatch): let PlotWidget plot a history with no live test pulse

Autopatch's Area 5 reuses this widget for a finished action's plot rather
than writing a second Rss plot (design doc §4.5). Its retained payload holds
the analysis history but no PatchClampTestPulse -- a recording is not plain
data -- so tp is None there.

With no tp, the analysis modes plot the history and blank the current-value
label, and the two modes that need the recording clear instead of raising.
setFrozen removes those two from the combo, which frozen plots keep visible:
re-reading a finished attempt through a different field is the point.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 2: The `"test_pulse_history"` renderer

**Files:**
- Modify: `acq4/modules/Autopatch/details_renderers.py`
- Test: `acq4/modules/Autopatch/tests/test_details_renderers.py`

**Interfaces:**
- Consumes: `captioned` and `BUILDERS` (phase 1, Task 2); `PlotWidget.setFrozen` and `newTestPulse(None, history)` (Task 1).
- Produces: `buildTestPulseHistory(payload)`, registered under `"test_pulse_history"`.
- Payload shape, produced by Task 4: `{"history": ndarray (TEST_PULSE_NUMPY_DTYPE), "transitions": [(time, state), ...], "entry_state": str, "reached": str | None, "log_file": str | None}`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/modules/Autopatch/tests/test_details_renderers.py`:

```python
def _tpHistory(count=5):
    import numpy as np
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(1e6, 1e9, count)
    return history


def _tpPayload(**overrides):
    payload = {
        "history": _tpHistory(),
        "transitions": [(0.0, "approach"), (1.5, "seal"), (3.0, "whole cell")],
        "entry_state": "approach",
        "reached": "whole cell",
        "log_file": "MultiPatch_004.log",
    }
    payload.update(overrides)
    return payload


def test_test_pulse_history_plots_the_retained_history(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    assert plot is not None
    assert len(plot.plot.plotItem.listDataItems()) == 1


def test_test_pulse_history_keeps_the_mode_combo_visible(qapp):
    # Re-reading a finished attempt through a different field is what the
    # dropdown is for; only the live plot hides it.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    assert not plot.modeCombo.isHidden()


def test_test_pulse_history_offers_no_live_only_modes(qapp):
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    plot = widget.findChild(PlotWidget)
    items = [plot.modeCombo.itemText(i) for i in range(plot.modeCombo.count())]
    assert "test pulse" not in items
    assert "tp analysis" not in items


def test_test_pulse_history_lists_the_state_transitions(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    transitions = widget.findChild(Qt.QListWidget)
    assert transitions is not None
    rows = [transitions.item(i).text() for i in range(transitions.count())]
    assert len(rows) == 3
    assert "approach" in rows[0]
    assert "seal" in rows[1]
    assert "whole cell" in rows[2]


def test_transition_rows_show_the_elapsed_time_from_the_first(qapp):
    # Absolute epoch timestamps are unreadable; what matters is how long the
    # FSM sat in each state.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history",
        _tpPayload(transitions=[(1000.0, "approach"), (1002.5, "seal")]),
    )

    transitions = widget.findChild(Qt.QListWidget)
    assert "0.00" in transitions.item(0).text()
    assert "2.50" in transitions.item(1).text()


def test_test_pulse_history_caption_reports_the_terminal_state_and_log(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload())

    caption = widget.layout().itemAt(0).widget().text()
    assert "approach" in caption
    assert "whole cell" in caption
    assert "MultiPatch_004.log" in caption


def test_test_pulse_history_caption_handles_never_reaching_a_terminal(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history", _tpPayload(reached=None, log_file=None)
    )

    caption = widget.layout().itemAt(0).widget().text()
    assert "approach" in caption
    assert "no terminal state" in caption


def test_test_pulse_history_tolerates_an_empty_history(qapp):
    # A patch stopped before its first test pulse landed.
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget(
        "test_pulse_history", _tpPayload(history=_tpHistory(count=0), transitions=[])
    )

    assert widget is not None


def test_test_pulse_history_tolerates_no_transitions(qapp):
    from acq4.modules.Autopatch.details_renderers import buildDetailsWidget

    widget = buildDetailsWidget("test_pulse_history", _tpPayload(transitions=[]))

    assert widget.findChild(Qt.QListWidget).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v -k test_pulse_history`

Expected: FAIL — the unknown-kind fallback returns a `QPlainTextEdit`, so `findChild(PlotWidget)` is `None`.

- [ ] **Step 3: Add the builder**

In `acq4/modules/Autopatch/details_renderers.py`, add the builder after `buildTaskResults`:

```python
def buildTestPulseHistory(payload) -> Qt.QWidget:
    """One FSM action's steady-state resistance plot beside the pipette states it
    walked.

    Reuses MultiPatch's PlotWidget rather than reimplementing the plot (design
    doc §4.5). The mode combo stays visible, unlike the live plot's: because the
    whole analysis array is retained, re-reading the same attempt through
    capacitance or holding current costs nothing. setFrozen drops the two modes
    that would need the recording itself.
    """
    # Imported here, not at module scope: pipetteControl pulls in PatchPipette
    # and the rest of the MultiPatch module's device imports, and this module is
    # imported by cell_panel at Autopatch startup.
    from acq4.modules.MultiPatch.pipetteControl import PlotWidget

    plot = PlotWidget(mode="ss resistance")
    plot.setFrozen(True)
    plot.newTestPulse(None, payload["history"])

    transitions = Qt.QListWidget()
    rows = list(payload.get("transitions", ()))
    firstTime = rows[0][0] if rows else 0.0
    for when, state in rows:
        # Elapsed rather than absolute: an epoch timestamp says nothing, and how
        # long the FSM sat in each state is what reading a failed patch needs.
        transitions.addItem(f"{when - firstTime:8.2f}s  {state}")

    split = Qt.QWidget()
    splitLayout = Qt.QHBoxLayout()
    splitLayout.setContentsMargins(0, 0, 0, 0)
    splitLayout.addWidget(plot, 2)
    splitLayout.addWidget(transitions, 1)
    split.setLayout(splitLayout)

    reached = payload.get("reached")
    caption = [
        f"entered at {payload.get('entry_state')!r}, "
        + (f"reached {reached!r}" if reached else "no terminal state reached")
    ]
    logFile = payload.get("log_file")
    if logFile:
        caption.append(f"events logged to {logFile}")
    return captioned(split, caption)
```

Register it:

```python
BUILDERS = {
    "text": buildText,
    "error": buildError,
    "image_stack": buildImageStack,
    "task_results": buildTaskResults,
    "test_pulse_history": buildTestPulseHistory,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/modules/Autopatch/tests/test_details_renderers.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add acq4/modules/Autopatch/details_renderers.py acq4/modules/Autopatch/tests/test_details_renderers.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(autopatch): render an FSM action's Rss plot and state transitions

Reuses MultiPatch's PlotWidget rather than writing a second Rss plot. The
mode combo stays visible here, unlike the live plot's: the whole analysis
array is retained, so re-reading the same attempt through capacitance or
holding current is free.

Transitions are listed as elapsed times rather than epoch timestamps --
reading a failed patch is mostly "where did it stall", and how long the FSM
sat in each state is what answers it.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 3: `_drive_fsm` records its state transitions

**Files:**
- Modify: `acq4/experiment/actions/fsm.py:23-52`
- Test: `acq4/experiment/tests/test_actions_fsm.py`

**Interfaces:**
- Consumes: `ActionLogEntry.set_details` (phase 1, Task 1).
- Produces: `_drive_fsm(ctx, name, entry_state, terminals, entry_config=None, poll_interval=0.1, record=True)`; `patch`/`reseal` accept `record_events` and `record_full_test_pulses` keyword arguments; `clean` passes `record=False`.

This task lands the transition list and the payload without the recorder, so the payload's shape and the `finally` ordering are proven before device wiring is added in Task 4.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_actions_fsm.py`:

```python
# -- details payloads -------------------------------------------------------


def _details(ctx):
    """Collect (kind, payload) from every entry this context opens."""
    seen = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: seen.append((kind, payload))

    ctx.on_log_action = hook
    return seen


def test_patch_retains_a_test_pulse_history_payload(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    patch(ctx)

    assert len(seen) == 1
    kind, payload = seen[0]
    assert kind == "test_pulse_history"
    assert payload["entry_state"] == "approach"
    assert payload["reached"] == "whole cell"


def test_the_payload_lists_every_state_the_fsm_walked(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "cell attached", "break in", "whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    patch(ctx)

    states = [state for _when, state in seen[0][1]["transitions"]]
    # The entry state first, then each change the poll loop observed --
    # including the internal hops the drive continues through.
    assert states == [
        "approach",
        "cell detect",
        "seal",
        "cell attached",
        "break in",
        "whole cell",
    ]


def test_transitions_carry_a_timestamp(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["seal", "whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    patch(ctx)

    times = [when for when, _state in seen[0][1]["transitions"]]
    assert times == sorted(times)
    assert all(isinstance(t, float) for t in times)


def test_the_payload_arrives_before_the_entry_finishes(fake_pip_factory, monkeypatch):
    # CellPanel resolves the payload to a timeline row through bookkeeping the
    # entry's finish tears down.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip)
    order = []

    def hook(action_entry):
        action_entry.on_details = lambda e, k, p: order.append("details")
        action_entry.on_finish = lambda e: order.append("finish")

    ctx.on_log_action = hook

    patch(ctx)

    assert order == ["details", "finish"]


def test_a_stopped_patch_still_retains_its_payload(fake_pip_factory, monkeypatch):
    # An interrupted attempt is exactly when an operator wants the plot.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(
        fsm_mod, "check_stop", lambda *a, **k: (_ for _ in ()).throw(Stopped("stop"))
    )
    pip = fake_pip_factory([])
    ctx = _ctx(pip)
    seen = _details(ctx)

    with pytest.raises(Stopped):
        patch(ctx)

    assert len(seen) == 1
    assert seen[0][1]["reached"] is None


def test_a_failed_patch_still_retains_its_payload(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "broken"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    with pytest.raises(BrokenPipette):
        reseal(ctx)

    assert len(seen) == 1
    assert seen[0][1]["reached"] is None
    assert "broken" in [state for _when, state in seen[0][1]["transitions"]]


def test_clean_retains_nothing(fake_pip_factory, monkeypatch):
    # There is nothing an operator reads off a clean (design doc §4.5).
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["out"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    clean(ctx)

    assert seen == []


def test_record_events_false_still_retains_the_payload(fake_pip_factory, monkeypatch):
    # Switching off the disk log is not a reason to lose the pane's plot.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    patch(ctx, record_events=False)

    assert len(seen) == 1


def test_record_kwargs_do_not_reach_set_state(fake_pip_factory, monkeypatch):
    # entry_config is forwarded to pip.setState; these two are this action's own
    # options and must not be.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])

    patch(
        _ctx(pip),
        record_events=False,
        record_full_test_pulses=False,
        autoBreakInDelay=2.0,
    )

    _state, config = pip.setState_calls[0]
    assert config == {"autoBreakInDelay": 2.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -v -k "payload or transitions or retains or record_"`

Expected: FAIL — `seen == []` everywhere, and `patch() got an unexpected keyword argument 'record_events'` for the last two.

- [ ] **Step 3: Capture transitions and set the payload in `_drive_fsm`**

In `acq4/experiment/actions/fsm.py`, add the import:

```python
import time
```

Replace `_drive_fsm` (lines 23-52) with:

```python
def _drive_fsm(
    ctx,
    name,
    entry_state,
    terminals,
    entry_config=None,
    poll_interval=0.1,
    record=True,
    record_full_test_pulses=True,
) -> str:
    """Drive the PatchPipette FSM from entry_state and return the terminal state
    it reaches. Abnormal states not in `terminals` raise (see raise_if_abnormal).

    With `record` true, this action also retains a "test_pulse_history" details
    payload for Area 5 -- the test-pulse analysis observed during the drive, and
    the pipette states it walked. `clean` passes false: there is nothing an
    operator reads off a clean (design doc §4.5).
    """
    with ctx.log_action(name) as action_entry:
        pip = ctx.pipette
        action_entry.set_status(f"driving FSM from {entry_state!r}")
        last_state = entry_state
        # (timestamp, state) for the entry state and every change the poll loop
        # observes. Reading a failed patch is mostly "where did it stall", and
        # this is what answers it; the loop already detects the changes.
        transitions = [(time.time(), entry_state)]
        reached = None
        try:
            # Fresh dict per call so no caller shares a mutable default.
            pip.setState(entry_state, **dict(entry_config or {}))
            while True:
                check_stop()
                if ctx.next_cell_requested():
                    ctx.next_cell()
                state = pip.getState().stateName
                if state in terminals:
                    action_entry.set_status(f"reached {state!r}")
                    if state != last_state:
                        transitions.append((time.time(), state))
                    reached = state
                    return state
                if state != last_state:
                    # Only on change: re-setting the same string every poll
                    # would spam the UI callback for no new information, and
                    # would hide a pipette parked in a non-terminal state
                    # (e.g. "cell attached") behind a stale row otherwise.
                    action_entry.set_status(f"now in {state!r}")
                    transitions.append((time.time(), state))
                    last_state = state
                raise_if_abnormal(state, terminals, name)
                sleep(poll_interval)
        except (Stopped, AdvanceToNextCell):
            _safe_abort(ctx)
            raise
        finally:
            # Inside the `with`, so this runs before the entry finishes -- a
            # payload set afterwards has no timeline row to attach to (see
            # ActionLogEntry.set_details). And in a finally, so a stopped,
            # abandoned, or failed attempt retains its plot too, which is
            # exactly when an operator wants to read one.
            if record:
                _setFsmDetails(action_entry, entry_state, reached, transitions)
```

`raise_if_abnormal` records the abnormal state before raising, which the tests above rely on: the state is appended by the `state != last_state` branch on the same iteration, before `raise_if_abnormal` is reached.

Add the payload helper above `_drive_fsm`:

```python
def _setFsmDetails(action_entry, entry_state, reached, transitions, recorder=None) -> None:
    """Retain this drive's Area 5 payload: the test-pulse analysis observed
    during it, and the states it walked.

    An empty history rather than None when there is no recorder, so the renderer
    has one payload shape to handle rather than two.
    """
    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    if recorder is None:
        history = np.empty(0, dtype=TEST_PULSE_NUMPY_DTYPE)
        log_file = None
    else:
        history = recorder.testPulseAnalysis()
        log_file = recorder.logFileName()
        if log_file is not None:
            log_file = os.path.basename(log_file)
    action_entry.set_details(
        "test_pulse_history",
        {
            "history": history,
            "transitions": list(transitions),
            "entry_state": entry_state,
            "reached": reached,
            "log_file": log_file,
        },
    )
```

Add its imports:

```python
import os

import numpy as np
```

- [ ] **Step 4: Give `patch` and `reseal` the new options**

Replace `patch`, `reseal`, and `clean`:

```python
def patch(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Drive approach through detection, sealing, and break-in to a resting
    terminal state.

    `record_events` and `record_full_test_pulses` are this action's own options,
    consumed here and never forwarded to pip.setState; a protocol may expose
    them to its author. See _drive_fsm for what they control.
    """
    return _drive_fsm(
        ctx,
        "Patch",
        "approach",
        # "cell attached" is not a resting state on these rigs: it exits via
        # spontaneous break-in (routed to "whole cell" by
        # spontaneousBreakInState) or spontaneous detachment (routed to
        # "fouled"), so it is an internal hop the poll continues through
        # rather than a patch outcome. autoBreakInDelay is an optional
        # wall-clock fallback that ships disabled (None) on both active rig
        # profiles.
        {"whole cell", "bath", "broken", "fouled"},
        entry_config,
        record=record_events,
        record_full_test_pulses=record_full_test_pulses,
    )


def reseal(ctx, record_events: bool = True, record_full_test_pulses: bool = True, **entry_config) -> str:
    """Reseal from whole-cell toward an outside-out patch, else fall back to
    whole cell."""
    return _drive_fsm(
        ctx,
        "Reseal",
        "reseal",
        {"outside out", "whole cell"},
        entry_config,
        record=record_events,
        record_full_test_pulses=record_full_test_pulses,
    )


def clean(ctx, **entry_config) -> str:
    """Run the pipette-cleaning cycle and return once it settles at its resting
    state (``out``).

    Records nothing: there is nothing an operator reads off a clean (design doc
    §4.5), so it gets neither a details payload nor an event log.
    """
    return _drive_fsm(ctx, "Clean Pipette", "clean", {"out"}, entry_config, record=False)
```

Update the module docstring's first line to mention the recording:

```python
"""FSM-driving actions: drive acq4's PatchPipette state machine from a declared
entry state to one of this action's declared terminal states, mapping unexpected
abnormal states to orchestration exceptions, and retaining each drive's
test-pulse analysis and state transitions for Area 5."""
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -v`

Expected: PASS, all tests in the file including every pre-existing one.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/actions/fsm.py acq4/experiment/tests/test_actions_fsm.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): retain each FSM drive's state transitions for Area 5

The poll loop already detects every state change; this records them with
timestamps and hands them to Area 5 alongside the entry and terminal states.

Set from a finally inside the log_action block: inside, so the payload
arrives before the entry finishes and still has a timeline row to attach to;
in a finally, so a stopped, abandoned, or failed attempt retains its record
too -- which is exactly when an operator wants to read one.

clean opts out entirely. patch and reseal gain record_events and
record_full_test_pulses as their own keyword options, consumed rather than
forwarded to pip.setState.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 4: The recorder and the live plot

**Files:**
- Modify: `acq4/experiment/actions/fsm.py`
- Test: `acq4/experiment/tests/test_actions_fsm.py`

**Interfaces:**
- Consumes: `MultiPatchLogRecorder(directory, pipettes=, record_full_test_pulses=)`, `.testPulseAnalysis()`, `.logFileName()`, `.stop()` (phase 2); `PlotWidget` (Task 1); `_setFsmDetails` (Task 3).
- Produces: `fsm._openRecorder(ctx, record_full_test_pulses)`, `fsm._openLivePlot(ctx, action_entry)`.

- [ ] **Step 1: Write the failing tests**

Append to `acq4/experiment/tests/test_actions_fsm.py`:

```python
# -- the recorder and the live plot -----------------------------------------


class _FakeRecorder:
    instances = []

    def __init__(self, directory, pipettes=(), record_full_test_pulses=True):
        import numpy as np
        from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

        self.directory = directory
        self.pipettes = list(pipettes)
        self.record_full_test_pulses = record_full_test_pulses
        self.stopped = False
        self._history = np.zeros(3, dtype=TEST_PULSE_NUMPY_DTYPE)
        self._history["steady_state_resistance"] = [1e6, 1e8, 1e9]
        _FakeRecorder.instances.append(self)

    def testPulseAnalysis(self):
        return self._history

    def logFileName(self):
        return "/data/cell_000/MultiPatch_004.log"

    def stop(self):
        self.stopped = True


class _FakeDir:
    pass


class _FakeManagerWithDir:
    def __init__(self):
        self.dir = _FakeDir()

    def getCurrentDir(self):
        return self.dir


@pytest.fixture
def fake_recorder(monkeypatch):
    _FakeRecorder.instances = []
    monkeypatch.setattr(fsm_mod, "MultiPatchLogRecorder", _FakeRecorder)
    # The live plot needs a real Qt widget and a real clamp device; those are
    # live-tested, so this suite stubs the plot out entirely.
    monkeypatch.setattr(fsm_mod, "_openLivePlot", lambda ctx, entry: None)
    return _FakeRecorder


def test_patch_opens_a_recorder_in_the_current_directory(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])
    manager = _FakeManagerWithDir()

    patch(_ctx(pip, manager=manager))

    assert len(fake_recorder.instances) == 1
    recorder = fake_recorder.instances[0]
    assert recorder.directory is manager.dir
    assert recorder.pipettes == [pip]
    assert recorder.record_full_test_pulses is True


def test_the_recorder_is_stopped_when_the_drive_ends(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances[0].stopped is True


def test_the_recorder_is_stopped_even_when_the_drive_raises(fake_pip_factory, monkeypatch, fake_recorder):
    # An unclosed file handle per failed patch attempt is a leak, not a nuisance.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["broken"])

    with pytest.raises(BrokenPipette):
        reseal(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances[0].stopped is True


def test_the_payload_carries_the_recorders_history(fake_pip_factory, monkeypatch, fake_recorder):
    import numpy as np

    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    seen = _details(ctx)

    patch(ctx)

    history = seen[0][1]["history"]
    assert len(history) == 3
    assert np.array_equal(history["steady_state_resistance"], [1e6, 1e8, 1e9])


def test_the_payload_names_the_log_file_without_its_path(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    seen = _details(ctx)

    patch(ctx)

    assert seen[0][1]["log_file"] == "MultiPatch_004.log"


def test_record_full_test_pulses_is_forwarded(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()), record_full_test_pulses=False)

    assert fake_recorder.instances[0].record_full_test_pulses is False


def test_record_events_false_opens_no_recorder(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()), record_events=False)

    assert fake_recorder.instances == []


def test_clean_opens_no_recorder(fake_pip_factory, monkeypatch, fake_recorder):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["out"])

    clean(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances == []


def test_a_recorder_that_will_not_open_does_not_fail_the_patch(fake_pip_factory, monkeypatch):
    # An unset storage directory must not stop the pipette from patching; the
    # attempt is the experiment, and the log is a record of it.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(fsm_mod, "_openLivePlot", lambda ctx, entry: None)

    def boom(*a, **k):
        raise OSError("no current directory")

    monkeypatch.setattr(fsm_mod, "MultiPatchLogRecorder", boom)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    logged = []
    ctx.log = logged.append
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    assert any("no current directory" in message for message in logged)
    assert len(seen) == 1  # still retains the transitions, with an empty history
    assert len(seen[0][1]["history"]) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -v -k "recorder or live_plot or log_file"`

Expected: FAIL — `AttributeError: module 'acq4.experiment.actions.fsm' has no attribute 'MultiPatchLogRecorder'` from the fixture's monkeypatch.

- [ ] **Step 3: Add the recorder and live-plot openers**

In `acq4/experiment/actions/fsm.py`, add the imports:

```python
from acq4.util import Qt
from acq4.util.multipatch_log_recorder import MultiPatchLogRecorder
from acq4.util.task import Stopped, check_stop, run_in_gui_thread, sleep
```

(the existing `from acq4.util.task import Stopped, check_stop, sleep` line is replaced by the last one above)

Add both openers above `_drive_fsm`:

```python
def _openRecorder(ctx, record_full_test_pulses: bool):
    """A recorder writing this drive's events into the current storage
    directory, or None if one could not be opened.

    Never raises: the patch attempt is the experiment and the log is a record of
    it, so an unset storage directory or a full disk must not stop a pipette
    from patching. The reason goes to the cell's log instead.
    """
    try:
        return MultiPatchLogRecorder(
            ctx.manager.getCurrentDir(),
            pipettes=(ctx.pipette,),
            record_full_test_pulses=record_full_test_pulses,
        )
    except Exception as exc:
        ctx.log(f"could not start event recording: {exc}")
        return None


def _openLivePlot(ctx, action_entry) -> object | None:
    """Mount a live steady-state resistance plot for this drive, returning a
    zero-argument teardown to call when it ends, or None if there is no clamp to
    plot from.

    Rss over time is the measurement an operator watches to judge whether a seal
    is forming, so it is what Area 5 shows while the FSM drives (design doc
    §4.5). Reuses MultiPatch's PlotWidget rather than reimplementing it.

    Built through run_in_gui_thread because this runs on the orchestrator's
    worker thread and a widget must not be constructed off the GUI thread.
    """
    clamp = getattr(ctx.pipette, "clampDevice", None)
    if clamp is None:
        return None

    def build():
        # Imported here: pipetteControl pulls in the MultiPatch module's device
        # imports, and acq4.experiment must stay importable without them.
        from acq4.modules.MultiPatch.pipetteControl import PlotWidget

        widget = PlotWidget(mode="ss resistance")
        # Autopatch picks the mode; the operator does not need the combo while
        # an action is driving (design doc §4.5). The frozen plot shows it.
        widget.hideHeader()
        return widget

    widget = run_in_gui_thread(build)

    def onTestPulse(_device, testPulse):
        widget.newTestPulse(testPulse, clamp.testPulseHistory())

    # Default (queued) connection deliberately: PatchPipetteState connects to
    # this same signal with an explicit DirectConnection, which is correct for a
    # state machine and wrong for a widget -- it would mutate the plot from the
    # clamp's thread.
    clamp.sigTestPulseFinished.connect(onTestPulse)
    action_entry.set_details_widget(widget)

    def teardown():
        # A live connection from a device signal into a widget the panel has
        # moved on from is the cross-module reference neither Autopatch's widget
        # -tree teardown nor unbindOrchestrator reaches (design doc §4.5).
        Qt.disconnect(clamp.sigTestPulseFinished, onTestPulse)

    return teardown
```

- [ ] **Step 4: Wire them into `_drive_fsm`**

In `_drive_fsm`, open both immediately after `action_entry.set_status(f"driving FSM from {entry_state!r}")`:

```python
        recorder = _openRecorder(ctx, record_full_test_pulses) if record else None
        teardownPlot = _openLivePlot(ctx, action_entry) if record else None
```

and replace the `finally` block with:

```python
        finally:
            # Inside the `with`, so this runs before the entry finishes -- a
            # payload set afterwards has no timeline row to attach to (see
            # ActionLogEntry.set_details). And in a finally, so a stopped,
            # abandoned, or failed attempt retains its plot too, which is
            # exactly when an operator wants to read one.
            if teardownPlot is not None:
                teardownPlot()
            if recorder is not None:
                recorder.stop()
            if record:
                _setFsmDetails(
                    action_entry, entry_state, reached, transitions, recorder
                )
```

`recorder.stop()` runs before `_setFsmDetails` deliberately: the payload names the log file, and the file has to be flushed and closed before anything is told where to find it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests/test_actions_fsm.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 6: Commit**

```bash
git add acq4/experiment/actions/fsm.py acq4/experiment/tests/test_actions_fsm.py
git commit --author="Martin Chase (claude) <outofculture@gmail.com>" -m "$(cat <<'EOF'
feat(experiment): give patch and reseal a live Rss plot and an event log

Rss over time is what an operator watches to judge whether a seal is forming,
so it is what Area 5 shows while the FSM drives, reusing MultiPatch's
PlotWidget. The device connection is queued deliberately -- PatchPipetteState
uses a DirectConnection on the same signal, right for a state machine and
wrong for a widget -- and is severed when the drive ends, since a live device
signal into an abandoned widget is the cross-module reference neither
Autopatch's teardown nor unbindOrchestrator reaches.

The recorder writes the attempt's events into the cell's storage directory,
and its accumulated analysis becomes the frozen plot's data. Opening it never
raises: the attempt is the experiment and the log is a record of it, so an
unset storage directory must not stop a pipette from patching.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

---

### Task 5: Verify the phase, and the whole feature

**Files:** none modified.

- [ ] **Step 1: Run every suite the three phases touched**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -m pytest acq4/experiment/tests acq4/modules/Autopatch/tests acq4/modules/MultiPatch/tests acq4/util/tests acq4/devices/PatchPipette/tests acq4/filetypes/tests tools/autopatch_analysis/tests -v`

Expected: PASS with no failures, errors, or new warnings. Output must be pristine.

- [ ] **Step 2: Confirm the Autopatch module still imports**

Run: `/home/martin/.miniforge3/envs/acq4-gl/bin/python -c "import acq4.modules.Autopatch.Autopatch as m; import acq4.modules.Autopatch.details_renderers as r; print(sorted(r.BUILDERS))"`

Expected: `['error', 'image_stack', 'task_results', 'test_pulse_history', 'text']` with no import error. This also proves `details_renderers` does not drag MultiPatch's device imports in at module scope.

- [ ] **Step 3: Write the live-testing checklist**

The device wiring in `patch`, `reseal`, and `run_task` is exercised by live testing rather than the headless suite (`actions/device.py`'s module docstring). Report a checklist for the operator covering:

1. A `patch` action's live Rss plot updating in Area 5 while the FSM drives, with the mode combo hidden.
2. The same action's row, reselected after it finishes, showing the frozen plot with the combo visible and switchable through `capacitance` and `holding current`.
3. The state-transition list matching what MultiPatch's own state display showed during the attempt.
4. A `MultiPatch_*.log` appearing in the cell's directory, opening in the MultiPatch log viewer, and — with MultiPatch also recording — both logs capturing full test pulses simultaneously.
5. A `cellfie` row showing the cell's stack, opened at the plane the cell sits on.
6. A `run_task` row showing one curve per sweep.
7. Switching between cells and between rows without the pane going stale or blank.

- [ ] **Step 4: Report**

State which tasks landed, the final test count, and the live-testing checklist from Step 3.

---

## Self-Review Notes

**Spec coverage for phase 3.** §4's `"test_pulse_history"` row and the hidden-live/shown-frozen combo decision → Tasks 1–2. §8's `patch`/`reseal` paragraph: the recorder → Task 4; `PlotWidget` construction, `hideHeader`, and the queued connection → Task 4; the transition list from the existing poll loop → Task 3; the `finally` inside the `with` → Tasks 3–4; "the payload's history comes from the recorder, not `clampDevice.testPulseHistory()`" → Task 4, and asserted by phase 2's `test_test_pulse_analysis_is_unaffected_by_a_device_history_reset`. §9's thread rules → Task 4's `run_in_gui_thread` and queued connection.

**Type consistency across phases.** The payload keys Task 2's renderer reads (`history`, `transitions`, `entry_state`, `reached`, `log_file`) are exactly those Task 3's `_setFsmDetails` writes. `testPulseAnalysis()` and `logFileName()` are the names phase 2 Task 4 and Task 2 produce.

**Deliberate asymmetry worth noting.** The live plot reads `clamp.testPulseHistory()` (the device's own, which is what a live view of "now" should show), while the frozen payload reads `recorder.testPulseAnalysis()` (immune to the mid-patch resets). Task 4's code comments say so at both sites.

**Not covered by headless tests, by design:** `_openLivePlot` itself, which is stubbed out in `fake_recorder`. It needs a real clamp device and a real `PlotWidget` against live hardware, and it is item 1 of Step 3's checklist.
