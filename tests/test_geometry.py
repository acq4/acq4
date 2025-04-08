import time

import numpy as np
import pytest

from acq4.modules.Visualize3D import VisualizerWindow
from acq4.util import Qt
from acq4.util.geometry import Geometry, Volume, Plane, Line, point_in_bounds
from acq4.util.geometry import GeometryMotionPlanner
from coorx import NullTransform, TTransform, SRT3DTransform, Transform
from coorx import Point


@pytest.fixture(autouse=True)
def setup():
    GeometryMotionPlanner.clear_cache()


@pytest.fixture
def geometry():
    return Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test_mesh", "test")


@pytest.fixture
def cube():
    return [
        Plane(np.array([1, 0, 0]), np.array([0, 0, 0])),
        Plane(np.array([0, 1, 0]), np.array([0, 0, 0])),
        Plane(np.array([0, 0, 1]), np.array([0, 0, 0])),
        Plane(np.array([-1, 0, 0]), np.array([1, 1, 1])),
        Plane(np.array([0, -1, 0]), np.array([1, 1, 1])),
        Plane(np.array([0, 0, -1]), np.array([1, 1, 1])),
    ]


def do_viz(viz, geometries: dict[Geometry, Transform]):
    import pyqtgraph as pg

    if viz is None:
        return
    viz._window.show()
    viz.focus()
    for g, to_global in geometries.items():
        viz.addObstacle(g.voxel_template(0.1), to_global * g.transform)
        # viz.addGeometry(g)
        # viz.setMeshTransform(g.name, (to_global * g.transform).as_pyqtgraph())
    pg.exec()


def test_mesh(geometry):
    mesh = geometry.mesh
    assert mesh is not None
    assert np.allclose(mesh.bounds, [[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]])


@pytest.mark.parametrize(
    "to_parent",
    [
        NullTransform(3),
        TTransform(offset=(-3, -3, -3)),
        TTransform(offset=(4.5, 4.5, 4.5)),
        SRT3DTransform(offset=(8.2, 8.2, -8.2), angle=30, axis=(0, 1, 0)),
        SRT3DTransform(offset=(-8.2, 8.2, 8.2), angle=30, axis=(0, 1, 0)),
        SRT3DTransform(offset=(-8.2, 8.2, -8.2), scale=(0.1, 0.1, 0.1), angle=30, axis=(0, 1, 0)),
    ],
)
def test_line_intersects_voxel(to_parent):
    to_parent.set_systems("global", "parent")

    def point(coords):
        # points are written relative to the volume origin, so we need to move them, but we need to pretend they were
        # always in parent
        return Point(to_parent.map(np.array(coords)), "parent")

    voxel = Volume(np.ones((3, 3, 3), dtype=bool), to_parent)
    assert voxel.intersects_line(point([-1, -1, -1]), point([4, 4, 4]))
    assert voxel.intersects_line(point([-1, -1, -1]), point([5, 5, 1]))
    assert not voxel.intersects_line(point([-1, -1, -1]), point([5, 5, 0]))
    assert not voxel.intersects_line(point([-1, -1, -1]), point([5, 5, -1]))
    a_bit = np.array([0, 0, 1e-6])
    assert not voxel.intersects_line(point([-1, 1.1, 2]), point([1, 1.1, 4] + a_bit))
    assert voxel.intersects_line(point([-1, 1.1, 2]), point([1, 1.1, 4] - a_bit))


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
    # TODO it would be nice to positively assert something about the transformed voxelization
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
        import pyqtgraph as pg
        import pyqtgraph.opengl as gl

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


def test_cached_voxels_behave_well(geometry):
    voxel_size = 0.1
    template = geometry.voxel_template(voxel_size)

    template2 = geometry.voxel_template(voxel_size)
    assert np.all(template.volume == template2.volume)


def test_cached_convolutions_behave_well(geometry):
    kernel_array = np.ones((1, 1, 1), dtype=bool)
    voxel_size = 0.1
    orig = geometry.voxel_template(voxel_size)
    center = np.array([-10, 0, 100])
    convolved = orig.convolve(kernel_array, center=center, name="fake")
    convolved2 = orig.convolve(kernel_array, center=center, name="fake")
    assert np.all(convolved.volume == convolved2.volume)


