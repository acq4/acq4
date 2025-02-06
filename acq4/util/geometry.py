from __future__ import annotations

import itertools
from functools import cached_property
from threading import RLock
from typing import List, Callable, Optional, Dict, Any, Generator

import numba
import numpy as np
import scipy
import trimesh
from trimesh.voxel import VoxelGrid

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from acq4.util.approx import ApproxDict, ApproxSet
from coorx import SRT3DTransform, Transform, NullTransform, TTransform, Point, AffineTransform
from pyqtgraph import debug
from pyqtgraph.units import µm


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


@numba.jit(nopython=True)
def line_intersects_voxel(start: np.ndarray, end: np.ndarray, vox: np.ndarray):
    """
    Check if a line segment intersects with a voxel (using Numba optimization)
    """
    diff = end - start
    norm = np.sqrt(diff[0] ** 2 + diff[1] ** 2 + diff[2] ** 2)  # Faster than np.linalg.norm
    direction = diff / norm

    # Check each axis
    for ax in range(3):
        if abs(direction[ax]) < 1e-10:  # Avoid division by zero
            continue

        ax2 = (ax + 1) % 3
        ax3 = (ax + 2) % 3

        # Calculate min and max for x_steps
        min_val = min(start[ax], end[ax])
        max_val = max(start[ax], end[ax])

        # Create steps array manually since np.arange isn't supported in nopython mode
        start_step = int(np.ceil(min_val))
        end_step = int(np.floor(max_val)) + 1

        for x in range(start_step, end_step):
            t = (x - start[ax]) / direction[ax]
            y = int(np.floor(start[ax2] + t * direction[ax2]))
            z = int(np.floor(start[ax3] + t * direction[ax3]))

            # Create index array
            index = np.zeros(3, dtype=np.int64)
            index[ax] = x
            index[ax2] = y
            index[ax3] = z

            # Check both current and previous voxel
            if index[0] == vox[0] and index[1] == vox[1] and index[2] == vox[2]:
                return True

            index[ax] -= 1
            if index[0] == vox[0] and index[1] == vox[1] and index[2] == vox[2]:
                return True

    return False


def find_intersected_voxels(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> Generator[tuple[int, int, int], Any, None]:
    """
    Find all voxels intersected by a line segment.

    Parameters:
    - line_start: Start point of the line segment
    - line_end: End point of the line segment
    - voxel_space_max: Maximum voxel coordinates in the space (assumes minimum is 0)

    Returns:
    - Generator of voxel coordinates intersected by the line
    """
    # Compute bounding box of the line
    min_point = np.minimum(line_start, line_end)
    max_point = np.maximum(line_start, line_end)

    # Determine voxel range
    start_voxel = np.floor(min_point).astype(int)
    start_voxel = np.maximum(start_voxel, 0)
    end_voxel = np.floor(max_point).astype(int)
    end_voxel = np.minimum(end_voxel, voxel_space_max)

    return (
        (x, y, z)
        for x in range(start_voxel[0], end_voxel[0] + 1)
        for y in range(start_voxel[1], end_voxel[1] + 1)
        for z in range(start_voxel[2], end_voxel[2] + 1)
        if line_intersects_voxel(line_start, line_end, np.array([x, y, z]))
    )


def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]


def generate_even_sphere_points(n_points: int, sphere_radius: float):
    """Generate points with an even distribution of directions but random lengths."""
    phi = np.pi * (3.0 - np.sqrt(5.0))  # golden angle in radians

    directions = []
    for i in range(n_points):
        y = 1 - (i / float(n_points - 1)) * 2  # y goes from 1 to -1
        radius = np.sqrt(1 - y * y)  # radius at y

        theta = phi * i  # golden angle increment

        x = np.cos(theta) * radius
        z = np.sin(theta) * radius

        directions.append(np.array([x, y, z]))

    radii = sphere_radius * np.cbrt(np.random.random(n_points))
    return np.array(directions) * radii[:, np.newaxis]


