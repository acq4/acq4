import numpy as np

import pyqtgraph as pg
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt
from .Device import Device
from .OptomechDevice import OptomechDevice


class RecordingChamber(Device, OptomechDevice):
    """Describes the location and dimensions of a circular recording chamber.

    Configuration options:

    * radius: The radius of the recording chamber (m)
    * height: The height of the recording chamber (m)
    * transform: Transformation setting the position/orientation of the chamber
        pos: x,y,z position of recording chamber
    """

    defaultGeometryArgs = {"color": (0.1, 0.1, 0.1, 0.7), "close_bottom": True}

    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        self.config = config
        self.radius = config["radius"]
        OptomechDevice.__init__(self, dm, config, name)

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module."""
        return RecordingChamberCameraInterface(self, mod)

    def globalCenter(self):
        return np.array(self.globalPosition())

    def globalPosition(self):
        return self.mapToGlobal([0, 0, 0])

    def containsPoint(self, pt):
        """Return True if the x,y coordinates in *pt* lie within
        the boundary of this RecordingChamber."""
        center = self.globalCenter()[:2]
        pt = np.array(pt)[:2]
        return np.linalg.norm(pt - center) <= self.radius


class RecordingChamberCameraInterface(CameraModuleInterface):
    def __init__(self, dev, mod):
        CameraModuleInterface.__init__(self, dev, mod)

        x, y, z = self.dev().globalCenter()
        radius = self.dev().radius
        self.boundingEllipse = Qt.QGraphicsEllipseItem(-1, -1, 2, 2)
        self.boundingEllipse.setPen(pg.mkPen("y"))
        self.boundingEllipse.setScale(radius)
        mod.window().addItem(self.boundingEllipse, ignoreBounds=True)
        self.boundingEllipse.setPos(x, y)
        self._name = pg.TextItem(text=dev.name(), color=pg.mkColor((255, 255, 0, 128)))
        mod.window().addItem(self._name, ignoreBounds=True)
        self._name.setPos(x + radius, y)

    def boundingRect(self):
        return None
        # we don't want the camera module to auto-range to this item.
        # return self.boundingEllipse.boundingRect()

    def graphicsItems(self):
        return [self.boundingEllipse, self._name]
