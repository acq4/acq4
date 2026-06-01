# Device class for a grid array of InteractionSite objects (e.g. nucleus deposition tube arrays).
# Each slot holds its own offset in the parent stage frame, calibrated empirically from corner sites.

from __future__ import annotations

import numpy as np

from acq4.util import Qt
from .Device import Device
from .InteractionSite import InteractionSite
from .OptomechDevice import OptomechDevice
from .Stage import Stage


class InteractionSiteArray(Device, OptomechDevice):
    """Array of cylindrical interaction sites arranged in a grid.

    Each site stores its own offset in the parent stage frame; positions are calibrated
    empirically by tagging corner sites and interpolating evenly.

    All sites in an array share a single role (set via the *role* config option); roles
    are not assignable per-site at runtime.

    Configuration options:
      rows: int — number of rows in the grid
      cols: int — number of columns in the grid
      siteRadius: float (m) — radius of each site cylinder
      siteHeight: float (m) — height of each site cylinder
      parentDevice: str — name of parent stage device
      role: str — the role shared by every site (clean, rinse, nucleus, refill, empty)
      childGeometry: dict (optional) — geometry config applied to every child site,
        same format as a standalone InteractionSite geometry block. Use to give the
        array a distinctive shape (e.g. tube + conic tip). The role-based color is
        always applied on top of whatever is configured here.
    """

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self._rows = config['rows']
        self._cols = config['cols']
        siteRadius = config['siteRadius']
        siteHeight = config['siteHeight']
        self._role = config.get('role', 'empty')
        child_geometry = config.get('childGeometry', None)

        parent = self
        while True:
            parent = parent.parentDevice()
            if parent is None or isinstance(parent, Stage):
                break
        self._parentStage: Stage | None = parent

        self.positions = self.readConfigFile("saved_positions")

        self._sites: list[InteractionSite] = []
        n = self._rows * self._cols
        for i in range(n):
            row = i // self._cols
            col = i % self._cols
            site_name = f"{name}[{i}]"
            site_config = {
                'radius': siteRadius,
                'height': siteHeight,
                'role': self._role,
            }
            if child_geometry is not None:
                site_config['geometry'] = child_geometry
            site = InteractionSite(dm, site_config, site_name)
            site.setParentDevice(self)
            dm.declareInterface(site_name, ['device', 'interactionSite'], site)
            self._sites.append(site)

    # ------------------------------------------------------------------
    # Site access

    @property
    def role(self) -> str:
        """The single role shared by every site in this array."""
        return self._role

    @property
    def sites(self) -> list[InteractionSite]:
        return list(self._sites)

    def getSite(self, index: int) -> InteractionSite:
        return self._sites[index]

    def getFirstAvailableSite(self) -> "InteractionSite | None":
        """Return the first non-used-up site, or None if all sites are used up.

        Callers are responsible for selecting an array whose role matches their need.
        """
        for site in self._sites:
            if not site.used_up:
                return site
        return None

    # ------------------------------------------------------------------
    # Calibration

    def calibrateApproach(self, pip):
        """Record the single approach waypoint: stage position and pipette global position.

        The approach point only needs to be a safe spot above the wells; its position
        relative to the interact point is shared by every (identical, parallel) site.
        """
        if self._parentStage is None:
            raise RuntimeError(f"{self.name()} has no parent Stage, cannot calibrate")
        pip_name = pip.name()
        self.positions.setdefault(pip_name, {})
        self.positions[pip_name]['approach'] = pip.globalPosition().tolist()
        self.positions[pip_name]['approach_stage'] = self._parentStage.globalPosition().tolist()
        self.writeConfigFile(self.positions, "saved_positions")

    def calibrateInteractCorner(self, pip, corner: str):
        """Record an interact corner: stage position and pipette tip global (deep in the fluid).

        corner: 'origin' ([0,0]), 'col_end' ([0,cols-1]), 'row_end' ([rows-1,0]).
        These three points define the grid of interact positions, which are the
        precision-critical targets for fluid interaction.
        """
        if self._parentStage is None:
            raise RuntimeError(f"{self.name()} has no parent Stage, cannot calibrate")
        pip_name = pip.name()
        self.positions.setdefault(pip_name, {})
        self.positions[pip_name][f'{corner}_stage'] = self._parentStage.globalPosition().tolist()
        self.positions[pip_name][f'{corner}_interact'] = pip.globalPosition().tolist()
        self.writeConfigFile(self.positions, "saved_positions")

    def _commonFrameRef(self, cal):
        """Return the reference stage position (origin corner) for common-frame conversion."""
        return np.asarray(cal['origin_stage'], dtype=float)

    def _cornerInCommonFrame(self, cal, corner):
        """Return one interact corner in the common frame (stage at the origin's stage position).

        A point measured at stage position S maps into the common frame (stage at S_ref) by
        adding (S_ref - S): moving the stage by that delta shifts the array — and the fluid
        it carries — by the same amount in global coordinates.
        """
        S_ref = self._commonFrameRef(cal)
        interact = np.asarray(cal[f'{corner}_interact'], dtype=float)
        stage = np.asarray(cal[f'{corner}_stage'], dtype=float)
        return interact + (S_ref - stage)

    def applyCalibration(self, pip):
        """Interpolate per-site interact positions from the three corners and apply them.

        Requires calibrateInteractCorner for 'origin', 'col_end' (and 'row_end' when
        rows > 1) plus calibrateApproach. Each site gets its own interact global position
        (interpolated) and an approach position derived from the shared approach-to-interact
        offset. Site offsets are placed so each site's origin sits at its approach point when
        the stage is at the reference position.
        """
        pip_name = pip.name()
        cal = self.positions.get(pip_name, {})
        S_ref = self._commonFrameRef(cal)
        J_00 = self._cornerInCommonFrame(cal, 'origin')

        if self._cols > 1:
            J_0N = self._cornerInCommonFrame(cal, 'col_end')
            col_step = (J_0N - J_00) / (self._cols - 1)
        else:
            col_step = np.zeros(3)
        if self._rows > 1:
            J_M0 = self._cornerInCommonFrame(cal, 'row_end')
            row_step = (J_M0 - J_00) / (self._rows - 1)
        else:
            row_step = np.zeros(3)

        # Approach point relative to the origin interact, in the common frame; shared by all sites.
        A_common = np.asarray(cal['approach'], dtype=float) + (
            S_ref - np.asarray(cal['approach_stage'], dtype=float)
        )
        approach_offset = A_common - J_00

        for i, site in enumerate(self._sites):
            r, c = divmod(i, self._cols)
            interact_global = J_00 + c * col_step + r * row_step
            approach_global = interact_global + approach_offset
            # Place the site origin at its approach point when the stage is at S_ref.
            site.setOffset(approach_global - S_ref)
            site.positions.setdefault(pip_name, {})
            site.positions[pip_name]['site global'] = approach_global.tolist()
            site.positions[pip_name]['interact global'] = interact_global.tolist()
            site.writeConfigFile(site.positions, "saved_positions")
            site._guessRotation()

    def columnSpacingMm(self, pip_name: str) -> float | None:
        """Return computed column spacing in mm (from interact corners), or None."""
        cal = self.positions.get(pip_name, {})
        needed = ('origin_interact', 'origin_stage', 'col_end_interact', 'col_end_stage')
        if any(k not in cal for k in needed) or self._cols < 2:
            return None
        J_00 = self._cornerInCommonFrame(cal, 'origin')
        J_0N = self._cornerInCommonFrame(cal, 'col_end')
        return np.linalg.norm(J_0N - J_00) / (self._cols - 1) * 1e3

    def rowSpacingMm(self, pip_name: str) -> float | None:
        """Return computed row spacing in mm (from interact corners), or None."""
        cal = self.positions.get(pip_name, {})
        needed = ('origin_interact', 'origin_stage', 'row_end_interact', 'row_end_stage')
        if any(k not in cal for k in needed) or self._rows < 2:
            return None
        J_00 = self._cornerInCommonFrame(cal, 'origin')
        J_M0 = self._cornerInCommonFrame(cal, 'row_end')
        return np.linalg.norm(J_M0 - J_00) / (self._rows - 1) * 1e3

    def approachMoveSpec(self, pip, speed='fast'):
        """Return a MoveSpec for the first site that has a saved approach position, or None."""
        for site in self._sites:
            spec = site.approachMoveSpec(pip, speed=speed)
            if spec is not None:
                return spec
        return None

    def hasApproachPosition(self, pip) -> bool:
        return any(site.hasApproachPosition(pip) for site in self._sites)

    # ------------------------------------------------------------------
    # Device interface

    def deviceInterface(self, win):
        return InteractionSiteArrayDeviceGui(self, win)

    def cameraModuleInterface(self, mod):
        return None


