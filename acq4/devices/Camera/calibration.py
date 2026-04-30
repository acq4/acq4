# Camera Petzval field curvature calibration tools.
# Discovers the focal surface shape via bead z-stacks or pipette tip scanning.

import numpy as np
import scipy.ndimage

import pyqtgraph as pg
from acq4.Manager import getManager
from acq4.util import Qt
from acq4.util.future import future_wrap
from acq4.util.imaging.sequencer import acquire_z_stack
from coorx.nonlinear import PetzvalTransform


class FieldCurvatureCalibrationWindow(Qt.QWidget):
    """Window to measure and display camera Petzval field curvature.

    Two measurement modes: fluorescent bead z-stack analysis, or pipette tip
    focus scanning across the field of view.
    """

    def __init__(self, camera):
        super().__init__()
        self.camera = camera
        self._calibration_future = None
        self._result = None
        self.setWindowTitle("Camera Field Curvature Calibration")
        self.resize(900, 800)
        self._setup_ui()

    def _setup_ui(self):
        layout = Qt.QVBoxLayout(self)

        # Mode selection
        mode_group = Qt.QGroupBox("Calibration Method")
        mode_layout = Qt.QVBoxLayout(mode_group)
        self._beads_radio = Qt.QRadioButton("Fluorescent beads / uniform-z grid objects")
        self._pipette_radio = Qt.QRadioButton("Calibrated pipette + manipulator")
        self._beads_radio.setChecked(True)
        mode_layout.addWidget(self._beads_radio)
        mode_layout.addWidget(self._pipette_radio)
        layout.addWidget(mode_group)

        # Per-mode parameter panels (stacked)
        self._params_stack = Qt.QStackedWidget()
        self._params_stack.addWidget(self._build_bead_params())
        self._params_stack.addWidget(self._build_pipette_params())
        layout.addWidget(self._params_stack)

        self._beads_radio.toggled.connect(
            lambda checked: self._params_stack.setCurrentIndex(0) if checked else None
        )
        self._pipette_radio.toggled.connect(
            lambda checked: self._params_stack.setCurrentIndex(1) if checked else None
        )

        # Polynomial degree (shared)
        poly_layout = Qt.QHBoxLayout()
        poly_layout.addWidget(Qt.QLabel("Petzval polynomial terms:"))
        self._n_terms_spin = Qt.QSpinBox()
        self._n_terms_spin.setRange(1, 4)
        self._n_terms_spin.setValue(1)
        self._n_terms_spin.setToolTip("Number of even-power radial terms: k₁·r² + k₂·r⁴ + …")
        poly_layout.addWidget(self._n_terms_spin)
        poly_layout.addStretch()
        layout.addLayout(poly_layout)

        # Start button
        ctrl_layout = Qt.QHBoxLayout()
        self._start_btn = Qt.QPushButton("Start Calibration")
        self._start_btn.clicked.connect(self._start)
        ctrl_layout.addWidget(self._start_btn)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Status / progress
        self._status_label = Qt.QLabel("Ready")
        self._progress_bar = Qt.QProgressBar()
        self._progress_bar.setVisible(False)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress_bar)

        # Visualization
        viz_group = Qt.QGroupBox("Field Curvature Map (µm relative to mean focal plane)")
        viz_layout = Qt.QVBoxLayout(viz_group)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setAspectLocked(True)
        self._plot_widget.setLabel("bottom", "X (µm)")
        self._plot_widget.setLabel("left", "Y (µm)")
        self._img_item = pg.ImageItem()
        self._plot_widget.addItem(self._img_item)

        cmap = pg.colormap.get("RdBu_r", source="matplotlib")
        self._colorbar = pg.ColorBarItem(
            label="z offset (µm)",
            interactive=False,
            colorMap=cmap,
        )
        self._colorbar.setImageItem(self._img_item, insert_in=self._plot_widget.getPlotItem())

        self._range_label = Qt.QLabel("")
        viz_layout.addWidget(self._plot_widget)
        viz_layout.addWidget(self._range_label)
        viz_group.setMinimumHeight(380)
        layout.addWidget(viz_group)

    def _build_bead_params(self):
        widget = Qt.QWidget()
        layout = Qt.QFormLayout(widget)
        self._bead_z_range = pg.SpinBox(
            value=20e-6, suffix="m", siPrefix=True, step=1e-6, bounds=(1e-6, 500e-6)
        )
        self._bead_z_step = pg.SpinBox(
            value=1e-6, suffix="m", siPrefix=True, step=0.5e-6, bounds=(0.1e-6, 20e-6)
        )
        self._bead_grid_n = Qt.QSpinBox()
        self._bead_grid_n.setRange(2, 16)
        self._bead_grid_n.setValue(5)
        layout.addRow("Z scan range (±):", self._bead_z_range)
        layout.addRow("Z step:", self._bead_z_step)
        layout.addRow("Analysis grid size:", self._bead_grid_n)
        return widget

    def _build_pipette_params(self):
        widget = Qt.QWidget()
        layout = Qt.QFormLayout(widget)

        man = getManager()
        from acq4.devices.Pipette.pipette import Pipette
        from acq4.devices.Stage.Stage import Stage

        pip_names = [name for name, dev in man.devices.items() if isinstance(dev, Pipette)]
        self._pip_combo = Qt.QComboBox()
        self._pip_combo.addItems(pip_names)

        stage_names = [name for name, dev in man.devices.items() if isinstance(dev, Stage)]
        self._stage_combo = Qt.QComboBox()
        self._stage_combo.addItems(stage_names)

        self._pip_xy_range = pg.SpinBox(
            value=100e-6, suffix="m", siPrefix=True, step=10e-6, bounds=(10e-6, 2e-3)
        )
        self._pip_grid_n = Qt.QSpinBox()
        self._pip_grid_n.setRange(2, 8)
        self._pip_grid_n.setValue(4)
        self._pip_z_range = pg.SpinBox(
            value=10e-6, suffix="m", siPrefix=True, step=1e-6, bounds=(1e-6, 100e-6)
        )
        self._pip_z_step = pg.SpinBox(
            value=1e-6, suffix="m", siPrefix=True, step=0.5e-6, bounds=(0.1e-6, 10e-6)
        )

        layout.addRow("Pipette device:", self._pip_combo)
        layout.addRow("XY stage:", self._stage_combo)
        layout.addRow("XY scan range (±):", self._pip_xy_range)
        layout.addRow("Grid size:", self._pip_grid_n)
        layout.addRow("Z search range (±):", self._pip_z_range)
        layout.addRow("Z step:", self._pip_z_step)
        return widget

    def _start(self):
        if self._calibration_future is not None and not self._calibration_future.isDone():
            return
        self._start_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate spinner

        if self._beads_radio.isChecked():
            self._run_bead_calibration()
        else:
            self._run_pipette_calibration()

    def _run_bead_calibration(self):
        self._status_label.setText("Acquiring z-stack…")
        self._calibration_future = measure_field_curvature_beads(
            self.camera,
            z_range=self._bead_z_range.value(),
            z_step=self._bead_z_step.value(),
            grid_n=self._bead_grid_n.value(),
            n_terms=self._n_terms_spin.value(),
        )
        self._calibration_future.sigFinished.connect(self._on_done)
        self._calibration_future.sigStateChanged.connect(self._on_state_changed)

    def _run_pipette_calibration(self):
        man = getManager()
        pip_name = self._pip_combo.currentText()
        stage_name = self._stage_combo.currentText()
        if not pip_name or not stage_name:
            self._status_label.setText("Select both a pipette and a stage device first.")
            self._start_btn.setEnabled(True)
            self._progress_bar.setVisible(False)
            return

        pipette = man.getDevice(pip_name)
        stage = man.getDevice(stage_name)
        self._status_label.setText("Starting pipette scan…")
        self._calibration_future = measure_field_curvature_pipette(
            self.camera,
            pipette=pipette,
            stage=stage,
            xy_range=self._pip_xy_range.value(),
            grid_n=self._pip_grid_n.value(),
            z_range=self._pip_z_range.value(),
            z_step=self._pip_z_step.value(),
            n_terms=self._n_terms_spin.value(),
        )
        self._calibration_future.sigFinished.connect(self._on_done)
        self._calibration_future.sigStateChanged.connect(self._on_state_changed)

    def _on_state_changed(self, _future, state):
        self._status_label.setText(str(state))

    def _on_done(self):
        self._start_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        try:
            result = self._calibration_future.getResult()
            self._result = result
            self._display_result(result)
        except Exception as exc:
            self._status_label.setText(f"Error: {exc}")

    def _display_result(self, result):
        grid_n = result["grid_n"]
        z_um = result["z_offsets_um"].reshape(grid_n, grid_n)
        xy_range_um = result["xy_range_um"]

        abs_max = max(float(np.abs(z_um).max()), 0.001)
        levels = (-abs_max, abs_max)

        # Transpose so image X = columns = global X, image Y = rows = global Y
        self._img_item.setImage(z_um.T, autoLevels=False)
        self._img_item.setLevels(levels)
        self._img_item.setRect(
            pg.QtCore.QRectF(-xy_range_um, -xy_range_um, 2 * xy_range_um, 2 * xy_range_um)
        )
        self._colorbar.setLevels(levels)

        peak_to_peak = float(z_um.max() - z_um.min())
        transform = result["petzval_transform"]
        coeffs_str = ", ".join(f"{c:.3g}" for c in transform.coeff)
        self._range_label.setText(
            f"Peak-to-peak: {peak_to_peak:.2f} µm  |  "
            f"Method: {result['method']}  |  "
            f"Petzval coefficients: [{coeffs_str}]"
        )
        self._status_label.setText("Calibration complete.")


