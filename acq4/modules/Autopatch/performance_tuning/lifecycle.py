"""The trial lifecycle behind the review window: arm, link data, analyse, accept, reject and abandon.

Qt-free, so each step can be driven and tested without a widget; TuningWindow wraps these in dialogs.
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

from acq4.util import tuning_points
from acq4.util.tuning_points import TuningPointWarning

from . import agent, arming, brief, catalogue, provenance, record, report
from .join import slice_ledger_lines
from .ledger import JsonlLedger, ledger_path

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SCRIPT_NAME = brief.KINDS["script"]
NOTEBOOK_NAME = brief.KINDS["notebook"]
ACCEPTED_NAME = "accepted_analysis.py"
HEADLINE_KEYS = (
    "condition",
    "n_units",
    "n_cells",
    "n_whole_cell",
    "minutes_per_whole_cell",
    "whole_cells_per_slice",
    "n_passing_gate",
)


class Refused(ValueError):
    """A lifecycle step that will not be taken, with the reason to show the operator."""


REFUSALS = (Refused, tuning_points.TuningPointError)


def group_of(trials_dir, trial):
    return [t for t in record.all_trials(trials_dir) if t.run_id == trial.run_id]


def problems(trial, group):
    siblings = [t for t in group if t.dir != trial.dir]
    return record.validate(trial, siblings) + record.stale_snapshot(trial)


def arm_warnings(trial):
    return arming.check(record.instantiate(record.load(trial.dir))).warnings


def arm(autopatch, manager, trials_dir, trial):
    group = group_of(trials_dir, trial)
    trial = next(t for t in group if t.dir == Path(trial.dir))
    found = [f"trial {t.id}: {p}" for t in group for p in problems(t, group)]
    if found:
        raise Refused("; ".join(found))
    mutators = record.instantiate(trial)
    result = arming.check(mutators)
    if result.errors:
        raise Refused("; ".join(result.errors))
    if result.warnings and not trial.interaction_signoff.strip():
        raise Refused(
            "these warnings need an interaction signoff: " + "; ".join(result.warnings)
        )
    protocol = str(record._acq4_root() / trial.protocol)
    ledger = JsonlLedger(ledger_path(manager, trial.run_id))
    hook = provenance.make_cell_close_hook(protocol, manager.configDir)
    arming.arm(autopatch, trial.run_id, mutators, ledger, cell_close_hook=hook)
    try:
        ids = ", ".join(t.id for t in group)
        autopatch.protocolPanel.pinProtocol(
            protocol, f"Run group {trial.run_id} armed (trials {ids})"
        )
    except Exception:
        arming.release(autopatch)
        raise
    for t in group:
        if t.status == "planned":
            t.status = "collecting"
            record.save(t)


def disarm(autopatch):
    if tuning_points.installed() is None:
        raise Refused("no run group is armed")
    arming.disarm(autopatch)
    autopatch.protocolPanel.unpinProtocol()


class WarningCollector:
    """While started, hands every TuningPointWarning to `on_warning`, repeats included, and passes other warnings on."""

    def __init__(self, on_warning):
        self._on_warning = on_warning
        self._catcher = None

    def start(self):
        if self._catcher is not None:
            return
        self._catcher = warnings.catch_warnings()
        self._catcher.__enter__()
        warnings.simplefilter("always", TuningPointWarning)
        pass_on = warnings.showwarning

        def show(message, category, filename, lineno, file=None, line=None):
            if issubclass(category, TuningPointWarning):
                self._on_warning(str(message))
            else:
                pass_on(message, category, filename, lineno, file, line)

        warnings.showwarning = show

    def stop(self):
        if self._catcher is None:
            return
        self._catcher.__exit__(None, None, None)
        self._catcher = None


def linkable_slice_dirs(manager, trial):
    if manager is None:
        return []
    linked = set(record.load(trial.dir).data)
    ledger = JsonlLedger(ledger_path(manager, trial.run_id))
    return [d for d in ledger.slice_dirs() if os.path.basename(d) not in linked]


def link_data(trials_dir, trial, slice_dirs):
    for t in group_of(trials_dir, trial):
        for slice_dir in slice_dirs:
            name = os.path.basename(slice_dir)
            link = Path(t.dir) / "data" / name
            if link.is_symlink():
                if link.resolve() != Path(slice_dir).resolve():
                    raise Refused(f"{link} already links elsewhere")
            else:
                link.parent.mkdir(exist_ok=True)
                os.symlink(slice_dir, link)
            if name not in t.data:
                t.data.append(name)
        record.save(t)


def new_analysis(config, trial, slug, question, kind, open_editor):
    if not SLUG_PATTERN.match(slug):
        raise Refused(f"slug {slug!r} must match {SLUG_PATTERN.pattern}")
    trial = record.load(trial.dir)
    text = brief.build_brief(trial, question, kind)
    analysis_dir = brief.next_analysis_dir(trial, slug)
    brief.write_brief(analysis_dir, text)
    agent.launch(analysis_dir, config, open_editor=open_editor)
    return analysis_dir


def missing_analysis(analysis_dir):
    return Refused(f"{analysis_dir.name} has no {SCRIPT_NAME} or {NOTEBOOK_NAME}")


def run_script(analysis_dir):
    """Runs analyze.py against this checkout's acq4, and returns out/report.txt (None if it wrote none)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(record._acq4_root()), env.get("PYTHONPATH")) if p
    )
    done = subprocess.run(
        [sys.executable, SCRIPT_NAME],
        cwd=analysis_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise Refused(
            f"{SCRIPT_NAME} exited with status {done.returncode}:\n"
            + done.stderr[-4000:]
        )
    report_path = Path(analysis_dir) / "out" / "report.txt"
    return report_path.read_text() if report_path.exists() else None


def _accepted_script(analysis_dir):
    script = analysis_dir / SCRIPT_NAME
    if script.exists():
        return script.read_text()
    notebook = analysis_dir / NOTEBOOK_NAME
    if not notebook.exists():
        raise missing_analysis(analysis_dir)
    if importlib.util.find_spec("nbconvert") is None:
        raise Refused(
            "accepting a notebook needs nbconvert to export it to a script, "
            "and nbconvert is not installed in this environment"
        )
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--to",
            "script",
            "--stdout",
            str(notebook),
        ],
        capture_output=True,
        text=True,
    )
    if done.returncode != 0:
        raise Refused(f"nbconvert could not export {notebook.name}:\n{done.stderr}")
    return done.stdout


