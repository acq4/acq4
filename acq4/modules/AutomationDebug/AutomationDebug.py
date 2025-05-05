from __future__ import annotations

import os

import numpy as np

from MetaArray import MetaArray
from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.Pipette import Pipette
from acq4.devices.Pipette.calibration import findNewPipette
from acq4.devices.Pipette.planners import PipettePathGenerator, GeometryAwarePathGenerator
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.debug import logMsg
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.target import TargetBox
from acq4.util.threadrun import runInGuiThread
from pyqtgraph.units import µm

UiTemplate = Qt.importTemplate(".window")


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
        self._previousTargets = []

        self.ui.clearBtn.clicked.connect(self.clearBoundingBoxes)
        self.ui.zStackDetectBtn.setOpts(future_producer=self._detectNeuronsZStack, stoppable=True)
        self.ui.zStackDetectBtn.sigFinished.connect(self._handleDetectResults)
        self.ui.testUIBtn.setOpts(future_producer=self._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._handleDetectResults)

        self.ui.multiChannelEnableCheck.toggled.connect(self._updateMultiChannelState)
        self.ui.motionPlannerSelector.currentIndexChanged.connect(self._changeMotionPlanner)

        self.ui.setTopLeftButton.clicked.connect(self._setTopLeft)
        self.ui.setBottomRightButton.clicked.connect(self._setBottomRight)

        self.ui.mockFilePath.setReadOnly(True)
        self.ui.mockFileButton.clicked.connect(self._selectMockFile)

        self.ui.autoTargetBtn.setOpts(future_producer=self._autoTarget, stoppable=True)
        self.ui.autoTargetBtn.sigFinished.connect(self._handleAutoFinish)

        self._motionPlanners = {}
        for name, dev in self.module.manager.devices.items():
            if isinstance(dev, Pipette):
                self.ui.pipetteSelector.addItem(name)
                self._motionPlanners[(name, dev.pathGeneratorClass)] = dev.pathGenerator
            elif isinstance(dev, Camera):
                self.ui.cameraSelector.addItem(name)

        self.ui.trackFeaturesBtn.setOpts(
            future_producer=self.doFeatureTracking, processing="Stop tracking", stoppable=True
        )
        self.ui.trackFeaturesBtn.sigFinished.connect(self._handleFeatureTrackingFinish)
        self._featureTracker = None

        self.ui.testPipetteBtn.setOpts(
            future_producer=self.doPipetteCalibrationTest,
            stoppable=True,
            processing="Interrupt pipette\ncalibration test",
        )
        self.ui.testPipetteBtn.setToolTip("Start with the pipette calibrated and in the field of view")
        self.ui.testPipetteBtn.sigFinished.connect(self._handleCalibrationFinish)

        self._testing_pipette = False
        self.ui.pipetteLog.setReadOnly(True)
        self.sigLogMessage.connect(self.ui.pipetteLog.append)

        self.show()
        planner = self.module.config.get("motionPlanner", "Geometry-aware")
        self.ui.motionPlannerSelector.setCurrentText(planner)
        self._populatePresetCombos()

    def _updateMultiChannelState(self, enabled):
        self.ui.detectionPresetCombo.setEnabled(enabled)
        self.ui.classificationPresetCombo.setEnabled(enabled)

    def _populatePresetCombos(self):
        presets = self.scopeDevice.presets.keys()
        self.ui.detectionPresetCombo.clear()
        self.ui.classificationPresetCombo.clear()
        self.ui.detectionPresetCombo.addItems(presets)
        self.ui.classificationPresetCombo.addItems(presets)

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
                _future.waitFor(findNewPipette(pipette, camera, camera.scopeDev))
                error = np.linalg.norm(pipette.globalPosition() - true_tip_position)
                self.sigLogMessage.emit(f"Calibration complete: {error * 1e6:.2g}µm error")
                if error > 50e-6:
                    self.failedCalibrations.append(error)
                    i = len(self.failedCalibrations) - 1
                    self.sigLogMessage.emit(
                        f'....so bad. Why? Check man.getModule("AutomationDebug").failedCalibrations[{i}]'
                    )
            except Future.Stopped:
                self.sigLogMessage.emit("Calibration interrupted by user request")
                break

    @future_wrap
    def doFeatureTracking(self, _future: Future):
        from acq4_automation.feature_tracking import (
            PyrLK3DTracker,
            CellPoseTracker,
            CV2MostFlowAgreementTracker,
            ObjectStack,
            ImageStack,
        )

        self.sigWorking.emit(self.ui.trackFeaturesBtn)
        pipette = self.pipetteDevice
        pix = self.cameraDevice.getPixelSize()[0]  # assume square pixels
        target = pipette.targetPosition()
        step = 1e-6
        direction = 1
        if self.ui.featureTrackerSelector.currentText() == "Cellpose":
            tracker = CellPoseTracker()
        elif self.ui.featureTrackerSelector.currentText() == "CV2":
            tracker = self._featureTracker = CV2MostFlowAgreementTracker()
        elif self.ui.featureTrackerSelector.currentText() == "PyrLK3D":
            tracker = self._featureTracker = PyrLK3DTracker()
        else:
            raise ValueError(f"unknown tracker '{self.ui.featureTrackerSelector.currentText()}'")
        self._featureTracker = tracker
        _future.waitFor(pipette.focusTarget())
        obj_stack = None
        sign = 1

        while True:
            sign *= -1
            start = target[2] - (10e-6 * sign)
            stop = target[2] + (10e-6 * sign)
            stack = _future.waitFor(acquire_z_stack(self.cameraDevice, start, stop, step), timeout=60).getResult()
            # get the closest frame to the target depth
            depths = [abs(f.depth - target[2]) for f in stack]
            z = np.argmin(depths)
            target_frame = stack[z]
            relative_target = np.array(tuple(reversed(target_frame.mapFromGlobalToFrame(tuple(target[:2])) + (z,))))
            stack_data = np.array([frame.data().T for frame in stack])
            if obj_stack is None:
                obj_stack = ObjectStack(
                    img_stack=stack_data,
                    px_size=pix,
                    z_step=step,
                    obj_center=relative_target,
                    tracked_z_vals=(-6e-6, -3e-6, 0, 3e-6, 6e-6),
                    feature_radius=12e-6,
                )
                tracker.set_tracked_object(obj_stack)
                continue
            if direction < 0:
                stack_data = stack_data[::-1]
            direction *= -1
            result = tracker.next_frame(ImageStack(stack_data, pix, step * direction))
            z, y, x = result["updated_object_stack"].obj_center  # frame, row, col
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
        self.ui.testUIBtn.setEnabled(working == self.ui.testUIBtn or not working)
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
        for box in self._previousBoxWidgets:
            cam_win.removeItem(box)
            self.scopeDevice.sigGlobalTransformChanged.disconnect(box.noticeFocusChange)
        self._previousBoxWidgets = []
        self._previousBoxBounds = []

    def _handleDetectResults(self, neurons_fut: Future) -> None:
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
            box = TargetBox(start, end)
            cam_win.addItem(box)
            self.scopeDevice.sigGlobalTransformChanged.connect(box.noticeFocusChange)
            self._previousBoxWidgets.append(box)
            self._previousBoxBounds.append((start, end))
            # TODO label boxes
            # label = TextItem('Neuron')
            # label.setPen(mkPen('r', width=1))
            # label.setPos(*end)
            # cam_win.addItem(label)
            # self._previousBoxWidgets.append(label)

    @future_wrap
    def _testUI(self, _future):
        with self.cameraDevice.ensureRunning():
            frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]
        points = np.random.random((20, 3))
        points[:, 2] *= 20e-6
        points[:, 1] *= frame.shape[0]
        points[:, 0] *= frame.shape[1]
        boxes = []
        for pt in points:
            center = frame.mapFromFrameToGlobal(pt)
            boxes.append((center - 20e-6, center + 20e-6))
        return boxes

    @future_wrap
    def _detectNeuronsZStack(self, _future: Future) -> list:
        self.sigWorking.emit(self.ui.zStackDetectBtn)
        from acq4_automation.object_detection import detect_neurons

        man = self.module.manager
        autoencoder = man.config.get("misc", {}).get("autoencoderPath", None)
        classifier = man.config.get("misc", {}).get("classifierPath", None)
        pixel_size = self.cameraDevice.getPixelSize()[0]
        z_scale = step_z = 1 * µm
        depth = self.cameraDevice.getFocusDepth()
        classification_stack = []
        if self.ui.mockCheckBox.isChecked() and self.ui.mockFilePath.text():
            with self.cameraDevice.ensureRunning():
                # Acquire a single frame to get the camera transform
                real_frame = self.cameraDevice.acquireFrames(1).getResult()[0]
            base_xform = real_frame.globalTransform()
            base_position = np.array(real_frame.mapFromFrameToGlobal((0, 0, 0)))
            # Load the MetaArray file
            mock_file_path = self.ui.mockFilePath.text()
            data = MetaArray(file=mock_file_path).asarray()
            detection_stack = [
                Frame(
                    data[i],
                    info={
                        "transform": {
                            "pos": base_position + (0, 0, i * z_scale),
                            "scale": base_xform.getScale(),
                        },
                    },
                )
                for i in range(len(data))
            ]
            # TODO: Handle multichannel mock file path later
        else:
            # --- Real Acquisition ---
            start_z = depth - 20 * µm
            stop_z = depth + 20 * µm

            if self.ui.multiChannelEnableCheck.isChecked():
                # --- Multichannel Acquisition ---
                detection_preset = self.ui.detectionPresetCombo.currentText()
                classification_preset = self.ui.classificationPresetCombo.currentText()

                if not detection_preset or not classification_preset:
                    raise ValueError("Detection and Classification presets must be selected for multichannel acquisition.")

                logMsg(f"Starting multichannel Z-stack acquisition: Detection='{detection_preset}', Classification='{classification_preset}'")
                _future.waitFor(self.scopeDevice.loadPreset(detection_preset))
                logMsg(f"Acquiring detection stack ({start_z/µm:.1f} - {stop_z/µm:.1f} µm, step {step_z/µm:.1f} µm)")
                detection_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z)
                ).getResult()

                _future.waitFor(self.scopeDevice.loadPreset(classification_preset))
                logMsg(f"Acquiring classification stack ({start_z/µm:.1f} - {stop_z/µm:.1f} µm, step {step_z/µm:.1f} µm)")
                classification_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z)
                ).getResult()
                logMsg("Multichannel acquisition complete.")

                # --- Verify Stack Alignment ---
                if len(detection_stack) != len(classification_stack):
                    raise ValueError(
                        f"Z-stack length mismatch: Detection ({len(detection_stack)}) != "
                        f"Classification ({len(classification_stack)})"
                    )
                # Check Z positions (assuming frame.depth exists and is reliable)
                # TODO: Confirm frame.depth is the correct attribute
                z_tolerance = 0.1 * step_z
                for i, (f1, f2) in enumerate(zip(detection_stack, classification_stack)):
                    # Check if frames have depth attribute before comparing
                    f1_depth = getattr(f1, 'depth', None)
                    f2_depth = getattr(f2, 'depth', None)
                    if f1_depth is None or f2_depth is None:
                        logMsg(f"Warning: Cannot verify Z alignment at frame {i}, missing 'depth' attribute.", msgType='warning')
                        continue # Skip check for this frame if depth is missing

                    if abs(f1_depth - f2_depth) > z_tolerance:
                        # Log detailed info from frame info if available
                        f1_info = f1.info().get('transform', {}).get('pos', 'N/A')
                        f2_info = f2.info().get('transform', {}).get('pos', 'N/A')
                        raise ValueError(
                            f"Z-position mismatch at frame {i}: "
                            f"Detection ({f1_depth/µm:.2f} µm, info: {f1_info}) != "
                            f"Classification ({f2_depth/µm:.2f} µm, info: {f2_info}). "
                            f"Tolerance: {z_tolerance/µm:.2f} µm"
                        )
                logMsg("Z-stack alignment verified.")
            else:
                # --- Single Channel Acquisition ---
                logMsg(f"Starting single channel Z-stack acquisition ({start_z/µm:.1f} - {stop_z/µm:.1f} µm, step {step_z/µm:.1f} µm)")
                detection_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z)
                ).getResult()
                logMsg("Single channel acquisition complete.")

        # --- Call Detection ---
        if detection_stack is None:
             raise RuntimeError("Detection stack acquisition failed or was skipped.")

        logMsg("Running neuron detection...")
        if classification_stack:
            working_stack = (detection_stack, classification_stack)
        else:
            working_stack = detection_stack
        result = _future.waitFor(
            detect_neurons(
                working_stack,
                autoencoder=autoencoder,
                classifier=classifier,
                xy_scale=pixel_size,
                z_scale=step_z,  # Use the actual step size
                multichannel=bool(classification_stack),
            ),
            timeout=600,
        ).getResult()
        logMsg(f"Neuron detection finished. Found {len(result)} potential neurons.")
        return result

    @future_wrap
    def _autoTarget(self, _future):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        possibly_stale = False
        if self._previousBoxBounds:
            possibly_stale = True
            neurons = self._previousBoxBounds
        else:
            x, y = self._randomLocation()
            _future.waitFor(self.scopeDevice.setGlobalPosition((x, y)))
            # TODO don't know why this hangs when using waitFor, but it does
            depth = self.scopeDevice.findSurfaceDepth(
                self.cameraDevice, searchDistance=50 * µm, searchStep=15 * µm, block=True
            ).getResult()
            depth -= 50 * µm
            self.cameraDevice.setFocusDepth(depth)
            neurons = _future.waitFor(self._detectNeuronsZStack()).getResult()
            runInGuiThread(self._displayBoundingBoxes, neurons)
        centers = [(start + end) / 2 for start, end in np.array(neurons)]
        target = next(
            c for c in centers
            if not self._previousTargets or all(np.linalg.norm(c - prev) > 35 * µm for prev in self._previousTargets)
        )
        if target is None:
            if possibly_stale:
                runInGuiThread(self.clearBoundingBoxes)
                return self.waitFor(self._autoTarget()).getResult()
            else:
                raise RuntimeError("No valid target found")
        self._previousTargets.append(target)
        self.pipetteDevice.setTarget(target)
        print(f"Setting pipette target to {target}")

    def _handleAutoFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _selectMockFile(self):
        filePath, _ = Qt.QFileDialog.getOpenFileName(
            self, "Select MetaArray File", "", "MetaArray Files (*.ma);;All Files (*)"
        )
        if filePath:
            self.ui.mockFilePath.setText(filePath)
            self.ui.mockCheckBox.setChecked(True)

    def _randomLocation(self):
        return self.cameraDevice.globalCenterPosition()[:2]
        # TODO get the spinners back
        # x = random.uniform(self._xLeftSpin.value(), self._xRightSpin.value())
        # y = random.uniform(self._yBottomSpin.value(), self._yTopSpin.value())
        # return x, y

    def _changeMotionPlanner(self, idx):
        name = self.ui.motionPlannerSelector.currentText()
        planner = {
            "Geometry-aware": GeometryAwarePathGenerator,
            "Objective radius only": PipettePathGenerator,
        }[name]
        Pipette.pathGeneratorClass = planner
        for name, dev in self.module.manager.devices.items():
            if isinstance(dev, Pipette):
                cache_key = (dev.name(), planner)
                if cache_key not in self._motionPlanners:
                    self._motionPlanners[cache_key] = planner(dev)
                dev.pathGenerator = self._motionPlanners[cache_key]

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
