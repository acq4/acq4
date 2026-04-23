import numpy as np

import pyqtgraph as pg
from acq4 import getManager
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt
from .Device import Device
from .OptomechDevice import OptomechDevice
from .Stage import Stage
from ..util.future import future_wrap, Future
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
        # self._approach_stage_path = None  # used by current moveToApproach/_unwindKludgePath
        if self.height is None:
            raise ValueError(f"{self.name()} must have a height specified in config")
        OptomechDevice.__init__(self, dm, config, name)
        if tuple(self.deviceTransform().offset) != (0, 0, 0):
            raise ValueError(
                f"{self.name()} cannot have a cfg-set global pos; only rotations allowed"
            )
        self.positions = self.readConfigFile("saved_positions")
        parent = self
        while True:
            parent = parent.parentDevice()
            if parent is None or isinstance(parent, Stage):
                break
        self._parentStage: Stage | None = parent
        offset = self.positions.get(self.name(), {}).get("offset", [0, 0, 0])
        self.setOffset(np.asarray(offset))
        self._guessRotation()

    def _guessRotation(self):
        for other_name, pos_config in self.positions.items():
            if other_name == self.name():
                continue
            if 'site global' in pos_config and 'interact global' in pos_config:
                self._inferAngle(pos_config['site global'], pos_config['interact global'])
                return

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

    def setLocalOrigin(self, global_pos):
        """Set the device's local coordinate origin, given the provided global_pos, and save to config."""
        self.setOffset(self.mapGlobalToParent(global_pos))

    def setOffset(self, offset):
        """Set the offset of the site from its configured position, and save to config."""
        tr = self.deviceTransform()
        tr.offset = offset
        self.setDeviceTransform(tr)
        self.positions.setdefault(self.name(), {})
        self.positions[self.name()]['offset'] = offset
        self.writeConfigFile(self.positions, "saved_positions")

        self.sigTransformChanged.emit(self)

    def setRotation(self, angle, axis):
        """Set the rotation of the site from its configured position, and save to config."""
        tr = self.deviceTransform()
        tr.rotation = (angle, axis)
        self.setDeviceTransform(tr)
        self.positions.setdefault(self.name(), {})
        self.positions[self.name()]['rotation'] = [angle, axis]
        self.writeConfigFile(self.positions, "saved_positions")

        self.sigTransformChanged.emit(self)

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module."""
        return InteractionSiteCameraInterface(self, mod)

    def deviceInterface(self, win):
        """Return a widget with a UI to put in the device rack."""
        return InteractionSiteDeviceGui(self, win)

    def globalPosition(self):
        return self.mapToGlobal(np.asarray([0, 0, 0]))

    def moveToGlobal(self, pos, speed, **kwds):
        """Move the parent stage so that this site's origin arrives at *pos* in global coordinates."""
        if self._parentStage is None:
            raise RuntimeError(f"{self.name()} has no parent Stage device and cannot be moved.")
        dif = np.asarray(pos) - self.globalPosition()
        stage_pos = np.asarray(self._parentStage.globalPosition()) + dif
        return self._parentStage.moveToGlobal(stage_pos, speed, **kwds)

    def containsPoint(self, pt, tolerance=1e-9):
        """Return True if the x,y,z coordinates in *pt* lie within the boundaries of this site."""
        for _, pos_config in self.positions.items():
            if 'site global' in pos_config and 'interact global' in pos_config:
                if np.linalg.norm(np.array(pos_config['site global']) - np.array(pt)) < tolerance:
                    return True
                if np.linalg.norm(np.array(pos_config['interact global']) - np.array(pt)) < tolerance:
                    return True
        local_pt = self.mapFromGlobal(pt)
        return (
            local_pt[0] ** 2 + local_pt[1] ** 2 <= self.radius**2 + tolerance
            and -tolerance <= local_pt[2] <= self.height + tolerance
        )

    def saveInteractPosition(self, other):
        self.positions.setdefault(other.name(), {})
        if len([p for p in self.positions if p != self.name()]) > 1:
            raise RuntimeError("Only one device can be saved for each interaction site")
        self._inferAngle(self.globalPosition(), other.globalPosition())
        self.positions[other.name()]['interact global'] = other.globalPosition()
        self.writeConfigFile(self.positions, "saved_positions")

    def saveApproachPosition(self, other):
        self.positions.setdefault(other.name(), {})
        if len([p for p in self.positions if p != self.name()]) > 1:
            raise RuntimeError("Only one device can be saved for each interaction site")
        if 'interact global' in self.positions[other.name()]:
            interact_local = self.mapFromGlobal(self.positions[other.name()]['interact global'])
            self.setLocalOrigin(other.globalPosition())
            self.positions[other.name()]['interact global'] = self.mapToGlobal(interact_local)
        else:
            self.setLocalOrigin(other.globalPosition())
        self.positions[other.name()]['site global'] = self.globalPosition()
        self.writeConfigFile(self.positions, "saved_positions")

    def _inferAngle(self, a, b):
        """Given two global points, infer the rotation of the site that would be needed to align
        its local "down" direction with the direction from a to b."""
        canonical = np.array([0.0, 0.0, -1.0])  # "down" into the well
        direction = np.array(b) - np.array(a)
        direction = direction / np.linalg.norm(direction)

        dot = np.clip(np.dot(canonical, direction), -1.0, 1.0)
        angle = np.arccos(dot)

        cross = np.cross(direction, canonical)
        cross_len = np.linalg.norm(cross)

        if cross_len < 1e-9:
            # Parallel or anti-parallel
            axis = np.array([1.0, 0.0, 0.0])
            # angle is already 0 or π from arccos
        else:
            axis = cross / cross_len

        tr = self.deviceTransform()
        tr.rotation = (np.degrees(angle), axis)
        self.setDeviceTransform(tr)

    @future_wrap
    def moveToInteract(self, other, speed='fast', _future=None):
        if other.name() not in self.positions:
            raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
        pos_config = self.positions[other.name()]
        if 'site global' not in pos_config:
            raise RuntimeError(f"No site global position saved for {other.name()} at {self.name()}")
        if 'interact global' not in pos_config:
            raise RuntimeError(f"No interact position saved for {other.name()} at {self.name()}")
        approach_pos = pos_config['site global']
        # TODO this will still need a real motion planner
        # TODO we'll maybe also need to make sure the other devices are out of the way...
        _future.waitFor(self.moveToGlobal(approach_pos, speed=speed, name=f"move {self.name()} to approach {other.name()}"), timeout=120)
        _future.waitFor(other._moveToGlobal(approach_pos, speed=speed, name=f"move {other.name()} to approach {self.name()}"), timeout=120)
        interact_global = pos_config['interact global']
        _future.waitFor(other._moveToGlobal(interact_global, speed=speed, name=f"move {other.name()} to interact with {self.name()}"))

    @future_wrap
    def moveToApproach(self, other, speed='fast', _future=None):
        if other.name() not in self.positions:
            raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
        pos_config = self.positions[other.name()]
        if 'site global' not in pos_config:
            raise RuntimeError(f"No site global position saved for {other.name()} at {self.name()}")
        _future.waitFor(self.moveToGlobal(pos_config['site global'], speed=speed, name=f"move {self.name()} to approach {other.name()}"), timeout=120)
        _future.waitFor(other._moveToGlobal(pos_config['site global'], speed=speed, name=f"move {other.name()} to approach {self.name()}"), timeout=120)

    # @future_wrap
    # def moveToInteract(self, other, speed='fast', _future=None):
    #     if other.name() not in self.positions:
    #         raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
    #     pos_config = self.positions[other.name()]
    #     if 'interact global' not in pos_config:
    #         raise RuntimeError(f"No interact position saved for {other.name()} at {self.name()}")
    #     _future.waitFor(self.moveToApproach(other, speed))
    #     interact_global = pos_config['interact global']
    #     _future.waitFor(other._moveToGlobal(interact_global, speed=speed, name=f"move to interact with {self.name()}"))

    # @future_wrap
    # def moveToApproach(self, other, speed='fast', _future=None):
    #     if other.name() not in self.positions:
    #         raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
    #     pos_config = self.positions[other.name()]
    #     if 'site global' not in pos_config:
    #         raise RuntimeError(f"No site global position saved for {other.name()} at {self.name()}")
    #     scope = other.imagingDevice().scopeDev
    #     start_pos = scope.globalPosition()
    #     approach_global = pos_config['site global']
    #     if np.linalg.norm(np.array(start_pos) - np.array(approach_global)) > 50e-6:
    #         stage_path = [
    #             np.array([start_pos[0], start_pos[1], 30e-3]),
    #             np.array([-90e-3, 20e-3, 30e-3]),
    #         ]
    #         for wp in stage_path:
    #             _future.waitFor(
    #                 scope.setGlobalPosition(wp, 20e-3, name=f"move {self.name()} into interaction position")
    #             )
    #         self._approach_stage_path = [start_pos] + stage_path
    #         self_move = self.moveToGlobal(approach_global, speed=speed, name="move to interaction position")
    #         _future.waitFor(other.retractFromSurface('fast'))
    #         _future.waitFor(other._moveToGlobal([0, 0, 10e-3], 'fast', name=f"safe position before {self.name()}"))
    #         _future.waitFor(self_move)
    #     _future.waitFor(other._moveToGlobal(approach_global, speed=speed, name=f"move to {self.name()} approach"))

    # @future_wrap
    # def _unwindKludgePath(self, other, _future):
    #     if self._approach_stage_path is not None:
    #         _future.waitFor(self.moveToApproach(other, speed='fast'))
    #         for wp in reversed(self._approach_stage_path):
    #             _future.waitFor(
    #                 self._parentStage.moveToGlobal(wp, 20e-3, name=f"move {self.name()} out of interaction position")
    #             )
    #         self._approach_stage_path = None

    # def moveToApproach(self, other, speed='fast'):
    #     if other.name() not in self.positions:
    #         raise RuntimeError(f"No positions saved for {other.name()} at {self.name()}")
    #     pos_config = self.positions[other.name()]
    #     return other._moveToGlobal(pos_config['site global'], speed=speed)


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

        layout.addWidget(Qt.QLabel("Interact (global):"), row, 0)
        self.interactLabel = Qt.QLabel("—")
        layout.addWidget(self.interactLabel, row, 1)
        row += 1

        # layout.addWidget(Qt.QLabel("( for testing )"), row, 0)
        # self.doInteractBtn = FutureButton(
        #     self._doInteractForTest, "Do test interact!", stoppable=True
        # )
        # layout.addWidget(self.doInteractBtn, row, 1)

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
        # self.doInteractBtn.setEnabled(has_pipettes)
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
            return self.dev.moveToInteract(pip, speed='fast')
        return Future.immediate()

    def _updatePositionLabels(self):
        positions = {}
        pip = self._selectedPipette()
        if pip is not None and pip.name() in self.dev.positions:
            positions = self.dev.positions[pip.name()]
        self.globalCenterLabel.setText(_fmt_pos(positions.get('site global')))
        self.interactLabel.setText(_fmt_pos(positions.get('interact global')))


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
