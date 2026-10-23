"""Tests for the plain-function FSM actions (patch, reseal, clean): drive the
PatchPipette FSM to a declared terminal state via the shared fake pipette."""
import pytest

from acq4.util import Qt
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
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"


def test_patch_passes_through_cell_attached_to_whole_cell(fake_pip_factory, monkeypatch):
    # Auto-break-in always follows "cell attached" on these rigs, so it is an
    # internal hop, not a patch terminal -- the poll must continue through it
    # and patch() must report the outcome it actually settles at.
    pip = fake_pip_factory(["cell detect", "seal", "cell attached", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"


def test_patch_on_broken_returns_broken(fake_pip_factory, monkeypatch):
    # broken IS a declared Patch terminal -> routes as an outcome, not an exception.
    pip = fake_pip_factory(["cell detect", "broken"])
    assert patch(_ctx(pip)) == "broken"


def test_reseal_reaches_outside_out(fake_pip_factory):
    pip = fake_pip_factory(["outside out"])
    assert reseal(_ctx(pip)) == "outside out"


def test_clean_reaches_out(fake_pip_factory):
    pip = fake_pip_factory(["out"])
    assert clean(_ctx(pip)) == "out"


# -- the pause checkpoint ----------------------------------------------------


def _checkpoints(ctx_kwargs):
    """Record calls to the context's pause checkpoint."""
    calls = []
    ctx_kwargs["checkpoint"] = lambda: calls.append("checkpoint")
    return calls


def test_patch_does_not_checkpoint_at_entry(fake_pip_factory):
    # Entering patch means the tip is already parked at the target in tissue
    # under the previous action's pressure -- not a boundary to hold at.
    kwargs = {}
    calls = _checkpoints(kwargs)
    pip = fake_pip_factory(["whole cell"])
    patch(_ctx(pip, **kwargs))
    assert calls == []


def test_reseal_does_not_checkpoint_at_entry(fake_pip_factory):
    kwargs = {}
    calls = _checkpoints(kwargs)
    pip = fake_pip_factory(["outside out"])
    reseal(_ctx(pip, **kwargs))
    assert calls == []


def test_clean_checkpoints_at_entry(fake_pip_factory):
    # Whatever patch settled at is a resting terminal state, so the boundary
    # before a clean is safe to hold at.
    kwargs = {}
    calls = _checkpoints(kwargs)
    pip = fake_pip_factory(["out"])
    clean(_ctx(pip, **kwargs))
    assert calls == ["checkpoint"]


def test_skipped_clean_checkpoints_at_entry(fake_pip_factory):
    # The only_if_needed skip opens its own entry; it is the same boundary.
    kwargs = {}
    calls = _checkpoints(kwargs)
    pip = fake_pip_factory(["out"])
    pip.isTipClean = lambda: True
    assert clean(_ctx(pip, **kwargs), only_if_needed=True) == "out"
    assert calls == ["checkpoint"]
    assert pip.setState_calls == []  # genuinely skipped, not driven


# -- abnormal-state mapping ---------------------------------------------------


def test_reseal_on_broken_raises_broken_pipette(fake_pip_factory, monkeypatch):
    # broken is NOT a declared Reseal terminal -> mapped to BrokenPipette.
    pip = fake_pip_factory(["reseal", "broken"])
    with pytest.raises(BrokenPipette):
        reseal(_ctx(pip))


def test_reseal_on_fouled_raises_fouled(fake_pip_factory, monkeypatch):
    # fouled is NOT a declared Reseal terminal -> the shared raise_if_abnormal
    # helper maps it to Fouled (the class only special-cased "broken" and would
    # have polled forever here).
    pip = fake_pip_factory(["reseal", "fouled"])
    with pytest.raises(Fouled):
        reseal(_ctx(pip))


def test_clean_on_broken_raises_broken_pipette(fake_pip_factory, monkeypatch):
    # broken is NOT a declared Clean terminal ({"out"}) -> mapped to BrokenPipette.
    pip = fake_pip_factory(["clean", "broken"])
    with pytest.raises(BrokenPipette):
        clean(_ctx(pip))


def test_clean_on_fouled_raises_fouled(fake_pip_factory, monkeypatch):
    # fouled is NOT a declared Clean terminal ({"out"}) -> mapped to Fouled.
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
    pip = fake_pip_factory(["cell detect", "seal", "break in", "whole cell"])
    assert patch(_ctx(pip)) == "whole cell"
    assert pip.stop_calls == []


def test_reseal_on_broken_does_not_call_stop(fake_pip_factory, monkeypatch):
    # An abnormal state mapped to an OrchestrationError (here BrokenPipette)
    # propagates untouched -- it is not a cooperative Stopped, so no abort.
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


def test_status_updates_on_each_state_change(fake_pip_factory):
    pip = fake_pip_factory(["cell detect", "seal", "whole cell"])
    ctx = _ctx(pip)
    statuses = _statuses(ctx)

    assert patch(ctx) == "whole cell"

    assert statuses == [
        "driving FSM from 'approach'",
        "now in 'cell detect'",
        "now in 'seal'",
        "reached 'whole cell'",
    ]


# -- following state changes ----------------------------------------------------


def _drive(pip, ctx=None, **kwargs):
    """_drive_fsm toward patch's terminals with a short poll interval and no recording."""
    return fsm_mod._drive_fsm(
        ctx or _ctx(pip),
        "Patch",
        "approach",
        {"whole cell", "bath", "broken", "fouled"},
        poll_interval=0.01,
        record=False,
        **kwargs,
    )


def test_states_reached_after_set_state_returns_are_followed(fake_pip_factory):
    # The usual case: the state machine moves on from its own threads.
    import threading

    pip = fake_pip_factory([])
    ctx = _ctx(pip)

    def advance():
        for state in ("cell detect", "seal", "whole cell"):
            pip.changeState(state)

    original = pip.setState

    def setState(state, **config):
        job = original(state, **config)
        threading.Thread(target=advance).start()
        return job

    pip.setState = setState
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    states = [state for _when, state in seen[0][1]["transitions"]]
    assert states == ["approach", "cell detect", "seal", "whole cell"]


def test_fast_intermediate_states_all_appear_in_the_transitions(fake_pip_factory):
    # Every state passes before the drive loop looks even once; a poll of
    # getState() would only ever have seen the last.
    pip = fake_pip_factory(["cell detect", "seal", "cell attached", "break in", "whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    states = [state for _when, state in seen[0][1]["transitions"]]
    assert states == ["approach", "cell detect", "seal", "cell attached", "break in", "whole cell"]


def test_an_entry_state_that_is_already_current_still_starts_the_drive(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])
    pip.changeState("approach")

    assert patch(_ctx(pip)) == "whole cell"


def test_states_announced_before_the_entry_state_are_ignored(fake_pip_factory):
    # e.g. a job finishing into its next state just as setState replaces it.
    pip = fake_pip_factory(["seal", "whole cell"])
    original = pip.setState

    def setState(state, **config):
        pip.changeState("fouled")  # would end a patch if taken as part of this drive
        return original(state, **config)

    pip.setState = setState
    ctx = _ctx(pip)
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    assert [s for _w, s in seen[0][1]["transitions"]] == ["approach", "seal", "whole cell"]


def test_a_failed_entry_propagates_and_unsubscribes(fake_pip_factory):
    # PatchPipetteStateManager falls back to another state and re-raises when the
    # entry state fails to start.
    pip = fake_pip_factory([])

    def setState(state, **config):
        pip.changeState(state)
        pip.changeState("bath")
        raise RuntimeError("could not start approach")

    pip.setState = setState

    with pytest.raises(RuntimeError, match="could not start"):
        patch(_ctx(pip))

    assert pip.receivers(pip.sigStateChanged) == 0


def test_the_drive_unsubscribes_when_it_ends(fake_pip_factory):
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip))

    assert pip.receivers(pip.sigStateChanged) == 0


def test_a_drive_parked_in_a_non_terminal_state_still_services_stops(fake_pip_factory, monkeypatch):
    pip = fake_pip_factory(["cell detect"])
    calls = {"n": 0}

    def fake_check_stop():
        calls["n"] += 1
        if calls["n"] > 5:
            raise Stopped("stopped by operator")

    monkeypatch.setattr(fsm_mod, "check_stop", fake_check_stop)

    with pytest.raises(Stopped):
        _drive(pip)

    assert len(pip.stop_calls) == 1


# -- details payloads -------------------------------------------------------


def _details(ctx):
    """Collect (kind, payload) from every entry this context opens."""
    seen = []

    def hook(action_entry):
        action_entry.on_details = lambda e, kind, payload: seen.append((kind, payload))

    ctx.on_log_action = hook
    return seen


def test_patch_retains_a_test_pulse_history_payload(fake_pip_factory, monkeypatch):
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
    pip = fake_pip_factory(["out"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    clean(ctx)

    assert seen == []


def test_record_events_false_still_retains_the_payload(fake_pip_factory, monkeypatch):
    # Switching off the disk log is not a reason to lose the pane's plot.
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip)
    seen = _details(ctx)

    patch(ctx, record_events=False)

    assert len(seen) == 1


def test_record_kwargs_do_not_reach_set_state(fake_pip_factory, monkeypatch):
    # entry_config is forwarded to pip.setState; these two are this action's own
    # options and must not be.
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
    pip = fake_pip_factory([])
    ctx = _ctx(pip, next_cell_requested=lambda: True)
    seen = _details(ctx)

    with pytest.raises(AdvanceToNextCell):
        patch(ctx)

    assert len(seen) == 1
    assert seen[0][1]["reached"] is None


# -- the recorder and the live plot -----------------------------------------


class _FakeRecorder:
    """Stands in for MultiPatchLogWriter."""

    instances = []

    def __init__(self, directory, pipettes=(), full_test_pulse_pipettes=()):
        import numpy as np
        from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

        self.directory = directory
        self.pipettes = list(pipettes)
        self.fullTestPulsePipettes = list(full_test_pulse_pipettes)
        self.started = False
        self.stopped = False
        self._history = np.zeros(3, dtype=TEST_PULSE_NUMPY_DTYPE)
        self._history["steady_state_resistance"] = [1e6, 1e8, 1e9]
        type(self).instances.append(self)

    def start(self):
        self.started = True
        return self

    def testPulseAnalysis(self):
        return self._history

    def logFileName(self):
        return "/data/cell_000/MultiPatch_004.log"

    def stop(self):
        self.stopped = True


class _FakeDir:
    pass


class _FakeManagerWithDir:
    def __init__(self, directory=None):
        self.dir = _FakeDir() if directory is None else directory

    def getCurrentDir(self):
        return self.dir


@pytest.fixture
def fake_recorder(monkeypatch):
    _FakeRecorder.instances = []
    monkeypatch.setattr(fsm_mod, "MultiPatchLogWriter", _FakeRecorder)
    # The live plot needs a real Qt widget and a real clamp device; those are
    # live-tested, so this suite stubs the plot out entirely.
    monkeypatch.setattr(fsm_mod, "_openLivePlot", lambda ctx, entry: None)
    return _FakeRecorder


def test_patch_opens_a_recorder_in_the_current_directory(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["whole cell"])
    manager = _FakeManagerWithDir()

    patch(_ctx(pip, manager=manager))

    (recorder,) = fake_recorder.instances
    assert recorder.directory is manager.dir
    assert recorder.pipettes == [pip]
    assert recorder.fullTestPulsePipettes == [pip]
    assert recorder.started is True


def test_the_recorder_is_stopped_when_the_drive_ends(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances[0].stopped is True


def test_the_recorder_is_stopped_even_when_the_drive_raises(fake_pip_factory, fake_recorder):
    # An unclosed file handle per failed patch attempt is a leak, not a nuisance.
    pip = fake_pip_factory(["broken"])

    with pytest.raises(BrokenPipette):
        reseal(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances[0].stopped is True


def test_the_payload_carries_the_recorders_history(fake_pip_factory, fake_recorder):
    import numpy as np

    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    seen = _details(ctx)

    patch(ctx)

    history = seen[0][1]["history"]
    assert len(history) == 3
    assert np.array_equal(history["steady_state_resistance"], [1e6, 1e8, 1e9])


def test_the_payload_names_the_log_file_without_its_path(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    seen = _details(ctx)

    patch(ctx)

    assert seen[0][1]["log_file"] == "MultiPatch_004.log"


def test_record_full_test_pulses_false_records_events_without_full_test_pulses(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()), record_full_test_pulses=False)

    (recorder,) = fake_recorder.instances
    assert recorder.fullTestPulsePipettes == []


def test_record_events_false_records_nothing_even_with_full_test_pulses(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["whole cell"])

    patch(_ctx(pip, manager=_FakeManagerWithDir()), record_events=False, record_full_test_pulses=True)

    assert fake_recorder.instances == []


def test_clean_opens_no_recorder(fake_pip_factory, fake_recorder):
    pip = fake_pip_factory(["out"])

    clean(_ctx(pip, manager=_FakeManagerWithDir()))

    assert fake_recorder.instances == []


def test_a_recorder_that_will_not_open_does_not_fail_the_patch(fake_pip_factory, monkeypatch):
    # An unset storage directory must not stop the pipette from patching; the
    # attempt is the experiment, and the log is a record of it.
    monkeypatch.setattr(fsm_mod, "_openLivePlot", lambda ctx, entry: None)

    def boom(*a, **k):
        raise OSError("no current directory")

    monkeypatch.setattr(fsm_mod, "MultiPatchLogWriter", boom)
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
    # A widget-construction failure is a display problem: logged, and the drive
    # continues with no plot, still closing the recorder at the end.
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


# -- the terminal transition vs. the recorder's teardown ----------------------


class _CreatingDir:
    """Stands in for a DirHandle backed by a real directory."""

    def __init__(self, root):
        self.root = root

    def createFile(self, name, autoIncrement=False):
        stem, _, ext = name.rpartition(".")
        path = self.root / f"{stem}_000.{ext}"
        path.touch()

        class _Handle:
            def name(self):
                return str(path)

        return _Handle()


def _loggedStates(tmp_path):
    import json

    with open(tmp_path / "MultiPatch_000.log", "rb") as fh:
        return [json.loads(line)["state"] for line in fh if b'"state_change"' in line]


def test_the_terminal_state_change_is_logged_without_any_wait(fake_pip_factory, monkeypatch, tmp_path, qapp):
    # The pipette queues its state_change event to the log before announcing the
    # state, so a drive that ends on seeing the state can stop the recorder at once.
    import threading

    monkeypatch.setattr(fsm_mod, "_openLivePlot", lambda ctx, entry: None)
    pip = fake_pip_factory([])
    original = pip.setState

    def setState(state, **config):
        job = original(state, **config)
        threading.Thread(target=lambda: [pip.changeState(s) for s in ("seal", "whole cell")]).start()
        return job

    pip.setState = setState
    ctx = _ctx(pip, manager=_FakeManagerWithDir(_CreatingDir(tmp_path)))

    assert patch(ctx) == "whole cell"

    assert _loggedStates(tmp_path) == ["approach", "seal", "whole cell"]
    assert not hasattr(fsm_mod, "_awaitLoggedTransition")


# -- the live plot's thread affinity ------------------------------------------


class _FakeClamp(Qt.QObject):
    """Stands in for a PatchClamp for the live plot's two needs: the
    sigTestPulseFinished stream and the history behind it."""

    sigTestPulseFinished = Qt.Signal(object, object)  # self, PatchClampTestPulse

    def __init__(self, history):
        super().__init__()
        self._history = history

    def testPulseHistory(self):
        return self._history


class _FakeTestPulse:
    """A test pulse for the analysis modes, which read only .analysis."""

    def __init__(self, resistance):
        self.analysis = {"steady_state_resistance": resistance}


class _FakeClampedPipette:
    def __init__(self, clamp):
        self.clampDevice = clamp


class _RecordingEntry:
    """Stands in for an ActionLogEntry for the one call _openLivePlot makes."""

    def __init__(self, error=None):
        self.widgets = []
        self.error = error

    def set_details_widget(self, widget):
        self.widgets.append(widget)
        if self.error is not None:
            raise self.error


def _tpHistory(count=4):
    import numpy as np

    from acq4.filetypes.MultiPatchLog import TEST_PULSE_NUMPY_DTYPE

    history = np.zeros(count, dtype=TEST_PULSE_NUMPY_DTYPE)
    history["event_time"] = np.arange(count, dtype=float)
    history["steady_state_resistance"] = np.linspace(1e6, 1e9, count)
    return history


def test_the_live_plot_updates_from_a_test_pulse_emitted_on_another_thread(qapp, qtbot):
    """_openLivePlot runs on the orchestrator's worker thread -- a gentletask
    ThreadTask with no Qt event loop -- while sigTestPulseFinished is emitted
    from the clamp's test-pulse thread. PyQt gives a plain callable slot the
    affinity of the thread that called connect(), so the connection has to be
    made on the GUI thread or every test pulse is queued to a loop that never
    runs and the plot mounts but never updates.

    Genuinely cross-thread on purpose: opened on one thread, emitted from a
    second, pumped on this one. A same-thread version passes either way.
    """
    import threading

    clamp = _FakeClamp(_tpHistory())
    ctx = _ctx(_FakeClampedPipette(clamp))
    entry = _RecordingEntry()
    opened = {}
    ready = threading.Event()
    release = threading.Event()

    def openOnWorker():
        opened["teardown"] = fsm_mod._openLivePlot(ctx, entry)
        opened["thread"] = Qt.QtCore.QThread.currentThread()
        ready.set()
        # Held open without an event loop for the rest of the test, the shape
        # of a real drive.
        release.wait(10)

    worker = threading.Thread(target=openOnWorker, name="live-plot-opener")
    worker.start()
    # From here down, everything runs under try/finally: worker sits in
    # release.wait(10) until release.set() below, so a failed assertion above
    # a bare `qtbot.waitUntil(ready.is_set, ...)` would otherwise leave that
    # non-daemon thread parked for up to 10s past this test's own failure.
    try:
        # This thread has to keep pumping: _openLivePlot builds its widget
        # through run_in_gui_thread, which blocks the worker until this loop
        # runs it.
        qtbot.waitUntil(ready.is_set, timeout=5000)
        assert opened["thread"] is not Qt.QtCore.QThread.currentThread()
        widget = entry.widgets[0]
        assert widget.plot.plotItem.listDataItems() == []

        emitter = threading.Thread(
            target=lambda: clamp.sigTestPulseFinished.emit(clamp, _FakeTestPulse(1e9)),
            name="clamp-emitter",
        )
        emitter.start()
        emitter.join(5)

        qtbot.waitUntil(
            lambda: len(widget.plot.plotItem.listDataItems()) == 1, timeout=3000
        )
    finally:
        release.set()
        worker.join(5)
        if "teardown" in opened:
            opened["teardown"]()


def test_the_live_plot_disconnects_when_mounting_the_widget_fails(qapp):
    # The connect is live before set_details_widget is called; if that raises,
    # the caller never receives the teardown, so nothing else would ever drop
    # the clamp's reference into a widget nobody owns.
    clamp = _FakeClamp(_tpHistory())
    ctx = _ctx(_FakeClampedPipette(clamp))
    entry = _RecordingEntry(error=RuntimeError("no pane to mount into"))

    with pytest.raises(RuntimeError, match="no pane to mount into"):
        fsm_mod._openLivePlot(ctx, entry)

    widget = entry.widgets[0]
    clamp.sigTestPulseFinished.emit(clamp, _FakeTestPulse(1e9))

    assert widget.plot.plotItem.listDataItems() == []


# -- the finally is guarded ---------------------------------------------------


def test_a_failing_plot_teardown_still_stops_the_recorder_and_retains_details(
    fake_pip_factory, monkeypatch, fake_recorder
):

    def openPlot(ctx, entry):
        def teardown():
            raise RuntimeError("plot teardown exploded")

        return teardown

    monkeypatch.setattr(fsm_mod, "_openLivePlot", openPlot)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    logged = []
    ctx.log = logged.append
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    assert fake_recorder.instances[0].stopped is True
    assert len(seen) == 1
    assert any("plot teardown exploded" in message for message in logged)


def test_a_failing_recorder_stop_still_retains_details(
    fake_pip_factory, monkeypatch, fake_recorder
):

    def boom(self):
        raise OSError("disk full on close")

    monkeypatch.setattr(_FakeRecorder, "stop", boom)
    pip = fake_pip_factory(["whole cell"])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    logged = []
    ctx.log = logged.append
    seen = _details(ctx)

    assert patch(ctx) == "whole cell"

    assert len(seen) == 1
    assert any("disk full on close" in message for message in logged)


def test_a_failing_details_payload_does_not_replace_a_stop(
    fake_pip_factory, monkeypatch, fake_recorder
):
    # An orderly operator stop must surface as Stopped, not as whatever the
    # payload builder happened to trip over on the way out.

    def boom(*a, **k):
        raise ValueError("payload exploded")

    monkeypatch.setattr(fsm_mod, "_setFsmDetails", boom)
    pip = fake_pip_factory([])
    ctx = _ctx(pip, manager=_FakeManagerWithDir())
    logged = []
    ctx.log = logged.append
    monkeypatch.setattr(fsm_mod, "check_stop", _raiseStopped)

    with pytest.raises(Stopped):
        patch(ctx)

    assert any("payload exploded" in message for message in logged)


def _raiseStopped():
    raise Stopped("operator stop")


# -- the conditional clean ----------------------------------------------------
#
# A PatchPipette carries its own "is this tip still clean" flag: True from
# construction and from the clean state's own success path, False once `seal`
# has sealed onto a cell or `fouled` has been entered. `clean(only_if_needed=
# True)` reads that flag and skips the cycle when it says the tip is clean.
# The shared FakePatchPipette has no such flag (nothing else in this suite
# asks about one), so these tests give the fake the one method the check
# calls, which is also the whole seam under test.


def _tipClean(pip, clean):
    pip.isTipClean = lambda: clean
    return pip


def _outcomes(ctx):
    """Collect every entry this context opens, so a test can read what the UI
    would have been shown."""
    entries = []
    ctx.on_log_action = entries.append
    return entries


def test_a_conditional_clean_runs_the_cycle_when_the_tip_reports_dirty(fake_pip_factory):
    pip = _tipClean(fake_pip_factory(["out"]), False)

    assert clean(_ctx(pip), only_if_needed=True) == "out"

    assert pip.setState_calls[0][0] == "clean"


def test_a_conditional_clean_skips_the_cycle_when_the_tip_reports_clean(fake_pip_factory):
    pip = _tipClean(fake_pip_factory(["out"]), True)

    assert clean(_ctx(pip), only_if_needed=True) == "out"

    # Nothing was driven: the FSM was never entered at all, which is the whole
    # point of the skip -- the cycle costs minutes at the wells.
    assert pip.setState_calls == []


def test_the_default_clean_still_cleans_a_pipette_that_reports_itself_clean(fake_pip_factory):
    # The default is unconditional, so an existing protocol's bare clean() call
    # does what it always did regardless of what the tip flag says.
    pip = _tipClean(fake_pip_factory(["out"]), True)

    assert clean(_ctx(pip)) == "out"

    assert pip.setState_calls[0][0] == "clean"


def test_forcing_cleans_a_pipette_that_reports_itself_clean(fake_pip_factory):
    pip = _tipClean(fake_pip_factory(["out"]), True)

    assert clean(_ctx(pip), only_if_needed=False) == "out"

    assert pip.setState_calls[0][0] == "clean"


def test_only_if_needed_does_not_reach_set_state(fake_pip_factory):
    # entry_config is forwarded to pip.setState; this is the action's own
    # option and must not be, the same as patch()'s recording options.
    pip = _tipClean(fake_pip_factory(["out"]), False)

    clean(_ctx(pip), only_if_needed=True, nextState="bath")

    _state, config = pip.setState_calls[0]
    assert config == {"nextState": "bath"}


def test_a_skipped_clean_still_puts_one_finished_row_in_the_timeline(fake_pip_factory):
    # An action that produced no row at all reads to the operator as one that
    # never ran, rather than one that was not needed.
    pip = _tipClean(fake_pip_factory(["out"]), True)
    ctx = _ctx(pip)
    entries = _outcomes(ctx)

    clean(ctx, only_if_needed=True)

    assert [entry.name for entry in entries] == ["Clean Pipette"]
    assert entries[0].outcome == "done"
    assert "skip" in entries[0].status


def test_a_clean_that_runs_puts_exactly_one_row_in_the_timeline(fake_pip_factory):
    # The guard against the obvious way to get this wrong: a skip-checking
    # wrapper that opens its own entry *around* the drive's would report two
    # rows for one clean.
    pip = _tipClean(fake_pip_factory(["out"]), False)
    ctx = _ctx(pip)
    entries = _outcomes(ctx)

    clean(ctx, only_if_needed=True)

    assert [entry.name for entry in entries] == ["Clean Pipette"]


def test_a_skipped_clean_retains_nothing(fake_pip_factory):
    # A clean records nothing whether it runs or not (design doc §4.5), so the
    # skip must not grow a payload the driving path doesn't have.
    pip = _tipClean(fake_pip_factory(["out"]), True)
    ctx = _ctx(pip)
    seen = _details(ctx)

    clean(ctx, only_if_needed=True)

    assert seen == []


def test_a_conditional_clean_with_no_pipette_fails_like_an_unconditional_one():
    """There is no flag to read off a context with no pipette, and the flag is
    the only thing that can authorize skipping the cycle -- so a missing
    pipette must not read as "already clean". It stays the same failure a bare
    clean() has always had on such a context, rather than becoming a silently
    skipped step that hides a mis-built context."""
    with pytest.raises(AttributeError) as unconditional:
        clean(_ctx(None))

    with pytest.raises(AttributeError) as conditional:
        clean(_ctx(None), only_if_needed=True)

    assert conditional.value.args == unconditional.value.args
