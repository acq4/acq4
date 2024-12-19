import time

import pytest
import numpy as np
from coorx import NullTransform
from vispy import scene
from vispy.scene import visuals

from acq4.util.geometry import Geometry, Volume, GeometryMotionPlanner
import pyqtgraph as pg


@pytest.fixture
def geometry():
    return Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test")


def test_mesh(geometry):
    mesh = geometry.mesh
    assert mesh is not None
    assert np.allclose(mesh.bounds, [[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]])


def test_identity_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    orig = geometry.voxel_template(0.1)
    center = (0, 0, 0)
    convolved = orig.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == orig.volume)
    assert np.all(convolved.transform.map((0, 0, 0)) == orig.transform.map((0, 0, 0)))


def test_cross_geometry_transform():
    geom_a = Geometry(
        {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": (-10, 2, 100), "angle": 45, "axis": (0, 0, 1)}},
        "a",
    )
    geom_b = Geometry({"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": (50, 50, 50)}}, "b")
    from_a_to_b = geom_a.transform * geom_b.transform.inverse
    geom_c = geom_a.transformed_to(geom_b.transform, from_a_to_b, name="transformed")
    # geom_c's transform should be the same as geam_b's
    assert np.all(geom_c.transform.map((0, 0, 0)) == np.array([50, 50, 50]))
    # geom_c's mesh should be rotated and therefore the voxels should be wholly unique
    assert geom_c.voxel_template(0.1).volume.shape != geom_a.voxel_template(0.1).volume.shape
    assert geom_c.voxel_template(0.1).volume.shape != geom_b.voxel_template(0.1).volume.shape
    # TODO it would be nice to positively assert something about the voxelization


def test_translated_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    resolution = 0.1
    orig = geometry.voxel_template(resolution)
    center = np.array([-10, 0, 100])  # off the grid centers are allowed
    convolved = orig.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == orig.volume)
    assert np.allclose(
        convolved.inverse_transform.map((0, 0, 0)) + center,
        orig.inverse_transform.map((0, 0, 0)),
    )


def test_offcenter_convolve(geometry):
    kernel_array = np.zeros((3, 3, 3), dtype=bool)
    kernel_array[1, 1, 1] = True
    orig = geometry.voxel_template(0.1)
    center = (1, 1, 1)
    convolved = orig.convolve(kernel_array, center=center)
    # we usually won't have kernels with empty edges, so these 1:-1 and +1 steps are only needed for this test
    assert np.allclose(convolved.volume[1:-1, 1:-1, 1:-1], orig.volume)
    assert np.allclose(convolved.inverse_transform.map((0, 0, 0)) + 1, orig.inverse_transform.map((0, 0, 0)))


def test_convolve_growth(geometry):
    dot = Geometry({"type": "box", "size": [0.1, 0.1, 0.1]}, "dot").voxel_template(0.1)
    kernel_array = geometry.voxel_template(0.1).volume
    center = (0, 0, 0)
    convolved = dot.convolve(kernel_array, center=center)
    assert np.all(convolved.volume == kernel_array)


