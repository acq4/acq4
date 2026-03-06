import numpy as np

import pyqtgraph as pg
from acq4 import getManager
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt
from .Device import Device
from .OptomechDevice import OptomechDevice
from .Stage import Stage
from ..util.future import future_wrap, FutureButton, Future
from ..util.target import color_for_diff


class InteractionSite(Device, OptomechDevice):
    """Describes the location and dimensions of a cylindrical zone of interaction, such as a
    recording chamber, a nucleus deposition tube or a cleaning well.

    Configuration options:

    * radius: The radius of the site (m)
    * height: The height of the site (m)
    * transform: (dict) Transformation setting the position/orientation of the site.  E.g. pos
    * geometry: Optional settings for visualizing the site in the 3D visualizer. See OptomechDevice
        for details.
    * parentDevice: Optional name of parent device for coordinate transforms.  E.g. a stage that
        the site is mounted on.
    """

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.radius = config["radius"]
        self.height = config.get("height")
        if self.height is None:
            raise ValueError(f"{self.name()} must have a height specified in config")
        OptomechDevice.__init__(self, dm, config, name)
        if tuple(self.globalPosition()) != (0, 0, 0):
            raise ValueError(f"{self.name()} cannot have a cfg-set global pos; only rotations allowed")
        self.positions = self.readConfigFile("saved_positions")
        parent = self
        while True:
            parent = parent.parentDevice()
            if parent is None or isinstance(parent, Stage):
                break
        self._parentStage: Stage | None = parent
        self.offset = self.positions.get(self.name(), {}).get("offset", [0, 0, 0])
        self.setOffset(self.offset)

    def getGeometry(self, name=None):
        if isinstance(self.config.get("geometry"), dict):
            defaults = {"color": (0.3, 0.3, 0.3, 0.7)}
            defaults.update(self.config["geometry"])
            self.config["geometry"] = defaults
        else:
            self.config["geometry"] = {
                "color": (0.3, 0.3, 0.3, 0.7),
                "type": "cylinder",
                "radius": self.radius,
                "height": self.height,
            }
        return super().getGeometry(name)

    def setOffset(self, offset):
        """Set the offset of the site from its configured position, and save to config."""
        self.offset = offset
        self.positions.setdefault(self.name(), {})
        self.positions[self.name()]['offset'] = offset
        self.writeConfigFile(self.positions, "saved_positions")
        # TODO change this to be compatible with coorx after merging axis-of-diagonevil
        tr = pg.SRTTransform3D(self.deviceTransform())
        tr.setTranslate(*offset)
        self.setDeviceTransform(tr)

        self.sigTransformChanged.emit(self)

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module."""
        return InteractionSiteCameraInterface(self, mod)

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack."""
        return InteractionSiteDeviceGui(self, win)

    def globalPosition(self):
        return self.mapToGlobal([0, 0, 0])

    def moveToGlobal(self, pos, speed, **kwds):
        """Move the parent stage so that this site's origin arrives at *pos* in global coordinates."""
        if self._parentStage is None:
            raise RuntimeError(f"{self.name()} has no parent Stage device and cannot be moved.")
        dif = np.asarray(pos) - np.asarray(self.globalPosition())
        stage_pos = np.asarray(self._parentStage.globalPosition()) + dif
        return self._parentStage.moveToGlobal(stage_pos, speed, **kwds)

    def containsPoint(self, pt, tolerance=1e-9):
        """Return True if the x,y,z coordinates in *pt* lie within the boundaries of this site."""
        local_pt = self.mapFromGlobal(pt)
        return (
            local_pt[0] ** 2 + local_pt[1] ** 2 <= self.radius ** 2 + tolerance
            and -tolerance <= local_pt[2] <= self.height + tolerance
        )

    def saveInteractPosition(self, other):
        self.positions.setdefault(other.name(), {})
        self.positions[other.name()]['interact local'] = self.mapFromGlobal(other.globalPosition())
        self.positions[other.name()]['site global'] = self.globalPosition()
        self.writeConfigFile(self.positions, "saved_positions")

    def saveApproachPosition(self, other):
        self.positions.setdefault(other.name(), {})
        interact_pos = self.positions[other.name()].get('interact local')
        if interact_pos is not None:
            interact_global = self.mapToGlobal(interact_pos)
            self.setOffset(other.globalPosition())
            self.positions[other.name()]['interact local'] = self.mapFromGlobal(interact_global)
        else:
            self.setOffset(other.globalPosition())
        self.positions[other.name()]['approach local'] = self.mapFromGlobal(other.globalPosition())
        self.positions[other.name()]['site global'] = self.globalPosition()
        self.writeConfigFile(self.positions, "saved_positions")

    @future_wrap
    def moveToInteract(self, other, speed='fast', _future=None):
        if other.name() not in self.positions:
            raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
        pos_config = self.positions[other.name()]
        if 'interact local' not in pos_config:
            raise RuntimeError(f"No interact position saved for {other.name()} at {self.name()}")
        if 'site global' not in pos_config:
            raise RuntimeError(f"No site global position saved for {other.name()} at {self.name()}")
        if 'approach local' not in pos_config:
            raise RuntimeError(f"No approach position saved for {other.name()} at {self.name()}")
        if self._parentStage is not None:
            # TODO this will still need a real motion planner
            # TODO we'll maybe also need to make sure the other devices are out of the way...
            _future.waitFor(self.moveToGlobal(pos_config['site global'], speed=speed))
        approach_local = pos_config['approach local']
        approach_global = self.mapToGlobal(approach_local)
        _future.waitFor(other._moveToGlobal(approach_global, speed=speed))
        interact_local = pos_config['interact local']
        interact_global = self.mapToGlobal(interact_local)
        _future.waitFor(other._moveToGlobal(interact_global, speed=speed))


