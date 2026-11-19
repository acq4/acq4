"""Tests for joining parsed attempts with each cell's performance_tuning block."""

import json
import os

import pandas as pd

from acq4.modules.Autopatch.performance_tuning import join
from acq4.modules.Autopatch.performance_tuning.ledger import MIRROR_NAME

from .conftest import RUN_ID, make_cell


def test_block_for_reads_the_cell_block(dataset):
    block = join.block_for(dataset["cells"]["c1"])
    assert block["run_id"] == RUN_ID
    assert block["conditions"] == {"seal_timeout": 30.0}
    assert join.block_for(dataset["cells"]["c1"].name())["survey_id"] == "s1"


def test_block_for_untuned_cell_is_none(dataset):
    assert join.block_for(dataset["cells"]["untuned"]) is None


def test_join_drops_untuned_cells_and_other_runs(dataset):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    cells = dataset["cells"]
    expected = {cells[k].info()["__uuid__"] for k in ("c1", "c2", "c3", "c4", "c5")}
    assert set(frame["cell_id"]) == expected
    assert len(frame) == 5


def test_join_id_columns(dataset):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    c4 = dataset["cells"]["c4"]
    row = frame[frame["cell_id"] == c4.info()["__uuid__"]].iloc[0]
    assert row["slice_id"] == dataset["slices"]["B"].info()["__uuid__"]
    assert row["survey_id"] == "s3"
    assert row["seal_timeout"] == 60.0
    assert row["duration_s"] == 240.0


def test_join_provenance_columns(dataset):
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    row = frame.iloc[0]
    assert row["acq4_sha"] == "aaa111"
    assert row["acq4_branch"] == "mini-rig"
    assert not row["acq4_dirty"]
    assert row["config_sha"] == "ccc111"
    assert row["config_dirty"]
    assert row["protocol_sha256"] == "p1"


def test_unassigned_mutator_column_is_empty(dataset):
    make_cell(
        dataset["slices"]["A"],
        "cell_009",
        {"min_health": 0.7},
        duration=30.0,
        whole_cell=False,
    )
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    assert len(frame) == 6
    health = frame[frame["min_health"].notna()]
    assert list(health["min_health"]) == [0.7]
    assert pd.isna(health["seal_timeout"]).all()
    assert frame["seal_timeout"].notna().sum() == 5


def test_missing_provenance_gives_empty_columns(dataset):
    make_cell(
        dataset["slices"]["A"],
        "cell_010",
        {"seal_timeout": 30.0},
        provenance={"acq4": None, "config": None, "protocol_sha256": "p1"},
        duration=30.0,
        whole_cell=False,
    )
    frame = join.attempts_with_conditions(dataset["data_dir"], RUN_ID)
    assert frame["acq4_sha"].isna().sum() == 1


def test_slice_ledger_lines_reads_every_mirror(dataset):
    for key in ("A", "B"):
        path = os.path.join(dataset["slices"][key].name(), MIRROR_NAME)
        with open(path, "w") as f:
            f.write(
                json.dumps({"event": "unit_open", "slice": key, "run_id": RUN_ID})
                + "\n"
            )
    lines = join.slice_ledger_lines(dataset["data_dir"], RUN_ID)
    assert sorted(line["slice"] for line in lines) == ["A", "B"]


def test_slice_ledger_lines_keeps_only_this_run(dataset):
    path = os.path.join(dataset["slices"]["A"].name(), MIRROR_NAME)
    with open(path, "w") as f:
        for run_id in (RUN_ID, "run-b", RUN_ID):
            f.write(json.dumps({"event": "unit_open", "run_id": run_id}) + "\n")
    lines = join.slice_ledger_lines(dataset["data_dir"], RUN_ID)
    assert [line["run_id"] for line in lines] == [RUN_ID, RUN_ID]