def test_coarse_voxelization(geometry):
    resolution = 0.25  # units per vx
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (5, 5, 5)  # not 4; the edge is in the next voxel over
    expected = np.ones((5, 5, 5), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    assert np.all(template.inverse_transform.map((0, 0, 0)) == np.array([2, 2, 2]))
    corner = np.array([0.5, 0.5, 0.5])
    assert np.all(template.inverse_transform.map(corner) == np.array([4, 4, 4]))
    assert np.all(template.transform.map(np.array([0, 3, 0]) == np.array([-0.5, 0.25, -0.5])))


def test_voxelized(geometry):
    resolution = 0.1
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    expected = np.ones((11, 11, 11), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    origin = template.inverse_transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([5, 5, 5]))


def test_translated_voxels_have_no_knowledge_of_such():
    resolution = 0.1
    offset = np.array([1.0, -0.1, 10.0])
    config = {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": offset}}
    geometry = Geometry(config, "test")
    template = geometry.voxel_template(resolution)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    # inverse goes from geometry to voxel
    origin = template.inverse_transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([5, 5, 5]))


def test_find_path(geometry):
    resolution = 0.1
    planner = GeometryMotionPlanner({geometry: NullTransform(3)}, resolution)
    point = Geometry({"type": "box", "size": [resolution, resolution, resolution]}, "point")
    dest = np.array([0.5, 0.5, 3])
    start = np.array([0.5, 0.5, -2])
    path = planner.find_path(point, NullTransform(3), start, dest)

    assert path is not None
    assert len(path) >= 2
    assert not np.all(path[0] == start)
    assert not np.all(path[0] == dest)
    assert np.all(path[-1] == dest)
    # walk along the path at resolution steps and assert that we haven't touched the box
    for waypoint in path:
        assert not geometry.contains(
            waypoint, padding=resolution
        ), f"waypoint {waypoint} is within {resolution} of {geometry.mesh.bounds}"
        # TODO this inifinite loops
        # step = start
        # step_size = (resolution * (waypoint - start) / np.linalg.norm(waypoint - start))
        # assert np.isclose(np.linalg.norm(step_size), resolution)
        # assert not np.all(step + step_size == start)
        # while np.linalg.norm(start - step) < np.linalg.norm(start - waypoint):
        #     step += step_size
        #     assert not geometry.contains(step, padding=resolution), f"step {step} is within {resolution} of {geometry.mesh.bounds}"
        # start = waypoint


def test_no_path(geometry):
    resolution = 0.1
    planner = GeometryMotionPlanner({geometry: NullTransform(3)}, resolution)
    point = Geometry({"type": "box", "size": [resolution, resolution, resolution]}, "point")
    dest = np.array([0.5, 0.5, 3])
    start = np.array([resolution, resolution, resolution]) * 2  # inside the box
    path = planner.find_path(point, NullTransform(3), start, dest)
    assert path is None


draw_n = 0


def visualize():
    app = pg.mkQApp()

    canvas = scene.SceneCanvas(keys="interactive", show=True)
    canvas.native.show()

    view = canvas.central_widget.add_view()
    view.camera = "turntable"

    grid = visuals.GridLines()
    view.add(grid)

    axis = visuals.XYZAxis(parent=view.scene)
    axis.set_transform("st", scale=(10e-3, 10e-3, 10e-3))

    geometry = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, {})
    # obj = geometry.visuals()[0]
    # view.add(obj.mesh)

    resolution = 0.1

    traveler = Geometry(
        {
            "type": "cylinder",
            "radius": resolution,
            "height": 10 * resolution,
            "transform": {"angle": 45, "axis": (0, 1, 0)},
        },
        "traveler",
    )

    from_self_to_other = traveler.transform * geometry.transform.inverse
    xformed = traveler.transformed_to(geometry.transform, from_self_to_other, f"{traveler.name}_in_{geometry.name}")
    kernel = xformed.voxel_template(resolution).volume[::-1, ::-1, ::-1]
    center = xformed.transform.map(np.array([0, 0, 0])) * -1
    obstacle = geometry.voxel_template(resolution).convolve(kernel, center)
    vol = scene.visuals.Volume(obstacle.volume.astype("float32"), parent=view.scene)
    vol.transform = scene.transforms.STTransform(scale=np.ones(3) * resolution, translate=(-0.5, -0.5, -0.5))

    # template = geometry.voxel_template(resolution)
    # template = template.convolve(template.volume, center=(0, 0, 0))

    # path = np.array([[0.041, -0.05, 0], [-0.04, 0.05, 0]])
    # scene.visuals.Line(pos=path, parent=view.scene, color='red')

    start = np.array([0.1, 0.1, -2])
    dest = np.array([0.2, 0.2, 3])
    start_target = scene.visuals.Sphere(radius=0.1, color="blue", parent=view.scene)
    start_target.transform = scene.transforms.STTransform(translate=start)
    dest_target = scene.visuals.Sphere(radius=0.1, color="green", parent=view.scene)
    dest_target.transform = scene.transforms.STTransform(translate=dest)
    path_line = scene.visuals.Line(pos=np.array([start, dest]), color="red", parent=view.scene)

    def update_path(p, skip=1):
        global draw_n
        draw_n += 1
        if draw_n % skip != 0:
            return
        # sleep to allow the user to watch
        then = time.time()
        while time.time() - then < 0.1:
            app.processEvents()
        path_line.set_data(p)
        app.processEvents()

    planner = GeometryMotionPlanner({geometry: NullTransform(3)}, resolution)
    path = planner.find_path(traveler, NullTransform(3), start, dest, callback=update_path)
    print(path)
    update_path([start] + path, skip=1)

    pg.exec()


if __name__ == "__main__":
    visualize()
