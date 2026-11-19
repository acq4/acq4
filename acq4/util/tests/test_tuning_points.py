"""Tests for the tuning-point registry, the API with nothing installed, and the installed runtime."""

import contextlib
import random
import subprocess
import sys
import threading
import warnings

import pytest

import acq4.util.DataManager as dm
from acq4.util import tuning_points
from acq4.util.tests.data_dir_helpers import strip_uuid
from acq4.util.tests.memory_ledger import MemoryLedger
from acq4.util.tuning_points import (
    INELIGIBLE,
    POINTS,
    Runtime,
    TuningPointError,
    TuningPointWarning,
    resolve_fact,
)


def test_value_returns_default_when_nothing_installed():
    assert tuning_points.value("min_health", 0.5, facts={"score": 0.9}) == 0.5


def test_scope_is_null_context_when_nothing_installed():
    ran = False
    with tuning_points.scope("patching", facts={"ctx": object()}):
        ran = True
    assert ran


def test_unknown_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.value("no_such_point", 1)
    with pytest.raises(TuningPointError):
        tuning_points.scope("no_such_point")


def test_value_on_scope_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.value("patching", None, facts={"ctx": 1})


def test_scope_on_value_point_raises():
    with pytest.raises(TuningPointError):
        tuning_points.scope("min_health", facts={"score": 1})


@pytest.mark.parametrize(
    "facts",
    [None, {}, {"scor": 1}, {"score": 1, "extra": 2}, {"extra": 2}],
)
def test_facts_keys_must_match_registry(facts):
    with pytest.raises(TuningPointError):
        tuning_points.value("min_health", 0.5, facts=facts)


def test_callable_fact_resolved_only_on_read():
    calls = []

    def score():
        calls.append(1)
        return 0.7

    facts = {"score": score}
    assert tuning_points.value("min_health", 0.5, facts=facts) == 0.5
    assert calls == []
    assert resolve_fact(facts, "score") == 0.7
    assert calls == [1]
    assert resolve_fact({"score": 3}, "score") == 3


def test_registry_entries_well_formed():
    assert set(POINTS) >= {
        "min_health",
        "pipette_detector_class",
        "patching",
        "whole_cell",
    }
    for name, point in POINTS.items():
        assert point.kind in ("value", "scope"), name
        assert point.unit_hint in ("cell", "survey", "slice"), name
        assert isinstance(point.facts, tuple), name
        assert all(isinstance(f, str) for f in point.facts), name
        assert point.doc and point.site, name


def test_module_imports_nothing_from_modules_or_experiment():
    code = (
        "import acq4.util.tuning_points, sys; "
        "print([m for m in sys.modules if m.startswith(('acq4.modules','acq4.experiment'))])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]"


class ValueMut:
    def __init__(self, name, unit, point, conditions=(1, 2), eligible=True):
        self.name = name
        self.unit = unit
        self.answers = {point}
        self.conditions = list(conditions)
        self._eligible = eligible
        self.eligible_calls = 0

    def eligible(self, facts):
        self.eligible_calls += 1
        return self._eligible

    def value(self, point, default, condition, facts):
        return condition


class ScopeMut:
    def __init__(self, name, unit, point, events, conditions=("a", "b"), eligible=True):
        self.name = name
        self.unit = unit
        self.wraps = {point}
        self.conditions = list(conditions)
        self.events = events
        self._eligible = eligible

    def eligible(self, facts):
        return self._eligible

    @contextlib.contextmanager
    def around(self, point, condition, facts):
        self.events.append(("enter", self.name, condition))
        yield
        self.events.append(("exit", self.name, condition))


@pytest.fixture(autouse=True)
def stray_tuning_warnings_fail():
    with warnings.catch_warnings():
        warnings.simplefilter("error", TuningPointWarning)
        yield


@pytest.fixture
def root(tmp_path):
    return dm.getDirHandle(str(tmp_path))


@pytest.fixture
def arm():
    def _arm(mutators, ledger=None, cell_close_hook=None, run_id="run-1"):
        ledger = ledger if ledger is not None else MemoryLedger(random.Random(0))
        runtime = Runtime(run_id, mutators, ledger, cell_close_hook=cell_close_hook)
        tuning_points.install(runtime)
        return runtime, ledger

    yield _arm
    tuning_points.uninstall()


def make_slice(root, name="slice_000"):
    return root.mkdir(name, info={"dirType": "Slice"})


def make_cell(parent, name="cell_000"):
    return parent.mkdir(name, info={"dirType": "Cell"})


def ask_health(default=0.5):
    return tuning_points.value("min_health", default, facts={"score": 0.9})


def ctx_facts(**extra):
    from acq4.experiment.context import ExecutionContext

    return {"ctx": ExecutionContext(), **extra}


def test_no_decision_until_asked(root, arm):
    m = ValueMut("m", "cell", "min_health")
    _, ledger = arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root), survey_id=None)
    assert c.decisions == {}
    assert ledger.decision_lines() == []
    assert m.eligible_calls == 0
    assert ask_health() in (1, 2)
    assert set(c.decisions) == {"m"}
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_decision_sticky_within_unit(root, arm):
    m = ValueMut("m", "cell", "min_health", conditions=list(range(10)))
    _, ledger = arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    first = ask_health()
    assert all(ask_health() == first for _ in range(5))
    assert len(ledger.decision_lines()) == 1
    assert c.fired == {"m": {"min_health": 6}}
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_new_cell_unit_gets_fresh_decision(root, arm):
    m = ValueMut("m", "cell", "min_health")
    _, ledger = arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c1 = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c1"))
    first = ask_health()
    tuning_points.close_unit(c1)
    c2 = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c2"))
    second = ask_health()
    tuning_points.close_unit(c2)
    tuning_points.close_unit(s)
    assert {first, second} == {1, 2}
    assert [line["unit_id"] for line in ledger.decision_lines()] == [c1.id, c2.id]


