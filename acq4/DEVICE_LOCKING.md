# ACQ4 device reservation spec

<svg width="100%" viewBox="0 0 680 820" role="img" xmlns="http://www.w3.org/2000/svg">
<title>ACQ4 device reservation spec diagram</title>
<desc>Structural diagram showing the relationships between Manager, ReservationContext, ReservedDevice, Device, and DeviceReservation</desc>
<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
    <path d="M2 1L8 5L2 9" fill="none" stroke="context-stroke" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </marker>
  <style>
    .th { font: 500 14px sans-serif; fill: #3C3489; }
    .ts { font: 400 12px sans-serif; fill: #534AB7; }
    .th-teal { font: 500 14px sans-serif; fill: #085041; }
    .ts-teal { font: 400 12px sans-serif; fill: #0F6E56; }
    .th-gray { font: 500 14px sans-serif; fill: #444441; }
    .ts-gray { font: 400 12px sans-serif; fill: #5F5E5A; }
    .th-coral { font: 500 14px sans-serif; fill: #712B13; }
    .ts-coral { font: 400 12px sans-serif; fill: #993C1D; }
    .th-amber { font: 500 14px sans-serif; fill: #633806; }
    .ts-amber { font: 400 12px sans-serif; fill: #854F0B; }
    .arr { stroke: #888780; stroke-width: 1.5; fill: none; }
    .leader { stroke: #B4B2A9; stroke-width: 0.5; stroke-dasharray: 4 3; fill: none; }
  </style>
</defs>

<!-- Manager -->
<rect x="220" y="30" width="240" height="56" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text class="th" x="340" y="52" text-anchor="middle" dominant-baseline="central">Manager</text>
<text class="ts" x="340" y="70" text-anchor="middle" dominant-baseline="central">reserveDevices(*devices, name, timeout)</text>

<!-- arrow down to ReservationContext -->
<line x1="340" y1="86" x2="340" y2="126" class="arr" marker-end="url(#arrow)"/>
<text class="ts" x="352" y="112" dominant-baseline="central">returns</text>

<!-- ReservationContext -->
<rect x="160" y="126" width="360" height="100" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text class="th-teal" x="340" y="152" text-anchor="middle" dominant-baseline="central">ReservationContext</text>
<text class="ts-teal" x="340" y="172" text-anchor="middle" dominant-baseline="central">__enter__ → tuple of ReservedDevice (input order)</text>
<text class="ts-teal" x="340" y="190" text-anchor="middle" dominant-baseline="central">__exit__ → releases only owned locks</text>
<text class="ts-teal" x="340" y="208" text-anchor="middle" dominant-baseline="central">owned: set[Device]  ·  inherited: set[Device]</text>

<!-- arrow down-left to ReservedDevice (owned) -->
<line x1="270" y1="226" x2="190" y2="286" class="arr" marker-end="url(#arrow)"/>
<text class="ts-teal" x="188" y="264" text-anchor="middle" dominant-baseline="central">acquired</text>

<!-- arrow down-right to ReservedDevice (inherited) -->
<line x1="410" y1="226" x2="490" y2="286" class="arr" marker-end="url(#arrow)"/>
<text class="ts-gray" x="494" y="264" dominant-baseline="central">inherited</text>

<!-- ReservedDevice (owned) -->
<rect x="40" y="286" width="300" height="100" rx="8" fill="#E1F5EE" stroke="#0F6E56" stroke-width="0.5"/>
<text class="th-teal" x="190" y="312" text-anchor="middle" dominant-baseline="central">ReservedDevice (owned)</text>
<text class="ts-teal" x="190" y="332" text-anchor="middle" dominant-baseline="central">pass-through to Device via __getattr__</text>
<text class="ts-teal" x="190" y="350" text-anchor="middle" dominant-baseline="central">holds creation stack + reservation name</text>
<text class="ts-teal" x="190" y="368" text-anchor="middle" dominant-baseline="central">_release() called by ReservationContext</text>

<!-- ReservedDevice (inherited) -->
<rect x="340" y="286" width="300" height="100" rx="8" fill="#F1EFE8" stroke="#888780" stroke-width="0.5"/>
<text class="th-gray" x="490" y="312" text-anchor="middle" dominant-baseline="central">ReservedDevice (inherited)</text>
<text class="ts-gray" x="490" y="332" text-anchor="middle" dominant-baseline="central">same object passed in by caller</text>
<text class="ts-gray" x="490" y="350" text-anchor="middle" dominant-baseline="central">__exit__ does not release it</text>
<text class="ts-gray" x="490" y="368" text-anchor="middle" dominant-baseline="central">caller remains owner</text>

<!-- arrow from ReservedDevice owned down to Device -->
<line x1="190" y1="386" x2="190" y2="446" class="arr" marker-end="url(#arrow)"/>
<text class="ts-coral" x="202" y="418" dominant-baseline="central">wraps</text>

<!-- Device -->
<rect x="40" y="446" width="300" height="100" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text class="th-coral" x="190" y="472" text-anchor="middle" dominant-baseline="central">Device</text>
<text class="ts-coral" x="190" y="492" text-anchor="middle" dominant-baseline="central">normal methods: always allowed</text>
<text class="ts-coral" x="190" y="510" text-anchor="middle" dominant-baseline="central">@state_changing methods: check lock first</text>
<text class="ts-coral" x="190" y="528" text-anchor="middle" dominant-baseline="central">stop(): always allowed, interrupts in-progress</text>

<!-- DeviceReservation -->
<rect x="40" y="590" width="300" height="120" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text class="th-amber" x="190" y="616" text-anchor="middle" dominant-baseline="central">DeviceReservation</text>
<text class="ts-amber" x="190" y="636" text-anchor="middle" dominant-baseline="central">lives on Device, not ReservedDevice</text>
<text class="ts-amber" x="190" y="654" text-anchor="middle" dominant-baseline="central">acquire(name, timeout) → bool</text>
<text class="ts-amber" x="190" y="672" text-anchor="middle" dominant-baseline="central">release()</text>
<text class="ts-amber" x="190" y="690" text-anchor="middle" dominant-baseline="central">state_changing() → context manager</text>

<!-- arrow Device to DeviceReservation -->
<line x1="190" y1="546" x2="190" y2="590" class="arr" marker-end="url(#arrow)"/>
<text class="ts-amber" x="202" y="570" dominant-baseline="central">owns</text>

<!-- state_changing decorator box -->
<rect x="380" y="446" width="260" height="76" rx="8" fill="#FAECE7" stroke="#993C1D" stroke-width="0.5"/>
<text class="th-coral" x="510" y="472" text-anchor="middle" dominant-baseline="central">@state_changing</text>
<text class="ts-coral" x="510" y="492" text-anchor="middle" dominant-baseline="central">decorator on Device methods</text>
<text class="ts-coral" x="510" y="510" text-anchor="middle" dominant-baseline="central">calls lock.state_changing()</text>

<!-- dashed line from decorator to Device -->
<line x1="380" y1="484" x2="340" y2="484" class="leader"/>

<!-- slow state change context manager note -->
<rect x="380" y="554" width="260" height="76" rx="8" fill="#FAEEDA" stroke="#854F0B" stroke-width="0.5"/>
<text class="th-amber" x="510" y="580" text-anchor="middle" dominant-baseline="central">state_changing() as ctx</text>
<text class="ts-amber" x="510" y="600" text-anchor="middle" dominant-baseline="central">blocks new reservations</text>
<text class="ts-amber" x="510" y="618" text-anchor="middle" dominant-baseline="central">while state change in progress</text>

<!-- dashed line from state_changing note to DeviceReservation -->
<line x1="380" y1="592" x2="340" y2="650" class="leader"/>

<!-- Manager global dict note -->
<rect x="380" y="670" width="260" height="76" rx="8" fill="#EEEDFE" stroke="#534AB7" stroke-width="0.5"/>
<text class="th" x="510" y="696" text-anchor="middle" dominant-baseline="central">Manager._reserved_devices</text>
<text class="ts" x="510" y="716" text-anchor="middle" dominant-baseline="central">dict[Device, ReservedDevice]</text>
<text class="ts" x="510" y="734" text-anchor="middle" dominant-baseline="central">source of truth for lock state</text>

<!-- dashed line from manager to registry -->
<line x1="460" y1="86" x2="510" y2="670" class="leader" marker-end="url(#arrow)"/>

</svg>

## `Manager.reserveDevices(*devices, name, timeout)`

Accepts any mix of `Device` and `ReservedDevice` objects. Creates a `ReservationContext`.

- For each `Device` argument: attempts to acquire its `DeviceReservation`, blocking up to `timeout` seconds. Partial failure is total failure — if any device times out, no locks are acquired and `DeviceReservationTimeout` is raised.
- For each `ReservedDevice` argument: passes through unchanged. The outer context remains the owner.
- If the same underlying device appears more than once (e.g. once as `Device` and once as `ReservedDevice`), the `ReservedDevice` wins — treated as inherited.
- If a `Device` is already locked, this will wait for exclusive access for `timeout` seconds, before then raising `DeviceReservationTimeout` with the holder's info.
- This is true even if the lock is held by the caller itself; to avoid this, callers must pass in the `ReservedDevice` they already hold instead of re-locking.

```python
with Manager.reserveDevices(camera, already_reserved_stage, name="z-stack", timeout=5.0) as res_camera, res_stage:
    res_camera.set_exposure(10)
    res_stage.move_to(z=100)
```

## `ReservationContext`

Returned by `reserveDevices`. A context manager.

- `__enter__` returns a tuple of `ReservedDevice` in the same order as the input arguments.
- `__exit__` calls `_release()` only on locks this context *acquired* (not inherited ones).

## `ReservedDevice`

A thin wrapper around a `Device`.

- Delegates all attribute access to the underlying device via `__getattr__`.
- Holds the stack trace captured at `reserveDevices` call time, plus the `name` string.
- `_release()` is nearly private — only `ReservationContext` calls it. (Maybe we should use `__del__` instead of explicit release?)
- `isinstance` checks must be migrated to interface checks alongside this change.

## `Device`

Unchanged externally. Internally:

- Owns a `DeviceReservation` instance.
- State-changing methods are decorated with `@state_changing`, which calls `self._reservation_lock.state_changing()` as a context manager before proceeding.
- `stop()` is always allowed and interrupts any in-progress state change, which must raise an appropriate exception.

## `@state_changing`

Decorator applied to Device methods that mutate state.

```python
def state_changing(method):
    def wrapper(self, *args, **kwargs):
        with self._reservation_lock.state_changing():
            return method(self, *args, **kwargs)
    return wrapper
```

## `DeviceReservation`

Lives on the `Device`, not the `ReservedDevice`. Separates locking mechanics for testability.

- `acquire(name: str, timeout: float) -> bool` — blocks using a `threading.Condition`, returns `False` on timeout.
- `release()` — releases the lock, notifies waiters.
- `state_changing()` — context manager. On enter: raises `DeviceReservedError` (with holder name and traceback) if locked. While inside: blocks new `acquire()` calls until exit. This is the slow-state-change guard.

## `Manager._reserved_devicesregistry`

`dict[Device, ReservedDevice]` — the global source of truth. `reserveDevices` reads and writes this atomically under a manager-level lock.

## Error types

- `DeviceReservationTimeout` — raised by `reserveDevices` when a device can't be acquired in time. Includes: device name, holder's `name` string, holder's creation traceback.
- `DeviceReservedError` — raised by `@state_changing` methods when called on a locked device directly (i.e. not through the `ReservedDevice`). Same info.

## Out of scope

- Cancellation of a waiting `reserveDevices` — timeouts are expected to be small.
- Re-entrancy — callers pass `ReservedDevice` objects down instead of re-locking.
- `isinstance` checks on `ReservedDevice` — we should migrate to interface checks instead.
- Dynamic packing (i.e. constructing the list of devices dynamically) — mostly Tasks, which can be expected to keep track of device order.