class InteractionSiteArrayDeviceGui(Qt.QWidget):
    def __init__(self, dev: InteractionSiteArray, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win

        main_layout = Qt.QVBoxLayout()
        self.setLayout(main_layout)

        # --- Role header ---
        main_layout.addWidget(Qt.QLabel(f"Role: {dev.role}"))

        # --- Site grid (physical layout; each button toggles used_up) ---
        grid_widget = Qt.QWidget()
        grid = Qt.QGridLayout(grid_widget)
        grid.setSpacing(2)
        main_layout.addWidget(grid_widget)

        self._site_buttons: list[Qt.QPushButton] = []
        cols = dev._cols
        for i, site in enumerate(dev.sites):
            row, col = divmod(i, cols)
            btn = Qt.QPushButton()
            btn.setCheckable(True)
            btn.setChecked(site.used_up)
            self._styleSiteButton(btn, i)
            btn.toggled.connect(self._makeUsedUpSetter(i))
            grid.addWidget(btn, row, col)
            self._site_buttons.append(btn)
            site.sigUsedUpChanged.connect(self._makeUsedUpReceiver(i))

        # --- Mark all unused button ---
        self._markAllBtn = Qt.QPushButton("Mark all unused")
        self._markAllBtn.clicked.connect(self._markAllUnused)
        main_layout.addWidget(self._markAllBtn)

        # --- Calibration section ---
        calib_group = Qt.QGroupBox("Calibration")
        calib_layout = Qt.QGridLayout()
        calib_group.setLayout(calib_layout)
        main_layout.addWidget(calib_group)

        calib_layout.addWidget(Qt.QLabel("Pipette:"), 0, 0)
        self._pipCombo = Qt.QComboBox()
        calib_layout.addWidget(self._pipCombo, 0, 1)

        calib_layout.addWidget(Qt.QLabel(f"Grid: {dev._rows} × {dev._cols}"), 1, 0)
        self._spacingLabel = Qt.QLabel("")
        calib_layout.addWidget(self._spacingLabel, 1, 1)

        self._calibBtn = Qt.QPushButton("Calibrate…")
        self._calibBtn.clicked.connect(self._startCalibration)
        calib_layout.addWidget(self._calibBtn, 2, 0, 1, 2)

        self._calibFlow = None
        self._populatePipettes()
        self._pipCombo.currentIndexChanged.connect(self._updateSpacingLabel)

    # ------------------------------------------------------------------
    # Site grid handlers

    def _styleSiteButton(self, btn, index):
        """Set a site button's label and tooltip from its position and used_up state."""
        row, col = divmod(index, self.dev._cols)
        site = self.dev.sites[index]
        offset = np.asarray(site.deviceTransform().offset, dtype=float)
        used = " (used)" if site.used_up else ""
        btn.setText(f"{row},{col}{used}")
        btn.setToolTip(f"site [{row},{col}] offset: {_fmt_pos(offset)}")

    def _makeUsedUpSetter(self, index):
        def setter(checked):
            self.dev.sites[index].used_up = bool(checked)
            self._styleSiteButton(self._site_buttons[index], index)
        return setter

    def _makeUsedUpReceiver(self, index):
        def receiver(value):
            btn = self._site_buttons[index]
            btn.blockSignals(True)
            btn.setChecked(value)
            btn.blockSignals(False)
            self._styleSiteButton(btn, index)
        return receiver

    def _markAllUnused(self):
        for site in self.dev.sites:
            site.used_up = False

    # ------------------------------------------------------------------
    # Calibration

    def _populatePipettes(self):
        pipettes = self.dev.dm.listInterfaces('pipette')
        for name in pipettes:
            self._pipCombo.addItem(name)
        has_pip = bool(pipettes)
        self._pipCombo.setEnabled(has_pip)
        self._calibBtn.setEnabled(has_pip)
        self._updateSpacingLabel()

    def _selectedPipette(self):
        name = self._pipCombo.currentText()
        if not name:
            return None
        return self.dev.dm.getDevice(name)

    def _updateSpacingLabel(self):
        pip = self._selectedPipette()
        if pip is None:
            self._spacingLabel.setText("")
            return
        parts = []
        col_mm = self.dev.columnSpacingMm(pip.name())
        if col_mm is not None:
            parts.append(f"{col_mm:.2f} mm/col")
        row_mm = self.dev.rowSpacingMm(pip.name())
        if row_mm is not None:
            parts.append(f"{row_mm:.2f} mm/row")
        self._spacingLabel.setText("  ".join(parts) if parts else "uncalibrated")

    def _startCalibration(self):
        pip = self._selectedPipette()
        if pip is None:
            return
        # Make sure the 3D visualizer is up so the user can see the sites move.
        try:
            self.dev.dm.getModule("Visualize3D")
        except Exception as exc:
            self.dev.logger.warning(f"Could not open Visualize3D for array calibration: {exc}")
        self._calibBtn.setEnabled(False)
        self._calibFlow = InteractionArrayCalibrationFlow(self.dev, pip, parent=self)
        self._calibFlow.finished.connect(self._onCalibrationFinished)
        self._calibFlow.show()
        self._calibFlow.raise_()

    def _onCalibrationFinished(self, _result):
        self._calibFlow = None
        self._calibBtn.setEnabled(self._selectedPipette() is not None)
        self._updateSpacingLabel()
        for i in range(len(self.dev.sites)):
            self._styleSiteButton(self._site_buttons[i], i)


class InteractionArrayCalibrationFlow(Qt.QDialog):
    """Modeless step-by-step calibration wizard for an InteractionSiteArray.

    Walks the user through (in order): the [0,0] interact point, the [0,0] approach
    waypoint, the [rows-1,0] interact corner, and the [0,cols-1] interact corner.
    Each step lets the user capture the current pipette position or keep a previously
    saved one. The calibration is applied automatically after the last step.
    """

    def __init__(self, dev: InteractionSiteArray, pip, parent=None):
        Qt.QDialog.__init__(self, parent)
        self.dev = dev
        self.pip = pip
        self.setWindowTitle(f"Calibrate {dev.name()}")
        self.setModal(False)

        # Build the ordered step list, skipping degenerate corners.
        self._steps = [
            ('origin', 'interact', "Site [0,0] — interact point",
             "Drive the pipette tip into the fluid at the bottom of site [0,0]."),
            ('origin', 'approach', "Site [0,0] — approach waypoint",
             "Raise the pipette to a safe waypoint above site [0,0]."),
        ]
        if dev._rows > 1:
            self._steps.append(
                ('row_end', 'interact', f"Site [{dev._rows-1},0] — interact point",
                 f"Drive the pipette tip into the fluid at the bottom of site [{dev._rows-1},0].")
            )
        if dev._cols > 1:
            self._steps.append(
                ('col_end', 'interact', f"Site [0,{dev._cols-1}] — interact point",
                 f"Drive the pipette tip into the fluid at the bottom of site [0,{dev._cols-1}].")
            )
        self._index = 0

        layout = Qt.QVBoxLayout()
        self.setLayout(layout)

        self._stepLabel = Qt.QLabel()
        f = self._stepLabel.font()
        f.setBold(True)
        self._stepLabel.setFont(f)
        layout.addWidget(self._stepLabel)

        self._instructionLabel = Qt.QLabel()
        self._instructionLabel.setWordWrap(True)
        layout.addWidget(self._instructionLabel)

        self._savedLabel = Qt.QLabel()
        layout.addWidget(self._savedLabel)

        btn_row = Qt.QHBoxLayout()
        layout.addLayout(btn_row)
        self._useBtn = Qt.QPushButton("Use current position")
        self._useBtn.clicked.connect(self._useCurrent)
        btn_row.addWidget(self._useBtn)
        self._keepBtn = Qt.QPushButton("Keep existing")
        self._keepBtn.clicked.connect(self._keepExisting)
        btn_row.addWidget(self._keepBtn)
        self._cancelBtn = Qt.QPushButton("Cancel")
        self._cancelBtn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancelBtn)

        self._showStep()

    def _currentSaved(self):
        """Return the saved value for the current step, or None."""
        corner, kind, _, _ = self._steps[self._index]
        cal = self.dev.positions.get(self.pip.name(), {})
        key = 'approach' if kind == 'approach' else f'{corner}_interact'
        return cal.get(key)

    def _showStep(self):
        corner, kind, title, instruction = self._steps[self._index]
        self._stepLabel.setText(f"Step {self._index + 1} of {len(self._steps)}: {title}")
        self._instructionLabel.setText(instruction)
        saved = self._currentSaved()
        if saved is not None:
            self._savedLabel.setText(f"Saved: {_fmt_pos(np.asarray(saved, dtype=float))}")
            self._keepBtn.setEnabled(True)
        else:
            self._savedLabel.setText("Saved: none yet")
            self._keepBtn.setEnabled(False)

    def _capture(self):
        corner, kind, _, _ = self._steps[self._index]
        if kind == 'approach':
            self.dev.calibrateApproach(self.pip)
        else:
            self.dev.calibrateInteractCorner(self.pip, corner)

    def _useCurrent(self):
        self._capture()
        self._advance()

    def _keepExisting(self):
        self._advance()

    def _advance(self):
        self._index += 1
        if self._index >= len(self._steps):
            self.dev.applyCalibration(self.pip)
            self.accept()
        else:
            self._showStep()


def _fmt_pos(pos):
    """Format a 3-element position as a string of mm values."""
    if pos is None:
        return "—"
    return "(%0.3f, %0.3f, %0.3f) mm" % tuple(p * 1e3 for p in pos[:3])
