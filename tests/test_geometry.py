import numpy as np
import pytest
from coorx import NullTransform, TTransform, Point, SRT3DTransform
from vispy import scene

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from acq4.util.geometry import Geometry, Volume, GeometryMotionPlanner


@pytest.fixture
def geometry():
    return Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test_mesh", "test")


def test_mesh(geometry):
    mesh = geometry.mesh
    assert mesh is not None
    assert np.allclose(mesh.bounds, [[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]])


def test_identity_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    orig = geometry.voxel_template(0.1)
    center = np.array((0, 0, 0))
    convolved = orig.convolve(kernel_array, center=center, name=geometry.name)
    assert np.all(convolved.volume == orig.volume)
    assert np.all(convolved.transform.map((0, 0, 0)) == orig.transform.map((0, 0, 0)))


def test_cross_geometry_transform():
    geom_a = Geometry(
        {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": (-10, 2, 100), "angle": 45, "axis": (0, 0, 1)}},
        "a_mesh",
        "a",
    )
    geom_b = Geometry({"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": (50, 50, 50)}}, "b_mesh", "b")
    from_a_to_global = NullTransform(3, from_cs=geom_a.parent_name, to_cs="global")
    from_b_to_global = NullTransform(3, from_cs=geom_b.parent_name, to_cs="global")
    from_a_to_b = geom_b.transform.inverse * from_b_to_global.inverse * from_a_to_global * geom_a.transform
    geom_c = geom_a.transformed_to(geom_b.transform, from_a_to_b)
    # geom_c's transform should be the same as geom_b's
    assert np.all(geom_c.transform.map((0, 0, 0)) == np.array([50, 50, 50]))
    # geom_c's mesh should be rotated and therefore the voxels should be wholly unique
    assert geom_c.voxel_template(0.1).volume.shape != geom_a.voxel_template(0.1).volume.shape
    assert geom_c.voxel_template(0.1).volume.shape != geom_b.voxel_template(0.1).volume.shape
    # TODO it would be nice to positively assert something about the voxelization
    # TODO would they have about the same volume?


