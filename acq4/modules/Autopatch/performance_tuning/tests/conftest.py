"""Builds a small tuned dataset on disk: slice and cell directories with real index metadata and MultiPatch logs."""

import os

import pytest

import acq4.util.DataManager as dm
from acq4.modules.Autopatch.analysis.tests.test_autopatch_log import _state, _tp

RUN_ID = "run-a"
PROVENANCE = {
    "acq4": {"sha": "aaa111", "branch": "mini-rig", "dirty": False},
    "config": {"sha": "ccc111", "branch": "main", "dirty": True},
    "protocol_sha256": "p1",
}


def write_log(
    cell_dir, duration, whole_cell, access=10e6, rin=200e6, cap=10e-12, ibase=-50e-12
):
    if whole_cell:
        lines = [
            _state(0.0, "bath", "out"),
            _state(5.0, "approach", "bath"),
            _state(10.0, "seal", "approach"),
            _state(15.0, "cell attached", "seal"),
            _state(20.0, "break in", "cell attached"),
            _state(25.0, "whole cell", "break in"),
            _tp(duration, ssr=3e8, access=access, rin=rin, cap=cap, ibase=ibase),
        ]
    else:
        lines = [
            _state(0.0, "bath", "out"),
            _state(5.0, "approach", "bath"),
            _state(10.0, "seal", "approach"),
            _state(duration, "fouled", "seal"),
        ]
    path = os.path.join(cell_dir.name(), "MultiPatch_000.log")
    with open(path, "w") as f:
        f.write("".join(line + ",\n" for line in lines))


def make_cell(
    slice_dir,
    name,
    conditions,
    run_id=RUN_ID,
    survey_id="s1",
    provenance=PROVENANCE,
    **log,
):
    cell = slice_dir.mkdir(name, info={"dirType": "Cell"})
    if conditions is not None:
        cell.setInfo(
            {
                "performance_tuning": {
                    "run_id": run_id,
                    "survey_id": survey_id,
                    "conditions": conditions,
                    "assigned_by": {k: "cell" for k in conditions},
                    "fired": {},
                    "provenance": provenance,
                }
            }
        )
    write_log(cell, **log)
    return cell


@pytest.fixture
def dataset(tmp_path):
    """Two slices, five tuned cells, plus one untuned cell and one from another run.

    seal_timeout=30.0: c1 (whole, 60 s, A), c3 (fail, 180 s, A), c5 (whole, 60 s, B)
    seal_timeout=60.0: c2 (fail, 120 s, A), c4 (whole, 240 s, B)
    """
    root = dm.getDirHandle(str(tmp_path / "rig"), create=True)
    a = root.mkdir("slice_000", info={"dirType": "Slice"})
    b = root.mkdir("slice_001", info={"dirType": "Slice"})
    cells = {
        "c1": make_cell(
            a,
            "cell_000",
            {"seal_timeout": 30.0},
            duration=60.0,
            whole_cell=True,
            access=10e6,
        ),
        "c2": make_cell(
            a, "cell_001", {"seal_timeout": 60.0}, duration=120.0, whole_cell=False
        ),
        "c3": make_cell(
            a,
            "cell_002",
            {"seal_timeout": 30.0},
            survey_id="s2",
            duration=180.0,
            whole_cell=False,
        ),
        "c4": make_cell(
            b,
            "cell_000",
            {"seal_timeout": 60.0},
            survey_id="s3",
            duration=240.0,
            whole_cell=True,
            access=30e6,
        ),
        "c5": make_cell(
            b,
            "cell_001",
            {"seal_timeout": 30.0},
            survey_id="s3",
            duration=60.0,
            whole_cell=True,
            access=20e6,
        ),
        "untuned": make_cell(b, "cell_002", None, duration=60.0, whole_cell=True),
        "other_run": make_cell(
            b,
            "cell_003",
            {"seal_timeout": 30.0},
            run_id="run-b",
            duration=60.0,
            whole_cell=True,
        ),
    }
    data = tmp_path / "trial" / "data"
    data.mkdir(parents=True)
    for s in (a, b):
        os.symlink(s.name(), data / os.path.basename(s.name()))
    return {"data_dir": str(data), "slices": {"A": a, "B": b}, "cells": cells}
