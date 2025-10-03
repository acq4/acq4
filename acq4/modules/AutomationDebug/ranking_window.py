import datetime
from MetaArray import MetaArray
import numpy as np
from pyqtgraph.debug import printExc
from pyqtgraph.units import µm, m
from acq4.util import Qt
from acq4.util.debug import logMsg


class RankingWindow(Qt.QWidget):
    sigClosed = Qt.Signal(object)  # emit self when closed

    def __init__(
        self,
        main_window: 'AutomationDebugWindow',
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
