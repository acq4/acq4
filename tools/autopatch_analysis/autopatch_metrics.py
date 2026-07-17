"""Aggregate parsed autopatch attempts into throughput/efficiency tables.

Turns a list of :class:`autopatch_log.Attempt` into pandas DataFrames for the
funnel (find/seal/break-in conversion), throughput, per-state time budget, and
failure-mode breakdown consumed by the analysis notebook.
"""

from __future__ import annotations

import os
from typing import Iterable

import pandas as pd

from autopatch_log import STAGE_NAMES, Attempt

# Funnel stages in order, as (display stage, Attempt-boolean DataFrame column).
# The funnel is rooted at ``approached`` -- attempts that never engaged a cell
# (setup/cleaning cycles) are not real patch attempts and are excluded, so the
# base of the funnel is the count of approached attempts, not all attempts.
FUNNEL_STAGES = [
    ("approached", "attempted_find"),
    ("found_cell", "found_cell"),
    ("sealed", "sealed"),
    ("broke_in", "broke_in"),
]


# Columns of the per-attempt table, in order. Declared so an empty run still
# yields a well-formed (column-bearing) DataFrame instead of a bare one.
ATTEMPT_COLUMNS = [
    "source",
    "cell_dir",
    "device",
    "attempt_index",
    "start_time",
    "end_time",
    "duration_s",
    "best_stage",
    "best_stage_name",
    "attempted_find",
    "found_cell",
    "sealed",
    "broke_in",
    "gigaseal",
    "outcome",
    "final_state",
    "max_seal_resistance",
    "access_resistance",
    "input_resistance",
    "holding_current",
    "capacitance",
    "n_test_pulses",
    "n_state_changes",
]


