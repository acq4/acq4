import numpy as np

from pyqtgraph import opengl as gl

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    _win = None

    @classmethod
    def openWindow(cls):
        if cls._win is None:
            cls._win = MainWindow()
        cls._win.clear()
        cls._win.show()

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.gridlines = None
        self.truncated_cone = None
        self.openWindow()
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self._win.add(dev)


class MainWindow(Qt.QMainWindow):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("3D Visualization with VisPy")
        self.setGeometry(100, 100, 800, 600)

        self.view = gl.GLViewWidget()
        self.setCentralWidget(self.view)
        self.view.setCameraPosition(distance=2)
        grid = gl.GLGridItem()
        grid.scale(1, 1, 1)
        self.view.addItem(grid)

        self._geometries = {}

    def clear(self):
        for dev in self._geometries:
            self._geometries[dev]["mesh"].parent = None
        self._geometries = {}

    def add(self, dev: OptomechDevice):
        dev.sigGeometryChanged.connect(self.handleGeometryChange)
        if (geom := dev.getGeometry()) is not None:
            self._geometries.setdefault(dev, {})["geom"] = geom
            mesh = geom.glMesh()
            self.view.addItem(mesh)
            self._geometries[dev]["mesh"] = mesh

            dev.sigGlobalTransformChanged.connect(self.handleTransformUpdate)
            self.handleTransformUpdate(dev, dev)

    def handleTransformUpdate(self, _, dev: Device):
        if dev in self._geometries:
            geom = self._geometries[dev]["geom"]
            xform = dev.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
            self._geometries[dev]["mesh"].setTransform(xform)

    def handleGeometryChange(self, dev: Device):
        if dev in self._geometries:
            self._geometries[dev]["mesh"].parent = None
        del self._geometries[dev]
        self.add(dev)
