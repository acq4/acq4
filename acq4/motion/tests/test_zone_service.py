"""Tests for the Zone Service (acq4.motion.zones).

Covers Zone membership, point mutation, serialisation roundtrip,
and DeviceZones management operations.
"""
from __future__ import annotations

import numpy as np
import pytest

import coorx

from acq4.motion.zones import (
    POSITION_TOLERANCE,
    DeviceZones,
    Zone,
    ZoneConfigError,
    _point_in_hull,
)

# ---------------------------------------------------------------------------
# Reference geometry — axis-aligned 2 mm cube centred at the origin
# ---------------------------------------------------------------------------

BOX_HULL_PTS = np.array(
    [
        [-1, -1, -1],
        [ 1, -1, -1],
        [-1,  1, -1],
        [ 1,  1, -1],
        [-1, -1,  1],
        [ 1, -1,  1],
        [-1,  1,  1],
        [ 1,  1,  1],
    ],
    dtype=float,
) * 1e-3  # vertices at ±1 mm in each axis

CENTER = np.zeros(3)                     # clearly inside the box
FAR_POINT = np.array([10e-3, 0.0, 0.0]) # clearly outside the box


# ---------------------------------------------------------------------------
# Local mock objects (self-contained — do not import from conftest)
# ---------------------------------------------------------------------------

class ZoneMockDevice:
    """Minimal device mock: fixed global position, in-memory config files."""

    def __init__(self, name: str, global_pos=(0.0, 0.0, 0.0)):
        self._name = name
        self._global_pos = np.asarray(global_pos, dtype=float)
        self._cfg: dict = {}

    def name(self) -> str:
        return self._name

    def globalPosition(self) -> np.ndarray:
        return self._global_pos.copy()

    def mapFromGlobal(self, global_pos) -> np.ndarray:
        return np.asarray(global_pos, dtype=float) - self._global_pos

    def readConfigFile(self, filename: str) -> dict:
        return self._cfg.get(filename, {})

    def writeConfigFile(self, data: dict, filename: str) -> None:
        self._cfg[filename] = data