def _fmt_pos(pos):
    """Format a 3-element position as a string of mm values."""
    if pos is None:
        return "—"
    return "(%0.3f, %0.3f, %0.3f) mm" % tuple(p * 1e3 for p in pos[:3])


class InteractionSiteDeviceGui(Qt.QWidget):
    def __init__(self, dev, win):
        Qt.QWidget.__init__(self)
        self.dev = dev
        self.win = win

        layout = Qt.QGridLayout()
        self.setLayout(layout)
        row = 0

        self.pipetteCombo = Qt.QComboBox()
        layout.addWidget(self.pipetteCombo, row, 0)

        self.saveApproachBtn = Qt.QPushButton("Save approach position")
        self.saveApproachBtn.clicked.connect(self._saveApproach)
        layout.addWidget(self.saveApproachBtn, row, 1)
        row += 1

        self.saveInteractBtn = Qt.QPushButton("Save interact position")
        self.saveInteractBtn.clicked.connect(self._saveInteract)
        layout.addWidget(self.saveInteractBtn, row, 1)
        row += 1

        # Position displays
        layout.addWidget(Qt.QLabel("Global site position:"), row, 0)
        self.globalCenterLabel = Qt.QLabel("—")
        layout.addWidget(self.globalCenterLabel, row, 1)
        row += 1

        layout.addWidget(Qt.QLabel("Approach (relative):"), row, 0)
        self.approachLabel = Qt.QLabel("—")
        layout.addWidget(self.approachLabel, row, 1)
        row += 1

        layout.addWidget(Qt.QLabel("Interact (relative):"), row, 0)
        self.interactLabel = Qt.QLabel("—")
        layout.addWidget(self.interactLabel, row, 1)
        row += 1

        layout.addWidget(Qt.QLabel("( for testing )"), row, 0)
        self.doInteractBtn = FutureButton(
            self._doInteractForTest, "Do test interact!", stoppable=True
        )
        layout.addWidget(self.doInteractBtn, row, 1)

        self._populatePipettes()
        self.pipetteCombo.currentIndexChanged.connect(self._updatePositionLabels)

    def _populatePipettes(self):
        from .Pipette.pipette import Pipette
        man = getManager()
        pipettes = [name for name in man.listDevices() if isinstance(man.getDevice(name), Pipette)]
        has_pipettes = bool(pipettes)
        for name in pipettes:
            self.pipetteCombo.addItem(name)
        self.pipetteCombo.setEnabled(has_pipettes)
        self.saveApproachBtn.setEnabled(has_pipettes)
        self.saveInteractBtn.setEnabled(has_pipettes)
        self.doInteractBtn.setEnabled(has_pipettes)
        self._updatePositionLabels()

    def _selectedPipette(self):
        name = self.pipetteCombo.currentText()
        if not name:
            return None
        return getManager().getDevice(name)

    def _saveApproach(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.saveApproachPosition(pip)
            self._updatePositionLabels()

    def _saveInteract(self):
        pip = self._selectedPipette()
        if pip is not None:
            self.dev.saveInteractPosition(pip)
            self._updatePositionLabels()

    def _doInteractForTest(self):
        pip = self._selectedPipette()
        if pip is not None:
            return self.dev.moveToInteract(pip, speed='slow')
        return Future.immediate()

    def _updatePositionLabels(self):
        positions = {}
        pip = self._selectedPipette()
        if pip is not None and pip.name() in self.dev.positions:
            positions = self.dev.positions[pip.name()]
        self.globalCenterLabel.setText(_fmt_pos(positions.get('site global')))
        self.approachLabel.setText(_fmt_pos(positions.get('approach local')))
        self.interactLabel.setText(_fmt_pos(positions.get('interact local')))


class InteractionSiteCameraInterface(CameraModuleInterface):

    canImage = False

    def __init__(self, dev, win):
        CameraModuleInterface.__init__(self, dev, win)
        x, y, z = self.dev().globalPosition()
        radius = self.dev().radius
        self.boundingEllipse = Qt.QGraphicsEllipseItem(-1, -1, 2, 2)
        self.boundingEllipse.setScale(radius)
        win.addItem(self.boundingEllipse, ignoreBounds=True)
        self.boundingEllipse.setPos(x, y)
        self._name = pg.TextItem(text=dev.name())
        win.addItem(self._name, ignoreBounds=True)
        self._name.setPos(x + radius, y)
        win.sigFocusPositionChanged.connect(self._handleFocusChange)
        dev.sigGlobalTransformChanged.connect(self._updateGraphics)
        self._updateGraphics(None, None)

    def _updateGraphics(self, _, __):
        center = self.dev().globalPosition()
        self.boundingEllipse.setPos(center[0], center[1])
        self._name.setPos(center[0] + self.dev().radius, center[1])
        self._handleFocusChange()

    def _handleFocusChange(self):
        center = self.dev().globalPosition()
        focus = self.win().globalCenterOfFocus()
        diff = 0
        if focus is not None:
            if focus[2] < center[2]:
                diff = focus[2] - center[2]
            elif focus[2] > center[2] + self.dev().height:
                diff = focus[2] - (center[2] + self.dev().height)
        self.boundingEllipse.setPen(pg.mkPen(color_for_diff(diff)))
        self._name.setColor(color_for_diff(diff))

    def boundingRect(self):
        return None
        # we don't want the camera module to auto-range to this item.
        # return self.boundingEllipse.boundingRect()

    def graphicsItems(self):
        return [self.boundingEllipse, self._name]
