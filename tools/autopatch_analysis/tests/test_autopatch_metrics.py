"""Tests for aggregating autopatch attempts into funnel/throughput tables."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autopatch_log as al  # noqa: E402
import autopatch_metrics as am  # noqa: E402


def _attempt(
    index, states, source="/run/cell_000/MultiPatch_000.log", start=0.0, tps=None
):
    end = states[-1][0] if states else start
    if tps:
        end = max(end, max(t["event_time"] for t in tps))
    return al.Attempt(
        source=source,
        device="PatchPipette1",
        index=index,
        start_time=start,
        end_time=end,
        states=states,
        test_pulses=tps or [],
    )


def _sample_attempts():
    return [
        # whole cell success
        _attempt(
            0,
            [
                (0.0, "bath"),
                (10.0, "seal"),
                (20.0, "cell attached"),
                (25.0, "break in"),
                (30.0, "whole cell"),
            ],
        ),
        # found + sealed but lost it
        _attempt(
            1,
            [(40.0, "bath"), (50.0, "seal"), (60.0, "cell attached"), (70.0, "fouled")],
        ),
        # found only
        _attempt(2, [(80.0, "bath"), (90.0, "seal"), (100.0, "fouled")]),
        # never found a cell
        _attempt(3, [(110.0, "bath"), (120.0, "clean")]),
    ]


def test_dataframe_has_row_per_attempt():
    df = am.attempts_to_dataframe(_sample_attempts())
    assert len(df) == 4
    assert df["cell_dir"].iloc[0] == "cell_000"
    assert list(df["broke_in"]) == [True, False, False, False]


def test_funnel_is_based_on_approached_not_all_attempts():
    # The 4th sample attempt (bath -> clean) never approached a cell and must
    # not count toward the funnel, even if the full df is passed in.
    df = am.attempts_to_dataframe(_sample_attempts())
    funnel = am.funnel_counts(df).set_index("stage")
    # base of the funnel is the 3 approached attempts, not all 4
    assert funnel.loc["approached", "count"] == 3
    assert "attempted" not in funnel.index
    assert funnel.loc["found_cell", "count"] == 3
    assert funnel.loc["sealed", "count"] == 2
    assert funnel.loc["broke_in", "count"] == 1
    # conversions/percentages are relative to approached attempts
    assert funnel.loc["found_cell", "pct_of_approached"] == pytest.approx(100.0)
    assert funnel.loc["sealed", "pct_of_approached"] == pytest.approx(200.0 / 3)
    # 1 of 2 sealed attempts broke in
    assert funnel.loc["broke_in", "conversion_from_prev"] == pytest.approx(50.0)


def test_state_timeline_spans_per_folder():
    attempts = _sample_attempts()
    tl = am.state_timeline(attempts)
    # one row per state interval across all attempts
    n_intervals = sum(len(a.states) for a in attempts)
    assert len(tl) == n_intervals
    assert set(["folder", "cell_dir", "device", "state", "t_start", "t_end"]) <= set(
        tl.columns
    )
    # spans are ordered and non-negative in duration
    assert (tl["t_end"] >= tl["t_start"]).all()
    # folder is the directory holding the log
    assert tl["folder"].iloc[0].endswith("cell_000")


def test_state_timeline_empty_is_well_formed():
    tl = am.state_timeline([])
    assert list(tl.columns) == [
        "folder",
        "cell_dir",
        "device",
        "attempt_index",
        "state",
        "t_start",
        "t_end",
    ]
    assert len(tl) == 0


def test_failure_mode_counts():
    df = am.attempts_to_dataframe(_sample_attempts())
    fm = am.failure_mode_counts(df).set_index("outcome")
    assert fm.loc["fouled", "count"] == 2
    assert fm.loc["whole cell", "count"] == 1
    assert fm.loc["clean", "count"] == 1


def test_state_dwell_times():
    dwell = am.state_dwell_times(_sample_attempts()).set_index("state")
    # attempt 0: bath spans 0->10 = 10s; attempt 1: bath 40->50 = 10s; etc.
    assert dwell.loc["bath", "total_s"] == pytest.approx(40.0)
    assert dwell.loc["bath", "n"] == 4
    assert dwell.loc["seal", "total_s"] == pytest.approx(30.0)  # 10 + 10 + 10


def test_throughput():
    df = am.attempts_to_dataframe(_sample_attempts())
    tp = am.throughput(df)
    assert tp["n_attempts"] == 4
    assert tp["n_whole_cell"] == 1
    assert tp["overall_yield_pct"] == pytest.approx(25.0)
    # single log spanning 0 -> 120 s = 1/30 hour of active time
    assert tp["active_hours"] == pytest.approx(120.0 / 3600.0)
    assert tp["attempts_per_hour"] == pytest.approx(4.0 / (120.0 / 3600.0))


def test_cumulative_whole_cells():
    df = am.attempts_to_dataframe(_sample_attempts())
    cum = am.cumulative_whole_cells(df)
    assert list(cum["cumulative_whole_cells"]) == [1]
    assert cum["minutes"].iloc[0] == pytest.approx(0.5)  # 30 s


def test_empty_inputs_do_not_crash():
    df = am.attempts_to_dataframe([])
    # even with no rows the expected columns exist, so downstream lookups don't KeyError
    assert "device" in df.columns and "broke_in" in df.columns
    assert df["device"].nunique() == 0
    assert am.throughput(df).empty
    assert am.state_dwell_times([]).empty
    assert am.cumulative_whole_cells(df).empty