def test_balance_alternates_across_cells(root, arm):
    m = ValueMut("m", "cell", "min_health", conditions=["x", "y"])
    arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    counts = {"x": 0, "y": 0}
    for i in range(6):
        c = tuning_points.open_unit("cell", cell_dir=make_cell(root, f"c{i}"))
        counts[ask_health()] += 1
        tuning_points.close_unit(c)
        assert abs(counts["x"] - counts["y"]) <= 1
    tuning_points.close_unit(s)
    assert counts == {"x": 3, "y": 3}


def test_ineligible_returns_default_and_sticks(root, arm):
    m = ValueMut("m", "cell", "min_health", eligible=False)
    _, ledger = arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    assert ask_health(0.5) == 0.5
    assert ask_health(0.5) == 0.5
    assert m.eligible_calls == 1
    assert c.decisions == {"m": INELIGIBLE}
    assert c.fired == {}
    (line,) = ledger.decision_lines()
    assert line["eligible"] is False
    assert "condition" not in line
    assert line["slice_id"] == s.id
    with pytest.warns(TuningPointWarning, match="'m'"):
        tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_ineligible_not_counted_toward_balance(root, arm):
    eligible = ValueMut("m", "cell", "min_health", conditions=["x", "y"])
    _, ledger = arm([eligible])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c0"))
    first = ask_health()
    tuning_points.close_unit(c)
    eligible._eligible = False
    for i in range(1, 4):
        c = tuning_points.open_unit("cell", cell_dir=make_cell(root, f"c{i}"))
        assert ask_health(0.5) == 0.5
        tuning_points.close_unit(c)
    eligible._eligible = True
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c4"))
    second = ask_health()
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert {first, second} == {"x", "y"}


def test_survey_decision_inherited_by_cell_via_survey_id(root, arm):
    m = ValueMut("health", "survey", "min_health", conditions=[0.6])
    arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    with tuning_points.unit("survey") as survey:
        assert ask_health() == 0.6
    assert survey.closed and survey.parent is s
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root), survey_id=survey.id)
    assert ask_health() == 0.6
    summary = tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert summary["survey_id"] == survey.id
    assert summary["conditions"] == {"health": 0.6}
    assert summary["assigned_by"] == {"health": "survey"}
    assert survey.fired == {"health": {"min_health": 2}}
    assert summary["fired"] == {}


def test_slice_decision_inherited_by_cell(root, arm):
    m = ValueMut("detector", "slice", "pipette_detector_class", conditions=["A"])
    arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    assert tuning_points.value("pipette_detector_class", "default") == "A"
    summary = tuning_points.close_unit(c)
    assert s.decisions == {"detector": "A"}
    assert summary["conditions"] == {"detector": "A"}
    assert summary["assigned_by"] == {"detector": "slice"}
    tuning_points.close_unit(s)