def attempts_to_dataframe(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """One row per attempt with outcome flags and whole-cell quality numbers."""
    rows = []
    for a in attempts:
        rows.append(
            {
                "source": a.source,
                "cell_dir": os.path.basename(os.path.dirname(a.source)),
                "device": a.device,
                "attempt_index": a.index,
                "start_time": a.start_time,
                "end_time": a.end_time,
                "duration_s": a.duration,
                "best_stage": a.best_stage,
                "best_stage_name": a.best_stage_name,
                "attempted_find": a.attempted_find,
                "found_cell": a.found_cell,
                "sealed": a.sealed,
                "broke_in": a.broke_in,
                "gigaseal": a.gigaseal,
                "outcome": a.outcome,
                "final_state": a.final_state,
                "max_seal_resistance": a.max_seal_resistance,
                "access_resistance": a.access_resistance,
                "input_resistance": a.input_resistance,
                "holding_current": a.holding_current,
                "capacitance": a.capacitance,
                "n_test_pulses": len(a.test_pulses),
                "n_state_changes": len(a.states),
            }
        )
    return pd.DataFrame(rows, columns=ATTEMPT_COLUMNS)


def funnel_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Counts and conversion percentages at each funnel stage.

    The funnel is rooted at ``approached`` (attempts that engaged a cell), so
    never-approached attempts are excluded even if they are present in ``df``.
    ``pct_of_approached`` is the share of approached attempts reaching a stage;
    ``conversion_from_prev`` is the share of the previous stage that advanced.
    """
    approached = int(df["attempted_find"].sum()) if len(df) else 0
    rows = []
    prev = None
    for stage, column in FUNNEL_STAGES:
        count = int(df[column].sum()) if len(df) else 0
        rows.append(
            {
                "stage": stage,
                "count": count,
                "pct_of_approached": (
                    (100.0 * count / approached) if approached else 0.0
                ),
                "conversion_from_prev": (100.0 * count / prev) if prev else 100.0,
            }
        )
        prev = count
    return pd.DataFrame(rows)


def failure_mode_counts(df: pd.DataFrame) -> pd.DataFrame:
    """How many attempts ended in each outcome, most common first."""
    counts = df["outcome"].value_counts()
    return (
        counts.rename_axis("outcome")
        .reset_index(name="count")
        .assign(pct=lambda d: 100.0 * d["count"] / len(df) if len(df) else 0.0)
    )


def state_dwell_times(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """Total/mean seconds spent in each patch state across all attempts."""
    rows = []
    for a in attempts:
        for state, t0, t1 in a.state_intervals():
            rows.append({"state": state, "seconds": t1 - t0})
    if not rows:
        return pd.DataFrame(columns=["state", "total_s", "mean_s", "n"])
    df = pd.DataFrame(rows)
    agg = (
        df.groupby("state")["seconds"]
        .agg(total_s="sum", mean_s="mean", n="count")
        .reset_index()
        .sort_values("total_s", ascending=False)
        .reset_index(drop=True)
    )
    return agg


# Columns of the state-timeline table, so an empty run still yields a
# well-formed (column-bearing) DataFrame.
TIMELINE_COLUMNS = [
    "folder",
    "cell_dir",
    "device",
    "attempt_index",
    "state",
    "t_start",
    "t_end",
]


def state_timeline(attempts: Iterable[Attempt]) -> pd.DataFrame:
    """Long-form (folder, device, state, t_start, t_end) spans for a Gantt view.

    One row per state interval of every attempt, keyed by ``folder`` (the
    directory holding the log). Times are absolute (epoch seconds); the notebook
    rebases them per folder. This intentionally includes non-approached attempts
    so the idle time trimmed from the active-time window stays visible.
    """
    rows = []
    for a in attempts:
        folder = os.path.dirname(a.source)
        cell_dir = os.path.basename(folder)
        for state, t0, t1 in a.state_intervals():
            rows.append(
                {
                    "folder": folder,
                    "cell_dir": cell_dir,
                    "device": a.device,
                    "attempt_index": a.index,
                    "state": state,
                    "t_start": t0,
                    "t_end": t1,
                }
            )
    return pd.DataFrame(rows, columns=TIMELINE_COLUMNS)


def throughput(df: pd.DataFrame) -> pd.Series:
    """Run-level throughput: active time, attempt and whole-cell rates.

    Rates use ``active_hours`` -- the summed per-log span of the attempts in
    ``df`` -- rather than the global first-to-last span, so pointing at logs
    recorded on different days doesn't count the idle gaps between runs against
    the rate. Pass the approached attempts (see ``approached_attempts``) so this
    span covers only the autopatch demo's active window and not the pipette
    setup/cleaning idle before the first cell or after the last.
    """
    if df.empty:
        return pd.Series(dtype=float)
    per_log = df.groupby("source").agg(t0=("start_time", "min"), t1=("end_time", "max"))
    active_h = (per_log["t1"] - per_log["t0"]).sum() / 3600.0
    span_h = (df["end_time"].max() - df["start_time"].min()) / 3600.0
    n_attempts = len(df)
    n_whole = int(df["broke_in"].sum())
    return pd.Series(
        {
            "n_logs": df["source"].nunique(),
            "n_attempts": n_attempts,
            "n_found": int(df["found_cell"].sum()),
            "n_sealed": int(df["sealed"].sum()),
            "n_whole_cell": n_whole,
            "active_hours": active_h,
            "span_hours": span_h,
            "attempts_per_hour": (n_attempts / active_h) if active_h else float("nan"),
            "whole_cells_per_hour": (n_whole / active_h) if active_h else float("nan"),
            "overall_yield_pct": 100.0 * n_whole / n_attempts if n_attempts else 0.0,
            "mean_attempt_minutes": df["duration_s"].mean() / 60.0,
        }
    )


def cumulative_whole_cells(df: pd.DataFrame) -> pd.DataFrame:
    """Whole-cell successes over wall-clock, for a cumulative-yield plot."""
    if df.empty:
        return pd.DataFrame(columns=["minutes", "cumulative_whole_cells"])
    t0 = df["start_time"].min()
    wc = df[df["broke_in"]].sort_values("end_time")
    return pd.DataFrame(
        {
            "minutes": (wc["end_time"] - t0) / 60.0,
            "cumulative_whole_cells": range(1, len(wc) + 1),
        }
    )


# Re-export for notebook convenience.
__all__ = [
    "STAGE_NAMES",
    "attempts_to_dataframe",
    "funnel_counts",
    "failure_mode_counts",
    "state_dwell_times",
    "state_timeline",
    "throughput",
    "cumulative_whole_cells",
]
