from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from acq4.util import Qt
from acq4.util.DirTreeWidget.DirTreeWidget import DirTreeWidget


class EmptyDirectory:
    def __init__(self):
        self.sigDelayedChange = SimpleNamespace(connect=Mock(), disconnect=Mock())

    def ls(self, **kwargs):
        return []


@pytest.fixture
def tree():
    app = Qt.QApplication.instance() or Qt.QApplication([])
    widget = DirTreeWidget()
    yield widget
    widget.quit()
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_delayed_change_after_switching_base_directory(tree, monkeypatch):
    old_base = EmptyDirectory()
    new_base = EmptyDirectory()
    tree.setBaseDirHandle(old_base)
    tree.setBaseDirHandle(new_base)
    rebuild = Mock()
    monkeypatch.setattr(tree, 'rebuildChildren', rebuild)
    tree.dirChanged(old_base, ['children', 'renamed', 'deleted'])
    rebuild.assert_not_called()
    tree.dirChanged(new_base, ['children'])
    rebuild.assert_called_once_with(tree.invisibleRootItem())


def test_delayed_change_for_removed_child(tree, monkeypatch):
    tree.setBaseDirHandle(EmptyDirectory())
    removed = EmptyDirectory()
    rebuild = Mock()
    monkeypatch.setattr(tree, 'rebuildChildren', rebuild)
    tree.dirChanged(removed, ['children'])
    rebuild.assert_not_called()


def test_current_child_rename_is_still_applied(tree):
    child = EmptyDirectory()
    child.shortName = lambda: 'renamed'
    item = Qt.QTreeWidgetItem()
    tree.items[child] = item
    tree.dirChanged(child, ['renamed'])
    assert item.text(0) == 'renamed'