def test_find_path(geometry, viz=None):
    voxel_size = 0.1
    geometry_to_global = NullTransform(3, from_cs=geometry.parent_name, to_cs="global")
    planner = GeometryMotionPlanner({geometry: geometry_to_global}, voxel_size)
    traveler = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "traveler_mesh", "traveler")
    dest = Point(np.array([0, 0, 3]), "global")
    start = Point(np.array([0, 0, -2]), "global")
    traveler_to_global = NullTransform(3, from_cs=traveler.parent_name, to_cs="global")
    path = planner.find_path(traveler, traveler_to_global, start, dest, visualizer=viz)
    do_viz(viz, {traveler: traveler_to_global, geometry: geometry_to_global})

    assert path is not None
    assert len(path) >= 2
    assert not np.all(path[0] == start.coordinates)
    assert not np.all(path[0] == dest.coordinates)
    assert np.all(path[-1] == dest.coordinates)
    # walk along the path at voxel_size steps and assert that we haven't touched the box
    last_point = start
    geometry_vol = geometry.voxel_template(voxel_size)
    global_to_geom_mesh = geometry.transform.inverse * geometry_to_global.inverse
    for waypoint in path:
        assert not geometry.contains(
            waypoint, padding=voxel_size
        ), f"waypoint {waypoint} is within {voxel_size} of {geometry.mesh.bounds}"
        # TODO ugh! this line is intermittently failing....
        # assert not geometry_vol.intersects_line(global_to_geom_mesh.map(last_point), global_to_geom_mesh.map(waypoint)), f"line from {last_point} to {waypoint} intersects {geometry.mesh.bounds}"
        last_point = waypoint


@pytest.mark.xfail(reason="we aren't currently building for multi-pipette planning")
@pytest.mark.parametrize("offset", [(0, 0, 0), (1, 1, 1), (0.2, 0.2, 0.2), (0.6, 0.6, 0.6)])
def test_grazing_paths(offset, viz=None):
    vx = 1.0
    trav = Geometry({"type": "box", "size": [vx / 2, vx / 2, vx / 2]}, "trav", "trav_mesh")
    obst = Geometry(
        {"type": "box", "size": [vx * 0.9, vx * 0.9, vx * 0.9], "transform": {"pos": (0.05, 0.05, 0.05)}},
        "obst",
        "obst_mesh",
    )
    trav_to_global = SRT3DTransform(angle=90, axis=(1, 0, 1), offset=offset, from_cs=trav.parent_name, to_cs="global")
    obst_to_global = TTransform(offset=(1, 1, 1.5), from_cs=obst.parent_name, to_cs="global")
    to_obst_parent_from_trav_parent = obst_to_global.inverse * trav_to_global
    conv_obst = obst.make_convolved_voxels(trav, to_obst_parent_from_trav_parent, vx)
    if viz:
        viz.addGeometry(trav)
        viz.setMeshTransform(trav.name, trav_to_global.as_pyqtgraph())
        viz.addGeometry(obst)
        viz.setMeshTransform(obst.name, obst_to_global.as_pyqtgraph())
        # viz.startPath(
        #     Point(np.array([0, 0, 0]), "trav").mapped_to("global"),
        #     Point(np.array([1.1, 2, 2]), "global"),
        #     [],
        # )
        viz.startPath(
            Point(np.array(offset), "global"),
            Point(np.array([2, 0, 2]), "global"),
            [],
        )
        viz.addObstacle(trav.voxel_template(vx), trav_to_global * trav.transform).wait()
        # viz.addObstacleVolumeOutline(obst.voxel_template(vx), obst_to_global * obst.transform).wait()
        viz.addObstacle(conv_obst, obst_to_global * obst.transform).wait()
        # to_obst_from_trav = obst.transform.inverse * to_obst_parent_from_trav_parent * trav.transform
        # xformed = trav.transformed_to(obst.transform, to_obst_from_trav)
        # xformed_voxels = xformed.voxel_template(vx)
        # viz.addObstacleVolumeOutline(xformed_voxels, obst_to_global * obst.transform)

        pg.exec()

    assert conv_obst.intersects_line(
        Point(np.array([0, 0, 0]), "trav").mapped_to("obst"), Point(np.array([1.1, 2, 2]), "global").mapped_to("obst")
    )
    assert conv_obst.intersects_line(
        Point(np.array(offset), "global").mapped_to("obst"), Point(np.array([2, 0, 2]), "global").mapped_to("obst")
    )
    for pt in obst.mesh.vertices:
        pt = Point(pt, "obst_mesh").mapped_to("obst")
        assert conv_obst.contains_point(pt), f"point {pt} is not in the convolved obstacle"


