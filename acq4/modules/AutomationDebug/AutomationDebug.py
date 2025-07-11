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
import pyqtgraph as pg
from coorx import SRT3DTransform, TransposeTransform, TTransform
from pyqtgraph.units import µm, m

UiTemplate = Qt.importTemplate(".window")


class RankingWindow(Qt.QWidget):
    sigClosed = Qt.Signal(object)  # emit self when closed

    def __init__(
        self,
        main_window: AutomationDebugWindow,
        cell_center,
        detection_stack,
        classification_stack,
        pixel_size,
        z_step,
        save_dir,
    ):
        super().__init__()
        self.main_window = main_window  # Keep reference for cleanup
        self.cell_center = cell_center
        self.detection_stack = detection_stack
        self.classification_stack = classification_stack  # May be None
        self.pixel_size = pixel_size
        self.z_step = z_step
        self.save_dir = save_dir
        self.rating = None
        self.save_format = "MetaArray"
        self.volume_data = None
        self.depths = None

        self.setWindowTitle(
            f"Rank Cell @ ({cell_center[0]/µm:.0f}, {cell_center[1]/µm:.0f}, {cell_center[2]/µm:.0f}) µm"
        )
        self.layout = Qt.QVBoxLayout()
        self.setLayout(self.layout)

        # --- Image Display ---
        self.image_views = []
        self.image_layout = Qt.QHBoxLayout()
        self.layout.addLayout(self.image_layout)
        for _ in range(5):
            iv = pg.ImageView()
            # Basic styling, can be expanded
            iv.ui.histogram.hide()
            iv.ui.roiBtn.hide()
            iv.ui.menuBtn.hide()
            self.image_views.append(iv)
            self.image_layout.addWidget(iv)

        # --- Z Slider ---
        self.z_slider = Qt.QSlider(Qt.Qt.Orientation.Horizontal)
        self.z_slider.setMinimum(0)
        # Max will be set in _load_cell_data
        self.z_slider.setPageStep(1)
        self.z_slider.setSingleStep(1)
        self.layout.addWidget(self.z_slider)
        self.z_slider.valueChanged.connect(self._update_displayed_slices)

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
        self.metaarray_radio.setChecked(True)  # Default to MetaArray
        self.format_group.addButton(self.nwb_radio)
        self.format_group.addButton(self.metaarray_radio)
        self.format_layout.addWidget(Qt.QLabel("Save Format:"))
        self.format_layout.addWidget(self.nwb_radio)
        self.format_layout.addWidget(self.metaarray_radio)
        self.layout.addLayout(self.format_layout)
        self.nwb_radio.toggled.connect(self._set_format)
        self.metaarray_radio.toggled.connect(self._set_format)

        # --- Action Buttons ---
        self.action_layout = Qt.QHBoxLayout()
        self.skip_button = Qt.QPushButton("Skip")
        self.save_button = Qt.QPushButton("Save")
        self.save_button.setEnabled(False)  # Enable only when rating is selected
        self.action_layout.addWidget(self.skip_button)
        self.action_layout.addWidget(self.save_button)
        self.layout.addLayout(self.action_layout)

        self.skip_button.clicked.connect(self.close)  # Just close the window
        self.save_button.clicked.connect(self._save_and_close)

        self._load_cell_data()

    def _set_rating(self, rating_id):
        self.rating = rating_id
        self.save_button.setEnabled(True)

    def _set_format(self):
        btn = self.sender()
        fmt = "NWB" if btn == self.nwb_radio else "MetaArray"
        self.save_format = fmt

    def _load_cell_data(self):
        if not self.detection_stack or len(self.detection_stack) == 0:
            raise ValueError("RankingWindow: No detection stack data to load.")

        # Find the Z index closest to the cell center
        self.depths = np.array([frame.depth for frame in self.detection_stack])
        self.center_z_global = self.cell_center[2]

        self.volume_data, _ = self._extract_cell_volume(self.cell_center, cube_size=20 * µm)
        n_frames = len(self.volume_data)
        self.center_z_idx = n_frames // 2

        # Set slider to the center Z index initially
        self.z_slider.setMaximum(n_frames - 1)
        self.z_slider.setValue(self.center_z_idx)  # This should trigger _update_displayed_slices

    def _update_displayed_slices(self, current_slider_idx):
        """Updates the 5 image views based on the current_slider_idx from the Z-slider."""
        if self.volume_data is None or len(self.volume_data) == 0 or self.depths is None:
            return

        n_frames = len(self.volume_data)
        if n_frames == 0:
            return

        # current_slider_idx is the Z-index for the 3rd (middle) image view
        # Ensure current_slider_idx is valid
        current_slider_idx = np.clip(current_slider_idx, 2, n_frames - 3)
        
        target_z_indices = [0] * 5

        # Image 1 (index 0): first frame
        target_z_indices[0] = 0

        # Image 5 (index 4): last frame
        target_z_indices[4] = n_frames - 1

        # Image 3 (index 2): Directly from slider
        target_z_indices[2] = current_slider_idx

        # Image 2 (index 1): 1/4 of the way
        target_z_indices[1] = min(n_frames // 4, target_z_indices[2] - 1)

        # Image 4 (index 3): 3/4 of the way
        target_z_indices[3] = max(3 * n_frames // 4, target_z_indices[2] + 1)

        for i, iv in enumerate(self.image_views):
            # Clamp the final index to be within the stack bounds
            display_z_idx = target_z_indices[i]
            frame_data = self.volume_data[display_z_idx]
            iv.setImage(frame_data.T, autoLevels=True)  # IJK to XYZ

    def _save_and_close(self):
        if self.rating is None:
            logMsg("No rating selected.", msgType="warning")
            # Optionally show a message box to the user
            return

        logMsg(f"Cell rated {self.rating}, saving as {self.save_format}...")
        try:
            volume_data, metadata = self._extract_cell_volume(self.cell_center, cube_size=20 * µm)
            self._save_ranked_cell(volume_data, metadata, self.rating, self.save_format, self.save_dir)
        except Exception:
            printExc(f"Failed to extract or save cell data for cell at {self.cell_center}")
        finally:
            self.close()  # Close the window regardless of save success/failure

    def closeEvent(self, event):
        """Emit signal when closed."""
        self.sigClosed.emit(self)
        super().closeEvent(event)

    # --- Data Extraction and Saving Logic (Moved from AutomationDebugWindow) ---

    def _extract_cell_volume(self, center_global, cube_size=20 * µm):
        """Extracts a 3D numpy array centered on the cell."""
        if not self.detection_stack:
            raise ValueError("Detection stack is not available.")

        # Use the stack data passed during initialization
        stack_data = np.array([frame.data() for frame in self.detection_stack])
        frame_shape = stack_data.shape[1:]  # (rows, cols) or (y, x)
        n_frames = stack_data.shape[0]

        # Get transform info from the first frame (assuming it's consistent)
        frame0 = self.detection_stack[0]
        # Use pixel_size passed during initialization
        if self.pixel_size is None:
            raise ValueError("Pixel size information missing.")
        pixel_size_m = self.pixel_size  # Assume square pixels in meters

        # Convert size in µm to pixels/frames
        size_px = int(np.ceil(cube_size / pixel_size_m))
        # Ensure odd size for centering
        if size_px % 2 == 0:
            size_px += 1
        half_size_px = size_px // 2

        # Find the Z index closest to the center
        center_z_idx = np.argmin(np.abs(self.depths - center_global[2]))

        # Use z_step passed during initialization
        z_step_m = self.z_step
        size_z_frames = int(np.ceil(cube_size / z_step_m))
        if size_z_frames % 2 == 0:
            size_z_frames += 1
        half_size_z = size_z_frames // 2

        # Map global center to the coordinates of the center frame
        center_frame = self.detection_stack[center_z_idx]
        center_frame_coords = center_frame.mapFromGlobalToFrame(center_global)  # Returns (x, y) in frame pixels
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
        corner_global_pos = origin_frame.mapFromFrameToGlobal([x_start, y_start])

        metadata = {
            "timestamp": datetime.datetime.now().isoformat(),
            "center_global": center_global.tolist(),
            "size": cube_size,
            "shape": volume.shape,  # (z, y, x)
            "pixel_size_m": pixel_size_m,
            "z_step_m": z_step_m,
            "voxel_origin_global": corner_global_pos + [origin_frame.depth],  # (x, y, z) of voxel [0,0,0]
            "source_detection_stack_info": [f.info() for f in self.detection_stack[z_start:z_end]],  # Basic info
            "source_classification_stack_info": None,
        }
        # Use classification_stack passed during initialization
        if self.classification_stack and z_start < len(self.classification_stack):
            metadata["source_classification_stack_info"] = [f.info() for f in self.classification_stack[z_start:z_end]]

        return volume, metadata

    def _save_ranked_cell(self, volume_data, metadata, rating, save_format, save_dir):
        """Saves the extracted cell volume and metadata."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        cell_id = f"cell_{timestamp}_rating_{rating}"
        filename_base = save_dir / cell_id

        metadata["rating"] = rating
        metadata["save_format"] = save_format
        metadata["cell_id"] = cell_id

        if save_format == "MetaArray":
            info = [
                {
                    "name": "Z",
                    "units": "m",
                    "values": np.arange(volume_data.shape[0]) * metadata["z_step_m"]
                    + metadata["voxel_origin_global"][2],
                },
                {
                    "name": "Y",
                    "units": "m",
                    "values": np.arange(volume_data.shape[1]) * metadata["pixel_size_m"]
                    + metadata["voxel_origin_global"][1],
                },
                {
                    "name": "X",
                    "units": "m",
                    "values": np.arange(volume_data.shape[2]) * metadata["pixel_size_m"]
                    + metadata["voxel_origin_global"][0],
                },
                metadata,
            ]
            ma = MetaArray(volume_data, info=info)
            filepath = f"{filename_base}.ma"
            try:
                ma.write(filepath)
                logMsg(f"Saved cell data to {filepath}")
            except Exception:
                printExc(f"Failed to write MetaArray file: {filepath}")
                logMsg(f"Error writing MetaArray file: {filepath}", msgType="error")
                # Re-raise or handle more gracefully?
                raise

        elif save_format == "NWB":
            logMsg("NWB saving not implemented yet.", msgType="warning")
            filepath = f"{filename_base}.nwb"
            logMsg(f"Placeholder: Would save cell data to {filepath}")
            # TODO: Implement NWB saving logic here using pynwb

        else:
            logMsg(f"Unknown save format: {save_format}", msgType="error")
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
        self._unranked_cells = []  # List of (start, end) tuples from detection
        self._ranked_cells = {}  # Dict mapping cell ID (e.g., timestamp) to ranking info
        self._current_detection_stack = None
        self._current_classification_stack = None  # May be None
        self._previousTargets = []  # Used by autoTarget
        self._open_ranking_windows = []  # Keep track of open windows

        self.ui.clearBtn.clicked.connect(self.clearBoundingBoxes)
        self.ui.zStackDetectBtn.setOpts(future_producer=self._detectNeuronsZStack, stoppable=True)
        self.ui.zStackDetectBtn.sigFinished.connect(self._handleDetectResults)
        self.ui.testUIBtn.setOpts(future_producer=self._testUI, stoppable=True)
        self.ui.testUIBtn.sigFinished.connect(self._handleDetectResults)

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

        self.show()
        planner = self.module.config.get("motionPlanner", "Geometry-aware")
        self.ui.motionPlannerSelector.setCurrentText(planner)
        # Set default ranking dir
        default_rank_dir = Path(self.module.manager.getBaseDir().name()) / "ranked_cells"
        self.ui.rankingSaveDirEdit.setText(str(default_rank_dir))
        self._populatePresetCombos()
        # Connect checkboxes to state update method
        self.ui.multiChannelEnableCheck.toggled.connect(self._updateMultiChannelAndMockStates)
        self.ui.mockCheckBox.toggled.connect(self._updateMultiChannelAndMockStates)
        self._updateMultiChannelAndMockStates()  # Set initial states

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
            ObjectStack,
            ImageStack,
        )

        self.sigWorking.emit(self.ui.trackFeaturesBtn)
        if self.ui.featureTrackerSelector.currentText() == "Cellpose":
            tracker = CellPoseTracker()
        elif self.ui.featureTrackerSelector.currentText() == "CV2":
            tracker = self._featureTracker = CV2MostFlowAgreementTracker()
        elif self.ui.featureTrackerSelector.currentText() == "PyrLK3D":
            tracker = self._featureTracker = PyrLK3DTracker()
        else:
            raise ValueError(f"unknown tracker '{self.ui.featureTrackerSelector.currentText()}'")
        self._featureTracker = tracker
        pipette = self.pipetteDevice
        target: np.ndarray = pipette.targetPosition()
        step = 1e-6
        direction = 1
        obj_stack = None
        margin = 10e-6

        while True:
            # get the stack, in alternating directions
            start_glob = target - margin
            stop_glob = target + margin
            if direction < 0:
                start_glob, stop_glob = stop_glob, start_glob
            _future.waitFor(self.cameraDevice.moveCenterToGlobal(start_glob, "fast"))
            stack = _future.waitFor(
                acquire_z_stack(self.cameraDevice, start_glob[2], stop_glob[2], step), timeout=60
            ).getResult()
            if direction < 0:
                stack = stack[::-1]
                start_glob, stop_glob = stop_glob, start_glob
            direction *= -1

            # get the normalized 20µm³ region for tracking
            ijk_stack = np.array([f.data().T for f in stack])
            stack_xform = SRT3DTransform.from_pyqtgraph(
                stack[0].globalTransform(),
                from_cs=f"frame_{stack[0].info()['id']}.xyz",
                to_cs="global",
            ) * TransposeTransform(
                (2, 1, 0),
                from_cs=f"frame_{stack[0].info()['id']}.ijk",
                to_cs=f"frame_{stack[0].info()['id']}.xyz",
            )
            start_ijk = np.round(stack_xform.inverse.map(start_glob)).astype(int)
            stop_ijk = np.round(stack_xform.inverse.map(stop_glob)).astype(int)
            start_ijk, stop_ijk = np.min((start_ijk, stop_ijk), axis=0), np.max((start_ijk, stop_ijk), axis=0)
            roi_stack = ijk_stack[
                start_ijk[0] : stop_ijk[0],
                start_ijk[1] : stop_ijk[1],
                start_ijk[2] : stop_ijk[2],
            ]
            region_xform = stack_xform * TTransform(
                offset=start_ijk,
                from_cs=f"frame_{stack[0].info()['id']}.roi",
                to_cs=f"frame_{stack[0].info()['id']}.ijk",
            )
            region_center = np.round(region_xform.inverse.map(target)).astype(int)
            if obj_stack is None:
                obj_stack = ObjectStack(
                    img_stack=roi_stack,
                    transform=region_xform,
                    obj_center=region_center,
                )
                tracker.set_tracked_object(obj_stack)
                continue
            result = tracker.next_frame(ImageStack(roi_stack, region_xform))
            target = result["updated_object_stack"].obj_center.mapped_to("global")
            pipette.setTarget(target)
            self.sigLogMessage.emit(f"Updated target to {target}")

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
        self.ui.rankCellsBtn.setEnabled(len(self._unranked_cells) > 0)

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
            # self.scopeDevice.sigGlobalTransformChanged.disconnect(box.noticeFocusChange)
        self._previousBoxWidgets = []

    def _handleDetectResults(self, future: Future) -> None:
        """Handles results from _detectNeuronsZStack or _testUI."""
        try:
            if future.wasInterrupted():
                logMsg("Cell detection failed.")
                return
            bounding_boxes = future.getResult()

            logMsg(f"Cell detection complete. Found {len(bounding_boxes)} potential cells")
            self._displayBoundingBoxes(bounding_boxes)
        finally:
            self.sigWorking.emit(False)

    def _displayBoundingBoxes(self, bounding_boxes):
        cam_win: CameraWindow = self.module.manager.getModule("Camera").window()
        self.clearBoundingBoxes()  # Clear previous boxes visually and state
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
    def _detectNeuronsZStack(self, _future: Future) -> tuple[list, list[Frame] | None, list[Frame] | None] | list:
        """Acquires Z-stack(s) and runs neuron detection. Returns (bboxes, detection_stack, classification_stack)."""
        from acq4_automation.object_detection import detect_neurons

        self.sigWorking.emit(self.ui.zStackDetectBtn)
        # Clear previous results before starting detection
        runInGuiThread(self.clearBoundingBoxes)
        self._unranked_cells = []
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
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z),
                    timeout=100,
                ).getResult()

                _future.waitFor(self.scopeDevice.loadPreset(classification_preset))
                classification_stack = _future.waitFor(
                    acquire_z_stack(self.cameraDevice, start_z, stop_z, step_z),
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
        self._current_detection_stack = detection_stack
        self._current_classification_stack = classification_stack
        self._unranked_cells = result
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

            step_z = 1 * µm  # Default Z step in meters
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