def _regenerate_tracking():
    if importlib.util.find_spec(f"{__package__}.tracking") is None:
        return
    from . import tracking

    tracking.regenerate()


def set_factor_status(catalogue_path, name, status):
    entries = catalogue.load(catalogue_path)
    next(e for e in entries if e.name == name).status = status
    catalogue.save(entries, catalogue_path)


def accept(catalogue_path, trial, analysis_dir, verdict):
    analysis_dir = Path(analysis_dir)
    trial = record.load(trial.dir)
    if not verdict.strip():
        raise Refused("a verdict is required")
    summary_path = analysis_dir / "out" / "summary.json"
    if not summary_path.exists():
        raise Refused(f"{analysis_dir.name} has no out/summary.json")
    summary = json.loads(summary_path.read_text())
    errors = report.validate_summary(summary)
    if errors:
        raise Refused("summary.json does not validate: " + "; ".join(errors))
    script = _accepted_script(analysis_dir)
    (Path(trial.dir) / ACCEPTED_NAME).write_text(script)
    trial.results = {
        "conditions": [
            {key: entry[key] for key in HEADLINE_KEYS}
            for entry in summary["conditions"]
        ],
        "provenance": summary["provenance"],
        "analysis": analysis_dir.name,
    }
    trial.verdict = verdict
    trial.closed_on = date.today().isoformat()
    trial.status = "closed"
    record.save(trial)
    set_factor_status(catalogue_path, trial.primary_factor, "tested")
    _regenerate_tracking()


def reject(trial, note):
    if not note.strip():
        raise Refused("a note is required")
    trial = record.load(trial.dir)
    trial.review_notes.append(note)
    record.save(trial)


def abandon(catalogue_path, trial, reason):
    if not reason.strip():
        raise Refused("a reason is required")
    trial = record.load(trial.dir)
    trial.status = "abandoned"
    trial.review_notes.append(f"abandoned: {reason}")
    record.save(trial)
    set_factor_status(catalogue_path, trial.primary_factor, "untested")


def ledger_lines(trial):
    data = Path(trial.dir) / "data"
    return slice_ledger_lines(data, trial.run_id) if data.is_dir() else []


def cells_so_far(lines):
    return sum(
        1
        for line in lines
        if line.get("event") == "unit_open" and line["unit"] == "cell"
    )


def days_collecting(trial, lines):
    stamps = [line["t"] for line in lines if line.get("t")]
    if not stamps:
        return None
    start = datetime.fromisoformat(min(stamps)).date()
    end = date.fromisoformat(trial.closed_on) if trial.closed_on else date.today()
    return (end - start).days


def latest_summary(trial):
    summaries = sorted(
        (Path(trial.dir) / "analyses").glob("*/out/summary.json"),
        key=lambda p: p.stat().st_mtime,
    )
    return json.loads(summaries[-1].read_text()) if summaries else None
