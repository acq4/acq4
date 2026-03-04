import numpy as np

import pyqtgraph as pg
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt
from .Device import Device
from .OptomechDevice import OptomechDevice
from .Stage import Stage
from ..util.target import color_for_diff


class InteractionSite(Device, OptomechDevice):
    """Describes the location and dimensions of a cylindrical zone of interaction, such as a
    recording chamber, a nucleus deposition tube or a cleaning well.

    Configuration options:

    * radius: The radius of the site (m)
    * height: The height of the site (m). Default 0.
    * transform: (dict) Transformation setting the position/orientation of the site.  E.g. pos
    * geometry: Optional settings for visualizing the site in the 3D visualizer. See OptomechDevice
        for details.
    * parentDevice: Optional name of parent device for coordinate transforms.  E.g. a stage that
        the site is mounted on.
    """

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.radius = config["radius"]
        self.height = config.get("height", 0)
        OptomechDevice.__init__(self, dm, config, name)

        parent = self
        while True:
            parent = parent.parentDevice()
            if parent is None or isinstance(parent, Stage):
                break
        self._parentStage: Stage = parent

    def getGeometry(self, name=None):
        if isinstance(self.config.get("geometry"), dict):
            defaults = {"color": (0.3, 0.3, 0.3, 0.7)}
            defaults.update(self.config["geometry"])
            self.config["geometry"] = defaults
        return super().getGeometry(name)

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module."""
        return InteractionSiteCameraInterface(self, mod)

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