def test_cell_opened_before_slice_close_keeps_old_slice(root, arm):
    m = ValueMut("detector", "slice", "pipette_detector_class", conditions=["A"])
    arm([m])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with pytest.warns(TuningPointWarning, match="'detector'"):
        tuning_points.close_unit(old)
    new = tuning_points.open_unit("slice", slice_dir=make_slice(root, "new"))
    assert tuning_points.current_slice() is new
    assert tuning_points.value("pipette_detector_class", "default") == "A"
    assert set(old.decisions) == {"detector"}
    assert new.decisions == {}
    summary = tuning_points.close_unit(c)
    assert summary["conditions"] == {"detector": "A"}
    tuning_points.close_unit(new)


def test_closed_slice_refuses_children(root, arm):
    arm([])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    tuning_points.close_unit(s)
    with pytest.raises(TuningPointError):
        tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with pytest.raises(TuningPointError):
        tuning_points.open_unit("survey")


def test_reopen_slice_restores_decision(root, arm):
    m = ValueMut(
        "detector", "slice", "pipette_detector_class", conditions=list(range(10))
    )
    ledger = MemoryLedger(random.Random(0))
    slice_dir = make_slice(root)
    arm([m], ledger=ledger)
    s = tuning_points.open_unit("slice", slice_dir=slice_dir)
    first = tuning_points.value("pipette_detector_class", None)
    tuning_points.close_unit(s)
    tuning_points.uninstall()

    m2 = ValueMut(
        "detector", "slice", "pipette_detector_class", conditions=list(range(10))
    )
    arm([m2], ledger=ledger)
    s2 = tuning_points.open_unit("slice", slice_dir=slice_dir)
    assert s2.decisions == {"detector": first}
    assert tuning_points.value("pipette_detector_class", None) == first
    assert m2.eligible_calls == 0
    assert len(ledger.decision_lines()) == 1
    tuning_points.close_unit(s2)


def test_unit_open_close_lines_for_every_kind(root, arm):
    _, ledger = arm([])
    slice_dir = make_slice(root)
    s = tuning_points.open_unit("slice", slice_dir=slice_dir)
    with tuning_points.unit("survey") as survey:
        pass
    cell_dir = make_cell(slice_dir)
    c = tuning_points.open_unit("cell", cell_dir=cell_dir, survey_id=survey.id)
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)

    unit_lines = [l for l in ledger.lines if l["event"] in ("unit_open", "unit_close")]
    assert [(l["event"], l["unit"]) for l in unit_lines] == [
        ("unit_open", "slice"),
        ("unit_open", "survey"),
        ("unit_close", "survey"),
        ("unit_open", "cell"),
        ("unit_close", "cell"),
        ("unit_close", "slice"),
    ]
    expected_ids = {"slice": s.id, "survey": survey.id, "cell": c.id}
    expected_parents = {"slice": None, "survey": s.id, "cell": s.id}
    for line in unit_lines:
        assert line["unit_id"] == expected_ids[line["unit"]]
        assert line["parent_id"] == expected_parents[line["unit"]]
        assert line["slice_id"] == s.id
        assert line["slice_dir"] == slice_dir.name()
        assert line["thread"] == threading.current_thread().name
        assert isinstance(line["t"], str)
    survey_close = unit_lines[2]
    assert survey_close["fired"] == {}
    assert survey_close["asked"] == []
    assert s.id == slice_dir.info()["__uuid__"]
    assert c.id == cell_dir.info()["__uuid__"]


def test_outside_unit_returns_default_and_warns_once(arm):
    m = ValueMut("m", "cell", "min_health")
    _, ledger = arm([m])
    with pytest.warns(TuningPointWarning, match="min_health") as record:
        assert ask_health(0.5) == 0.5
        assert ask_health(0.5) == 0.5
    assert len(record) == 1
    assert ledger.decision_lines() == []
    assert m.eligible_calls == 0


