"""Tests for aggregating autopatch attempts into funnel/throughput tables."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autopatch_log as al  # noqa: E402
import autopatch_metrics as am  # noqa: E402
import autopatch_session_log as asl  # noqa: E402


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


def test_funnel_conversion_from_zero_prev_is_zero():
    # A single attempt that approached but never found a cell: found_cell count
    # is 0, so sealed/broke_in have a zero-count predecessor. Their conversion
    # from the previous stage must be 0.0, not 100.0.
    attempts = [_attempt(0, [(0.0, "bath"), (1.0, "approach")])]
    df = am.attempts_to_dataframe(attempts)
    funnel = am.funnel_counts(df).set_index("stage")
    assert funnel.loc["approached", "count"] == 1
    assert funnel.loc["found_cell", "count"] == 0
    assert funnel.loc["sealed", "count"] == 0
    # first stage is always 100%; downstream stages with a 0-count predecessor
    # convert at 0%, not 100%.
    assert funnel.loc["approached", "conversion_from_prev"] == pytest.approx(100.0)
    assert funnel.loc["found_cell", "conversion_from_prev"] == pytest.approx(0.0)
    assert funnel.loc["sealed", "conversion_from_prev"] == pytest.approx(0.0)
    assert funnel.loc["broke_in", "conversion_from_prev"] == pytest.approx(0.0)


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
    # The cleaning cycle's log stops in 'clean', so its outcome is a state the
    # pipette was passing through rather than one it gave up in.
    assert fm.loc["clean (outcome not logged)", "count"] == 1


def test_state_dwell_times():
    dwell = am.state_dwell_times(_sample_attempts()).set_index("state")
    # attempt 0: bath spans 0->10 = 10s; attempt 1: bath 40->50 = 10s; etc.
    assert dwell.loc["bath", "total_s"] == pytest.approx(40.0)
    assert dwell.loc["bath", "n_attempts"] == 4
    assert dwell.loc["seal", "total_s"] == pytest.approx(30.0)  # 10 + 10 + 10


def test_state_dwell_mean_averages_only_attempts_that_reached_the_state():
    # 'cell attached' is left by two of four attempts; its mean must be over
    # those two, not the dwell spread over the whole run.
    dwell = am.state_dwell_times(_sample_attempts()).set_index("state")
    assert dwell.loc["cell attached", "n_attempts"] == 2
    assert dwell.loc["cell attached", "mean_s"] == pytest.approx(7.5)  # (5 + 10) / 2
    assert dwell.loc["seal", "n_attempts"] == 3
    assert dwell.loc["seal", "mean_s"] == pytest.approx(10.0)


def test_state_dwell_excludes_the_state_an_attempt_never_left():
    # The last state of an attempt has no logged exit, so its span is only
    # "time until the log stopped". Terminal states -- 'whole cell' when the
    # log ends on break-in, 'fouled'/'clean' when the attempt gave up -- would
    # otherwise show up as near-zero dwell times.
    dwell = am.state_dwell_times(_sample_attempts()).set_index("state")
    assert "whole cell" not in dwell.index
    assert "fouled" not in dwell.index
    assert "clean" not in dwell.index
    # A state that an attempt does leave is still counted for that attempt.
    attempts = [_attempt(0, [(0.0, "fouled"), (5.0, "clean"), (9.0, "bath")])]
    dwell = am.state_dwell_times(attempts).set_index("state")
    assert dwell.loc["fouled", "total_s"] == pytest.approx(5.0)
    assert "bath" not in dwell.index


def test_state_dwell_mean_counts_a_revisited_state_once_per_attempt():
    # One attempt entering 'seal' twice (10s + 20s) is one attempt at 30s, not
    # two visits averaged to 15s.
    attempts = [
        _attempt(
            0,
            [
                (0.0, "seal"),
                (10.0, "cell attached"),
                (20.0, "seal"),
                (40.0, "fouled"),
            ],
        )
    ]
    dwell = am.state_dwell_times(attempts).set_index("state")
    assert dwell.loc["seal", "n_attempts"] == 1
    assert dwell.loc["seal", "n_visits"] == 2
    assert dwell.loc["seal", "total_s"] == pytest.approx(30.0)
    assert dwell.loc["seal", "mean_s"] == pytest.approx(30.0)


def test_throughput():
    df = am.attempts_to_dataframe(_sample_attempts())
    tp = am.throughput(df)
    assert tp["n_attempts"] == 4
    assert tp["n_whole_cell"] == 1
    assert tp["overall_yield_pct"] == pytest.approx(25.0)
    # single log spanning 0 -> 120 s = 1/30 hour of active time
    assert tp["active_hours"] == pytest.approx(120.0 / 3600.0)
    assert tp["attempts_per_hour"] == pytest.approx(4.0 / (120.0 / 3600.0))


def test_throughput_counts_attempts_whose_outcome_was_never_logged():
    # The sample's 4th attempt ends in 'clean', a cycle rather than a resting
    # state, and a 5th here is cut off in 'break in' -- the shape a truncated
    # acq4 log has. Both bound how far the whole-cell count can be trusted, so
    # the headline numbers have to say how many there are.
    attempts = _sample_attempts() + [
        _attempt(4, [(130.0, "bath"), (140.0, "seal"), (150.0, "break in")])
    ]
    tp = am.throughput(am.attempts_to_dataframe(attempts))
    assert tp["n_whole_cell"] == 1
    assert tp["n_outcome_unlogged"] == 2



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
    assert am.session_time_budget([]).empty
    assert am.session_category_totals(am.session_time_budget([])).empty
    assert am.survey_time([], []).empty
    assert am.session_time_summary([], []).empty


# --- session-log time budget --------------------------------------------------


def _span(state, t0, t1, device="PatchPipette1", source="/run/log.json"):
    return asl.StateSpan(source, device, state, t0, t1)


def _sample_session():
    """One attempt-and-clean cycle, bracketed by pre/post-run idle.

    out(-100..0) approach(0..40) seal(40..70) fouled(70..80) clean(80..152)
    out(152..182) approach(182..222) whole cell(222..282) fouled(282..1000)
    """
    return [
        _span("out", -100.0, 0.0),
        _span("approach", 0.0, 40.0),
        _span("seal", 40.0, 70.0),
        _span("fouled", 70.0, 80.0),
        _span("clean", 80.0, 152.0),
        _span("out", 152.0, 182.0),
        _span("approach", 182.0, 222.0),
        _span("whole cell", 222.0, 282.0),
        _span("fouled", 282.0, 1000.0),
    ]


def test_states_are_categorized_by_what_they_cost():
    assert am.categorize_state("clean") == am.CLEANING
    assert am.categorize_state("approach") == am.PATCHING
    assert am.categorize_state("fouled") == am.IDLE
    assert am.categorize_state("whole cell") == am.RECORDING
    # an unknown state is called out rather than quietly counted as idle
    assert am.categorize_state("some new state") == am.OTHER


def test_active_window_opens_at_first_patching_and_closes_at_last_work():
    windows = am.session_active_windows(_sample_session())
    assert windows == {("/run/log.json", "PatchPipette1"): (0.0, 282.0)}


def test_idle_outside_the_window_is_not_charged_to_the_run():
    # The 100 s parked before the run and the 718 s fouled after it are not costs
    # of the run; only the 30 s of 'out' between the two attempts is.
    budget = am.session_time_budget(_sample_session())
    idle = budget[budget["category"] == am.IDLE].set_index("state")["total_s"]
    assert idle["out"] == pytest.approx(30.0)
    assert idle["fouled"] == pytest.approx(10.0)
    assert budget["total_s"].sum() == pytest.approx(282.0)


def test_budget_percentages_are_shares_of_the_active_window():
    budget = am.session_time_budget(_sample_session())
    clean = budget[budget["state"] == "clean"].iloc[0]
    assert clean["total_s"] == pytest.approx(72.0)
    assert clean["n_visits"] == 1
    assert clean["pct_of_active"] == pytest.approx(100.0 * 72.0 / 282.0)
    assert budget["pct_of_active"].sum() == pytest.approx(100.0)


def test_category_totals_roll_up_in_display_order():
    totals = am.session_category_totals(am.session_time_budget(_sample_session()))
    assert list(totals["category"]) == [am.PATCHING, am.CLEANING, am.IDLE, am.RECORDING]
    assert totals.set_index("category")["minutes"][am.CLEANING] == pytest.approx(72 / 60)


def test_a_device_that_never_patched_is_not_part_of_the_run():
    # A second pipette parked in the bath all day would otherwise double the
    # run's clock and drown the working pipette's numbers in idle.
    spans = _sample_session() + [
        _span("bath", -100.0, 1000.0, device="PatchPipette2"),
    ]
    budget = am.session_time_budget(spans)
    assert list(budget["device"].unique()) == ["PatchPipette1"]
    assert budget["total_s"].sum() == pytest.approx(282.0)


def test_survey_time_is_reported_apart_from_the_budget_not_inside_it():
    # The survey runs while the pipette sits fouled: it is concurrent with the
    # budget, so it must not be added to it.
    surveys = [asl.SurveySpan("/run/log.json", 72.0, 78.0, 31)]
    budget = am.session_time_budget(_sample_session())
    surv = am.survey_time(_sample_session(), surveys)
    assert budget["total_s"].sum() == pytest.approx(282.0)
    assert surv["minutes"] == pytest.approx(6.0 / 60.0)
    assert surv["blocking_minutes"] == pytest.approx(6.0 / 60.0)
    assert surv["n_candidates"] == 31
    assert surv["per_candidate_s"] == pytest.approx(6.0 / 31)


def test_survey_overlapping_patch_work_is_not_counted_as_blocking():
    # Surveying while the pipette is approaching the next cell costs the run
    # nothing: only the part that overlaps non-patching time is a delay.
    surveys = [asl.SurveySpan("/run/log.json", 10.0, 90.0, 40)]
    surv = am.survey_time(_sample_session(), surveys)
    assert surv["minutes"] == pytest.approx(80.0 / 60.0)
    # 70..80 fouled + 80..90 clean = 20 s of it ran while not patching
    assert surv["blocking_minutes"] == pytest.approx(20.0 / 60.0)


def test_survey_outside_the_active_window_is_not_charged_to_the_run():
    surveys = [asl.SurveySpan("/run/log.json", -90.0, -30.0, 31)]
    surv = am.survey_time(_sample_session(), surveys)
    assert surv["n_surveys"] == 0
    assert surv["minutes"] == pytest.approx(0.0)


def test_summary_separates_overhead_from_the_task_protocol():
    surveys = [asl.SurveySpan("/run/log.json", 72.0, 78.0, 31)]
    s = am.session_time_summary(_sample_session(), surveys, n_attempts=2)
    assert s["active_minutes"] == pytest.approx(282.0 / 60.0)
    assert s["patching_minutes"] == pytest.approx(110.0 / 60.0)
    assert s["cleaning_minutes"] == pytest.approx(72.0 / 60.0)
    assert s["idle_minutes"] == pytest.approx(40.0 / 60.0)
    # whole-cell time is the experiment's, so it is reported but never overhead
    assert s["recording_minutes"] == pytest.approx(60.0 / 60.0)
    assert s["overhead_minutes"] == pytest.approx(112.0 / 60.0)
    assert s["overhead_pct"] == pytest.approx(100.0 * 112.0 / 282.0)
    assert s["n_clean_cycles"] == 1
    assert s["detection_minutes"] == pytest.approx(6.0 / 60.0)
    assert s["minutes_per_attempt"] == pytest.approx(282.0 / 2 / 60.0)
    assert s["cleaning_per_attempt_minutes"] == pytest.approx(72.0 / 2 / 60.0)


def test_summary_without_an_attempt_count_omits_the_per_attempt_figures():
    s = am.session_time_summary(_sample_session())
    assert "minutes_per_attempt" not in s.index
    assert s["detection_minutes"] == pytest.approx(0.0)
    assert s["n_surveys"] == 0