def test_z_and_x_are_not_swapped(viz=None):
    geometry = Geometry({"type": "box", "size": [10.0, 1.0, 1.0]}, "test_mesh", "test")
    voxel_size = 0.1
    from_geom_to_global = NullTransform(3, from_cs=geometry.parent_name, to_cs="global")
    start = Point(np.array([0, 0, 3]), "global")
    dest = Point(np.array([0, -4, 0]), "global")
    planner = GeometryMotionPlanner({geometry: from_geom_to_global}, voxel_size)
    traveler = Geometry({"type": "box", "size": [voxel_size, voxel_size, voxel_size]}, "traveler_mesh", "traveler")

    traveler_to_global = NullTransform(3, from_cs=traveler.parent_name, to_cs="global")
    path = planner.find_path(traveler, traveler_to_global, start, dest, visualizer=viz)
    do_viz(viz, {geometry: from_geom_to_global, traveler: traveler_to_global})
    assert path is not None

    with pytest.raises(ValueError):
        planner.find_path(
            traveler, NullTransform(3, from_cs=traveler.parent_name, to_cs="global"), start[::-1], dest, visualizer=viz
        )
    do_viz(viz, {geometry: from_geom_to_global, traveler: traveler_to_global})


def test_path_with_funner_traveler(geometry, viz=None):
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
    to_global_from_geometry = NullTransform(3, from_cs="test", to_cs="global")
    planner = GeometryMotionPlanner({geometry: to_global_from_geometry}, voxel_size)
    to_global_from_traveler = TTransform(offset=start, from_cs="traveler", to_cs="global")
    path = planner.find_path(traveler, to_global_from_traveler, start, dest, visualizer=viz)
    do_viz(viz, {traveler: to_global_from_traveler, geometry: to_global_from_geometry})
    assert path is not None
    assert len(path) >= 2
    assert not np.all(path[0] == start)
    assert not np.all(path[0] == dest)


def test_bounds_prevent_path(geometry, cube, viz=None):
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
    traveler_to_global = TTransform(offset=start, from_cs="traveler", to_cs="global")
    with pytest.raises(ValueError):
        planner.find_path(traveler, traveler_to_global, start, dest, cube, visualizer=viz)
    do_viz(viz, {traveler: traveler_to_global})


@pytest.mark.xfail(reason="This scenario is highly unlikely, but we may fix it at some point")
def test_paths_stay_inside_bounds(geometry, viz=None):
    voxel_size = 1
    sqrt3 = 3**0.5
    sqrt6 = 6**0.5
    tetrahedron = [
        Plane(np.array([sqrt3 / 3, 0, -1 / 3]), np.array([0, 0, 10])),
        Plane(np.array([-sqrt3 / 6, -1 / 2, -1 / 3]), np.array([0, 0, 10])),
        Plane(np.array([-sqrt3 / 6, 1 / 2, -1 / 3]), np.array([0, 0, 10])),
        Plane(np.array([0, 0, 1]), np.array([0, 0, 0])),
    ]
    edges = Plane.wireframe(*tetrahedron)
    bottom_corners = {tuple(pt) for edge in edges for pt in edge if pt[2] == 0}
    start = bottom_corners.pop()
    start = Point(start, "global")
    stop = np.sum([np.array(c) for c in bottom_corners], axis=0) / 2
    stop = Point(stop, "global")

    edge_length = 10 * 4 / (6**0.5)
    transecting_obst = Geometry(
        {"type": "cylinder", "radius": voxel_size * 0.49, "height": edge_length}, "blocker_mesh", "blocker"
    )
    obst_to_global = SRT3DTransform(
        offset=(0, -edge_length / 2, 0), angle=90, axis=(1, 0, 0), from_cs="blocker", to_cs="global"
    )
    trav_to_global = TTransform(offset=start, from_cs="test", to_cs="global")
    if viz:
        viz.startPath(start, stop, tetrahedron)
    planner = GeometryMotionPlanner({transecting_obst: obst_to_global}, voxel_size)
    try:
        for _ in range(1):
            path = planner.find_path(geometry, trav_to_global, start, stop, tetrahedron, visualizer=viz)
            for point in path:
                assert point_in_bounds(point, tetrahedron)
    finally:
        if viz:
            pg.exec()


