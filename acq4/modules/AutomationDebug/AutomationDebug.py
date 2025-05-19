from __future__ import annotations

import os
from pathlib import Path

import numpy as np

import pyqtgraph as pg
from MetaArray import MetaArray
from acq4 import getManager
from acq4.devices.Camera import Camera
from acq4.devices.Microscope import Microscope
from acq4.devices.PatchPipette import PatchPipette
from acq4.devices.Pipette import Pipette
from acq4.devices.Pipette.calibration import findNewPipette
from acq4.devices.Pipette.planners import PipettePathGenerator, GeometryAwarePathGenerator
from acq4.modules.Camera import CameraWindow
from acq4.modules.Module import Module
from acq4.modules.TaskRunner import TaskRunner
from acq4.util import Qt
from acq4.util.debug import logMsg, printExc
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.target import TargetBox
from acq4.util.threadrun import futureInGuiThread, runInGuiThread
from coorx import SRT3DTransform, TransposeTransform
from pyqtgraph.units import µm, m
from .cell import Cell
from .ranking_window import RankingWindow

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
        self._mockDemo = True
        self._cell = None
        self._unranked_cells = []  # List of global positions of cells
        self._ranked_cells = {}  # Dict mapping cell ID (e.g., timestamp) to ranking info
        self._current_detection_stack = None
        self._current_classification_stack = None  # May be None
        self._previousTargets = []  # Used by autoTarget
        self._open_ranking_windows = []  # Keep track of open windows

        self.ui.clearBtn.clicked.connect(self.clearCells)
        self.ui.zStackDetectBtn.setOpts(future_producer=self._detectNeuronsZStack, stoppable=True)
        self.ui.zStackDetectBtn.sigFinished.connect(self._handleDetectResults)
        self.ui.testUIBtn.setOpts(future_producer=self._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._handleDetectResults)
        self.ui.addCellFromTargetBtn.setOpts(future_producer=self._addCellFromTarget, stoppable=True)

        self.ui.motionPlannerSelector.currentIndexChanged.connect(self._changeMotionPlanner)

        # Connect regular button click
        self.ui.rankCellsBtn.clicked.connect(self._rankCells)
        self.ui.selectRankDirBtn.clicked.connect(self._selectRankDir)

        self.ui.setTopLeftButton.clicked.connect(self._setTopLeft)
        self.ui.setBottomRightButton.clicked.connect(self._setBottomRight)

        self.ui.mockFilePath.setReadOnly(True)
        self.ui.mockFileButton.clicked.connect(self._selectMockFile)
        self.ui.mockClassificationFilePath.setReadOnly(True)
        self.ui.mockClassificationFileButton.clicked.connect(self._selectMockClassificationFile)

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

        self.ui.autopatchDemoBtn.setToolTip("Patch a cell! Repeat! REPEAT!")
        self.ui.autopatchDemoBtn.setOpts(future_producer=self._autopatchDemo, stoppable=True)
        self.ui.autopatchDemoBtn.sigFinished.connect(self._handleAutopatchDemoFinish)

        self.show()
        planner = self.module.config.get("motionPlanner", "Objective radius only")
        self.ui.motionPlannerSelector.setCurrentText(planner)
        # Set default ranking dir
        default_rank_dir = Path(self.module.manager.getBaseDir().name()) / "ranked_cells"
        self.ui.rankingSaveDirEdit.setText(str(default_rank_dir))
        self._populatePresetCombos()
        # Connect checkboxes to state update method
        self.ui.multiChannelEnableCheck.toggled.connect(self._updateMultiChannelAndMockStates)
        self.ui.mockCheckBox.toggled.connect(self._updateMultiChannelAndMockStates)
        self._updateMultiChannelAndMockStates()  # Set initial states

        self.loadConfig()

    def _selectRankDir(self):
        path = Qt.QFileDialog.getExistingDirectory(
            self, "Select Directory to Save Ranked Cells", self.ui.rankingSaveDirEdit.text()
        )
        if path:
            self.ui.rankingSaveDirEdit.setText(path)

    def _selectMockClassificationFile(self):
        filePath, _ = Qt.QFileDialog.getOpenFileName(
            self, "Select Mock Classification Z-Stack File", "", "MetaArray Files (*.ma);;All Files (*)"
        )
        if filePath:
            self.ui.mockClassificationFilePath.setText(filePath)

    def _updateMultiChannelAndMockStates(self):
        multi_channel_enabled = self.ui.multiChannelEnableCheck.isChecked()
        mock_mode_active = self.ui.mockCheckBox.isChecked()

        self.ui.detectionPresetCombo.setEnabled(multi_channel_enabled)
        self.ui.classificationPresetCombo.setEnabled(multi_channel_enabled)

        mock_classification_widgets_enabled = multi_channel_enabled and mock_mode_active
        self.ui.mockClassificationFileLabel.setEnabled(mock_classification_widgets_enabled)
        self.ui.mockClassificationFileButton.setEnabled(mock_classification_widgets_enabled)
        self.ui.mockClassificationFilePath.setEnabled(mock_classification_widgets_enabled)

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
        )

        self.sigWorking.emit(self.ui.trackFeaturesBtn)
        # TODO no bad! no gui access!
        if self.ui.featureTrackerSelector.currentText() == "Cellpose":
            tracker = CellPoseTracker
        elif self.ui.featureTrackerSelector.currentText() == "CV2":
            tracker = self._featureTracker = CV2MostFlowAgreementTracker
        elif self.ui.featureTrackerSelector.currentText() == "PyrLK3D":
            tracker = self._featureTracker = PyrLK3DTracker
        else:
            raise ValueError(f"unknown tracker '{self.ui.featureTrackerSelector.currentText()}'")
        pipette = self.pipetteDevice
        target: np.ndarray = pipette.targetPosition()
        cell = self._cell = Cell(target)
        _future.waitFor(cell.initializeTracker(self.cameraDevice, trackerClass=tracker))
        cell.enableTracking()
        cell.sigPositionChanged.connect(self._updatePipetteTarget)
        try:
            while cell.isTracking:
                _future.sleep(1)
        except Exception:
            cell.enableTracking(False)
            cell.sigPositionChanged.disconnect(self._updatePipetteTarget)
            raise

    @future_wrap
    def _addCellFromTarget(self, _future):
        target = self.pipetteDevice.targetPosition()
        cell = Cell(target)
        _future.waitFor(cell.initializeTracker(self.cameraDevice))
        self._unranked_cells.append(cell)
        boxPositions = [c.position for c in self._unranked_cells]
        _future.waitFor(futureInGuiThread(self._displayBoundingBoxes, boxPositions))

    def _updatePipetteTarget(self, pos):
        self.pipetteDevice.setTarget(pos)
        self.sigLogMessage.emit(f"Updated target to {pos}")

    def _handleFeatureTrackingFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _handleCalibrationFinish(self, fut: Future):
        self.sigWorking.emit(False)

    def _handleAutopatchDemoFinish(self, fut):
        self.sigWorking.emit(False)

    def _setWorkingState(self, working: bool | Qt.QPushButton):
        if working:
            self.module.manager.getModule("Camera").window()  # make sure camera window is open
        self.ui.zStackDetectBtn.setEnabled(working == self.ui.zStackDetectBtn or not working)
        self.ui.testUIBtn.setEnabled(working == self.ui.testUIBtn or not working)
        self.ui.autoTargetBtn.setEnabled(working == self.ui.autoTargetBtn or not working)
        self.ui.testPipetteBtn.setEnabled(working == self.ui.testPipetteBtn or not working)
        self.ui.trackFeaturesBtn.setEnabled(working == self.ui.trackFeaturesBtn or not working)
        self.ui.rankCellsBtn.setEnabled(len(self._unranked_cells) > 0)
        self.ui.autopatchDemoBtn.setEnabled(working == self.ui.autopatchDemoBtn or not working)

    @property
    def cameraDevice(self) -> Camera:
        return self.module.manager.getDevice(self.ui.cameraSelector.currentText())

    @property
    def scopeDevice(self) -> Microscope:
        return self.cameraDevice.scopeDev  # TODO

    @property
    def pipetteDevice(self) -> Pipette:
        return self.module.manager.getDevice(self.ui.pipetteSelector.currentText())

    @property
    def patchPipetteDevice(self) -> PatchPipette | None:
        pip = self.pipetteDevice
        man = self.module.manager
        for pp in man.listDevices():
            pp = man.getDevice(pp)
            if isinstance(pp, PatchPipette) and pp.pipetteDevice == pip:
                return pp
        return None

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

    def clearCells(self):
        self._unranked_cells = []
        self.clearBoundingBoxes()

    def clearBoundingBoxes(self):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        for box in self._previousBoxWidgets:
            cam_win.removeItem(box)
            self.scopeDevice.sigGlobalTransformChanged.disconnect(box.noticeFocusChange)
        self._previousBoxWidgets = []

    def _handleDetectResults(self, future: Future) -> None:
        """Handles results from _detectNeuronsZStack or _testUI."""
        try:
            if future.wasInterrupted():
                logMsg("Cell detection failed.")
                return
            neurons = future.getResult()

            logMsg(f"Cell detection complete. Found {len(neurons)} potential cells")
            self._displayBoundingBoxes(neurons)
            # from acq4_automation.object_detection import NeuronBoxViewer
            # if self._current_classification_stack is not None:
            #     data = np.array(([[s.data().T for s in self._current_detection_stack]], [[s.data().T for s in self._current_classification_stack]]))
            # else:
            #     data = np.array([s.data().T for s in self._current_detection_stack])
            # xform = SRT3DTransform.from_pyqtgraph(self._current_detection_stack[0].globalTransform()) * TransposeTransform((1, 0, 2))
            # self._viewer = NeuronBoxViewer(data, neurons, xform)
            # self._viewer.show()
        finally:
            self.sigWorking.emit(False)

    def _displayBoundingBoxes(self, neurons):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        self.clearBoundingBoxes()  # Clear previous boxes visually and state
        for neuron in neurons:
            start, end = np.array(neuron) - 10e-6, np.array(neuron) + 10e-6
            box = TargetBox(start, end)
            cam_win.addItem(box)
            # TODO: Re-evaluate if this connection is still needed or causes issues
            self.scopeDevice.sigGlobalTransformChanged.connect(box.noticeFocusChange)
            self._previousBoxWidgets.append(box)
            # TODO label boxes? Maybe add index number?
            # label = pg.TextItem(f'{len(self._previousBoxWidgets)}') # Example index
            # label.setPen(pg.mkPen('r', width=1))
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
    def _detectNeuronsZStack(self, _future: Future) -> tuple[list, list[Frame] | None, list[Frame] | None] | list:
        """Acquires Z-stack(s) and runs neuron detection. Returns (bboxes, detection_stack, classification_stack)."""
        from acq4_automation.object_detection import detect_neurons

        self.sigWorking.emit(self.ui.zStackDetectBtn)
        # Clear previous results before starting detection
        runInGuiThread(self.clearCells)
        self._current_detection_stack = None
        self._current_classification_stack = None

        pixel_size = self.cameraDevice.getPixelSize()[0]  # Used for both real and mock
        man = self.module.manager
        autoencoder = man.config.get("misc", {}).get("autoencoderPath", None)
        classifier = man.config.get("misc", {}).get("classifierPath", None)
        # pixel_size is now fetched earlier
        step_z = 1 * µm  # Default, will be updated by mock or real acquisition
        depth = self.cameraDevice.getFocusDepth()
        detection_stack = None  # Ensure it's initialized
        classification_stack = None  # Initialize as None

        # This flag indicates intent for multichannel *real* acquisition or processing type
        detection_preset = self.ui.detectionPresetCombo.currentText()
        classification_preset = self.ui.classificationPresetCombo.currentText()
        multichannel_processing_intended = (
            self.ui.multiChannelEnableCheck.isChecked() and detection_preset and classification_preset
        )

        if self.ui.mockCheckBox.isChecked():
            detection_stack, classification_stack, step_z = self._mockNeuronStacks(_future)
            if detection_stack is None:
                raise RuntimeError("Failed to load mock detection stack.")

            if classification_stack is not None and multichannel_processing_intended:
                working_stack = (detection_stack, classification_stack)
                multichannel = True
            else:
                working_stack = detection_stack
                multichannel = False
        else:  # --- Real Acquisition ---
            start_z = depth - 20 * µm
            stop_z = depth + 20 * µm
            # Use step_z = 1 * µm for real acquisition as previously defined

            if multichannel_processing_intended:
                logMsg(
                    f"Starting multichannel Z-stack acquisition: Detection='{detection_preset}', "
                    f"Classification='{classification_preset}'"
                )
                _future.waitFor(self.scopeDevice.loadPreset(detection_preset))
                detection_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z, slow_fallback=False),
                    timeout=100,
                ).getResult()

                _future.waitFor(self.scopeDevice.loadPreset(classification_preset))
                classification_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z, slow_fallback=False),
                    timeout=100,
                ).getResult()

                if len(detection_stack) != len(classification_stack):
                    logMsg(
                        f"Warning: Z-stack length mismatch: Detection ({len(detection_stack)}) != Classification"
                        f" ({len(classification_stack)}). Trimming to match.",
                        msgType="warning",
                    )
                    min_length = min(len(detection_stack), len(classification_stack))
                    detection_stack = detection_stack[:min_length]
                    classification_stack = classification_stack[:min_length]
            else:  # --- Single Channel Acquisition ---
                detection_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z)  # step_z is 1um here
                ).getResult()

            if multichannel_processing_intended:
                working_stack = (detection_stack, classification_stack)
                multichannel = True
            else:
                working_stack = detection_stack
                multichannel = False

        result = _future.waitFor(
            detect_neurons(
                working_stack,  # Prepared based on mock/real and single/multi
                autoencoder=autoencoder,
                classifier=classifier,
                xy_scale=pixel_size,  # Global pixel_size
                z_scale=step_z,  # Actual step_z from mock or real (1um for real)
                multichannel=multichannel,  # Actual flag for detect_neurons
            ),
            timeout=600,
        ).getResult()
        logMsg(f"Neuron detection finished. Found {len(result)} potential neurons.")
        # result = [(r[1], r[0], r[2]) for r in result]  # col-major getting in the way?
        self._current_detection_stack = detection_stack
        self._current_classification_stack = classification_stack
        self._unranked_cells = [Cell(r) for r in result]
        return result

    def _create_mock_stack_from_file(
        self, mock_file_path: str, base_frame: Frame, _future: Future
    ) -> tuple[list[Frame] | None, float | None]:
        """
        Loads a MetaArray file and converts it into a list of Frame objects.
        The Z positions and transforms of the mock frames are relative to the provided base_frame.
        Returns (stack_frames, step_z_microns) or (None, None) on failure.
        """
        if not mock_file_path:
            return None, None
        try:
            logMsg(f"Loading mock Z-stack from: {mock_file_path}")
            marr = MetaArray(file=mock_file_path)
            data = marr.asarray()
            info = marr.infoCopy()

            live_frame_global_transform = base_frame.globalTransform()
            live_frame_origin_global_xyz = np.array(base_frame.mapFromFrameToGlobal([0, 0, 0]))

            z_info = next((ax for ax in info if ax.get("name") == "Z"), None)
            if z_info and "values" in z_info:
                z_vals = z_info["values"]
                if len(z_vals) > 1:
                    step_z = abs(z_vals[1] - z_vals[0]) * m  # Assume meters
                    logMsg(f"Using Z step from mock file '{os.path.basename(mock_file_path)}': {step_z / µm:.2f} µm")
                elif len(z_vals) == 1:
                    logMsg(
                        f"Only one Z value in mock file '{os.path.basename(mock_file_path)}'. Assuming 1µm step.",
                        msgType="warning",
                    )
                    step_z = 1 * µm
                else:
                    logMsg(
                        f"No Z values in mock file '{os.path.basename(mock_file_path)}', using default 1µm step.",
                        msgType="warning",
                    )
                    step_z = 1 * µm
            else:
                logMsg(
                    f"Z info not in mock file '{os.path.basename(mock_file_path)}', using default 1µm step.",
                    msgType="warning",
                )
                step_z = 1 * µm

            pixel_size = self.cameraDevice.getPixelSize()[0]  # Assuming square pixels
            stack_frames = []
            current_mock_frame_global_z = live_frame_origin_global_xyz[2]  # Start Z from the live frame's depth

            for i in range(len(data)):
                mock_frame_transform = pg.SRTTransform3D(live_frame_global_transform.saveState())
                mock_frame_transform.setScale(pixel_size, pixel_size, step_z)
                z_offset = current_mock_frame_global_z - live_frame_origin_global_xyz[2]
                mock_frame_transform.translate(0, 0, z_offset)

                frame_info = {
                    "pixelSize": [pixel_size, pixel_size],
                    "depth": current_mock_frame_global_z,
                    "transform": mock_frame_transform.saveState(),
                }
                if "device" in base_frame.info():
                    frame_info["device"] = base_frame.info()["device"]

                frame = Frame(data[i], info=frame_info)
                stack_frames.append(frame)
                current_mock_frame_global_z += step_z
            return stack_frames, step_z
        except Exception:
            printExc(f"Failed to load or process mock file: {mock_file_path}")
            return None, None

    def _mockNeuronStacks(self, _future: Future) -> tuple[list[Frame] | None, list[Frame] | None, float]:
        logMsg("Using mock Z-stack file(s) for detection.")
        detection_stack = None
        classification_stack = None
        # Default step_z, will be updated by the first successfully loaded mock stack
        # or remain 1um if primary mock fails but code proceeds.
        step_z = 1 * µm

        with self.cameraDevice.ensureRunning():
            base_frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]

        # Load detection stack
        detection_mock_path = self.ui.mockFilePath.text()
        if detection_mock_path:
            detection_stack, det_step_z = self._create_mock_stack_from_file(detection_mock_path, base_frame, _future)
            if det_step_z is not None:
                step_z = det_step_z
        else:
            logMsg("Primary mock file path is empty.", msgType="warning")
            # detection_stack remains None, step_z remains default

        # Load classification stack if multichannel mock is enabled and path is provided
        if (
            self.ui.multiChannelEnableCheck.isChecked() and self.ui.mockCheckBox.isChecked()
        ):  # Redundant mockCheckBox check, but safe
            classification_mock_path = self.ui.mockClassificationFilePath.text()
            if classification_mock_path:
                # The base_frame and _future are passed again.
                # The step_z from the classification mock file will be returned by _create_mock_stack_from_file.
                # We prioritize step_z from the detection stack if both are loaded.
                # Or, one could enforce consistency or average, but for now, just log if different.
                classification_stack, class_step_z = self._create_mock_stack_from_file(
                    classification_mock_path, base_frame, _future
                )
                if class_step_z is not None and step_z != class_step_z and detection_stack is not None:
                    logMsg(
                        f"Z-step mismatch: Detection mock ({step_z/µm:.2f} µm) vs Classification mock ({class_step_z/µm:.2f} µm). Using detection Z-step.",
                        msgType="warning",
                    )
                # If detection_stack failed to load (det_step_z is None), but classification loaded, use its step_z.
                elif class_step_z is not None and detection_stack is None:
                    step_z = class_step_z
            else:
                raise ValueError("Multichannel mock enabled, but no classification mock file selected.")

        return detection_stack, classification_stack, step_z

    def _rankCells(self):
        """Pops the next unranked cell and opens a RankingWindow for it."""
        if not self._unranked_cells:
            # TODO teach the ranking window to detect cells (since I don't want this to be a future button)
            raise ValueError("No unranked cells available. Run detection first.")
        stack = self._current_classification_stack or self._current_detection_stack
        if not stack:
            raise ValueError("Stack data is missing, cannot rank. Run detection first.")
        if len(stack) <= 1:
            raise ValueError("Stack has only one frame.")
        save_dir = Path(self.ui.rankingSaveDirEdit.text())
        if not save_dir.is_dir():
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ValueError(f"Could not create ranking save directory: {save_dir}") from e

        # --- Get next cell ---
        # TODO separate ranking cells from targeting cells
        start, end = np.array(self._unranked_cells.pop(0))
        center_global = (start + end) / 2.0
        pixel_size = self.cameraDevice.getPixelSize()[0]  # Get current pixel size
        z_step = abs(stack[1].depth - stack[0].depth)

        # --- Create and show RankingWindow ---
        ranking_window = RankingWindow(
            main_window=self,  # Pass reference for cleanup
            cell_center=center_global,
            detection_stack=stack,
            classification_stack=self._current_classification_stack,
            pixel_size=pixel_size,
            z_step=z_step,
            save_dir=save_dir,
        )
        # Keep track of the window and connect its closed signal for cleanup
        self._open_ranking_windows.append(ranking_window)
        ranking_window.sigClosed.connect(self._ranking_window_closed)
        ranking_window.show()

    def _ranking_window_closed(self, window):
        """Callback to remove window reference when it's closed."""
        try:
            self._open_ranking_windows.remove(window)
        except ValueError:
            # Window might have already been removed or was never added properly
            printExc("Attempted to remove a ranking window reference that was not found.")

    @future_wrap
    def _autoTarget(self, _future):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        # If _unranked_cells is populated, use it. Otherwise, run detection.
        if not self._unranked_cells:
            logMsg("Need new potential cells; running detection")
            x, y = self._randomLocation()
            _future.waitFor(self.scopeDevice.setGlobalPosition((x, y)))
            # TODO don't know why this hangs when using waitFor, but it does
            depth_fut = self.scopeDevice.findSurfaceDepth(
                self.cameraDevice, searchDistance=50 * µm, searchStep=15 * µm  # , block=True, checkStopThrough=_future
            )
            depth = depth_fut.getResult() - 50 * µm  # Target below surface
            _future.checkStop()
            self.cameraDevice.setFocusDepth(depth)  # Set focus depth

            _future.waitFor(self._detectNeuronsZStack(), timeout=600)  # Side-effect: populates _unranked_cells
        if not self._unranked_cells:
            raise RuntimeError("Neuron detection ran, but no cells found for autoTarget.")

        neurons = self._unranked_cells

        # --- Calculate target ---
        centers = [(start + end) / 2 for start, end in np.array(neurons)]
        # TODO is this important to check? does the detection algorithm already guarantee this?
        target = next(
            (c for c in centers if all(np.linalg.norm(c - prev) > 35 * µm for prev in self._previousTargets)),
            None,
        )

        if target is None:
            raise RuntimeError("No suitable new target found among detected cells.")
        self._previousTargets.append(target)
        self.pipetteDevice.setTarget(target)
        logMsg(f"Setting pipette target to {target}")

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

    @future_wrap
    def _autopatchDemo(self, _future):
        self.sigWorking.emit(self.ui.autopatchDemoBtn)
        ppip: PatchPipette = self.patchPipetteDevice
        cleaning = None
        while True:
            try:
                if not ppip.isTipClean():
                    cleaning = ppip.setState("clean")
                cell = self._autopatchFindCell(_future)
                _future.setState("Autopatch: cell found")
                if cleaning is not None:
                    _future.setState("Autopatch: cleaning pipette")
                    _future.waitFor(cleaning, timeout=600)
                    cleaning = None
                ppip.setState("bath")
                ppip.clampDevice.resetTestPulseHistory()
                _future.setState("Autopatch: go above target")
                _future.waitFor(ppip.pipetteDevice.goAboveTarget("fast"))
                _future.setState("Autopatch: finding pipette tip")
                ppip.clampDevice.autoPipetteOffset()
                self._autopatchFindPipetteTip(_future)
                _future.setState("Autopatch: go approach")
                _future.waitFor(ppip.pipetteDevice.goApproach("fast"))
                cell.enableTracking()
                state = self._autopatchCellDetect(cell, _future)
                if state != "whole cell":
                    logMsg(f"Autopatch: Cell detect finished: {state}. Next!")
                    continue
                _future.setState("Autopatch: running task runner")
                self._autopatchRunTaskRunner(_future)

                self.scopeDevice.loadPreset('GFP')
                _future.sleep(5)
                self.scopeDevice.loadPreset('tdTomato')
                _future.sleep(5)
                self.scopeDevice.loadPreset('brightfield')

                _future.setState("Autopatch: resealing")
                _future.waitFor(ppip.setState("reseal"), timeout=None)
            except _future.StopRequested:
                raise
            except Exception as exc:
                printExc("Error during protocol:")
                continue

    def _autopatchCellDetect(self, cell, _future):
        try:
            ppip = self.patchPipetteDevice
            ppip.setState("cell detect")
            while True:
                if (state := ppip.getState().stateName) != "cell detect":
                    _future.setState(f"Autopatch: patch cell: {state}")
                    cell.enableTracking(False)
                    _future.waitFor(self.cameraDevice.moveCenterToGlobal(cell.position, "fast"))
                if state in ("whole cell", "bath", "broken", "fouled"):
                    break
                _future.sleep(0.1)
            return state
        finally:
            cell.enableTracking(False)
            pg.disconnect(cell.sigPositionChanged, self._updatePipetteTarget)

    def _autopatchFindCell(self, _future):
        if not self._unranked_cells:
            _future.setState("Autopatch: searching for cells")
            surf = _future.waitFor(self.cameraDevice.scopeDev.findSurfaceDepth(self.cameraDevice)).getResult()
            _future.waitFor(self.cameraDevice.setFocusDepth(surf - 60e-6, "fast"))
            z_stack = self._detectNeuronsZStack()
            z_stack.sigFinished.connect(self._handleDetectResults)
            _future.waitFor(z_stack, timeout=600)

        _future.setState("Autopatch: checking selected cell")
        cell = self._unranked_cells.pop(0)
        self.pipetteDevice.setTarget(cell.position)
        self._cell = cell
        cell.sigPositionChanged.connect(self._updatePipetteTarget)
        # stack = self._current_classification_stack or self._current_detection_stack
        # if (pos - margin) not in stack or (pos + margin) not in stack:
        # stack = None
        try:
            _future.waitFor(cell.initializeTracker(self.cameraDevice))
        except _future.StopRequested:
            raise
        except ValueError as e:
            if self._mockDemo:
                logMsg(f"Autopatch: Mocking cell despite {e}")
                return cell
            logMsg(f"Cell moved too much? {e}\nRetrying")
            return self._autopatchFindCell(_future)
        logMsg(f"Autopatch: Cell found at {cell.position}")
        return cell

    def _autopatchFindPipetteTip(self, _future):
        if self._mockDemo:
            logMsg("Autopatch: Mock pipette tip detection")
            return
        pip = self.pipetteDevice
        pos = pip.tracker.findTipInFrame()
        _future.waitFor(self.cameraDevice.moveCenterToGlobal(pos, "fast"))
        pos = pip.tracker.findTipInFrame()
        _future.waitFor(self.cameraDevice.moveCenterToGlobal(pos, "fast"))
        pos = pip.tracker.findTipInFrame()
        pip.resetGlobalPosition(pos)
        logMsg(f"Autopatch: Tip found at {pos}")

    def _autopatchRunTaskRunner(self, _future):
        man = self.module.manager
        ppip = self.patchPipetteDevice
        clampName = ppip.clampDevice.name()
        taskrunner: TaskRunner | None = None
        for mod in man.listModules():
            if not mod.startswith("Task Runner"):
                continue
            mod = man.getModule(mod)
            if clampName in mod.docks:
                taskrunner = mod
                break
        if taskrunner is None:
            logMsg(f"No task runner found that uses {clampName}")
            return

        expected_duration = taskrunner.sequenceInfo["period"] * taskrunner.sequenceInfo["totalParams"]
        _future.waitFor(
            # runInGuiThread(taskrunner.runSequence, store=True, storeDirHandle=self.dh), timeout=expected_duration
            runInGuiThread(taskrunner.runSequence, store=False), timeout=expected_duration*2
        )
        logMsg("Autopatch: Task runner sequence completed.")

    def saveConfig(self):
        geom = self.geometry()
        config = {
            'geometry': [geom.x(), geom.y(), geom.width(), geom.height()],
        }
        getManager().writeConfigFile(config, self._configFileName())

    def loadConfig(self):
        config = getManager().readConfigFile(self._configFileName())
        if 'geometry' in config:
            geom = Qt.QRect(*config['geometry'])
            self.setGeometry(geom)

    def _configFileName(self):
        return os.path.join('modules', f'{self.module.name}.cfg')


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
        self.ui.saveConfig()
        if not fromUi:
            self.ui.quit()
        super().quit()
