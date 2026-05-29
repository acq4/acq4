# Device class for a grid array of InteractionSite objects (e.g. nucleus deposition tube arrays).
# Each slot is a real InteractionSite child whose position is offset from the array origin.

from __future__ import annotations

import numpy as np

from acq4.util import Qt
from .Device import Device
from .InteractionSite import InteractionSite, VALID_ROLES
from .OptomechDevice import OptomechDevice
from .Stage import Stage


class InteractionSiteArray(Device, OptomechDevice):
    """Array of cylindrical interaction sites arranged in a grid.

    Configuration options:
      rows: int — number of rows in the grid
      cols: int — number of columns in the grid
      spacing_x: float (m) — x spacing between adjacent columns
      spacing_y: float (m) — y spacing between adjacent rows
      site_radius: float (m) — radius of each site cylinder
      site_height: float (m) — height of each site cylinder
      parentDevice: str — name of parent stage device (same as OptomechDevice)
      transform: dict — optional transform (same as OptomechDevice)
      site_role_defaults: list (optional) — roles in row-major order; length may be
        shorter than rows*cols, remaining sites default to 'empty'
    """

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self._rows = config['rows']
        self._cols = config['cols']
        self._spacing_x = config['spacing_x']
        self._spacing_y = config['spacing_y']
        site_radius = config['site_radius']
        site_height = config['site_height']
        role_defaults = config.get('site_role_defaults', [])

        self.positions = self.readConfigFile("saved_positions")
        array_offset = np.asarray(
            self.positions.get(self.name(), {}).get("offset", [0, 0, 0]), dtype=float
        )

        self._sites: list[InteractionSite] = []
        n = self._rows * self._cols
        for i in range(n):
            row = i // self._cols
            col = i % self._cols
            site_name = f"{name}[{i}]"
            role = role_defaults[i] if i < len(role_defaults) else 'empty'
            site_config = {
                'radius': site_radius,
                'height': site_height,
                'role': role,
            }
            site = InteractionSite(dm, site_config, site_name)
            # attach as child of this array so transforms compose correctly
            site.setParentDevice(self)
            # set the site's local offset within the array frame
            site.setOffset(np.array([col * self._spacing_x, row * self._spacing_y, 0.0]))
            dm.declareInterface(site_name, ['device', 'interactionSite'], site)
            self._sites.append(site)

        tr = self.deviceTransform()
        tr.offset = array_offset
        self.setDeviceTransform(tr)

    # ------------------------------------------------------------------
    # Site access

    @property
    def sites(self) -> list[InteractionSite]:
        """Return a copy of the list of child InteractionSite objects."""
        return list(self._sites)

    def getSite(self, index: int) -> InteractionSite:
        """Return the child site at *index* (row-major order)."""
        return self._sites[index]

    def getFirstAvailableSite(self, role: str) -> "InteractionSite | None":
        """Return the first site with *role* that is not used_up, or None."""
        for site in self._sites:
            if site.role == role and not site.used_up:
                return site
        return None

    # ------------------------------------------------------------------
    # Calibration

    def setArrayOriginFromPipette(self, pip, reference_slot_index: int):
        """Position the array so that reference_slot is at the pipette's current position.

        Computes the array's parent-frame offset and saves it to config.
        """
        pip_global = np.asarray(pip.globalPosition(), dtype=float)
        site_in_array = np.array([
            (reference_slot_index % self._cols) * self._spacing_x,
            (reference_slot_index // self._cols) * self._spacing_y,
            0.0,
        ])
        desired_array_global = pip_global - site_in_array
        new_offset = self.mapGlobalToParent(desired_array_global)
        self._setOffset(new_offset)

    def _setOffset(self, offset):
        """Set the array's local offset and persist it (same pattern as InteractionSite.setOffset)."""
        tr = self.deviceTransform()
        tr.offset = offset
        self.setDeviceTransform(tr)
        self.positions.setdefault(self.name(), {})
        self.positions[self.name()]['offset'] = list(offset)
        self.writeConfigFile(self.positions, "saved_positions")
        self.sigTransformChanged.emit(self)

    def saveInteractPosition(self, pip):
        """Save pip's current global position as the interact position in each site's local frame."""
        for site in self._sites:
            # Store interact position in each site's local frame so that,
            # after a stage move, mapToGlobal(local) still gives the right global position.
            site.positions.setdefault(pip.name(), {})
            # avoid the "only one device per site" guard in InteractionSite.saveInteractPosition
            interact_global = np.asarray(pip.globalPosition(), dtype=float)
            interact_local = site.mapFromGlobal(interact_global)
            site.positions[pip.name()]['interact global'] = interact_global.tolist()
            site.positions[pip.name()]['interact local'] = interact_local.tolist()
            site.writeConfigFile(site.positions, "saved_positions")

    def approachMoveSpec(self, pip, speed='fast'):
        """Return a MoveSpec for the first site that has a saved approach position, or None."""
        for site in self._sites:
            spec = site.approachMoveSpec(pip, speed=speed)
            if spec is not None:
                return spec
        return None

    def hasApproachPosition(self, pip) -> bool:
        """Return True if any site has a saved approach position for pip."""
        return any(site.hasApproachPosition(pip) for site in self._sites)

    # ------------------------------------------------------------------
    # Device interface

    def deviceInterface(self, win):
        """Return the array management widget."""
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

        # --- Slot table ---
        self._table = Qt.QTableWidget(len(dev.sites), 3)
        self._table.setHorizontalHeaderLabels(["Slot", "Role", "Used up"])
        self._table.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self._table)

        self._role_combos: list[Qt.QComboBox] = []
        self._used_up_checks: list[Qt.QCheckBox] = []

        for i, site in enumerate(dev.sites):
            slot_item = Qt.QTableWidgetItem(str(i))
            slot_item.setFlags(Qt.Qt.ItemIsEnabled)
            self._table.setItem(i, 0, slot_item)

            combo = Qt.QComboBox()
            for role in VALID_ROLES:
                combo.addItem(role)
            combo.setCurrentText(site.role)
            combo.currentTextChanged.connect(self._makeRoleSetter(i))
            self._table.setCellWidget(i, 1, combo)
            self._role_combos.append(combo)

            check = Qt.QCheckBox()
            check.setChecked(site.used_up)
            check.stateChanged.connect(self._makeUsedUpSetter(i))
            self._table.setCellWidget(i, 2, check)
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

        calib_layout.addWidget(Qt.QLabel("Pipette:"), 0, 0)
        self._pipCombo = Qt.QComboBox()
        calib_layout.addWidget(self._pipCombo, 0, 1)

        calib_layout.addWidget(Qt.QLabel("Reference slot:"), 1, 0)
        self._refSlotCombo = Qt.QComboBox()
        for i in range(len(dev.sites)):
            self._refSlotCombo.addItem(str(i))
        calib_layout.addWidget(self._refSlotCombo, 1, 1)

        self._setOriginBtn = Qt.QPushButton("Set array origin")
        self._setOriginBtn.clicked.connect(self._setArrayOrigin)
        calib_layout.addWidget(self._setOriginBtn, 2, 0, 1, 2)

        self._saveInteractBtn = Qt.QPushButton("Set interact position")
        self._saveInteractBtn.clicked.connect(self._saveInteractPosition)
        calib_layout.addWidget(self._saveInteractBtn, 3, 0, 1, 2)

        calib_layout.addWidget(Qt.QLabel("Array origin (global):"), 4, 0)
        self._originLabel = Qt.QLabel("—")
        calib_layout.addWidget(self._originLabel, 4, 1)

        calib_layout.addWidget(Qt.QLabel("Interact position (site-local):"), 5, 0)
        self._interactLabel = Qt.QLabel("—")
        calib_layout.addWidget(self._interactLabel, 5, 1)

        self._populatePipettes()
        self._pipCombo.currentIndexChanged.connect(self._updateCalibLabels)

    def _makeRoleSetter(self, index):
        def setter(text):
            self.dev.sites[index].role = text
        return setter

    def _makeUsedUpSetter(self, index):
        def setter(state):
            self.dev.sites[index].used_up = bool(state)
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

    def _populatePipettes(self):
        pipettes = self.dev.dm.listInterfaces('pipette')
        for name in pipettes:
            self._pipCombo.addItem(name)
        has_pip = bool(pipettes)
        self._pipCombo.setEnabled(has_pip)
        self._setOriginBtn.setEnabled(has_pip)
        self._saveInteractBtn.setEnabled(has_pip)
        self._updateCalibLabels()

    def _selectedPipette(self):
        name = self._pipCombo.currentText()
        if not name:
            return None
        return self.dev.dm.getDevice(name)

    def _setArrayOrigin(self):
        pip = self._selectedPipette()
        if pip is not None:
            ref = int(self._refSlotCombo.currentText())
            self.dev.setArrayOriginFromPipette(pip, ref)
            self._updateCalibLabels()

    def _saveInteractPosition(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.saveInteractPosition(pip)
            self._updateCalibLabels()

    def _updateCalibLabels(self):
        origin = self.dev.mapToGlobal(np.zeros(3))
        self._originLabel.setText(_fmt_pos(origin))
        pip = self._selectedPipette()
        if pip is not None and self.dev.sites:
            local = self.dev.sites[0].interactLocalFor(pip)
            self._interactLabel.setText(_fmt_pos(local))
        else:
            self._interactLabel.setText("—")


def _fmt_pos(pos):
    """Format a 3-element position as a string of mm values."""
    if pos is None:
        return "—"
    return "(%0.3f, %0.3f, %0.3f) mm" % tuple(p * 1e3 for p in pos[:3])
