from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
from pyqtgraph import opengl as gl


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
            self._win.addDevice(dev)


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
            self._removeDevice(dev)
        self._geometries = {}

    def addDevice(self, dev: OptomechDevice):
        dev.sigGeometryChanged.connect(self.handleGeometryChange)
        self._geometries.setdefault(dev, {})
        if (geom := dev.getGeometry()) is None:
            return
        self._geometries[dev]["geom"] = geom
        mesh = geom.glMesh()
        self.view.addItem(mesh)
        self._geometries[dev]["mesh"] = mesh

        dev.sigGlobalTransformChanged.connect(self.handleTransformUpdate)
        self.handleTransformUpdate(dev, dev)

    def _removeDevice(self, dev):
        if dev not in self._geometries:
            return
        dev.sigGeometryChanged.disconnect(self.handleGeometryChange)
        mesh = self._geometries[dev].get("mesh")
        if mesh is None:
            return
        dev.sigGlobalTransformChanged.disconnect(self.handleTransformUpdate)
        self.view.removeItem(mesh)

    def handleTransformUpdate(self, dev: OptomechDevice, _: OptomechDevice):
        if self._geometries.get(dev, {}).get("geom") is None:
            return
        geom = self._geometries[dev]["geom"]
        xform = dev.globalPhysicalTransform() * geom.transform.as_pyqtgraph()
        self._geometries[dev]["mesh"].setTransform(xform)

    def handleGeometryChange(self, dev: OptomechDevice):
        self._removeDevice(dev)
        self._geometries[dev] = {}
        self.addDevice(dev)
