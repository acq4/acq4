"""Tests for the per-condition trial summary, its validation, and the files report.write produces."""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from acq4.modules.Autopatch.analysis import autopatch_log as al
from acq4.modules.Autopatch.analysis import autopatch_metrics as am
from acq4.modules.Autopatch.performance_tuning import join, record, report
from acq4.modules.Autopatch.performance_tuning.ledger import MIRROR_NAME

from .conftest import RUN_ID

SEAL = {"class": "SealTimeout", "unit": "cell", "conditions": [30.0, 60.0]}
HEALTH = {"class": "MinHealth", "unit": "survey", "conditions": [0.5, 0.7]}


def make_trial(tmp_path, primary="seal_timeout", mutators=None, quality_gate=None):
    return record.Trial(
        dir=tmp_path / "trial",
        id="001",
        slug="seal-timeout",
        run_id=RUN_ID,
        title="Seal timeout",
        status="collecting",
        created="2026-11-13",
        primary_factor=primary,
        hypothesis="longer is better\n",
        protocol="acq4/modules/Autopatch/example_protocols/_example_patch.py",
        mutators=mutators or {"seal_timeout": dict(SEAL)},
        quality_gate=quality_gate,
    )


def _whole_cell_attempt(source, access, ibase, rin):
    tp = {
        "event_time": 30.0,
        "access_resistance": access,
        "baseline_current": ibase,
        "input_resistance": rin,
        "capacitance": 10e-12,
    }
    return al.Attempt(
        source=source,
        device="PatchPipette1",
        index=0,
        start_time=0.0,
        end_time=30.0,
        states=[
            (0.0, "approach"),
            (10.0, "seal"),
            (20.0, "cell attached"),
            (25.0, "whole cell"),
        ],
        test_pulses=[tp],
    )


def hand_frame(cells):
    """A joined frame built from attempts in code; each cell dict names its ids, conditions and break-in numbers."""
    attempts = [
        _whole_cell_attempt(
            f"/rig/{c['cell_id']}/MultiPatch_000.log",
            c.get("access", 10e6),
            c.get("ibase", -50e-12),
            c.get("rin", 200e6),
        )
        for c in cells
    ]
    frame = am.attempts_to_dataframe(attempts)
    for column in join.ID_COLUMNS:
        frame[column] = [c.get(column, f"{column}-{i}") for i, c in enumerate(cells)]
    names = sorted({name for c in cells for name in c.get("conditions", {})})
    for name in names:
        frame[name] = join.object_column(
            [c.get("conditions", {}).get(name) for c in cells]
        )
    for column in join.PROVENANCE_COLUMNS:
        frame[column] = join.object_column([c.get(column) for c in cells])
    return frame


T0 = datetime(2026, 11, 14, tzinfo=timezone.utc)


