"""Builds the BRIEF.md that tells an agent how to write an ad hoc analysis of a trial."""

import inspect
import json
import re
from pathlib import Path

import yaml

from acq4.modules.Autopatch.analysis import autopatch_log, autopatch_metrics
from acq4.util.tuning_points import POINTS

from . import join, report
from .ledger import MIRROR_NAME
from .mutators import MUTATORS

KINDS = {"script": "analyze.py", "notebook": "analyze.ipynb"}

METADATA_CONTRACT = """\
{"performance_tuning": {
    "run_id": "2026-11-14-seal-health",
    "survey_id": "…",
    "conditions": {"seal_timeout": 30.0, "min_health": 0.7},
    "assigned_by": {"seal_timeout": "cell", "min_health": "survey"},
    "fired": {"seal_timeout": {"patching": 2}},
    "provenance": {
        "acq4": {"sha": "…", "branch": "mini-rig", "dirty": False},
        "config": {"sha": "…", "branch": "main", "dirty": True},
        "protocol_sha256": "…",
    },
}}"""

CONTRACT_NOTES = """\
The cell's own `__uuid__` and its `slice_id` are already on the index, so the block
repeats neither. A mutator that was never asked in this cell, or found it ineligible,
is absent from `conditions`. Ineligibility lives only in the ledger. Survey `fired`
counts live in the ledger at survey-unit exit, not on the cell. A cell with no
`performance_tuning` key was not part of any armed run."""

STATISTICS_CAVEAT = """\
Report the unit count beside the cell count: the unit, not the cell, is the unit of
assignment. Survey- and slice-unit trials have few units and so few samples; say so
instead of presenting a small difference as a finding."""

RULES = """\
- The data is read-only.
- Write only under this analysis's `out/`.
- Import from `acq4.modules.Autopatch.analysis` and `performance_tuning` rather than
  reimplementing parsing.
- To be acceptable, write `out/summary.json` via `report.write` or in its schema."""


def next_analysis_dir(trial, slug):
    analyses = Path(trial.dir) / "analyses"
    numbers = [
        int(m.group(1))
        for p in analyses.glob("*-*")
        if (m := re.match(r"(\d+)-", p.name))
    ]
    path = analyses / f"{max(numbers, default=0) + 1:03d}-{slug}"
    (path / "out").mkdir(parents=True)
    return path


def write_brief(analysis_dir, text):
    path = Path(analysis_dir) / "BRIEF.md"
    path.write_text(text)
    return path


def _fenced(text, lang=""):
    return f"```{lang}\n{text.rstrip()}\n```"


def _record_section(trial):
    mutators = yaml.safe_dump(trial.mutators, sort_keys=False)
    return "\n\n".join(
        [
            f"# Analysis brief: {trial.title}",
            f"## Trial\n\nHypothesis: {trial.hypothesis.strip()}\n\n"
            f"Primary factor: `{trial.primary_factor}`\n\n"
            f"Run id: `{trial.run_id}`",
            "Armed mutators:\n\n" + _fenced(mutators, "yaml"),
            "Quality gate: " + json.dumps(trial.quality_gate),
            "Interaction signoff: " + (trial.interaction_signoff.strip() or "none"),
        ]
    )


def _points_answered(cls):
    return sorted(getattr(cls, "answers", set()) | getattr(cls, "wraps", set()))


def _mutator_section(trial):
    parts = ["## What each condition changes"]
    for name in trial.mutators:
        cls = MUTATORS[name]
        parts.append(
            f"### `{name}` ({cls.__name__})\n\n{_fenced(inspect.getsource(cls), 'python')}"
        )
        for point_name in _points_answered(cls):
            point = POINTS.get(point_name)
            if point is None:
                continue
            parts.append(
                f"Tuning point `{point_name}` ({point.kind}, unit hint "
                f"{point.unit_hint}, facts {list(point.facts)}): {point.doc} "
                f"Site: {point.site}"
            )
    return "\n\n".join(parts)


def _paths_section(trial):
    lines = ["## Data (read-only)", ""]
    for name in trial.data:
        path = (Path(trial.dir) / "data" / name).resolve()
        ledger = path / MIRROR_NAME
        lines.append(f"- slice dir: `{path}`{'' if path.exists() else ' (missing)'}")
        lines.append(f"  ledger: `{ledger}`{'' if ledger.exists() else ' (missing)'}")
    if not trial.data:
        lines.append("No data is linked to this trial yet.")
    return "\n".join(lines)


def _contract_section():
    return "\n\n".join(
        [
            "## Metadata contract",
            "One nested key on the cell's index, written once at cell-unit exit:",
            _fenced(METADATA_CONTRACT, "python"),
            CONTRACT_NOTES,
        ]
    )


def _entry_points(module, qualified):
    entries = []
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != module.__name__:
            continue
        doc = inspect.getdoc(fn) or ""
        entries.append(f"### `{qualified}.{name}{inspect.signature(fn)}`\n\n{doc}")
    return entries


def _helpers_section():
    parts = ["## Analysis helpers"]
    for module, qualified in (
        (join, "join"),
        (report, "report"),
        (autopatch_log, "autopatch_log"),
        (autopatch_metrics, "autopatch_metrics"),
    ):
        parts += _entry_points(module, qualified)
    return "\n\n".join(parts)


def _earlier_summary_section(trial):
    summaries = sorted(
        (Path(trial.dir) / "analyses").glob("*/out/summary.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not summaries:
        return (
            "## Earlier analyses\n\nThere is no earlier analysis with a summary.json."
        )
    latest = summaries[-1]
    return f"## Earlier analyses\n\nLatest summary.json (`{latest}`):\n\n" + _fenced(
        latest.read_text(), "json"
    )


def build_brief(trial, question, kind="script"):
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}, not {kind!r}")
    return (
        "\n\n".join(
            [
                _record_section(trial),
                _mutator_section(trial),
                _paths_section(trial),
                _contract_section(),
                _helpers_section(),
                _earlier_summary_section(trial),
                "## Statistics\n\n" + STATISTICS_CAVEAT,
                f"## Rules\n\nWrite the analysis as `{KINDS[kind]}` in this directory.\n\n{RULES}",
                "## The question\n\n" + question,
            ]
        )
        + "\n"
    )
