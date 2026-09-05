"""Widget-level tests for the Device Zones editor.

Exercise the editing lifecycle a user reaches in a few clicks -- add, rename,
clear, record -- against config files written by the real config writer, so that
a zone the editor saves is a zone the next session can load.
"""
from __future__ import annotations

import os

import numpy as np
import pytest
from pyqtgraph import configfile

from acq4.motion.zones import DeviceZones
from acq4.util import Qt

BOX_HULL_PTS = np.array(
    [
        [-1, -1, -1],
        [1, -1, -1],
        [-1, 1, -1],
        [1, 1, -1],
        [-1, -1, 1],
        [1, -1, 1],
        [-1, 1, 1],
        [1, 1, 1],
    ],
    dtype=float,
) * 1e-3

_UserRole = Qt.Qt.ItemDataRole.UserRole


class FileDevice:
    """Device stub whose zone config goes through the real config file writer."""

    def __init__(self, name, config_dir, global_pos=(0.0, 0.0, 0.0)):
        self._name = name
        self._config_dir = str(config_dir)
        self._global_pos = np.asarray(global_pos, dtype=float)

    def name(self):
        return self._name

    def globalPosition(self):
        return self._global_pos.copy()

    def mapFromGlobal(self, global_pos):
        return np.asarray(global_pos, dtype=float) - self._global_pos

    def _path(self, filename):
        return os.path.join(self._config_dir, f"{self._name}_{filename}")

    def readConfigFile(self, filename):
        path = self._path(filename)
        if not os.path.isfile(path):
            return {}
        return configfile.readConfigFile(path)

    def writeConfigFile(self, data, filename):
        configfile.writeConfigFile(data, self._path(filename))


class FakeInterfaceDir(Qt.QObject):
    sigInterfaceListChanged = Qt.Signal(object)

    def __init__(self, devices):
        super().__init__()
        self._devices = devices

    def listInterfaces(self, types):
        if isinstance(types, str):
            return list(self._devices)
        return {t: list(self._devices) for t in types}

    def getInterface(self, typ, name):
        return self._devices[name]


class FakeManager:
    def __init__(self, devices, zone_service):
        self._devices = {d.name(): d for d in devices}
        self.deviceZones = zone_service
        self.interfaceDir = FakeInterfaceDir(self._devices)

    def listInterfaces(self, types):
        return self.interfaceDir.listInterfaces(types)

    def getInterface(self, typ, name):
        return self.interfaceDir.getInterface(typ, name)

    def getDevice(self, name):
        return self._devices[name]


class FakeModule:
    """Stands in for DeviceZonesModule: the widget only uses these two members."""

    def __init__(self):
        self._3d_adapter = None
        self.quit_calls = 0

    def quit(self, fromUi=False):
        self.quit_calls += 1


class StubMessageBox:
    """Answers every confirmation with Yes and records warnings."""

    StandardButton = Qt.QMessageBox.StandardButton

    def __init__(self):
        self.warnings = []

    def question(self, *args, **kwargs):
        return self.StandardButton.Yes

    def warning(self, *args, **kwargs):
        self.warnings.append(args)


class Editor:
    """Handle on the widget under test plus the pieces a test needs to poke."""

    def __init__(self, widget, device, manager, message_box):
        self.widget = widget
        self.device = device
        self.manager = manager
        self.message_box = message_box

    @property
    def device_item(self):
        return self.widget.zone_tree.topLevelItem(0)

    def zone_names(self):
        item = self.device_item
        return [item.child(i).text(0) for i in range(item.childCount())]

    def zone_item(self, index):
        return self.device_item.child(index)

    def select_zone(self, index):
        self.widget.zone_tree.setCurrentItem(self.zone_item(index))

    def reload(self):
        """Return the zones a fresh session would load from what the editor saved."""
        return DeviceZones().list_zones(self.device)


@pytest.fixture
def editor(qtbot, tmp_path, monkeypatch):
    from acq4.modules.DeviceZones import device_zones

    dev = FileDevice("dev1", tmp_path)
    manager = FakeManager([dev], DeviceZones())
    # InterfaceCombo reaches for the global Manager singleton, which no test has.
    monkeypatch.setattr("acq4.util.InterfaceCombo.getManager", lambda: manager)
    message_box = StubMessageBox()
    monkeypatch.setattr(device_zones.Qt, "QMessageBox", message_box)

    widget = device_zones.DeviceZonesWidget(manager, FakeModule())
    qtbot.addWidget(widget)
    yield Editor(widget, dev, manager, message_box)
    widget._do_cleanup()


class TestAddZone:
    def test_new_zone_is_loadable_by_a_fresh_session(self, editor):
        editor.widget._on_add_zone()
        zones = editor.reload()
        assert [z.name for z in zones] == ["New Zone"]
        assert len(zones[0].hull_points) == 0

    def test_adding_twice_keeps_both_zones(self, editor):
        editor.widget._on_add_zone()
        editor.widget._on_add_zone()
        assert editor.zone_names() == ["New Zone", "New Zone 2"]
        assert len(editor.reload()) == 2


class TestRenameZone:
    def test_rename_updates_the_saved_config(self, editor):
        editor.widget._on_add_zone()
        editor.zone_item(0).setText(0, "Bath")
        assert [z.name for z in editor.reload()] == ["Bath"]

    def test_rename_onto_an_existing_name_is_rejected(self, editor):
        editor.widget._on_add_zone()
        editor.widget._on_add_zone()

        editor.zone_item(1).setText(0, "New Zone")

        assert editor.zone_item(1).text(0) == "New Zone 2"
        assert [z.name for z in editor.reload()] == ["New Zone", "New Zone 2"]
        assert editor.message_box.warnings


class TestPointEditing:
    def test_clearing_points_leaves_a_loadable_config(self, editor):
        editor.widget._on_add_zone()
        editor.select_zone(0)
        for pt in BOX_HULL_PTS:
            editor.widget._current_zone.add_point(pt)

        editor.widget._on_clear_points()

        zones = editor.reload()
        assert len(zones) == 1
        assert len(zones[0].hull_points) == 0

    def test_partially_recorded_zone_is_loadable(self, editor):
        editor.widget._on_add_zone()
        editor.select_zone(0)
        for pt in BOX_HULL_PTS[:3]:
            editor.widget._current_zone.add_point(pt)
        editor.manager.deviceZones.save_device_zones(editor.device)

        zones = editor.reload()
        assert len(zones) == 1
        assert len(zones[0].hull_points) == 3
        assert zones[0].hull is None
