"""Per-thread bound on how long run_in_gui_thread waits for the GUI thread.

Kept free of Qt imports so callers can set a limit without loading the GUI stack.
"""

import contextlib
import threading
from typing import Optional

_state = threading.local()


def current_limit() -> Optional[float]:
    """Return this thread's wait limit in seconds, or None for no limit."""
    return getattr(_state, "limit", None)


@contextlib.contextmanager
def gui_wait_limit(seconds: Optional[float]):
    """Bound, on this thread, how long run_in_gui_thread waits for the GUI thread.

    On expiry run_in_gui_thread raises TimeoutError and the abandoned call is skipped.
    None means wait indefinitely.
    """
    previous = current_limit()
    _state.limit = seconds
    try:
        yield
    finally:
        _state.limit = previous