@future_wrap
def measure_field_curvature_beads(camera, z_range, z_step, grid_n, n_terms=1, _future=None):
    """Measure field curvature from a z-stack of uniform-z objects (e.g. fluorescent beads).

    Divides each frame into a grid_n × grid_n tiling.  For each tile the frame
    with the highest Laplacian-variance sharpness is selected, giving the
    local best-focus depth.  A PetzvalTransform is then fit to the result.

    Returns a dict with keys: z_offsets_um, z_absolute, grid_n, xy_range_um,
    positions_global, petzval_transform, method.
    """
    _future.setState("Acquiring z-stack…")
    z_center = camera.getFocusDepth()
    frames = acquire_z_stack(
        camera,
        z_center - z_range,
        z_center + z_range,
        z_step,
        name="field curvature calibration",
    ).getResult()

    _future.setState("Analyzing sharpness per tile…")
    images = np.stack([f.data() for f in frames])
    z_positions = np.array([f.depth for f in frames])

    h, w = images.shape[1], images.shape[2]
    tile_h, tile_w = h // grid_n, w // grid_n

    tile_z = np.zeros((grid_n, grid_n))
    positions_global = np.zeros((grid_n * grid_n, 2))

    for row in range(grid_n):
        for col in range(grid_n):
            r0, r1 = row * tile_h, (row + 1) * tile_h
            c0, c1 = col * tile_w, (col + 1) * tile_w
            sharpness = np.array(
                [_focus_quality(images[i, r0:r1, c0:c1]) for i in range(len(frames))]
            )
            tile_z[row, col] = z_positions[np.argmax(sharpness)]
            px_center = np.array([(r0 + r1) / 2.0, (c0 + c1) / 2.0, 0.0])
            global_pos = frames[0].mapFromFrameToGlobal(px_center)
            positions_global[row * grid_n + col] = global_pos[:2]

    _future.setState("Fitting Petzval surface…")
    z_flat = tile_z.ravel()
    petzval = _fit_petzval(positions_global, z_flat, n_terms=n_terms)

    # Approximate FOV half-extent from frame corners
    corner0 = frames[0].mapFromFrameToGlobal(np.array([0.0, 0.0, 0.0]))
    corner1 = frames[0].mapFromFrameToGlobal(np.array([float(h), float(w), 0.0]))
    xy_range_um = (
        float(max(abs(corner1[0] - corner0[0]), abs(corner1[1] - corner0[1]))) * 0.5 * 1e6
    )

    return {
        "z_offsets_um": (z_flat - z_flat.mean()) * 1e6,
        "z_absolute": z_flat,
        "grid_n": grid_n,
        "xy_range_um": xy_range_um,
        "positions_global": positions_global,
        "petzval_transform": petzval,
        "method": "beads",
    }