def test_translated_convolve(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    voxel_size = 0.1
    orig = geometry.voxel_template(voxel_size)
    center = np.array([-10, 0, 100])  # off the grid centers are allowed
    convolved = orig.convolve(kernel_array, center=center, name="fake")
    assert np.all(convolved.volume == orig.volume)
    assert np.allclose(
        convolved.inverse_transform.map((0, 0, 0)) - center,
        orig.inverse_transform.map((0, 0, 0)),
    )


def test_offcenter_convolve(geometry):
    kernel_array = np.zeros((3, 3, 3), dtype=bool)
    kernel_array[1, 1, 1] = True
    orig = geometry.voxel_template(0.1)
    center = np.array((1, 1, 1))
    convolved = orig.convolve(kernel_array, center=center, name="fake")
    # we usually won't have kernels with empty edges, so this 1:-1 step is only needed for this test
    assert np.allclose(convolved.volume[1:-1, 1:-1, 1:-1], orig.volume)
    assert np.allclose(convolved.inverse_transform.map((0, 0, 0)) - center, orig.inverse_transform.map((0, 0, 0)))


def test_convolve_growth(geometry):
    dot = Geometry({"type": "box", "size": [0.1, 0.1, 0.1]}, "dot_mesh", "dot").voxel_template(0.1)
    kernel_array = geometry.voxel_template(0.1).volume
    center = np.array((0, 0, 0))
    convolved = dot.convolve(kernel_array, center=center, name=geometry.name)
    assert np.all(convolved.volume == kernel_array)


def test_single_voxel_voxelization(geometry, visualize=False):
    voxel_size = 1.0
    template = geometry.voxel_template(voxel_size)
    if visualize:
        w = gl.GLViewWidget()
        w.show()
        w.setCameraPosition(distance=20)
        g = gl.GLGridItem()
        g.scale(1, 1, 1)
        w.addItem(g)

        mesh = gl.MeshData(vertexes=geometry.mesh.vertices, faces=geometry.mesh.faces)
        m = gl.GLMeshItem(meshdata=mesh, smooth=False, color=(1, 0, 0, 0.5))
        m.setTransform(geometry.transform.as_pyqtgraph())
        w.addItem(m)

        vol = np.zeros(template.volume.T.shape + (4,), dtype=np.ubyte)
        vol[..., :3] = (30, 30, 100)
        vol[..., 3] = template.volume.T * 20
        v = gl.GLVolumeItem(vol, sliceDensity=10, smooth=False)
        v.setTransform((geometry.transform * template.transform).as_pyqtgraph())
        w.addItem(v)

        pg.exec()
    assert isinstance(template, Volume)
    assert template.volume.shape == (1, 1, 1)
    assert np.all(template.volume)
    assert np.all(template.inverse_transform.map((0, 0, 0)) == np.array([0.5, 0.5, 0.5]))


def test_coarse_voxelization(geometry):
    voxel_size = 0.25  # units per vx
    template = geometry.voxel_template(voxel_size)
    assert isinstance(template, Volume)
    assert template.volume.shape == (5, 5, 5)  # not 4; the edge is in the next voxel over
    expected = np.ones((5, 5, 5), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    assert np.all(template.inverse_transform.map((0, 0, 0)) == np.array([5 / 2, 5 / 2, 5 / 2]))
    corner = np.array([0.5, 0.5, 0.5])
    assert np.all(template.inverse_transform.map(corner) == np.array([4.5, 4.5, 4.5]))
    assert np.all(template.transform.map(np.array([0, 3, 0]) == np.array([-0.5, 0.25, -0.5])))


def test_voxelized(geometry):
    voxel_size = 0.1
    template = geometry.voxel_template(voxel_size)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    expected = np.ones((11, 11, 11), dtype=bool)
    expected[1:-1, 1:-1, 1:-1] = False
    assert np.all(template.volume == expected)
    origin = template.inverse_transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([11 / 2, 11 / 2, 11 / 2]))


def test_translated_voxels_have_no_knowledge_of_such():
    voxel_size = 0.1
    offset = np.array([1.0, -0.1, 10.0])
    config = {"type": "box", "size": [1.0, 1.0, 1.0], "transform": {"pos": offset}}
    geometry = Geometry(config, "test_mesh", "test")
    template = geometry.voxel_template(voxel_size)
    assert isinstance(template, Volume)
    assert template.volume.shape == (11, 11, 11)
    # inverse goes from geometry to voxel
    origin = template.inverse_transform.map(np.array([0, 0, 0]))
    assert np.all(origin[:3] == np.array([11 / 2, 11 / 2, 11 / 2]))


def test_find_path(geometry, viz=False):
    voxel_size = 0.1
    planner = GeometryMotionPlanner(
        {geometry: NullTransform(3, from_cs=geometry.parent_name, to_cs="global")}, voxel_size
    )
    point = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "point_mesh", "point")
    dest = Point(np.array([0, 0, 3]), "global")
    start = Point(np.array([0, 0, -2]), "global")
    path = planner.find_path(
        point, NullTransform(3, from_cs=point.parent_name, to_cs="global"), start, dest, visualize=viz
    )
    if viz:
        pg.exec()

    assert path is not None
    assert len(path) >= 2
    assert not np.all(path[0] == start)
    assert not np.all(path[0] == dest)
    assert np.all(path[-1] == dest)
    # walk along the path at voxel_size steps and assert that we haven't touched the box
    for waypoint in path:
        assert not geometry.contains(
            waypoint, padding=voxel_size
        ), f"waypoint {waypoint} is within {voxel_size} of {geometry.mesh.bounds}"
        # TODO this inifinite loops
        # step = start
        # step_size = (voxel_size * (waypoint - start) / np.linalg.norm(waypoint - start))
        # assert np.isclose(np.linalg.norm(step_size), voxel_size)
        # assert not np.all(step + step_size == start)
        # while np.linalg.norm(start - step) < np.linalg.norm(start - waypoint):
        #     step += step_size
        #     assert not geometry.contains(step, padding=voxel_size), f"step {step} is within {voxel_size} of {geometry.mesh.bounds}"
        # start = waypoint


def test_z_and_x_are_not_swapped(viz=False):
    geometry = Geometry({"type": "box", "size": [10.0, 1.0, 1.0]}, "test_mesh", "test")
    voxel_size = 0.1
    from_geom_to_global = NullTransform(3, from_cs=geometry.parent_name, to_cs="global")
    start = Point(np.array([0, 0, 3]), "global")
    dest = Point(np.array([0, -4, 0]), "global")
    planner = GeometryMotionPlanner({geometry: from_geom_to_global}, voxel_size)
    traveler = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "traveler_mesh", "traveler")

    path = planner.find_path(
        traveler, NullTransform(3, from_cs=traveler.parent_name, to_cs="global"), start, dest, visualize=viz
    )
    if viz:
        pg.exec()
    assert path is not None

    path = planner.find_path(
        traveler, NullTransform(3, from_cs=traveler.parent_name, to_cs="global"), start[::-1], dest, visualize=viz
    )
    if viz:
        pg.exec()
    assert path is None


def test_path_with_funner_traveler(geometry, viz=False):
    voxel_size = 0.1
    traveler = Geometry(
        {
            "type": "cylinder",
            "radius": voxel_size,
            "height": 10 * voxel_size,
            "transform": {"angle": 45, "axis": (0, 1, 0)},
        },
        "traveler_mesh",
        "traveler",
    )
    start = Point(np.array([-0.4, -0.4, -1.2]), "global")
    dest = Point(np.array([0.2, 0.2, 3]), "global")
    planner = GeometryMotionPlanner({geometry: NullTransform(3, from_cs="test", to_cs="global")}, voxel_size)
    path = planner.find_path(
        traveler, TTransform(offset=start, from_cs="traveler", to_cs="global"), start, dest, visualize=viz
    )
    if viz:
        pg.exec()
    assert path is not None
    assert len(path) >= 2
    assert not np.all(path[0] == start)
    assert not np.all(path[0] == dest)


