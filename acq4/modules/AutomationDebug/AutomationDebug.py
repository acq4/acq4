from __future__ import annotations

import datetime
import os
from pathlib import Path

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
from acq4.util.debug import logMsg, printExc
from acq4.util.future import Future, future_wrap
from acq4.util.imaging import Frame
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.target import TargetBox
from acq4.util.threadrun import runInGuiThread
from pyqtgraph.units import µm, m

UiTemplate = Qt.importTemplate(".window")


class RankingWindow(Qt.QWidget):
    sigClosed = Qt.Signal(object) # emit self when closed

    def __init__(self, main_window: AutomationDebugWindow, cell_center, detection_stack, classification_stack, pixel_size, z_step, save_dir):
        super().__init__()
        self.main_window = main_window # Keep reference for cleanup
        self.cell_center = cell_center
        self.detection_stack = detection_stack
        self.classification_stack = classification_stack # May be None
        self.pixel_size = pixel_size
        self.z_step = z_step
        self.save_dir = save_dir
        self.rating = None
        self.save_format = 'NWB' # Default format

        self.setWindowTitle(f"Rank Cell @ ({cell_center[0]/µm:.0f}, {cell_center[1]/µm:.0f}, {cell_center[2]/µm:.0f}) µm")
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)

        # --- Image Display ---
        self.image_views = []
        self.image_layout = Qt.QHBoxLayout()
        self.layout.addLayout(self.image_layout)
        # TODO: Create 5 ImageView widgets and add them to image_layout
        # TODO: Display initial slices (e.g., center +/- 20um, +/- 10um, 0um)

        # --- Z Slider ---
        self.z_slider = Qt.QSlider(Qt.Qt.Orientation.Horizontal)
        # TODO: Set slider range based on stack depth
        # TODO: Connect slider valueChanged signal to update displayed slices
        self.layout.addWidget(self.z_slider)

        # --- Rating Buttons ---
        self.rating_layout = Qt.QHBoxLayout()
        self.rating_group = Qt.QButtonGroup(self)
        ratings = {
            1: "Not a cell",
            2: "Unpatchable",
            3: "Barely patchable",
            4: "Average",
            5: "Excellent",
        }
        for i in range(1, 6):
            btn = Qt.QPushButton(f"{i}: {ratings[i]}")
            btn.setCheckable(True)
            self.rating_group.addButton(btn, i)
            self.rating_layout.addWidget(btn)
        self.layout.addLayout(self.rating_layout)
        self.rating_group.buttonClicked[int].connect(self._set_rating)

        # --- Format Selection ---
        self.format_layout = Qt.QHBoxLayout()
        self.format_group = Qt.QButtonGroup(self)
        self.nwb_radio = Qt.QRadioButton("NWB")
        self.metaarray_radio = Qt.QRadioButton("MetaArray")
        self.nwb_radio.setChecked(True)
        self.format_group.addButton(self.nwb_radio)
        self.format_group.addButton(self.metaarray_radio)
        self.format_layout.addWidget(Qt.QLabel("Save Format:"))
        self.format_layout.addWidget(self.nwb_radio)
        self.format_layout.addWidget(self.metaarray_radio)
        self.layout.addLayout(self.format_layout)
        self.nwb_radio.toggled.connect(lambda checked: self._set_format('NWB') if checked else None)
        self.metaarray_radio.toggled.connect(lambda checked: self._set_format('MetaArray') if checked else None)


        # --- Action Buttons ---
        self.action_layout = Qt.QHBoxLayout()
        self.skip_button = Qt.QPushButton("Skip")
        self.save_button = Qt.QPushButton("Save & Next")
        self.save_button.setEnabled(False) # Enable only when rating is selected
        self.action_layout.addWidget(self.skip_button)
        self.action_layout.addWidget(self.save_button)
        self.layout.addLayout(self.action_layout)

        self.skip_button.clicked.connect(self.close) # Just close the window
        self.save_button.clicked.connect(self._save_and_close)

        # TODO: Implement image loading and display logic
        # TODO: Implement slider logic
        self._load_cell_data() # Placeholder call

    def _set_rating(self, rating_id):
        self.rating = rating_id
        self.save_button.setEnabled(True)

    def _set_format(self, fmt):
        self.save_format = fmt

    def _load_cell_data(self):
        # Placeholder: This is where you'd load the 5 slices into self.image_views
        # and configure the self.z_slider based on self.detection_stack depth.
        logMsg("RankingWindow: _load_cell_data() - Implement me!")
        pass

    def _save_and_close(self):
        if self.rating is None:
            logMsg("No rating selected.", msgType='warning')
            # Optionally show a message box to the user
            return

        logMsg(f"Cell rated {self.rating}, saving as {self.save_format}...")
        try:
            volume_data, metadata = self._extract_cell_volume(self.cell_center, size_um=20)
            self._save_ranked_cell(volume_data, metadata, self.rating, self.save_format, self.save_dir)
        except Exception:
            printExc(f"Failed to extract or save cell data for cell at {self.cell_center}")
            logMsg(f"Error saving cell data for cell at {self.cell_center}", msgType='error')
            # Optionally show error message to user before closing
        finally:
            self.close() # Close the window regardless of save success/failure

    def closeEvent(self, event):
        """Emit signal when closed."""
        self.sigClosed.emit(self)
        super().closeEvent(event)

    # --- Data Extraction and Saving Logic (Moved from AutomationDebugWindow) ---

    def _extract_cell_volume(self, center_global, size_um=20):
        """Extracts a 3D numpy array centered on the cell."""
        if not self.detection_stack:
            raise ValueError("Detection stack is not available.")

        # Use the stack data passed during initialization
        stack_data = np.array([frame.data() for frame in self.detection_stack])
        frame_shape = stack_data.shape[1:] # (rows, cols) or (y, x)
        n_frames = stack_data.shape[0]

        # Get transform info from the first frame (assuming it's consistent)
        frame0 = self.detection_stack[0]
        # Use pixel_size passed during initialization
        if self.pixel_size is None:
             raise ValueError("Pixel size information missing.")
        pixel_size_m = self.pixel_size # Assume square pixels in meters

        # Convert size in µm to pixels/frames
        size_m = size_um * 1e-6
        size_px = int(np.ceil(size_m / pixel_size_m))
        # Ensure odd size for centering
        if size_px % 2 == 0:
            size_px += 1
        half_size_px = size_px // 2

        # Find the Z index closest to the center
        depths = np.array([frame.depth for frame in self.detection_stack])
        center_z_idx = np.argmin(np.abs(depths - center_global[2]))

        # Use z_step passed during initialization
        z_step_m = self.z_step
        size_z_frames = int(np.ceil(size_m / z_step_m))
        if size_z_frames % 2 == 0:
             size_z_frames += 1
        half_size_z = size_z_frames // 2

        # Map global center to the coordinates of the center frame
        center_frame = self.detection_stack[center_z_idx]
        center_frame_coords = center_frame.mapFromGlobal(center_global) # Returns (x, y) in frame pixels
        center_x_px, center_y_px = int(round(center_frame_coords[0])), int(round(center_frame_coords[1]))

        # Calculate slice boundaries, clamping to stack dimensions
        z_start = max(0, center_z_idx - half_size_z)
        z_end = min(n_frames, center_z_idx + half_size_z + 1)
        y_start = max(0, center_y_px - half_size_px)
        y_end = min(frame_shape[0], center_y_px + half_size_px + 1)
        x_start = max(0, center_x_px - half_size_px)
        x_end = min(frame_shape[1], center_x_px + half_size_px + 1)

        # Extract volume
        volume = stack_data[z_start:z_end, y_start:y_end, x_start:x_end]

        # --- Create Metadata ---
        origin_frame = self.detection_stack[z_start]
        corner_global_pos = origin_frame.mapToGlobal((x_start, y_start))

        metadata = {
            'timestamp': datetime.datetime.now().isoformat(),
            'center_global': center_global.tolist(),
            'size_um': size_um,
            'shape': volume.shape, # (z, y, x)
            'pixel_size_m': pixel_size_m,
            'z_step_m': z_step_m,
            'voxel_origin_global': corner_global_pos.tolist() + [origin_frame.depth], # (x, y, z) of voxel [0,0,0]
            'source_detection_stack_info': [f.info() for f in self.detection_stack[z_start:z_end]], # Basic info
            'source_classification_stack_info': None,
        }
        # Use classification_stack passed during initialization
        if self.classification_stack and z_start < len(self.classification_stack):
             metadata['source_classification_stack_info'] = [
                 f.info() for f in self.classification_stack[z_start:z_end]
             ]

        logMsg(f"Extracted volume shape: {volume.shape} centered near {center_global}")
        return volume, metadata

    def _save_ranked_cell(self, volume_data, metadata, rating, save_format, save_dir):
        """Saves the extracted cell volume and metadata."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        cell_id = f"cell_{timestamp}_rating_{rating}"
        filename_base = save_dir / cell_id

        metadata['rating'] = rating
        metadata['save_format'] = save_format
        metadata['cell_id'] = cell_id

        if save_format == 'MetaArray':
            info = [
                {'name': 'Z', 'units': 'm', 'values': np.arange(volume_data.shape[0]) * metadata['z_step_m'] + metadata['voxel_origin_global'][2]},
                {'name': 'Y', 'units': 'm', 'values': np.arange(volume_data.shape[1]) * metadata['pixel_size_m'] + metadata['voxel_origin_global'][1]},
                {'name': 'X', 'units': 'm', 'values': np.arange(volume_data.shape[2]) * metadata['pixel_size_m'] + metadata['voxel_origin_global'][0]},
                metadata,
            ]
            ma = MetaArray(volume_data, info=info)
            filepath = f"{filename_base}.ma"
            try:
                ma.write(filepath)
                logMsg(f"Saved cell data to {filepath}")
            except Exception:
                printExc(f"Failed to write MetaArray file: {filepath}")
                logMsg(f"Error writing MetaArray file: {filepath}", msgType='error')
                # Re-raise or handle more gracefully?
                raise

        elif save_format == 'NWB':
            logMsg("NWB saving not implemented yet.", msgType='warning')
            filepath = f"{filename_base}.nwb"
            logMsg(f"Placeholder: Would save cell data to {filepath}")
            # TODO: Implement NWB saving logic here using pynwb

        else:
            logMsg(f"Unknown save format: {save_format}", msgType='error')
            raise ValueError(f"Unknown save format: {save_format}")


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
        self._unranked_cells = [] # List of (start, end) tuples from detection
        self._ranked_cells = {} # Dict mapping cell ID (e.g., timestamp) to ranking info
        self._current_detection_stack = None
        self._current_classification_stack = None # May be None
        self._previousTargets = [] # Used by autoTarget
        self._open_ranking_windows = [] # Keep track of open windows

        self.ui.clearBtn.clicked.connect(self.clearBoundingBoxes)
        self.ui.zStackDetectBtn.setOpts(future_producer=self._detectNeuronsZStackWrapper, stoppable=True)
        self.ui.zStackDetectBtn.sigFinished.connect(self._handleDetectWrapperResults)
        self.ui.testUIBtn.setOpts(future_producer=self._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._handleDetectWrapperResults) # Use wrapper handler for consistency

        self.ui.multiChannelEnableCheck.toggled.connect(self._updateMultiChannelState)
        self.ui.motionPlannerSelector.currentIndexChanged.connect(self._changeMotionPlanner)

        # Connect regular button click
        self.ui.rankCellsBtn.clicked.connect(self._rankCells)
        self.ui.selectRankDirBtn.clicked.connect(self._selectRankDir)

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
        # Set default ranking dir
        default_rank_dir = Path(self.module.manager.getBaseDir().name()) / "ranked_cells"
        self.ui.rankingSaveDirEdit.setText(str(default_rank_dir))
        self._populatePresetCombos()

    def _selectRankDir(self):
        path = Qt.QFileDialog.getExistingDirectory(self, "Select Directory to Save Ranked Cells", self.ui.rankingSaveDirEdit.text())
        if path:
            self.ui.rankingSaveDirEdit.setText(path)

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
        # Rank button is now a regular button, manage its state based on _unranked_cells?
        # self.ui.rankCellsBtn.setEnabled(len(self._unranked_cells) > 0) # Example: enable only if cells exist

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
        self._unranked_cells = [] # Clear previous detections
        self._current_detection_stack = None
        self._current_classification_stack = None

    def _handleDetectWrapperResults(self, future: Future) -> None:
        """Handles results from _detectNeuronsZStackWrapper or _testUI."""
        try:
            if future.wasInterrupted():
                logMsg("Detection/Test interrupted.")
                return
            result = future.getResult()
            if isinstance(result, tuple) and len(result) == 3: # From _detectNeuronsZStackWrapper
                bounding_boxes, det_stack, class_stack = result
                self._current_detection_stack = det_stack
                self._current_classification_stack = class_stack
            elif isinstance(result, list): # From _testUI
                 bounding_boxes = result
                 self._current_detection_stack = None # Cannot rank test UI results yet
                 self._current_classification_stack = None
            else:
                logMsg(f"Unexpected result type from detection future: {type(result)}", msgType='warning')
                return

            self._unranked_cells = bounding_boxes
            logMsg(f"Detection complete. Found {len(self._unranked_cells)} potential cells. Ready for ranking.")
            self._displayBoundingBoxes(self._unranked_cells)

        except Exception:
            printExc("Error handling detection results:")
        finally:
            self.sigWorking.emit(False)


    def _displayBoundingBoxes(self, bounding_boxes):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        self.clearBoundingBoxes() # Clear previous boxes visually and state
        for start, end in bounding_boxes:
            box = TargetBox(start, end)
            cam_win.addItem(box)
            # TODO: Re-evaluate if this connection is still needed or causes issues
            # self.scopeDevice.sigGlobalTransformChanged.connect(box.noticeFocusChange)
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
    def _detectNeuronsZStackWrapper(self, _future: Future) -> tuple[list, list[Frame] | None, list[Frame] | None] | list:
        """Wraps _detectNeuronsZStack to emit working signal and return stacks."""
        self.sigWorking.emit(self.ui.zStackDetectBtn)
        # Clear previous results before starting detection
        runInGuiThread(self.clearBoundingBoxes)
        self._unranked_cells = []
        self._current_detection_stack = None
        self._current_classification_stack = None
        try:
            result, det_stack, class_stack = _future.waitFor(self._detectNeuronsZStack(_future)).getResult()
            return result, det_stack, class_stack
        except Exception:
            printExc("Error during neuron detection Z-stack acquisition/processing:")
            # Return empty results on failure to avoid crashing downstream processing
            return [], None, None


    def _detectNeuronsZStack(self, _future: Future) -> tuple[list, list[Frame], list[Frame] | None]:
        """Acquires Z-stack(s) and runs neuron detection. Returns (bboxes, detection_stack, classification_stack)."""
        from acq4_automation.object_detection import detect_neurons

        man = self.module.manager
        autoencoder = man.config.get("misc", {}).get("autoencoderPath", None)
        classifier = man.config.get("misc", {}).get("classifierPath", None)
        pixel_size = self.cameraDevice.getPixelSize()[0]
        z_scale = step_z = 1 * µm
        depth = self.cameraDevice.getFocusDepth()
        detection_stack = None
        classification_stack = None # Initialize as None

        if self.ui.mockCheckBox.isChecked() and self.ui.mockFilePath.text():
            # --- Mock Acquisition ---
            logMsg("Using mock Z-stack file for detection.")
            with self.cameraDevice.ensureRunning():
                # Acquire a single frame to get the camera transform and pixel size
                real_frame = _future.waitFor(self.cameraDevice.acquireFrames(1)).getResult()[0]
            pixel_size = self.cameraDevice.getPixelSize()[0] # Update pixel size based on current state
            base_xform = real_frame.globalTransform()
            base_position = np.array(real_frame.mapFromFrameToGlobal((0, 0, 0))) # Use frame mapping
            # Load the MetaArray file
            mock_file_path = self.ui.mockFilePath.text()
            marr = MetaArray(file=mock_file_path)
            data = marr.asarray()
            info = marr.infoCopy()
            # Try to get z_step from metaarray info, default to 1um
            z_info = next((ax for ax in info if ax.get('name') == 'Z'), None)
            if z_info and 'values' in z_info:
                 z_vals = z_info['values']
                 if len(z_vals) > 1:
                     step_z = abs(z_vals[1] - z_vals[0]) * m # Assume meters if unitless
                     logMsg(f"Using Z step from mock file: {step_z / µm:.2f} µm")
                 else:
                     logMsg("Only one Z value found in mock file, using default step.", msgType='warning')
                     step_z = 1 * µm
            else:
                 logMsg("Z information not found in mock file info, using default step.", msgType='warning')
                 step_z = 1 * µm

            # Create Frame objects, mapping Z based on step_z
            detection_stack = []
            current_z = base_position[2] # Start Z from the real frame's depth
            for i in range(len(data)):
                 frame_to_global = base_xform
                 # Adjust Z position in the transform
                 frame_to_global.translate(0, 0, current_z - base_position[2])
                 frame_info = {
                     "pixelSize": [pixel_size, pixel_size],
                     "depth": current_z, # Assign calculated depth
                     "transform": frame_to_global.saveState(),
                 }
                 frame = Frame(data[i], info=frame_info)
                 detection_stack.append(frame)
                 current_z += step_z # Increment Z for the next frame

            # TODO: Handle multichannel mock file path later (needs two files or specific format)
            classification_stack = None # No classification stack for mock yet
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
                if detection_stack is None or classification_stack is None:
                     raise RuntimeError("Stack acquisition failed for one or both channels.") # Should not happen if futures succeeded

                if len(detection_stack) != len(classification_stack):
                    logMsg(
                        f"Warning: Z-stack length mismatch: Detection ({len(detection_stack)}) != "
                        f"Classification ({len(classification_stack)}). Proceeding with detection on detection stack only.",
                        msgType='warning'
                    )
                    # Attempt to use only the detection stack if lengths mismatch significantly?
                    # For now, just warn. Detection might fail or give weird results.
                else:
                    # Check Z positions (assuming frame.depth exists and is reliable)
                    z_tolerance = 0.1 * step_z # Allow 10% of step size difference
                    alignment_ok = True
                    for i, (f1, f2) in enumerate(zip(detection_stack, classification_stack)):
                        f1_depth = getattr(f1, 'depth', None)
                        f2_depth = getattr(f2, 'depth', None)
                        if f1_depth is None or f2_depth is None:
                            logMsg(f"Warning: Cannot verify Z alignment at frame {i}, missing 'depth' attribute.", msgType='warning')
                            continue # Skip check for this frame if depth is missing

                        if abs(f1_depth - f2_depth) > z_tolerance:
                            f1_pos = f1.info().get('transform', {}).get('pos', (None, None, None))
                            f2_pos = f2.info().get('transform', {}).get('pos', (None, None, None))
                            logMsg(
                                f"Warning: Z-position mismatch at frame {i}: "
                                f"Detection ({f1_depth/µm:.2f} µm, pos_z={f1_pos[2]}) != "
                                f"Classification ({f2_depth/µm:.2f} µm, pos_z={f2_pos[2]}). "
                                f"Tolerance: {z_tolerance/µm:.2f} µm",
                                msgType='warning'
                            )
                            alignment_ok = False
                            # Don't raise an error, just warn. Allow detection to proceed.
                    if alignment_ok:
                        logMsg("Z-stack alignment verified.")
                    else:
                        logMsg("Z-stack alignment issues detected (see warnings).", msgType='warning')

            else:
                # --- Single Channel Acquisition ---
                logMsg(f"Starting single channel Z-stack acquisition ({start_z/µm:.1f} - {stop_z/µm:.1f} µm, step {step_z/µm:.1f} µm)")
                detection_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z)
                ).getResult()
                logMsg("Single channel acquisition complete.")

        # --- Call Detection ---
        if not detection_stack:
             logMsg("Detection stack is empty or acquisition failed. Cannot run detection.", msgType='error')
             return [], detection_stack, classification_stack # Return empty results

        logMsg("Running neuron detection...")
        # Use classification stack only if it exists and lengths match (or close enough?)
        use_classification = bool(classification_stack) and len(classification_stack) == len(detection_stack)
        if use_classification:
            logMsg("Using multichannel input for detection.")
            working_stack = (detection_stack, classification_stack)
        else:
            if classification_stack:
                 logMsg("Classification stack exists but will not be used for detection due to length mismatch or other issues.", msgType='warning')
            logMsg("Using single channel (detection) input for detection.")
            working_stack = detection_stack

        try:
            result = _future.waitFor(
                detect_neurons(
                    working_stack,
                    autoencoder=autoencoder,
                    classifier=classifier,
                    xy_scale=pixel_size,
                    z_scale=step_z,  # Use the actual step size
                    multichannel=use_classification,
                ),
                timeout=600,
            ).getResult()
            logMsg(f"Neuron detection finished. Found {len(result)} potential neurons.")
            return result, detection_stack, classification_stack
        except Exception as e:
            printExc("Error during detect_neurons call:")
            logMsg(f"Neuron detection failed: {e}", msgType='error')
            return [], detection_stack, classification_stack # Return empty results on failure

    @future_wrap
    def _rankCells(self, _future: Future):
        """Presents the next unranked cell to the user for ranking."""
        self.sigWorking.emit(self.ui.rankCellsBtn)
        save_dir = Path(self.ui.rankingSaveDirEdit.text())
        if not save_dir.is_dir():
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                printExc(f"Could not create ranking save directory: {save_dir}")
                logMsg(f"Error: Could not create save directory {save_dir}. Please select a valid directory.", msgType='error')
                logMsg(f"Error: Could not create save directory {save_dir}. Please select a valid directory.", msgType='error')
                # TODO: Show error dialog to user?
                return # Need a valid directory to save

        if not self._unranked_cells:
            logMsg("No unranked cells available. Run detection first.", msgType='warning')
            # TODO: Show message to user?
            return

        if not self._current_detection_stack:
             logMsg("Detection stack data is missing, cannot rank. Run detection first.", msgType='error')
             # TODO: Show error dialog to user?
             return

        # --- Get next cell ---
        # Pop the first one. This modifies the list in place.
        cell_bounds = self._unranked_cells.pop(0)
        start, end = np.array(cell_bounds)
        center_global = (start + end) / 2.0

        logMsg(f"Ranking cell at {center_global}. {len(self._unranked_cells)} remaining.")

        # --- Prepare data for dialog ---
        pixel_size = self.cameraDevice.getPixelSize()[0] # Get current pixel size
        # Estimate z_step from the stack if possible
        if len(self._current_detection_stack) > 1:
             z_step = abs(self._current_detection_stack[1].depth - self._current_detection_stack[0].depth)
        else:
             z_step = 1 * µm # Default if only one frame
             logMsg("Only one frame in detection stack, assuming 1µm Z step for ranking.", msgType='warning')

        # --- Show Dialog ---
        dialog = RankingDialog(
            cell_center=center_global,
            detection_stack=self._current_detection_stack,
            classification_stack=self._current_classification_stack,
            pixel_size=pixel_size,
            z_step=z_step,
            parent=self,
        )
        accepted = dialog.exec()

        if accepted:
            rating, save_format = dialog.getResult()
            logMsg(f"Cell rated {rating}, saving as {save_format}...")
            try:
                volume_data, metadata = self._extract_cell_volume(center_global, size_um=20)
                self._save_ranked_cell(volume_data, metadata, rating, save_format, save_dir)
                # TODO: Add to _ranked_cells list/dict
            except Exception:
                printExc(f"Failed to extract or save cell data for cell at {center_global}")
                logMsg(f"Error saving cell data for cell at {center_global}", msgType='error')
                # Put the cell back? Or just log the error? For now, just log.
        else:
            logMsg("Cell skipped.")

        # Update the display of bounding boxes (remove the one just processed)
        self._displayBoundingBoxes(self._unranked_cells) # Re-display remaining boxes

    def _handleRankCellsFinish(self, fut: Future):
        self.sigWorking.emit(False)
        if fut.didFail():
            logMsg("Cell ranking process failed.", msgType='error')
            printExc("Error during cell ranking:")
        else:
            logMsg("Cell ranking finished for this cell.")
            if self._unranked_cells:
                 logMsg(f"{len(self._unranked_cells)} cells remaining in this batch.")
            else:
                 logMsg("All detected cells in this batch have been processed.")


    def _extract_cell_volume(self, center_global, size_um=20):
        """Extracts a 3D numpy array centered on the cell."""
        if not self._current_detection_stack:
            raise ValueError("Detection stack is not available.")

        stack_data = np.array([frame.data() for frame in self._current_detection_stack])
        frame_shape = stack_data.shape[1:] # (rows, cols) or (y, x)
        n_frames = stack_data.shape[0]

        # Get transform info from the first frame (assuming it's consistent)
        frame0 = self._current_detection_stack[0]
        pixel_size = frame0.info().get('pixelSize', [None, None])
        if pixel_size[0] is None:
             raise ValueError("Pixel size information missing from frame.")
        pixel_size_m = pixel_size[0] # Assume square pixels in meters

        # Convert size in µm to pixels/frames
        size_m = size_um * 1e-6
        size_px = int(np.ceil(size_m / pixel_size_m))
        # Ensure odd size for centering
        if size_px % 2 == 0:
            size_px += 1
        half_size_px = size_px // 2

        # Find the Z index closest to the center
        depths = np.array([frame.depth for frame in self._current_detection_stack])
        center_z_idx = np.argmin(np.abs(depths - center_global[2]))

        # Estimate Z step if possible, otherwise assume 1um
        if len(depths) > 1:
            z_step_m = np.mean(np.diff(depths)) # Use mean difference
        else:
            z_step_m = 1e-6
        size_z_frames = int(np.ceil(size_m / z_step_m))
        if size_z_frames % 2 == 0:
             size_z_frames += 1
        half_size_z = size_z_frames // 2

        # Map global center to the coordinates of the center frame
        center_frame = self._current_detection_stack[center_z_idx]
        center_frame_coords = center_frame.mapFromGlobal(center_global) # Returns (x, y) in frame pixels
        center_x_px, center_y_px = int(round(center_frame_coords[0])), int(round(center_frame_coords[1]))

        # Calculate slice boundaries, clamping to stack dimensions
        z_start = max(0, center_z_idx - half_size_z)
        z_end = min(n_frames, center_z_idx + half_size_z + 1)
        y_start = max(0, center_y_px - half_size_px)
        y_end = min(frame_shape[0], center_y_px + half_size_px + 1)
        x_start = max(0, center_x_px - half_size_px)
        x_end = min(frame_shape[1], center_x_px + half_size_px + 1)

        # Extract volume
        volume = stack_data[z_start:z_end, y_start:y_end, x_start:x_end]

        # --- Create Metadata ---
        # Get transform of the center pixel of the extracted volume's center frame
        volume_center_z_idx_local = center_z_idx - z_start
        volume_center_y_px_local = center_y_px - y_start
        volume_center_x_px_local = center_x_px - x_start

        # We need the global position of the corner (0,0,0) of the extracted volume
        # Find the frame corresponding to z_start
        origin_frame = self._current_detection_stack[z_start]
        # Map the local pixel coords (x_start, y_start) in that frame to global
        corner_global_pos = origin_frame.mapToGlobal((x_start, y_start))

        metadata = {
            'timestamp': datetime.datetime.now().isoformat(),
            'center_global': center_global.tolist(),
            'size_um': size_um,
            'shape': volume.shape, # (z, y, x)
            'pixel_size_m': pixel_size_m,
            'z_step_m': z_step_m,
            'voxel_origin_global': corner_global_pos.tolist() + [origin_frame.depth], # (x, y, z) of voxel [0,0,0]
            'source_detection_stack_info': [f.info() for f in self._current_detection_stack[z_start:z_end]], # Basic info
            # Add classification stack info if available
            'source_classification_stack_info': None,
        }
        if self._current_classification_stack and z_start < len(self._current_classification_stack):
             # Assume alignment holds for the extracted region
             metadata['source_classification_stack_info'] = [
                 f.info() for f in self._current_classification_stack[z_start:z_end]
             ]

        logMsg(f"Extracted volume shape: {volume.shape} centered near {center_global}")
        return volume, metadata

    def _save_ranked_cell(self, volume_data, metadata, rating, save_format, save_dir):
        """Saves the extracted cell volume and metadata."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        cell_id = f"cell_{timestamp}_rating_{rating}"
        filename_base = save_dir / cell_id

        metadata['rating'] = rating
        metadata['save_format'] = save_format
        metadata['cell_id'] = cell_id

        if save_format == 'MetaArray':
            # Create MetaArray info structure
            info = [
                {'name': 'Z', 'units': 'm', 'values': np.arange(volume_data.shape[0]) * metadata['z_step_m'] + metadata['voxel_origin_global'][2]},
                {'name': 'Y', 'units': 'm', 'values': np.arange(volume_data.shape[1]) * metadata['pixel_size_m'] + metadata['voxel_origin_global'][1]},
                {'name': 'X', 'units': 'm', 'values': np.arange(volume_data.shape[2]) * metadata['pixel_size_m'] + metadata['voxel_origin_global'][0]},
                metadata,  # Add the rest of the metadata dict
            ]
            ma = MetaArray(volume_data, info=info)
            filepath = f"{filename_base}.ma"
            try:
                ma.write(filepath)
                logMsg(f"Saved cell data to {filepath}")
            except Exception:
                printExc(f"Failed to write MetaArray file: {filepath}")
                logMsg(f"Error writing MetaArray file: {filepath}", msgType='error')

        elif save_format == 'NWB':
            # Placeholder for NWB saving logic
            # Requires pynwb library
            logMsg("NWB saving not implemented yet.", msgType='warning')
            filepath = f"{filename_base}.nwb"
            logMsg(f"Placeholder: Would save cell data to {filepath}")
            # Example structure (needs pynwb):
            # from pynwb import NWBHDF5IO, NWBFile
            # from pynwb.ophys import TwoPhotonSeries, OpticalChannel, ImageSegmentation, PlaneSegmentation
            # from pynwb.device import Device
            #
            # nwbfile = NWBFile(...)
            # device = Device(name=self.cameraDevice.name()) # Or more specific info
            # nwbfile.add_device(device)
            # optical_channel = OpticalChannel(...)
            # imaging_plane = nwbfile.create_imaging_plane(...)
            # image_series = TwoPhotonSeries(
            #      name=cell_id,
            #      description=f"Ranked cell volume, rating {rating}",
            #      data=volume_data,
            #      imaging_plane=imaging_plane,
            #      rate=1.0, # Fake rate
            #      unit='raw',
            #      dimension=list(volume_data.shape), # Check order
            #      resolution=metadata['pixel_size_m'], # Check if this is right place
            #      starting_time=0.0,
            #      # Need to map metadata['voxel_origin_global'] and z_step correctly
            # )
            # nwbfile.add_acquisition(image_series)
            # # Add metadata as needed, potentially in processing modules or general fields
            # with NWBHDF5IO(filepath, 'w') as io:
            #      io.write(nwbfile)

        else:
            logMsg(f"Unknown save format: {save_format}", msgType='error')

    @future_wrap
    def _autoTarget(self, _future):
        self.sigWorking.emit(self.ui.autoTargetBtn)
        # --- Modification for autoTarget ---
        # Instead of using _previousBoxBounds directly, check _unranked_cells
        # If _unranked_cells is populated, use it. Otherwise, run detection.
        possibly_stale = False
        if self._unranked_cells:
            logMsg("Using existing detected cells for autoTarget.")
            possibly_stale = True # Could be stale if user moved stage
            neurons = self._unranked_cells # Use the current list of unranked cells
        else:
            logMsg("No cells found, running detection for autoTarget.")
            x, y = self._randomLocation()
            _future.waitFor(self.scopeDevice.setGlobalPosition((x, y))) # TODO: Check if stage move invalidates stack
            # TODO don't know why this hangs when using waitFor, but it does
            depth_fut = self.scopeDevice.findSurfaceDepth(
                self.cameraDevice, searchDistance=50 * µm, searchStep=15 * µm # Non-blocking find surface
            )
            depth = _future.waitFor(depth_fut).getResult() # Wait for surface depth future
            if depth is None:
                 logMsg("Failed to find surface depth for autoTarget.", msgType='warning')
                 # Maybe try a default depth or abort? Abort for now.
                 raise RuntimeError("Could not find surface depth.")

            depth -= 50 * µm # Target below surface
            self.cameraDevice.setFocusDepth(depth) # Set focus depth

            # Run detection using the wrapper to get stacks and handle results
            detect_future = self._detectNeuronsZStackWrapper()
            _future.waitFor(detect_future)
            if detect_future.wasInterrupted() or detect_future.didFail():
                 raise RuntimeError("Neuron detection failed or was interrupted during autoTarget.")
            # Results are handled by _handleDetectWrapperResults, populating _unranked_cells
            if not self._unranked_cells:
                 raise RuntimeError("Neuron detection ran, but no cells found for autoTarget.")
            neurons = self._unranked_cells # Use the newly detected cells

        # --- Calculate target ---
        centers = [(start + end) / 2 for start, end in np.array(neurons)]
        target = next(
            (c for c in centers
             if not self._previousTargets or all(np.linalg.norm(c - prev) > 35 * µm for prev in self._previousTargets)),
            None # Default None if no suitable target found
        )

        if target is None:
            logMsg("No suitable new target found among detected cells.")
            if possibly_stale:
                logMsg("Cell locations might be stale. Clearing and re-running detection.")
                runInGuiThread(self.clearBoundingBoxes) # Clear visual boxes and state
                # Re-run the autoTarget future
                new_target_future = self._autoTarget()
                _future.waitFor(new_target_future) # Wait for the new future
                # The result of the original future will be the result of the new one
                return new_target_future.getResult()
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