@future_wrap
def measure_field_curvature_pipette(
    camera, pipette, stage, xy_range, grid_n, z_range, z_step, n_terms=1, _future=None
):
    """Measure field curvature by scanning the pipette tip across the field.

    Moves the XY stage to a grid of positions so the pipette tip appears at
    different field locations.  At each position a z-scan finds the focus depth
    that maximises PipetteTracker detection confidence, then a PetzvalTransform
    is fit to the resulting (x, y) → z data.

    Returns a dict with keys: z_offsets_um, z_absolute, grid_n, xy_range_um,
    positions_global, petzval_transform, method.
    """
    center_pos = np.array(stage.getPosition())
    offsets = np.linspace(-xy_range, xy_range, grid_n)
    total = grid_n * grid_n
    z_values = np.zeros((grid_n, grid_n))
    positions_global = np.zeros((total, 2))

    try:
        for i, dx in enumerate(offsets):
            for j, dy in enumerate(offsets):
                count = i * grid_n + j + 1
                _future.setState(f"Scanning position {count}/{total}…")

                target = center_pos.copy()
                target[0] += dx
                target[1] += dy
                stage.move(list(target), "slow").wait()

                z_values[i, j] = _find_focus_z_with_pipette(camera, pipette, z_range, z_step)
                positions_global[i * grid_n + j] = target[:2]
    finally:
        _future.setState("Returning stage to start position…")
        stage.move(list(center_pos), "slow").wait()

    _future.setState("Fitting Petzval surface…")
    z_flat = z_values.ravel()
    petzval = _fit_petzval(positions_global, z_flat, n_terms=n_terms)

    return {
        "z_offsets_um": (z_flat - z_flat.mean()) * 1e6,
        "z_absolute": z_flat,
        "grid_n": grid_n,
        "xy_range_um": xy_range * 1e6,
        "positions_global": positions_global,
        "petzval_transform": petzval,
        "method": "pipette",
    }


