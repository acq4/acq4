import sys

import numpy as np
from vispy import scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform

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
        for dev in manager.listDevices():
            dev = manager.getDevice(dev)
            self.win.add(dev)
            dev.sigGeometryChanged.connect(self.win.handleGeometryChange)


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
        color=(1, 0.7, 0.1, 0.4),
        offset=(0, 0, 0),
        pitch=0,
        yaw=0,
        roll=0,
        **kwargs,
    ):
        vertices, faces = truncated_cone(**kwargs)

        transform = MatrixTransform()
        transform.translate(offset)
        transform.rotate(pitch, (1, 0, 0))
        transform.rotate(yaw, (0, 1, 0))
        transform.rotate(roll, (0, 0, 1))
        vertices = transform.map(vertices)[:, :3]

        self.mesh = visuals.Mesh(vertices=vertices, faces=faces, color=color, shading="smooth")

    def handleTransformUpdate(self, dev: OptomechDevice, _: OptomechDevice):
        xform = dev.globalPhysicalTransform()
        self.mesh.transform = MatrixTransform(np.array(xform.data()).reshape((4, 4)))


def _convert_to_args(**config) -> dict:
    if "transform" in config:
        xform = config.pop("transform")
        if "pos" in xform:
            config["offset"] = xform["pos"]
        if "pitch" in xform:
            config["pitch"] = xform["pitch"]
        if "yaw" in xform:
            config["yaw"] = xform["yaw"]
        if "roll" in xform:
            config["roll"] = xform["roll"]
    if "radius" in config:
        config["bottom_radius"] = config.pop("radius")
        config["top_radius"] = config["bottom_radius"]
    return config


def create_geometry(**config):
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
    config = _convert_to_args(**config)
    defaults = {}
    for key in list(config.keys()):
        if key in truncated_cone.__code__.co_varnames or key in TruncatedConeVisual.__init__.__code__.co_varnames:
            defaults[key] = config.pop(key)
    if len(config) < 1:
        print(defaults)
        return [TruncatedConeVisual(**defaults)]
    objects = []
    for obj in config.values():
        obj = _convert_to_args(**obj)
        args = {**defaults, **obj}
        objects.append(TruncatedConeVisual(**args))
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

        self._deviceGeometries = {}

    def add(self, dev: Device):
        for conic in dev.getGeometry():
            dev.sigGlobalTransformChanged.connect(conic.handleTransformUpdate)
            conic.handleTransformUpdate(dev, dev)
            self._deviceGeometries.setdefault(dev, []).append(conic)
            self.view.add(conic.mesh)

    def handleGeometryChange(self, dev: Device):
        for conic in self._deviceGeometries[dev]:
            conic.mesh.parent = None
        self._deviceGeometries[dev] = []
        self.add(dev)


if __name__ == "__main__":
    app = Qt.QApplication(sys.argv)

    window = MainWindow()

    objective = TruncatedConeVisual(
        offset=(0, 0, 100e-3),
        bottom_radius=10e-3,
        top_radius=35e-3,
        height=80e-3,
        close_top=True,
        close_bottom=True,
    )
    window.add(objective)

    pipette = TruncatedConeVisual(
        bottom_radius=1e-6,
        top_radius=1.1e-3,
        height=80e-3,
        offset=(0, 0, 13e-3),
        yaw=90 - 27,
        pitch=45,
    )
    window.add(pipette)

    chamber = TruncatedConeVisual(
        bottom_radius=20e-3,
        top_radius=20e-3,
        height=3e-3,
        close_bottom=True,
        offset=(0, 0, -10e-6),
    )
    window.add(chamber)

    window.show()
    sys.exit(app.exec_())
