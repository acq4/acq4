"""Tests for the stimset actions, against a fake StimsetRunner."""

import sys
import threading
import types

import pytest

from acq4.experiment.actions import run_stimset, run_stimset_chain
from acq4.experiment.actions import stimsets as stimsets_mod
from acq4.experiment.context import ExecutionContext
from acq4.experiment.exceptions import AdvanceToNextCell, OrchestrationError
from acq4.util.allen_stimsets import stimset as stimset_mod
from acq4.util.allen_stimsets.core import SetResult
from acq4.util.allen_stimsets.notebook import Notebook
from acq4.util.task import Stopped


class _Dir:
    def __init__(self, path):
        self.path = path

    def name(self):
        return str(self.path)


class _Manager:
    def __init__(self, path):
        self.current = _Dir(path)

    def getCurrentDir(self):
        return self.current


class _Pressure:
    def __init__(self):
        self.source, self.pressure = "atmosphere", 0.0
        self.calls = []

    def getSource(self):
        return self.source

    def getPressure(self):
        return self.pressure

    def setPressure(self, source=None, pressure=None):
        self.calls.append((source, pressure))
        self.source, self.pressure = source, pressure


class _Pipette:
    def __init__(self, pressure=None):
        self.clampDevice = object()
        self.pressureDevice = pressure

    def name(self):
        return "Pipette1"


class FakeRunner:
    """Returns canned results; with ``block`` set, runs until stop() is called."""

    def __init__(self, results=None, block=False, error=None):
        self.results = results or {}
        self.block = block
        self.error = error
        self.calls = []
        self.stopped = threading.Event()
        self.pressureDuringRun = None

    def _wait(self):
        if self.block and not self.stopped.wait(5):
            raise AssertionError("runner was never stopped")

    def runSet(self, name):
        self.calls.append(("runSet", name))
        self._wait()
        if self.error is not None:
            raise self.error
        return self.results[name]

    def runChain(self, start, end=None):
        self.calls.append(("runChain", start, end))
        self._wait()
        return list(self.results.items())

    def stop(self):
        self.calls.append(("stop",))
        self.stopped.set()


@pytest.fixture
def ctx(tmp_path):
    return ExecutionContext(pipette=_Pipette(), manager=_Manager(tmp_path))


def _useRunner(monkeypatch, runner):
    made = []

    def newRunner(ctx, source, test_pulse, param_overrides):
        made.append((source, test_pulse, param_overrides))
        return runner

    monkeypatch.setattr(stimsets_mod, "_newRunner", newRunner)
    return made


def _details(ctx):
    seen = []

    def hook(action_entry):
        seen.append(action_entry)
        action_entry.on_details = lambda e, kind, payload: seen.append((kind, payload))

    ctx.on_log_action = hook
    return seen


# -- run_stimset ----------------------------------------------------------------


def test_run_stimset_returns_the_set_result(ctx, monkeypatch):
    result = SetResult(passed=True, values={"Ra": 8.2})
    runner = FakeRunner({"EXTPBREAKN180424_DA_0": result})
    _useRunner(monkeypatch, runner)
    assert run_stimset(ctx, "EXTPBREAKN180424_DA_0") is result
    assert runner.calls == [("runSet", "EXTPBREAKN180424_DA_0")]


def test_a_failed_set_is_returned_not_raised(ctx, monkeypatch):
    _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=False)}))
    assert run_stimset(ctx, "A").passed is False


def test_run_stimset_reports_the_result_in_area_5(ctx, monkeypatch):
    _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=False, values={"Ra": 30})}))
    seen = _details(ctx)
    run_stimset(ctx, "A")
    entry, (kind, payload) = seen
    assert entry.name == "Stimset A"
    assert entry.status == "A: FAILED"
    assert kind == "text"
    assert payload["lines"] == ["A: FAILED", "  Ra: 30"]


def test_run_stimset_passes_options_to_the_runner(ctx, monkeypatch):
    made = _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=True)}))
    run_stimset(ctx, "A", source="x.nwb", test_pulse="tp", param_overrides={"A": {"k": 1}})
    assert made == [("x.nwb", "tp", {"A": {"k": 1}})]


def test_a_runner_error_propagates(ctx, monkeypatch):
    _useRunner(monkeypatch, FakeRunner(error=RuntimeError("daq gone")))
    with pytest.raises(RuntimeError, match="daq gone"):
        run_stimset(ctx, "A")


def test_run_stimset_does_not_checkpoint_by_default(tmp_path, monkeypatch):
    calls = []
    ctx = ExecutionContext(
        pipette=_Pipette(), manager=_Manager(tmp_path), checkpoint=lambda: calls.append(1)
    )
    _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=True)}))
    run_stimset(ctx, "A")
    assert calls == []
    run_stimset(ctx, "A", pausable=True)
    assert calls == [1]


# -- stopping ---------------------------------------------------------------------


def test_stopping_the_run_stops_the_runner(ctx, monkeypatch):
    runner = FakeRunner({"A": SetResult(passed=True)}, block=True)
    _useRunner(monkeypatch, runner)
    polls = {"n": 0}

    def fake_check_stop():
        polls["n"] += 1
        if polls["n"] > 2:
            raise Stopped("operator stop")

    monkeypatch.setattr(stimsets_mod, "check_stop", fake_check_stop)
    with pytest.raises(Stopped):
        run_stimset(ctx, "A")
    assert ("stop",) in runner.calls


def test_next_cell_stops_the_runner(tmp_path, monkeypatch):
    runner = FakeRunner({"A": SetResult(passed=True)}, block=True)
    _useRunner(monkeypatch, runner)
    ctx = ExecutionContext(
        pipette=_Pipette(), manager=_Manager(tmp_path), next_cell_requested=lambda: True
    )
    with pytest.raises(AdvanceToNextCell):
        run_stimset_chain(ctx, "X0NRMP_DA_0", "X7RampN3_DA_0")
    assert ("stop",) in runner.calls