class MockManager:
    """Minimal manager mock: resolves devices by name for relativeTo loading."""

    def __init__(self, devices=None):
        self._devices = {d.name(): d for d in (devices or [])}

    def getDevice(self, name: str):
        if name not in self._devices:
            raise KeyError(name)
        return self._devices[name]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dev():
    return ZoneMockDevice("dev1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_box_zone(name: str = "zone_a") -> Zone:
    """Return a Zone pre-loaded with the standard 2 mm box hull."""
    return Zone(name, BOX_HULL_PTS.copy())


def _dz_with_box(dev: ZoneMockDevice, name: str = "zone_a") -> DeviceZones:
    """Return a DeviceZones with one complete box zone for *dev* (no file I/O)."""
    dz = DeviceZones()
    zone = dz.add_zone(dev, name, save=False)
    for pt in BOX_HULL_PTS:
        zone.add_point(pt)
    return dz


# ===========================================================================
# 1. Zone membership — find_zones
# ===========================================================================

def test_find_zones_inside_hull(dev):
    dz = _dz_with_box(dev)
    zones = dz.find_zones(dev, CENTER)
    assert len(zones) == 1
    assert zones[0].name == "zone_a"


def test_find_zones_outside_all_hulls(dev):
    dz = _dz_with_box(dev)
    zones = dz.find_zones(dev, FAR_POINT)
    assert zones == []


def test_find_zones_within_position_tolerance(dev):
    """A point tol*0.5 outside the hull surface is accepted (tolerance in)."""
    dz = _dz_with_box(dev)
    tol = POSITION_TOLERANCE
    # +x face is at x = 1e-3; outward normal is [1,0,0] (unit length for axis-aligned box)
    pt = np.array([1e-3 + tol * 0.5, 0.0, 0.0])
    zones = dz.find_zones(dev, pt)
    assert len(zones) == 1


def test_find_zones_just_beyond_position_tolerance(dev):
    """A point tol*1.5 outside the hull surface is rejected."""
    dz = _dz_with_box(dev)
    tol = POSITION_TOLERANCE
    pt = np.array([1e-3 + tol * 1.5, 0.0, 0.0])
    zones = dz.find_zones(dev, pt)
    assert zones == []


def test_find_zones_relative_zone_anchor_at_origin():
    """Relative zone: anchor at origin — membership in global == membership in local."""
    anchor = ZoneMockDevice("anchor", global_pos=(0.0, 0.0, 0.0))
    dev = ZoneMockDevice("dev1")
    dz = DeviceZones()
    zone = dz.add_zone(dev, "rel_zone", relative_to=anchor, save=False)
    for pt in BOX_HULL_PTS:
        zone.add_point(pt)
    # Anchor is at origin, so global CENTER maps to local [0,0,0] — inside the box.
    assert len(dz.find_zones(dev, CENTER)) == 1


def test_find_zones_relative_zone_anchor_moved():
    """Relative zone moves with its anchor device."""
    anchor = ZoneMockDevice("anchor", global_pos=(0.0, 0.0, 0.0))
    dev = ZoneMockDevice("dev1")
    dz = DeviceZones()
    zone = dz.add_zone(dev, "rel_zone", relative_to=anchor, save=False)
    for pt in BOX_HULL_PTS:
        zone.add_point(pt)

    # With anchor at origin, global CENTER is inside the zone.
    assert len(dz.find_zones(dev, CENTER)) == 1

    # Move anchor to (5 mm, 0, 0).
    # Global CENTER now maps to local [-5e-3, 0, 0], which is outside the ±1 mm box.
    anchor._global_pos = np.array([5e-3, 0.0, 0.0])
    assert dz.find_zones(dev, CENTER) == []

    # A global point that sits at the new anchor origin maps to local [0,0,0] → inside.
    at_anchor = np.array([5e-3, 0.0, 0.0])
    assert len(dz.find_zones(dev, at_anchor)) == 1


def test_find_zones_overlapping_returns_both_in_config_order(dev):
    """When a point is inside multiple zones, all are returned in config order."""
    dz = DeviceZones()
    zone_a = dz.add_zone(dev, "zone_a", save=False)
    zone_b = dz.add_zone(dev, "zone_b", save=False)
    for pt in BOX_HULL_PTS:
        zone_a.add_point(pt)
        zone_b.add_point(pt)

    zones = dz.find_zones(dev, CENTER)
    assert len(zones) == 2
    assert [z.name for z in zones] == ["zone_a", "zone_b"]


# ===========================================================================
# 8. list_zones
# ===========================================================================

def test_list_zones_returns_all_in_config_order(dev):
    dz = DeviceZones()
    for n in ("first", "second", "third"):
        dz.add_zone(dev, n, save=False)
    assert [z.name for z in dz.list_zones(dev)] == ["first", "second", "third"]


def test_list_zones_empty_when_no_zones_configured(dev):
    dz = DeviceZones()
    assert dz.list_zones(dev) == []


# ===========================================================================
# 9. validate
# ===========================================================================

def test_validate_raises_zone_config_error_for_fewer_than_4_points():
    zone = Zone(
        "bad",
        np.array([[0, 0, 0], [1e-3, 0, 0], [0, 1e-3, 0]], dtype=float),
    )
    with pytest.raises(ZoneConfigError, match="at least 4"):
        zone.validate("test_device")


def test_validate_raises_for_zero_points():
    zone = Zone("empty", np.empty((0, 3), dtype=float))
    with pytest.raises(ZoneConfigError):
        zone.validate("test_device")


def test_validate_passes_for_valid_hull():
    zone = _make_box_zone()
    zone.validate("test_device")  # must not raise


# ===========================================================================
# 10. Zone.mesh()
# ===========================================================================

def test_mesh_returns_none_when_hull_not_built():
    zone = Zone("z", np.empty((0, 3), dtype=float))
    assert zone.mesh() is None


def test_mesh_returns_none_for_3_coplanar_points():
    zone = Zone(
        "z",
        np.array([[0, 0, 0], [1e-3, 0, 0], [0, 1e-3, 0]], dtype=float),
    )
    assert zone.mesh() is None


def test_mesh_returns_vertices_and_faces_when_hull_built():
    zone = _make_box_zone()
    result = zone.mesh()
    assert result is not None
    verts, faces = result
    assert isinstance(verts, np.ndarray)
    assert verts.ndim == 2 and verts.shape[1] == 3
    assert isinstance(faces, np.ndarray)
    assert faces.ndim == 2 and faces.shape[1] == 3


def test_mesh_returns_copies_not_hull_internals():
    """mesh() copies must be independent of internal hull arrays."""
    zone = _make_box_zone()
    verts1, faces1 = zone.mesh()
    verts1[:] = 0  # mutate the copy
    verts2, _ = zone.mesh()
    assert not np.all(verts2 == 0)


# ===========================================================================
# 11. Zone.hull_points property
# ===========================================================================

def test_hull_points_returns_coorx_point_array():
    zone = _make_box_zone()
    hp = zone.hull_points
    assert isinstance(hp, coorx.PointArray)


def test_hull_points_values_match_construction_input():
    zone = _make_box_zone()
    np.testing.assert_array_equal(np.asarray(zone.hull_points), BOX_HULL_PTS)



# ===========================================================================
# 12. Zone.add_point
# ===========================================================================

def test_add_point_appends_incrementally():
    zone = Zone("z", np.empty((0, 3), dtype=float))
    zone.add_point([1e-3, 0.0, 0.0])
    assert len(zone.hull_points) == 1
    zone.add_point([0.0, 1e-3, 0.0])
    assert len(zone.hull_points) == 2


def test_add_point_hull_none_before_4_points():
    zone = Zone("z", np.empty((0, 3), dtype=float))
    for pt in BOX_HULL_PTS[:3]:
        zone.add_point(pt)
    assert zone.hull is None


def test_add_point_hull_built_at_4_noncoplanar_points():
    zone = Zone("z", np.empty((0, 3), dtype=float))
    # BOX_HULL_PTS[:4] are all coplanar (z = -1e-3); use indices that span all 3 axes.
    noncoplanar = [BOX_HULL_PTS[0], BOX_HULL_PTS[1], BOX_HULL_PTS[2], BOX_HULL_PTS[4]]
    for pt in noncoplanar:
        zone.add_point(pt)
    assert zone.hull is not None


def test_add_point_hull_rebuilt_after_every_additional_point():
    zone = _make_box_zone()
    old_hull = zone.hull
    extra = np.array([0.5e-3, 0.5e-3, 0.5e-3])
    zone.add_point(extra)
    # Hull must be valid and contain the new point count
    assert zone.hull is not None
    assert len(zone.hull_points) == len(BOX_HULL_PTS) + 1


# ===========================================================================
# 13. Zone.remove_points
# ===========================================================================

def test_remove_points_by_index():
    zone = Zone(
        "z",
        np.array([[1, 0, 0], [2, 0, 0], [3, 0, 0]], dtype=float) * 1e-3,
    )
    zone.remove_points([1])  # remove middle point
    pts = np.asarray(zone.hull_points)
    assert len(pts) == 2
    np.testing.assert_array_equal(pts[0], [1e-3, 0, 0])
    np.testing.assert_array_equal(pts[1], [3e-3, 0, 0])


def test_remove_points_clears_hull_when_fewer_than_4_remain():
    zone = _make_box_zone()
    assert zone.hull is not None
    # Remove 5 of the 8 points, leaving 3
    zone.remove_points(list(range(3, 8)))
    assert len(zone.hull_points) == 3
    assert zone.hull is None


def test_remove_points_hull_rebuilt_when_4_or_more_remain():
    zone = _make_box_zone()
    # Remove indices [3,5,6,7], leaving [0,1,2,4]:
    #   [-1,-1,-1], [1,-1,-1], [-1,1,-1], [-1,-1,1]  — a proper tetrahedron, non-coplanar.
    zone.remove_points([3, 5, 6, 7])
    assert len(zone.hull_points) == 4
    assert zone.hull is not None


# ===========================================================================
# 14. to_config / load roundtrip
# ===========================================================================

def test_to_config_load_roundtrip_single_zone(dev):
    dz = _dz_with_box(dev, "zone_a")
    dz.save_device_zones(dev)

    dz2 = DeviceZones()
    dz2.load_device_zones(dev)
    zones = dz2.list_zones(dev)

    assert len(zones) == 1
    assert zones[0].name == "zone_a"
    np.testing.assert_allclose(np.asarray(zones[0].hull_points), BOX_HULL_PTS)


def test_to_config_load_roundtrip_multiple_zones(dev):
    dz = DeviceZones()
    zone_a = dz.add_zone(dev, "zone_a", save=False)
    zone_b = dz.add_zone(dev, "zone_b", save=False)
    for pt in BOX_HULL_PTS:
        zone_a.add_point(pt)
        zone_b.add_point(pt * 0.5)  # smaller box, same shape
    dz.save_device_zones(dev)

    dz2 = DeviceZones()
    dz2.load_device_zones(dev)
    zones = dz2.list_zones(dev)

    assert [z.name for z in zones] == ["zone_a", "zone_b"]
    assert zones[0].hull is not None
    assert zones[1].hull is not None


def test_to_config_roundtrip_via_invalidate(dev):
    """invalidate_device followed by list_zones triggers a fresh load from config."""
    dz = _dz_with_box(dev, "zone_a")
    dz.save_device_zones(dev)

    dz.invalidate_device(dev)
    zones = dz.list_zones(dev)
    assert len(zones) == 1
    assert zones[0].name == "zone_a"


# ===========================================================================
# 15. relativeTo config roundtrip
# ===========================================================================

def test_relative_to_saved_in_config(dev):
    """to_config must emit 'relativeTo' when a relative_to device is set."""
    anchor = ZoneMockDevice("anchor")
    manager = MockManager([anchor])
    dz = DeviceZones(manager=manager)
    zone = dz.add_zone(dev, "rel_zone", relative_to=anchor, save=False)
    for pt in BOX_HULL_PTS:
        zone.add_point(pt)
    dz.save_device_zones(dev)

    raw_cfg = dev.readConfigFile("motion_zones.cfg")
    assert raw_cfg["zones"]["rel_zone"]["relativeTo"] == "anchor"


def test_relative_to_roundtrip_resolves_device(dev):
    """After reload the zone's relative_to attribute points to the anchor device."""
    anchor = ZoneMockDevice("anchor")
    manager = MockManager([anchor])
    dz = DeviceZones(manager=manager)
    zone = dz.add_zone(dev, "rel_zone", relative_to=anchor, save=False)
    for pt in BOX_HULL_PTS:
        zone.add_point(pt)
    dz.save_device_zones(dev)

    dz2 = DeviceZones(manager=manager)
    dz2.load_device_zones(dev)
    zones = dz2.list_zones(dev)
    assert len(zones) == 1
    assert zones[0].relative_to is anchor


def test_zone_without_relative_to_has_none_after_roundtrip(dev):
    dz = _dz_with_box(dev)
    dz.save_device_zones(dev)

    dz2 = DeviceZones()
    dz2.load_device_zones(dev)
    zones = dz2.list_zones(dev)
    assert zones[0].relative_to is None


# ===========================================================================
# 16. ZoneConfigError on load
# ===========================================================================

def test_load_raises_zone_config_error_for_too_few_hull_points(dev):
    bad_cfg = {
        "zones": {
            "bad_zone": {
                "hull_points": [
                    [0.0, 0.0, 0.0],
                    [1e-3, 0.0, 0.0],
                ]
            }
        }
    }
    dev.writeConfigFile(bad_cfg, "motion_zones.cfg")
    dz = DeviceZones()
    with pytest.raises(ZoneConfigError):
        dz.load_device_zones(dev)


def test_load_raises_zone_config_error_for_3_hull_points(dev):
    bad_cfg = {
        "zones": {
            "coplanar": {
                "hull_points": [
                    [0.0, 0.0, 0.0],
                    [1e-3, 0.0, 0.0],
                    [0.0, 1e-3, 0.0],
                ]
            }
        }
    }
    dev.writeConfigFile(bad_cfg, "motion_zones.cfg")
    dz = DeviceZones()
    with pytest.raises(ZoneConfigError):
        dz.load_device_zones(dev)


def test_zone_config_error_propagates_through_list_zones(dev):
    """ZoneConfigError from load_device_zones propagates through list_zones."""
    bad_cfg = {
        "zones": {
            "bad_zone": {
                "hull_points": [[0.0, 0.0, 0.0], [1e-3, 0.0, 0.0]]
            }
        }
    }
    dev.writeConfigFile(bad_cfg, "motion_zones.cfg")
    dz = DeviceZones()
    with pytest.raises(ZoneConfigError):
        dz.list_zones(dev)


def test_zone_config_error_propagates_through_find_zones(dev):
    """ZoneConfigError from load_device_zones propagates through find_zones."""
    bad_cfg = {
        "zones": {
            "bad_zone": {
                "hull_points": [[0.0, 0.0, 0.0], [1e-3, 0.0, 0.0]]
            }
        }
    }
    dev.writeConfigFile(bad_cfg, "motion_zones.cfg")
    dz = DeviceZones()
    with pytest.raises(ZoneConfigError):
        dz.find_zones(dev, CENTER)


# ===========================================================================
# 17. reorder_zones
# ===========================================================================

def test_reorder_zones_changes_list_order(dev):
    dz = DeviceZones()
    for n in ("first", "second", "third"):
        dz.add_zone(dev, n, save=False)

    dz.reorder_zones(dev, ["third", "first", "second"], save=False)
    assert [z.name for z in dz.list_zones(dev)] == ["third", "first", "second"]


def test_reorder_zones_omitted_names_are_dropped(dev):
    dz = DeviceZones()
    for n in ("a", "b", "c"):
        dz.add_zone(dev, n, save=False)

    dz.reorder_zones(dev, ["c", "a"], save=False)
    assert [z.name for z in dz.list_zones(dev)] == ["c", "a"]


# ===========================================================================
# 18. remove_zone
# ===========================================================================

def test_remove_zone_zone_no_longer_in_list(dev):
    dz = DeviceZones()
    dz.add_zone(dev, "keep", save=False)
    dz.add_zone(dev, "delete_me", save=False)

    dz.remove_zone(dev, "delete_me", save=False)
    names = [z.name for z in dz.list_zones(dev)]
    assert "delete_me" not in names
    assert "keep" in names


def test_remove_zone_other_zones_unaffected(dev):
    dz = DeviceZones()
    for n in ("a", "b", "c"):
        dz.add_zone(dev, n, save=False)

    dz.remove_zone(dev, "b", save=False)
    names = [z.name for z in dz.list_zones(dev)]
    assert names == ["a", "c"]


def test_remove_zone_all_zones(dev):
    dz = DeviceZones()
    dz.add_zone(dev, "only", save=False)
    dz.remove_zone(dev, "only", save=False)
    assert dz.list_zones(dev) == []
