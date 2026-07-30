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
