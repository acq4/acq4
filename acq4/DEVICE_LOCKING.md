# ACQ4 device reservation spec

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
