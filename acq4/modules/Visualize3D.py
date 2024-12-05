from vispy import scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform, ChainTransform

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
from acq4.util.geometry import truncated_cone
from pyqtgraph import SRTTransform3D


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


class Visual(Qt.QObject):
    def __init__(self, transform=None):
        super().__init__()
        self.drawingTransform = MatrixTransform(SRTTransform3D(transform).matrix().T)
        self._deviceTransform = MatrixTransform()

    def handleTransformUpdate(self, dev: OptomechDevice, _: OptomechDevice):
        self.setDeviceTransform(dev.globalPhysicalTransform())

    def setDeviceTransform(self, xform):
        self._deviceTransform.matrix = SRTTransform3D(xform).matrix().T


class BoxVisual(Visual):
    def __init__(self, name: str, size: tuple, color=(1, 0.7, 0.1, 0.4), transform=None):
        super().__init__(transform)

        self.mesh = visuals.Box(
            width=size[0],
            height=size[1],
            depth=size[2],
            color=color,
            edge_color=(0, 0, 0, 1),
        )
        self.mesh.transform = ChainTransform(self._deviceTransform, self.drawingTransform)


class TruncatedConeVisual(Visual):
    def __init__(
        self,
        name: str,
        color=(1, 0.7, 0.1, 0.4),
        transform=None,
        **kwargs,
    ):
        super().__init__(transform)

        vertices, faces = truncated_cone(**kwargs)
        self.mesh = visuals.Mesh(vertices=vertices, faces=faces, color=color, shading="smooth")
        self.mesh.transform = ChainTransform(self._deviceTransform, self.drawingTransform)


class CylinderVisual(TruncatedConeVisual):
    def __init__(self, name: str, color=(1, 0.7, 0.1, 0.4), radius=None, transform=None, **kwargs):
        kwargs["top_radius"] = radius
        kwargs["bottom_radius"] = radius
        super().__init__(name, color, transform, **kwargs)


_VISUALS = {
    "box": BoxVisual,
    "cone": TruncatedConeVisual,
    "cylinder": CylinderVisual,
}
_CONTROL_ARGS = (
    {"type"}
    | set(truncated_cone.__code__.co_varnames)
    | set(BoxVisual.__init__.__code__.co_varnames)
    | set(CylinderVisual.__init__.__code__.co_varnames)
    | set(TruncatedConeVisual.__init__.__code__.co_varnames)
)


def create_geometry(defaults=None, **config):
    """Create 3D mesh from a configuration. Format example::

        geometry:
            color: (1, 0.7, 0.1, 1)    # default arguments at top level
            type: "cone"               # type must be "cone", "cylinder" or "box"
            top_radius: 20 * mm
            bottom_radius: 4 * mm
            component_1:               # arbitrary names for components
                height: 3 * mm
                top_radius: 40 * mm    # overrides top-level defaults
                transform:
                    pos: 0, 0, -10 * um
                children:              # nested components compound their transforms
                    halo:
                        type: "cylinder"
                        height: 1 * mm
                        radius: 50 * mm
                        color: (1, 1, 1, 0.1)
                        transform:
                            pos: 0, 0, 3 * mm
            fuse:                      # some devices may expect specific component names
                type: "box"
                size: (80 * mm, 80 * mm, 10 * mm)
                transform:
                    pos: 0, 0, -83 * mm

    If no components are specified beyond the toplevel config, a single geometry is created.

    Returns a flattened list of visuals.
    """
    if defaults is None:
        defaults = {}
    for key in list(config.keys()):
        if key in _CONTROL_ARGS:
            defaults[key] = config.pop(key)
    if len(config) < 1:
        defaults.setdefault("name", "geometry")
        return [_VISUALS[defaults.pop("type")](**defaults)]
    objects = []
    for name, obj in config.items():
        args = {**defaults, **obj}
        kid_args = args.pop("children", {})
        visual = _VISUALS[args.pop("type")](name=name, **args)
        objects.append(visual)
        if kid_args:
            for kid in create_geometry(defaults=defaults, **kid_args):
                kid.mesh.parent = visual.mesh
    return objects


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
                dev.sigGlobalTransformChanged.connect(shape.handleTransformUpdate)
                shape.handleTransformUpdate(dev, dev)
                self._geometries.setdefault(dev, []).append(shape)
                self.view.add(shape.mesh)

    def handleGeometryChange(self, dev: Device):
        for geom in self._geometries[dev]:
            geom.mesh.parent = None
        self._geometries[dev] = []
        self.add(dev)
