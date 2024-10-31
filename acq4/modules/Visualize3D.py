import numpy as np
from vispy import scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform, ChainTransform

from acq4.devices.Device import Device
from acq4.devices.OptomechDevice import OptomechDevice
from acq4.modules.Module import Module
from acq4.util import Qt
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
        for dev in manager.listDevices():
            dev = manager.getDevice(dev)
            self.win.add(dev)


def truncated_cone(
    bottom_radius: float,
    top_radius: float,
    height: float,
    close_top: bool = False,
    close_bottom: bool = False,
    segments: int = 32,
) -> (np.ndarray, np.ndarray):
    theta = np.linspace(0, 2 * np.pi, segments, endpoint=False)
    bottom_circle = np.column_stack((bottom_radius * np.cos(theta), bottom_radius * np.sin(theta), np.zeros(segments)))
    top_circle = np.column_stack((top_radius * np.cos(theta), top_radius * np.sin(theta), np.full(segments, height)))

    vertices = np.vstack((bottom_circle, top_circle))

    faces = []
    for i in range(segments):
        next_i = (i + 1) % segments
        faces.extend(
            (
                [i, next_i, segments + next_i],
                [i, segments + next_i, segments + i],
            )
        )

    if close_bottom:
        bottom_center = len(vertices)
        vertices = np.vstack((vertices, [[0, 0, 0], [0, 0, height]]))
        for i in range(segments):
            next_i = (i + 1) % segments
            faces.append([i, next_i, bottom_center])
    if close_top:
        top_center = len(vertices)
        vertices = np.vstack((vertices, [[0, 0, height]]))
        for i in range(segments):
            next_i = (i + 1) % segments
            faces.append([segments + i, segments + next_i, top_center])

    return vertices, np.array(faces)


class TruncatedConeVisual:
    def __init__(
        self,
        name: str,
        color=(1, 0.7, 0.1, 0.4),
        transform=None,
        **kwargs,
    ):
        vertices, faces = truncated_cone(**kwargs)
        self._drawingTransform = MatrixTransform(SRTTransform3D(transform).matrix().T)
        self._deviceTransform = MatrixTransform()

        self.mesh = visuals.Mesh(vertices=vertices, faces=faces, color=color, shading="smooth")
        self.mesh.transform = ChainTransform(self._deviceTransform, self._drawingTransform)

    def handleTransformUpdate(self, dev: OptomechDevice, _: OptomechDevice):
        xform = dev.globalPhysicalTransform()
        self._deviceTransform.matrix = SRTTransform3D(xform).matrix().T


def _convert_to_args(**config) -> dict:
    # TODO delete this function and use cylinders
    if "radius" in config:
        config["bottom_radius"] = config.pop("radius")
        config["top_radius"] = config["bottom_radius"]
    return config


def create_geometry(defaults=None, **config):
    """Create 3D mesh from a configuration. Format example::

        geometry:
            color: (1, 0.7, 0.1, 0.4)  # default arguments at top level
            transform:
                pitch: 45
            radius: 20 * mm            # radius expands to top and bottom radii
            component_1:               # arbitrary names for components
                height: 3 * mm
                top_radius: 40 * mm    # overrides top-level defaults
                transform:
                    pos: 0, 0, -10 * um
            fuse:                      # some devices may expect specific component names
                height: 80 * mm
                close_bottom: True
                transform:
                    pos: 0, 0, -83 * mm

    If no components are specified beyond the default arguments, a single geometry is created.
    TODO Alternately, geometry can be a filename.
    """
    if defaults is None:
        defaults = {}
    defaults = _convert_to_args(**defaults)
    config = _convert_to_args(**config)
    for key in list(config.keys()):
        if key in truncated_cone.__code__.co_varnames or key in TruncatedConeVisual.__init__.__code__.co_varnames:
            defaults[key] = config.pop(key)
    if len(config) < 1:
        defaults.setdefault("name", "geometry")
        return [TruncatedConeVisual(**defaults)]
    objects = []
    for name, obj in config.items():
        obj = _convert_to_args(**obj)
        args = {**defaults, **obj}
        kid_args = args.pop("children", {})
        cone = TruncatedConeVisual(name=name, **args)
        objects.append(cone)
        if kid_args:
            for kid in create_geometry(defaults=defaults, **kid_args):
                kid.mesh.parent = cone.mesh
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

    def add(self, dev: Device):
        if hasattr(dev, "geometry"):
            dev.sigGeometryChanged.connect(self.handleGeometryChange)
            for geom in dev.geometry.getGeometries():
                dev.sigGlobalTransformChanged.connect(geom.handleTransformUpdate)
                geom.handleTransformUpdate(dev, dev)
                self._geometries.setdefault(dev, []).append(geom)
                self.view.add(geom.mesh)

    def handleGeometryChange(self, dev: Device):
        for geom in self._geometries[dev]:
            geom.mesh.parent = None
        self._geometries[dev] = []
        self.add(dev)
