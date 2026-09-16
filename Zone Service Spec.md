# Zone Service — Specification

**Status:** Draft · Rev 0.1 · 2026-08-26

---

## Contents

1. [Overview](#1-overview)
2. [Concepts](#2-concepts)
3. [Data Model](#3-data-model)
4. [Configuration Format](#4-configuration-format)
5. [Zone Membership API](#5-zone-membership-api)
6. [Zone Graph API](#6-zone-graph-api)
7. [User Interface](#7-user-interface)
8. [Class Structure](#8-class-structure)
9. [Error Conditions](#9-error-conditions)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. Overview

The Device Zone Service is an independent component that tracks named regions of space for each device and provides a stable public API for querying zone membership. It has no knowledge of motion planning; any consumer — a motion planner, a UI widget, a state machine, or a script — can ask which zone(s) a device currently occupies.

Zone data is stored in per-device `motion_zones.cfg` files and loaded into memory. The service exposes zone membership queries. It does not command hardware.

**What this spec covers:**
- Zone and path data model
- Configuration file format
- Public zone membership and route API
- UI for recording and managing zones

**What this spec does not cover:**
- How a motion planner uses zones to generate a plan (see Zone-Based Motion Planner Spec)
- Waypoint resolution (partial-axis positions) during plan execution
- Rollback on motion failure

---

## 2. Concepts

| Term | Definition |
|---|---|
| **Zone** | A named convex hull of positions associated with a specific device. A device is *in* a zone when its current global position falls inside the hull. Each device may have any number of zones. |
| **Relative zone** | A zone whose hull is defined in another device's local coordinate frame. The zone moves when the anchor device moves. Membership is tested by first transforming the device's global position into the anchor's local frame. |
| **Anchor device** | The device that a relative zone is defined relative to. |

---

## 3. Data Model

### Zone

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Unique within the device's zone set. |
| `hull_points` | `np.ndarray (N×3)` | Raw recorded points used to build the convex hull. At least 4 non-coplanar points required. |
| `hull` | `ConvexHull` | Computed from `hull_points` via `scipy.spatial.ConvexHull`. Rebuilt on load; not stored in config. |
| `relative_to` | `Device \| None` | If set, `hull_points` are in this device's local frame and membership tests transform to that frame first. |

---

## 4. Configuration Format

Zone and path data for a device are stored in `motion_zones.cfg` in the device's state directory (same location as `transform.cfg` and other per-device calibration files). The file uses ACQ4's standard indented key-value `.cfg` format.

### Example — Pipette device

```
# Pipette1/motion_zones.cfg

zones:
    Bath:
        hull_points:
            0: [-0.0080, -0.0050, 0.0010]
            1: [ 0.0020, -0.0050, 0.0010]
            2: [-0.0080,  0.0040, 0.0010]
            3: [ 0.0020,  0.0040, 0.0010]
            4: [-0.0080, -0.0050, 0.0060]

    RecordingChamber:
        hull_points:
            0: [-0.0015, -0.0015, -0.0020]
            1: [ 0.0015, -0.0015, -0.0020]
            2: [-0.0015,  0.0015, -0.0020]
            3: [ 0.0015,  0.0015, -0.0020]
            4: [ 0.0000,  0.0000,  0.0010]

    InsideCleaningWell:
        relativeTo: CleaningWell           # hull points in CleaningWell's local frame
        hull_points:
            0: [-0.0004, -0.0004, -0.0005]
            1: [ 0.0004, -0.0004, -0.0005]
            2: [-0.0004,  0.0004, -0.0005]
            3: [ 0.0004,  0.0004, -0.0005]
            4: [ 0.0000,  0.0000,  0.0010]

```

### Zone ordering

Zones are evaluated in config order; when a position falls inside more than one zone, the first match wins. For overlapping zones — such as a small specific zone nested inside a larger one — list the more specific zone first. The UI provides a drag-to-reorder list; the user does not need to edit the config file directly.

### Coordinate conventions

Hull points are recorded relative to a reference coordinate system, which can be either global (defualt), or any other selected device. For example, a pipette may record coordinates relative to a cleaning well such that if the well moves, the zone moves with it.

---

## 5. DeviceZones API

Zone membership queries are independent of motion planning and may be called by any consumer at any time.

### `find_zones(device, position_global=None) → list[Zone]`

Returns all zones containing `position_global`, in config order (first match = highest priority). Defaults to the device's current global position.

```python
def find_zones(device: Device, position_global: np.ndarray | None = None) -> list[Zone]:
    if position_global is None:
        position_global = device.globalPosition()

    zones = self._db.zones.get(device.name(), [])
    matches = []
    for zone in zones:
        if zone.relative_to is None:
            test_point = position_global
        else:
            test_point = zone.relative_to.mapFromGlobal(position_global)
        if _point_in_hull(zone.hull, test_point, tol=POSITION_TOLERANCE):
            matches.append(zone)
    return matches
```

### `list_zones(device) -> list[Zone]`

List all zones configured for a device.

### `Zone.hull_points() -> coorx.PointArray`


### Hull containment test

A point *p* is inside a `scipy.spatial.ConvexHull` if and only if it satisfies all face half-spaces within tolerance:

```python
def _point_in_hull(hull: ConvexHull, point: np.ndarray, tol: float) -> bool:
    return bool(np.all(hull.equations @ np.append(point, 1) <= tol))
```

**Tolerance:** `POSITION_TOLERANCE = 1e-4` m (0.1 mm). Handles floating-point drift and small positioning errors at zone boundaries. Configurable via `ZoneService` constructor argument.

---

## 7. User Interface

The Zone Service UI is an acq4 UI module (acq4/modules/DeviceZones)

### 7.1 Zone panel layout

The panel shows a QTreeWidget listing all OptoMechDevice instances as top-level items, and zones defined per-device as children. Zones are shown in priority order and can be dragged to reorder. A zone cannot be dragged from one device to another.

To the right side of the tree widget is:
- A "Relative to: " check box and a dropdown menu of optomech devices (InterfaceCombo). The dropdown is enabled only if the box is checked.
- A QTreeidget that lists all hull points for the selected zone, with x/y/z columns. Any number of items may be selected, and pressing 'delete' will remove points. User may also manually edit coodrinate values from here.

The panel also has buttons to add/remove zones record/clear the selected zone, and record one point, positioned in a 3x2 grid below the tree.

Existing zones can be renamed via the tree, and newly created zones begin a tree item that is in edit mode already.
The Record button is checkable, and recording immediately begins adding points to its list of hull points (see below).
The Record Point button adds a single point to the zone.
Clearing a zone removes all hull points after presenting a confirmation dialog.
Changing the relative-to device for a zone requires clearing its recorded points, and thus also requires confirmation (if the user cancels, make sure to reset the relative-to check/combo state)

ALL updates to zones / hull points are immediately saved to config file, except during continuous recording.

### 7.2 Recording points

When recording, the global position of the device is acquired and optionally mapped into the local space of the relative-to device. 
For continuous recording, 3 points per second are added except when the device is not moving.

### 7.3 3D Visualization

While the Device Zones module is running, it connects to the 3d visualization module and adds:
- A scatter plot of hull points in the selected zone (updates in realtime during recording). Points that are selected in the table of hull points are colored differently.
- A transparent mesh of the selected hull (Zone class should have a method for retrieving shared mesh data for visualization). Hull is _not_ updated during continuous recording; only after recording completes or after a single-point add.

### 7.4 viewing zones outside the module

The 3D viewer module is updated such that for each device displayed, a list of zones allows to select and visualize the hull of the zone as a transparent mesh (also retrieved from Zone class). 
Meshes are hidden by default and loaded lazily. 
This is available independently of the Device Zones module.


## 8. DeviceZones class

**Manager integration:** `Manager.deviceZones` follows the same lazy-singleton pattern as `Manager.motionPlanner`. It is instantiated on first access and accessible to any code that holds a reference to the Manager.

---

## 9. Error Conditions

`ZoneConfigError` is raised at `ZoneDatabase.load()` time. `ZoneRoutingError` is raised by graph queries.

| Condition | Exception | Message pattern |
|---|---|---|
| Fewer than 4 hull points | `ZoneConfigError` | *Zone '{zone}' for {device} has {N} hull points; at least 4 non-coplanar points required.* |
| `relativeTo` names an unknown device | `ZoneConfigError` | *Zone '{zone}' for {device}: relativeTo device '{name}' not found.* |

---

## 10. Testing Strategy

Tests live in `acq4/motion/tests/test_zone_service.py`, using mock device objects (no real hardware or file I/O). A `MockZoneDatabase` builder utility constructs in-memory zone configs from Python dicts.

### Zone membership

- Point clearly inside hull → correct zone returned.
- Point clearly outside all hulls → `None` returned.
- Point within `POSITION_TOLERANCE` of hull surface → inside (tolerance accepted).
- Point just beyond `POSITION_TOLERANCE` → outside.
- Relative zone: anchor at recorded position → membership correct. Anchor moved → membership follows anchor.
- Overlapping zones: both zones returned in config order if test point is inside both