def test_never_fired_warns_at_unit_close_until_first_fire(root, arm):
    m = ValueMut("m", "cell", "min_health")
    arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    for i in range(2):
        c = tuning_points.open_unit("cell", cell_dir=make_cell(root, f"a{i}"))
        with pytest.warns(TuningPointWarning, match=r"'m'.*min_health") as record:
            tuning_points.close_unit(c)
        assert len(record) == 1
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "fired"))
    ask_health()
    tuning_points.close_unit(c)
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "after"))
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_scope_enter_exit_order(root, arm):
    events = []
    first = ScopeMut("first", "cell", "patching", events, conditions=["a"])
    second = ScopeMut("second", "cell", "patching", events, conditions=["b"])
    arm([first, second])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with tuning_points.scope("patching", facts=ctx_facts()):
        events.append("body")
    assert events == [
        ("enter", "first", "a"),
        ("enter", "second", "b"),
        "body",
        ("exit", "second", "b"),
        ("exit", "first", "a"),
    ]
    assert c.fired == {"first": {"patching": 1}, "second": {"patching": 1}}
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_scope_skips_ineligible_mutator(root, arm):
    events = []
    on = ScopeMut("on", "cell", "patching", events, conditions=["a"])
    off = ScopeMut("off", "cell", "patching", events, eligible=False)
    arm([off, on])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with tuning_points.scope("patching", facts=ctx_facts()):
        events.append("body")
    assert events == [("enter", "on", "a"), "body", ("exit", "on", "a")]
    assert c.decisions == {"off": INELIGIBLE, "on": "a"}
    with pytest.warns(TuningPointWarning, match="'off'"):
        summary = tuning_points.close_unit(c)
    assert summary["conditions"] == {"on": "a"}
    tuning_points.close_unit(s)


def test_log_action_called_when_ctx_fact_present(root, arm):
    from acq4.experiment.context import ExecutionContext

    entries = []
    ctx = ExecutionContext(on_log_action=entries.append)
    events = []
    arm([ScopeMut("seal", "cell", "patching", events, conditions=[30.0])])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with tuning_points.scope("patching", facts={"ctx": ctx}):
        pass
    with tuning_points.scope("patching", facts={"ctx": ctx}):
        pass
    assert [e.name for e in entries] == ["Assign Condition: seal=30.0"]
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)


def test_summary_shape_matches_metadata_contract(root, arm):
    events = []
    seal = ScopeMut("seal_timeout", "cell", "patching", events, conditions=[30.0])
    health = ValueMut("min_health", "survey", "min_health", conditions=[0.7])
    _, _ = arm([seal, health], run_id="2026-11-14-seal-health")
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    with tuning_points.unit("survey") as survey:
        ask_health()
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root), survey_id=survey.id)
    for _ in range(2):
        with tuning_points.scope("patching", facts=ctx_facts()):
            pass
    summary = tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert summary == {
        "run_id": "2026-11-14-seal-health",
        "survey_id": survey.id,
        "conditions": {"seal_timeout": 30.0, "min_health": 0.7},
        "assigned_by": {"seal_timeout": "cell", "min_health": "survey"},
        "fired": {"seal_timeout": {"patching": 2}},
    }


def test_summary_empty_when_nothing_applied():
    assert tuning_points.close_unit(None) == {}


@pytest.mark.parametrize("eligible", [False, None], ids=["ineligible", "never_asked"])
def test_armed_cell_gets_block_when_no_condition_applies(root, arm, eligible):
    seen = []

    def hook(cell_dir):
        seen.append(cell_dir)
        return {"protocol_sha256": "abc"}

    m = ValueMut("m", "cell", "min_health", eligible=bool(eligible))
    arm([m], cell_close_hook=hook, run_id="run-x")
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    cell_dir = make_cell(root)
    c = tuning_points.open_unit("cell", cell_dir=cell_dir, survey_id="sv")
    if eligible is not None:
        assert ask_health(0.5) == 0.5
    with pytest.warns(TuningPointWarning, match="'m'"):
        summary = tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert summary == {
        "run_id": "run-x",
        "survey_id": "sv",
        "conditions": {},
        "assigned_by": {},
        "fired": {},
        "provenance": {"protocol_sha256": "abc"},
    }
    assert seen == [cell_dir]


def test_inherited_asks_recorded_on_asking_unit(root, arm):
    health = ValueMut("health", "survey", "min_health", conditions=[0.6])
    detector = ValueMut("detector", "slice", "pipette_detector_class", conditions=["A"])
    _, ledger = arm([health, detector])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    with tuning_points.unit("survey") as survey:
        ask_health()
        tuning_points.value("pipette_detector_class", None)
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root), survey_id=survey.id)
    ask_health()
    tuning_points.value("pipette_detector_class", None)
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    closes = {l["unit"]: l for l in ledger.lines if l["event"] == "unit_close"}
    assert closes["cell"]["asked"] == ["detector", "health"]
    assert closes["survey"]["asked"] == ["detector", "health"]
    assert closes["slice"]["asked"] == ["detector"]


