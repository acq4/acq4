from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from acq4.logging_config import get_logger
from acq4.modules.Camera import CameraWindow
from acq4.util import Qt
from acq4.util.gentle import Stopped, Task, gui_asynch, synch
from acq4.util.imaging.sequencer import acquire_z_stack
from acq4.util.target import TargetBox
from acq4.util.threadrun import futureInGuiThread, runInGuiThread
from acq4_automation.cell_quality_annotation_tool import open_annotation_tool_with_detections
from acq4_automation.feature_tracking.cell import Cell
from coorx import Point
from pyqtgraph.units import µm
from .ranking_window import RankingWindow

if TYPE_CHECKING:
    from .AutomationDebug import AutomationDebugWindow

logger = get_logger(__name__)


def _health_model_config(manager) -> dict:
    """Health-model paths and score cutoffs from the global ``misc`` config.

    Shared by neuron detection and the annotation-tool launch so both use the same
    configured models. ``scoreCutoffs`` is an ascending list mapping a ranking
    model's raw scores onto the 0-5 rating bins (see
    acq4_automation.compute_score_cutoffs); None falls back to equal-width bins.
    """
    misc = manager.config.get("misc", {})
    return {
        "segmenter": misc.get("segmenterPath", None),
        "autoencoder": misc.get("autoencoderPath", None),
        "classifier": misc.get("classifierPath", None),
        "resnet_classifier": misc.get("resnetClassifierPath", None),
        "score_cutoffs": misc.get("scoreCutoffs", None),
    }


