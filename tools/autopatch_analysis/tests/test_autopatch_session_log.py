"""Tests for reading cleaning/detection/idle time out of an ACQ4 session log.

Fixtures use real record shapes copied from an actual ``log.json``: one JSON
object per line, the patch state named on the gentletask ``throughline``, and the
tile detector's survey messages.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autopatch_session_log as asl  # noqa: E402


def _record(t, module, func, message, throughline=()):
    return {
        "message": message,
        "name": "acq4",
        "msg": message,
        "args": [],
        "levelname": "DEBUG",
        "level": 10,
        "module": module,
        "filename": f"{module}.py",
        "lineno": 227,
        "funcName": func,
        "created": t,
        "throughline": list(throughline),
    }


def _transition(t, state, old="bath", dev="PatchPipette1", throughline=None):
    """The pair of records ``_configureState`` writes for one state change."""
    frames = [f"{dev} -> state '{state}'"] if throughline is None else throughline
    return [
        _record(t, "statemanager", "_configureState",
                f"Configuring next state {state} with config: {{'initialPressure': 1000}}",
                frames),
        _record(t, "statemanager", "_configureState",
                f"Stopping previous state {old}", frames),
    ]


def _survey_start(t, x=0.0003):
    return _record(t, "tile_detector", "detect", f"Surveying tile at (np.float64({x}),)")


def _survey_end(t, n=31, x=0.0003):
    return _record(
        t, "tile_detector", "detect", f"Tile at (np.float64({x}),) yielded {n} candidates"
    )


def _write(tmp_path, records, name="log.json"):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in records))
    return str(p)


# --- state spans --------------------------------------------------------------


def test_transitions_become_spans_between_consecutive_states(tmp_path):
    path = _write(
        tmp_path,
        _transition(100.0, "approach", old="bath")
        + _transition(140.0, "seal", old="approach")
        + _transition(200.0, "fouled", old="seal"),
    )
    spans, _ = asl.parse_session_log(path)
    assert [(s.state, s.t_start, s.t_end) for s in spans] == [
        ("approach", 100.0, 140.0),
        ("seal", 140.0, 200.0),
    ]
    assert {s.device for s in spans} == {"PatchPipette1"}


def test_final_state_is_dropped_rather_than_run_to_the_end_of_the_session(tmp_path):
    # The log records 'fouled' being entered but never left: its "duration" would
    # be time-until-ACQ4-quit, which is not a dwell time.
    path = _write(
        tmp_path,
        _transition(100.0, "clean") + _transition(180.0, "fouled", old="clean"),
    )
    spans, _ = asl.parse_session_log(path)
    assert [s.state for s in spans] == ["clean"]


def test_reconfiguring_the_same_state_does_not_split_the_stay(tmp_path):
    # A profile change reconfigures the state in place; the pipette never left it.
    path = _write(
        tmp_path,
        _transition(100.0, "out", old=None)
        + _transition(130.0, "out", old="out")
        + _transition(160.0, "approach", old="out"),
    )
    spans, _ = asl.parse_session_log(path)
    assert [(s.state, s.t_start, s.t_end) for s in spans] == [("out", 100.0, 160.0)]


def test_one_transition_per_state_change_not_one_per_logged_line(tmp_path):
    path = _write(tmp_path, _transition(100.0, "clean") + _transition(150.0, "out"))
    spans, _ = asl.parse_session_log(path)
    assert len(spans) == 1


def test_configure_that_never_reached_the_stopping_line_is_not_a_transition(tmp_path):
    # Building the next state's job raised, so that state never ran.
    failed = _record(
        120.0, "statemanager", "_configureState",
        "Configuring next state break in with config: {}",
        ["PatchPipette1 -> state 'break in'"],
    )
    path = _write(
        tmp_path,
        _transition(100.0, "seal") + [failed] + _transition(160.0, "fouled", old="seal"),
    )
    spans, _ = asl.parse_session_log(path)
    assert [(s.state, s.t_end) for s in spans] == [("seal", 160.0)]


def test_state_frame_is_found_when_nested_under_a_named_operation(tmp_path):
    # configureState called from a GUI action pushes its frame under that action's.
    frames = ["Move pipettes home", "PatchPipette2 -> state 'out'"]
    path = _write(
        tmp_path,
        _transition(100.0, "out", throughline=frames)
        + _transition(150.0, "bath", dev="PatchPipette2")
        + _transition(190.0, "approach", dev="PatchPipette2"),
    )
    spans, _ = asl.parse_session_log(path)
    assert [(s.device, s.state) for s in spans] == [
        ("PatchPipette2", "out"),
        ("PatchPipette2", "bath"),
    ]


def test_devices_are_spanned_independently(tmp_path):
    path = _write(
        tmp_path,
        _transition(100.0, "approach", dev="PatchPipette1")
        + _transition(110.0, "clean", dev="PatchPipette2")
        + _transition(160.0, "seal", dev="PatchPipette1")
        + _transition(200.0, "out", dev="PatchPipette2"),
    )
    spans, _ = asl.parse_session_log(path)
    by_device = {(s.device, s.state): (s.t_start, s.t_end) for s in spans}
    assert by_device[("PatchPipette1", "approach")] == (100.0, 160.0)
    assert by_device[("PatchPipette2", "clean")] == (110.0, 200.0)


def test_records_without_a_state_frame_are_ignored(tmp_path):
    noise = _record(105.0, "planner", "_move_device", "Starting move to [0. 0. 0.]", [])
    path = _write(
        tmp_path, _transition(100.0, "clean") + [noise] + _transition(150.0, "out")
    )
    spans, _ = asl.parse_session_log(path)
    assert [s.state for s in spans] == ["clean"]


def test_unparseable_lines_are_skipped(tmp_path):
    p = tmp_path / "log.json"
    body = "".join(json.dumps(r) + "\n" for r in _transition(100.0, "clean"))
    body += "{truncated line with -> state 'clean'\n"
    body += "".join(json.dumps(r) + "\n" for r in _transition(150.0, "out"))
    p.write_text(body)
    spans, _ = asl.parse_session_log(str(p))
    assert [s.duration for s in spans] == [50.0]


# --- tile surveys -------------------------------------------------------------


def test_survey_spans_from_start_and_yield_records(tmp_path):
    path = _write(
        tmp_path,
        [_survey_start(100.0), _survey_end(160.0, n=31)]
        + [_survey_start(500.0), _survey_end(548.0, n=48)],
    )
    _, surveys = asl.parse_session_log(path)
    assert [(s.t_start, s.t_end, s.n_candidates) for s in surveys] == [
        (100.0, 160.0, 31),
        (500.0, 548.0, 48),
    ]
    assert surveys[0].duration == 60.0


def test_aborted_survey_is_superseded_rather_than_closed_at_a_guess(tmp_path):
    # The first survey was stopped mid-stack: no "yielded" record was ever written,
    # so its length is unknown and it must not absorb the wait until the next one.
    path = _write(
        tmp_path, [_survey_start(100.0), _survey_start(400.0), _survey_end(450.0, n=12)]
    )
    _, surveys = asl.parse_session_log(path)
    assert [(s.t_start, s.t_end) for s in surveys] == [(400.0, 450.0)]


def test_survey_still_running_when_the_log_ends_is_not_reported(tmp_path):
    path = _write(tmp_path, [_survey_start(100.0)])
    _, surveys = asl.parse_session_log(path)
    assert surveys == []


# --- finding the session log --------------------------------------------------


def test_find_session_logs_searches_below_the_root(tmp_path):
    run = tmp_path / "2026.08.20_000"
    path = _write(run, _transition(100.0, "clean"))
    assert asl.find_session_logs([str(tmp_path)]) == [path]


def test_find_session_logs_walks_up_from_a_cell_directory(tmp_path):
    run = tmp_path / "2026.08.20_000"
    path = _write(run, _transition(100.0, "clean"))
    cell = run / "slice_000" / "cell_003"
    cell.mkdir(parents=True)
    assert asl.find_session_logs([str(cell)]) == [path]


def test_find_session_logs_prefers_the_logs_inside_the_root(tmp_path):
    outer = _write(tmp_path, _transition(100.0, "clean"))
    run = tmp_path / "2026.08.20_000"
    inner = _write(run, _transition(100.0, "clean"))
    assert asl.find_session_logs([str(run)]) == [inner]
    assert outer not in asl.find_session_logs([str(run)])


def test_load_session_logs_merges_runs_and_keeps_the_source(tmp_path):
    a = _write(tmp_path / "run_a", _transition(100.0, "clean") + _transition(180.0, "out"))
    b = _write(tmp_path / "run_b", _transition(900.0, "clean") + _transition(950.0, "out"))
    spans, _ = asl.load_session_logs([str(tmp_path)])
    assert sorted(s.source for s in spans) == sorted([a, b])


def test_no_session_log_anywhere_yields_nothing(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    assert asl.find_session_logs([str(empty)]) == []
    assert asl.load_session_logs([str(empty)]) == ([], [])