# -- run_stimset_chain --------------------------------------------------------------


def test_run_stimset_chain_returns_every_set(ctx, monkeypatch):
    results = {
        "X0NRMP_DA_0": SetResult(passed=True),
        "X1PS_SubThresh_DA_0": SetResult(passed=False),
    }
    runner = FakeRunner(results)
    _useRunner(monkeypatch, runner)
    seen = _details(ctx)
    out = run_stimset_chain(ctx, "X0NRMP_DA_0", "X7RampN3_DA_0")
    assert out == list(results.items())
    assert runner.calls == [("runChain", "X0NRMP_DA_0", "X7RampN3_DA_0")]
    entry = seen[0]
    assert entry.name == "Stimsets X0NRMP_DA_0 -> X7RampN3_DA_0"
    assert entry.status == "1/2 sets passed"


def test_run_stimset_chain_without_an_end(ctx, monkeypatch):
    runner = FakeRunner({"A": SetResult(passed=True)})
    _useRunner(monkeypatch, runner)
    run_stimset_chain(ctx, "A")
    assert runner.calls == [("runChain", "A", None)]


# -- pressure -----------------------------------------------------------------------


def test_pressure_is_held_during_the_set_and_restored(tmp_path, monkeypatch):
    pressure = _Pressure()
    ctx = ExecutionContext(pipette=_Pipette(pressure), manager=_Manager(tmp_path))
    runner = FakeRunner({"A": SetResult(passed=True)})
    original = runner.runSet

    def runSet(name):
        runner.pressureDuringRun = (pressure.source, pressure.pressure)
        return original(name)

    runner.runSet = runSet
    _useRunner(monkeypatch, runner)
    run_stimset(ctx, "A", pressure=3500.0)
    assert runner.pressureDuringRun == ("regulator", 3500.0)
    assert (pressure.source, pressure.pressure) == ("atmosphere", 0.0)


def test_pressure_is_restored_when_the_set_raises(tmp_path, monkeypatch):
    pressure = _Pressure()
    ctx = ExecutionContext(pipette=_Pipette(pressure), manager=_Manager(tmp_path))
    _useRunner(monkeypatch, FakeRunner(error=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        run_stimset(ctx, "A", pressure=3500.0)
    assert (pressure.source, pressure.pressure) == ("atmosphere", 0.0)


def test_pressure_without_a_pressure_device_raises(ctx, monkeypatch):
    runner = FakeRunner({"A": SetResult(passed=True)})
    _useRunner(monkeypatch, runner)
    with pytest.raises(OrchestrationError, match="no pressureDevice"):
        run_stimset(ctx, "A", pressure=3500.0)
    assert runner.calls == []


# -- the cell notebook ----------------------------------------------------------------


def test_the_notebook_lives_in_the_cell_directory_and_is_shared(ctx, monkeypatch, tmp_path):
    _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=True)}))
    notebook = stimsets_mod.cell_notebook(ctx)
    assert notebook.path == tmp_path / "notebook.json"
    run_stimset(ctx, "A")
    assert stimsets_mod.cell_notebook(ctx) is notebook
    assert notebook.path.exists()


def test_a_retried_cell_reloads_the_saved_notebook(ctx, monkeypatch, tmp_path):
    _useRunner(monkeypatch, FakeRunner({"A": SetResult(passed=True)}))
    stimsets_mod.cell_notebook(ctx).newSet("EXTPBREAKN180424_DA_0", "AR")
    run_stimset(ctx, "A")
    retry = ExecutionContext(pipette=ctx.pipette, manager=ctx.manager)
    assert [s.stimset for s in stimsets_mod.cell_notebook(retry).sets()] == [
        "EXTPBREAKN180424_DA_0"
    ]


def test_the_notebook_is_created_where_the_first_stimset_ran(ctx, tmp_path):
    notebook = stimsets_mod.cell_notebook(ctx)
    ctx.manager.current = _Dir(tmp_path / "elsewhere")
    assert stimsets_mod.cell_notebook(ctx) is notebook


# -- runner construction -----------------------------------------------------------------


def test_new_runner_wires_clamp_notebook_and_storage(ctx, monkeypatch):
    built = {}

    class StimsetRunner:
        def __init__(self, clamp, stimsets, notebook, storageDir, **kwargs):
            built.update(
                clamp=clamp, stimsets=stimsets, notebook=notebook, storageDir=storageDir, **kwargs
            )

    fakeModule = types.ModuleType("acq4.util.allen_stimsets.runner")
    fakeModule.StimsetRunner = StimsetRunner
    monkeypatch.setitem(sys.modules, "acq4.util.allen_stimsets.runner", fakeModule)
    monkeypatch.setattr(stimset_mod, "loadProductionStimsets", lambda: {"prod": 1}, raising=False)
    monkeypatch.setattr(stimset_mod, "loadStimsets", lambda path: {"file": path})

    stimsets_mod._newRunner(ctx, None, "tp", {"A": {}})
    assert built["clamp"] is ctx.pipette.clampDevice
    assert built["stimsets"] == {"prod": 1}
    assert isinstance(built["notebook"], Notebook)
    assert built["notebook"] is stimsets_mod.cell_notebook(ctx)
    assert built["storageDir"] is ctx.manager.getCurrentDir()
    assert built["testPulse"] == "tp"
    assert built["paramOverrides"] == {"A": {}}
    assert built["manager"] is ctx.manager

    stimsets_mod._newRunner(ctx, "cell.nwb", None, None)
    assert built["stimsets"] == {"file": "cell.nwb"}
