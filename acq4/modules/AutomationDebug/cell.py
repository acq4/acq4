import numpy as np

from acq4.Manager import getManager
from acq4.util import Qt, ptime
from acq4.util.debug import logMsg, printExc
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
        return np.array(self._positions[max(self._positions)])

    @future_wrap
    def initializeTracker(self, imager, stack=None, trackerClass=CV2MostFlowAgreementTracker, _future=None):
        # Initialize tracker if we have none, or just grab another stack and check if it still matches otherwise
        if self._tracker is None:
            self._imager = imager
            self._tracker = trackerClass()
            stack, xform, center = self._takeStackshot(_future)
            obj_stack = ObjectStack(stack, xform, center)
            self._tracker.set_tracked_object(obj_stack)
        else:
            if not self.updatePosition(_future):
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
        self.isTracking = enable
        if enable:
            if self._trackingFuture is not None:
                self._trackingFuture.stop("Tracking restarted")
            self._trackingFuture = self._track(interval)
            self._trackingFuture.onFinish(self._handleTrackingFinished)
        elif self._trackingFuture is not None:
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
                except _future.StopRequested:
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
        self.isTracking = False
        if not future.wasStopped():
            future.wait()

    def updatePosition(self, _future):
        while len(self._tracker.object_stacks) == 0:
            _future.sleep(0.1)
        frame, xform, _ = self._takeStackshot(_future, single=True)
        result = self._tracker.next_frame(frame[0], xform)
        if not result["match_success"]:
            stack, xform, _ = self._takeStackshot(_future)
            img_stack = ImageStack(stack, xform)
            result = self._tracker.next_frame(img_stack)
        global_position = result["position"].mapped_to("global")
        self._positions[ptime.time()] = global_position
        self.sigPositionChanged.emit(global_position)
        return result["match_success"]

    def _takeStackshot(self, _future, single=False):
        target = np.array(self.position)
        current_focus = self._imager.globalCenterPosition()
        direction = np.sign(target[2] - current_focus[2])
        margin = 20e-6

        with getManager().reserveDevices(
            [self._imager, self._imager.scopeDev.positionDevice(), self._imager.scopeDev.focusDevice()], timeout=30.0
        ):
            if single:
                start_glob = target - np.array([margin, margin, 0])
                stop_glob = target + np.array([margin, margin, 0])
                _future.waitFor(self._imager.moveCenterToGlobal(target, "fast"))
                with self._imager.ensureRunning():
                    stack = _future.waitFor(self._imager.acquireFrames(1, ensureFreshFrames=True)).getResult()
            else:
                start_glob = target - margin
                stop_glob = target + margin
                if direction < 0:
                    start_glob, stop_glob = stop_glob, start_glob
                _future.waitFor(self._imager.moveCenterToGlobal((target[0], target[1], start_glob[2]), "fast"))
                stack = acquire_z_stack(
                    self._imager,
                    start_glob[2],
                    stop_glob[2],
                    1e-6,
                    hysteresis_correction=False,
                    slow_fallback=False,  # the slow fallback mode is too slow to be useful here
                    deviceReservationTimeout=30.0,  # possibly competing with pipette calibration, which can take a while
                    block=True,
                    checkStopThrough=_future,
                ).getResult()
                assert stack[0].depth < stack[-1].depth
                if direction < 0:
                    # stack = stack[::-1]  # TODO stacks always come back in the ascending depth order, but they shouldn't
                    start_glob, stop_glob = stop_glob, start_glob

        fav_frame = stack[0]

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
        if np.any(start_ijk < 0) or np.any(stop_ijk < 0):
            raise ValueError("target is too close to the edge of this stack")
        start_ijk, stop_ijk = np.min((start_ijk, stop_ijk), axis=0), np.max((start_ijk, stop_ijk), axis=0)
        if not single:
            if self._roiSize is None:
                self._roiSize = tuple(stop_ijk - start_ijk)
            stop_ijk = start_ijk + self._roiSize  # always be the same size
        roi_stack = ijk_stack[
            start_ijk[0] : stop_ijk[0],
            start_ijk[1] : stop_ijk[1],
            start_ijk[2] : stop_ijk[2],
        ].copy()  # copy to allow freeing of the full stack memory
        if not single:
            assert (
                roi_stack.shape == self._roiSize
            ), f"stackshot generated wrong size stack ({roi_stack.shape} vs {self._roiSize})"
        region_xform = stack_xform * TTransform(
            offset=start_ijk,
            from_cs=f"frame_{fav_frame.info()['id']}.roi",
            to_cs=f"frame_{fav_frame.info()['id']}.ijk",
        )
        region_center = np.round(region_xform.inverse.map(target)).astype(int)
        return roi_stack, region_xform, region_center
