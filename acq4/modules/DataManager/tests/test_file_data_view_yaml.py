"""Tests that the Data tab renders a .yaml file as a browsable tree.

Dicts, lists and scalars all have to show up; keys keep the order they appear in
the document, and epoch timestamps are spelled out as dates.
"""
import time

import pytest

from acq4.filetypes.YamlFile import YamlFile
from acq4.modules.DataManager.FileDataView import FileDataView, YamlTreeWidget
from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeFileHandle:
    def __init__(self, path):
        self._path = str(path)

    def isDir(self):
        return False

    def fileType(self):
        return "YamlFile"

    def name(self, relativeTo=None):
        return self._path

    def read(self):
        return YamlFile.read(self)


def _yamlFile(tmp_path, text, name="data.yaml"):
    path = tmp_path / name
    path.write_text(text)
    return _FakeFileHandle(path)


def _tree(view):
    trees = view.findChildren(YamlTreeWidget)
    assert len(trees) == 1
    return trees[0]


def _rows(item):
    """(key, type, value) for an item and everything under it, depth first."""
    rows = []
    for i in range(item.childCount()):
        child = item.child(i)
        rows.append((child.text(0), child.text(1), child.text(2)))
        rows.extend(_rows(child))
    return rows


def test_mapping_is_shown_as_key_value_rows(qapp, tmp_path):
    view = FileDataView(None)
    fh = _yamlFile(tmp_path, "name: alpha\ncount: 3\n")

    view.setCurrentFile(fh)

    rows = _rows(_tree(view).invisibleRootItem())
    assert ("name", "str", "alpha") in rows
    assert ("count", "int", "3") in rows


def test_keys_keep_document_order(qapp, tmp_path):
    view = FileDataView(None)
    fh = _yamlFile(tmp_path, "zebra: 1\nalpha: 2\nmiddle: 3\n")

    view.setCurrentFile(fh)

    assert [r[0] for r in _rows(_tree(view).invisibleRootItem())] == ["zebra", "alpha", "middle"]


def test_list_of_scalars_gets_a_row_per_item(qapp, tmp_path):
    view = FileDataView(None)
    fh = _yamlFile(tmp_path, "pipettes:\n  - one\n  - two\n")

    view.setCurrentFile(fh)

    rows = _rows(_tree(view).invisibleRootItem())
    assert ("pipettes", "list", "length=2") in rows
    assert ("0", "str", "one") in rows
    assert ("1", "str", "two") in rows


def test_top_level_list_of_mappings_is_shown(qapp, tmp_path):
    view = FileDataView(None)
    fh = _yamlFile(tmp_path, "- cell: 1\n  ok: true\n- cell: 2\n  ok: false\n")

    view.setCurrentFile(fh)

    rows = _rows(_tree(view).invisibleRootItem())
    assert ("0", "dict", "length=2") in rows
    assert ("cell", "int", "1") in rows
    assert ("cell", "int", "2") in rows


def test_epoch_timestamps_are_spelled_out(qapp, tmp_path):
    stamp = 1700000000.5
    view = FileDataView(None)
    fh = _yamlFile(tmp_path, f"startTime: {stamp}\n")

    view.setCurrentFile(fh)

    rows = _rows(_tree(view).invisibleRootItem())
    expected = time.strftime("%Y.%m.%d %H:%M:%S", time.localtime(stamp))
    assert any(r[0] == "startTime" and expected in r[2] for r in rows)


def test_switching_away_from_yaml_clears_the_panel(qapp, tmp_path):
    view = FileDataView(None)
    view.setCurrentFile(_yamlFile(tmp_path, "name: alpha\n"))

    view.setCurrentFile(None)

    assert view.findChildren(YamlTreeWidget) == []
