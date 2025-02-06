from __future__ import annotations

import os
import random

import numpy as np

from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.Pipette import Pipette
from acq4.devices.Pipette.calibration import calibratePipette
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.future import Future, future_wrap, FutureButton
from acq4.util.imaging.sequencer import acquire_z_stack
from pyqtgraph import mkPen, SpinBox
from pyqtgraph.units import µm

UiTemplate = Qt.importTemplate('.window')


class AutomationDebugWindow(Qt.QWidget):
    sigWorking = Qt.Signal(object)  # a btn that is busy or False to signify no longer working
    sigLogMessage = Qt.Signal(str)

    def __init__(self, module: "AutomationDebug"):
        super().__init__()
        self.ui = UiTemplate()
        self.ui.setupUi(self)

        self.sigWorking.connect(self._setWorkingState)
        self.failedCalibrations = []
        self.module = module
        self.setWindowTitle("Automation Debug")
        self._previousBoxWidgets = []
        self._previousBoxBounds = []

        self.ui.clearBtn.clicked.connect(self.clearBoundingBoxes)
        self.ui.zStackDetectBtn.setOpts(future_producer=self._detectNeuronsZStack, stoppable=True)
        self.ui.zStackDetectBtn.sigFinished.connect(self._handleDetectResults)
        self.ui.flatDetectBtn.setOpts(future_producer=self._detectNeuronsFlat, stoppable=True)
        self.ui.flatDetectBtn.sigFinished.connect(self._handleDetectResults)

        self.ui.setTopLeftButton.clicked.connect(self._setTopLeft)
        self.ui.setBottomRightButton.clicked.connect(self._setBottomRight)

        self.ui.autoTargetBtn.setOpts(future_producer=self._autoTarget, stoppable=True)
        self.ui.autoTargetBtn.sigFinished.connect(self._handleAutoFinish)

        for name, dev in self.module.manager.devices.items():
            if isinstance(dev, Pipette):
                self.ui.pipetteSelector.addItem(name)
            elif isinstance(dev, Camera):
                self.ui.cameraSelector.addItem(name)

        self.ui.trackFeaturesBtn.setOpts(future_producer=self.doFeatureTracking, 
            processing="Stop tracking", stoppable=True)
        self.ui.trackFeaturesBtn.sigFinished.connect(self._handleFeatureTrackingFinish)
        self._featureTracker = None

        self.ui.testPipetteBtn.setOpts(
            future_producer=self.doPipetteCalibrationTest,
            stoppable=True,
            processing="Interrupt pipette\ncalibration test"
        )
        self.ui.testPipetteBtn.setToolTip("Start with the pipette calibrated and in the field of view")
        self.ui.testPipetteBtn.sigFinished.connect(self._handleCalibrationFinish)

        self._testing_pipette = False
        self.ui.pipetteLog.setReadOnly(True)
        self.sigLogMessage.connect(self.ui.pipetteLog.append)

        self.show()

    @future_wrap
    def doPipetteCalibrationTest(self, _future):
        self.sigWorking.emit(self.ui.testPipetteBtn)
        camera = self.cameraDevice
        pipette = self.pipetteDevice
        true_tip_position = pipette.globalPosition()
        fake_tip_position = true_tip_position + np.random.uniform(-100e-6, 100e-6, 3)
        pipette.resetGlobalPosition(fake_tip_position)
        pipette.moveTo("home", "fast")
        while True:
            try:
                _future.waitFor(calibratePipette(pipette, camera, camera.scopeDev))
                error = np.linalg.norm(pipette.globalPosition() - true_tip_position)
                self.sigLogMessage.emit(f"Calibration complete: {error*1e6:.2g}µm error")
                if error > 50e-6:
                    self.failedCalibrations.append(error)
                    i = len(self.failedCalibrations) - 1
                    self.sigLogMessage.emit(
                        f'....so bad. Why? Check man.getModule("AutomationDebug").failedCalibrations[{i}]'
                    )
            except Future.Stopped:
                self.sigLogMessage.emit('Calibration interrupted by user request')
                break

    @future_wrap
    def doFeatureTracking(self, _future: Future):
        from acq4.util.visual_tracker import PyrLK3DTracker, ObjectStack, ImageStack

        self.sigWorking.emit(self.ui.trackFeaturesBtn)
        pipette = self.pipetteDevice
        pix = self.cameraDevice.getPixelSize()[0]  # assume square pixels
        target = pipette.targetPosition()
        start = target[2] - 10e-6
        stop = target[2] + 10e-6
        step = 1e-6
        direction = 1
        tracker = None

        _future.waitFor(pipette.focusTarget())

        while True:
            stack = _future.waitFor(acquire_z_stack(self.cameraDevice, start, stop, step), timeout=60).getResult()
            # get the closest frame to the target depth
            depths = [abs(f.depth - target[2]) for f in stack]
            z = np.argmin(depths)
            target_frame = stack[z]
            relative_target = np.array(tuple(reversed(target_frame.mapFromGlobalToFrame(tuple(target[:2])) + (z,))))
            stack_data = np.array([frame.data().T for frame in stack])
            start, stop = stop, start
            if tracker is None:
                obj_stack = ObjectStack(
                    img_stack=stack_data,
                    px_size=pix,
                    z_step=step,
                    obj_center=relative_target,
                    tracked_z_vals=(-6e-6, -3e-6, 0, 3e-6, 6e-6),
                    feature_radius=12e-6,
                )
                tracker = self._featureTracker = PyrLK3DTracker()
                tracker.set_tracked_object(obj_stack)
                continue
            if direction < 0:
                stack_data = stack_data[::-1]
            direction *= -1
            result = tracker.next_frame(ImageStack(stack_data, pix, step * direction))
            z, y, x = result['updated_object_stack'].obj_center  # frame, row, col
            frame = stack[round(z)]
            target = frame.mapFromFrameToGlobal((x, y)) + (frame.depth,)
            pipette.setTarget(target)
            self.sigLogMessage.emit(f"Updated target to ({x}, {y}, {z}): {target}")

    def _handleFeatureTrackingFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _handleCalibrationFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _setWorkingState(self, working: bool | Qt.QPushButton):
        if working:
            self.module.manager.getModule("Camera").window()  # make sure camera window is open
        self.ui.zStackDetectBtn.setEnabled(working == self.ui.zStackDetectBtn or not working)
        self.ui.flatDetectBtn.setEnabled(working == self.ui.flatDetectBtn or not working)
        self.ui.autoTargetBtn.setEnabled(working == self.ui.autoTargetBtn or not working)
        self.ui.testPipetteBtn.setEnabled(working == self.ui.testPipetteBtn or not working)
        self.ui.trackFeaturesBtn.setEnabled(working == self.ui.trackFeaturesBtn or not working)

    @property
    def cameraDevice(self) -> Camera:
        return self.module.manager.getDevice(self.ui.cameraSelector.currentText())

    @property
    def scopeDevice(self) -> Microscope:
        return self.cameraDevice.scopeDev  # TODO

    @property
    def pipetteDevice(self) -> Pipette:
        return self.module.manager.getDevice(self.ui.pipetteSelector.currentText())

    def _setTopLeft(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0], region[1]))
        self._xLeftSpin.setValue(bound.x())
        self._yTopSpin.setValue(bound.y())

    def _setBottomRight(self):
        cam = self.cameraDevice
        region = cam.getParam("region")
        bound = cam.globalTransform().map(Qt.QPointF(region[0] + region[2], region[1] + region[3]))
        self._xRightSpin.setValue(bound.x())
        self._yBottomSpin.setValue(bound.y())

    def clearBoundingBoxes(self):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        for widget in self._previousBoxWidgets:
            cam_win.removeItem(widget)
        self._previousBoxWidgets = []
        self._previousBoxBounds = []

    def _handleDetectResults(self, neurons_fut: Future) -> list:
        try:
            if neurons_fut.wasInterrupted():
                return
            self._displayBoundingBoxes(neurons_fut.getResult())
        finally:
            self.sigWorking.emit(False)

    def _displayBoundingBoxes(self, bounding_boxes):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        self.clearBoundingBoxes()
        for start, end in bounding_boxes:
            box = Qt.QGraphicsRectItem(Qt.QRectF(Qt.QPointF(start[0], start[1]), Qt.QPointF(end[0], end[1])))
            box.setPen(mkPen("r", width=2))
            box.setBrush(Qt.QBrush(Qt.QColor(0, 0, 0, 0)))
            cam_win.addItem(box)
            self._previousBoxWidgets.append(box)
            self._previousBoxBounds.append((start, end))
            # TODO label boxes
            # label = TextItem('Neuron')
            # label.setPen(mkPen('r', width=1))
            # label.setPos(*end)
            # cam_win.addItem(label)
            # self._previousBoxWidgets.append(label)

    @future_wrap
    def _detectNeuronsFlat(self, _future: Future):
        self.sigWorking.emit(self.ui.flatDetectBtn)
        from acq4.util.imaging.object_detection import detect_neurons

        with self.cameraDevice.ensureRunning():
            frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]
        with self.cameraDevice.ensureRunning():
            frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]
        return _future.waitFor(detect_neurons(frame)).getResult()

    @future_wrap
    def _detectNeuronsZStack(self, _future: Future) -> list:
        self.sigWorking.emit(self.ui.zStackDetectBtn)
        from acq4.util.imaging.object_detection import detect_neurons

        depth = self.cameraDevice.getFocusDepth()
        start = depth - 10 * µm
        stop = depth + 10 * µm
        z_stack = _future.waitFor(acquire_z_stack(self.cameraDevice, start, stop, 1 * µm)).getResult()
        self.cameraDevice.setFocusDepth(depth)  # no need to wait
        return _future.waitFor(detect_neurons(z_stack)).getResult()

    @future_wrap
    def _autoTarget(self, _future):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        x, y = self._randomLocation()
        _future.waitFor(self.scopeDevice.setGlobalPosition((x, y)))
        # TODO don't know why this hangs when using waitFor, but it does
        depth = self.scopeDevice.findSurfaceDepth(
            self.cameraDevice, searchDistance=50 * µm, searchStep=15 * µm, block=True
        ).getResult()
        depth -= 50 * µm
        self.cameraDevice.setFocusDepth(depth)
        neurons_fut = _future.waitFor(self._detectNeuronsZStack())
        self._displayBoundingBoxes(neurons_fut.getResult())

    def _handleAutoFinish(self, fut: Future):
        try:
            if self._previousBoxBounds:
                box = random.choice(self._previousBoxBounds)
                center = np.array(box[0]) + np.array(box[1]) / 2
                if center.ndim == 2:
                    center = (center[0], center[1], self.cameraDevice.getFocusDepth())
                print(f"Setting pipette target to {center}")
                self.pipetteDevice.setTarget(center)
        finally:
            self.sigWorking.emit(False)

    def _randomLocation(self):
        x = random.uniform(self._xLeftSpin.value(), self._xRightSpin.value())
        y = random.uniform(self._yBottomSpin.value(), self._yTopSpin.value())
        return x, y

    def quit(self):
        self.close()


class AutomationDebug(Module):
    moduleDisplayName = "Automation Debug"
    moduleCategory = "Utilities"

    def __init__(self, manager, name, config):
        Module.__init__(self, manager, name, config)
        self.ui = AutomationDebugWindow(self)
        manager.declareInterface(name, ["automationDebugModule"], self)
        this_dir = os.path.dirname(__file__)
        self.ui.setWindowIcon(Qt.QIcon(os.path.join(this_dir, "Manager", "icon.png")))

    def quit(self, fromUi=False):
        if not fromUi:
            self.ui.quit()
        super().quit()
