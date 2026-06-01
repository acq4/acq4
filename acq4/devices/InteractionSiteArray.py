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

        row = 0
        calib_layout.addWidget(Qt.QLabel("Pipette:"), row, 0)
        self._pipCombo = Qt.QComboBox()
        calib_layout.addWidget(self._pipCombo, row, 1, 1, 2)
        row += 1

        calib_layout.addWidget(Qt.QLabel(f"Rows: {dev._rows}   Cols: {dev._cols}"), row, 0, 1, 3)
        row += 1

        # Single approach waypoint
        self._approachStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._approachStatus, row, 0)
        calib_layout.addWidget(Qt.QLabel("Approach waypoint:"), row, 1)
        self._setApproachBtn = Qt.QPushButton("Set")
        self._setApproachBtn.clicked.connect(self._calibrateApproach)
        calib_layout.addWidget(self._setApproachBtn, row, 2)
        row += 1

        # Origin interact [0,0]
        self._originStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._originStatus, row, 0)
        calib_layout.addWidget(Qt.QLabel("[0,0] interact:"), row, 1)
        self._setOriginBtn = Qt.QPushButton("Set")
        self._setOriginBtn.clicked.connect(self._calibrateOrigin)
        calib_layout.addWidget(self._setOriginBtn, row, 2)
        row += 1

        # Column-end interact [0, cols-1]
        self._colEndStatus = Qt.QLabel("?")
        calib_layout.addWidget(self._colEndStatus, row, 0)
        self._colSpacingLabel = Qt.QLabel(f"[0,{dev._cols-1}] interact:")
        calib_layout.addWidget(self._colSpacingLabel, row, 1)
        self._setColEndBtn = Qt.QPushButton("Set")
        self._setColEndBtn.clicked.connect(self._calibrateColEnd)
        calib_layout.addWidget(self._setColEndBtn, row, 2)
        row += 1

        # Row-end interact [rows-1, 0] — only shown when rows > 1
        self._rowEndStatus = Qt.QLabel("?")
        self._rowSpacingLabel = Qt.QLabel(f"[{dev._rows-1},0] interact:")
        self._setRowEndBtn = Qt.QPushButton("Set")
        self._setRowEndBtn.clicked.connect(self._calibrateRowEnd)
        if dev._rows > 1:
            calib_layout.addWidget(self._rowEndStatus, row, 0)
            calib_layout.addWidget(self._rowSpacingLabel, row, 1)
            calib_layout.addWidget(self._setRowEndBtn, row, 2)
            row += 1

        # Apply
        self._applyBtn = Qt.QPushButton("Apply calibration")
        self._applyBtn.clicked.connect(self._applyCalibration)
        calib_layout.addWidget(self._applyBtn, row, 0, 1, 3)

        self._populatePipettes()
        self._pipCombo.currentIndexChanged.connect(self._updateCalibStatus)

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
    # Calibration handlers

    def _populatePipettes(self):
        pipettes = self.dev.dm.listInterfaces('pipette')
        for name in pipettes:
            self._pipCombo.addItem(name)
        has_pip = bool(pipettes)
        self._pipCombo.setEnabled(has_pip)
        for btn in (self._setApproachBtn, self._setOriginBtn, self._setColEndBtn,
                    self._setRowEndBtn, self._applyBtn):
            btn.setEnabled(has_pip)
        self._updateCalibStatus()

    def _selectedPipette(self):
        name = self._pipCombo.currentText()
        if not name:
            return None
        return self.dev.dm.getDevice(name)

    def _calibrateApproach(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateApproach(pip)
            self._updateCalibStatus()

    def _calibrateOrigin(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateInteractCorner(pip, 'origin')
            self._updateCalibStatus()

    def _calibrateColEnd(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateInteractCorner(pip, 'col_end')
            self._updateCalibStatus()

    def _calibrateRowEnd(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.calibrateInteractCorner(pip, 'row_end')
            self._updateCalibStatus()

    def _applyCalibration(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.applyCalibration(pip)
            self._updateCalibStatus()
            for i in range(len(self.dev.sites)):
                self._styleSiteButton(self._site_buttons[i], i)

    def _updateCalibStatus(self):
        pip = self._selectedPipette()
        if pip is None:
            return
        pip_name = pip.name()
        cal = self.dev.positions.get(pip_name, {})

        def _mark(label, key):
            label.setText("✓" if key in cal else "?")

        _mark(self._approachStatus, 'approach')
        _mark(self._originStatus, 'origin_interact')
        _mark(self._colEndStatus, 'col_end_interact')
        _mark(self._rowEndStatus, 'row_end_interact')

        # Update spacing labels
        col_mm = self.dev.columnSpacingMm(pip_name)
        if col_mm is not None:
            self._colSpacingLabel.setText(
                f"[0,{self.dev._cols-1}] interact:  ({col_mm:.2f} mm/col)"
            )
        else:
            self._colSpacingLabel.setText(f"[0,{self.dev._cols-1}] interact:")

        row_mm = self.dev.rowSpacingMm(pip_name)
        if row_mm is not None:
            self._rowSpacingLabel.setText(
                f"[{self.dev._rows-1},0] interact:  ({row_mm:.2f} mm/row)"
            )
        else:
            self._rowSpacingLabel.setText(f"[{self.dev._rows-1},0] interact:")

        # Enable Apply only when approach and all required interact corners are ready
        has_cols = 'origin_interact' in cal and 'col_end_interact' in cal
        has_rows = self.dev._rows == 1 or 'row_end_interact' in cal
        self._applyBtn.setEnabled('approach' in cal and has_cols and has_rows)


def _fmt_pos(pos):
    """Format a 3-element position as a string of mm values."""
    if pos is None:
        return "—"
    return "(%0.3f, %0.3f, %0.3f) mm" % tuple(p * 1e3 for p in pos[:3])
