import pytest
import numpy as np
from vispy import scene
from vispy.scene import visuals

from acq4.devices.OptomechDevice import Geometry
import pyqtgraph as pg


@pytest.fixture
def geometry():
    config = {"type": "box", "size": [1.0, 1.0, 1.0]}
    defaults = {}
    return Geometry(config, defaults)


def test_small_voxelization(geometry):
    resolution = 0.25
    template = geometry.voxel_template(resolution)
    assert isinstance(template, np.ndarray)
    assert template.shape == (5, 5, 5)
    expected = np.ones((5, 5, 5), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template == expected)


def test_voxelized(geometry):
    resolution = 0.1
    template = geometry.voxel_template(resolution)
    assert isinstance(template, np.ndarray)
    assert template.shape == (11, 11, 11)
    expected = np.ones((11, 11, 11), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    # surface_area = np.sum(template) * resolution ** 2
    # assert np.isclose(surface_area, 6.0, atol=resolution)
    assert np.all(template == expected)


def test_translated_voxels():
    config = {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": [1.0, 0.0, 0.0]}}
    geometry = Geometry(config, {})
    resolution = 0.1
    template = geometry.voxel_template(resolution)
    assert isinstance(template, np.ndarray)
    assert template.shape == (21, 11, 11)
    surface_area = np.sum(template) * resolution**2
    assert np.isclose(surface_area, 6.0, atol=resolution)
    assert not np.any(np.argmax(template, axis=0) < 10)


def test_path_intersects(geometry):
    path = np.array([[0, -1, 0], [1, 15, 0]])
    intersects = geometry.global_path_intersects(path, resolution=0.1)
    assert intersects


def test_path_barely_intersects(geometry):
    path = np.array([[0.0401, -0.05, 0], [-0.04, 0.05, 0]])
    intersects = geometry.global_path_intersects(path, resolution=0.1)
    assert intersects



def test_path_does_not_intersect(geometry):
    path = np.array([[0, -1, 0], [5, -5, 0]])
    intersects = geometry.global_path_intersects(path, resolution=0.1)
    assert not intersects


def test_convolve_across(geometry):
    space = np.zeros((10, 10, 10), dtype=bool)
    geometry.convolve_across(space)
    # Add assertions to verify the expected behavior
    assert False, "todo"


def test_get_geometries(geometry):
    geometries = geometry.get_geometries()
    assert isinstance(geometries, list)
    # Add more assertions to verify the expected behavior
    assert False, "todo"


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
    obj = geometry.get_geometries()[0]
    view.add(obj.mesh)

    template = geometry.voxel_template(0.1)
    vol = scene.visuals.Volume(template.astype('float32'), parent=view.scene)
    vol.transform = scene.transforms.STTransform(scale=(0.1, 0.1, 0.1), translate=(0.5, 0, 0))

    path = np.array([[0.041, -0.05, 0], [-0.04, 0.05, 0]])
    scene.visuals.Line(pos=path, parent=view.scene, color='red')

    pg.exec()


if __name__ == "__main__":
    visualize()
