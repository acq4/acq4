from vispy import scene
from vispy.scene import visuals

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt


class Visualize3D(Module):
    moduleDisplayName = "3D Visualization"
    moduleCategory = "Utilities"

    def __init__(self, manager, name: str, config: dict):
        super().__init__(manager, name, config)
        self.gridlines = None
        self.truncated_cone = None
        self.win = MainWindow()
        self.win.show()
        for dev in manager.listInterfaces("OptomechDevice"):
            dev = manager.getDevice(dev)
            self.win.add(dev)
            # todo handle devices added or removed


class MainWindow(Qt.QMainWindow):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("3D Visualization with VisPy")
        self.setGeometry(100, 100, 800, 600)

        self.canvas = scene.SceneCanvas(keys="interactive", show=True)
        self.setCentralWidget(self.canvas.native)

        self.view = self.canvas.central_widget.add_view()
        self.view.camera = "turntable"

        grid = visuals.GridLines()
        self.view.add(grid)

        self.axis = visuals.XYZAxis(parent=self.view.scene)
        self.axis.set_transform("st", scale=(10e-3, 10e-3, 10e-3))

        self._geometries = {}

    def add(self, dev: OptomechDevice):
        dev.sigGeometryChanged.connect(self.handleGeometryChange)
        for geom in dev.getGeometries():
            for shape in geom.visuals():
                # TODO this probably needs to be handled by the device
                self._geometries.setdefault(dev, []).append(shape)
                if shape.mesh.parent is None:
                    dev.sigGlobalTransformChanged.connect(shape.handleTransformUpdate)
                    shape.handleTransformUpdate(dev, dev)
                    self.view.add(shape.mesh)

    def handleGeometryChange(self, dev: Device):
        for geom in self._geometries.get(dev, []):
            geom.mesh.parent = None
        self._geometries[dev] = []
        self.add(dev)
