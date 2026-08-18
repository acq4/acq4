"""Tests for the plain-function FSM actions (patch, reseal, clean): drive the
PatchPipette FSM to a declared terminal state via the shared fake pipette."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, BrokenPipette, Fouled
from acq4.experiment.actions import fsm as fsm_mod
from acq4.experiment.actions.fsm import patch, reseal, clean


def _ctx(pip, **kwargs):
    return ExecutionContext(pipette=pip, **kwargs)


def _entry_names(ctx):
    names = []
    ctx.on_log_action = lambda action_entry: names.append(action_entry.name)
    return names


# -- entry states -----------------------------------------------------------


def test_patch_enters_at_approach(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    patch(_ctx(pip))
    assert pip.setState_calls[0][0] == "approach"


def test_reseal_enters_at_reseal(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    reseal(_ctx(pip))
    assert pip.setState_calls[0][0] == "reseal"


def test_clean_enters_at_clean(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    clean(_ctx(pip))
    assert pip.setState_calls[0][0] == "clean"


# -- reaching declared terminals ---------------------------------------------


def test_patch_reaches_whole_cell(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"


def test_patch_passes_through_cell_attached_to_whole_cell(fake_pip_factory, monkeypatch):
    # Auto-break-in always follows "cell attached" on these rigs, so it is an
    # internal hop, not a patch terminal -- the poll must continue through it
    # and patch() must report the outcome it actually settles at.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "cell attached", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"


def test_patch_on_broken_returns_broken(fake_pip_factory, monkeypatch):
    # broken IS a declared Patch terminal -> routes as an outcome, not an exception.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "broken"])
    assert patch(_ctx(pip)) == "broken"


def test_reseal_reaches_outside_out(fake_pip_factory):
    pip = fake_pip_factory(["outside out"])
    assert reseal(_ctx(pip)) == "outside out"


def test_clean_reaches_out(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    assert clean(_ctx(pip)) == "out"


# -- abnormal-state mapping ---------------------------------------------------


def test_reseal_on_broken_raises_broken_pipette(fake_pip_factory, monkeypatch):
    # broken is NOT a declared Reseal terminal -> mapped to BrokenPipette.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["reseal", "broken"])
    with pytest.raises(BrokenPipette):
        reseal(_ctx(pip))


def test_reseal_on_fouled_raises_fouled(fake_pip_factory, monkeypatch):
    # fouled is NOT a declared Reseal terminal -> the shared raise_if_abnormal
    # helper maps it to Fouled (the class only special-cased "broken" and would
    # have polled forever here).
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["reseal", "fouled"])
    with pytest.raises(Fouled):
        reseal(_ctx(pip))


def test_clean_on_broken_raises_broken_pipette(fake_pip_factory, monkeypatch):
    # broken is NOT a declared Clean terminal ({"out"}) -> mapped to BrokenPipette.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["clean", "broken"])
    with pytest.raises(BrokenPipette):
        clean(_ctx(pip))


def test_clean_on_fouled_raises_fouled(fake_pip_factory, monkeypatch):
    # fouled is NOT a declared Clean terminal ({"out"}) -> mapped to Fouled.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["clean", "fouled"])
    with pytest.raises(Fouled):
        clean(_ctx(pip))


# -- entry_config -------------------------------------------------------------


def test_entry_config_reaches_set_state(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    reseal(_ctx(pip), resealTimeout=30)
    state, config = pip.setState_calls[0]
    assert state == "reseal"
    assert config == {"resealTimeout": 30}


def test_entry_config_not_shared_between_calls(fake_pip_factory):
    pip1 = fake_pip_factory(["whole cell"])
    reseal(_ctx(pip1), resealTimeout=30)
    config1 = pip1.setState_calls[0][1]

    pip2 = fake_pip_factory(["whole cell"])
    reseal(_ctx(pip2))
    config2 = pip2.setState_calls[0][1]

    assert config2 == {}
    assert config2 is not config1


# -- stop mid-poll -------------------------------------------------------------


def test_stopped_mid_poll_propagates_and_triggers_safe_abort(fake_pip_factory, monkeypatch):
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)

    calls = {"n": 0}

    def fake_check_stop():
        calls["n"] += 1
        if calls["n"] > 1:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(fsm_mod, "check_stop", fake_check_stop)

    with pytest.raises(Stopped):
        patch(_ctx(pip))

    # The FSM's own declared fallback state was told to stop, mirroring
    # MultiPatch's Cancel button -- not a hard-coded holding state.
    assert len(pip.stop_calls) == 1
    assert pip.stop_calls[0][1] == "orchestration abort"
    # wait=True makes the abort synchronous: the state has actually unwound
    # by the time _safe_abort returns, so the orchestrator doesn't move on
    # while the pipette is still mid-transition.
    assert pip.stop_calls[0][2] is True


def test_safe_abort_cleanup_failure_propagates_instead_of_stopped(fake_pip_factory, monkeypatch):
    """_safe_abort is called from inside _drive_fsm's `except (Stopped,
    AdvanceToNextCell)` clause. If it raises (e.g. the state job's stop()
    itself fails -- the pipette didn't respond), Python's own exception
    semantics mean that new exception replaces the Stopped that triggered the
    abort on its way out of patch() -- there is no `except Stopped` upstream
    that could catch it instead."""
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)

    def failing_stop(reason=None, wait=False):
        raise RuntimeError("pipette did not respond to stop")

    original_get_state = pip.getState

    def get_state_with_failing_stop():
        job = original_get_state()
        job.stop = failing_stop
        return job

    pip.getState = get_state_with_failing_stop

    calls = {"n": 0}

    def fake_check_stop():
        calls["n"] += 1
        if calls["n"] > 1:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(fsm_mod, "check_stop", fake_check_stop)

    with pytest.raises(RuntimeError, match="did not respond"):
        patch(_ctx(pip))


def test_patch_success_does_not_call_stop(fake_pip_factory, monkeypatch):
    # Reaching a terminal state normally (no Stopped) must leave the pipette
    # alone -- a successful patch() ends by *staying* in its terminal state
    # (e.g. "whole cell"), not by having that state's job stopped.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"
    assert pip.stop_calls == []


def test_reseal_on_broken_does_not_call_stop(fake_pip_factory, monkeypatch):
    # An abnormal state mapped to an OrchestrationError (here BrokenPipette)
    # propagates untouched -- it is not a cooperative Stopped, so no abort.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["reseal", "broken"])
    with pytest.raises(BrokenPipette):
        reseal(_ctx(pip))
    assert pip.stop_calls == []


# -- next-cell request mid-poll ------------------------------------------


def test_next_cell_requested_mid_poll_raises_advance_and_triggers_safe_abort(
    fake_pip_factory, monkeypatch
):
    # "approach" is not a Patch terminal, so without a next-cell request this
    # would poll forever; the fake never advances its own state sequence.
    pip = fake_pip_factory([])
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)

    calls = {"n": 0}

    def requested():
        calls["n"] += 1
        return calls["n"] > 1

    ctx = _ctx(pip, next_cell_requested=requested)
    with pytest.raises(AdvanceToNextCell):
        patch(ctx)

    # Abandoning the cell mid-FSM must stop the pipette's in-flight job, the
    # same as a cooperative Stopped -- not leave it running underneath the
    # cell the orchestrator has already moved on from.
    assert len(pip.stop_calls) == 1


def test_next_cell_requested_mid_poll_sets_abandoned_outcome_on_log_entry(
    fake_pip_factory, monkeypatch
):
    # The regression this guards: the operator hits "Next cell" mid-Patch, the
    # poll loop's cooperative checkpoint raises AdvanceToNextCell from *inside*
    # patch()'s own open log_action block (not from a standalone flow action),
    # and the entry that reaches the UI must say the action was abandoned, not
    # report a false "done" for work that was cut short.
    pip = fake_pip_factory([])
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)

    calls = {"n": 0}

    def requested():
        calls["n"] += 1
        return calls["n"] > 1

    entries = []
    ctx = _ctx(pip, next_cell_requested=requested)
    ctx.on_log_action = entries.append

    with pytest.raises(AdvanceToNextCell):
        patch(ctx)

    assert len(entries) == 1
    assert entries[0].outcome == "abandoned"
    # The safe-abort still fires on this path.
    assert len(pip.stop_calls) == 1


def test_no_next_cell_request_does_not_raise(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"


# -- log entry ------------------------------------------------------------


def test_patch_creates_log_entry_named_patch(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip)
    names = _entry_names(ctx)
    patch(ctx)
    assert names == ["Patch"]


def test_reseal_creates_log_entry_named_reseal(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip)
    names = _entry_names(ctx)
    reseal(ctx)
    assert names == ["Reseal"]


def test_clean_creates_log_entry_named_clean(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    ctx = _ctx(pip)
    names = _entry_names(ctx)
    clean(ctx)
    assert names == ["Clean Pipette"]


# -- status updates on state change ------------------------------------------


def _statuses(ctx):
    """Attach an on_status recorder to the next log_action entry, returning the
    list of status strings it observes over the entry's lifetime."""
    statuses = []

    def on_log_action(action_entry):
        action_entry.on_status = lambda entry: statuses.append(entry.status)

    ctx.on_log_action = on_log_action
    return statuses


def test_status_updates_when_observed_state_changes(fake_pip_factory, monkeypatch):
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    # "cell detect" repeats before advancing, so the repeat must not re-emit.
    pip = fake_pip_factory(["cell detect", "cell detect", "seal", "whole cell"])
    ctx = _ctx(pip)
    statuses = _statuses(ctx)

    assert patch(ctx) == "whole cell"

    assert statuses == [
        "driving FSM from 'approach'",
        "now in 'cell detect'",
        "now in 'seal'",
        "reached 'whole cell'",
    ]


# -- fake state-sequence exhaustion ------------------------------------------


def test_fake_pipette_raises_once_its_declared_state_sequence_is_exhausted(
    fake_pip_factory, monkeypatch
):
    # A declared sequence that never reaches a terminal is a broken test setup
    # -- with sleep() a no-op, silently repeating the last state forever turns
    # this into a hanging hot loop instead of a fast, clear failure.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory(["cell detect"])
    with pytest.raises(RuntimeError, match="exhausted"):
        patch(_ctx(pip))


def test_fake_pipette_with_no_declared_sequence_repeats_forever(fake_pip_factory):
    # An explicitly empty state_sequence is the deliberate "never advances"
    # shape other tests rely on (driven out only by check_stop/next_cell), so
    # it must NOT be treated as an exhausted sequence.
    pip = fake_pip_factory([])
    for _ in range(5):
        assert pip.getState().stateName == "out"


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


def test_advance_to_next_cell_still_retains_its_payload(fake_pip_factory, monkeypatch):
    # AdvanceToNextCell shares _drive_fsm's finally with Stopped -- covered
    # separately here since a shared code path can still silently regress on
    # only one of its callers.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)
    pip = fake_pip_factory([])
    ctx = _ctx(pip, next_cell_requested=lambda: True)
    seen = _details(ctx)

    with pytest.raises(AdvanceToNextCell):
        patch(ctx)

    assert len(seen) == 1
    assert seen[0][1]["reached"] is None


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


def test_a_recorder_already_opened_is_stopped_even_if_the_live_plot_fails(
    fake_pip_factory, monkeypatch, fake_recorder
):
    # If _openLivePlot raises after _openRecorder has already succeeded, the
    # recorder must still be torn down -- an unclosed log file handle per
    # failed plot mount is a leak, not a nuisance. A widget-construction
    # failure is a display problem, not a reason to fail the patch attempt
    # itself, so it is logged and the drive continues with no plot.
    monkeypatch.setattr(fsm_mod, "sleep", lambda *a, **k: None)

    def boom(ctx, entry):
        raise RuntimeError("no display available")

    monkeypatch.setattr(fsm_mod, "_openLivePlot", boom)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    logged = []
    ctx.log = logged.append

    assert patch(ctx) == "whole cell"

    assert fake_recorder.instances[0].stopped is True
    assert any("no display available" in message for message in logged)
