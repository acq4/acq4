from __future__ import annotations

import os
from typing import TYPE_CHECKING

import numpy as np
from MetaArray import MetaArray

from acq4.logging_config import get_logger
from acq4.util import Qt
from acq4.util.imaging import Frame
from coorx import AffineTransform, SRT3DTransform
from pyqtgraph.units import µm, m

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


class MockDataHandler:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

    def _selectMockFile(self):
        filePath, _ = Qt.QFileDialog.getOpenFileName(
            self._window, "Select MetaArray File", "", "MetaArray Files (*.ma);;All Files (*)"
        )
        if filePath:
            self._window.ui.mockFilePath.setText(filePath)
            self._window.ui.mockCheckBox.setChecked(True)

    def _selectMockClassificationFile(self):
        filePath, _ = Qt.QFileDialog.getOpenFileName(
            self._window,
            "Select Mock Classification Z-Stack File",
            "",
            "MetaArray Files (*.ma);;All Files (*)",
        )
        if filePath:
            self._window.ui.mockClassificationFilePath.setText(filePath)

    def _create_mock_stack_from_file(
        self, mock_file_path: str, base_frame: Frame
    ) -> tuple[list[Frame] | None, float | None]:
        """
        Loads a MetaArray file and converts it into a list of Frame objects.
        The Z positions and transforms of the mock frames are relative to the provided base_frame.
        Returns (stack_frames, step_z_microns) or (None, None) on failure.
        """
        if not mock_file_path:
            return None, None
        try:
            logger.info(f"Loading mock Z-stack from: {mock_file_path}")
            marr = MetaArray(file=mock_file_path)
            data = marr.asarray()
            info = marr.infoCopy()

            live_frame_global_transform = base_frame.globalTransform()
            live_frame_origin_global_xyz = np.array(
                base_frame.mapFromFrameToGlobal([0, 0, 0])
            )

            z_info = next((ax for ax in info if ax.get("name") == "Z"), None)
            if z_info and "values" in z_info:
                z_vals = z_info["values"]
                if len(z_vals) > 1:
                    step_z = abs(z_vals[1] - z_vals[0]) * m  # Assume meters
                    logger.info(
                        f"Using Z step from mock file '{os.path.basename(mock_file_path)}': {step_z / µm:.2f} µm"
                    )
                elif len(z_vals) == 1:
                    logger.warning(
                        f"Only one Z value in mock file '{os.path.basename(mock_file_path)}'. Assuming 1µm step.",
                    )
                    step_z = 1 * µm
                else:
                    logger.warning(
                        f"No Z values in mock file '{os.path.basename(mock_file_path)}', using default 1µm step.",
                    )
                    step_z = 1 * µm
            else:
                logger.warning(
                    f"Z info not in mock file '{os.path.basename(mock_file_path)}', using default 1µm step.",
                )
                step_z = 1 * µm

            stack_frames = []
            # Start Z from the live frame's depth
            current_mock_frame_global_z = live_frame_origin_global_xyz[2]

            for i in range(len(data)):
                mock_frame_transform = live_frame_global_transform.full_matrix
                px_size = (mock_frame_transform[0, 0], mock_frame_transform[1, 1])
                mock_frame_transform[2, 2] = step_z
                z_offset = current_mock_frame_global_z - live_frame_origin_global_xyz[2]
                mock_frame_transform[2, 3] = z_offset
                mock_frame_transform = AffineTransform.from_matrix(mock_frame_transform)
                srt = SRT3DTransform(dims=(3, 3))
                srt.set_from_affine(mock_frame_transform)
                mock_frame_transform = srt

                frame_info = {
                    "pixelSize": px_size,
                    "depth": current_mock_frame_global_z,
                    "transform": mock_frame_transform,
                }
                if "device" in base_frame.info():
                    frame_info["device"] = base_frame.info()["device"]

                frame = Frame(data[i], info=frame_info)
                stack_frames.append(frame)
                current_mock_frame_global_z += step_z
            return stack_frames, step_z
        except Exception:
            logger.exception(f"Failed to load or process mock file: {mock_file_path}")
            return None, None

    def _mockNeuronStacks(
        self,
    ) -> tuple[list[Frame] | None, list[Frame] | None, float]:
        win = self._window
        logger.info("Using mock Z-stack file(s) for detection.")
        detection_stack = None
        classification_stack = None
        # Default step_z, will be updated by the first successfully loaded mock stack
        # or remain 1um if primary mock fails but code proceeds.
        step_z = 1 * µm

        with win.cameraDevice.ensureRunning():
            base_frame = win.cameraDevice.acquireFrames(1).get_result()[0]

        # Load detection stack
        detection_mock_path = win.ui.mockFilePath.text()
        if detection_mock_path:
            detection_stack, det_step_z = self._create_mock_stack_from_file(
                detection_mock_path, base_frame
            )
            if det_step_z is not None:
                step_z = det_step_z
        else:
            logger.warning("Primary mock file path is empty.")
            # detection_stack remains None, step_z remains default

        # Load classification stack if multichannel mock is enabled and path is provided
        # Redundant mockCheckBox check, but safe
        if win.ui.multiChannelEnableCheck.isChecked() and win.ui.mockCheckBox.isChecked():
            classification_mock_path = win.ui.mockClassificationFilePath.text()
            if classification_mock_path:
                # The step_z from the classification mock file will be returned by _create_mock_stack_from_file.
                # We prioritize step_z from the detection stack if both are loaded.
                # Or, one could enforce consistency or average, but for now, just log if different.
                classification_stack, class_step_z = self._create_mock_stack_from_file(
                    classification_mock_path, base_frame
                )
                if (
                    class_step_z is not None
                    and step_z != class_step_z
                    and detection_stack is not None
                ):
                    logger.warning(
                        f"Z-step mismatch: Detection mock ({step_z/µm:.2f} µm) vs Classification mock ({class_step_z/µm:.2f} µm). Using detection Z-step.",
                    )
                # If detection_stack failed to load (det_step_z is None), but classification loaded, use its step_z.
                elif class_step_z is not None and detection_stack is None:
                    step_z = class_step_z
            else:
                raise ValueError(
                    "Multichannel mock enabled, but no classification mock file selected."
                )

        return detection_stack, classification_stack, step_z
