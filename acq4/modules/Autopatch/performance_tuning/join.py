"""Join parsed autopatch attempts with each cell's performance_tuning metadata block."""

import copy
import os

import pandas as pd

import acq4.util.DataManager as dm
from acq4.modules.Autopatch.analysis import autopatch_log, autopatch_metrics

from .ledger import MIRROR_NAME, read_lines

BLOCK_KEY = "performance_tuning"
ID_COLUMNS = ("cell_id", "slice_id", "survey_id")
PROVENANCE_COLUMNS = (
    "acq4_sha",
    "acq4_branch",
    "acq4_dirty",
    "config_sha",
    "config_branch",
    "config_dirty",
    "protocol_sha256",
)


def _dir_handle(cell_dir):
    if hasattr(cell_dir, "info"):
        return cell_dir
    return dm.getDirHandle(str(cell_dir))


def block_for(cell_dir):
    block = _dir_handle(cell_dir).info().get(BLOCK_KEY)
    return None if block is None else copy.deepcopy(block)


def object_column(values):
    """A column that keeps None for "not assigned" rather than coercing it to NaN."""
    return pd.Series(list(values), dtype=object)


def _slice_dirs(data_dir):
    return [os.path.join(data_dir, name) for name in sorted(os.listdir(data_dir))]


def _provenance_values(provenance):
    provenance = provenance or {}
    values = {}
    for repo in ("acq4", "config"):
        repo_info = provenance.get(repo) or {}
        for key in ("sha", "branch", "dirty"):
            values[f"{repo}_{key}"] = repo_info.get(key)
    values["protocol_sha256"] = provenance.get("protocol_sha256")
    return values


def attempts_with_conditions(data_dir, run_id):
    attempts = autopatch_log.load_run(_slice_dirs(data_dir))
    frame = autopatch_metrics.attempts_to_dataframe(attempts)
    cells = {}
    for path in frame["source"].map(os.path.dirname).unique():
        handle = _dir_handle(path)
        info = handle.info()
        block = info.get(BLOCK_KEY)
        if block is None or block.get("run_id") != run_id:
            continue
        cells[path] = {
            "cell_id": info.get("__uuid__"),
            "slice_id": info.get("slice_id"),
            "survey_id": block.get("survey_id"),
            "conditions": copy.deepcopy(block.get("conditions") or {}),
            **_provenance_values(copy.deepcopy(block.get("provenance"))),
        }
    cell_paths = frame["source"].map(os.path.dirname)
    frame = frame[cell_paths.isin(cells)].reset_index(drop=True)
    rows = [cells[os.path.dirname(source)] for source in frame["source"]]
    for column in ID_COLUMNS + PROVENANCE_COLUMNS:
        frame[column] = object_column(row[column] for row in rows)
    mutators = sorted({name for row in rows for name in row["conditions"]})
    for name in mutators:
        frame[name] = object_column(row["conditions"].get(name) for row in rows)
    return frame


def slice_ledger_lines(data_dir):
    lines = []
    for slice_dir in _slice_dirs(data_dir):
        lines.extend(read_lines(os.path.join(slice_dir, MIRROR_NAME)))
    return lines