def test_open_slice_while_slice_open_raises(root, arm):
    arm([])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root, "a"))
    with pytest.raises(TuningPointError):
        tuning_points.open_unit("slice", slice_dir=make_slice(root, "b"))
    assert tuning_points.current_slice() is s
    tuning_points.close_unit(s)


def test_eligible_may_reenter_tuning_points(root, arm):
    detector = ValueMut("detector", "slice", "pipette_detector_class", conditions=["A"])

    class Reentrant(ValueMut):
        def eligible(self, facts):
            return tuning_points.value("pipette_detector_class", None) == "A"

    m = Reentrant("m", "cell", "min_health", conditions=[1])
    arm([detector, m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    assert ask_health() == 1
    summary = tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert summary["conditions"] == {"detector": "A", "m": 1}


def test_worker_cell_keeps_old_slice_across_gui_slice_change(root, arm):
    detector = ValueMut(
        "detector", "slice", "pipette_detector_class", conditions=["A", "B"]
    )
    arm([detector])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    cell_open = threading.Event()
    slice_changed = threading.Event()
    results = {}
    errors = []

    def worker():
        try:
            c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c0"))
            cell_open.set()
            assert slice_changed.wait(10)
            tuning_points.value("pipette_detector_class", None)
            results["first"] = tuning_points.close_unit(c)
            c = tuning_points.open_unit("cell", cell_dir=make_cell(root, "c1"))
            tuning_points.value("pipette_detector_class", None)
            results["second"] = tuning_points.close_unit(c)
        except BaseException as exc:
            errors.append(exc)
            cell_open.set()

    thread = threading.Thread(target=worker, name="worker")
    thread.start()
    assert cell_open.wait(10)
    with pytest.warns(TuningPointWarning, match="'detector'"):
        tuning_points.close_unit(old)
    new = tuning_points.open_unit("slice", slice_dir=make_slice(root, "new"))
    slice_changed.set()
    thread.join(10)
    assert not thread.is_alive()
    assert errors == []
    tuning_points.close_unit(new)
    assert results["first"]["conditions"] == {"detector": old.decisions["detector"]}
    assert results["second"]["conditions"] == {"detector": new.decisions["detector"]}
    assert old.decisions["detector"] != new.decisions["detector"]


def test_cell_close_hook_merged_as_provenance(root, arm):
    seen = []

    def hook(cell_dir):
        seen.append(cell_dir)
        return {"protocol_sha256": "abc"}

    arm([ValueMut("m", "cell", "min_health", conditions=[1])], cell_close_hook=hook)
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    cell_dir = make_cell(root)
    c = tuning_points.open_unit("cell", cell_dir=cell_dir)
    ask_health()
    summary = tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    assert seen == [cell_dir]
    assert summary["provenance"] == {"protocol_sha256": "abc"}


def test_second_install_raises(arm):
    runtime, ledger = arm([])
    assert tuning_points.installed() is runtime
    with pytest.raises(TuningPointError):
        tuning_points.install(Runtime("other", [], ledger))
    assert tuning_points.installed() is runtime


def test_open_unit_returns_none_when_nothing_installed(root):
    assert tuning_points.open_unit("slice", slice_dir=make_slice(root)) is None
    with tuning_points.unit("survey") as u:
        assert u is None
    assert tuning_points.current_slice() is None


def test_every_ledger_line_carries_run_id(root, arm):
    m = ValueMut("m", "cell", "min_health")
    _, ledger = arm([m])
    s = tuning_points.open_unit("slice", slice_dir=make_slice(root))
    with tuning_points.unit("survey"):
        pass
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    ask_health()
    tuning_points.close_unit(c)
    tuning_points.close_unit(s)
    events = {line["event"] for line in ledger.lines}
    assert {"unit_open", "unit_close", "decision"} <= events
    assert all(line["run_id"] == "run-1" for line in ledger.lines)


def test_outside_unit_warning_is_a_ledger_line(arm):
    _, ledger = arm([ValueMut("m", "cell", "min_health")])
    with pytest.warns(TuningPointWarning):
        ask_health()
        ask_health()
    (line,) = [l for l in ledger.lines if l["event"] == "warning"]
    assert line == {
        "event": "warning",
        "kind": "outside_unit",
        "point": "min_health",
        "mutator": "m",
        "run_id": "run-1",
        "slice_id": None,
        "slice_dir": None,
        "t": line["t"],
    }
    assert isinstance(line["t"], str)


def test_outside_unit_warning_line_names_the_open_slice(root, arm):
    _, ledger = arm([ValueMut("m", "survey", "min_health")])
    slice_dir = make_slice(root)
    s = tuning_points.open_unit("slice", slice_dir=slice_dir)
    c = tuning_points.open_unit("cell", cell_dir=make_cell(slice_dir))
    with pytest.warns(TuningPointWarning):
        ask_health()
        tuning_points.close_unit(c)
    (line,) = [l for l in ledger.lines if l.get("kind") == "outside_unit"]
    assert (line["slice_id"], line["slice_dir"]) == (s.id, slice_dir.name())
    tuning_points.close_unit(s)


def test_never_fired_warning_is_a_ledger_line(root, arm):
    _, ledger = arm([ValueMut("m", "cell", "min_health")])
    slice_dir = make_slice(root)
    s = tuning_points.open_unit("slice", slice_dir=slice_dir)
    c = tuning_points.open_unit("cell", cell_dir=make_cell(slice_dir))
    with pytest.warns(TuningPointWarning, match="'m'"):
        tuning_points.close_unit(c)
    (line,) = [l for l in ledger.lines if l["event"] == "warning"]
    assert line == {
        "event": "warning",
        "kind": "never_fired",
        "mutator": "m",
        "unit": "cell",
        "unit_id": c.id,
        "run_id": "run-1",
        "slice_id": s.id,
        "slice_dir": slice_dir.name(),
        "t": line["t"],
    }
    tuning_points.close_unit(s)


def _unit_events(ledger):
    return [
        (l["event"], l["unit"], l["unit_id"])
        for l in ledger.lines
        if l["event"] in ("unit_open", "unit_close")
    ]


def test_replace_slice_closes_the_old_and_opens_the_new(root, arm):
    _, ledger = arm([])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    new_dir = make_slice(root, "new")
    new = tuning_points.replace_slice(old, new_dir)
    assert old.closed and not new.closed
    assert tuning_points.current_slice() is new
    assert new.id == new_dir.info()["__uuid__"]
    assert _unit_events(ledger) == [
        ("unit_open", "slice", old.id),
        ("unit_close", "slice", old.id),
        ("unit_open", "slice", new.id),
    ]
    tuning_points.close_unit(new)


def test_replace_slice_keeps_a_cell_opened_before_the_swap_on_the_old_slice(root, arm):
    m = ValueMut("detector", "slice", "pipette_detector_class", conditions=["A"])
    arm([m])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    c = tuning_points.open_unit("cell", cell_dir=make_cell(root))
    with pytest.warns(TuningPointWarning, match="'detector'"):
        new = tuning_points.replace_slice(old, make_slice(root, "new"))
    assert tuning_points.value("pipette_detector_class", "default") == "A"
    assert set(old.decisions) == {"detector"}
    assert new.decisions == {}
    summary = tuning_points.close_unit(c)
    assert summary["assigned_by"] == {"detector": "slice"}
    tuning_points.close_unit(new)


def test_replace_slice_with_no_old_unit_opens_the_new(root, arm):
    _, ledger = arm([])
    new = tuning_points.replace_slice(None, make_slice(root))
    assert tuning_points.current_slice() is new
    assert _unit_events(ledger) == [("unit_open", "slice", new.id)]
    tuning_points.close_unit(new)


def test_replace_slice_that_cannot_open_the_new_leaves_the_old_open(root, arm):
    _, ledger = arm([])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    no_uuid = make_slice(root, "no_uuid")
    strip_uuid(no_uuid)
    with pytest.raises(KeyError):
        tuning_points.replace_slice(old, no_uuid)
    assert not old.closed
    assert tuning_points.current_slice() is old
    assert _unit_events(ledger) == [("unit_open", "slice", old.id)]
    tuning_points.close_unit(old)


def test_replace_slice_returns_none_when_nothing_installed(root):
    assert tuning_points.replace_slice(None, make_slice(root)) is None


def test_open_slice_still_refused_while_a_slice_is_open_after_a_replace(root, arm):
    arm([])
    old = tuning_points.open_unit("slice", slice_dir=make_slice(root, "old"))
    new = tuning_points.replace_slice(old, make_slice(root, "new"))
    with pytest.raises(TuningPointError, match="still open"):
        tuning_points.open_unit("slice", slice_dir=make_slice(root, "other"))
    tuning_points.close_unit(new)
