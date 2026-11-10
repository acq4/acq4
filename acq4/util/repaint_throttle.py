"""Rate-limited repainting that keeps only the newest pending request."""

import math
import time

from acq4.logging_config import get_logger
from acq4.util import Qt

logger = get_logger(__name__)


class RepaintThrottle(Qt.QObject):
    """Calls fn(*args) with the newest submitted args, at most maxRate times per second.

    GUI thread only. A submission after an idle period paints on the next event-loop pass;
    submissions arriving sooner are merged into one paint at the end of the interval.
    An exception from fn is logged once until the next cancel().
    """

    def __init__(self, fn, maxRate=20.0, parent=None):
        Qt.QObject.__init__(self, parent)
        self._fn = fn
        self._minInterval = 1.0 / maxRate
        self._pending = None
        self._lastPaint = -math.inf
        self._failureLogged = False
        self._timer = Qt.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.Qt.PreciseTimer)
        self._timer.timeout.connect(self._paint)

    def submit(self, *args):
        """Replace any pending repaint with fn(*args) and schedule it."""
        self._pending = args
        if not self._timer.isActive():
            wait = max(0.0, self._lastPaint + self._minInterval - time.perf_counter())
            self._timer.start(int(math.ceil(wait * 1000)))

    def cancel(self):
        """Drop the pending repaint, if any, and re-arm failure logging."""
        self._pending = None
        self._timer.stop()
        self._failureLogged = False

    def isPending(self):
        return self._pending is not None

    def _paint(self):
        args, self._pending = self._pending, None
        if args is None:
            return
        self._lastPaint = time.perf_counter()
        try:
            self._fn(*args)
        except Exception:
            if not self._failureLogged:
                self._failureLogged = True
                logger.exception(f"Error in repaint {self._fn!r}")