def _find_focus_z_with_pipette(camera, pipette, z_range, z_step):
    """Scan z and return the depth at which tip-detection confidence is highest."""
    z_center = camera.getFocusDepth()
    z_positions = np.arange(
        z_center - z_range, z_center + z_range + z_step / 2, z_step
    )

    best_confidence = -np.inf
    best_z = z_center

    for z in z_positions:
        camera.setFocusDepth(z).wait()
        frame = pipette.tracker.takeFrame()
        try:
            _, confidence = pipette.tracker.measureTipPosition(frame=frame)
            if confidence > best_confidence:
                best_confidence = confidence
                best_z = z
        except Exception:
            pass

    camera.setFocusDepth(best_z).wait()
    return best_z


def _fit_petzval(positions, z_values, n_terms=1):
    """Fit a PetzvalTransform to measured (x, y) → z data.

    The optical-axis centre is fixed at the centroid of the measurement
    positions.  Coefficients are found via linear least-squares on the
    mean-subtracted z values.
    """
    cx = float(positions[:, 0].mean())
    cy = float(positions[:, 1].mean())
    x = positions[:, 0] - cx
    y = positions[:, 1] - cy
    r2 = x ** 2 + y ** 2

    A = np.column_stack([r2 ** (i + 1) for i in range(n_terms)])
    z_centered = z_values - z_values.mean()
    coeffs, _, _, _ = np.linalg.lstsq(A, z_centered, rcond=None)

    return PetzvalTransform(coeff=list(coeffs), center=(cx, cy))


def _focus_quality(image):
    """Laplacian variance focus metric — higher values indicate sharper focus."""
    lap = scipy.ndimage.laplace(image.astype(float))
    return float(np.var(lap))