def test_no_path(viz=False):
    geometry = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test_mesh", "test")
    voxel_size = 0.1
    planner = GeometryMotionPlanner(
        {geometry: NullTransform(3, from_cs=geometry.parent_name, to_cs="global")}, voxel_size
    )
    traveler = Geometry(
        {"type": "box", "size": [voxel_size, voxel_size, 6 * voxel_size], "transform": {"pos": (0, 0, -0.3)}},
        "traveler_mesh",
        "traveler",
    )
    from_traveler_to_global = TTransform(offset=(0, 2, 3), from_cs="traveler", to_cs="global")
    start = from_traveler_to_global.map(Point(np.array([0, 0, 0]), "traveler"))
    dest = Point(np.array([voxel_size, voxel_size, voxel_size]) * 2, "global")  # inside the box
    path = planner.find_path(traveler, from_traveler_to_global, start, dest, visualize=viz)
    if viz:
        pg.exec()
    assert path is None


def test_no_path_because_of_shadow(geometry):
    voxel_size = 0.1
    traveler = Geometry(
        {
            "type": "cylinder",
            "radius": voxel_size,
            "height": 10 * voxel_size,
            "transform": {"angle": 45, "axis": (0, 1, 0)},
        },
        "traveler_mesh",
        "traveler",
    )
    point = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "point_mesh", "point")
    start = Point(np.array([0.7, 0, -0.7]), "global")
    dest = Point(np.array([0.2, 0.2, 5]), "global")
    planner = GeometryMotionPlanner(
        {geometry: NullTransform(3, from_cs=geometry.parent_name, to_cs="global")}, voxel_size
    )
    point_to_global = NullTransform(3, from_cs=point.parent_name, to_cs="global")
    path = planner.find_path(point, point_to_global, start, dest)
    assert path is not None
    traveler_to_global = NullTransform(3, from_cs=traveler.parent_name, to_cs="global")
    path = planner.find_path(traveler, traveler_to_global, start, dest)
    assert path is None


def test_no_path_because_of_offset_shadow(geometry, viz=False):
    voxel_size = 0.1
    traveler = Geometry(
        {
            "type": "cylinder",
            "radius": voxel_size,
            "height": 50 * voxel_size,
            "transform": {"angle": 45, "axis": (0, 1, 0)},
        },
        "traveler_mesh",
        "traveler",
    )
    point = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "point_mesh", "point")
    to_the_side = TTransform(offset=(1, 2, 3), from_cs="test", to_cs="global")
    from_geom_to_global = SRT3DTransform(
        offset=(1, 2, 3),
        angle=45,
        axis=(1, 0, 0),
        from_cs="test",
        to_cs="global",
    )
    dest = to_the_side.map(Point(np.array([0.7, 0, -0.7]), "test"))
    start = to_the_side.map(Point(np.array([0.2, 0.2, 5]), "test"))
    planner = GeometryMotionPlanner({geometry: from_geom_to_global}, voxel_size)
    path = planner.find_path(point, NullTransform(3, from_cs="point", to_cs="global"), start, dest, visualize=viz)
    if viz:
        pg.exec()
    assert path is not None
    path = planner.find_path(traveler, NullTransform(3, from_cs="traveler", to_cs="global"), start, dest, visualize=viz)
    if viz:
        pg.exec()
    assert path is None


draw_n = 0


def visualize():
    geometry = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "geometry_mesh", "geom")
    from_geom_to_global = SRT3DTransform(
        offset=(1, 2, 3),
        angle=45,
        axis=(1, 0, 0),
        from_cs="geom",
        to_cs="global",
    )

    voxel_size = 0.1

    traveler = Geometry(
        {
            "type": "cylinder",
            "radius": voxel_size,
            "height": 40 * voxel_size,
            "transform": {"angle": 45, "axis": (0, 1, 0)},
        },
        "traveler_mesh",
        "traveler",
    )

    dest = from_geom_to_global.map(Point(np.array([0.7, -0, -0.7]), "geom"))
    start = from_geom_to_global.map(Point(np.array([4, -2, 5]), "geom"))
    from_traveler_to_global = TTransform(offset=start, from_cs="traveler", to_cs="global")

    planner = GeometryMotionPlanner({geometry: from_geom_to_global}, voxel_size)
    path = planner.find_path(traveler, from_traveler_to_global, start, dest, visualize=True)
    print(path)

    pg.exec()


if __name__ == "__main__":
    pg.mkQApp()
    # visualize()
    geom = Geometry(
        {
            "type": "box",
            "size": [1.0, 1.0, 1.0],
            # "transform": {"angle": 45, "axis": (1, 1, 0)},
            "children": {
                "more rotated": {
                    "type": "box",
                    "size": [0.5, 0.5, 0.5],
                    "transform": {"pos": (1.5, 0, 0), "angle": 45, "axis": (0, 0, 1)},
                }
            },
        },
        "test_mesh",
        "test",
    )
    test_path_with_funner_traveler(geom, True)
    # test_single_voxel_voxelization(geom, True)
    # test_find_path(geom, True)
    # test_no_path(True)
    # test_no_path_because_of_offset_shadow(geom, True)