class CellDetector:
    def __init__(self, window: AutomationDebugWindow):
        self._window = window

    def _ui(self):
        return self._window.ui

    def _selectRankDir(self):
        path = Qt.QFileDialog.getExistingDirectory(
            self._window,
            "Select Directory to Save Ranked Cells",
            self._window.ui.rankingSaveDirEdit.text(),
        )
        if path:
            self._window.ui.rankingSaveDirEdit.setText(path)

    @gui_asynch
    def _addCellFromTarget(self):
        target = Point(self._window.pipetteDevice.targetPosition(), "global")
        cell = self._window.patchPipetteDevice.cell
        if cell is None or cell.position != target:
            cell = Cell(target)
            cell.initializeTracker(self._window.cameraDevice)
        self._window._unranked_cells.append(cell)
        cells = list(self._window._unranked_cells)
        futureInGuiThread(self._displayBoundingBoxes, cells).wait()

    @gui_asynch
    def _testUI(self):
        with self._window.cameraDevice.ensureRunning():
            frame = self._window.cameraDevice.acquireFrames(1).wait()[0]
        points = np.random.random((20, 3))
        points[:, 2] *= 20e-6
        points[:, 1] *= frame.shape[0]
        points[:, 0] *= frame.shape[1]
        return [frame.mapFromFrameToGlobal(pt) for pt in points]

    @gui_asynch
    def _detectNeuronsZStack(
        self,
    ) -> tuple[list, list[Frame] | None, list[Frame] | None] | list:
        """Acquires Z-stack(s) and runs neuron detection. Returns (bboxes, detection_stack, classification_stack)."""
        from acq4_automation.object_detection import detect_neurons

        win = self._window
        self._window.sigWorking.emit(win.ui.zStackDetectBtn)
        # Clear previous results before starting detection
        runInGuiThread(self.clearCells)
        win._current_detection_stack = None
        win._current_classification_stack = None

        pixel_size = win.cameraDevice.getPixelSize()[0]  # Real acquisition; overridden from the loaded stack for mock
        man = win.module.manager
        models = _health_model_config(man)
        segmenter = models["segmenter"]
        autoencoder = models["autoencoder"]
        classifier = models["classifier"]
        resnet_classifier = models["resnet_classifier"]
        step_z = 1 * µm  # can be updated by mock metadata
        depth = win.cameraDevice.getFocusDepth()
        classification_stack = None  # Initialize as None

        # This flag indicates intent for multichannel *real* acquisition or processing type
        detection_preset = win.ui.detectionPresetCombo.currentText()
        classification_preset = win.ui.classificationPresetCombo.currentText()
        multichannel_processing_intended = (
            win.ui.multiChannelEnableCheck.isChecked()
            and detection_preset
            and classification_preset
        )

        if win.ui.mockCheckBox.isChecked():
            detection_stack, classification_stack, step_z = win._mock_handler._mockNeuronStacks()
            if detection_stack is None:
                raise RuntimeError("Failed to load mock detection stack.")
            # Use the loaded mock stack's pixel size rather than the live camera's.
            pixel_size = detection_stack[0].info()["pixelSize"][0]
            if classification_stack is not None:
                classification_pixel_size = classification_stack[0].info()["pixelSize"][0]
                if classification_pixel_size != pixel_size:
                    raise ValueError(
                        f"Mock detection stack pixel size ({pixel_size / µm:.4f} µm) does not match "
                        f"classification stack pixel size ({classification_pixel_size / µm:.4f} µm)."
                    )

        else:  # --- Real Acquisition ---
            surface = synch(win.scopeDevice.findSurfaceDepth)(win.cameraDevice)

            start_z = surface - win.ui.zStackStartDepthSpin.value()
            stop_z = surface - win.ui.zStackStopDepthSpin.value()

            if multichannel_processing_intended:
                logger.info(
                    f"Starting multichannel Z-stack acquisition: Detection='{detection_preset}', "
                    f"Classification='{classification_preset}'"
                )
                synch(win.scopeDevice.loadPreset)(detection_preset)
            detection_stack = acquire_z_stack(
                win.cameraDevice, start_z, stop_z, step_z, slow_fallback=False, name="neuron detection stack"
            )

            if multichannel_processing_intended:
                synch(win.scopeDevice.loadPreset)(classification_preset)
                classification_stack = acquire_z_stack(
                    win.cameraDevice, start_z, stop_z, step_z, slow_fallback=False, name="neuron classification stack"
                )

                if len(detection_stack) != len(classification_stack):
                    logger.warning(
                        f"Warning: Z-stack length mismatch: Detection ({len(detection_stack)}) != Classification"
                        f" ({len(classification_stack)}). Trimming to match.",
                    )
                    min_length = min(len(detection_stack), len(classification_stack))
                    detection_stack = detection_stack[:min_length]
                    classification_stack = classification_stack[:min_length]

        if multichannel_processing_intended and classification_stack is not None:
            working_stack = (detection_stack, classification_stack)
            multichannel = True
        else:
            working_stack = detection_stack
            multichannel = False

        win.cameraDevice.setFocusDepth(depth, name=f"{win.cameraDevice.name()} restore focus after detection z-stack")  # Restore focus

        # Persist this detection session under one base name so the saved z-stack,
        # cellpose masks, and annotations share the annotation tool's naming scheme
        # and reload together. The base is shared with the annotation tool launched
        # in _handleDetectResults.
        win.annotation_base_name = datetime.datetime.now().strftime(
            "in_memory_stack_%Y%m%d_%H%M%S_%f"
        )
        annotation_save_dir = win.annotation_save_dir
        if annotation_save_dir is None:
            logger.warning(
                "No annotation save directory available (set misc/cellAnnotationDir, "
                "or configure a storage directory); the detection z-stack, cellpose "
                "masks, and annotations will not be saved alongside the data."
            )
            save_prefix = None
        else:
            save_prefix = str(annotation_save_dir / win.annotation_base_name)

        detection_results = detect_neurons(
            working_stack,  # Prepared based on mock/real and single/multi
            segmenter=segmenter,
            autoencoder=autoencoder,
            classifier=classifier,
            resnet_classifier=resnet_classifier,
            xy_scale=pixel_size,  # Global pixel_size
            z_scale=step_z,  # Actual step_z from mock or real (1um for real)
            multichannel=multichannel,  # Actual flag for detect_neurons
            trim_edges=True,
            min_volume_m3=win.ui.minVolumeSpin.value(),
            n=None,
            save_prefix=save_prefix,
        )
        logger.info(f"Neuron detection finished. Found {len(detection_results)} potential neurons.")

        win._current_detection_stack = detection_stack
        win._current_classification_stack = classification_stack
        win._unranked_cells = []
        for pos, score in detection_results:
            cell = Cell(pos)
            cell.score = score
            win._unranked_cells.append(cell)
        return detection_results

    def _handleDetectResults(self, future: Task) -> None:
        """Handles results from _detectNeuronsZStack or _testUI."""
        win = self._window
        try:
            try:
                neurons = future.wait()
            except Stopped:
                logger.info("Cell detection failed.")
                return

            logger.info(f"Cell detection complete. Found {len(neurons)} potential cells")
            self._displayBoundingBoxes(neurons)

            if win._current_detection_stack is None:
                logger.info("No detection stack available, skipping annotation tool launch.")
                return

            # Extract plain positions for annotation tool (neurons may be (pos, score) tuples)
            positions = [pos for pos, _ in neurons] if neurons and isinstance(neurons[0], tuple) else neurons
            stack = np.asarray([frame.data().T for frame in win._current_detection_stack])
            stack_transform = win._current_detection_stack[0].globalTransform()
            frame_to_global = stack_transform.inverse
            centers_ijk = [np.abs(frame_to_global.map(n)[::-1]) for n in positions]

            win._annotation_stack_transform = stack_transform

            def _center_camera_on_cell(context, _win=win):
                if _win._annotation_stack_transform is None:
                    return
                global_pos = _win._annotation_stack_transform.map(context.center_ijk[::-1])
                _win.cameraDevice.moveCenterToGlobal(global_pos, speed='fast')

            if win._annotation_tool is not None:
                win._annotation_tool.close()
            # Same configured health models as detection, plus score cutoffs, so the
            # annotation tool re-scores the detected cells and bins them consistently.
            models = _health_model_config(win.module.manager)
            win._annotation_tool = open_annotation_tool_with_detections(
                stack=stack,
                cell_centers_ijk=centers_ijk,
                xy_scale=win._current_detection_stack[0].info()["pixelSize"][0],
                z_scale=1.0e-6,
                preserve_order=True,  # Keep healthy-first order
                filter=False,  # No extra filtering
                transpose_display=True,  # stack is (n_frames, Y, X) after .T; row-major matches camera module orientation
                custom_buttons=[("Center Camera", _center_camera_on_cell)],
                save_dir=win.annotation_save_dir,
                base_name=win.annotation_base_name,
                classifier=models["classifier"],
                autoencoder=models["autoencoder"],
                resnet_classifier=models["resnet_classifier"],
                score_cutoffs=models["score_cutoffs"],
            )

            # from acq4_automation.object_detection import NeuronBoxViewer
            # if win._current_classification_stack is not None:
            #     data = np.array(([[s.data().T for s in win._current_detection_stack]], [[s.data().T for s in win._current_classification_stack]]))
            # else:
            #     data = np.array([s.data().T for s in win._current_detection_stack])
            # xform = SRT3DTransform.from_pyqtgraph(win._current_detection_stack[0].globalTransform()) * TransposeTransform((1, 0, 2))
            # self._viewer = NeuronBoxViewer(data, neurons, xform)
            # self._viewer.show()
        finally:
            win.sigWorking.emit(False)

    def _displayBoundingBoxes(self, neurons):
        win = self._window
        cam_win: CameraWindow = win.module.manager.getModule("Camera").window()
        self.clearBoundingBoxes()  # Clear previous boxes visually and state
        rois_visible = win.ui.showRoisBtn.isChecked()
        for neuron in neurons:
            if isinstance(neuron, tuple):
                pos, score = neuron
                pos = np.array(pos)
            elif hasattr(neuron, 'position'):
                pos = np.array(neuron.position.coordinates)
                score = getattr(neuron, 'score', None)
            else:
                pos = np.array(neuron)
                score = None
            start, end = pos - 10e-6, pos + 10e-6
            label = f"{score:.0%}" if score is not None else None
            box = TargetBox(start, end, label=label)
            box.noticeFocusChange(win.scopeDevice, None)  # initialize opacity for current focus depth
            box.setVisible(rois_visible)
            cam_win.addItem(box)
            win.scopeDevice.sigGlobalTransformChanged.connect(box.noticeFocusChange)
            win._previousBoxWidgets.append(box)

    def clearCells(self):
        self._window._unranked_cells = []
        self._window._ranked_cells = []
        self.clearBoundingBoxes()

    def clearBoundingBoxes(self):
        win = self._window
        cam_win: CameraWindow = win.module.manager.getModule("Camera").window()
        for box in win._previousBoxWidgets:
            cam_win.removeItem(box)
            win.scopeDevice.sigGlobalTransformChanged.disconnect(box.noticeFocusChange)
        win._previousBoxWidgets = []

    def _rankCells(self):
        """Pops the next unranked cell and opens a RankingWindow for it."""
        win = self._window
        if not win._unranked_cells:
            # TODO teach the ranking window to detect cells (since I don't want this to be a future button)
            raise ValueError("No unranked cells available. Run detection first.")
        stack = win._current_classification_stack or win._current_detection_stack
        if not stack:
            raise ValueError("Stack data is missing, cannot rank. Run detection first.")
        if len(stack) <= 1:
            raise ValueError("Stack has only one frame.")
        save_dir = Path(win.ui.rankingSaveDirEdit.text())
        if not save_dir.is_dir():
            try:
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise ValueError(
                    f"Could not create ranking save directory: {save_dir}"
                ) from e

        # --- Get next cell ---
        # TODO separate ranking cells from targeting cells
        cell: Cell = win._unranked_cells.pop(0)
        center_global = cell.position.coordinates
        pixel_size = stack[0].info()["pixelSize"][0]  # Assume square pixels
        z_step = abs(stack[1].depth - stack[0].depth)

        # --- Create and show RankingWindow ---
        ranking_window = RankingWindow(
            main_window=win,  # Pass reference for cleanup
            cell_center=center_global,
            detection_stack=stack,
            classification_stack=win._current_classification_stack,
            pixel_size=pixel_size,
            z_step=z_step,
            save_dir=save_dir,
        )
        # Keep track of the window and connect its closed signal for cleanup
        win._open_ranking_windows.append(ranking_window)
        ranking_window.sigClosed.connect(self._rankingWindowClosed)
        ranking_window.show()

    def _rankingWindowClosed(self, window):
        """Callback to remove window reference when it's closed."""
        try:
            self._window._open_ranking_windows.remove(window)
        except ValueError:
            # Window might have already been removed or was never added properly
            logger.exception("Attempted to remove a ranking window reference that was not found.")
