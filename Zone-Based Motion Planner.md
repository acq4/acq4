Zone-Based Motion Planner
=========================

* "Zones" are defined as a region of space that a particular device may occupy
* Zones are defined by the user: a UI allows to "record zone" => user moves device to many locations within the zone => a convex hull is calculated, within which the device is considered to be in that zone. User may define any number of named zones for each device.
* Within a zone, a device is allowed to move freely. To move from one zone to another, the device must follow a prescribed path
* User defines paths between zones using the same UI:
    - start anywhere inside a zone
    - move device to position
    - record x, y, and/or z position
      example: if ony z is recorded, then when replaying only the z position will be moved
    - optionally record a name for the waypoint
    - repeat until inside next zone
    - path is recorded from beginning to ending zone
* InteractionSite devices have an extra configuration: a user-definable, per-device interaction position. Example: User may say "CleaningWell1 must go to interaction position x,y,z before Pipette1 can interact with it"
    - Zones may be defined _relative to another device_. For example, a pipette may have a zone defined inside of a cleaning well, and if the well moves, then the zone moves with it. 


Example Use
-----------

Pipette cleaning
- cleaning requests to move the pipette to its known cleaning position relative to the cleaning well interaction site
- planner knows that interaction site must move to its configured position for interacting with pipette
- planner lays out motion plan for getting interaction site to final position, possibly with a zone change
- planner adds steps for getting pipette to interaction site zone (this is a zone change by virtue of the position being relative to an interaction site, regardless of whether the actual global position is inside the pipette's current zone
- planner adds a final step to move the pipette to its requested position

Exiting Pipette Cleaning
------------------------




Reliability
-----------

Guaranteed reliable behaviors are a high priority. 
- Devices are reserved during move sequences to ensure no interruptions are allowed
- When transitioning between zones, we record the sequence of moves taken so that if an error occurs at any point, the sequence can be rewound
- Devices are not allowed to move freely to a location outside of a zone (although they may have such waypoints between zones)
- Devices may never move from one zone to another without taking a configured safe path


Logging
-------

- All move requests are logged with an appropriate throughline, respecting the name of the plan request
- Log messages are clear about what device will move, where it moves to, and why
- Logging explains the structure of the plan and its reasoning


Architectural Context
---------------------

### Plugin contract

A planner is a class that subclasses `MotionPlanner` (acq4/motion/planner.py) and implements one method:

```python
def plan(self, specs: list[MoveSpec], name: str = "") -> MovePlanStep:
```

`plan()` must be a pure planning function: it may read device positions but must not command hardware. All device reservation, threading, execution, and final-position validation are handled by the base-class `execute()` template — the planner only builds and returns a plan tree.

The planner is registered by dotted class path in the ACQ4 config:

```yaml
motionPlanner:
    class: acq4.motion.ZoneBasedMotionPlanner
```

It can also be hot-swapped at runtime via `Manager.motionPlanner = ZoneBasedMotionPlanner()` (used by the AutomationDebug UI dropdown).

---

### Input: `MoveSpec` (acq4/motion/spec.py)

Each element of `specs` describes one device movement:

| Field | Type | Meaning |
|---|---|---|
| `device` | Device | The device to move |
| `position` | np.ndarray | Target position; global coords if `relative_to` is None, otherwise in the local frame of `relative_to` |
| `relative_to` | Device or None | Usually an `InteractionSite`; the planner must resolve this to global coords before emitting `AtomicMove` nodes |
| `speed` | str or float | `"fast"`, `"slow"`, or m/s; the planner may tighten (slow down) but not loosen |
| `kwargs` | dict | Passed verbatim to the hardware move call |

The base class validates specs before calling `plan()` (duplicate devices, moving a `relative_to` anchor) and validates the returned plan after (final position of each device must match its spec target).

All Devices exist in a scene graph-like hierarchy of inherited coordinate systems, with "global" at the root. Devices provide methods for mapping between coordinate systems.

---

### Output: the plan tree (acq4/motion/plan.py)

`plan()` returns a tree of three node types. All positions in `AtomicMove` must be in **global coordinates**.

| Node | Meaning |
|---|---|
| `AtomicMove(device, position, speed, explanation, kwargs)` | Leaf: one device, one destination |
| `SequentialGroup(steps, explanation)` | Run children one after another |
| `ParallelGroup(steps, explanation)` | Start all children simultaneously; wait for all |


---

### `collect_devices()` — reserving additional devices

The planner can override `collect_devices(plan)` to add devices to the reservation set beyond those directly moved (e.g. locking the scope so its position stays stable during planning). The default implementation just walks the plan tree for `AtomicMove.device` values.

---

### What the existing DefaultMotionPlanner does that the zone planner will extend

`DefaultMotionPlanner._safe_path()` generates waypoints using a tissue-crossing heuristic: it checks whether start and end are above or below a device-specific `approachDepth` boundary and inserts waypoints along the pipette's physical insertion axis. The zone-based planner will extend this waypoint-generation strategy to allow motion outside of the tissue.