"""Widget-level tests for the Device Zones editor.

Exercise the editing lifecycle a user reaches in a few clicks -- add, rename,
clear, record -- against config files written by the real config writer, so that
a zone the editor saves is a zone the next session can load.
"""
from __future__ import annotations

import logging
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
    """Device stub whose zone config goes through the real config file writer.

    Reports no position, like the cameras, filter wheels and objectives that
    share the OptomechDevice interface with the stages.
    """

    def __init__(self, name, config_dir):
        self._name = name
        self._config_dir = str(config_dir)

    def name(self):
        return self._name

    def _path(self, filename):
        return os.path.join(self._config_dir, f"{self._name}_{filename}")

    def readConfigFile(self, filename):
        path = self._path(filename)
        if not os.path.isfile(path):
            return {}
        return configfile.readConfigFile(path)

    def writeConfigFile(self, data, filename):
        configfile.writeConfigFile(data, self._path(filename))


class PositionedDevice(FileDevice):
    """A device that can say where it is, as Stage, Pipette and Microscope do."""

    def __init__(self, name, config_dir, global_pos=(0.0, 0.0, 0.0)):
        super().__init__(name, config_dir)
        self._global_pos = np.asarray(global_pos, dtype=float)

    def globalPosition(self):
        return self._global_pos.copy()

    def mapFromGlobal(self, global_pos):
        return np.asarray(global_pos, dtype=float) - self._global_pos


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
        return self.device_item_for(self.device.name())

    def device_item_for(self, dev_name):
        tree = self.widget.zone_tree
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.text(0) == dev_name:
                return item
        raise AssertionError(f"no device item named {dev_name!r}")

    def add_zone_to(self, dev_name, zone_name):
        """Add a zone to a named device and return its tree item."""
        self.widget.zone_tree.setCurrentItem(self.device_item_for(dev_name))
        self.widget._on_add_zone()
        item = self.device_item_for(dev_name).child(0)
        item.setText(0, zone_name)
        return item

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


def _open_editor(qtbot, monkeypatch, devices):
    from acq4.modules.DeviceZones import device_zones

    manager = FakeManager(devices, DeviceZones())
    # InterfaceCombo reaches for the global Manager singleton, which no test has.
    monkeypatch.setattr("acq4.util.InterfaceCombo.getManager", lambda: manager)
    message_box = StubMessageBox()
    monkeypatch.setattr(device_zones.Qt, "QMessageBox", message_box)

    widget = device_zones.DeviceZonesWidget(manager, FakeModule())
    qtbot.addWidget(widget)
    return Editor(widget, devices[0], manager, message_box)


@pytest.fixture
def editor(qtbot, tmp_path, monkeypatch):
    ed = _open_editor(qtbot, monkeypatch, [PositionedDevice("dev1", tmp_path)])
    yield ed
    ed.widget._do_cleanup()


@pytest.fixture
def mixed_editor(qtbot, tmp_path, monkeypatch):
    """An editor over one device that reports a position and one that cannot."""
    devices = [PositionedDevice("stage1", tmp_path), FileDevice("camera1", tmp_path)]
    ed = _open_editor(qtbot, monkeypatch, devices)
    yield ed
    ed.widget._do_cleanup()


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


class TestRecordingNeedsAPosition:
    """Every OptomechDevice is listed, but only some can say where they are."""

    def test_record_controls_are_enabled_for_a_device_that_reports_position(
        self, mixed_editor
    ):
        mixed_editor.add_zone_to("stage1", "Bath")

        assert mixed_editor.widget.btn_record.isEnabled()
        assert mixed_editor.widget.btn_record_point.isEnabled()

    def test_record_controls_are_disabled_for_a_device_with_no_position(
        self, mixed_editor
    ):
        mixed_editor.add_zone_to("camera1", "Field")

        assert not mixed_editor.widget.btn_record.isEnabled()
        assert not mixed_editor.widget.btn_record_point.isEnabled()

    def test_selecting_a_positionless_device_stops_a_running_recording(
        self, mixed_editor
    ):
        widget = mixed_editor.widget
        mixed_editor.add_zone_to("stage1", "Bath")
        widget.btn_record.setChecked(True)
        assert widget._record_timer.isActive()

        mixed_editor.add_zone_to("camera1", "Field")

        assert not widget._recording
        assert not widget.btn_record.isChecked()
        assert not widget._record_timer.isActive()

    def test_recording_a_point_from_a_positionless_device_records_nothing(
        self, mixed_editor
    ):
        mixed_editor.add_zone_to("camera1", "Field")

        mixed_editor.widget._on_record_point()

        assert len(mixed_editor.widget._current_zone.hull_points) == 0


class TestInZoneColumn:
    """The column polls once a second, so it must not ask for what it cannot get."""

    def test_a_device_that_cannot_be_located_is_not_polled(
        self, mixed_editor, monkeypatch, caplog
    ):
        mixed_editor.add_zone_to("camera1", "Field")
        service = mixed_editor.manager.deviceZones
        asked = []
        monkeypatch.setattr(
            service, "find_zones", lambda dev, *args, **kwds: asked.append(dev) or []
        )
        caplog.clear()

        with caplog.at_level(logging.WARNING):
            mixed_editor.widget._update_in_zone_column()

        assert asked == []
        assert caplog.records == []

    def test_a_device_that_cannot_be_located_reports_membership_unknown(
        self, mixed_editor
    ):
        item = mixed_editor.add_zone_to("camera1", "Field")

        mixed_editor.widget._update_in_zone_column()

        assert item.text(1) == "?"

    def test_a_device_that_reports_position_is_still_polled(
        self, mixed_editor, monkeypatch
    ):
        mixed_editor.add_zone_to("stage1", "Bath")
        service = mixed_editor.manager.deviceZones
        asked = []
        monkeypatch.setattr(
            service, "find_zones", lambda dev, *args, **kwds: asked.append(dev) or []
        )

        mixed_editor.widget._update_in_zone_column()

        assert [d.name() for d in asked] == ["stage1"]
