"""Summarize a tuning trial per condition of its primary factor, and write summary.json, report.txt and plots."""

import json
import math
import os
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from acq4.modules.Autopatch.analysis.autopatch_metrics import funnel_counts

from .join import slice_ledger_lines

SUMMARY_SCHEMA_VERSION = 1
DEFAULT_GATE = {
    "access_resistance_max": 25e6,
    "holding_current_min": -200e-12,
    "input_resistance_min": 50e6,
}
ELIGIBILITY_SPLIT_MARGIN = 0.1
QUALITY_FIELDS = (
    "access_resistance",
    "holding_current",
    "input_resistance",
    "capacitance",
)
UNIT_ID_COLUMN = {"cell": "cell_id", "survey": "survey_id", "slice": "slice_id"}
SUMMARY_KEYS = (
    "schema_version",
    "trial_id",
    "run_id",
    "primary_factor",
    "unit",
    "no_units_assigned",
    "quality_gate",
    "conditions",
    "eligibility",
    "asked_rate",
    "provenance",
    "warnings",
)
CONDITION_KEYS = (
    "condition",
    "n_units",
    "n_cells",
    "n_attempts",
    "n_whole_cell",
    "minutes_per_whole_cell",
    "whole_cells_per_slice",
    "quality",
    "n_passing_gate",
    "funnel",
)
PLOT_NAME = "metric_pair.png"
BAR_COLOR = "#2a78d6"


def condition_key(condition):
    return json.dumps(condition, sort_keys=True)


def _keys(frame, name):
    if name not in frame:
        return frame.index.to_series().map(lambda _: None)
    return frame[name].map(lambda v: None if _missing(v) else condition_key(v))


def _missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


