"""Tests for parsing MultiPatch logs into per-attempt funnel records.

Fixtures use real event-line shapes copied from actual MultiPatch_*.log files.
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autopatch_log as al  # noqa: E402


def _write(tmp_path, lines, name="MultiPatch_000.log"):
    p = tmp_path / name
    p.write_text("".join(line + ",\n" for line in lines))
    return str(p)


# --- real-shaped event lines --------------------------------------------------


def _state(t, state, old, dev="PatchPipette1"):
    return (
        f'{{"device": "{dev}", "event_time": {t}, "event": "state_change", '
        f'"state": "{state}", "old_state": "{old}"}}'
    )


def _attempt_marker(t, dev="PatchPipette1"):
    return f'{{"device": "{dev}", "event_time": {t}, "event": "new_patch_attempt"}}'


def _tp(t, ssr, access=10e6, rin=200e6, cap=10e-12, ibase=5e-13, dev="PatchPipette1"):
    return (
        f'{{"device": "{dev}", "event_time": {t}, "event": "test_pulse", '
        f'"start_time": {t}, "steady_state_resistance": {ssr}, '
        f'"input_resistance": {rin}, "access_resistance": {access}, '
        f'"capacitance": {cap}, "time_constant": 0.001, "fit_yoffset": -1e-11, '
        f'"fit_xoffset": 0.005, "fit_amplitude": -7e-10, "baseline_potential": 0.0, '
        f'"baseline_current": {ibase}}}'
    )


def test_parse_log_events_strips_trailing_commas_and_blanks(tmp_path):
    path = _write(
        tmp_path, [_state(100.0, "bath", "out"), "", _state(101.0, "seal", "bath")]
    )
    events = al.parse_log_events(path)
    assert [e["state"] for e in events] == ["bath", "seal"]


def test_single_attempt_reaching_whole_cell(tmp_path):
    # bath -> seal -> cell attached -> break in -> whole cell (no attempt marker)
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out"),
            _state(10.0, "seal", "bath"),
            _tp(15.0, ssr=1.2e9),  # gigaseal during seal
            _state(20.0, "cell attached", "seal"),
            _state(25.0, "break in", "cell attached"),
            _state(30.0, "whole cell", "break in"),
            _tp(35.0, ssr=3e8, access=12e6, rin=250e6, ibase=-1e-10),
        ],
    )
    attempts = al.load_log(path)
    assert len(attempts) == 1
    a = attempts[0]
    assert a.device == "PatchPipette1"
    assert a.found_cell and a.sealed and a.broke_in
    assert a.best_stage_name == "whole_cell"
    assert a.outcome == "whole cell"
    assert a.duration == pytest.approx(35.0)
    assert a.gigaseal is True
    assert a.max_seal_resistance == pytest.approx(1.2e9)
    assert a.access_resistance == pytest.approx(12e6)
    assert a.holding_current == pytest.approx(-1e-10)


def test_attempt_markers_split_attempts(tmp_path):
    path = _write(
        tmp_path,
        [
            _attempt_marker(0.0),
            _state(1.0, "bath", "out"),
            _state(2.0, "seal", "bath"),
            _state(3.0, "fouled", "seal"),
            _attempt_marker(10.0),
            _state(11.0, "bath", "out"),
            _state(12.0, "seal", "bath"),
            _state(13.0, "cell attached", "seal"),
            _state(14.0, "break in", "cell attached"),
            _state(15.0, "whole cell", "break in"),
        ],
    )
    attempts = al.load_log(path)
    assert len(attempts) == 2
    first, second = attempts
    assert first.found_cell and not first.sealed
    assert first.outcome == "fouled"
    assert second.broke_in
    assert second.outcome == "whole cell"


def test_preamble_before_first_marker_is_its_own_attempt(tmp_path):
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out"),
            _attempt_marker(5.0),
            _state(6.0, "seal", "bath"),
        ],
    )
    attempts = al.load_log(path)
    assert len(attempts) == 2
    assert attempts[0].best_stage_name == "attempted"
    assert attempts[1].found_cell


def test_never_found_cell(tmp_path):
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out"),
            _state(5.0, "fouled", "bath"),
            _state(9.0, "clean", "fouled"),
        ],
    )
    a = al.load_log(path)[0]
    assert not a.attempted_find
    assert not a.found_cell
    assert a.outcome == "clean"


def test_outcome_ignores_earlier_reset_states(tmp_path):
    # Ends in a progress state after starting in bath; must report the progress
    # state, not the earlier bath reset state.
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out"),
            _state(5.0, "approach", "bath"),
            _state(10.0, "seal", "approach"),
        ],
    )
    a = al.load_log(path)[0]
    assert a.outcome == "seal"


def test_outcome_is_last_non_reset_state(tmp_path):
    # A failure (broken) followed by a bath reset gives up in 'broken'.
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out"),
            _state(5.0, "approach", "bath"),
            _state(10.0, "broken", "approach"),
            _state(15.0, "bath", "broken"),
        ],
    )
    a = al.load_log(path)[0]
    assert a.outcome == "broken"


def test_outcome_only_reset_states_falls_back_to_final_state(tmp_path):
    path = _write(tmp_path, [_state(0.0, "bath", "out"), _state(5.0, "out", "bath")])
    a = al.load_log(path)[0]
    assert a.outcome == "out"


def test_outcome_no_states(tmp_path):
    a = al.Attempt(
        source="x", device="PatchPipette1", index=0, start_time=0.0, end_time=0.0
    )
    assert a.outcome == "no states"


def test_max_seal_resistance_ignores_nan(tmp_path):
    # A NaN test-pulse value must not defeat the real gigaohm reading.
    a = al.Attempt(
        source="x",
        device="PatchPipette1",
        index=0,
        start_time=0.0,
        end_time=40.0,
        states=[(0.0, "bath"), (10.0, "seal")],
        test_pulses=[
            {"event_time": 15.0, "steady_state_resistance": float("nan")},
            {"event_time": 20.0, "steady_state_resistance": 1.2e9},
        ],
    )
    assert a.max_seal_resistance == pytest.approx(1.2e9)
    assert a.gigaseal is True


def test_whole_cell_stat_ignores_nan(tmp_path):
    a = al.Attempt(
        source="x",
        device="PatchPipette1",
        index=0,
        start_time=0.0,
        end_time=40.0,
        states=[(0.0, "whole cell")],
        test_pulses=[
            {"event_time": 10.0, "access_resistance": float("nan")},
            {"event_time": 20.0, "access_resistance": 12e6},
        ],
    )
    assert a.access_resistance == pytest.approx(12e6)
    assert math.isfinite(a.access_resistance)


def test_whole_cell_stat_is_true_median_for_even_length(tmp_path):
    a = al.Attempt(
        source="x",
        device="PatchPipette1",
        index=0,
        start_time=0.0,
        end_time=40.0,
        states=[(0.0, "whole cell")],
        test_pulses=[
            {"event_time": 10.0, "access_resistance": 10e6},
            {"event_time": 20.0, "access_resistance": 20e6},
        ],
    )
    # true median of [10e6, 20e6] is 15e6, not the upper-middle element (20e6)
    assert a.access_resistance == pytest.approx(15e6)


def test_approached_attempts_filters_out_never_approached(tmp_path):
    # idx0 never gets past bath/clean; idx1 seals (so it approached a cell)
    path = _write(
        tmp_path,
        [
            _attempt_marker(0.0),
            _state(1.0, "bath", "out"),
            _state(2.0, "clean", "bath"),
            _attempt_marker(10.0),
            _state(11.0, "bath", "out"),
            _state(12.0, "seal", "bath"),
            _state(13.0, "fouled", "seal"),
        ],
    )
    attempts = al.load_log(path)
    assert len(attempts) == 2
    approached = al.approached_attempts(attempts)
    assert [a.index for a in approached] == [1]
    assert all(a.attempted_find for a in approached)


def test_multiple_devices_are_separated(tmp_path):
    path = _write(
        tmp_path,
        [
            _state(0.0, "bath", "out", dev="PatchPipette1"),
            _state(1.0, "seal", "bath", dev="PatchPipette2"),
            _state(2.0, "whole cell", "break in", dev="PatchPipette1"),
        ],
    )
    attempts = al.load_log(path)
    devs = {a.device for a in attempts}
    assert devs == {"PatchPipette1", "PatchPipette2"}


def test_global_events_without_device_are_ignored(tmp_path):
    path = _write(
        tmp_path,
        [
            '{"device": "Microscope", "event_time": 0.0, "event": "surface_depth_changed", "surface_depth": 0.0001}',
            '{"event_time": 0.5, "device": null, "event": "global patch profiles changed", "profile": "{}"}',
            _state(1.0, "bath", "out"),
            _state(2.0, "seal", "bath"),
        ],
    )
    attempts = al.load_log(path)
    # Microscope has no patch states; only PatchPipette1 yields a real attempt
    patch_attempts = [a for a in attempts if a.device == "PatchPipette1"]
    assert len(patch_attempts) == 1
    assert patch_attempts[0].found_cell


def test_find_logs_is_recursive_and_case_insensitive(tmp_path):
    (tmp_path / "cell_000").mkdir()
    (tmp_path / "cell_001").mkdir()
    p1 = _write(tmp_path / "cell_000", [_state(0.0, "bath", "out")])
    p2 = _write(
        tmp_path / "cell_001", [_state(0.0, "bath", "out")], name="multipatch_000.log"
    )
    (tmp_path / "unrelated.log").write_text("nope")
    found = al.find_logs([str(tmp_path)])
    assert set(found) == {p1, p2}


def test_load_run_tags_source(tmp_path):
    d = tmp_path / "cell_000"
    d.mkdir()
    path = _write(d, [_state(0.0, "bath", "out"), _state(1.0, "seal", "bath")])
    attempts = al.load_run([str(tmp_path)])
    assert len(attempts) == 1
    assert attempts[0].source == path
