# Panic Lock — Specification

**Status:** Implemented · Rev 1.0 · 2026-08-28

Shipped and tested against mock devices; ESC verified on a live rig. This document now describes code that exists — see [Implementation map](#implementation-map). §12 is the only part that is still forward-looking; nothing there blocks the feature, and it is the reason this file is kept rather than deleted.

---

## Contents

1. [Overview](#1-overview)
2. [Concepts](#2-concepts)
3. [State Model](#3-state-model)
4. [Trigger Paths](#4-trigger-paths)
5. [Halt Fan-Out](#5-halt-fan-out)
6. [Guarded Operations](#6-guarded-operations)
7. [GlobalHaltException](#7-globalhaltexception)
8. [Resume](#8-resume)
9. [User Interface](#9-user-interface)
10. [Class Structure](#10-class-structure)
11. [Error Conditions](#11-error-conditions)
12. [Future Research](#12-future-research)
13. [Testing Strategy](#13-testing-strategy)
14. [Implementation map](#implementation-map)

---

## 1. Overview

The Panic Lock is a rig-wide safety interlock. When triggered, it halts every device capable of motion or energy delivery, then **latches** — refusing all further unsafe commands until a human explicitly resumes.

The existing ESC behaviour (`Manager.sigAbortAll`) is a best-effort broadcast: it asks stages to stop, but nothing prevents the next line of an automation state from immediately commanding a new move. The Panic Lock replaces this with a latched, enforced state.

**Design principle:** panic is not "abort the current operation." It is "the rig is unsafe; nothing moves until a human says so." Every rule below follows from that.

**What this spec covers:**
- Panic state model, trigger paths, and halt fan-out
- Per-device-class guard behaviour and the safe-direction allowlist
- `GlobalHaltException` semantics and propagation
- Resume flow and UI

**What this spec does not cover:**
- Hardware-level emergency stop (E-stop relays, interlocked enclosures)
- Recovery of interrupted experiment data
- Motion planning (see Zone Service Spec, Zone-Based Motion Planner Spec)

---

## 2. Concepts

| Term | Definition |
|---|---|
| **Panic Lock** | The rig-wide halt state, managed by the `GlobalHalt` instance at `Manager.globalHalt`. |
| **Halt fan-out** | The one-shot sweep over all devices that drives each to its safe state at panic time. |
| **Latch** | The persistent HALTED condition that outlives the fan-out and blocks new commands. |
| **Guard** | A check at a device chokepoint that raises `GlobalHaltException` while HALTED. |
| **Safe direction** | An operation that strictly reduces stored energy or risk (venting to atmosphere, closing a shutter). Permitted while HALTED. |
| **Abort callback** | A no-argument callable registered via `add_abort_callback()`, invoked on halt. |
| **Participant** | Anything holding a registered abort callback — a device, a state machine, or any automation system. |

---

## 3. State Model

Two states. No intermediate "halting" state is exposed — `halted` is set *before* the fan-out begins, so there is no window in which a device is halted but not yet guarded.

| State | Meaning |
|---|---|
| `ARMED` | Normal operation. All commands permitted. |
| `HALTED` | Latched. Halt fan-out has been initiated. Unsafe commands raise `GlobalHaltException`. |

**Ordering requirement:** `globalHalt.halt('reason')` sets `halted` first, then runs the fan-out. A device commanded concurrently from another thread must be refused even if its own abort callback has not yet run.

**Repeat halts:** `halt()` while already halted re-runs the fan-out — a second ESC press is a legitimate "I mean it" from the user. `reason` is recorded **only on the ARMED -> HALTED transition**, so the first reason, the one that explains why the rig became unsafe, survives every subsequent halt.

---

## 4. Trigger Paths

| Path | Mechanism |
|---|---|
| ESC key | Application-scoped `QShortcut` (`Manager.py:722-730`), calling `globalHalt.halt("User pressed ESC")` |
| Programmatic | `getManager().globalHalt.halt(reason: str)` |

The ESC shortcut is created with `Qt.Qt.ApplicationShortcut` context, so it fires from any ACQ4 window, but it is created in `showGUI()` and therefore exists only once a GUI is up. A headless session has no panic key; programmatic `halt()` remains available there, which is the only input such a session has anyway.

### 4.1 Input-path robustness

The implementation must:

1. Immediately set the halt state flag, before anything else (§3).
2. Run the abort fan-out on threads, so a hung or slow device cannot delay the fan-out to other devices or freeze the resume dialog.

**Accepted limitation: the trigger depends on the Qt event loop.** An earlier revision required an event-loop-independent trigger — a dedicated watchdog thread holding an OS-level hotkey — so that ESC would still work with the GUI thread wedged. That was dropped deliberately: on Windows it means `RegisterHotKey`, which claims ESC across the entire desktop and breaks it in every other application while ACQ4 runs. The cost to everyday use outweighs the benefit in a failure mode that is already catastrophic.

The consequence is explicit: **if the GUI thread is wedged, ESC does not panic, and the resume dialog (§9.1) cannot be shown or dismissed either.** Recovery from that state is a process restart. Everything below the trigger is unaffected — once `halt()` is called from any source, the latch is set synchronously and the fan-out runs on its own threads, neither of which needs the event loop. See §12 item 3.

---

## 5. Halt Fan-Out

`halt()` invokes every registered abort callback, each on its own task.

Participants register themselves rather than being discovered. A device knows how it must be made safe; the Panic Lock does not need to know that a `Stage` stops differently from a `Laser`. Registration also lets non-device participants — the PatchPipette state machine, the Autopatch orchestrator — take part on the same footing, which duck-typed device discovery could never reach.

### 5.1 Base API

`Manager.globalHalt` is a `GlobalHalt` instance managing panic state:

| Member | Type | Meaning |
|---|---|---|
| `halted` | `bool` (property) | True while the rig is halted. |
| `reason` | `str \| None` | Why the halt was initiated; `None` when armed. |
| `halt(reason)` | method | Initiates the halt state. |
| `resume()` | method | Ends the halt state. |
| `check()` | method | Raises `GlobalHaltException` if halted. Called by device guards. |
| `add_abort_callback(cb, name=None)` | method | Register `cb` to be invoked on halt. |
| `remove_abort_callback(cb)` | method | Unregister `cb`. |


Devices are required to call `globalHalt.check()` before initiating an unsafe operation (any physical movement other than de-energising a motor, any change in pressure other than to equilibrium, any opening or energizing of a laser, any motion of scan mirrors other than to their virtual shutter position, etc.). `globalHalt.check()` performs the test and raises `GlobalHaltException` (§7), so guards need not repeat it.

`globalHalt.halt(reason)` initiates this state by:
- setting `halted` — and, only when entering the halt state, `reason` — synchronously and before anything else
- Starting fan-out to ask all callbacks to abort current operations
- Displaying UI to allow the user to resume, raised and activated (§9.1)


### 5.2 Per-class behaviour

As a matter of convention / consistency, devices that participate should implement abort() and register that method as a globalHalt callback.

| Participant | Registered callback does |
|---|---|
| `Stage` (incl. `DoverStage`, `Scientifica`, `SutterMP285`, `MockStage`) | `self.stop(reason=...)`; fail any in-flight `MoveFuture` with `GlobalHaltException`. Implemented as `Stage.abortForHalt()`, **not** `abort()`: `MockStage`, `MicroManagerStage` and `Scientifica` already override `abort()` to mean "hard stop" and their `stop()` calls it, so putting the fail there would recurse and would also fail futures with `GlobalHaltException` on a routine cooperative stop. Registered under the name `f"{name}.abort"`. |
| `Pipette` | No action -- delegated to parent stage |
| `PressureControl` | `setPressure(source='atmosphere', pressure=0)` |
| `Laser` | `closeShutter()`, `closeQSwitch()`, power to zero. "Power" means the Pockels cell drive (`setChanHolding('pCell', 0)`) — the only settable power control the class has. The `power` DAQ channel is virtual (widget-building only) and lasers such as the Coherent have no software setpoint at all, so on a shutter-only laser the closed shutter *is* the safe state. |
| `LightSource` | No action -- lights assumed to be safe |
| `Scanner` | Abort any scan in progress; close the virtual shutter if available |
| `PatchClamp` | Stop any running tasks, leave mode+holding unchanged |
| `FilterWheel` | `stop()`, failing any in-flight move future — preserves today's `sigAbortAll` behaviour (`filterwheel.py:100`) |
| `Camera`, `StreamDock`, etc. | Nothing — registers no callback |
| `PatchPipetteStateManager` | Stop the running state job |
| `Imager` (module) | `abortTask()`: close the laser shutter and abort the imaging thread (`Imager.py:449`) |
| `Manager` | `Task.abort()` on every task in progress, each started on its own task. The Manager is one callback aborting many tasks, so §5.3's isolation has to be repeated inside it: neither a driver that hangs while stopping nor a task blocked in `Task.execute()` may starve the rest. `Task.execute()` holds `taskLock` for setup and start only, never across its wait loop -- `Task.stop()` takes the same lock, and the abort always arrives on a different thread, so a blocking task holding it for the whole run could not be aborted at all. |

### 5.3 Fault tolerance

The fan-out is **best-effort and exhaustive**. A callback that raises or hangs must not prevent any other participant from being aborted. Each callback runs on its own task, so neither a raised exception nor a blocking driver call can stall the sweep.

`_fanOut()` is fire-and-forget: it starts one task per callback and returns immediately. Nothing is collected and nothing is waited on — each task reports its own failure as it exits.

```python
from acq4.util.task import asynch

def _fanOut(self):
    """Start an abort task for every registered callback. Returns immediately."""
    callbacks = list(self._abortCallbacks)   # snapshot: a callback may register or remove
    for name, cb in callbacks:
        asynch(
            cb,
            name=f"abort({name})",
            detach=True,
            raise_errors="{name} failed: {error}",
        )()
```

Two `asynch` options carry the whole implementation:

- **`detach=True`** — without it each abort becomes a child of whatever task called `halt()`, and a stop cascading from that parent would kill the aborts themselves.
- **`raise_errors=...`** — the task surfaces its own failure through the process's unhandled-exception hook, so no completion callback, collection, or progress signal is needed. The registered `name` labels the task, so the message identifies the participant. `Stopped` is deliberately exempt (`_raise_errors_impl`), so a stopped abort is not reported as a failure — but `GlobalHaltException` is **not** a `Stopped` (§7), so an abort callback that trips its own guard is reported loudly rather than swallowed. That is what makes the §6.3 contract enforceable at runtime and not only in a test.

A callback that never finishes is simply never reported. There is no timeout: a driver blocked in a synchronous RPC cannot be interrupted, so a deadline would only produce a report, not a safer rig.

---

## 6. Guarded Operations

While HALTED, guarded methods raise `GlobalHaltException` **before** touching hardware.

### 6.1 Safe direction

The guard is directional. Panic itself sets pressure to atmosphere and closes shutters, and state `_cleanup()` handlers do the same on their way out — those must keep working. The rule: **an operation is permitted while HALTED if and only if it strictly reduces risk.**

| Device | Operation | While HALTED |
|---|---|---|
| `Stage` | `move()`, `moveToGlobalNoPlanning()`, `movePath()`, `step()`, `setVelocity()` | **Raise** |
| `Stage` | `stop()` | Allowed |
| `Stage` | Failing an in-flight `MoveFuture` | Allowed |
| `PressureControl` | `setPressure(source='atmosphere')`, with or without `pressure=0` | Allowed |
| `PressureControl` | `setPressure(source='regulator'\|'user')`, `rampPressure()` | **Raise** |
| `PressureControl` | `setPressure(pressure=...)` with non-atmosphere source active | **Raise** |
| `Laser` | `openShutter()`, `openQSwitch()`, `setChanHolding('shutter'\|'qSwitch', >0)` | **Raise** |
| `Laser` | `closeShutter()`, `closeQSwitch()`, set power to zero | Allowed |
| `Scanner` | Starting any new scan | **Raise** |
| `Scanner` | Aborting a scan in progress; closing the virtual shutter | Allowed |
| `MotionPlanner` | `execute()` | **Refuse** before reserving devices. Note this is *not* a synchronous raise: `execute()` is decorated `@asynch_with_qt_signals`, so the guard runs inside the task body and the refusal is delivered by **failing the returned task**. Callers must `wait()` on it or connect a completion handler race-free (§9.2); an `except GlobalHaltException:` around the call itself will never fire. |
| `PatchClamp` | Stop a running task | Allowed |
| `PatchPipetteStateManager` | Stopping the running state job | Allowed |
| `PatchPipetteStateManager` | Starting a new state other than `out` | **Raise** |
| `FilterWheel` | `stop()` | Allowed |
| `FilterWheel` | Starting a new filter move | **Raise** |
| `Manager` | `runTask()`, `Task.execute()` | **Raise** |
| `Manager` | `Task.abort()`, `Task.stop()` | Allowed |

### 6.2 Placement

Guards go at the **lowest common chokepoint** so no caller can route around them:

- `Stage.move()` (`Stage.py:375`) — the single funnel for `moveToGlobalNoPlanning`, `step`, and `MovePathFuture` steps. Guarding here covers every stage subclass and `Pipette` without per-driver work.
- `PressureControl.setPressure()` (`PressureControl/device.py:77`) — funnel for `setSource` and `rampPressure`.
- `Laser.setChanHolding()` — funnel for shutter and Q-switch.
- `MotionPlanner.execute()` (`planner.py:51`) — fails a plan before device reservation, so panic never contends for locks.

A guard at `Stage.move()` is what makes panic "circumvent all other motion planning": the refusal happens below the planner, so no plan, waypoint, or retry can reach hardware.

### 6.3 Bypass for the halt path

Abort callbacks run *after* `globalHalt` is set and could trip their own guards.
These must somehow ensure their action will not be blocked, even if guards are later added at a lower level. The key here is that certain actions (stop, close shutter, etc) are allowed during a halted state, and abort callbacks only request these actions.

This makes §6.1 a contract rather than a description: **every action in the §5.2 table must appear as Allowed in §6.1.** Adding a guard that blocks one of them silently breaks the halt path — the abort callback would raise `GlobalHaltException` against itself, and the device would never be made safe. Two things keep that from being silent: `GlobalHaltException` is not a `Stopped`, so the fan-out's `raise_errors` reports the self-inflicted raise instead of swallowing it (§5.3), and a test enforces the pairing statically (§13).

A thread-local bypass flag was considered and **rejected**: it would be inherited by anything the halt path calls, including automation code, silently reopening the hole the guards exist to close.

---

## 7. GlobalHaltException

```python
class GlobalHaltException(Exception):
    """Raised by globalHalt.check() when an unsafe operation is attempted while halted."""
```

It derives from `Exception`, **not** `Stopped`. A halt is not a routine cancellation, and the machinery around `Stopped` is built to treat cancellation as an expected, absorbable outcome — exactly the wrong disposition for a safety latch.

### 7.1 Consequences

- `except Stopped` sites do **not** catch it. It propagates past handlers written for ordinary cancellation, which is correct — those handlers assume the operation may be retried or cleaned up normally.
- The task machinery treats it as a genuine failure rather than an expected outcome. `Task.stop()` swallows a child's `Stopped` as "that is what we asked for" (`gentletask.py:879`) and `MultiTask` collapses all-`Stopped` children into a single `Stopped` (`gentletask.py:1406`); neither absorbs a `GlobalHaltException`.
- `raise_errors` reports it (`_raise_errors_impl` exempts `Stopped` only), so a halt that fails inside the fan-out is visible (§5.3).
- `except Exception` sites catch it. Acceptable: the latch still holds, so the next guarded call raises again.
- No special thread-boundary handling is needed; an ordinary exception propagates through `asynch`, `producerThread`, and the task wrappers.
- A retry loop that catches broadly and retries will spin against `check()` rather than proceeding. It cannot reach hardware, but it will not exit cleanly either (§12 item 1).

## 8. Resume

`globalHalt.resume()` clears the halt state and returns to ARMED.

**Only an explicit human action resumes.** No timeout, no automatic clear on the next user-initiated move, no programmatic `resume()` from automation code. A latch that clears itself is not a latch.

Devices are **not** restored to their pre-panic state — shutters stay closed, pressure stays at atmosphere, no move is resumed. Automation must re-establish whatever it needs, and the operator must consciously re-enable each energy source.

```python
def resume(self) -> None:
    """Clear the panic latch. Must be called from the GUI thread by explicit user action."""
```

---

## 9. User Interface

### 9.1 Panic dialog

Shown on the GUI thread after the abort callbacks have been invoked. Because `_fanOut()` is fire-and-forget (§5.3), "after invoking" means after every abort task has been *started*, not after it finishes — so a hung or slow device cannot delay the dialog.

The dialog is shown, raised, and activated on **every** `halt()` call, including a repeat halt that changes no state. A second ESC press means "I mean it" (§3), and the operator must see the rig respond to it — so this cannot ride on `sigPanicStateChanged`, which fires only on a real transition. `GlobalHalt` emits a separate `sigHaltRequested` on every `halt()` for exactly this purpose.

Contents:

- Headline: **"ALL DEVICES HALTED"**
- `globalHalt.reason`
- Button: **Resume**

The dialog is modeless with respect to the event loop and must be shown, **raised**, and **activated**, so it takes focus even when another window was in front.
The dialog window is not closeable except by clicking Resume.

ESC must **not** dismiss this dialog — ESC is the panic key, and a second press means "panic again," not "close this."


### 9.2 Controls that latch pending a move

A control that optimistically shows a requested state and waits on the move to
reconcile must release itself on **every** outcome, including the ones that never
produce a running task. There are three, and the second is the one that shipped
broken:

1. The call raises synchronously (`Stage.move()` and the other undecorated
   chokepoints).
2. The call returns a task that is **already finished**. This is the normal path
   for anything routed through `MotionPlanner.execute()`: the guard runs inside
   the decorated body, so the task is failed before the caller can connect, and
   `sigFinished` has already been emitted. Connecting afterwards can never fire.
   `Manager.move()`'s inline branch converts a raise into an already-failed task
   for the same reason.
3. The task finishes later, successfully or not (`sigFinished` fires on both).

The safe shape is therefore: guard the call in `try/except`, connect the handler,
**then check `is_done` and call the handler directly if so** -- with an idempotent
handler, so the doubled call when the signal also fires is harmless.

`ZPositionWidget` (the Camera module's depth gauge) is the worked example; it
latches its target line via `setMovingToTarget()`. See §12 item 7 for the sweep of
other controls that may share the pattern.

## 10. Class Structure

Panic state is owned by a `GlobalHalt` instance reachable as `Manager.globalHalt`, so any code holding a Manager reference can test it without an extra lookup.

```python
class GlobalHalt(Qt.QObject):
    sigPanicStateChanged = Qt.Signal(object)     # reason str, or None on resume; only on a real transition
    sigHaltRequested = Qt.Signal()               # every halt(), including repeats -- drives the dialog (§9.1)

    @property
    def halted(self) -> bool: ...
    @property
    def reason(self) -> str | None: ...

    def halt(self, reason: str = "User pressed ESC") -> None:
        """Initiate the halt state, invoke every registered abort callback, then show the dialog.

        *reason* is recorded only when this call transitions ARMED -> HALTED; a
        repeat halt re-runs the fan-out and leaves the original reason intact (§3).
        Emits sigHaltRequested every time and sigPanicStateChanged only on a
        real transition (§9.1).
        """

    def resume(self) -> None:
        """End the halt state. GUI thread, explicit user action only (§8)."""

    def check(self) -> None:
        """Raise GlobalHaltException if halted. Called by device guards."""

    def add_abort_callback(self, cb: Callable[[], None], name: str = None) -> None:
        """Register cb to be invoked on halt. Idempotent.

        *name* labels the task and its failure messages; it defaults to a name
        derived from cb. Registering while halted does NOT invoke cb -- a
        participant created during a halt is already subject to the guards.
        """

    def remove_abort_callback(self, cb: Callable[[], None]) -> None:
        """Unregister cb. Silent if not registered."""
```

### 10.1 Callback lifetime

Registration takes a **strong reference**, so participants must unregister. Two lifetimes:

- **Devices** register in `__init__` and unregister in `quit()`. Effectively permanent; the strong reference is harmless because the Manager outlives them.
- **Transient participants** — a `PatchPipetteState` job, an Autopatch run — register when they start and unregister when they finish. States fail to `out` and the state manager refuses to start a new state while `globalHalt.halted` is True.

  Unregistration is the participant's own responsibility on **every** exit path, including death by unhandled `GlobalHaltException`. Not all of these jobs can be wrapped in a single `try:/finally:`, so this cannot be delegated to one guaranteed unwind point: a job that dies must take itself out of the registry, and code added to these paths has to be written without the safety of a `finally:`. A stale callback is not itself a hazard — it aborts an already-dead job — but it holds a strong reference alive and produces a spurious failure report on the next halt.

The registry is read during `halt()` and written from device construction (GUI thread) and from state jobs (worker threads). No mutex: `list.append` and `list.remove` are atomic, and `_fanOut()` copies the list before iterating, so a concurrent registration is either included in the sweep or not — it cannot corrupt one in progress.

`halted` and `reason` are read from every device thread and written by `halt()`/`resume()`; the implementation must make both safe to read without a lock (a single `reason` attribute, with `halted` derived from it, achieves this — no torn read is possible between the two).

`Manager.sigAbortAll` is **removed**, not deprecated. Two reasons survive the decision to drop the watchdog trigger (§4.1). First, a Qt signal runs its receivers on the emitting thread or queues them on the GUI thread, so one slow or hung device delays every device behind it; the registered-callback fan-out gives each participant its own thread (§5.3). Second, a signal can only reach QObjects, whereas registration lets non-device participants — the PatchPipette state machine, the Autopatch orchestrator — take part on the same footing (§5).

Every current receiver becomes a registered abort callback instead — including `FilterWheel` and the `Imager` module, which are easy to lose in the translation; see the §5.2 table.

`GlobalHaltException` and `GlobalHalt` both live in `acq4/panic.py`. The live instance is owned by the Manager as `Manager.globalHalt`.

---

## 11. Error Conditions

| Condition | Behaviour |
|---|---|
| Guarded operation attempted while HALTED | `GlobalHaltException` with the panic reason |
| Callback raises | Surfaced by the task's own `raise_errors`; other participants unaffected |
| Callback never returns | No timeout; never reported; other participants unaffected |
| Callback registered twice | Second registration is a no-op |
| Callback removed during fan-out | Runs anyway if already snapshotted; never runs on a later halt |
| `resume()` called while ARMED | No-op |
| `halt()` while halted | Re-runs fan-out; original `reason` retained; dialog re-raised and re-activated (§9.1) |
| `halt()` with the GUI thread wedged | Latch and fan-out still work; ESC does not fire and the dialog cannot appear (§4.1) |



## 12. Future Research

None of the following blocks the Panic Lock. They are items worth looking into once it is in place.

1. **Audit `try:/except` blocks that continue a loop on error.** Each needs an explicit exit path for both cancellation and halt: an `except Stopped` that breaks the loop gracefully rather than continuing, and a broad `except Exception` that does not swallow `GlobalHaltException` into a retry — such a loop cannot reach hardware, but it spins instead of unwinding (§7.1).

2. **Push halt checks deeper than `Stage.move()`.** The `Stage.move()` guard covers `moveToGlobalNoPlanning()`, `step()`, and `MovePathFuture` steps, but `move()` is not the only route to hardware. `Scientifica`'s axis auto-zero calls `self.dev._move(...)` directly (`scientifica.py:533`), below the guard. `Stage.setVelocity()` is listed as **Raise** in §6.1 but is currently a stub (`Stage.py:521`) with no chokepoint of its own. Audit for other direct `_move()` and driver-level motion calls, and decide whether the guard belongs in `_move()` — or in each driver's motion entry point — rather than, or in addition to, `move()`. Pushing it down is not free: the halt path must stay clear of its own guards, so any deeper placement has to be re-checked against the §6.3 contract.

3. **Revisit an event-loop-independent panic trigger.** §4.1 accepts that ESC does not work with the GUI thread wedged, because the Windows options are unattractive: `RegisterHotKey` claims ESC desktop-wide, and a `WH_KEYBOARD_LL` hook needs its own message pump and is often flagged by security software. Worth re-examining if wedged-GUI incidents actually occur — a focus-gated global hotkey (act only when an ACQ4 window is foreground) would keep the benefit without breaking ESC elsewhere, at the cost of a foreground check that must not itself touch the event loop. A hardware E-stop is out of scope for this spec (§1) but is the real answer to this class of failure.

4. **Implement `DeviceTask.stop(abort=True)` where it matters.** The base implementation is a no-op (`Device.py:293-299`), so a device that never overrode it will not actually stop when the Manager aborts its task — the halt would appear to succeed while hardware keeps running. Audit each `DeviceTask` subclass and implement or explicitly document the no-op as correct.

5. **Distinguish abort from failure on the Dover path.** `_stop()` and `_check_move_status()` both call `SmartStageRequestFuture.fail(<string>)` (`control_thread.py:188-194`), so the local side cannot tell a deliberate halt from a hardware alert — `DoverMoveFuture._future_finished` turns both into `RuntimeError`. Add an `aborted` flag so a halt surfaces as `GlobalHaltException`. Each `._get_value()` on the teleprox proxy is a blocking RPC round trip; return `(error, aborted, exc_info)` from a single remote call rather than three.

6. **Drain the Dover control-thread queue on stop.** `_handle_stop` should fail any queued move requests, not just the in-flight one (`control_thread.py:85-94`). The `Stage.move()` guard makes this mostly moot, but a queued move that survives a panic is worth closing off. Check that Scientifica and Sensapex have similar behaviors.

7. **Audit UI controls that latch pending a move.** Found on a live rig: the Camera module's depth gauge (`ZPositionWidget`) pins its target line while a move is in flight and releases it when the move future finishes. A move refused *synchronously* by a guard never produces a future, so the line stayed where the operator dragged it — advertising a focus depth the stage was not at and would never reach. Fixed for that widget (`setMovingToTarget(False)` now snaps the line back, and `ScopeCameraModInterface.focusChangedFromWidget` releases the latch on every non-future path). The shape is general: any control that optimistically shows a requested state and waits on completion to reconcile will stick when the request is refused before it starts. Sweep the other target/position widgets for the same pattern.

8. **Audit state `_cleanup()` paths.** Handlers that call `pip.goHome()` or similar will now raise. Verify `log_and_ignore_exception` wrappers do not mask a genuine cleanup failure, and that cleanup restricted to safe-direction operations still completes.

   A second confirmed case: `DAQGenericTask.stop()` restores each channel's remembered holding level (`DAQGeneric.py:409`). `Manager.abortAllTasks()` -> `Task.abort()` -> `Task.stop(abort=True)` therefore attempts an energising write for a laser channel whose remembered holding is an *open* shutter, which the `setChanHolding()` guard refuses. Refusing is the correct behaviour, and it is contained -- `Task.stop()` wraps each device stop in `try/except` and logs -- so `abortAllTasks` still completes. The open question is the same one: what *should* a task teardown restore when it is not allowed to energise anything?

   One confirmed case: `NucleusCollectState._cleanup()` calls `pip.dm.move(...)` (`states/nucleus_collect.py:90`), a **Raise** operation under the `Stage.move()` guard. It cannot break the halt path — it is inside `log_and_ignore_exception`, and `jobFinished` wraps cleanup in `except Exception` — so the §6.3 contract holds at the callback boundary. The consequence is narrower and still real: after a panic during nucleus collection, the pipette is not retracted. Motion during cleanup is exactly what the latch is meant to prevent, so the fix is not to exempt it; it is to decide what a nucleus-collect cleanup should do when it is not allowed to move.

---

## 13. Testing Strategy

Tests live in `acq4/tests/test_panic_lock.py`, using mock devices — no hardware.

### State model
- `halt()` → `halted` True; `resume()` → False; signals emitted once each.
- `halt()` while halted re-runs fan-out and retains the original `reason`.
- `sigHaltRequested` fires on every `halt()`, including repeats; `sigPanicStateChanged` fires only on a real transition.
- `resume()` while ARMED is a no-op.

### Latch ordering
- A device commanded from another thread between `halt()` and the end of the fan-out is refused. Assert `halted` is observable before the first callback runs.

### Fan-out
- Every registered callback is invoked exactly once per `halt()`.
- A removed callback is not invoked on a subsequent `halt()`.
- Registering or removing from inside a callback does not disturb the running fan-out (snapshot semantics).
- A callback that raises does not prevent others from running; the failure is surfaced by `raise_errors`.
- A callback that hangs never reports, but every other callback still completes; `_fanOut()` itself returns without blocking.
- The panic dialog appears after the abort tasks are started, and a hung callback does not delay it.
- A repeat `halt()` re-raises and re-activates the dialog even though no state change occurred.

### Guards
- Each row of the §6.1 table: blocked operations raise, safe-direction operations succeed.
- `Stage.move()` raises before any driver call (assert the mock driver was never touched).
- `MotionPlanner.execute()` fails the returned task before reserving devices, and does **not** raise synchronously — assert both, since the caller-visible difference is what §9.2 exists for.
- Every abort callback in §5.2 completes successfully with `globalHalt` set — no callback trips a guard.
- Contract check: each action named in §5.2 is Allowed in §6.1, so a newly added guard cannot silently block the halt path.

### Exception propagation
- `GlobalHaltException` is **not** a `Stopped`: `except Stopped` does not catch it, `Task.stop()` does not absorb it, and `MultiTask` does not collapse it into a stop.
- It propagates out of `asynch`, `producerThread`, and nested task boundaries as an ordinary exception.
- An abort callback that raises `GlobalHaltException` is reported by the fan-out's `raise_errors` rather than swallowed — a §6.3 violation is detectable at runtime, not only by the contract test below.
- `finally` blocks and context managers run during unwind; device locks are released.
- **Swallowing it does not defeat the halt**: a handler that catches and continues hits `check()` on the next guarded call and raises again. Assert the hardware was never commanded.

### Integration
- A running `CleanState` panicked mid-move terminates and does not advance to the rinse stage or `nextState`.
- A panic between plan steps of a `SequentialGroup` prevents the next step from starting.
- Regression for the reported incident: panic during a move-to-clean halts the Dover stage and no further motion is commanded.

---

## Implementation map

| Spec | Code |
|---|---|
| §7 `GlobalHaltException`, §10 `GlobalHalt` | `acq4/panic.py` |
| §10 `Manager.globalHalt`; §5.2 Manager callback | `acq4/Manager.py` (`abortAllTasks`, `_tasksInProgress`) |
| §4 ESC trigger | `Manager.showGUI()` — application-scoped `QShortcut` |
| §5.2 participants (9) | `Stage.abortForHalt`, `FilterWheel.abort`, `Laser.abort`, `PressureControl.abort`, `Scanner.abort`, `PatchClamp.abort`, `PatchPipetteStateManager.abort`, `Imager.abortTask`, `Manager.abortAllTasks` |
| §6.2 guards (13 call sites) | `Stage.move`/`setVelocity`, `PressureControl.setPressure`/`rampPressure`, `Laser.setChanHolding`, `Scanner.setShutterOpen`/`_setVoltage`/`ScannerTask.configure`, `FilterWheel.setPosition`, `MotionPlanner.execute`, `Manager.runTask`/`Task.execute`, `PatchPipetteStateManager._configureState` |
| §9 dialog | `acq4/util/PanicDialog.py` (`PanicDialog`, `PanicDialogController`) |
| §13 tests | `acq4/tests/test_panic_lock.py`, `test_panic_lock_guards.py`, `test_panic_lock_integration.py`, `test_panic_lock_zwidget.py` |

### Pre-existing bugs found and fixed on the way

These were not Panic Lock defects; the work surfaced them.

- `MovePathFuture._movePath()` resolved the path promise as **success** when a step failed — both when `dev.move()` raised synchronously, and when a step future failed while the loop was blocked in its 0.1 s poll. Either way the caller was told a path completed when it had not.
- `MultiClamp.quit()` and `MockClamp.quit()` bypassed `PatchClamp.quit()` entirely; `FalconTurret.quit()` did not chain to `FilterWheel.quit()`.

### Known gaps at ship

- No hardware in the automated tests — all mocks. ESC-to-halt was exercised manually on a live rig.
- `§12 item 2`: `Scientifica`'s auto-zero calls `_move()` directly, below the `Stage.move()` guard.
- `§12 item 8`: two teardown paths (`NucleusCollectState._cleanup`, `DAQGenericTask.stop`) attempt operations the guards refuse. Contained, logged, and understood — but a panic during nucleus collection leaves the pipette unretracted.
