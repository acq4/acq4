import sys
from typing import Callable

import numpy as np
from vispy import scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform

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
            if model := dev.get3DModel():
                model.handleTransformUpdate(dev, dev)
                self.win.add(model)


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
        transform_getter: Callable[[], SRTTransform3D],
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
        self._transform_getter = transform_getter

    def handleTransformUpdate(self, dev: OptomechDevice, _: OptomechDevice):
        xform = self._transform_getter()
        new_xform = MatrixTransform(np.array(xform.data()).reshape((4, 4)))
        self.mesh.transform = new_xform


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
        self._displayed = []

    def add(self, conic: TruncatedConeVisual):
        self._displayed.append(conic)
        self.view.add(conic.mesh)


if __name__ == "__main__":
    app = Qt.QApplication(sys.argv)

    window = MainWindow()

    objective = TruncatedConeVisual(
        lambda: SRTTransform3D(),
        bottom_radius=10e-3,
        top_radius=35e-3,
        height=80e-3,
        close_top=True,
        close_bottom=True,
        offset=(0, 0, 40e-3),
    )
    window.add(objective)

    pipette = TruncatedConeVisual(
        lambda: SRTTransform3D(),
        bottom_radius=1e-6,
        top_radius=1.1e-3,
        height=50e-3,
        offset=(1e-3, -1e-3, 13e-3),
        yaw=90 - 27,
        pitch=45,
    )
    window.add(pipette)

    chamber = TruncatedConeVisual(
        lambda: SRTTransform3D(),
        bottom_radius=50e-3,
        top_radius=50e-3,
        height=13e-3,
        close_bottom=True,
        offset=(0, 0, -10e-6),
    )
    window.add(chamber)

    window.show()
    sys.exit(app.exec_())