def generate_biased_sphere_points(n_points: int, sphere_radius: float, bias_direction: np.ndarray, concentration=1.0):
    """
    Generate random points within a sphere with directional bias.

    Parameters:
    - n_points: Number of points to generate
    - sphere_radius: Radius of the containing sphere
    - bias_direction: Unit vector indicating preferred direction
    - concentration: Controls spread (higher = more concentrated around bias direction)

    Returns:
    - Array of points (n_points, 3)
    """
    bias_direction = bias_direction / np.linalg.norm(bias_direction)

    # Generate points using von Mises-Fisher distribution
    # This provides a directionally biased distribution on a sphere
    def sample_vmf(mu, kappa, size):
        dim = len(mu)

        # Generate base distribution
        base = np.random.normal(0, 1, (size, dim))
        base /= np.linalg.norm(base, axis=1)[:, np.newaxis]

        dot_products = base @ mu

        # Apply concentration with element-wise multiplication
        result = base + kappa * (dot_products[:, np.newaxis] * mu - base)
        return result / np.linalg.norm(result, axis=1)[:, np.newaxis]

    # Sample directions with bias
    directions = sample_vmf(bias_direction, concentration, n_points)

    # Random radial distance (uniform within sphere)
    radii = sphere_radius * np.cbrt(np.random.random(n_points))

    # Combine directions and radii
    return directions * radii[:, np.newaxis]


def a_star_ish(
    start: np.ndarray,
    finish: np.ndarray,
    edge_cost: Callable,
    heuristic: Callable = None,
    neighbors: Callable = None,
    max_cost: int = 4000,
    callback: Callable = None,
) -> List[np.ndarray]:
    """Find a path between *start* and *finish*. Return the path or raise a ValueError.

    Parameters
    ----------
    start
        Initial position.
    finish
        Final position.
    edge_cost
        Function that takes two points and returns the cost of moving between them. If the cost is np.inf, the edge is
        treated as impossible.
    heuristic
        Function that estimates the cost of moving from a point to the finish. Defaults to the Euclidean distance.
    neighbors
        Function that returns the neighbors of a point to try building a path to the finish.
    max_cost
        Maximum number of iterations before giving up.
    callback
        Used for debugging and visualization. Called with the current path at each iteration.
    """
    if heuristic is None:

        def heuristic(x, y):
            return np.linalg.norm(y - x)

    if neighbors is None:
        radius = np.linalg.norm(finish - start) / 5
        radius = max(radius, 100e-6)
        count = 10

        def neighbors(pt):
            yield (radius * (finish - pt) / np.linalg.norm(finish - pt)) + pt
            points = generate_biased_sphere_points(count, radius, finish - pt, concentration=0.4)
            yield from (points + pt)
            yield finish

    open_set = {tuple(start): start}
    came_from = {}
    g_score = {tuple(start): 0}
    f_score = {tuple(start): heuristic(start, finish)}
    cost = 0

    while open_set:
        curr_key = min(open_set, key=lambda x: f_score[x])
        current = open_set.pop(curr_key)
        if np.all(current == finish):
            return reconstruct_path(came_from, curr_key)

        for neighbor in neighbors(current):
            cost += 1
            if cost > max_cost:
                raise ValueError(f"Pathfinding exceeded maximum cost of {max_cost}")
            neigh_key = tuple(neighbor)
            this_cost = edge_cost(current, neighbor)
            tentative_g_score = g_score[curr_key] + this_cost
            if neigh_key not in g_score or tentative_g_score < g_score[neigh_key] or np.all(neighbor == finish):
                came_from[neigh_key] = curr_key
                g_score[neigh_key] = tentative_g_score
                f_score[neigh_key] = tentative_g_score + 2 * heuristic(neighbor, finish)
                if f_score[neigh_key] < np.inf and neigh_key not in open_set:
                    open_set[neigh_key] = neighbor
            if callback is not None:
                callback(reconstruct_path(came_from, neigh_key)[::-1])

    raise ValueError("Pathfinding failed; no valid paths found.")


