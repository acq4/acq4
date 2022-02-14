import numpy as np
import pyqtgraph as pg
from .OptomechDevice import OptomechDevice
from .Device import Device
from acq4.modules.Camera import CameraModuleInterface
from acq4.util import Qt


class RecordingChamber(Device, OptomechDevice):
    """Describes the location and dimensions of a recording chamber.
    """
    def __init__(self, dm, config, name):
        Device.__init__(self, dm, config, name)
        OptomechDevice.__init__(self, dm, config, name)

        self.config = config
        self.radius = config['radius']

    def cameraModuleInterface(self, mod):
        """Return an object to interact with camera module.
        """
        return RecordingChamberCameraInterface(self, mod)

    def globalCenter(self):
        return np.array(self.mapToGlobal([0, 0, 0]))

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

    def boundingRect(self):
        return None
        # we don't want the camera module to auto-range to this item.
        # return self.boundingEllipse.boundingRect()

    def graphicsItems(self):
        return [self.boundingEllipse]
