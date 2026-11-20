"""Tests for directory uuids and ancestor-id association in the DataManager."""
import shutil
import tempfile

import pytest

import acq4.util.DataManager as dm


@pytest.fixture
def root():
    path = tempfile.mkdtemp()
    yield dm.getDirHandle(path)
    shutil.rmtree(path)


def test_mkdir_assigns_unique_uuid(root):
    a = root.mkdir("a")
    b = root.mkdir("b")
    assert a.info()["__uuid__"] != b.info()["__uuid__"]
    assert len(a.info()["__uuid__"]) == 32


def test_mkdir_keeps_supplied_uuid(root):
    assert root.mkdir("a", info={"__uuid__": "fixed"}).info()["__uuid__"] == "fixed"


def test_children_get_ancestor_ids_by_dirtype(root):
    slice_dir = root.mkdir("slice_000")
    slice_dir.setInfo({"dirType": "Slice"})
    cell_dir = slice_dir.mkdir("cell_000")
    cell_dir.setInfo({"dirType": "Cell"})
    sub = cell_dir.mkdir("sub")

    assert cell_dir.info()["slice_id"] == slice_dir.info()["__uuid__"]
    assert "cell_id" not in cell_dir.info()
    assert sub.info()["slice_id"] == slice_dir.info()["__uuid__"]
    assert sub.info()["cell_id"] == cell_dir.info()["__uuid__"]


def test_files_get_ancestor_ids(root):
    slice_dir = root.mkdir("slice_000")
    slice_dir.setInfo({"dirType": "Slice"})
    created = slice_dir.createFile("blank.txt")
    assert created.info()["slice_id"] == slice_dir.info()["__uuid__"]


def test_explicit_key_is_not_overwritten(root):
    slice_dir = root.mkdir("slice_000")
    slice_dir.setInfo({"dirType": "Slice"})
    child = slice_dir.mkdir("c", info={"slice_id": "mine"})
    assert child.info()["slice_id"] == "mine"


def test_nearest_ancestor_wins_for_repeated_type(root):
    outer = root.mkdir("outer")
    outer.setInfo({"dirType": "Slice"})
    inner = outer.mkdir("inner")
    inner.setInfo({"dirType": "Slice"})
    leaf = inner.mkdir("leaf")
    assert leaf.info()["slice_id"] == inner.info()["__uuid__"]


def test_dir_made_before_dirtype_has_no_key(root):
    parent = root.mkdir("p")
    early = parent.mkdir("early")
    parent.setInfo({"dirType": "Slice"})
    assert "slice_id" not in early.info()
