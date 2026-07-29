"""Tests for the plain-function FSM actions (patch, reseal, clean): drive the
PatchPipette FSM to a declared terminal state via the shared fake pipette."""
import pytest

from acq4.util.task import Stopped
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import BrokenPipette, Fouled
from acq4.experiment.actions import fsm as fsm_mod
from acq4.experiment.actions.fsm import patch, reseal, clean


def _ctx(pip, **kwargs):
    return ExecutionContext(pipette=pip, **kwargs)


def _entry_names(ctx):
    names = []
    ctx.on_log_action = lambda entry: names.append(entry.name)
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
    assert names == ["Clean"]
