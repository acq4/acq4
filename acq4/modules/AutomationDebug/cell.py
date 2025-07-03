import numpy as np

from acq4.Manager import getManager
from acq4.util import Qt, ptime
from acq4.util.debug import logMsg, printExc
from acq4.util.future import future_wrap, Future
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4_automation.feature_tracking import (
    CameraCellTracker,
    SingleFrameMotionEstimator,
    ObjectStack,
    ImageStack,
)
from coorx import SRT3DTransform, TransposeTransform, TTransform, Point


class Cell(Qt.QObject):
    sigPositionChanged = Qt.pyqtSignal(object)

    def __init__(self, position):
        """Initialize the Cell object.
        Parameters
        ----------
        position : tuple
            The global position of the cell
        imager : Camera
            The camera used for imaging
        """
        super().__init__()
        self.initialPosition = position
        self._positions = {ptime.time(): position}
        self._imager = None
        self._trackingFuture = None
        self._tracker = None

    @property
    def isTracking(self):
        """Check if the cell is currently being tracked."""
        return self._tracker is not None and self._tracker.is_tracking

    @property
    def position(self) -> Point:
        """Get the current global position of the cell."""
        return Point(np.array(self._positions[max(self._positions)]), "global")

    @future_wrap
    def initializeTracker(self, imager, _future=None):
        # Initialize tracker if we have none, or just grab another stack and check if it still matches otherwise
        if self._tracker is None:
            self._imager = imager
            self._tracker = CameraCellTracker(SingleFrameMotionEstimator(), imager)
            self._tracker.initialize_at_position(self.position)
        elif not self.updatePosition(_future):
            raise ValueError("Cell moved too much to treat as tracked")

    def enableTracking(self, enable=True, interval=0):
        """Enable or disable tracking of the cell position.

        Parameters
        ----------
        enable : bool
            If True, tracking is enabled. If False, tracking is disabled.
        interval : int
            The interval in milliseconds at which to check the cell position.
        """
        if enable:
            self._tracker.start_tracking()
            if self._trackingFuture is not None:
                self._trackingFuture.stop("Tracking restarted")
            self._trackingFuture = self._track(interval)
            self._trackingFuture.onFinish(self._handleTrackingFinished)
        else:
            self._tracker.stop_tracking()
            if self._trackingFuture is not None:
                self._trackingFuture.stop("Tracking disabled")
                self._trackingFuture = None

    @future_wrap
    def _track(self, interval: float, _future):
        """Track the cell position at the specified interval."""
        while True:
            last_tracked = max(self._positions)
            if ptime.time() - last_tracked > interval:
                try:
                    self.updatePosition(_future)
                except (_future.StopRequested, self._tracker._motion_estimator.TrackingError):
                    raise
                except _future.Stopped as exc:
                    logMsg(f"Cell tracker exiting: {exc}")
                    return
                except Exception:
                    printExc("Hopefully harmless error in tracking")
            _future.sleep(interval)

    def _handleTrackingFinished(self, future: Future):
        # TODO do we need a mutex
        self._trackingFuture = None
        if not future.wasStopped():
            future.wait()

    def updatePosition(self, _future):
        while self._tracker.position is None:
            _future.sleep(0.1)

        result = self._tracker.track_next_frame()
        global_position = result.position.mapped_to("global")
        self._positions[ptime.time()] = global_position
        self.sigPositionChanged.emit(global_position)
        return result.success
