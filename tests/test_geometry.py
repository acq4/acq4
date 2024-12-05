import pytest
import numpy as np
from vispy import scene
from vispy.scene import visuals

from acq4.util.geometry import Geometry, Volume, GeometryMotionPlanner
import pyqtgraph as pg


@pytest.fixture
def geometry():
    return Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test")


def test_identity_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    orig = geometry.voxel_template(0.1)
    center = (0, 0, 0)
    convolved = orig.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == orig.volume)
    assert np.all(convolved.transform.map((0, 0, 0)) == orig.transform.map((0, 0, 0)))


def test_translated_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    orig = geometry.voxel_template(0.1)
    center = (-10, 0, 100)  # off the grid centers are allowed
    convolved = orig.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == orig.volume)
    assert np.all(convolved.transform.map((0, 0, 0)) == orig.transform.map((0, 0, 0)) + center)


def test_offcenter_convolve(geometry):
    kernel_array = np.zeros((3, 3, 3), dtype=bool)
    kernel_array[1, 1, 1] = True
    orig = geometry.voxel_template(0.1)
    center = (1, 1, 1)
    convolved = orig.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == orig.volume)
    assert np.all(convolved.transform.map((0, 0, 0)) == orig.transform.map((0, 0, 0)))



def test_small_voxelization(geometry):
    resolution = 0.25
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (5, 5, 5)
    expected = np.ones((5, 5, 5), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    assert np.all(template.transform.map((0, 0, 0)) == np.array([2, 2, 2]))
    corner = np.array([0.5, 0.5, 0.5])
    assert np.all(template.transform.map(corner) == np.array([4, 4, 4]))


def test_voxelized(geometry):
    resolution = 0.1
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    expected = np.ones((11, 11, 11), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    origin = template.transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([5, 5, 5]))


def test_translated_voxels():
    config = {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": [1.0, 0.0, 0.0]}}
    geometry = Geometry(config, "test")
    resolution = 0.1
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    origin = template.transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([15, 5, 5]))


def visualize():
    pg.mkQApp()

    canvas = scene.SceneCanvas(keys="interactive", show=True)
    canvas.native.show()

    view = canvas.central_widget.add_view()
    view.camera = "turntable"

    grid = visuals.GridLines()
    view.add(grid)

    axis = visuals.XYZAxis(parent=view.scene)
    axis.set_transform("st", scale=(10e-3, 10e-3, 10e-3))

    geometry = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, {})
    obj = geometry.visuals()[0]
    view.add(obj.mesh)

    resolution = 0.1
    template = geometry.voxel_template(resolution)
    template = template.convolve(template.volume, center=(0, 0, 0))
    vol = scene.visuals.Volume(template.volume.astype('float32'), parent=view.scene)
    vol.transform = scene.transforms.STTransform(scale=np.ones(3) * resolution, translate=(2.5, -0.5, -0.5))

    path = np.array([[0.041, -0.05, 0], [-0.04, 0.05, 0]])
    scene.visuals.Line(pos=path, parent=view.scene, color='red')

    pg.exec()


if __name__ == "__main__":
    visualize()