def simplify_path(path, edge_cost: Callable):
    """Simplify the given path by iteratively removing unnecessary waypoints."""
    path = list(path)
    made_change = True
    while made_change:
        made_change = False
        ptr = 0
        while ptr < len(path) - 2:
            if edge_cost(np.array(path[ptr]), np.array(path[ptr + 2])) < np.inf:
                path.pop(ptr + 1)
                made_change = True
            ptr += 1
    return path


class GeometryMotionPlanner:
    _cache = {}
    _cache_lock = RLock()

    @classmethod
    def clear_cache(cls):
        with cls._cache_lock:
            cls._cache = {}

    def __init__(self, geometries: Dict[Geometry, Transform], voxel_size: float = 350 * µm):
        """
        Parameters
        ----------
        geometries : Dict[Geometry, BaseTrasnform]
            Dictionary of Geometry instances representing all collision objects in the world and the transform that
            respectively takes them to the global coordinate system.
        voxel_size : float
            Resolution of the voxel grid used for path planning.
        """
        self._draw_n = 0
        self.geometries = geometries
        self.voxel_size = voxel_size

    def find_path(
        self,
        traveler: Geometry,
        to_global_from_traveler: Transform,
        start,
        stop,
        bounds=None,
        callback=None,
        visualizer=None,
    ):
        """
        Return a path from *start* to *stop* in the global coordinate system that *traveling_object* can follow to avoid
        collisions.

        Method:
        1. Create voxelized representations of traveling_object in the coordinate systems of all other geometries
             traveling_object.voxelize (in coordinate system of traveling_object)
             take mirror image of volume; this becomes the convolution kernel
             the center of the kernel needs to be mirrored as well
        2. Create convolutions between all other geometries and traveling_object
             geometry.voxelize (in local coordinate system)
             volume.convolve(geometry_voxels, traveling_kernel)
        3. Do a path-finding algorithm that, at each step, checks for collisions among all convolved volumes
             A* (ish)
             volume.check_edge_collision

        Parameters
        ----------
        traveler : Geometry
            Geometry representing the object to be moved from *start* to *stop*
        to_global_from_traveler : Transform
            Transform that maps from the traveling_object's local coordinate system to global
        start
            Global coordinates of the traveling object's origin when at initial location
        stop
            Global coordinates of the final location we want the traveling object's origin to be.
        callback : callable
            A function to be called at each step of the path planning process (mostly to aid in visualization and
            debugging).
        bounds : Planes
            Planes that define the bounds of the space in which the path is to be found.
        visualizer : window or None
            If not None, a window to visualize the path planning process in real time.

        Returns
        -------
        path : list
            List of global positions to get from start to stop
        """
        start = Point(start, "global")
        stop = Point(stop, "global")
        bounds = [] if bounds is None else bounds
        if visualizer is not None:
            if callback is None:
                callback = visualizer.updatePath
            visualizer.startPath(start, stop, bounds)
            visualizer.addObstacleVolumeOutline(
                traveler.voxel_template(self.voxel_size), to_global_from_traveler * traveler.transform
            )
        in_bounds, bound_plane = point_in_bounds(start.coordinates, bounds)
        if not in_bounds:
            raise ValueError(f"Starting point {start} is on the wrong side of the {bound_plane} boundary")

        profile = debug.Profiler()
        obstacles = []
        for obst, to_global_from_obst in self.geometries.items():
            if obst is traveler:
                continue
            cache_key = (obst.name, traveler.name)
            with self._cache_lock:
                if cache_key not in self._cache:
                    convolved_obst = obst.make_convolved_voxels(
                        traveler, to_global_from_obst.inverse * to_global_from_traveler, self.voxel_size
                    )
                    # TODO is this bad? explicitly setting transforms frequently is...
                    convolved_obst.transform = obst.transform * convolved_obst.transform
                    self._cache[cache_key] = convolved_obst
                    profile.mark(f"cache miss: generated convolved obstacle {obst.name}")
                obst_volume = self._cache[cache_key]

            obstacles.append((obst_volume, to_global_from_obst))
            if visualizer is not None:
                visualizer.addObstacleVolumeOutline(obst_volume, to_global_from_obst)
            if obst_volume.contains_point(to_global_from_obst.inverse.map(start)):
                raise ValueError(f"Start point {start} is inside obstacle {obst.name}")
            if obst_volume.contains_point(to_global_from_obst.inverse.map(stop)):
                raise ValueError(f"Destination point {stop} is inside obstacle {obst.name}")

        profile.mark("voxelized all obstacles")

        def edge_cost(a: np.ndarray, b: np.ndarray):
            if not point_in_bounds(b, bounds)[0]:
                return np.inf
            a = Point(a, start.system)
            b = Point(b, start.system)
            for vol, to_global in obstacles:
                if vol.intersects_line(to_global.inverse.map(a), to_global.inverse.map(b)):
                    return np.inf
            return np.linalg.norm(b - a)

        path = a_star_ish(start.coordinates, stop.coordinates, edge_cost, callback=callback)
        profile.mark("A*")
        path = simplify_path(path, edge_cost)
        profile.mark("simplified path")
        if callback:
            callback(path, skip=1)
        profile.finish()
        return path[1:]


