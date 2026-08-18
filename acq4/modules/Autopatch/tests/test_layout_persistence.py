"""Tests that the split the operator drags the window into, and the window's own
geometry, survive closing it -- through the same manager config file the Camera
and Manager modules keep their window state in."""
from types import SimpleNamespace

import pytest

from acq4.util import Qt


@pytest.fixture(scope="module")
def qapp():
    return Qt.QApplication.instance() or Qt.QApplication([])


class _FakeDeviceSelector(Qt.QWidget):
    def getSelectedObj(self):
        return None


class _FakeManager:
    """Manager's config-file pair, backed by a dict rather than the config
    directory: a window built by these tests must not write into the real rig's
    configuration, and what is being tested is the round trip, not configfile's
    own serialisation."""

    def __init__(self, files=None):
        self.files = {} if files is None else files

    def readConfigFile(self, fileName, missingOk=True):
        if fileName not in self.files and not missingOk:
            raise FileNotFoundError(fileName)
        return self.files.get(fileName, {})

    def writeConfigFile(self, data, fileName):
        self.files[fileName] = data


def _makeWindow(tmp_path, manager, moduleName="Autopatch"):
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    return AutopatchWindow(
        module=SimpleNamespace(manager=manager, name=moduleName),
        protocolDir=str(tmp_path),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )


def test_the_layout_is_written_to_the_modules_state_file_on_teardown(qapp, tmp_path):
    """Same place, and same shape, as every other module's window state: a
    ``modules/<module name>_ui.cfg`` under the config directory, holding the
    geometry as four numbers and each Qt state blob percent-encoded."""
    manager = _FakeManager()
    win = _makeWindow(tmp_path, manager)
    win.teardown()

    assert list(manager.files) == ["modules/Autopatch_ui.cfg"]
    state = manager.files["modules/Autopatch_ui.cfg"]
    assert len(state["geometry"]) == 4
    assert set(state["splitters"]) == {"columns", "leftColumn", "rightColumn"}
    for blob in state["splitters"].values():
        assert isinstance(blob, str) and blob


def test_a_saved_split_is_what_the_next_window_opens_with(qapp, tmp_path):
    """The point of saving it: an operator who has given the slice view most of
    the window, or squeezed the status area down to a strip, finds it that way
    tomorrow rather than back at this constructor's opening arrangement."""
    manager = _FakeManager()
    first = _makeWindow(tmp_path, manager)
    first.resize(1000, 800)
    first.show()
    qapp.processEvents()
    first.columnSplitter.setSizes([300, 700])
    first.rightColumn.setSizes([40, 260, 460])
    qapp.processEvents()
    saved = (first.columnSplitter.sizes(), first.rightColumn.sizes())
    first.teardown()
    first.close()

    second = _makeWindow(tmp_path, manager)
    second.show()
    qapp.processEvents()
    try:
        assert second.columnSplitter.sizes() == saved[0]
        assert second.rightColumn.sizes() == saved[1]
    finally:
        second.teardown()
        second.close()


def test_a_saved_geometry_is_what_the_next_window_opens_at(qapp, tmp_path):
    manager = _FakeManager()
    first = _makeWindow(tmp_path, manager)
    first.setGeometry(120, 140, 1020, 760)
    first.teardown()

    second = _makeWindow(tmp_path, manager)
    try:
        assert second.geometry().width() == 1020
        assert second.geometry().height() == 760
    finally:
        second.teardown()


def test_each_module_instance_keeps_its_own_layout(qapp, tmp_path):
    """The file is named for the module, as every other module's is, so two
    Autopatch modules configured on one rig do not overwrite each other."""
    manager = _FakeManager()
    win = _makeWindow(tmp_path, manager, moduleName="Autopatch2")
    win.teardown()

    assert list(manager.files) == ["modules/Autopatch2_ui.cfg"]


def test_a_window_with_no_module_neither_saves_nor_restores(qapp, tmp_path):
    """module=None is a supported mode (headless, and every test that builds
    this window without a Manager to stand in for), and there is no config
    directory to keep a layout in there. Teardown must still be quiet."""
    from acq4.modules.Autopatch.Autopatch import AutopatchWindow

    win = AutopatchWindow(
        module=None,
        protocolDir=str(tmp_path),
        pipetteSelector=_FakeDeviceSelector(),
        cameraSelector=_FakeDeviceSelector(),
    )
    win.teardown()  # must not raise


def test_a_layout_saved_by_a_different_window_size_is_ignored_not_crashed_on(
    qapp, tmp_path
):
    """A state file is on disk from a previous version of this window, or was
    hand-edited: a splitter blob Qt refuses is dropped and the window opens at
    its own arrangement, rather than failing to open at all."""
    manager = _FakeManager(
        {
            "modules/Autopatch_ui.cfg": {
                "geometry": [10, 10, 900, 700],
                "splitters": {"columns": "not-a-splitter-state"},
            }
        }
    )
    win = _makeWindow(tmp_path, manager)
    try:
        assert win.columnSplitter.count() == 2
        assert win.geometry().width() == 900
    finally:
        win.teardown()


def test_a_layout_that_cannot_be_written_does_not_cost_the_window_its_teardown(
    qapp, tmp_path, caplog
):
    """A read-only or missing config directory is a lost preference, nothing
    more. Teardown is what stops the orchestrator and hands the Camera module's
    graphics back, and skipping it is the crash-on-exit this window's
    deterministic teardown exists to prevent -- so the failure is reported and
    stepped over, not propagated."""

    class _UnwritableManager(_FakeManager):
        def writeConfigFile(self, data, fileName):
            raise OSError("read-only config directory")

    win = _makeWindow(tmp_path, _UnwritableManager())
    with caplog.at_level("ERROR", logger="acq4.modules.Autopatch.Autopatch"):
        win.teardown()

    assert win.orchestrator is None
    assert win._referenceImagery is None
    assert "read-only config directory" in caplog.text
