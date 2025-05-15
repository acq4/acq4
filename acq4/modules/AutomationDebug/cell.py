import numpy as np

from acq4.util import Qt, ptime
from acq4.util.debug import printExc
from acq4.util.future import future_wrap, Future
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4_automation.feature_tracking import CV2MostFlowAgreementTracker, ObjectStack, ImageStack
from coorx import SRT3DTransform, TransposeTransform, TTransform


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
        self.isTracking = False
        self._tracker = None
        self._roiSize = None

    @property
    def position(self):
        """Get the current position of the cell."""
        return self._positions[max(self._positions)]

    @future_wrap
    def initializeTracker(self, imager, stack=None, trackerClass=CV2MostFlowAgreementTracker, _future=None):
        self._imager = imager
        self._tracker = trackerClass()
        stack, xform, center = _future.waitFor(self._takeStackshot(stack)).getResult()
        obj_stack = ObjectStack(stack, xform, center)
        self._tracker.set_tracked_object(obj_stack)
        if stack is not None and not self.updatePosition(_future):
            raise RuntimeError("Cell moved too much to treat as tracked")

    def enableTracking(self, enable=True, interval=0):
        """Enable or disable tracking of the cell position.

        Parameters
        ----------
        enable : bool
            If True, tracking is enabled. If False, tracking is disabled.
        interval : int
            The interval in milliseconds at which to check the cell position.
        """
        self.isTracking = enable
        if enable:
            if self._trackingFuture is not None:
                self._trackingFuture.stop("Tracking restarted")
            self._roiSize = None
            self._trackingFuture = self._track(interval)
            self._trackingFuture.onFinish(self._handleTrackingFinished)
        elif self._trackingFuture is not None:
            self._trackingFuture.stop("Tracking disabled")
            self._trackingFuture = None

    @future_wrap
    def _track(self, interval: float, _future):
        """Track the cell position at the specified interval."""
        last_tracked = max(self._positions)
        while True:
            if ptime.time() - last_tracked > interval:
                try:
                    self.updatePosition(_future)
                except _future.StopRequested:
                    raise
                except Exception:
                    printExc("Error in tracking")
            _future.sleep(interval)

    def _handleTrackingFinished(self, future: Future):
        # TODO do we need a mutex
        self._trackingFuture = None
        self.isTracking = False
        if not future.wasStopped():
            future.wait()

    def updatePosition(self, _future):
        while len(self._tracker.object_stacks) == 0:
            _future.sleep(0.1)
        stack, xform, _ = _future.waitFor(self._takeStackshot()).getResult()
        img_stack = ImageStack(stack, xform)
        result = self._tracker.next_frame(img_stack)
        global_position = result["position"].mapped_to("global")
        self._positions[ptime.time()] = global_position
        self.sigPositionChanged.emit(global_position)
        return result["match_success"]

    @future_wrap
    def _takeStackshot(self, stack=None, _future=None):
        target = np.array(self.position)
        margin = 20e-6
        start_glob = target - margin
        stop_glob = target + margin
        if stack:
            direction = np.sign(stack[0].globalCenterPosition()[2] - stack[-1].globalCenterPosition()[2])
        else:
            current_focus = self._imager.globalCenterPosition()
            direction = np.sign(current_focus[2] - target[2])
        if direction > 0:
            start_glob, stop_glob = stop_glob, start_glob
        if stack is None:
            _future.waitFor(self._imager.moveCenterToGlobal((target[0], target[1], start_glob[2]), "fast"))
            stack = _future.waitFor(
                acquire_z_stack(self._imager, start_glob[2], stop_glob[2], 1e-6, hysteresis_correction=False),
                timeout=60,
            ).getResult()
        fav_frame = stack[0]
        if direction > 0:
            stack = stack[::-1]
            start_glob, stop_glob = stop_glob, start_glob

        # get the normalized 20µm³ region for tracking
        ijk_stack = np.array([f.data().T for f in stack])
        stack_xform = SRT3DTransform.from_pyqtgraph(
            fav_frame.globalTransform(),
            from_cs=f"frame_{fav_frame.info()['id']}.xyz",
            to_cs="global",
        ) * TransposeTransform(
            (2, 1, 0),
            from_cs=f"frame_{fav_frame.info()['id']}.ijk",
            to_cs=f"frame_{fav_frame.info()['id']}.xyz",
        )
        start_ijk = np.round(stack_xform.inverse.map(start_glob)).astype(int)
        stop_ijk = np.round(stack_xform.inverse.map(stop_glob)).astype(int)
        start_ijk, stop_ijk = np.min((start_ijk, stop_ijk), axis=0), np.max((start_ijk, stop_ijk), axis=0)
        if self._roiSize is None:
            self._roiSize = tuple(stop_ijk - start_ijk)
        stop_ijk = start_ijk + self._roiSize  # always be the same size
        roi_stack = ijk_stack[
            start_ijk[0] : stop_ijk[0],
            start_ijk[1] : stop_ijk[1],
            start_ijk[2] : stop_ijk[2],
        ]
        assert roi_stack.shape == self._roiSize
        region_xform = stack_xform * TTransform(
            offset=start_ijk,
            from_cs=f"frame_{fav_frame.info()['id']}.roi",
            to_cs=f"frame_{fav_frame.info()['id']}.ijk",
        )
        region_center = np.round(region_xform.inverse.map(target)).astype(int)
        return roi_stack, region_xform, region_center
