# Agents Overview

- This file captures agent-specific instructions. Shared project conventions now live in `CONTRIBUTING.md`.
- Machine-specific adjustments can live in an untracked `AGENTS.local.md`; reference it when present.

## Testing

* acq4 uses pytest-style testing; place tests in a `tests/` directory adjacent to the relevant code.

## Project Overview

ACQ4 is a platform for neurophysiology acquisition and analysis, focusing on patch clamp electrophysiology, optogenetics, and related techniques. It provides tools for data acquisition, management, and analysis with features including:

* Semi- and fully-automated patch clamp electrophysiology
* Automated manipulator control
* Pipette cleaning/reuse and multipatch support
* Resistance-based autopatch
* Photostimulation mapping
* Fluorescent indicator imaging
* 2-photon imaging

## Collaboration & Workflow

* Favor small, maintainable changes; avoid redesigning large surfaces.
* Preserve existing comments unless demonstrably incorrect.

## Concurrency — Future and threading primitives

acq4 uses a thread-backed `Future` class (`acq4.util.future`) for async tasks.

**Starting async work:**
```python
from acq4.util.future import Future
fut = Future(fn, (arg1, arg2), name="task name")  # starts thread immediately
result = fut.wait()                                # block and return result
```

**Inside functions that run in a Future:**
```python
from acq4.util.future import sleep, check_stop, Queue, Event, Stopped

sleep(0.5)      # interruptible; raises Stopped if the future is stopped
check_stop()    # raises Stopped immediately if stopped; use in tight loops
q = Queue()     # queue.Queue replacement; q.get() raises Stopped if stopped
ev = Event()    # threading.Event replacement; ev.wait() raises Stopped
```

Do NOT use `time.sleep`, `queue.Queue`, or `threading.Event` inside functions
that run inside a Future — they ignore stop requests and block cancellation.
Use the drop-in replacements above instead.

**Cooperative cancellation:**
- `future.stop()` requests cancellation; it cascades to child futures automatically.
- `sleep()`, `check_stop()`, `Queue.get()`, and `Event.wait()` raise `Stopped` when
  the current future is stopped.
- `Stopped` is caught in `_executeAndSetReturn_v2` and marks the future as stopped.

**Worker threads (queue-based, long-lived):**
Capture `task_stack.get()` at job submission time and restore with
`task_stack.push_full(caller_stack)` in the worker. See `SmartStageControlThread`
and `ScientificaControlThread` for examples.

**Do not use `@future_wrap`** — it has been removed. Use `Future(fn)` directly.

## Shared Guidance

- Workflow, testing, technology, and architecture expectations are detailed in `CONTRIBUTING.md`; follow them unless explicitly directed otherwise.
- Consult `CONTRIBUTING.md` for environment setup, configuration search paths, and common development patterns before improvising.
- Use `AGENTS.local.md` for any local overrides and note deviations in your journal when they occur.
