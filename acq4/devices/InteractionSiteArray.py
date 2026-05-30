# Device class for a grid array of InteractionSite objects (e.g. nucleus deposition tube arrays).
# Each slot holds its own offset in the parent stage frame, calibrated empirically from corner sites.

from __future__ import annotations

import numpy as np

from acq4.util import Qt
from .Device import Device
from .InteractionSite import InteractionSite, VALID_ROLES
from .OptomechDevice import OptomechDevice
from .Stage import Stage


class InteractionSiteArray(Device, OptomechDevice):
    """Array of cylindrical interaction sites arranged in a grid.

    Each site stores its own offset in the parent stage frame; positions are calibrated
    empirically by tagging corner sites and interpolating evenly.

    Configuration options:
      rows: int — number of rows in the grid
      cols: int — number of columns in the grid
      siteRadius: float (m) — radius of each site cylinder
      siteHeight: float (m) — height of each site cylinder
      parentDevice: str — name of parent stage device
      siteRoleDefaults: list (optional) — roles in row-major order
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
        role_defaults = config.get('siteRoleDefaults', [])
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
            role = role_defaults[i] if i < len(role_defaults) else 'empty'
            site_config = {
                'radius': siteRadius,
                'height': siteHeight,
                'role': role,
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
    def sites(self) -> list[InteractionSite]:
        return list(self._sites)

    def getSite(self, index: int) -> InteractionSite:
        return self._sites[index]

    def getFirstAvailableSite(self, role: str) -> "InteractionSite | None":
        """Return the first site with *role* that is not used_up, or None."""
        for site in self._sites:
            if site.role == role and not site.used_up:
                return site
        return None

    # ------------------------------------------------------------------
    # Calibration

    def calibrateCorner(self, pip, corner: str):
        """Record stage and pipette positions for a calibration corner.

        corner: 'origin' ([0,0]), 'col_end' ([0,cols-1]), 'row_end' ([rows-1,0])
        """
        if self._parentStage is None:
            raise RuntimeError(f"{self.name()} has no parent Stage, cannot calibrate")
        pip_name = pip.name()
        self.positions.setdefault(pip_name, {})
        self.positions[pip_name][f'{corner}_stage'] = self._parentStage.globalPosition().tolist()
        self.positions[pip_name]['approach'] = pip.globalPosition().tolist()
        self.writeConfigFile(self.positions, "saved_positions")

    def calibrateInteract(self, pip):
        """Record the pipette interact position (tip inside a reference site) for all sites."""
        pip_name = pip.name()
        interact_global = np.asarray(pip.globalPosition(), dtype=float)
        self.positions.setdefault(pip_name, {})
        self.positions[pip_name]['interact_global'] = interact_global.tolist()
        self.writeConfigFile(self.positions, "saved_positions")

        for site in self._sites:
            site.positions.setdefault(pip_name, {})
            site.positions[pip_name]['interact global'] = interact_global.tolist()
            site.writeConfigFile(site.positions, "saved_positions")
            site._guessRotation()

    def applySpacing(self, pip):
        """Interpolate all site offsets from the calibrated corners and write approach positions.

        Requires calibrateCorner for 'origin', 'col_end' (and 'row_end' when rows > 1).
        Each site gets its own offset in the parent stage frame so that when the stage moves
        to bring site [r,c] to the pipette approach position, the site arrives at the correct
        spot. All sites share the same approach global and interact global.
        """
        pip_name = pip.name()
        cal = self.positions.get(pip_name, {})
        P = np.asarray(cal['approach'], dtype=float)
        S_00 = np.asarray(cal['origin_stage'], dtype=float)
        S_0_N = np.asarray(cal['col_end_stage'], dtype=float)

        col_step = (S_0_N - S_00) / (self._cols - 1) if self._cols > 1 else np.zeros(3)
        if self._rows > 1:
            S_M_0 = np.asarray(cal['row_end_stage'], dtype=float)
            row_step = (S_M_0 - S_00) / (self._rows - 1)
        else:
            row_step = np.zeros(3)

        for i, site in enumerate(self._sites):
            r, c = divmod(i, self._cols)
            # Stage position when this site will be under the pipette.
            S_r_c = S_00 + c * col_step + r * row_step
            # Site offset in parent frame so site.globalPosition() == P when stage is at S_r_c.
            site_offset = P - S_r_c
            site.setOffset(site_offset)
            # Record approach position for the motion planner.
            site.positions.setdefault(pip_name, {})
            site.positions[pip_name]['site global'] = P.tolist()
            site.writeConfigFile(site.positions, "saved_positions")
            site._guessRotation()

    def columnSpacingMm(self, pip_name: str) -> float | None:
        """Return computed column spacing in mm, or None if not yet calibrated."""
        cal = self.positions.get(pip_name, {})
        if 'origin_stage' not in cal or 'col_end_stage' not in cal or self._cols < 2:
            return None
        span = np.linalg.norm(np.array(cal['col_end_stage']) - np.array(cal['origin_stage']))
        return span / (self._cols - 1) * 1e3

    def rowSpacingMm(self, pip_name: str) -> float | None:
        """Return computed row spacing in mm, or None if not yet calibrated."""
        cal = self.positions.get(pip_name, {})
        if 'origin_stage' not in cal or 'row_end_stage' not in cal or self._rows < 2:
            return None
        span = np.linalg.norm(np.array(cal['row_end_stage']) - np.array(cal['origin_stage']))
        return span / (self._rows - 1) * 1e3

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


def _centered(widget):
    """Wrap a widget in a centered container for use as a QTableWidget cell widget."""
    container = Qt.QWidget()
    layout = Qt.QHBoxLayout(container)
    layout.addWidget(widget)
    layout.setAlignment(Qt.Qt.AlignCenter)
    layout.setContentsMargins(0, 0, 0, 0)
    return container


class InteractionSiteArrayDeviceGui(Qt.QWidget):
    def __init__(self, dev: InteractionSiteArray, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win

        main_layout = Qt.QVBoxLayout()
        self.setLayout(main_layout)

        # --- Slot table ---
        self._table = Qt.QTableWidget(len(dev.sites), 3)
        self._table.setHorizontalHeaderLabels(["Slot", "Role", "Used up"])
        self._table.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self._table)

        self._role_combos: list[Qt.QComboBox] = []
        self._used_up_checks: list[Qt.QCheckBox] = []
        cols = dev._cols

        for i, site in enumerate(dev.sites):
            row, col = divmod(i, cols)
            slot_item = Qt.QTableWidgetItem(f"{row},{col}")
            slot_item.setTextAlignment(Qt.Qt.AlignCenter)
            slot_item.setFlags(Qt.Qt.ItemIsEnabled)
            self._table.setItem(i, 0, slot_item)

            combo = Qt.QComboBox()
            for role in VALID_ROLES:
                combo.addItem(role)
            combo.setCurrentText(site.role)
            combo.currentTextChanged.connect(self._makeRoleSetter(i))
            self._table.setCellWidget(i, 1, _centered(combo))
            self._role_combos.append(combo)

            check = Qt.QCheckBox()
            check.setChecked(site.used_up)
            check.stateChanged.connect(self._makeUsedUpSetter(i))
            self._table.setCellWidget(i, 2, _centered(check))
            self._used_up_checks.append(check)

            site.sigRoleChanged.connect(self._makeRoleReceiver(i))
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

        row = 0
        calib_layout.addWidget(Qt.QLabel("Pipette:"), row, 0)
        self._pipCombo = Qt.QComboBox()
        calib_layout.addWidget(self._pipCombo, row, 1, 1, 2)
        row += 1

        calib_layout.addWidget(Qt.QLabel(f"Rows: {dev._rows}   Cols: {dev._cols}"), row, 0, 1, 3)
        row += 1

        # Origin [0,0]
        self._originStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._originStatus, row, 0)
        calib_layout.addWidget(Qt.QLabel("[0,0] approach:"), row, 1)
        self._setOriginBtn = Qt.QPushButton("Set")
        self._setOriginBtn.clicked.connect(self._calibrateOrigin)
        calib_layout.addWidget(self._setOriginBtn, row, 2)
        row += 1

        # Column end [0, cols-1]
        self._colEndStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._colEndStatus, row, 0)
        self._colSpacingLabel = Qt.QLabel(f"[0,{dev._cols-1}] approach:")
        calib_layout.addWidget(self._colSpacingLabel, row, 1)
        self._setColEndBtn = Qt.QPushButton("Set")
        self._setColEndBtn.clicked.connect(self._calibrateColEnd)
        calib_layout.addWidget(self._setColEndBtn, row, 2)
        row += 1

        # Row end [rows-1, 0] — only shown when rows > 1
        self._rowEndStatus = Qt.QLabel("?")
        self._rowSpacingLabel = Qt.QLabel(f"[{dev._rows-1},0] approach:")
        self._setRowEndBtn = Qt.QPushButton("Set")
        self._setRowEndBtn.clicked.connect(self._calibrateRowEnd)
        if dev._rows > 1:
            calib_layout.addWidget(self._rowEndStatus, row, 0)
            calib_layout.addWidget(self._rowSpacingLabel, row, 1)
            calib_layout.addWidget(self._setRowEndBtn, row, 2)
            row += 1

        # Interact depth
        self._interactStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._interactStatus, row, 0)
        calib_layout.addWidget(Qt.QLabel("Interact depth:"), row, 1)
        self._setInteractBtn = Qt.QPushButton("Set")
        self._setInteractBtn.clicked.connect(self._calibrateInteract)
        calib_layout.addWidget(self._setInteractBtn, row, 2)
        row += 1

        # Apply
        self._applyBtn = Qt.QPushButton("Apply spacing")
        self._applyBtn.clicked.connect(self._applySpacing)
        calib_layout.addWidget(self._applyBtn, row, 0, 1, 3)

        self._populatePipettes()
        self._pipCombo.currentIndexChanged.connect(self._updateCalibStatus)

    # ------------------------------------------------------------------
    # Slot table handlers

    def _makeRoleSetter(self, index):
        def setter(text):
            self.dev.sites[index].role = text
        return setter

    def _makeUsedUpSetter(self, index):
        def setter(state):
            self.dev.sites[index].used_up = (state == Qt.Qt.Checked)
        return setter

    def _makeRoleReceiver(self, index):
        def receiver(value):
            combo = self._role_combos[index]
            combo.blockSignals(True)
            combo.setCurrentText(value)
            combo.blockSignals(False)
        return receiver

    def _makeUsedUpReceiver(self, index):
        def receiver(value):
            check = self._used_up_checks[index]
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        return receiver

    def _markAllUnused(self):
        for site in self.dev.sites:
            site.used_up = False

    # ------------------------------------------------------------------
    # Calibration handlers

    def _populatePipettes(self):
        pipettes = self.dev.dm.listInterfaces('pipette')
        for name in pipettes:
            self._pipCombo.addItem(name)
        has_pip = bool(pipettes)
        self._pipCombo.setEnabled(has_pip)
        for btn in (self._setOriginBtn, self._setColEndBtn, self._setRowEndBtn,
                    self._setInteractBtn, self._applyBtn):
            btn.setEnabled(has_pip)
        self._updateCalibStatus()

    def _selectedPipette(self):
        name = self._pipCombo.currentText()
        if not name:
            return None
        return self.dev.dm.getDevice(name)

    def _calibrateOrigin(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateCorner(pip, 'origin')
            self._updateCalibStatus()

    def _calibrateColEnd(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateCorner(pip, 'col_end')
            self._updateCalibStatus()

    def _calibrateRowEnd(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateCorner(pip, 'row_end')
            self._updateCalibStatus()

    def _calibrateInteract(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateInteract(pip)
            self._updateCalibStatus()

    def _applySpacing(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.applySpacing(pip)
            self._updateCalibStatus()

    def _updateCalibStatus(self):
        pip = self._selectedPipette()
        if pip is None:
            return
        pip_name = pip.name()
        cal = self.dev.positions.get(pip_name, {})

        def _mark(label, key):
            label.setText("✓" if key in cal else "?")

        _mark(self._originStatus, 'origin_stage')
        _mark(self._colEndStatus, 'col_end_stage')
        _mark(self._rowEndStatus, 'row_end_stage')
        _mark(self._interactStatus, 'interact_global')

        # Update spacing labels
        col_mm = self.dev.columnSpacingMm(pip_name)
        if col_mm is not None:
            self._colSpacingLabel.setText(
                f"[0,{self.dev._cols-1}] approach:  ({col_mm:.2f} mm/col)"
            )
        else:
            self._colSpacingLabel.setText(f"[0,{self.dev._cols-1}] approach:")

        row_mm = self.dev.rowSpacingMm(pip_name)
        if row_mm is not None:
            self._rowSpacingLabel.setText(
                f"[{self.dev._rows-1},0] approach:  ({row_mm:.2f} mm/row)"
            )
        else:
            self._rowSpacingLabel.setText(f"[{self.dev._rows-1},0] approach:")

        # Enable Apply only when all required corners are ready
        has_cols = 'origin_stage' in cal and 'col_end_stage' in cal
        has_rows = self.dev._rows == 1 or 'row_end_stage' in cal
        self._applyBtn.setEnabled(has_cols and has_rows)


def _fmt_pos(pos):
    """Format a 3-element position as a string of mm values."""
    if pos is None:
        return "—"
    return "(%0.3f, %0.3f, %0.3f) mm" % tuple(p * 1e3 for p in pos[:3])