def point_in_bounds(point, bounds):
    """Return True if the given point is inside the given bounds.
    Also return the first plane that the point is outside of, if any."""
    for plane in bounds:
        if plane.distance_to_point(point) < 0:
            return False, plane
    return True, None


@numba.jit(nopython=True)
def convolve_kernel_onto_volume(volume: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    # scipy does weird stuff
    # return scipy.signal.convolve(volume.astype(int), kernel.astype(int), mode="full").astype(bool)
    v_shape = volume.shape
    k_shape = kernel.shape
    shape = (v_shape[0] + k_shape[0] - 1, v_shape[1] + k_shape[1] - 1, v_shape[2] + k_shape[2] - 1)

    dest = np.zeros(shape, dtype=np.bool_)

    for x in range(v_shape[0]):
        for y in range(v_shape[1]):
            for z in range(v_shape[2]):
                if volume[x, y, z]:
                    for kx in range(k_shape[0]):
                        for ky in range(k_shape[1]):
                            for kz in range(k_shape[2]):
                                if kernel[kx, ky, kz]:
                                    dest[x + kx, y + ky, z + kz] = True
    return dest


class Volume(object):
    """
    A volumetric representation of Geometry

    Parameters
    ----------
    volume : ndarray
        3D boolean array containing voxelized geometry
    transform : coorx.Transform
        Transform that maps from the local coordinate system of this volume (i.e. voxel coordinates) to the parent
        geometry's coordinate system.
    """

    def __init__(self, volume: np.ndarray, transform: Transform):
        self.volume = volume
        self.transform: Transform = transform

    @property
    def inverse_transform(self):
        """The transform that maps from the parent geometry's coordinate system to the local coordinate system."""
        return self.transform.inverse

    @property
    def parent_origin(self):
        """The origin of the mesh CS in the voxel's CS"""
        origin = Point(np.array([0, 0, 0]), self.transform.systems[1])
        return self.transform.inverse.map(origin)

    def convolve(self, kernel_array: np.ndarray, center: np.ndarray, name: str) -> Volume:
        """
        Return a new Volume that contains the convolution of self with *kernel_array*.

        Parameters
        ----------
        kernel_array
            Voxel array to convolve with, already transformed to match the rotation of self
        center
            Position of the "center" point relative to the kernel. This is added to the resulting Volume's transform.
        name
            Name of the kernel
        """
        dest = convolve_kernel_onto_volume(self.volume, kernel_array)
        draw_xform = TTransform(
            offset=-center,
            to_cs=self.transform.systems[0],
            from_cs=f"[convolved {name} in {self.transform.systems[1]}]",
        )
        return Volume(dest, self.transform * draw_xform)

    def intersects_line(self, a, b):
        """Return True if the line segment between *a* and *b* intersects with this volume. Points should be in the
        parent coordinate system of the volume"""
        line_voxels = find_intersected_voxels(
            self.transform.inverse.map(a)[::-1],
            self.transform.inverse.map(b)[::-1],
            np.array(self.volume.shape) - 1,
        )
        return next((True for x, y, z in line_voxels if self.volume[x, y, z]), False)

    def contains_point(self, point: np.ndarray):
        """Return True if the given point is inside this volume. Point should be in the parent coordinate system of the
        volume"""
        # TODO turn [::-1] into a part of the transform
        coords = np.floor(self.transform.inverse.map(point)).astype(int)[::-1]
        if np.any(coords < 0) or np.any(coords >= self.volume.shape):
            return False
        return self.volume[tuple(coords)]

    @cached_property
    def surface_mesh(self):
        return pg.isosurface(np.ascontiguousarray(self.volume.T.astype(int)), 1)


class Geometry:
    def __init__(
        self,
        config: Dict | str = None,
        name: str = None,
        parent_name: str = None,
        mesh: trimesh.Trimesh = None,
        transform: Transform = None,
        color=None,
    ):
        """Create a geometry either from a configuration (see parse_config) or from a mesh and transform."""
        self.color = color
        self.name = name
        self.parent_name = parent_name
        if parent_name is None and transform is not None:
            self.parent_name = str(transform.systems[1])
        if name is None and transform is not None:
            self.name = str(transform.systems[0])
        self._config = config
        self._children: List[Geometry] = []
        if mesh is None:
            self._mesh: trimesh.Trimesh = trimesh.Trimesh()
            self._total_mesh: Optional[trimesh.Trimesh] = None
        else:
            self._mesh = self._total_mesh = mesh
        # maps from local coordinate system of geometry (the coordinates in which mesh vertices are specified) to parent
        if config is not None:
            self.parse_config()
        if getattr(self, "_transform", None) is None:
            self._transform: Transform = transform or NullTransform(3, **self._default_transform_args())

    def parse_config(self):
        """Create 3D mesh from a configuration. Format example::

        geometry:
            color: (1, 0.7, 0.1, 1)    # color will be inherited by children
            type: "cone"               # type must be "cone", "cylinder" or "box"
            top_radius: 20 * mm
            bottom_radius: 4 * mm
            children:
                component_1:               # names for children are in their key
                    type: "cone"
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
        """
        config = self._config.copy()

        self.color = config.pop("color", None)

        xform = config.pop("transform", {}).copy()
        if "pos" in xform:
            xform["offset"] = xform.pop("pos")
        self._transform = SRT3DTransform(**self._default_transform_args(), **xform)

        self._children = []
        for name, child_config in config.pop("children", {}).items():
            if "color" not in child_config:
                child_config["color"] = self.color
            child = Geometry(child_config, name, self.name)
            self._children.append(child)

        geom_type = config.pop("type", None)
        if geom_type == "box":
            self._mesh = self.make_box(config)
        elif geom_type == "cone":
            self._mesh = self.make_cone(config)
        elif geom_type == "cylinder":
            self._mesh = self.make_cylinder(config)
        elif geom_type is not None:
            raise ValueError(f"Unsupported geometry type: {geom_type}")

        if len(config) > 0:
            raise ValueError(f"Invalid geometry config: {config}")

    @property
    def mesh(self) -> trimesh.Trimesh:
        """
        Returns
        -------
        mesh : Mesh
            Concatenated Mesh containing all geometry from this object and its children,
            expressed in the local coordinate system of this object
        """
        if self._total_mesh is None:
            self._total_mesh = self._mesh
            for child in self._children:
                kid = child.mesh.copy()
                kid.apply_transform(child.transform.full_matrix)
                self._total_mesh += kid
        return self._total_mesh

    def glMesh(self) -> gl.GLMeshItem:
        # TODO get children to have separate colors
        mesh = gl.MeshData(vertexes=self.mesh.vertices, faces=self.mesh.faces)
        if self.color is None:
            color = (1, 1, 1, 1)
        else:
            color = np.array(self.color)
        return gl.GLMeshItem(meshdata=mesh, smooth=False, color=color, shader="shaded")

    @property
    def transform(self):
        """Transform that maps from the local coordinate system of this geometry to the parent geometry's coordinate"""
        return self._transform

    def voxel_template(self, voxel_size: float) -> Volume:
        voxels: VoxelGrid = self.mesh.voxelized(voxel_size)
        matrix = voxels.transform
        from_voxels_to_mesh = AffineTransform(
            matrix=matrix[:3, :3],
            offset=matrix[:3, 3],
            from_cs=f"Voxel centers of {self.transform.systems[0]}",
            to_cs=self.transform.systems[0],
        ) * TTransform(
            offset=(-0.5, -0.5, -0.5),
            to_cs=f"Voxel centers of {self.transform.systems[0]}",
            from_cs=f"Voxels of {self.transform.systems[0]}",
        )

        return Volume(voxels.encoding.dense.T, from_voxels_to_mesh)

    # old code, but we might use urdf again someday
    # def _urdf_visuals(self):
    #     from pymp import Planner
    #     import hppfcl
    #
    #     urdf: str = self._config
    #     srdf = f"{urdf[:-5]}.srdf"
    #     end_effector = ET.parse(srdf).getroot().find("end_effector").attrib["name"]
    #     joints = [j.attrib["name"] for j in ET.parse(urdf).getroot().findall("joint") if j.attrib["type"] != "fixed"]
    #     planner = Planner(urdf, joints, end_effector, srdf)
    #     objects = []
    #     for obj in planner.scene.collision_model.geometryObjects:
    #         geom = obj.geometry
    #         if isinstance(geom, hppfcl.Cylinder):
    #             conf = {
    #                 "type": "cylinder",
    #                 "radius": geom.radius,
    #                 "height": 2.0 * geom.halfLength,
    #                 "close_top": True,
    #                 "close_bottom": True,
    #             }
    #         elif isinstance(geom, hppfcl.Cone):
    #             conf = {
    #                 "type": "cone",
    #                 "bottom_radius": geom.radius,
    #                 "top_radius": 0,
    #                 "height": 2.0 * geom.halfLength,
    #                 "close_bottom": True,
    #             }
    #         elif isinstance(geom, hppfcl.Box):
    #             conf = {"type": "box", "size": 2.0 * geom.halfSide}
    #         else:
    #             raise ValueError(f"Unsupported geometry type: {type(geom)}")
    #         xform = np.dot(
    #             np.array(planner.scene.model.jointPlacements[obj.parentJoint]),
    #             np.array(obj.placement),
    #         )
    #         conf["transform"] = Qt.QtGui.QMatrix4x4(xform.reshape((-1,)))
    #         objects.append({obj.name: conf})
    #
    #     root = objects.pop(0)
    #     last = root
    #     while objects:
    #         obj = objects.pop(0)
    #         list(last.values())[0].setdefault("children", {}).update(obj)
    #         last = obj
    #     return []

    @staticmethod
    def make_box(args) -> trimesh.Trimesh:
        return trimesh.creation.box(args.pop("size"))

    @staticmethod
    def make_cone(args) -> trimesh.Trimesh:
        points, faces = truncated_cone(
            bottom_radius=args.pop("bottom_radius"),
            top_radius=args.pop("top_radius"),
            height=args.pop("height"),
            close_top=args.pop("close_top", False),
            close_bottom=args.pop("close_bottom", False),
            segments=args.pop("segments", 32),
        )
        return trimesh.Trimesh(points, faces)

    def make_cylinder(self, args):
        args["bottom_radius"] = args["top_radius"] = args.pop("radius")
        return self.make_cone(args)

    def contains(self, point, padding=None) -> bool:
        if padding is not None:
            for ax in range(3):
                for sign in (-1, 1):
                    adjustment = np.zeros(3)
                    adjustment[ax] = sign * padding
                    if self.contains(point + adjustment):
                        return True
        bounds = self.mesh.bounds
        return np.all(bounds[0] <= point) and np.all(point <= bounds[1])

    def transformed_to(self, other_transform, from_self_to_other):
        """
        Return a new Geometry that is a transformed version of this one. The mesh will be transformed by the
        from_self_to_other transform, while the new geometry itself will have the other_transform.
        """
        vertices = from_self_to_other.map(self.mesh.vertices)
        mesh = trimesh.Trimesh(vertices=vertices, faces=self.mesh.faces)
        return Geometry(
            mesh=mesh,
            transform=other_transform,
            color=self.color,
            name=f"[{self.name} in {other_transform.systems[0]}]",
        )

    def _default_transform_args(self):
        return dict(from_cs=self.name, to_cs=self.parent_name)

    def make_convolved_voxels(
        self, other: Geometry, to_my_parent_from_other_parent: Transform, voxel_size: float
    ) -> Volume:
        """Return a Volume that represents the accessible space the other geometry could move through without a
        collision."""
        to_self_from_other = self.transform.inverse * to_my_parent_from_other_parent * other.transform
        xformed = other.transformed_to(self.transform, to_self_from_other)
        xformed_voxels = xformed.voxel_template(voxel_size)
        # extend out the voxels by one in each positive direction, to account for sub-voxel movement
        xformed_voxels.volume = np.pad(xformed_voxels.volume, 1, mode="constant")[1:, 1:, 1:]
        xformed_voxels.volume = scipy.ndimage.binary_dilation(xformed_voxels.volume, iterations=1)
        # TODO this is adding a scale=-1, but none of the transforms reflect this
        shadow = xformed_voxels.volume[::-1, ::-1, ::-1]
        other_origin = Point((0, 0, 0), other.parent_name)
        other_origin_in_my_parent = to_my_parent_from_other_parent.map(other_origin)
        other_origin_in_self = self.transform.inverse.map(other_origin_in_my_parent)
        other_origin_in_xformed_voxels = xformed_voxels.transform.inverse.map(other_origin_in_self)
        center = (np.array(shadow.T.shape) - other_origin_in_xformed_voxels - (0.5, 0.5, 0.5)).round()
        self_voxels = self.voxel_template(voxel_size)
        return self_voxels.convolve(shadow, center, f"[shadow of {xformed.name}]")


class Line:
    def __init__(self, direction, point):
        self.direction = direction / np.linalg.norm(direction)
        if np.isnan(self.direction).any():
            raise ValueError(f"Direction vector {direction} is invalid")
        self.point = point

    def __eq__(self, other: "Line") -> bool:
        epsilon = 1e-12
        cross_product = np.cross(self.direction, other.direction)
        return (
            np.linalg.norm(cross_product) < epsilon
            and np.linalg.norm(np.cross(self.direction, other.point - self.point)) < epsilon
        )

    def intersecting_point(self, other: "Line", epsilon: float = 1e-12) -> np.ndarray | None:
        """
        Find the intersection point of two 3D lines, accounting for floating point precision.

        Returns:
            The closest point between the two lines, if that's within epsilon of the lines
            intersecting. None, otherwise.
        """
        # Check if lines are parallel
        cross_product = np.cross(self.direction, other.direction)
        if np.linalg.norm(cross_product) < epsilon:
            if np.linalg.norm(np.cross(self.direction, other.point - self.point)) < epsilon:
                return self.point
            return None

        w0 = self.point - other.point

        # Coefficients for the system of equations
        a = np.dot(self.direction, self.direction)
        b = np.dot(self.direction, other.direction)
        c = np.dot(other.direction, other.direction)
        d = np.dot(self.direction, w0)
        e = np.dot(other.direction, w0)

        # Parameters for points of closest approach
        denominator = a * c - b * b
        if abs(denominator) < epsilon:
            return None

        sc = (b * e - c * d) / denominator
        tc = (a * e - b * d) / denominator

        # Find closest points on each line
        closest_point1 = self.point + sc * self.direction
        closest_point2 = other.point + tc * other.direction

        # Calculate distance between lines
        distance = np.linalg.norm(closest_point1 - closest_point2)

        # If distance is within epsilon, lines intersect
        if distance < epsilon:
            return closest_point1
        return None

    def __str__(self):
        return f"Line({self.point} -> {self.point + self.direction})"

    def __repr__(self):
        return str(self)


def are_colinear(l1, l2):
    a, b = l1
    c, d = l2
    return np.allclose(np.cross(b - a, d - c), 0, atol=1e-10) and np.allclose(np.cross(a - c, b - c), 0, atol=1e-10)


class Plane:
    @classmethod
    def wireframe(cls, *planes: "Plane", containing: np.ndarray = None) -> List[tuple[np.ndarray, np.ndarray]]:
        """Given a set of intersecting planes, assumed to form a closed volume with side-length greater than 1e-9,
        make a wireframe of that volume. Returns a list of segment endpoints. If containing is provided, the
        wireframe will only describe the innermost containing volume that includes that point.
        """
        # TODO handle containing
        lines = []
        segments = ApproxDict()
        for i, plane in enumerate(planes):
            for other in planes[i + 1 :]:
                line = plane.intersecting_line(other)
                if line is not None:
                    lines.append(line)

        for a, b, c in itertools.product(lines, lines, lines):
            if a == b or b == c or a == c:
                continue
            if (start := a.intersecting_point(b)) is not None and (end := a.intersecting_point(c)) is not None:
                if np.allclose(start, end, atol=1e-9):
                    continue
                start = tuple(start)  # tuples so we can key a dict
                end = tuple(end)
                if start not in segments.get(end, ApproxSet()):
                    segments.setdefault(start, ApproxSet()).add(end)
        return [(np.array(start), np.array(end)) for start, ends in segments.items() for end in ends]

    def __init__(self, normal, point, name=None):
        self.normal = normal / np.linalg.norm(normal)
        self.point = point
        self.name = name

    def line_intersects(self, start: np.ndarray, end: np.ndarray) -> bool:
        if self.contains_point(start) or self.contains_point(end):
            return False
        diff = end - start
        denom = np.dot(self.normal, diff)
        if denom == 0:
            return False
        t = np.dot(self.normal, self.point - start) / denom
        return 0 <= t <= 1

    def contains_point(self, pt: np.ndarray, tolerance: float = 1e-9) -> bool:
        # If the dot product is close to zero, the point is on the plane
        dot_product = np.dot(pt - self.point, self.normal)
        return abs(dot_product) < tolerance

    def distance_to_point(self, pt: np.ndarray) -> bool:
        """Return the distance from the plane to a point, where positive
        directions are in the direction of the normal."""
        return np.dot(self.normal, pt - self.point)

    def intersecting_line(self, other: "Plane") -> Line | None:
        direction = np.cross(self.normal, other.normal)
        if np.allclose(direction, 0):
            return None

        # Normalize the direction vector
        direction = direction / np.linalg.norm(direction)

        # Calculate a point on the intersection line
        n1n2 = np.dot(self.normal, other.normal)
        n1n1 = np.dot(self.normal, self.normal)
        n2n2 = np.dot(other.normal, other.normal)
        c1 = np.dot(self.normal, self.point)
        c2 = np.dot(other.normal, other.point)

        det = n1n1 * n2n2 - n1n2 * n1n2
        c1n2 = c1 * n2n2 - c2 * n1n2
        c2n1 = c2 * n1n1 - c1 * n1n2

        point = (c1n2 * self.normal + c2n1 * other.normal) / det
        return Line(direction, point)

    @property
    def coefficients(self):
        a, b, c = self.normal
        d = -np.dot(self.normal, self.point)
        return a, b, c, d

    def __str__(self):
        if self.name is not None:
            return self.name
        a, b, c, d = self.coefficients
        return f"Plane({a}x + {b}y + {c}z + {d} = 0)"

    def __repr__(self):
        return str(self)
