# Zone-Based Motion Planner — Implementation Specification

**Status:** Draft · Rev 0.10 · 2026-08-13

---

## Contents

1. [Overview](#1-overview)
2. [Concepts](#2-concepts)
3. [Data Model](#3-data-model)
4. [Configuration Format](#4-configuration-format)
5. [Zone Membership](#5-zone-membership)
6. [Zone Graph](#6-zone-graph)
7. [Planning Algorithm](#7-planning-algorithm)
8. [Waypoint Resolution](#8-waypoint-resolution)
9. [Multi-Spec Composition](#9-multi-spec-composition)
10. [Device Collection](#10-device-collection)
11. [InteractionSite Additions](#11-interactionsite-additions)
12. [Rollback](#12-rollback)
13. [Logging](#13-logging)
14. [Class Structure](#14-class-structure)
15. [Error Conditions](#15-error-conditions)
16. [Testing Strategy](#16-testing-strategy)

---

## 1. Overview

`ZoneBasedMotionPlanner` is a new `MotionPlanner` subclass that adds zone-aware routing on top of an existing inner planner. Each device has its own list of named zones; cross-zone moves must follow configured waypoint paths; and before entering a relative zone, the anchor device must be at the position it occupied when that zone was recorded (`Zone.anchor_position`, captured automatically at definition time).

The zone planner composes with, rather than replaces, planners like `DefaultMotionPlanner`. Each zone may individually name a delegate planner class (configured in `motion_zones.cfg`); same-zone moves within that zone are forwarded to an instance of that planner. `ZoneBasedMotionPlanner` instantiates delegate planners on first use and caches them by class path. This allows, for example, a `RecordingChamber` zone to apply tissue-crossing logic (from `DefaultMotionPlanner`) for movements within the chamber, while the zone planner handles all routing between zones.

The planner implements the existing plugin contract: `plan()` is a pure function that reads device positions and returns a plan tree without commanding hardware. All device reservation, execution threading, and final-position validation remain in the base-class `execute()` template. Rollback on failure is added as an execution-layer extension in this class.

**Design goals:**
- Every device start and end position must be in a named zone; any other position is an error.
- Devices may never move from one zone to another without following a configured path.
- Devices may move freely (directly) between two positions in the *same* zone, unless that zone delegates to another planner.
- A zone may specify a delegate planner class; same-zone moves within that zone are forwarded to an instance of that planner.
- Zones may be defined relative to a movable device; when the anchor moves, the zone moves with it.
- Relative zones record the anchor device's global position at definition time (`anchor_position`); the planner ensures the anchor is at that position before routing a device into the zone.
- On inter-zone failure the executor reverses all completed moves until the device is returned to its previous zone.
- All planning decisions are logged with sufficient detail to reconstruct the planner's reasoning.

**Plugin registration:**
```yaml
motionPlanner:
    class: acq4.motion.ZoneBasedMotionPlanner
```
Hot-swappable at runtime via `Manager.motionPlanner`.

---

## 2. Concepts

| Term | Definition |
|---|---|
| **Zone** | A named convex hull of positions associated with a specific device. A device is *in* a zone when its current global position, optionally transformed into the zone's reference frame, falls inside the hull. Each device may have any number of zones. |
| **Relative zone** | A zone whose hull is defined in another device's local coordinate frame (e.g. a pipette zone inside a cleaning well). The zone moves when the anchor device moves. Membership is tested in the anchor's local frame. |
| **Path** | An ordered sequence of waypoints connecting two zones for a given device. By default a single path entry applies in both directions; if both directions are configured explicitly, each is used independently. |
| **Waypoint** | A partial position update: a dict of axis names (`'x'`, `'y'`, `'z'`, `'d'`, …) to absolute values. Axes not listed stay at their value from the previous step. Waypoints must always be named for logging. |
| **Zone graph** | The directed graph of zones (nodes) and paths (edges) for a single device. Used to find minimum-hop routes across multiple zone transitions. |
| **Anchor position** | The global position the anchor device occupied when a relative zone was recorded. Stored as `anchor_position` on the `Zone`, in the moving device's `motion_zones.cfg`. Captured automatically during zone recording — not set separately by the user. |

---

## 3. Data Model

### Zone

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Unique within the device's zone set. |
| `hull_points` | `np.ndarray (N×3)` | Raw recorded points used to build the convex hull. At least 4 non-coplanar points required. |
| `hull` | `ConvexHull` | Computed from `hull_points` via `scipy.spatial.ConvexHull`. Rebuilt on load; not stored directly. |
| `relative_to` | `Device \| None` | If set, `hull_points` are in this device's local frame and the membership test transforms to that frame first. |
| `anchor_position` | `np.ndarray \| None` | Global position of the anchor device at the moment this zone was recorded. Present only when `relative_to` is not `None`; `None` for non-relative zones. Never edited by the user. |
| `delegate_class` | `str \| None` | Dotted class path of the planner to delegate same-zone moves to (e.g. `acq4.motion.DefaultMotionPlanner`). `None` means no delegation. |

### Path

| Field | Type | Description |
|---|---|---|
| `zone_a` | `str` | First zone name (ordering determines canonical direction). |
| `zone_b` | `str` | Second zone name. |
| `waypoints` | `list[Waypoint]` | Ordered waypoints for the A→B direction. |
| `direction` | `'both' \| 'a_to_b' \| 'b_to_a'` | `'both'` (default): used in both directions, reversed for B→A. Explicit directional entries override this. |

### Waypoint

| Field | Type | Description |
|---|---|---|
| `axes` | `dict[str, float]` | Absolute values for each recorded axis. Any subset of the device's axes. |
| `name` | `str \| None` | Optional label used in log messages. |

### ZoneDatabase (in-memory, per planner instance)

| Field | Type | Description |
|---|---|---|
| `zones` | `dict[str, list[Zone]]` | Device name → list of zones (config order; first match wins for overlapping hulls). |
| `graph` | `dict[str, dict[tuple[str,str], list[Waypoint]]]` | Device name → (from_zone, to_zone) → ordered waypoint list. Both directions populated at load time. |
| `_delegate_planners` | `dict[str, MotionPlanner]` | Cache of instantiated delegate planners, keyed by class path. Populated lazily on first use. |

---

## 4. Configuration Format

Zone and path data for a device are stored in a file named `motion_zones.cfg` in the device's state directory (same location as other per-device calibration state, e.g. `transform.cfg`). The file uses ACQ4's standard indented key-value `.cfg` format.

The planner reads all devices' `motion_zones.cfg` at initialization and rebuilds the `ZoneDatabase`. A `reload_zones()` method triggers a hot-reload without restarting the planner.

### Pipette device example

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
            # ... additional recorded points ...

    InsideCleaningWell:
        relativeTo: CleaningWell      # hull points in CleaningWell's local frame
        anchorPosition: [0.00523, 0.01045, 0.00000]   # CleaningWell's global position when this zone was recorded; captured automatically
        hull_points:
            0: [-0.0004, -0.0004, -0.0005]
            1: [ 0.0004, -0.0004, -0.0005]
            2: [-0.0004,  0.0004, -0.0005]
            3: [ 0.0004,  0.0004, -0.0005]
            4: [ 0.0000,  0.0000,  0.0010]

    InsideElectrodeSolutionWell:
        relativeTo: ElectrodeSolutionWell
        hull_points:
            # ...

    RecordingChamber:
        delegate: acq4.motion.DefaultMotionPlanner  # same-zone moves forwarded to DefaultMotionPlanner
        hull_points:
            0: [-0.0015, -0.0015, -0.0020]
            1: [ 0.0015, -0.0015, -0.0020]
            2: [-0.0015,  0.0015, -0.0020]
            3: [ 0.0015,  0.0015, -0.0020]
            4: [ 0.0000,  0.0000,  0.0010]

paths:
    0:                                # bidirectional: Bath ↔ InsideCleaningWell
        from: Bath
        to: InsideCleaningWell
        waypoints:
            0:
                z: 0.0050            # raise z only; x and y unchanged
            1:
                x: 0.0120
                y: -0.0030
            2:
                z: 0.0005            # descend into well approach
    1:                                # explicit B→A override (different exit sequence)
        from: InsideCleaningWell
        to: Bath
        waypoints:
            0:
                z: 0.0010
            1:
                x: -0.0050
                y:  0.0020
                z:  0.0050
    2:                                # bidirectional: Bath ↔ InsideElectrodeSolutionWell
        from: Bath
        to: InsideElectrodeSolutionWell
        waypoints:
            0:
                z: 0.0050
            1:
                x: -0.0200
                y:  0.0100
```

**Zone ordering:** Zones are evaluated in the order they appear in `motion_zones.cfg`; when a position falls inside more than one zone, the first match wins (§5). For overlapping zones — such as a small specific zone nested inside a larger one — list the more specific zone first. The zone configuration UI displays a reorderable list of zones for each device; users can drag items to change priority without editing the config file directly.

**Bidirectionality rule:** When both A→B and B→A entries appear in the config, they are used independently. When only one direction is present, it applies in both directions — reversed for the return trip.

**Anchor devices have no interaction-position config.** The required anchor position is stored as `anchorPosition:` in the moving device's zone entry (e.g. `Pipette1/motion_zones.cfg`), captured automatically when the zone is recorded. `InteractionSite` devices do not have a `motion_zones.cfg` entry for this value.

**Coordinate convention:** All hull points in non-relative zones are in global coordinates at the time of recording. Hull points in relative zones are in the anchor device's local frame. Waypoints are always in global coordinates, recorded with the anchor site at the `anchor_position` recorded when the zone was defined.

---

## 5. Zone Membership

Zone membership is tested independently of the planner — also used by the UI to display which zone a device currently occupies.

### `find_zones(device, position_global=None) → list[Zone]`

```python
def find_zones(device: Device, position_global: np.ndarray | None = None) -> list[Zone]:
    """Return all zones containing position_global, in config order.
    Defaults to the device's current position if position_global is None."""
    if position_global is None:
        position_global = device.globalPosition()

    zones = self._db.zones.get(device.name(), [])
    matches = []

    for zone in zones:
        if zone.relative_to is None:
            test_point = position_global
        else:
            test_point = zone.relative_to.mapFromGlobal(position_global)

        if point_in_convex_hull(zone.hull, test_point, tol=POSITION_TOLERANCE):
            matches.append(zone)

    return matches
```

### `find_zone(device, position_global=None) → Zone | None`

Convenience wrapper; returns the first result from `find_zones`, or `None` if the list is empty.

```python
def find_zone(device: Device, position_global: np.ndarray | None = None) -> Zone | None:
    results = self.find_zones(device, position_global)
    return results[0] if results else None
```

### Hull containment test

Given a `scipy.spatial.ConvexHull`, a point *p* is inside if and only if for every face equation `[a, b, c, d]`: `a·px + b·py + c·pz + d ≤ tol`. Equivalently:

```python
np.all(hull.equations @ np.append(point, 1) <= tol)
```

**Tolerance:** `POSITION_TOLERANCE = 1e-4` m (0.1 mm). Configurable via planner config. Handles floating-point drift and small positioning errors at zone boundaries.

### Overlapping zones

If a position falls inside more than one zone, `find_zones` returns all of them in config order. Callers that use `find_zone` (which takes only the first result) will silently prefer the highest-priority zone. User is warned when creating a new zone if it overlaps with an existing one.

### `find_zone_in_frame(device, position_local, anchor) → Zone | None`

Used when `MoveSpec.relative_to` is set: tests `position_local` directly against zones whose `relative_to == anchor` (already in anchor's frame).

```python
def find_zone_in_frame(device: Device, position_local: np.ndarray,
                        anchor: Device) -> Zone | None:
    for zone in self._db.zones.get(device.name(), []):
        if zone.relative_to is anchor:
            if point_in_convex_hull(zone.hull, position_local, tol=POSITION_TOLERANCE):
                return zone
    return None
```

`find_zone_in_frame` does not accept a `None` position; the caller must always supply an explicit local coordinate.

> **Overlapping relative zones:** If a device has two relative zones anchored to the same device and their hulls overlap, `find_zone_in_frame` also returns the first match in config order. The same rule applies: list the more specific relative zone first in `motion_zones.cfg`.

---

## 6. Zone Graph

### Graph construction (at load time)

For each device's set of path entries, the planner populates `dict[(from_name, to_name), list[Waypoint]]`:

1. Collect all path entries from `motion_zones.cfg`.
2. Build the set of explicitly-configured (from, to) pairs.
3. For each path entry whose reverse is *also* explicitly in the config: store each direction as-is.
4. For each path entry with no explicit reverse counterpart: store both `(A, B) → waypoints` and `(B, A) → reversed(waypoints)`.

### `find_route(device, from_zone, to_zone) → list[Zone]`

BFS over the zone graph, returning the minimum-hop sequence of zones from start to end (inclusive).

```python
def find_route(device, from_zone: Zone, to_zone: Zone) -> list[Zone]:
    if from_zone.name == to_zone.name:
        return [from_zone]

    graph = self._db.graph.get(device.name(), {})
    visited = {from_zone.name}
    queue = [[from_zone]]          # each item is a path-so-far

    while queue:
        path = queue.pop(0)
        current = path[-1]
        for (src, dst) in graph:
            if src == current.name and dst not in visited:
                dst_zone = next(z for z in self._db.device_zones(device.name()) if z.name == dst)
                new_path = path + [dst_zone]
                if dst == to_zone.name:
                    return new_path
                visited.add(dst)
                queue.append(new_path)

    raise PlanningError(
        f"No path from zone '{from_zone.name}' to '{to_zone.name}'"
        f" for {device.name()}. Configure a path or intermediate zone."
    )
```

If `Bath` connects to `Approach` and `Approach` connects to `InsideCleaningWell`, a request to move from `Bath` directly to `InsideCleaningWell` routes through `Approach` automatically. All intermediate waypoints are concatenated into a single `SequentialGroup`.

---

## 7. Planning Algorithm

`plan(specs, name)` validates all specs (via base class), calls `_plan_one(spec)` for each, then composes the per-spec plans (see §9). `_plan_one` runs a single unified algorithm for every `MoveSpec` regardless of zone type or `relative_to`.

---

### Overview

`_plan_one()` runs a single algorithm for every `MoveSpec` regardless of zone type or `relative_to`. There are no special cases dispatched by device type.

### `_plan_one(spec, name="") → MovePlanStep`

The following is ILLUSTRATIVE to be clear about the intended algorithm; should not be taken as final code. This may be modified as needed when other parts of the system evolve.

```python
def _plan_one(self, spec: MoveSpec, name: str = "") -> MovePlanStep:
    device = spec.device

    # ── Step 1: Determine zones ───────────────────────────────────────────────
    if spec.relative_to is not None:
        z_end = self._find_zone_in_frame(device, spec.position, anchor=spec.relative_to)
    else:
        z_end = self._find_zone(device, spec.position)

    z_start = self._find_zone(device)              # device's current position

    if z_start is None:
        raise PlanningError(f"{device.name()} is not in any known zone at its current position")

    if z_start.relative_to is not None:
        anchor_dist = np.linalg.norm(
            z_start.relative_to.globalPosition() - z_start.anchor_position
        )
        if anchor_dist > POSITION_TOLERANCE:
            raise PlanningError(
                f"{device.name()} is in zone '{z_start.name}' (relative to "
                f"{z_start.relative_to.name()}) but {z_start.relative_to.name()} "
                f"is {anchor_dist*1e3:.2f} mm from its anchor position — "
                f"inconsistent state."
            )

    if z_end is None:
        raise PlanningError(f"Target position for {device.name()} is not in any known zone")

    # Resolve global target. z_end is valid; anchor_position is guaranteed set for
    # relative zones by ConfigError at load time.
    if spec.relative_to is not None:
        P_global = spec.relative_to.mapToGlobalAtPosition(spec.position, z_end.anchor_position)
    else:
        P_global = spec.position

    # ── Step 2: Build raw position sequence ──────────────────────────────────
    # positions = [wp1, wp2, ..., wpN, P_global]
    # where wp1..wpN are zone-transition waypoints (may be outside all zones).
    if z_start.name == z_end.name:
        positions = [P_global]
    else:
        route = self._find_route(device, z_start, z_end)
        positions = []
        cur = device.globalPosition()
        for from_z, to_z in zip(route, route[1:]):
            for wp in self._db.zone_graph(device.name())[(from_z.name, to_z.name)]:
                cur = self._resolve_waypoint(device, cur, wp)
                positions.append(cur)
        positions.append(P_global)

    # ── Step 3: Apply delegate sub-planners ───────────────────────────────────
    steps = []

    if z_start.name != z_end.name and z_start.delegate_class is not None:
        # First step: delegate [current_pos] → positions[0] to z_start's sub-planner.
        first_spec = MoveSpec(device, positions[0], speed=spec.speed)
        steps.append(self._get_delegate(z_start).plan([first_spec], name=name))
        remainder = positions[1:]
    else:
        remainder = positions

    # Middle steps (raw zone-transition waypoints between the two delegate regions):
    for pos in remainder[:-1]:
        steps.append(AtomicMove(device, pos, spec.speed, "zone transition waypoint"))

    # Final step: delegate or direct AtomicMove.
    final_pos = remainder[-1]
    if z_end.delegate_class is not None:
        final_spec = MoveSpec(device, final_pos, speed=spec.speed)
        steps.append(self._get_delegate(z_end).plan([final_spec], name=name))
    else:
        steps.append(AtomicMove(device, final_pos, spec.speed,
                                f"destination in zone '{z_end.name}'"))

    # ── Step 4: Prepend anchor-device plan ────────────────────────────────────
    # If the end zone is relative to an anchor device, the anchor must be at
    # z_end.anchor_position when this path begins. By the start-zone invariant
    # above, if z_start is relative to the same anchor, the anchor is already
    # at z_start.anchor_position. We only generate a repositioning plan when
    # the anchor is measurably out of position.
    if z_end.relative_to is not None:
        anchor = z_end.relative_to
        anchor_dist = np.linalg.norm(anchor.globalPosition() - z_end.anchor_position)
        if anchor_dist > POSITION_TOLERANCE:
            anchor_spec = MoveSpec(anchor, z_end.anchor_position, speed=spec.speed)
            anchor_plan = self._plan_one(anchor_spec, name=f"{name}:reposition {anchor.name()}")
            steps = [anchor_plan] + steps

    if len(steps) == 1:
        return steps[0]
    return SequentialGroup(steps, f"Move {device.name()} → zone '{z_end.name}'")
```

### Planning assumptions and constraints

1. **Unzoned device is always an error.** A device with no zone configuration is not a special case — it raises `PlanningError` at the zone-lookup step. Devices that are not zone-managed should not be included in specs passed to this planner.

2. **Delegate planning uses current device position.** The end-zone delegate plans as if the device is at its position when `plan()` is called, not at the last zone-transition waypoint. For cross-zone moves into a delegate zone, configure transition paths so the last waypoint is in a state consistent with what the delegate expects (e.g. above `approachDepth` for a tissue-crossing planner).

3. **Anchor positioning is recursive.** `_plan_one(anchor_spec)` passes the anchor device through the same algorithm. The anchor's own zone graph is used to route it to `z_end.anchor_position`. If the anchor's target zone is itself relative to a third device, the recursion continues. Circular anchor dependencies (A's zone is relative to B, B's zone is relative to A) are a configuration error detected at planning time as infinite recursion; the spec flags this as a `ConfigError` at load time (see §15).

4. **Same-zone moves.** When `z_start == z_end` the position sequence is `[P_global]` with no intermediate waypoints. The start-zone delegate condition (`z_start != z_end`) is false; the end-zone delegate (if set) handles the single step. This is the degenerate form of the general algorithm, not a special case.

5. **Relative-zone start invariant.** If the device's current position is inside a relative zone, the anchor device must already be at that zone's `anchor_position`. If it is not, the world is in an inconsistent state and `PlanningError` is raised immediately — the planner does not attempt to recover. This invariant is maintained by the planner itself: whenever a device transitions into a relative zone, the anchor is repositioned first (Step 4).

---

## 8. Waypoint Resolution

A waypoint specifies values for a subset of axes. Unspecified axes retain the current device position for that axis. The result is a complete global position suitable for an `AtomicMove`.

```python
def _resolve_waypoint(self, device: Device, current_pos: np.ndarray,
                       wp: Waypoint) -> np.ndarray:
    result = current_pos.copy()
    axis_map = device.axis_order()            # e.g. {'x':0,'y':1,'z':2} or {'x':0,'y':1,'z':2,'d':3}
    for axis_name, value in wp.axes.items():
        idx = axis_map[axis_name]
        result[idx] = value
    return result
```

**Axis mapping:** The device exposes `axis_order()` returning a dict of axis name → array index. Standard mapping: `'x'→0, 'y'→1, 'z'→2`, with `'d'→3` for four-axis manipulators. An unknown axis name in a waypoint raises `ConfigError` at load time.

**Position propagation:** When a path has multiple waypoints, each waypoint's result becomes the `current_pos` for the next. The chain is computed entirely in the planner before any hardware moves.

> **Recording convention:** Waypoints are recorded in global coordinates with the anchor InteractionSite at the `anchor_position` recorded when the zone was defined. The UI should enforce that path recording for relative-zone paths is only allowed while the site is at the `anchor_position` recorded when the zone was defined.

---

## 9. Multi-Spec Composition

When `plan()` receives multiple `MoveSpec` entries, it plans each independently, then composes the results.

### Grouping by site dependency

Specs are partitioned into groups by their `relative_to` InteractionSite (or `None` for specs with no site dependency):

- **No-site group** (`relative_to` is None or a non-site device): all sub-plans placed in a single `ParallelGroup`.
- **Per-site group** (`relative_to = SiteX`): a single site-repositioning step is generated (if needed), followed by a `ParallelGroup` of all device routing plans for that site. Combined form: `SequentialGroup([site_move, ParallelGroup([...])])`.

### Final structure

All group plans are combined into an outer `ParallelGroup`, allowing different sites to be repositioned simultaneously:

```python
# Example: Pipette1 → CleaningWell, Pipette2 → ElectrodeSolutionWell, Scope → global pos

ParallelGroup([
    SequentialGroup([
        AtomicMove(CleaningWell.stage, ..., "position CleaningWell at interaction pos"),
        ParallelGroup([
            SequentialGroup([...], "route Pipette1 to CleaningWell"),
        ])
    ]),
    SequentialGroup([
        AtomicMove(ElecSolWell.stage, ..., "position ElecSolWell at interaction pos"),
        ParallelGroup([
            SequentialGroup([...], "route Pipette2 to ElecSolWell"),
        ])
    ]),
    AtomicMove(Scope, ..., "direct move within zone 'Park'"),   # no-site group
])
```

### Two specs sharing a site

If two specs have the same `relative_to` site, one site-repositioning step is generated and both device routings are placed in the same `ParallelGroup` after it. Both pipettes converge on the same site at the same interaction position, so this is valid.

### Conflict: site already in specs

The base-class `_validate_specs` already prohibits a `relative_to` anchor from also appearing as a moving device in the same plan call. The zone planner adds a further check: if the planner would generate a site-move step for site S but S's parent stage is also explicitly in the spec list as a moving device, raise `PlanningError`.

---

## 10. Device Collection

`collect_devices(plan)` extends the base-class implementation (which walks the plan tree for `AtomicMove.device` values) to include:

- All anchor devices (`Zone.relative_to`) for zones referenced in the plan — so their coordinate frames cannot shift during execution.
- All parent stages of any `InteractionSite` that appears as a `relative_to` in any spec — even if no site-move step was generated.

```python
def collect_devices(self, plan: MovePlanStep) -> set[Device]:
    devices = super().collect_devices(plan)       # walk AtomicMove nodes

    for spec in self._current_specs:
        if spec.relative_to is not None:
            anchor = spec.relative_to
            devices.add(anchor)
            if hasattr(anchor, '_parentStage') and anchor._parentStage is not None:
                devices.add(anchor._parentStage)

    return devices
```

`self._current_specs` is stored at the start of `plan()` for use by `collect_devices()`.

---

## 11. InteractionSite Additions

The zone planner introduces a clean division of responsibility: `InteractionSite` knows *where it needs to be*; the zone planner knows *how to get devices there*.

**Departure from existing system:** The existing system gives `InteractionSite` full responsibility for knowing approach positions per-pipette and for driving its own stage moves. In the zone planner: each relative zone records the anchor position at which the site must be (`Zone.anchor_position`, captured automatically at zone recording time), and the planner drives the stage move and all device routing. The site's existing `hasApproachPosition` / `saveApproachPosition` API remains intact and is used by `DefaultMotionPlanner`; the two planners coexist via composition: `ZoneBasedMotionPlanner` holds a `_next_planner` reference (typically a `DefaultMotionPlanner`) and delegates same-zone moves to it in zones marked `delegate: true`.

### New method: `globalPosition() → np.ndarray`

The site's current global position (its device origin in global coordinates). Verify whether this already exists on `OptomechDevice`; expose if not.

### New method: `computeStagePositionForSiteAt(desired_global) → np.ndarray`

Given a desired global position for the site's origin, returns the required position for the site's parent stage.

```python
def computeStagePositionForSiteAt(self, desired_global: np.ndarray) -> np.ndarray:
    # Assumes site moves rigidly with parent stage (pure translation).
    current_site_global = self.globalPosition()
    current_stage_global = self._parentStage.globalPosition()
    delta = desired_global - current_site_global
    return current_stage_global + delta
```

> **Implementation note:** This assumes the site's local offset from the stage is constant (no stage rotation changes the site's local offset). If the stage can rotate, a full transform-chain computation is needed; flag this.

### New method: `mapToGlobalAtPosition(local_pos, site_global) → np.ndarray`

Maps a position in the site's local frame to global coordinates, assuming the site *will be* at `site_global` rather than its current position. Used by the planner to resolve targets before executing the site move.

```python
def mapToGlobalAtPosition(self, local_pos: np.ndarray,
                            site_global: np.ndarray) -> np.ndarray:
    delta = site_global - self.globalPosition()
    return self.mapToGlobal(local_pos) + delta
```

### Interaction position storage

Stored as `anchorPosition:` within the relative zone's entry in the moving device's `motion_zones.cfg` (e.g. `Pipette1/motion_zones.cfg`). Captured automatically when the zone is recorded — the user does not set it separately. Read by the `ZoneDatabase` loader into `Zone.anchor_position`. `InteractionSite` devices have no separate interaction-position config.

---

## 12. Rollback

Rollback is an execution-layer responsibility. `plan()` is unaware of rollback. `ZoneBasedMotionPlanner` overrides the base-class plan execution path to track completed moves and reverse them on failure.

### Mechanism

```python
def _execute_with_rollback(self, plan: MovePlanStep) -> None:
    undo_stack: list[tuple[Device, np.ndarray]] = []   # (device, position_before_move)

    def run(step):
        if isinstance(step, AtomicMove):
            prev = step.device.globalPosition()
            self._move_device(step)                 # blocks until complete
            undo_stack.append((step.device, prev))
        elif isinstance(step, SequentialGroup):
            for child in step.steps:
                run(child)
        elif isinstance(step, ParallelGroup):
            # Launch all children; on any child failure, cancel siblings and rollback.
            run_parallel_with_rollback(step.steps, run, undo_stack)

    try:
        run(plan)
    except Exception as exc:
        log.warning("Move failed (%s); rolling back %d completed step(s).", exc, len(undo_stack))
        for device, prev_pos in reversed(undo_stack):
            try:
                device.moveTo(prev_pos, speed='fast')
                log.debug("Rollback: moved %s back to %s", device.name(), prev_pos)
            except Exception as rb_exc:
                log.error("Rollback failed for %s: %s", device.name(), rb_exc)
        raise
```

**Best-effort semantics:** Rollback moves use `speed='fast'` and are best-effort. If a rollback move itself fails, the error is logged at `ERROR` level and rollback continues with the remaining steps. The original exception is re-raised regardless.

**Parallel group rollback:** Within a `ParallelGroup`, all children start simultaneously. If any child fails, the executor sends a stop signal to in-progress siblings, waits for them to settle, then adds all completed moves to the undo stack before propagating the failure upward.

---

## 13. Logging

Logger name: `'acq4.motion.zone_planner'`. All messages include the plan name as a prefix (throughline) so a complete plan's decisions can be filtered from a busy log.

| Event | Level | Message content |
|---|---|---|
| Plan start | `DEBUG` | `[{name}] Planning {N} spec(s). Devices: {device_list}` |
| Zone lookup result | `DEBUG` | `[{name}] {device}: current zone '{z_start}', target zone '{z_end}'` |
| Route found | `DEBUG` | `[{name}] {device}: route {zone_a} → … → {zone_b} ({N} hop(s), {M} waypoint(s))` |
| Site repositioning needed | `DEBUG` | `[{name}] {site}: moving to interaction position {req} (currently {cur}, Δ={dist:.2f}mm)` |
| Site already positioned | `DEBUG` | `[{name}] {site}: already at interaction position (within tolerance)` |
| Unzoned device warning | `WARNING` | `[{name}] {device}: no zone config — falling back to direct move` |
| Overlapping zones | `WARNING` | `{device}: position is in both '{z1}' and '{z2}'; using '{z1}' (config order). To change priority, reorder zones in motion_zones.cfg.` (once per pair per session) |
| Rollback start | `WARNING` | `[{name}] Failure during execution; rolling back {N} move(s)` |
| Rollback step | `DEBUG` | `[{name}] Rollback: {device} → {prev_pos}` |
| Rollback step failure | `ERROR` | `[{name}] Rollback failed for {device}: {exc}` |

---

## 14. Class Structure

```python
# acq4/motion/zone_planner.py

class ZoneBasedMotionPlanner(MotionPlanner):
    def __init__(self, config: dict = None)
    def plan(self, specs: list[MoveSpec], name: str = "") -> MovePlanStep
    def collect_devices(self, plan: MovePlanStep) -> set[Device]
    def execute(self, specs: list[MoveSpec], name: str = "") -> None
    def reload_zones(self) -> None               # hot-reload ZoneDatabase from disk

    # planning internals
    def _plan_one(self, spec: MoveSpec) -> MovePlanStep
    def _build_transition(self, device, route, final_pos, speed, explanation) -> SequentialGroup
    def _compose_multi_spec(self, sub_plans: list, specs: list[MoveSpec]) -> MovePlanStep

    # zone lookups (delegates to ZoneDatabase)
    def _find_zones(self, device, pos_global=None) -> list[Zone]
    def _find_zone(self, device, pos_global=None) -> Zone | None     # returns _find_zones(...)[0]
    def _find_zone_in_frame(self, device, pos_local, anchor) -> Zone | None
    def _find_route(self, device, from_zone, to_zone) -> list[Zone]
    def _resolve_waypoint(self, device, current_pos, wp) -> np.ndarray

    # delegate planner cache
    def _get_delegate(self, zone: Zone) -> MotionPlanner  # instantiate and cache by zone.delegate_class

    # execution
    def _execute_with_rollback(self, plan: MovePlanStep) -> None

    # state
    _db: ZoneDatabase
    _delegate_planners: dict[str, MotionPlanner]  # keyed by class path; populated lazily
    _current_specs: list[MoveSpec]             # set at plan() entry for collect_devices


# acq4/motion/zone_database.py

class ZoneDatabase:
    def load(self, manager) -> None             # iterate devices, read motion_zones.cfg
    def device_zones(self, device_name: str) -> list[Zone]
    def zone_graph(self, device_name: str) -> dict[tuple[str,str], list[Waypoint]]
    def point_in_hull(self, hull: ConvexHull, point: np.ndarray, tol: float) -> bool


class Zone:
    name: str
    hull_points: np.ndarray
    hull: ConvexHull                            # derived; not serialized
    relative_to: Device | None
    anchor_position: np.ndarray | None   # global position of relative_to device at zone recording time; None for non-relative zones


class Waypoint:
    axes: dict[str, float]
    name: str | None


# acq4/devices/InteractionSite.py  (additions)

class InteractionSite:
    # Existing API unchanged.
    def globalPosition(self) -> np.ndarray
    def computeStagePositionForSiteAt(self, desired_global: np.ndarray) -> np.ndarray
    def mapToGlobalAtPosition(self, local_pos: np.ndarray, site_global: np.ndarray) -> np.ndarray
```

---

## 15. Error Conditions

`ConfigError` is raised at `ZoneDatabase.load()` time, preventing planner initialization with invalid config. `PlanningError` is raised inside `plan()` and propagates to the caller.

| Condition | Exception | Message pattern |
|---|---|---|
| Device's current position not in any known zone | `PlanningError` | *{device} is not in any known zone at {pos}. Define a zone that covers this position.* |
| Target position (global) not in any known zone | `PlanningError` | *Target {pos} is not in any known zone for {device}.* |
| Target (in anchor's frame) not in any zone relative to anchor | `PlanningError` | *Position {pos} in {anchor}'s frame is not in any zone for {device}. Define a zone with relativeTo: {anchor}.* |
| Cross-zone target whose anchor is not at interaction position (no relative_to in spec) | `PlanningError` | *Target is in zone '{zone}' (relative to {anchor}) but {anchor} is {dist}mm from interaction position. Use relative_to={anchor} to request repositioning.* |
| Relative zone has no `anchor_position` (zone recording incomplete) | `ConfigError` | *Zone '{zone}' for {device} has `relativeTo: {anchor}` but no recorded anchor position. Re-record the zone.* |
| No path between two zones (direct or via graph) | `PlanningError` | *No path from zone '{A}' to '{B}' for {device}. Configure a path or an intermediate zone.* |
| Two specs require repositioning the same site to different positions | `PlanningError` | *Conflicting site requirements: both {device_a} and {device_b} need {site} but at different positions.* |
| Spec moves a site's parent stage while another spec uses that site as relative_to | `PlanningError` | *Cannot move {stage} while {pipette} is also requesting interaction with {site}.* |
| Fewer than 4 hull points (degenerate hull) | `ConfigError` | *Zone '{zone}' for {device} has {N} hull points; at least 4 non-coplanar points required.* |
| Waypoint specifies unknown axis | `ConfigError` | *Zone path for {device}: waypoint axis '{axis}' is not valid. Valid axes: {list}.* |
| Path references non-existent zone name | `ConfigError` | *Path from '{A}' to '{B}' references unknown zone '{A}' for {device}.* |
| `relativeTo` names a device not in the device manager | `ConfigError` | *Zone '{zone}' for {device}: relativeTo device '{name}' not found.* |
| Device has no zone configuration | `PlanningError` | *{device} has no zone configuration; the zone-based planner requires all devices to have defined zones.* |
| Circular anchor dependency detected at load time | `ConfigError` | *Zone '{zone}' for {device} creates a circular dependency: {device} → {anchor} → … → {device}. Remove the cycle.* |
| Device is in a relative zone but anchor is not at `anchor_position` | `PlanningError` | *{device} is in zone '{zone}' (relative to {anchor}) but {anchor} is {dist}mm from its anchor position — inconsistent state.* |

---

## 16. Testing Strategy

Tests live in `acq4/motion/tests/test_zone_planner.py`, using the existing mock device infrastructure from `conftest.py`. New mocks needed: `MockZoneDatabase` (in-memory, no file I/O) and an extended `MockInteractionSite` with `globalPosition` / `computeStagePositionForSiteAt` / `mapToGlobalAtPosition`.

### Zone membership
- Point clearly inside hull → correct zone returned.
- Point clearly outside all hulls → `None` returned.
- Point within `POSITION_TOLERANCE` of hull surface → inside (tolerance accepted).
- Relative zone: test with anchor at two different positions; confirm membership follows the anchor.
- Overlapping zones: confirm first-match-wins and a warning is logged once only.

### Zone graph and route finding
- Same zone → route is `[zone]`, length 1.
- Direct connection A→B: route is `[A, B]`.
- Multi-hop A→C via B: route is `[A, B, C]`.
- No path: `PlanningError` with descriptive message.
- Bidirectional path: confirm B→A uses reversed waypoints.
- Explicit B→A override: confirm reversed waypoints are not used.

### Planning cases
- **Zone lookup failure (start):** device at a position not in any zone → `PlanningError`.
- **Start zone is relative, anchor out of position:** device is in a relative zone but its anchor is not within `POSITION_TOLERANCE` of `anchor_position` → `PlanningError` with "inconsistent state" message.
- **Zone lookup failure (end):** target position not in any zone → `PlanningError`.
- **Same zone, no delegate:** single `AtomicMove` to target.
- **Same zone, end-zone delegate:** delegate's `plan()` result returned directly; no `AtomicMove` emitted by zone planner.
- **Cross-zone, no delegates:** `SequentialGroup` containing waypoint `AtomicMove` nodes and final `AtomicMove`.
- **Cross-zone, start-zone delegate:** delegate's plan replaces the first `[start] → [wp1]` step; middle and final steps are direct.
- **Cross-zone, end-zone delegate:** delegate's plan replaces the final `[wpN] → [end]` step; earlier steps are direct.
- **Cross-zone, both delegates:** first and last steps both delegated; middle steps are direct.
- **Relative zone, anchor already in position:** no anchor plan prepended (anchor's `_plan_one` produces a same-zone direct `AtomicMove` to current position which is a zero-distance move — acceptable, or the anchor plan can be omitted if the anchor is already within `POSITION_TOLERANCE`).
- **Relative zone, anchor needs repositioning:** anchor `_plan_one` plan prepended; main device plan follows.
- **Recursive anchor:** anchor's own end zone is relative to a third device → third device's plan prepended to anchor's plan (recursion depth 2).

### Multi-spec composition
- Two independent specs → outer `ParallelGroup`.
- Two specs sharing one site → one site move, `ParallelGroup` of device routings.
- Two specs, different sites → `ParallelGroup` of two sequential groups.
- Spec moves site's stage while another spec uses site as relative_to → `PlanningError`.

### Rollback
- Failure after first `AtomicMove`: device returned to starting position.
- Failure after third move in a five-step sequence: three rollback moves emitted in reverse order.
- Rollback move itself fails: `ERROR` logged, rollback continues, original exception re-raised.

### Config loading
- Valid config round-trips correctly.
- Fewer than 4 hull points → `ConfigError` at load time.
- Unknown `relativeTo` device name → `ConfigError`.
- Path referencing non-existent zone → `ConfigError`.
- Unknown axis in waypoint → `ConfigError`.
- `reload_zones()`: updated config is reflected without restarting planner.
- Relative zone with `anchorPosition:` key → `zone.anchor_position` populated correctly.
- Relative zone missing `anchorPosition:` key → `ConfigError` at load time.
- Non-relative zone → `zone.anchor_position` is `None`.