def test_no_path(viz=None):
    geometry = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test_mesh", "test")
    voxel_size = 0.1
    geometry_to_global = NullTransform(3, from_cs=geometry.parent_name, to_cs="global")
    planner = GeometryMotionPlanner({geometry: geometry_to_global}, voxel_size)
    traveler = Geometry(
        {"type": "box", "size": [voxel_size, voxel_size, 6 * voxel_size], "transform": {"pos": (0, 0, -0.3)}},
        "traveler_mesh",
        "traveler",
    )
    from_traveler_to_global = TTransform(offset=(0, 2, 3), from_cs="traveler", to_cs="global")
    start = from_traveler_to_global.map(Point(np.array([0, 0, 0]), "traveler"))
    dest = Point(np.array([voxel_size, voxel_size, voxel_size]) * 2, "global")  # inside the box
    with pytest.raises(ValueError):
        planner.find_path(traveler, from_traveler_to_global, start, dest, visualizer=viz)
    do_viz(viz, {geometry: geometry_to_global, traveler: from_traveler_to_global})


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
    with pytest.raises(ValueError):
        planner.find_path(traveler, traveler_to_global, start, dest)


def test_no_path_because_of_offset_shadow(geometry, viz=None):
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
    point_to_global = TTransform(offset=start, from_cs="point", to_cs="global")
    path = planner.find_path(point, point_to_global, start, dest, visualizer=viz)
    do_viz(viz, {geometry: from_geom_to_global, point: point_to_global})
    assert path is not None
    traveler_to_global = TTransform(offset=start, from_cs="traveler", to_cs="global")
    with pytest.raises(ValueError):
        planner.find_path(traveler, traveler_to_global, start, dest, visualizer=viz)
    do_viz(viz, {geometry: from_geom_to_global, traveler: traveler_to_global})


def assert_all_intersect_at(pt, *lines):
    for a in lines:
        for b in lines:
            if a == b:
                # point can be arbitrary
                assert a.intersecting_point(b) is not None
                assert b.intersecting_point(a) is not None
            else:
                assert np.allclose(x := a.intersecting_point(b), pt), f"{a} and {b} intersect at {x}, not {pt}"
                assert np.allclose(x := b.intersecting_point(a), pt), f"{b} and {a} intersect at {x}, not {pt}"


def test_line_intersections():
    a = Line(np.array([1.0, 0.0, 0.0]), np.array([0.0, 0.0, 0.0]))

    assert_all_intersect_at(
        np.array([0.0, 0.0, 0.0]),
        a,
        Line(np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 0.0])),
        Line(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 0.0])),
        Line(np.array([0.0, 0.0, 1.0]), np.array([0.0, 0.0, 10.0])),
        Line(np.array([0.0, 0.0, -1.0]), np.array([0.0, 0.0, 10.0])),
        Line(np.array([0.0, -1.0, 1.0]), np.array([0.0, 1.0, -1.0])),
        Line(np.array([1.0, 1.0, 1.0]), np.array([3.14159, 3.14159, 3.14159])),
    )

    b = Line(np.array([0.0, 1.0, 0.0]), np.array([1.0, 1.0, 1.0]))
    assert a.intersecting_point(b) is None
    assert b.intersecting_point(a) is None


def test_wireframe(cube):
    wireframe = Plane.wireframe(*cube)
    assert len(wireframe) == 12
    wireframe = np.array(wireframe)
    assert wireframe.shape == (12, 2, 3)

    assert np.any(np.all(wireframe == np.array([[0, 0, 0], [1, 0, 0]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[0, 0, 0], [0, 1, 0]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[0, 0, 0], [0, 0, 1]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[1, 1, 1], [0, 1, 1]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[1, 1, 1], [1, 0, 1]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[1, 1, 1], [1, 1, 0]]), axis=1))


