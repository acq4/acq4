# Mesh Collision Check — Specification

**Status:** Draft · Rev 0.2 · 2026-08-27

Rev 0.2 supersedes Rev 0.1. The geometric core is unchanged (per-triangle swept prisms), but the
collision engine is now `python-fcl` rather than a hand-rolled SAT kernel, and §3 adds the
surface-vs-solid semantics that the earlier draft left implicit and got wrong in places.

---

## Contents

1. [Overview](#1-overview)
2. [Concepts](#2-concepts)
3. [Geometry Semantics: Surfaces, Not Solids](#3-geometry-semantics-surfaces-not-solids)
4. [Scope and Non-Goals](#4-scope-and-non-goals)
5. [Data Model](#5-data-model)
6. [Pose Simulation](#6-pose-simulation)
7. [Sweep Construction](#7-sweep-construction)
8. [Collision Pipeline](#8-collision-pipeline)
9. [FCL Usage Constraints](#9-fcl-usage-constraints)
10. [Public API](#10-public-api)
11. [Exclusion Rules](#11-exclusion-rules)
12. [Configuration](#12-configuration)
13. [Integration with MotionPlanner](#13-integration-with-motionplanner)
14. [Module Structure](#14-module-structure)
15. [Performance Budget](#15-performance-budget)
16. [Error Conditions](#16-error-conditions)
17. [Testing Strategy](#17-testing-strategy)
18. [Rejected Alternatives](#18-rejected-alternatives)
19. [Open Questions](#19-open-questions)

---

## 1. Overview

The Mesh Collision Check is a one-shot verification service. Given a fully-formed motion plan
(`acq4.motion.plan.MovePlanStep`), it answers a single question:

> If we execute this plan exactly as written, does any device mesh pass through any other device mesh?

It is a **final gate**, not a planner. It runs once, after planning completes and before any hardware
is commanded. It is allowed to be far more expensive per query than the voxel-based edge test inside
`GeometryMotionPlanner`, because it runs once per move rather than thousands of times per search.

It shares **no code** with the voxel/`Volume`/convolution pathway in `acq4/util/geometry.py`. That
pathway exists to make many candidate plans cheap to reject. This service exists to make one final
plan trustworthy. The two are deliberately independent so that a bug in the fast approximate path
cannot mask itself in the slow exact one.

### Why mesh, not voxel

The voxel path convolves an obstacle volume with the traveler's shadow at a fixed `voxel_size`
(default 200 µm). At that resolution a pipette shaft 1.1 mm in diameter is five voxels across, and
clearances below ~200 µm are unrepresentable. The mesh path works on the actual triangles, so its
accuracy is limited only by mesh tessellation (`segments: 32` for cones by default), and it can
report true separation distances.

### The core geometric idea

A device that moves from pose `A` to pose `B` sweeps a volume. For each triangle `(v0, v1, v2)` of
its mesh, the region swept is the convex hull of the six points

```
A·v0, A·v1, A·v2, B·v0, B·v1, B·v2
```

Call each such hull a **prism**. The region swept by the body's *surface* is the union of its
prisms. We never compute that union — collision testing only needs the pieces.

**This construction is exact when the motion is a pure translation.** In ACQ4 every device transform
is `baseTransform * TTransform(offset)` (see `Stage._makeStageTransform`), so the moving subtree
translates rigidly and the hull of the six endpoints is precisely the region swept by the triangle.
There is no time discretization, therefore no step size to choose and no tunneling to bound. §7.3
specifies the subdivision that keeps this conservative if a rotating device is ever added.

---

## 2. Concepts

| Term | Definition |
|---|---|
| **Body** | One device's collidable geometry: the `trimesh.Trimesh` from `Geometry.mesh`, expressed in the device's local physical frame (already premultiplied by `geometry.transform`). One body per geometry-bearing `OptomechDevice`. |
| **Pose** | A 4×4 homogeneous matrix mapping a body's local frame to global. From `device.globalPhysicalTransform()` live, or from pose simulation (§6) hypothetically. |
| **State** | A mapping `{Stage: device-axis position}`. A state determines every body's pose. |
| **Rigid group** | Bodies whose relative poses are fixed for a given interval. Two bodies in the same group can never newly collide, so those pairs are skipped. |
| **Motion root** | The `Stage` that physically actuates when a plan step names a device. For `AtomicMove(Pipette1, …)` it is `Manipulator1`; the pipette has no actuator of its own. |
| **Interval** | A time slice of the plan during which a fixed set of rigid groups each translate from one pose to another. |
| **Prism** | The convex hull of ≤6 points — one triangle at the start pose plus the same triangle at the end pose. Represented as an `fcl.Convex`. |
| **Swept surface region** | The union of a body's prisms: the region swept by its *surface*. This, and never an enclosed volume, is what every body is represented by. |
| **Contact** | A reported intersection between two bodies' swept surface regions, annotated with interval, devices, and an approximate location. |

---

## 3. Geometry Semantics: Surfaces, Not Solids

This section exists because getting it wrong silently inverts the answer, and because ACQ4's
geometry config does not distinguish the two cases.

### 3.1 The problem

ACQ4 geometry is built from `box`, `cone`, and `cylinder` primitives whose `close_top` /
`close_bottom` flags default to `False`. The resulting meshes are frequently **open shells**, and the
free space a device must occupy is often the shell's *interior*:

- `RecordingChamber` is a truncated cone, `close_bottom: True`, open top. The pipette's job is to
  descend **inside** it.
- `CleaningWell` and `ElectrodeSolutionWell` are an open `tube` + `taper` + `tip`. The pipette
  descends **into the bore**.

So "is the pipette inside the recording chamber?" is not a collision question — it is the normal
operating condition. A naive solid interpretation (e.g. taking each primitive's convex hull) would
fill in exactly the free space the pipette needs and reject every approach.

Meanwhile genuine engulfment *is* a collision: a small object entirely swallowed by a moving solid
must be caught, even though no surface need be crossed at the start or end pose.

The geometry config carries no `solid:` / `shell:` annotation, and adding one would require
correctly classifying every existing device.

### 3.2 The rule

> **Every body is represented by the region swept by its surface — never by an enclosed volume.**

Applied uniformly, this resolves both cases with no annotation:

- A **static** body's swept surface region is its surface: a triangle soup (`fcl.BVHModel`). Static
  is simply the zero-motion case of the same rule.
- A **moving** body's swept surface region is the union of its prisms (`fcl.Convex` each).

### 3.3 Why this gives the right answers

The engine pairs a solid prism against a triangle soup, which is deliberately asymmetric:

| Situation | Mechanism | Result |
|---|---|---|
| Pipette descends a well bore, no wall contact | Prisms lie inside a closed shell; no triangle of the shell enters any prism | **no collision** ✓ |
| Pipette crosses the well wall | Wall triangles enter prisms | **collision** ✓ |
| Small obstacle engulfed by a moving solid | To engulf it, some face of the solid must pass over it; that face's prism contains the obstacle's triangles | **collision** ✓ |
| Obstacle beside the sweep | No prism contains any obstacle triangle | **no collision** ✓ |

The last row of the well case is the important one: because we never fill an interior, a hollow body
sweeping over an object in its bore does not report a collision, while a solid body sweeping over the
same object does. The distinction falls out of the mesh itself.

Moving-vs-moving stays correct for the same reason: prism-vs-prism is `Convex`-vs-`Convex`, but each
prism is genuinely the swept region of *one triangle*, so the union is still a thin swept shell, not
a filled volume.

### 3.4 Verified behaviour

Measured against `python-fcl` 0.7.0.11 (see §17 for the corresponding tests):

| Case | Result |
|---|---|
| Rod sweeping down an open tube bore | no collision ✓ |
| Rod sweeping through the tube wall | collision ✓ |
| Tiny obstacle engulfed by a solid box sweep | collision ✓ |
| Same sweep, obstacle off to the side | no collision ✓ |
| Non-convex L-bracket, obstacle in the concave notch | no collision ✓ |
| L-bracket sweeping into the obstacle | collision ✓ |
| Same, sweep too short to reach | no collision ✓ |

### 3.5 Consequences

- **Arbitrary non-convex STL is supported natively.** No convex decomposition, no watertightness
  requirement, no VHACD dependency. This matters because future geometry is expected to come from
  STL files rather than config primitives.
- **No convex hulling of bodies, ever.** Whole-body hulls are correct only for convex bodies and
  catastrophically wrong for shells. Prisms must be built per triangle.
- **One accepted blind spot:** if body *X* is *already* entirely contained inside body *Y*'s shell at
  the plan's start state, no surface crosses and soup-vs-soup cannot see it. This is genuinely
  undetectable without the solid semantics we rejected. See §11.3 and Open Question 9.

---

## 4. Scope and Non-Goals

**In scope**

- Body-vs-body swept-surface intersection for every interval of a plan.
- Broadphase acceleration (rigid-group filter, swept AABB, FCL broadphase manager).
- A configurable clearance margin, reported as separation distance.
- Exclusion of pairs that are rigidly attached, explicitly permitted, or already overlapping.
- Optional materialization of the swept mesh for display in `Visualize3D`.

**Out of scope**

- Path *finding* or plan repair. This service reports; it does not propose alternatives.
- Any use of `Volume`, `voxel_template`, `make_convolved_voxels`, `convolve_kernel_onto_volume`,
  `find_intersected_voxels_*`, `a_star_ish`, or `rrt_connect`.
- Modelling the sample, slice, or bath. There is no mesh for tissue; the surface is a `Plane` handled
  by the planner. See Open Question 4.
- Velocity, acceleration, or true time parameterization (§8.1 treats `ParallelGroup` conservatively).
- Deformable geometry.

---

## 5. Data Model

### `Body`

| Field | Type | Description |
|---|---|---|
| `device` | `OptomechDevice` | Owning device. |
| `name` | `str` | `device.name()`. |
| `vertices` | `np.ndarray (V×3)` | Vertices in the device's local physical frame, including `Geometry.transform`. |
| `faces` | `np.ndarray (F×3) int` | Triangle indices. |
| `local_bounds` | `np.ndarray (2×3)` | Local AABB, cached. |
| `cache_key` | `str` | `device.geometryCacheKey`. Bodies cache on this, so an objective swap invalidates correctly. |
| `soup` | `fcl.BVHModel` | Built once per body; used whenever the body is static in an interval. |

Construction: `Geometry.mesh` already concatenates children with their transforms applied, so
`vertices = geom.transform.map(geom.mesh.vertices)` and `faces = geom.mesh.faces`.

### `Placement`, `Interval`, `Contact`, `CollisionReport`

Unchanged from Rev 0.1, except:

- `Contact.kind` is `"overlap" | "clearance" | "pre_existing"`.
- `Contact.separation` is `0.0` for overlap (FCL returns `-1.0` for penetration; we normalize),
  otherwise the measured gap.
- `CollisionReport.stats` gains `fcl_queries` and `broadphase_rejected`.

---

## 6. Pose Simulation

Unchanged from Rev 0.1. Summarized:

- For `AtomicMove(device=D, position=p_global)`, resolve the **motion root** by walking up
  `parentDevice()` to the first `Stage`, compute the root's required global position as
  `root_global + (p_global - D_global)` **evaluated in the simulated state**, convert via
  `Stage.mapGlobalToDevicePosition`, and form `baseTransform * _makeStageTransform(new_axis_pos)`.
- Poses compose upward as **raw 4×4 numpy matrices**, not `coorx.Transform` objects. `coorx`
  validates coordinate-system names on every multiply and the device transform chain is currently
  unnamed (see the comment at `Geometry._default_transform_args`); raw matrices sidestep that
  entirely and are faster. Conversion happens once at the boundary via `transform.full_matrix`.
- Nothing mutates device state.

> **4-axis stages.** `_makeStageTransform` maps the 4-axis position through `axisTransform()` to a
> 3-vector offset, so distinct axis solutions with the same offset give the same pose; the IK
> ambiguity does not leak into collision results. It does mean a pure d-axis move is modelled as
> translating the whole manipulator assembly, which is not physically true — acceptable while no
> manipulator carries geometry, but it must be revisited if manipulator bodies are ever meshed.

---

## 7. Sweep Construction

### 7.1 Analytic prism topology

A translated triangle's hull is always a triangular prism: **6 vertices, 8 triangular faces**, with
fixed connectivity. There is no need to call QHull per triangle (measured at ~2.4 ms per hull —
prohibitive). The vertex order is `[A·v0, A·v1, A·v2, B·v0, B·v1, B·v2]` and the face table is a
module constant:

```python
PRISM_FACES = np.array([[0,1,2],[5,4,3],[0,3,4],[0,4,1],
                        [1,4,5],[1,5,2],[2,5,3],[2,3,0]], dtype=np.int32)
```

`fcl.Convex` takes a flattened face array of the form `[3,i,j,k, 3,i,j,k, ...]`, which is a constant
computed once at import.

Vertices are transformed **once per body per interval** (a `V×3` matrix multiply), then indexed by
faces. Never per-triangle.

### 7.2 Degenerate prisms

A prism is flat (zero volume) whenever the sweep direction lies in the triangle's plane. This is
**common, not exceptional** — a box sweeping along +x has flat side-face prisms.

Measured behaviour: flat prisms, zero-length sweeps, and zero-area triangles all cause
`fcl.collide` to return "no collision" rather than faulting. No crash across any tested degenerate
input. This is acceptable because a flat prism covers a measure-zero sheet, so it can only ever
contribute grazing contact, and the non-degenerate prisms of the same body carry the real detection.
Grazing is the clearance margin's job (§12).

The checker still skips prisms whose 6 points span less than `1e-12 · scale` in volume, to avoid
handing FCL numerically meaningless input.

### 7.3 Rotational motion (forward compatibility)

If a body's `local_matrix` differs between `A` and `B` by more than a pure translation, the chord
between `A·v` and `B·v` cuts *inside* the true arc and the prism **under**-approximates. Handling:

1. Extract the rotation angle `θ` between `A` and `B`.
2. Compute the body's maximum radius `r` from the rotation axis.
3. Sagitta `s = r(1 - cos(θ/2))`. If `s > sweep_tolerance` (default 10 µm), subdivide into
   `n = ceil(θ / (2·arccos(1 - tol/r)))` sub-intervals and sweep each.
4. Inflate remaining sub-interval prisms outward by the residual sagitta.

Not exercised by any current device, but must be implemented with a synthetic-rotating-body test
rather than deferred to `NotImplementedError`.

### 7.4 Materialized sweep mesh (optional)

`build_sweep_mesh(placement) -> trimesh.Trimesh` produces the swept surface for display: start mesh,
end mesh, and a quad band across every silhouette edge. Not used by the collision test; built only
when `materialize=True` or on demand from the visualizer after a failure.

---

## 8. Collision Pipeline

### 8.1 Flattening the plan into intervals

Walk the `MovePlanStep` tree:

- **`AtomicMove`** → one interval; the motion root's group translates, all others static.
- **`SequentialGroup`** → concatenate children's intervals in order, threading simulated state
  forward so each child starts where the previous ended.
- **`ParallelGroup`** → **one** interval in which every participating motion root sweeps its complete
  sub-path. A branch that is itself a `SequentialGroup` contributes a prism set per segment, all
  considered simultaneously live.

  Deliberately conservative: with no velocity model, two devices whose paths cross at different times
  will be flagged. See Open Question 2.

Each interval records the explanation strings of every plan node on the path from the root, joined
with `" → "`, so failures read like `approach RecordingChamber → pip to safe height`.

### 8.2 Broadphase

1. **Group filter.** Skip pairs in the same rigid group — exact, not heuristic. In the current rig
   this removes the entire `Stage` subtree (microscope, camera, LEDs, all three wells, deposition
   array) from consideration against itself.
2. **Swept AABB.** Per placement, the AABB of `start_bounds ∪ end_bounds` inflated by `clearance`.
   Reject disjoint pairs.
3. **FCL broadphase.** Surviving prisms are registered into an
   `fcl.DynamicAABBTreeCollisionManager` per body and collided manager-against-object.

### 8.3 Narrowphase

Two pairings only:

| Moving body | Other body | Pairing |
|---|---|---|
| prisms (`fcl.Convex`) | static (`fcl.BVHModel` soup) | Convex-vs-BVH |
| prisms (`fcl.Convex`) | prisms (`fcl.Convex`) | Convex-vs-Convex |

Clearance uses `fcl.distance`, which returns the true gap when separated and `-1.0` on penetration
(normalized to `0.0` in the report).

### 8.4 Result assembly

Contacts are deduplicated per `(device_a, device_b, interval)`; a single overlapping region produces
many prism pairs, so the report keeps the deepest one per pair per interval with a count.
`stop_on_first` (default `False`) short-circuits at the first blocking contact.

---

## 9. FCL Usage Constraints

`python-fcl` is added to `pyproject.toml`. It has confirmed sharp edges; these constraints are
normative, and each has a corresponding test in §17.

### 9.1 Never call `continuousCollide`

FCL's CCD subsystem **fails open**: unsupported node-type pairs, stubbed solvers, and broken mesh
paths all return `-1` from C++, which python-fcl's wrapper merges into the result object as
`is_collide=False, time_of_contact=1.0` — byte-identical to a genuine "no collision", frequently with
nothing on stderr. For a safety gate this is disqualifying regardless of any individual bug. Full
evidence in §18.1.

### 9.2 Pin `gjk_solver_type` to `GST_LIBCCD`

Measured on our exact query shapes, 600 randomized cases each, cross-validated against an independent
exact SAT implementation:

| Query | `GST_LIBCCD` (default) | `GST_INDEP` |
|---|---|---|
| Convex-prism vs BVH-triangle | **0 errors** | 0 errors |
| Convex-prism vs Convex-prism | **0 errors** | **2 false negatives** |

Both `GST_INDEP` failures were false negatives, one at a penetration depth of `0.395` — not a
grazing numerical edge case. The default is correct for our use; it must be **pinned explicitly**
rather than relied upon, and guarded by the randomized regression test in §17.

> Note: guidance to prefer `GST_INDEP` circulates in the context of FCL's conservative-advancement
> path. It does **not** transfer to discrete queries and is unsafe here.

### 9.3 Allocate `CollisionObject`s once and reuse via `setTransform`

`fcl.pyx` allocates `Transform` (line 106) and `CollisionObject` (line 157) with C++ `new` but frees
them with C `free()`, skipping the destructor so the geometry `shared_ptr` never releases.
(`CollisionGeometry` and the broadphase manager correctly use `del`.)

Measured impact — a bounded leak, **not** heap corruption; 450k allocation cycles produced no crash:

| Pattern | Leak |
|---|---|
| 200k `CollisionObject` create/destroy | +6.4 MB (~32 B each) |
| 200k `Transform` create/destroy | +0.0 MB |
| 200k reuse via `setTransform` | **+0.0 MB** |

The checker therefore maintains a pool of `CollisionObject`s and mutates them with `setTransform`.
This eliminates the leak and is faster than reallocating.

### 9.4 Never pass a `BVHModel` as the second operand to any CCD entry point

Moot given §9.1, but recorded because it kills the process rather than raising: it triggers
`STATUS_STACK_OVERFLOW` (`0xC00000FD`) via infinite recursion in `distanceRecurse`
([fcl#512](https://github.com/flexible-collision-library/fcl/issues/512),
[python-fcl#10](https://github.com/BerkeleyAutomation/python-fcl/issues/10) — open since 2018). A
stack overflow is not catchable, so there is no fail-safe wrapper.

---

## 10. Public API

```python
from acq4.util.collision import CollisionChecker, CollisionReport, CollisionError

checker = CollisionChecker(
    devices=None,          # None -> all OptomechDevices with geometry, from the Manager
    clearance=0.0,         # metres; report contacts closer than this
    ignore=(),             # iterable of (name_a, name_b) pairs never checked
    stop_on_first=False,
    materialize=False,     # build swept meshes for the visualizer
    sweep_tolerance=10e-6, # metres; only relevant for rotational motion
)
report: CollisionReport = checker.check_plan(plan)
```

| Function | Purpose |
|---|---|
| `check_plan(plan, **kw)` | Primary entry point; builds a default checker from the Manager. |
| `check_move(device, start, stop, **kw)` | Single straight-line segment; the unit-test workhorse. |
| `check_state(**kw)` | Zero-length interval at the live state — "is the rig currently interpenetrating?" Useful at startup and after a manual jog. |

`CollisionError` subclasses `acq4.motion.planner.PlanningError` and carries `.report`.

---

## 11. Exclusion Rules

### 11.1 Rigid-group exclusion (automatic)

Bodies whose relative pose is constant throughout an interval are never checked against each other —
exact, since neither moves in the other's frame. Computed per interval, so a pair may be excluded in
one interval and checked in the next.

### 11.2 Declared exclusions

Pairs that overlap by design (objective inside a turret, pipette through a headstage holder) are
declared once in configuration (§12) and never checked.

### 11.3 Pre-existing overlap

The plan's **start state** is evaluated first as a zero-length interval. Any pair overlapping there
is recorded as `kind="pre_existing"` and downgraded for the rest of the run.

Under §3's surface semantics this is rarer than it would be under solid semantics — a pipette resting
in a well bore is not an overlap at all, because no surface crosses. It still matters for genuine
start-state contact.

Trade-off: a pair that starts in contact gets no protection for the remainder of the plan. The
stricter alternative is to require overlap depth to be non-increasing. See Open Question 3.

---

## 12. Configuration

Under the existing `motionPlanner:` block:

```yaml
motionPlanner:
    class: acq4.motion.GeometryAwareMotionPlanner
    collisionCheck:
        enabled: True
        mode: 'raise'          # 'raise' | 'warn' | 'off'
        clearance: 0           # metres, global default
        deviceClearance:       # per-device override; a pair uses the max of the two
            Pipette1: 200*um
        ignore:
            - [Microscope, Camera]
            - [Pipette1, Manipulator1]
        timeout: 2.0           # seconds; exceeding this is a failure, never a silent pass
        materializeOnFailure: True
```

`mode: 'warn'` logs `report.describe()` and proceeds. `enabled: False` is the true bypass.

---

## 13. Integration with MotionPlanner

`MotionPlanner.execute()` currently runs:

```
_validate_specs → plan → _validate_plan → collect_devices → reserveDevices → _execute_plan
```

The check inserts between `_validate_plan` and `collect_devices`:

```python
self._validate_plan(specs, plan)
self._check_collisions(plan)          # new
devices = self.collect_devices(plan)
```

`_check_collisions` is a base-class method, so `Default`, `GeometryAware`, and `MiniRigV1` all get
it; it is a no-op when config disables it.

**Placement rationale.** It runs *before* `reserveDevices` so a rejected plan does not take locks it
will not use, and a rejection cannot leave `_on_lock_failure` state to unwind. The cost is a
theoretical race with another device moving between check and reservation; given a sub-second check
and operator- or state-machine-initiated moves, that is accepted. Checking inside the reservation
would hold every device in the rig for the duration of the test.

`check_move()` remains available for callers that want per-segment validation during planning, but is
**not** wired up by default — that would reintroduce the many-queries cost this service avoids.

---

## 14. Module Structure

New package `acq4/util/collision/`. Nothing is added to `acq4/util/geometry.py`, which is already
2653 lines and owns the voxel pathway.

| File | Contents |
|---|---|
| `__init__.py` | Re-exports `CollisionChecker`, `CollisionReport`, `Contact`, `CollisionError`, `check_plan`, `check_move`, `check_state`. |
| `bodies.py` | `Body`, scene enumeration, mesh + `BVHModel` cache keyed on `geometryCacheKey`. |
| `poses.py` | `SceneState`, motion-root resolution, pose composition (§6). The only module touching `OptomechDevice`/`Stage` internals. |
| `intervals.py` | Plan-tree flattening (§8.1). Depends only on `acq4.motion.plan` types. |
| `sweep.py` | Prism generation, analytic topology, rotational subdivision, `build_sweep_mesh` (§7). |
| `engine.py` | FCL wrapper: object pool, solver pinning, broadphase managers, collide/distance calls (§9). The only module importing `fcl`. |
| `checker.py` | `CollisionChecker`, exclusion bookkeeping, report assembly. |
| `tests/` | See §17. |

`sat.py` and `bvh.py` from Rev 0.1 are **deleted** — FCL replaces both.

**Dependency direction:** `collision` imports `acq4.util.geometry` (for `Geometry` only),
`acq4.devices`, and `acq4.motion.plan`. Nothing in `acq4.util.geometry` imports `collision`.
`acq4.motion.planner` imports `collision`, not the reverse. Only `engine.py` imports `fcl`.

---

## 15. Performance Budget

Target: **< 250 ms** for a typical plan. Measured inputs from `config/devices.cfg`:

| Device | Triangles |
|---|---|
| RecordingChamber | 96 |
| CleaningWell | 192 |
| ElectrodeSolutionWell | 192 |
| Pipette1 | 128 |

Measured: **~10.8 µs** per prism query. A full pipette sweep (128 prisms) against one obstacle is
**~1.4 ms**. Geometry construction for all four devices is ~4 ms.

Mitigations, in priority order:

1. Cache `Body` meshes and `BVHModel`s on `geometryCacheKey` at module level — `getGeometry()`
   reparses config and rebuilds meshes on every call today, which would otherwise dominate.
2. Reuse `CollisionObject`s via the §9.3 pool.
3. Cache static-body `BVHModel`s across intervals.

If a plan exceeds `timeout`, the checker finishes the current interval and returns a report with
`stats['timed_out'] = True`. **A timeout is never a pass** — `mode: 'raise'` treats it as a failure,
because "we could not verify this" and "this is safe" are different answers.

---

## 16. Error Conditions

| Condition | Behaviour |
|---|---|
| Device has no `geometry:` config | Excluded from scene. Debug log once. |
| Mesh is empty | Excluded. Info log once. |
| Motion root unresolvable for a plan device | `CollisionError`. We cannot verify a move we cannot simulate. |
| `mapGlobalToDevicePosition` raises (limits, IK) | `CollisionError`, underlying exception chained. |
| Prism below the degeneracy threshold | Skipped (§7.2). Counted in `stats`. |
| Non-translational motion with degenerate radius | Treated as translation; logged. |
| `fcl.distance` returns `-1.0` | Normalized to separation `0.0`, `kind="overlap"`. |
| Blocking contact, `mode: 'raise'` | `CollisionError(report.describe())` carrying `.report`. |
| Blocking contact, `mode: 'warn'` | Warning log; execution proceeds. |

---

## 17. Testing Strategy

Tests are pure-python and hardware-free, building `Body` objects from `trimesh` primitives and
hand-built pose matrices.

**Semantics tests** (`tests/test_semantics.py`) — the §3.4 matrix, and the highest-value tests here:
open-bore pass-through, wall crossing, engulfment, off-path, non-convex notch, non-convex hit,
too-short sweep. A regression in any of these silently inverts the service's answer.

**FCL constraint tests** (`tests/test_engine.py`) — one per §9 constraint:
- Randomized 600-case cross-validation of Convex-vs-BVH and Convex-vs-Convex against an independent
  exact SAT reference, asserting zero disagreement under `GST_LIBCCD`. This is the guard on §9.2 and
  must fail if the solver is changed.
- Assert no `continuousCollide` call appears anywhere in the package (source grep).
- Allocation-churn test asserting bounded RSS growth under the object-pool pattern.

**Sweep tests** (`tests/test_sweep.py`)
- Analytic prism topology matches a QHull-computed hull (vertices, faces, volume) on randomized
  triangles and sweeps.
- Degenerate inputs — flat prism, zero-length sweep, zero-area triangle — return cleanly, no crash.
- Rotational subdivision: a bar rotating 90° about its end. The unsubdivided prism misses a target
  the subdivided sweep catches. Regression guard for §7.3.

**Pose simulation tests** (`tests/test_poses.py`)
- Simulated pose at the current state equals `device.globalPhysicalTransform().full_matrix` to 1e-12
  for every device. Anchors simulation to live state.
- Simulate a move and back; poses return to original.
- 4-axis stage: two axis solutions with the same 3-D offset yield identical poses.

**Interval tests** (`tests/test_intervals.py`)
- `SequentialGroup` threads state: interval *n*'s start poses equal interval *n−1*'s end poses.
- `ParallelGroup` yields one interval with two moving groups.
- Nested `Sequential(Parallel(Sequential(...)))` preserves total segment count.

**End-to-end tests** (`tests/test_checker.py`), building on `acq4/motion/tests/conftest.py`
- Pipette driven through the objective is rejected, naming both devices and the correct interval.
- Same plan routed around it passes.
- Pipette starting in a well and moving out is not a blocking failure.
- Declared `ignore` pair passes.
- `clearance=1*mm` rejects a path `clearance=0` accepts.
- Same-rigid-group pair (well vs microscope) never reported even on a large stage move.
- `@pytest.mark.slow`: representative 6-segment plan completes within budget.

---

## 18. Rejected Alternatives

### 18.1 FCL continuous collision detection

Investigated because a working CCD would replace the entire sweep construction. **Rejected.**

- **Fails open.** Every failure mode surfaces as `is_collide=False, time_of_contact=1.0`,
  indistinguishable from "no collision", often with nothing on stderr. Only the raw `-1.0` return
  reveals it, and the binding discards it.
- **Untested upstream.** FCL ships zero CCD unit tests; none of its 26 test sources reference
  ccd/continuous/conservative/motion.
- **Partly stubbed.** `CCDC_RAY_SHOOTING` is an empty `{}` block falling through to `return -1`.
- **Crashes.** Any `BVHModel` as second operand triggers `STATUS_STACK_OVERFLOW` — uncatchable
  ([fcl#512](https://github.com/flexible-collision-library/fcl/issues/512),
  [python-fcl#10](https://github.com/BerkeleyAutomation/python-fcl/issues/10), open since 2018).
- **Binding incomplete.** No motion classes are exposed, so `CCDM_SPLINE` is constructed from two
  transforms with no control points and reports contact at `t=0.0` for objects 5 units apart.
- **Only `CCDC_NAIVE` + `CCDM_TRANS` is trustworthy — and it is just a sampling loop**
  (`n_iter = min(num_max_iterations, ceil(1/toc_err))`). It tunnels: at the default
  `num_max_iterations=10`, a 0.1-unit body crossing a 10-unit path misses walls up to 1.0 thick.
- **Ecosystem has abandoned it.** `coal` (the maintained hpp-fcl fork) deleted CCD outright; MoveIt's
  request to use FCL CCD ([moveit#29](https://github.com/moveit/moveit/issues/29)) has been open and
  unimplemented for 10 years and they shipped Bullet instead. No CCD-touching commit upstream through
  Feb 2026.

Note the prism sweep is *stronger* than the usual replacement (bounded-step discretization): it is
exact for translation, so there is no step size to choose and no tunneling to bound.

### 18.2 Hand-rolled SAT + BVH (Rev 0.1's design)

Superseded by FCL, which removes roughly half the code. Retained only as the independent reference
implementation used by the §17 cross-validation test — its value is now as an oracle, not an engine.

### 18.3 Convex decomposition of bodies

Every config primitive (box, cone, cylinder) is convex, and the swept volume of a convex body under
translation is `conv(K ∪ (K+d))`, so a pipette's whole sweep would be two convex hulls. **Rejected**:
it is wrong for shells (§3), which is the dominant case here — hulling `RecordingChamber` or
`CleaningWell` fills exactly the free space the pipette must occupy. It also would not extend to
arbitrary non-convex STL without VHACD.

### 18.4 Solid semantics with a `solid:` config flag

Would allow containment testing for genuinely closed bodies. **Deferred**: it requires correctly
classifying every existing geometry, does not survive non-watertight STL, and §3.2's uniform rule
handles every case we currently have. Revisit only if Open Question 9 bites.

---

## 19. Open Questions

Each records the assumption the spec currently encodes, so the document is coherent either way.

1. **Non-linear moves.** `AtomicMove.kwargs['linear']` defaults to `False`, and `Stage.move()` does
   not guarantee a straight path — so the straight-line sweep assumption is **unsound** for a
   non-linear move. Options: (a) accept it; (b) sweep the axis-space AABB of the endpoints — sound
   but much more conservative (a box, not a tube, for a diagonal move); (c) have the checker set
   `linear=True` on every `AtomicMove` it certifies, making the assumption true by construction at
   some cost in move time.
   *Current: (a), with a `TODO` at the sweep site.* **This is the largest remaining soundness gap.**

2. **`ParallelGroup` timing.** Time-free and conservative; crossing paths at different times are
   flagged. Adding time parameterization means modelling speed and acceleration, which the plan does
   not carry. *Current: conservative.*

3. **Where permitted-contact rules live.** Explicit `ignore` config list vs. deriving from existing
   device relationships (`Pipette1.cleaningWell` arguably already declares permission). Deriving is
   less duplication but more magic, and does not cover objective-vs-turret.
   *Current: explicit list plus automatic pre-existing downgrade.*

4. **Sample and boundaries.** No mesh for tissue. Should the swept volume also be verified against
   the `Plane` half-spaces from `getBoundaries()` and the surface plane — cheap, reusing the same
   prism vertices — or is that strictly `checkLimits`' job? *Current: out of scope.*

5. **Failure mode and default.** `enabled: True, mode: 'raise'` means a geometry-config error can
   block all motion until someone edits config; `'warn'` initially would let it bake in.
   *Current: `raise`, on the grounds that a check nobody acts on is not a safety check.*

6. **Clearance granularity.** Per-device, pair taking the max. Cannot express "~0 at the pipette tip,
   millimetres on the shaft", which would need per-region annotation in the geometry config.
   *Current: per-device, with a note that per-region may be needed.*

7. **Materializing the hypermesh.** *Current: on failure only.*

8. **~~python-fcl~~ — RESOLVED.** Adopted. A cp312 win_amd64 wheel exists; installed and added to
   `pyproject.toml`. Constraints in §9 are normative.

9. **Start-state containment blind spot (new).** Per §3.5, a body already entirely inside another
   body's shell at the start state is invisible to surface-crossing semantics. Is that acceptable, or
   should `check_state()` do a one-time solid containment test at startup — where the cost of a
   watertightness check and a slower algorithm is affordable because it runs once, not per move?
   *Current: accepted blind spot, documented, not mitigated.*
