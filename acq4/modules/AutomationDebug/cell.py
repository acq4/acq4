import numpy as np

from acq4.util import Qt, ptime
from acq4.util.future import future_wrap
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4_automation.feature_tracking import CV2MostFlowAgreementTracker, ObjectStack, ImageStack
from coorx import SRT3DTransform, Image, Point, TransposeTransform


class Cell(Qt.QObject):
    sigPositionChanged = Qt.pyqtSignal(object)

    def __init__(self, position, imager):
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
        self._imager = imager
        self._trackingFuture = None
        self._tracker = CV2MostFlowAgreementTracker()
        self._initializeTracker()

    @property
    def position(self):
        """Get the current position of the cell."""
        return self._positions[max(self._positions)]

    @future_wrap
    def _initializeTracker(self, _future):
        full_stack = _future.waitFor(self._takeStackshot()).getResult()
        xforms = [
            SRT3DTransform.from_pyqtgraph(f.globalTransform(), from_cs=f"frame_{f.info()['id']}.xyz", to_cs="global") *
            TransposeTransform((2,1,0), from_cs=f"frame_{f.info()['id']}.ijk", to_cs=f"frame_{f.info()['id']}.xyz") for f in full_stack
            for f in full_stack
        ]
        global_center = Point(self.initialPosition, "global")
        full_center = global_center.mapped_to(xforms[0].systems[0])
        bounds = ((full_center[1], full_center[1]), (full_center[2], full_center[2]))
        full_stack = [Image(f.data(), cs_name=f"frame_{f.info()['id']}.ijk") for f in full_stack]

        obj_stack = ObjectStack(stack, xform, center)
        self._tracker.set_tracked_object(obj_stack)

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
            if self._trackingFuture is not None:
                self._trackingFuture.stop("Tracking restarted")
            self._trackingFuture = self._track(interval)
        elif self._trackingFuture is not None:
            self._trackingFuture.stop("Tracking disabled")
            self._trackingFuture = None

    @future_wrap
    def _track(self, interval: float, _future):
        """Track the cell position at the specified interval."""
        last_tracked = max(self._positions)
        while True:
            if ptime.time() - last_tracked > interval:
                _future.waitFor(self.updatePosition())
            _future.sleep(interval)

    @future_wrap
    def updatePosition(self, _future):
        while self._tracker.current_object_stack is None:
            _future.sleep(0.1)
        stack = _future.waitFor(self._takeStackshot()).getResult()
        xform = SRT3DTransform.from_pyqtgraph(stack[0].globalTransform())
        img_stack = ImageStack(stack, xform)
        result = self._tracker.next_frame(img_stack)
        global_position = xform.map(result["position"])
        self._positions[ptime.time()] = global_position
        self.sigPositionChanged.emit(global_position)

    @future_wrap
    def _takeStackshot(self, _future):
        current_focus = self._imager.globalCenterPosition()

        my_x, my_y, my_z = self.position
        start = my_z - 10e-6
        end = my_z + 10e-6
        if current_focus[2] > my_z:
            start, end = end, start

        cam_left, cam_top, cam_width, cam_height = self._imager.getBoundary()
        if (
            (my_x - 50e-6) < cam_left
            or (my_x + 50e-6) > (cam_left + cam_width)
            or (my_y + 50e-6) > cam_top
            or (my_y - 50e-6) < (cam_top + cam_height)
        ):
            _future.waitFor(self._imager.moveCenterToGlobal((my_x, my_y, start)))

        stack = _future.waitFor(acquire_z_stack(self._imager, start, end, 1e-6)).getResult()
        if current_focus[2] > my_z:
            stack = stack[::-1]
        # extract 20µm³ region
        µm_x = stack[0].globalTransform().getScale()[0] / 1e-6
        µm_y = stack[0].globalTransform().getScale()[1] / 1e-6
        stack = [
            Image(st.data()[int(µm_x / 2) : -int(µm_x / 2), int(µm_y / 2) : -int(µm_y / 2)], st.globalTransform())
            for st in stack
        ]