def _iso(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


def _span(unit, unit_id, t0, t1, parent_id=None, run_id=RUN_ID):
    common = {
        "unit": unit,
        "unit_id": unit_id,
        "parent_id": parent_id,
        "run_id": run_id,
    }
    return [
        {"event": "unit_open", "t": _iso(t0), **common},
        {"event": "unit_close", "t": _iso(t1), "asked": [], **common},
    ]


def _by_condition(summary):
    return {entry["condition"]: entry for entry in summary["conditions"]}


def _dataset_spans(dataset):
    """Ledger cell spans for c1..c4 (c5 has none, so it falls back to its 60 s attempt)."""
    seconds = {"c1": 120, "c2": 180, "c3": 300, "c4": 420}
    lines = []
    for key, length in seconds.items():
        cell_id = dataset["cells"][key].info()["__uuid__"]
        lines += _span("cell", cell_id, 1000, 1000 + length)
    return lines


def test_report_arithmetic_on_the_dataset(dataset, tmp_path):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    summary = report.summarize(frame, make_trial(tmp_path), _dataset_spans(dataset))
    by = _by_condition(summary)
    assert summary["schema_version"] == report.SUMMARY_SCHEMA_VERSION
    assert summary["no_units_assigned"] is False

    thirty = by[30.0]
    assert (thirty["n_units"], thirty["n_cells"], thirty["n_attempts"]) == (3, 3, 3)
    assert thirty["n_whole_cell"] == 2
    assert thirty["minutes_per_whole_cell"] == pytest.approx((120 + 300 + 60) / 60 / 2)
    assert thirty["minutes_fallback_cells"] == 1
    assert thirty["whole_cells_per_slice"] == pytest.approx(1.0)
    assert thirty["quality"]["access_resistance"]["median"] == pytest.approx(15e6)
    assert thirty["quality"]["access_resistance"]["iqr"] == pytest.approx(5e6)
    assert thirty["n_passing_gate"] == 2
    assert [s["count"] for s in thirty["funnel"]] == [3, 3, 2, 2]

    sixty = by[60.0]
    assert sixty["n_whole_cell"] == 1
    assert sixty["minutes_per_whole_cell"] == pytest.approx((180 + 420) / 60 / 1)
    assert sixty["minutes_fallback_cells"] == 0
    assert sixty["whole_cells_per_slice"] == pytest.approx(0.5)
    assert sixty["n_passing_gate"] == 0
    assert [s["count"] for s in sixty["funnel"]] == [2, 2, 1, 1]


def test_condition_without_whole_cells_has_no_minutes_per_whole_cell(tmp_path):
    frame = hand_frame([{"cell_id": "a", "conditions": {"seal_timeout": 30.0}}])
    summary = report.summarize(frame, make_trial(tmp_path), [])
    assert _by_condition(summary)[60.0]["minutes_per_whole_cell"] is None
    assert _by_condition(summary)[60.0]["n_cells"] == 0


def test_survey_unit_counts_surveys_and_warns(tmp_path):
    cells = [
        {
            "cell_id": f"c{i}",
            "survey_id": "s1" if i < 3 else "s2",
            "conditions": {"min_health": 0.5},
        }
        for i in range(5)
    ]
    trial = make_trial(
        tmp_path, primary="min_health", mutators={"min_health": dict(HEALTH)}
    )
    summary = report.summarize(hand_frame(cells), trial, [])
    half = _by_condition(summary)[0.5]
    assert (half["n_units"], half["n_cells"]) == (2, 5)
    assert any("2 survey units" in w for w in summary["warnings"])


def test_gate_boundaries_are_inclusive(tmp_path):
    cond = {"seal_timeout": 30.0}
    cells = [
        {"cell_id": "at_access_max", "access": 25e6, "conditions": cond},
        {"cell_id": "over_access_max", "access": 25.1e6, "conditions": cond},
        {"cell_id": "at_holding_min", "ibase": -200e-12, "conditions": cond},
        {"cell_id": "under_holding_min", "ibase": -201e-12, "conditions": cond},
        {"cell_id": "at_rin_min", "rin": 50e6, "conditions": cond},
        {"cell_id": "under_rin_min", "rin": 49e6, "conditions": cond},
    ]
    summary = report.summarize(hand_frame(cells), make_trial(tmp_path), [])
    assert _by_condition(summary)[30.0]["n_passing_gate"] == 3


def test_trial_gate_overrides_the_default(tmp_path):
    cells = [{"cell_id": "a", "access": 30e6, "conditions": {"seal_timeout": 30.0}}]
    trial = make_trial(tmp_path, quality_gate={"access_resistance_max": 40e6})
    summary = report.summarize(hand_frame(cells), trial, [])
    assert summary["quality_gate"] == {
        **report.DEFAULT_GATE,
        "access_resistance_max": 40e6,
    }
    assert _by_condition(summary)[30.0]["n_passing_gate"] == 1


def test_partial_trial_gate_keeps_the_other_default_limits(tmp_path):
    cond = {"seal_timeout": 30.0}
    cells = [
        {"cell_id": "a", "access": 30e6, "conditions": cond},
        {"cell_id": "b", "access": 30e6, "rin": 40e6, "conditions": cond},
    ]
    trial = make_trial(tmp_path, quality_gate={"access_resistance_max": 40e6})
    summary = report.summarize(hand_frame(cells), trial, [])
    assert summary["quality_gate"]["input_resistance_min"] == 50e6
    assert _by_condition(summary)[30.0]["n_passing_gate"] == 1


def test_no_units_assigned(dataset, tmp_path):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    trial = make_trial(
        tmp_path,
        primary="min_health",
        mutators={"seal_timeout": dict(SEAL), "min_health": dict(HEALTH)},
    )
    summary = report.summarize(frame, trial, [])
    assert summary["no_units_assigned"] is True
    assert all(entry["n_cells"] == 0 for entry in summary["conditions"])
    assert any("'min_health' never fired" in w for w in summary["warnings"])
    report.write(frame, trial, tmp_path / "out", [])
    assert (tmp_path / "out" / "report.txt").read_text().splitlines()[
        0
    ] == "no units assigned"


def _decision(mutator, unit, unit_id, eligible=True, condition=30.0, run_id=RUN_ID):
    line = {
        "event": "decision",
        "mutator": mutator,
        "unit": unit,
        "unit_id": unit_id,
        "run_id": run_id,
    }
    if eligible:
        line["condition"] = condition
    else:
        line["eligible"] = False
    return line


def _split_case(tmp_path):
    cells = [
        {"cell_id": f"c{i}", "conditions": {"min_health": 0.5 if i < 4 else 0.7}}
        for i in range(8)
    ]
    eligible = [True, True, True, True, True, True, False, False]
    lines = [
        _decision("seal_timeout", "cell", f"c{i}", ok) for i, ok in enumerate(eligible)
    ]
    lines += [
        _decision("min_health", "survey", "s1"),
        _decision("min_health", "survey", "s2"),
    ]
    trial = make_trial(
        tmp_path, mutators={"seal_timeout": dict(SEAL), "min_health": dict(HEALTH)}
    )
    return hand_frame(cells), trial, lines


def test_eligibility_split_is_flagged(tmp_path):
    frame, trial, lines = _split_case(tmp_path)
    summary = report.summarize(frame, trial, lines)
    seal = summary["eligibility"]["seal_timeout"]
    assert (seal["eligible"], seal["ineligible"]) == (6, 2)
    assert seal["rate"] == pytest.approx(0.75)
    assert seal["by"]["min_health"]["0.5"]["rate"] == pytest.approx(1.0)
    assert seal["by"]["min_health"]["0.7"]["rate"] == pytest.approx(0.5)
    assert seal["split"] is True
    health = summary["eligibility"]["min_health"]
    assert health["rate"] == pytest.approx(1.0)
    assert health["by"] == {"seal_timeout": {}}
    assert health["split"] is False


def test_eligibility_split_respects_the_margin(tmp_path):
    frame, trial, lines = _split_case(tmp_path)
    summary = report.summarize(frame, trial, lines, margin=0.6)
    assert summary["eligibility"]["seal_timeout"]["split"] is False


def test_mutator_with_no_decisions_has_no_eligibility_rate(tmp_path):
    frame, trial, _ = _split_case(tmp_path)
    summary = report.summarize(frame, trial, [])
    assert summary["eligibility"]["seal_timeout"]["rate"] is None


def _close(unit, unit_id, asked, run_id=RUN_ID):
    return {
        "event": "unit_close",
        "unit": unit,
        "unit_id": unit_id,
        "asked": asked,
        "run_id": run_id,
    }


def test_asked_rate_counts_closed_units_of_the_mutator_kind(tmp_path):
    frame, trial, _ = _split_case(tmp_path)
    lines = [
        _close("cell", "c0", ["seal_timeout", "min_health"]),
        _close("cell", "c1", ["seal_timeout"]),
        _close("cell", "c2", ["seal_timeout"]),
        _close("cell", "c3", []),
        _close("survey", "s1", ["min_health"]),
        _close("survey", "s2", []),
        {
            "event": "unit_open",
            "unit": "cell",
            "unit_id": "c4",
            "run_id": RUN_ID,
            "t": _iso(0),
        },
    ]
    summary = report.summarize(frame, trial, lines)
    assert summary["asked_rate"]["seal_timeout"] == {
        "asked": 3,
        "closed": 4,
        "rate": 0.75,
    }
    assert summary["asked_rate"]["min_health"] == {"asked": 1, "closed": 2, "rate": 0.5}


def test_provenance_summary_counts_cells_per_version(tmp_path):
    cond = {"seal_timeout": 30.0}
    cells = [
        {
            "cell_id": "a",
            "conditions": cond,
            "acq4_sha": "s1",
            "acq4_dirty": False,
            "protocol_sha256": "p1",
        },
        {
            "cell_id": "b",
            "conditions": cond,
            "acq4_sha": "s1",
            "acq4_dirty": False,
            "protocol_sha256": "p1",
        },
        {
            "cell_id": "c",
            "conditions": cond,
            "acq4_sha": "s2",
            "acq4_dirty": True,
            "protocol_sha256": "p2",
        },
    ]
    summary = report.summarize(hand_frame(cells), make_trial(tmp_path), [])
    prov = summary["provenance"]
    assert prov["protocol_sha256"] == [
        {"value": "p1", "n_cells": 2},
        {"value": "p2", "n_cells": 1},
    ]
    assert [(v["sha"], v["dirty"], v["n_cells"]) for v in prov["acq4"]] == [
        ("s1", False, 2),
        ("s2", True, 1),
    ]
    assert any("2 protocol versions" in w for w in summary["warnings"])
    assert any("2 acq4 versions" in w for w in summary["warnings"])


def test_write_produces_valid_files(dataset, tmp_path):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    out = tmp_path / "out"
    summary = report.write(frame, make_trial(tmp_path), out, [])

    def no_nan(token):
        raise AssertionError(f"non-JSON constant {token}")

    on_disk = json.loads((out / "summary.json").read_text(), parse_constant=no_nan)
    assert on_disk == json.loads(json.dumps(summary))
    assert report.validate_summary(on_disk) == []
    assert (out / "report.txt").read_text().strip()
    assert (out / "metric_pair.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_write_reads_slice_mirrors_when_no_ledger_lines_are_given(dataset, tmp_path):
    c1 = dataset["cells"]["c1"].info()["__uuid__"]
    path = os.path.join(dataset["slices"]["A"].name(), MIRROR_NAME)
    with open(path, "w") as f:
        f.write(json.dumps(_close("cell", c1, ["seal_timeout"])) + "\n")
    trial = make_trial(tmp_path)
    trial.dir = Path(dataset["data_dir"]).parent
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    summary = report.write(frame, trial, tmp_path / "out")
    assert summary["asked_rate"]["seal_timeout"]["rate"] == 1.0


def test_validate_summary_rejects_a_missing_key(dataset, tmp_path):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    summary = report.summarize(frame, make_trial(tmp_path), [])
    del summary["warnings"]
    assert any("warnings" in e for e in report.validate_summary(summary))
    summary = report.summarize(frame, make_trial(tmp_path), [])
    del summary["conditions"][0]["minutes_per_whole_cell"]
    assert any("minutes_per_whole_cell" in e for e in report.validate_summary(summary))


def test_validate_summary_rejects_nan(dataset, tmp_path):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    summary = report.summarize(frame, make_trial(tmp_path), [])
    summary["conditions"][0]["minutes_per_whole_cell"] = float("nan")
    assert report.validate_summary(summary)


def test_provenance_with_no_acq4_checkout(tmp_path):
    cells = [
        {"cell_id": "a", "conditions": {"seal_timeout": 30.0}, "protocol_sha256": "p1"}
    ]
    summary = report.summarize(hand_frame(cells), make_trial(tmp_path), [])
    assert summary["provenance"]["acq4"] == [
        {"sha": None, "branch": None, "dirty": None, "n_cells": 1}
    ]
    assert report.validate_summary(summary) == []


def test_summarize_ignores_lines_from_other_runs(tmp_path):
    frame, trial, lines = _split_case(tmp_path)
    lines = lines + [
        _decision("seal_timeout", "cell", "c0", eligible=False, run_id="run-b"),
        _close("cell", "c0", ["seal_timeout"], run_id="run-b"),
    ]
    summary = report.summarize(frame, trial, lines)
    assert summary["eligibility"]["seal_timeout"]["ineligible"] == 2
    assert summary["asked_rate"]["seal_timeout"]["closed"] == 0


def _warning(kind, mutator, point=None, run_id=RUN_ID):
    line = {"event": "warning", "kind": kind, "mutator": mutator, "run_id": run_id}
    if point is not None:
        line["point"] = point
    return line


def test_runtime_warnings_are_counted_by_kind_mutator_and_point(tmp_path):
    frame, trial, lines = _split_case(tmp_path)
    lines = lines + [
        _warning("outside_unit", "min_health", "min_health"),
        _warning("outside_unit", "min_health", "min_health"),
        _warning("never_fired", "seal_timeout"),
        _warning("never_fired", "seal_timeout"),
        _warning("never_fired", "seal_timeout"),
        _warning("never_fired", "seal_timeout", run_id="run-b"),
    ]
    summary = report.summarize(frame, trial, lines)
    assert summary["runtime_warnings"] == [
        {"kind": "never_fired", "mutator": "seal_timeout", "point": None, "count": 3},
        {
            "kind": "outside_unit",
            "mutator": "min_health",
            "point": "min_health",
            "count": 2,
        },
    ]
    text = report.format_text(summary)
    assert "never_fired seal_timeout x3" in text


def test_never_fired_comes_from_eligible_ledger_decisions(tmp_path):
    cells = [{"cell_id": "a", "conditions": {"seal_timeout": 30.0}}]
    trial = make_trial(
        tmp_path, mutators={"seal_timeout": dict(SEAL), "min_health": dict(HEALTH)}
    )
    lines = [
        _decision("seal_timeout", "cell", "a", eligible=False),
        _decision("min_health", "survey", "s1", condition=0.5),
    ]
    summary = report.summarize(hand_frame(cells), trial, lines)
    assert any("'seal_timeout' never fired" in w for w in summary["warnings"])
    assert not any("'min_health' never fired" in w for w in summary["warnings"])


def _factorial_cells():
    plan = [
        ("c0", 30.0, 0.5),
        ("c1", 30.0, 0.5),
        ("c2", 30.0, 0.7),
        ("c3", 30.0, None),
        ("c4", 60.0, 0.5),
        ("c5", 60.0, None),
    ]
    cells = []
    for cell_id, seal, health in plan:
        conditions = {"seal_timeout": seal}
        if health is not None:
            conditions["min_health"] = health
        cells.append({"cell_id": cell_id, "slice_id": "S", "conditions": conditions})
    return cells


def _two_factor_trial(tmp_path):
    return make_trial(
        tmp_path, mutators={"seal_timeout": dict(SEAL), "min_health": dict(HEALTH)}
    )


def test_covariates_count_cells_per_condition_pair(tmp_path):
    summary = report.summarize(
        hand_frame(_factorial_cells()), _two_factor_trial(tmp_path), []
    )
    assert list(summary["covariates"]) == ["min_health"]
    rows = [
        (r["condition"], r["other_condition"], r["assigned"], r["n_cells"])
        for r in summary["covariates"]["min_health"]
    ]
    assert rows == [
        (30.0, 0.5, True, 2),
        (30.0, 0.7, True, 1),
        (30.0, None, False, 1),
        (60.0, 0.5, True, 1),
        (60.0, 0.7, True, 0),
        (60.0, None, False, 1),
    ]
    assert "covariate min_health" in report.format_text(summary)


def test_factorial_needs_enough_cells_in_every_cell(tmp_path):
    summary = report.summarize(
        hand_frame(_factorial_cells()), _two_factor_trial(tmp_path), []
    )
    assert summary["factorial"]["min_health"] == {
        "insufficient": True,
        "min_cell_count": 0,
    }
    assert "factorial min_health: insufficient" in report.format_text(summary)


def test_factorial_reports_the_metric_pair_per_condition_pair(tmp_path):
    cells = []
    for i, (seal, health) in enumerate(
        [(30.0, 0.5), (30.0, 0.7), (60.0, 0.5), (60.0, 0.7)] * 2
    ):
        conditions = {"seal_timeout": seal, "min_health": health}
        cells.append({"cell_id": f"c{i}", "slice_id": "S", "conditions": conditions})
    summary = report.summarize(
        hand_frame(cells), _two_factor_trial(tmp_path), [], min_factorial_cells=2
    )
    rows = summary["factorial"]["min_health"]["cells"]
    assert [(r["condition"], r["other_condition"]) for r in rows] == [
        (30.0, 0.5),
        (30.0, 0.7),
        (60.0, 0.5),
        (60.0, 0.7),
    ]
    for r in rows:
        assert r["n_cells"] == 2
        assert r["minutes_per_whole_cell"] == pytest.approx(60 / 60 / 2)
        assert r["whole_cells_per_slice"] == pytest.approx(2.0)
        assert r["minutes_fallback_cells"] == 2
    assert "factorial min_health" in report.format_text(summary)


def test_survey_unit_minutes_include_survey_spans(tmp_path):
    cells = [
        {"cell_id": "c0", "survey_id": "s1", "conditions": {"min_health": 0.5}},
        {"cell_id": "c1", "survey_id": "s1", "conditions": {"min_health": 0.5}},
        {"cell_id": "c2", "survey_id": "s2", "conditions": {"min_health": 0.7}},
    ]
    lines = (
        _span("cell", "c0", 0, 60)
        + _span("cell", "c1", 100, 160)
        + _span("cell", "c2", 200, 320)
        + _span("survey", "s1", 400, 430)
        + _span("survey", "s2", 500, 590)
        + [
            _decision("min_health", "survey", "s1", condition=0.5),
            _decision("min_health", "survey", "s2", condition=0.7),
        ]
    )
    trial = make_trial(
        tmp_path, primary="min_health", mutators={"min_health": dict(HEALTH)}
    )
    by = _by_condition(report.summarize(hand_frame(cells), trial, lines))
    assert by[0.5]["minutes_per_whole_cell"] == pytest.approx((60 + 60 + 30) / 60 / 2)
    assert by[0.7]["minutes_per_whole_cell"] == pytest.approx((120 + 90) / 60 / 1)
    assert by[0.5]["minutes_fallback_cells"] == 0


def test_slice_unit_minutes_include_surveys_of_that_slice(tmp_path):
    detector = {"class": "Detector", "unit": "slice", "conditions": ["a", "b"]}
    cells = [{"cell_id": "c0", "slice_id": "S1", "conditions": {"detector": "a"}}]
    lines = (
        _span("cell", "c0", 0, 60, parent_id="S1")
        + _span("survey", "s1", 100, 160, parent_id="S1")
        + _span("survey", "s2", 200, 500, parent_id="S2")
        + [
            _decision("detector", "slice", "S1", condition="a"),
            _decision("detector", "slice", "S2", condition="b"),
        ]
    )
    trial = make_trial(tmp_path, primary="detector", mutators={"detector": detector})
    by = _by_condition(report.summarize(hand_frame(cells), trial, lines))
    assert by["a"]["minutes_per_whole_cell"] == pytest.approx(120 / 60)
