"""Tests for directory uuids and ancestor-id association in the DataManager."""
import os
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


def _rawFile(dirHandle, name):
    with open(os.path.join(dirHandle.name(), name), "wb") as fh:
        fh.write(b"x")


def test_created_files_get_a_uuid(root):
    assert len(root.createFile("blank.txt").info()["__uuid__"]) == 32


def test_written_files_get_a_uuid(root):
    fh = root.writeFile({"a": 1}, "a.yaml", fileType="YamlFile")
    assert len(fh.info()["__uuid__"]) == 32


def test_indexed_files_get_a_uuid(root):
    _rawFile(root, "raw.bin")
    root.indexFile("raw.bin")
    assert len(root["raw.bin"].info()["__uuid__"]) == 32


def test_files_get_distinct_uuids(root):
    assert root.createFile("a.txt").info()["__uuid__"] != root.createFile("b.txt").info()["__uuid__"]


def test_rewriting_a_file_keeps_its_uuid(root):
    first = root.writeFile({"v": 1}, "s.yaml", fileType="YamlFile").info()["__uuid__"]
    second = root.writeFile({"v": 2}, "s.yaml", fileType="YamlFile").info()["__uuid__"]
    assert first == second


def test_re_indexing_a_file_keeps_its_uuid(root):
    _rawFile(root, "raw.bin")
    root.indexFile("raw.bin")
    first = root["raw.bin"].info()["__uuid__"]
    root.indexFile("raw.bin", info={"k": 1})
    assert root["raw.bin"].info()["__uuid__"] == first


def test_a_supplied_file_uuid_is_kept(root):
    assert root.createFile("a.txt", info={"__uuid__": "fixed"}).info()["__uuid__"] == "fixed"


def test_indexed_files_get_ancestor_ids(root):
    slice_dir = root.mkdir("slice_000")
    slice_dir.setInfo({"dirType": "Slice"})
    _rawFile(slice_dir, "raw.bin")
    slice_dir.indexFile("raw.bin")
    assert slice_dir["raw.bin"].info()["slice_id"] == slice_dir.info()["__uuid__"]


def test_index_file_leaves_the_callers_info_alone(root):
    _rawFile(root, "raw.bin")
    info = {"k": 1}
    root.indexFile("raw.bin", info=info)
    assert info == {"k": 1}
