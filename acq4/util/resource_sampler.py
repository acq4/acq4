"""System resource sampling, run outside the ACQ4 process by resource_monitor.

psutil.virtual_memory() costs ~68 ms per call and holds the GIL, so sampling it
once a second inside ACQ4 stalls every thread ~7% of wall time. CPU and memory
are machine-wide, so a teleprox child reads them here and ACQ4 does a cheap
latest() round trip instead.

Imports nothing from acq4, to keep the child small.
"""

import threading
import time

import psutil

DEFAULT_INTERVAL = 1.0

_lock = threading.Lock()
_thread = None
_stop = threading.Event()
_latest = {"cpu_percent": None, "memory_percent": None, "sampled_at": None}


def sample_now():
    """Take one system sample. Slow; see module docstring."""
    try:
        cpu = psutil.cpu_percent(interval=None)
    except Exception:
        cpu = None
    try:
        memory = psutil.virtual_memory().percent
    except Exception:
        memory = None
    return {"cpu_percent": cpu, "memory_percent": memory, "sampled_at": time.time()}


def _loop(interval):
    # cpu_percent is a delta since its previous call; prime it so the first
    # reported reading is not 0.0
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass
    while not _stop.is_set():
        sample = sample_now()
        with _lock:
            _latest.update(sample)
        _stop.wait(interval)


def start(interval=DEFAULT_INTERVAL):
    """Begin sampling in a background thread. Idempotent."""
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return True
        _stop.clear()
        _thread = threading.Thread(
            target=_loop, args=(interval,), name="resource_sampler", daemon=True
        )
        _thread.start()
    return True


def stop():
    """Stop the sampling thread."""
    global _thread
    _stop.set()
    t = _thread
    if t is not None:
        t.join(timeout=5.0)
    _thread = None
    return True


def latest():
    """Return the most recent sample, plus its age in seconds.

    age is None until the first sample lands, distinguishing "not started yet"
    from "stale".
    """
    with _lock:
        out = dict(_latest)
    at = out.get("sampled_at")
    out["age"] = None if at is None else time.time() - at
    return out