def _clean(value):
    """Convert numpy scalars to Python and NaN to None so the result is strict JSON."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) else float(value)
    return value


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _quality(whole):
    quality = {}
    for name in QUALITY_FIELDS:
        values = whole[name].dropna().astype(float)
        if values.empty:
            quality[name] = {"median": None, "iqr": None}
            continue
        q1, median, q3 = np.percentile(values, [25, 50, 75])
        quality[name] = {"median": median, "iqr": q3 - q1}
    return quality


def _passes_gate(whole, gate):
    passing = np.ones(len(whole), dtype=bool)
    for key, limit in gate.items():
        name, bound = key.rsplit("_", 1)
        values = whole[name].astype(float)
        if bound == "max":
            passing &= (values <= limit).to_numpy()
        elif bound == "min":
            passing &= (values >= limit).to_numpy()
        else:
            raise ValueError(f"quality gate key {key!r} must end in _min or _max")
    return int(passing.sum())


def _condition_entry(frame, condition, unit, gate):
    funnel = funnel_counts(frame)
    n_whole = int(funnel.loc[funnel["stage"] == "broke_in", "count"].iloc[0])
    whole = frame[frame["broke_in"].astype(bool)]
    return {
        "condition": condition,
        "n_units": int(frame[UNIT_ID_COLUMN[unit]].nunique()),
        "n_cells": int(frame["cell_id"].nunique()),
        "n_attempts": len(frame),
        "n_whole_cell": n_whole,
        "minutes_per_whole_cell": _ratio(frame["duration_s"].sum() / 60.0, n_whole),
        "whole_cells_per_slice": _ratio(n_whole, frame["slice_id"].nunique()),
        "quality": _quality(whole),
        "n_passing_gate": _passes_gate(whole, gate),
        "funnel": funnel.to_dict(orient="records"),
    }


def _rate(eligible, ineligible):
    return {
        "eligible": eligible,
        "ineligible": ineligible,
        "rate": _ratio(eligible, eligible + ineligible),
    }


def _eligibility(frame, trial, decisions, margin):
    cell_conditions = {}
    for name in trial.mutators:
        keys = _keys(frame, name)
        cell_conditions[name] = {
            cell: key for cell, key in zip(frame["cell_id"], keys) if key is not None
        }
    result = {}
    for name in trial.mutators:
        mine = [d for d in decisions if d.get("mutator") == name]
        ineligible = sum(1 for d in mine if d.get("eligible") is False)
        entry = _rate(len(mine) - ineligible, ineligible)
        entry["by"] = {}
        split = False
        cell_decisions = [d for d in mine if d.get("unit") == "cell"]
        for other in trial.mutators:
            if other == name:
                continue
            groups = {}
            for d in cell_decisions:
                key = cell_conditions[other].get(d.get("unit_id"))
                if key is None:
                    continue
                counts = groups.setdefault(key, [0, 0])
                counts[d.get("eligible") is False] += 1
            by = {key: _rate(*counts) for key, counts in sorted(groups.items())}
            rates = [g["rate"] for g in by.values()]
            if rates and max(rates) - min(rates) > margin:
                split = True
            entry["by"][other] = by
        entry["split"] = split
        result[name] = entry
    return result


def _asked_rates(trial, closes):
    result = {}
    for name, spec in trial.mutators.items():
        units = {}
        for line in closes:
            if line.get("unit") == spec["unit"]:
                units.setdefault(line["unit_id"], False)
                if name in line.get("asked", ()):
                    units[line["unit_id"]] = True
        asked = sum(units.values())
        result[name] = {
            "asked": asked,
            "closed": len(units),
            "rate": _ratio(asked, len(units)),
        }
    return result


def _provenance(cells):
    protocols = cells.groupby("protocol_sha256", dropna=False).size()
    summary = {
        "protocol_sha256": [
            {"value": value, "n_cells": int(n)} for value, n in protocols.items()
        ]
    }
    for repo in ("acq4", "config"):
        columns = [f"{repo}_sha", f"{repo}_branch", f"{repo}_dirty"]
        versions = cells.groupby(columns, dropna=False).size()
        summary[repo] = [
            {"sha": sha, "branch": branch, "dirty": dirty, "n_cells": int(n)}
            for (sha, branch, dirty), n in versions.items()
        ]
    return summary


def _warnings(frame, trial, n_units_by_condition, provenance):
    warnings = []
    for name in trial.mutators:
        if _keys(frame, name).isna().all():
            warnings.append(
                f"mutator {name!r} never fired: no cell carries a condition for it"
            )
    unit = trial.mutators[trial.primary_factor]["unit"]
    if unit != "cell":
        n_units = sum(n_units_by_condition)
        warnings.append(
            f"primary factor is randomized per {unit}: {n_units} {unit} units are the "
            f"samples, not the cells"
        )
    if len(provenance["protocol_sha256"]) > 1:
        warnings.append(
            f"{len(provenance['protocol_sha256'])} protocol versions in this data"
        )
    for repo in ("acq4", "config"):
        if len(provenance[repo]) > 1:
            warnings.append(f"{len(provenance[repo])} {repo} versions in this data")
    return warnings


def summarize(frame, trial, ledger_lines, margin=ELIGIBILITY_SPLIT_MARGIN):
    primary = trial.primary_factor
    spec = trial.mutators[primary]
    gate = dict(trial.quality_gate or DEFAULT_GATE)
    primary_keys = _keys(frame, primary)
    assigned = frame[primary_keys.notna()]
    conditions = [
        _condition_entry(
            frame[primary_keys == condition_key(condition)],
            condition,
            spec["unit"],
            gate,
        )
        for condition in spec["conditions"]
    ]
    provenance = _provenance(assigned.drop_duplicates("cell_id"))
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "trial_id": trial.id,
        "run_id": trial.run_id,
        "primary_factor": primary,
        "unit": spec["unit"],
        "no_units_assigned": assigned.empty,
        "quality_gate": gate,
        "conditions": conditions,
        "eligibility": _eligibility(
            frame,
            trial,
            [line for line in ledger_lines if line.get("event") == "decision"],
            margin,
        ),
        "asked_rate": _asked_rates(
            trial, [line for line in ledger_lines if line.get("event") == "unit_close"]
        ),
        "provenance": provenance,
        "warnings": _warnings(
            frame, trial, [c["n_units"] for c in conditions], provenance
        ),
    }
    return _clean(summary)


def validate_summary(summary):
    errors = [f"missing key {key!r}" for key in SUMMARY_KEYS if key not in summary]
    if summary.get("schema_version", SUMMARY_SCHEMA_VERSION) != SUMMARY_SCHEMA_VERSION:
        errors.append(
            f"schema_version {summary['schema_version']!r} is not {SUMMARY_SCHEMA_VERSION}"
        )
    for i, entry in enumerate(summary.get("conditions") or ()):
        errors += [
            f"conditions[{i}] is missing key {key!r}"
            for key in CONDITION_KEYS
            if key not in entry
        ]
    try:
        json.dumps(summary, allow_nan=False)
    except (TypeError, ValueError) as exc:
        errors.append(f"summary is not strict JSON: {exc}")
    return errors


def _format(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def format_text(summary):
    lines = []
    if summary["no_units_assigned"]:
        lines.append("no units assigned")
    lines.append(
        f"trial {summary['trial_id']}  run {summary['run_id']}  "
        f"primary factor {summary['primary_factor']} (unit: {summary['unit']})"
    )
    lines.append("")
    for entry in summary["conditions"]:
        lines.append(f"{summary['primary_factor']} = {entry['condition']!r}")
        lines.append(
            f"  units {entry['n_units']}  cells {entry['n_cells']}  "
            f"attempts {entry['n_attempts']}  whole cells {entry['n_whole_cell']}"
        )
        lines.append(
            f"  minutes per whole cell {_format(entry['minutes_per_whole_cell'])}  "
            f"whole cells per slice {_format(entry['whole_cells_per_slice'])}"
        )
        for name, q in entry["quality"].items():
            lines.append(
                f"  {name}: median {_format(q['median'])}  IQR {_format(q['iqr'])}"
            )
        lines.append(f"  passing gate {entry['n_passing_gate']}")
        funnel = "  ->  ".join(f"{s['stage']} {s['count']}" for s in entry["funnel"])
        lines.append(f"  funnel: {funnel}")
        lines.append("")
    for name, e in summary["eligibility"].items():
        flag = "  SPLIT" if e["split"] else ""
        lines.append(
            f"eligibility {name}: {e['eligible']}/{e['eligible'] + e['ineligible']} "
            f"({_format(e['rate'])}){flag}"
        )
    for name, a in summary["asked_rate"].items():
        lines.append(f"asked {name}: {a['asked']}/{a['closed']} ({_format(a['rate'])})")
    lines.append("")
    for p in summary["provenance"]["protocol_sha256"]:
        lines.append(f"protocol {p['value']}: {p['n_cells']} cells")
    for repo in ("acq4", "config"):
        for v in summary["provenance"][repo]:
            dirty = " dirty" if v["dirty"] else ""
            lines.append(
                f"{repo} {v['sha']} ({v['branch']}{dirty}): {v['n_cells']} cells"
            )
    if summary["warnings"]:
        lines.append("")
        lines += [f"warning: {w}" for w in summary["warnings"]]
    return "\n".join(lines) + "\n"


def plot_metric_pair(summary, path):
    labels = [repr(entry["condition"]) for entry in summary["conditions"]]
    panels = [
        ("minutes_per_whole_cell", "Minutes per whole cell"),
        ("whole_cells_per_slice", "Whole cells per slice"),
    ]
    fig = Figure(figsize=(8, 3.5), layout="constrained")
    FigureCanvasAgg(fig)
    for ax, (key, title) in zip(fig.subplots(1, 2), panels):
        values = [entry[key] for entry in summary["conditions"]]
        heights = [0.0 if v is None else v for v in values]
        bars = ax.bar(labels, heights, color=BAR_COLOR, width=0.6)
        ax.bar_label(bars, labels=[_format(v) for v in values], padding=2)
        ax.set_title(title, loc="left")
        ax.set_xlabel(summary["primary_factor"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.3)
        ax.set_axisbelow(True)
        ax.margins(y=0.12)
    fig.savefig(path, dpi=100)


def write(frame, trial, out_dir, ledger_lines=None):
    if ledger_lines is None:
        ledger_lines = slice_ledger_lines(Path(trial.dir) / "data")
    out_dir = Path(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    summary = summarize(frame, trial, ledger_lines)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False)
    )
    (out_dir / "report.txt").write_text(format_text(summary))
    plot_metric_pair(summary, out_dir / PLOT_NAME)
    return summary
