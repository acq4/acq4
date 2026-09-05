"""Tests for the zone half of OptomechDeviceVisualizerAdapter.

The 3D viewer builds one control per zone and one mesh per displayed zone.
Both have to keep up with the zone editor, and a mesh may only be remembered
once it is actually in the scene.
"""
from __future__ import annotations

import numpy as np
import pytest

import pyqtgraph as pg
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


class FakeTransform:
    """Stands in for a coorx transform; every product is the identity."""

    def __mul__(self, other):
        return self

    def as_pyqtgraph(self):
        return pg.Transform3D()

    def map(self, pt):
        return np.zeros(3)


class FakeMesh:
    def __init__(self):
        self.transform = None
        self.visible = True

    def setTransform(self, tr):
        self.transform = tr

    def setVisible(self, vis):
        self.visible = vis


class FakeGeometry:
    transform = FakeTransform()

    def glMesh(self):
        return FakeMesh()


class FakeWindow:
    """Records what the adapter puts into the 3D scene."""

    def __init__(self):
        self.items = []
        self.controls = []
        self.add_error = None

    def add3DItem(self, item):
        if self.add_error is not None:
            raise self.add_error
        self.items.append(item)

    def remove3DItem(self, item):
        if item in self.items:
            self.items.remove(item)

    def addControls(self, param):
        self.controls.append(param)

    def removeControls(self, param):
        if param in self.controls:
            self.controls.remove(param)


class FakeManager:
    def __init__(self):
        self.deviceZones = DeviceZones(manager=self)

    def getDevice(self, name):
        raise KeyError(name)


class FakeDevice(Qt.QObject):
    sigGeometryChanged = Qt.Signal(object)
    sigGlobalTransformChanged = Qt.Signal(object, object)

    def __init__(self, name, manager):
        super().__init__()
        self._name = name
        self.dm = manager
        self._cfg = {}
        self._geometry = FakeGeometry()

    def name(self):
        return self._name

    def getGeometry(self):
        return self._geometry

    def getBoundaries(self):
        return None

    def globalPhysicalTransform(self):
        return FakeTransform()

    def globalTransform(self):
        return FakeTransform()

    def globalPosition(self):
        return np.zeros(3)

    def mapFromGlobal(self, pos):
        return np.asarray(pos, dtype=float)

    def readConfigFile(self, filename):
        return self._cfg.get(filename, {})

    def writeConfigFile(self, data, filename):
        self._cfg[filename] = data


class Rig:
    def __init__(self, adapter, device, win):
        self.adapter = adapter
        self.device = device
        self.win = win
        self.zones = device.dm.deviceZones

    def add_box_zone(self, name):
        zone = self.zones.add_zone(self.device, name, save=False)
        for pt in BOX_HULL_PTS:
            zone.add_point(pt)
        self.zones.save_device_zones(self.device)
        return zone

    def zones_param(self):
        return self.adapter._param.names.get('Zones')

    def zone_param_names(self):
        group = self.zones_param()
        return [] if group is None else [p.name() for p in group.children()]

    def zone_mesh(self, name):
        return self.adapter._zone_meshes.get(name)


@pytest.fixture
def rig(qapp):
    from acq4.devices.OptomechDevice import OptomechDeviceVisualizerAdapter

    device = FakeDevice("dev1", FakeManager())
    win = FakeWindow()
    return Rig(OptomechDeviceVisualizerAdapter(device, win), device, win)


class TestControlsFollowTheZoneList:
    def test_control_appears_for_a_zone_added_later(self, rig):
        assert rig.zone_param_names() == []
        rig.add_box_zone("bath")
        assert rig.zone_param_names() == ["bath"]

    def test_control_disappears_when_the_zone_is_removed(self, rig):
        rig.add_box_zone("bath")
        rig.add_box_zone("well")
        rig.zones.remove_zone(rig.device, "bath", save=True)
        assert rig.zone_param_names() == ["well"]

    def test_control_follows_a_rename(self, rig):
        rig.add_box_zone("bath")
        rig.zones.rename_zone(rig.device, "bath", "chamber", save=True)
        assert rig.zone_param_names() == ["chamber"]

    def test_displayed_mesh_is_dropped_when_its_zone_is_removed(self, rig):
        rig.add_box_zone("bath")
        rig.zones_param().child("bath").setValue(True)
        mesh = rig.zone_mesh("bath")
        assert mesh in rig.win.items

        rig.zones.remove_zone(rig.device, "bath", save=True)
        assert rig.zone_mesh("bath") is None
        assert mesh not in rig.win.items

    def test_displayed_mesh_is_rebuilt_when_the_zone_geometry_changes(self, rig):
        zone = rig.add_box_zone("bath")
        rig.zones_param().child("bath").setValue(True)
        mesh = rig.zone_mesh("bath")
        assert mesh.opts['meshdata'].vertexes().shape[0] == len(BOX_HULL_PTS)

        zone.add_point([5e-3, 0.0, 0.0])
        rig.zones.save_device_zones(rig.device)

        assert rig.zone_mesh("bath") is mesh
        assert mesh.opts['meshdata'].vertexes().shape[0] == len(BOX_HULL_PTS) + 1


class TestVisibilityAggregation:
    def test_zone_toggled_on_under_a_disabled_group_stays_hidden(self, rig):
        rig.add_box_zone("bath")
        rig.zones_param().setValue(False)

        rig.zones_param().child("bath").setValue(True)

        assert rig.zone_mesh("bath").visible() is False

    def test_zone_becomes_visible_once_the_group_is_enabled(self, rig):
        rig.add_box_zone("bath")
        rig.zones_param().child("bath").setValue(True)
        rig.zones_param().setValue(True)
        assert rig.zone_mesh("bath").visible() is True

    def test_zone_hidden_when_the_device_is_switched_off(self, rig):
        rig.add_box_zone("bath")
        rig.zones_param().setValue(True)
        rig.zones_param().child("bath").setValue(True)
        assert rig.zone_mesh("bath").visible() is True

        rig.adapter._param.setValue(False)
        assert rig.zone_mesh("bath").visible() is False


class TestMeshIsOnlyRememberedOnceDisplayed:
    def test_failure_to_add_the_mesh_is_reported_and_not_cached(self, rig):
        rig.add_box_zone("bath")
        rig.win.add_error = RuntimeError("no GL context")

        with pytest.raises(RuntimeError):
            rig.adapter._showZoneMesh("bath")

        assert rig.zone_mesh("bath") is None

    def test_a_zone_can_still_be_displayed_after_a_failed_attempt(self, rig):
        rig.add_box_zone("bath")
        rig.win.add_error = RuntimeError("no GL context")
        with pytest.raises(RuntimeError):
            rig.adapter._showZoneMesh("bath")

        rig.win.add_error = None
        rig.adapter._showZoneMesh("bath")

        assert rig.zone_mesh("bath") in rig.win.items

    def test_clear_drops_the_meshes_and_stops_following_the_zone_service(self, rig):
        rig.add_box_zone("bath")
        rig.zones_param().child("bath").setValue(True)

        rig.adapter.clear()

        assert rig.win.items == []
        assert rig.win.controls == []
        rig.zones.add_zone(rig.device, "well", save=True)  # must not raise

    def test_incomplete_zone_builds_no_mesh(self, rig):
        rig.zones.add_zone(rig.device, "recording", save=True)
        rig.zones_param().setValue(True)
        rig.zones_param().child("recording").setValue(True)
        assert rig.zone_mesh("recording") is None