def test_allows_point():
    plane = Plane(np.array((0, 0, 1)), np.array((0, 0, 0)))
    assert plane.allows_point(np.array((0, 0, 0)))
    assert plane.allows_point(np.array((0, 0, 1)))
    assert plane.allows_point(np.array((0, 0, 1e-9)))
    assert plane.allows_point(np.array((0, 0, -1e-10)))
    assert not plane.allows_point(np.array((0, 0, -1e-9)))
    assert not plane.allows_point(np.array((0, 0, -1)))


def test_wireframe_acq4():
    bounds = [
        Plane(
            np.array([9.99999971e-01, -2.41127827e-04, -4.41750099e-07]),
            np.array([0.00012748, -0.00034118, -0.00010044]),
        ),
        Plane(
            np.array([-9.99999971e-01, -2.41237557e-04, -4.41951126e-07]),
            np.array([0.14022748, 0.13975882, 0.13999956]),
        ),
        Plane(
            np.array([2.27538386e-04, 9.99999974e-01, -4.41957183e-07]),
            np.array([0.00012748, -0.00034118, -0.00010044]),
        ),
        Plane(
            np.array([2.27428656e-04, -9.99999974e-01, -4.41744050e-07]), np.array([0.14022748, 0.13975882, 0.13999956])
        ),
        Plane(
            np.array([2.27483601e-04, -2.41182780e-04, 9.99999945e-01]),
            np.array([0.00012748, -0.00034118, -0.00010044]),
        ),
        Plane(
            np.array([2.27483400e-04, -2.41182566e-04, -9.99999945e-01]), np.array([0.14022748, 0.13975882, 0.13999956])
        ),
    ]
    wireframe = Plane.wireframe(*bounds)
    assert len(wireframe) == 12
    wireframe = np.array(wireframe)
    assert wireframe.shape == (12, 2, 3)


def test_nested_wireframes_only_show_the_innermost(cube):
    inner_cube = [Plane(p.normal, p.point / 2) for p in cube]
    edges = Plane.wireframe(*cube, *inner_cube)
    assert len(edges) == 12
    for e in edges:
        for pt in e:
            for val in pt:
                assert val in [0, 0.5]


def test_wireframe_rhomboid():
    rhomboid = [
        Plane(np.array([1, 0, 1]), np.array([0, 0, 0])),
        Plane(np.array([0, 1, 1]), np.array([0, 0, 0])),
        Plane(np.array([0, 0, 1]), np.array([0, 0, 0])),
        Plane(np.array([-1, 0, -1]), np.array([1, 1, 1])),
        Plane(np.array([0, -1, -1]), np.array([1, 1, 1])),
        Plane(np.array([0, 0, -1]), np.array([1, 1, 1])),
    ]
    wireframe = Plane.wireframe(*rhomboid)
    assert len(wireframe) == 12
    wireframe = np.array(wireframe)
    assert wireframe.shape == (12, 2, 3)

    assert np.any(np.all(wireframe == np.array([[-1, 0, 0], [1, 0, 0]]), axis=1))
    assert np.any(np.all(wireframe == np.array([[1, 1, 1], [0, 1, 0]]), axis=1))


def test_cylinder_pathfinding_performance():
    """
    Performance test for pathfinding in a challenging scenario:
    - Navigating from under a half-closed cylinder to a position just inside the top lip
    """
    voxel_size = 0.1
    height = 10.0
    radius = 5.0
    cylinder = Geometry(
        {
            "type": "cylinder",
            "radius": radius,
            "height": height,
            "close_bottom": True,
            "close_top": False,
        },
        "cylinder_mesh",
        "cylinder"
    )

    # Create a small traveler
    traveler = Geometry(
        {"type": "box", "size": [0.5, 0.5, 0.5]},
        "traveler_mesh",
        "traveler"
    )

    cylinder_to_global = NullTransform(3, from_cs="cylinder", to_cs="global")
    planner = GeometryMotionPlanner({cylinder: cylinder_to_global}, voxel_size)
    traveler_to_global = NullTransform(3, from_cs="traveler", to_cs="global")

    # Start inside/under the cylinder
    start = Point(np.array([0.0, 0, -1.0]), "global")

    # End just inside the top lip - requires navigating around the edge
    end = Point(np.array([0, 0, height - 0.2]), "global")

    # Timing variables
    times = []
    path_lengths = []
    iterations = 5  # Number of iterations to run

    # First run (warm-up)
    print("\nRunning initial warm-up iteration...")
    start_time = time.time()
    path = planner.find_path(traveler, traveler_to_global, start, end)
    first_run_time = time.time() - start_time
    print(f"Initial run: {first_run_time:.4f}s, path length: {len(path)}")

    # Benchmark runs
    print(f"Running {iterations} benchmark iterations...")
    for i in range(iterations):
        start_time = time.time()
        path = planner.find_path(traveler, traveler_to_global, start, end)
        elapsed = time.time() - start_time
        times.append(elapsed)
        path_lengths.append(len(path))
        print(f"Iteration {i + 1}: {elapsed:.4f}s, path length: {len(path)}")

    # Report results
    avg_time = sum(times) / len(times)
    avg_path_length = sum(path_lengths) / len(path_lengths)

    print("\nResults:")
    print(f"Average execution time: {avg_time:.4f}s")
    print(f"Average path length: {avg_path_length:.1f} waypoints")
    print(f"Time range: {min(times):.4f}s - {max(times):.4f}s")

    return avg_time, avg_path_length, path


draw_n = 0


class FakeDevice(Qt.QObject):
    sigGeometryChanged = Qt.pyqtSignal(str, str)
    sigGlobalTransformChanged = Qt.pyqtSignal(str, str)

    def __init__(self, name, geom, bounds=None):
        super().__init__()
        self._name = name
        self._bounds = bounds
        self.transform = NullTransform(3, from_cs=name, to_cs="global").as_pyqtgraph()
        self.geom = geom

    def name(self):
        return self._name

    def getGeometry(self):
        return self.geom

    def globalPhysicalTransform(self):
        return self.transform

    def getBoundaries(self):
        return self._bounds


if __name__ == "__main__":
    avg_time, avg_path_length, path = test_cylinder_pathfinding_performance()
    print(f"\nTarget performance: 0.2s or less (current: {avg_time:.4f}s)")

    import pyqtgraph as pg
    import pyqtgraph.opengl as gl

    pg.mkQApp()
    visualizer = VisualizerWindow(testing=True)
    visualizer.show()
    # geom = Geometry(
    #     {
    #         "type": "box",
    #         "size": [0.2, 0.2, 0.2],
    #         # "transform": {"angle": 45, "axis": (1, 1, 0)},
    #         "children": {
    #             "more rotated": {
    #                 "type": "box",
    #                 "size": [0.5, 0.5, 0.5],
    #                 "transform": {"pos": (1.5, 0, 0), "angle": 45, "axis": (0, 0, 1)},
    #             }
    #         },
    #     },
    #     "test_mesh",
    #     "test",
    # )
    geom = Geometry({"type": "box", "size": [1.0, 1.0, 1.0]}, "test_mesh", "test")
    bounds = [
        Plane(np.array([1, 0, 0]), np.array([0, 0, 0])),
        Plane(np.array([0, 1, 0]), np.array([0, 0, 0])),
        Plane(np.array([0, 0, 1]), np.array([0, 0, 0])),
        Plane(np.array([1, 0, 0]), np.array([1, 1, 1])),
        Plane(np.array([0, 1, 0]), np.array([1, 1, 1])),
        Plane(np.array([0, 0, 1]), np.array([1, 1, 1])),
    ]

    dev = FakeDevice("test", geom)  # , bounds=bounds)
    visualizer.addDevice(dev)
    viz = visualizer.pathPlanVisualizer(dev)
    # test_paths_stay_inside_bounds(geom, viz)
    # test_grazing_paths((0.6, 0.6, 0.6), viz)
    # test_bounds_prevent_path(geom, bounds, viz)
    # test_path_with_funner_traveler(geom, viz)
    # test_single_voxel_voxelization(geom, viz)
    # test_find_path(geom, viz)
    # test_no_path(viz)
    test_no_path_because_of_offset_shadow(geom, viz)
