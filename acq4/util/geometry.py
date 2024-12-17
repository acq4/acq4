from __future__ import annotations

from copy import deepcopy
from functools import reduce
from typing import List, Tuple, Callable, Optional, Dict
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from coorx import SRT3DTransform, BaseTransform, NullTransform, TTransform
from trimesh.voxel import VoxelGrid
from vispy import scene
from vispy.scene import visuals
from vispy.visuals.transforms import MatrixTransform, ChainTransform

from acq4.util import Qt
from pyqtgraph import SRTTransform3D
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


def line_intersects_voxel(start, end, vox):
    # TODO as an optimization later, we can check for intersections with arbitrary bounding boxes, not just voxels
    direction = (end - start) / np.linalg.norm(end - start)
    for ax in (0, 1, 2):
        if direction[ax] == 0:
            continue
        ax2 = (ax + 1) % 3
        ax3 = (ax + 2) % 3
        x_steps = np.arange(np.ceil(min(start[ax], end[ax])), np.floor(max(start[ax], end[ax])) + 1).astype(int)
        for x in x_steps:
            t = (x - start[ax]) / direction[ax]
            y = int(np.floor(start[ax2] + t * direction[ax2]))
            z = int(np.floor(start[ax3] + t * direction[ax3]))
            index = [None, None, None]
            index[ax] = x
            index[ax2] = y
            index[ax3] = z
            if tuple(vox) == tuple(index):
                return True
            index[ax] -= 1
            if tuple(vox) == tuple(index):
                return True
    return False


def find_intersected_voxels(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> List[Tuple[int, int, int]]:
    """
    Find all voxels intersected by a line segment.

    Parameters:
    - line_start: Start point of the line segment
    - line_end: End point of the line segment
    - voxel_size: Size of each voxel

    Returns:
    - List of voxel coordinates intersected by the line
    """
    # Compute bounding box of the line
    min_point = np.minimum(line_start, line_end)
    max_point = np.maximum(line_start, line_end)

    # Determine voxel range
    start_voxel = np.floor(min_point).astype(int)
    start_voxel = np.maximum(start_voxel, 0)
    end_voxel = np.floor(max_point).astype(int)
    end_voxel = np.minimum(end_voxel, voxel_space_max)

    return [
        (x, y, z)
        for x in range(start_voxel[0], end_voxel[0] + 1)
        for y in range(start_voxel[1], end_voxel[1] + 1)
        for z in range(start_voxel[2], end_voxel[2] + 1)
        if line_intersects_voxel(line_start, line_end, np.array([x, y, z]))
    ]


def reconstruct_path(came_from, current):
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]


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
    # Normalize bias direction
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
    heuristic=None,
    neighbors=None,
    max_cost=2000,
    callback=None,
):
    """Run the A* algorithm to find the shortest path between *start* and *finish*."""
    if heuristic is None:

        def heuristic(x, y):
            return np.linalg.norm(y - x)

    if neighbors is None:
        radius = np.linalg.norm(finish - start) / 10
        count = 10

        def neighbors(pt):
            points = generate_biased_sphere_points(count, radius, finish - pt, concentration=0.2)
            points += pt
            return np.vstack((points, finish))

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
                return None
            neigh_key = tuple(neighbor)
            tentative_g_score = g_score[curr_key] + edge_cost(current, neighbor)
            if neigh_key not in g_score or tentative_g_score < g_score[neigh_key]:
                came_from[neigh_key] = curr_key
                g_score[neigh_key] = tentative_g_score
                f_score[neigh_key] = tentative_g_score + 2 * heuristic(neighbor, finish)
                if f_score[neigh_key] < np.inf and neigh_key not in open_set:
                    open_set[neigh_key] = neighbor
            if callback is not None:
                callback(reconstruct_path(came_from, neigh_key)[::-1])

    return None


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
    def __init__(self, geometries: Dict[Geometry, BaseTransform], resolution: float = 500 * µm):
        """
        Parameters
        ----------
        geometries : Dict[Geometry, BaseTrasnform]
            Dictionary of Geometry instances representing all collision objects in the world and the transform that
            respectively takes them to the global coordinate system.
        resolution : float
            Resolution of the voxel grid used for path planning.
        """
        self.geometries = geometries
        self.resolution = resolution
        self._viz = None

    def find_path(self, traveling_object: Geometry, from_traveler_to_global: BaseTransform, start, stop, callback=None):
        """
        Return a path from *start* to *stop* in the global coordinate system that *traveling_object* can follow to avoid
        collisions.

        Returns
        -------
        path : list
            List of global positions to get from start to stop

        Method:
        1. Create voxelized representations of traveling_object in the coordinate systems of all other geometries
             traveling_object.voxelize (in coordinate system of traveling_object)
             take mirror image of volume; this becomes the convolution kernel
             the center of the kernel needs to be mirrored as well
        2. Create convolutions between all other geometries and traveling_object
             geometry.voxelize (in local coordinate system)
             volume.convolve(geometry_voxels, traveling_kernel)
        3. Do a path-finding algorithm that, at each step, checks for collisions among all convolved volumes
             A*
             volume.check_edge_collision
        """
        # vol = traveling_object.voxel_template(self.resolution)
        # kernel = vol.volume[::-1, ::-1, ::-1]
        # center = vol.transform.map(np.array([0, 0, 0])) * -1
        obstacles = []
        for geom in self.geometries:
            if geom is not traveling_object:
                from_obj_to_geom = self.geometries[geom]
                from_self_to_other = (
                    traveling_object.transform * from_traveler_to_global * from_obj_to_geom * geom.transform.inverse
                )
                xformed = traveling_object.transformed_to(
                    geom.transform, from_self_to_other, f"{traveling_object.name}_in_{geom.name}"
                )
                kernel = xformed.voxel_template(self.resolution).volume[::-1, ::-1, ::-1]
                center = xformed.transform.map(np.array([0, 0, 0])) * -1
                obstacles.append(geom.voxel_template(self.resolution).convolve(kernel, center))

        def edge_cost(a, b):
            for obj in obstacles:
                if obj.intersects_line(from_traveler_to_global.inverse.map(a), from_traveler_to_global.inverse.map(b)):
                    return np.inf
            return np.linalg.norm(b - a)

        path = a_star_ish(start, stop, edge_cost, callback=callback)
        if path is None:
            return None
        return simplify_path(path, edge_cost)[1:]

    def visualize(self, traveling_object, start, stop):
        if self._viz is not None:
            self._viz.close()

        self._viz = scene.SceneCanvas(keys="interactive", show=True)
        self._viz.native.show()

        view = self._viz.central_widget.add_view()
        view.camera = "turntable"

        grid = visuals.GridLines()
        view.add(grid)

        axis = visuals.XYZAxis(parent=view.scene)
        axis.set_transform("st", scale=(10e-3, 10e-3, 10e-3))

        start_target = scene.visuals.Sphere(radius=100 * µm, color="blue", parent=view.scene)
        start_target.transform = scene.transforms.STTransform(translate=start)
        dest_target = scene.visuals.Sphere(radius=100 * µm, color="green", parent=view.scene)
        dest_target.transform = scene.transforms.STTransform(translate=stop)

        vol = traveling_object.voxel_template(self.resolution)
        kernel = vol.volume[::-1, ::-1, ::-1]
        center = vol.transform.map(np.array([0, 0, 0])) * -1
        for geom, to_global in self.geometries.items():
            obstacle = geom.voxel_template(self.resolution).convolve(kernel, center)
            viz = scene.visuals.Volume(obstacle.volume.astype("float32"), parent=view.scene)
            viz.transform = obstacle.transform.to_vispy()


class Volume(object):
    """
    A volumetric representation of Geometry

    Parameters
    ----------
    volume : ndarray
        3D boolean array containing voxelized geometry
    transform : coorx.BaseTransform
        Transform that maps from the local coordinate system of this volume (i.e. voxel coordinates) to the parent
        geometry's coordinate system.
    """

    def __init__(self, volume: np.ndarray, transform: BaseTransform):
        self.volume = volume
        self.transform: BaseTransform = transform

    @property
    def inverse_transform(self):
        """The transform that maps from the parent geometry's coordinate system to the local coordinate system."""
        return self.transform.inverse

    def convolve(self, kernel_array, center) -> Volume:
        """
        Return a new Volume that contains the convolution of self with *kernel_array*

        Parameters
        ----------
        kernel_array : ndarray
            Voxel array to convolve with, already transformed to match the rotation of self
        center : array-like
            Position of the "center" point relative to the kernel. This is added to the resulting Volume's transform.
        """
        # dest = scipy.signal.convolve(self.volume.astype(int), kernel_array.astype(int), mode="valid").astype(bool)
        dest = np.zeros_like(self.volume, dtype=bool)
        dest = np.pad(dest, [(0, d - 1) for d in kernel_array.shape], constant_values=False)
        for x in range(self.volume.shape[0]):
            for y in range(self.volume.shape[1]):
                for z in range(self.volume.shape[2]):
                    if self.volume[x, y, z]:
                        dest[
                            x : x + kernel_array.shape[0],
                            y : y + kernel_array.shape[1],
                            z : z + kernel_array.shape[2],
                        ] |= kernel_array
        first_nonzero_x = np.argmax(np.any(dest, axis=(1, 2)))
        last_nonzero_x = dest.shape[0] - np.argmax(np.any(dest[::-1], axis=(1, 2)))
        first_nonzero_y = np.argmax(np.any(dest, axis=(0, 2)))
        last_nonzero_y = dest.shape[1] - np.argmax(np.any(dest[:, ::-1], axis=(0, 2)))
        first_nonzero_z = np.argmax(np.any(dest, axis=(0, 1)))
        last_nonzero_z = dest.shape[2] - np.argmax(np.any(dest[:, :, ::-1], axis=(0, 1)))
        dest = dest[
            first_nonzero_x:last_nonzero_x,
            first_nonzero_y:last_nonzero_y,
            first_nonzero_z:last_nonzero_z,
        ]
        center = np.array(center) - np.array([first_nonzero_x, first_nonzero_y, first_nonzero_z])
        draw_xform = TTransform(offset=center)
        return Volume(dest, self.transform * draw_xform)

    def intersects_line(self, a, b):
        indexes = find_intersected_voxels(self.transform.map(a), self.transform.map(b), np.array(self.volume.shape) - 1)
        return next((True for x, y, z in indexes if self.volume[x, y, z]), False)


class Geometry:
    def __init__(
        self,
        config: Dict = None,
        name: str = "geometry",
        mesh: trimesh.Trimesh = None,
        transform: BaseTransform = None,
        color=None,
    ):
        """Create a geometry either from a configuration (see parse_config) or from an existing mesh and transform."""
        self.color = color
        self.name = name
        self._config = config
        self._children: List[Geometry] = []
        if mesh is None:
            self._mesh: trimesh.Trimesh = trimesh.Trimesh()
            self._total_mesh: Optional[trimesh.Trimesh] = None
        else:
            self._mesh = self._total_mesh = mesh
        # maps from local coordinate system of geometry (the coordinates in which mesh vertices are specified) to parent
        self._transform: BaseTransform = transform or NullTransform()
        if config is not None:
            self.parse_config()

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
        self._transform = SRT3DTransform(**xform)

        self._children = []
        for name, child_config in config.pop("children", {}).items():
            if "color" not in child_config:
                child_config["color"] = self.color
            child = Geometry(child_config, name)
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
            self._total_mesh = reduce(lambda m, o: m + o, [child.mesh for child in self._children], self._mesh)
        return self._total_mesh

    @property
    def transform(self):
        """Transform that maps from the local coordinate system of this geometry to the parent geometry's coordinate"""
        return self._transform

    def voxel_template(self, resolution: float) -> Volume:
        bounds = self.mesh.bounds
        # this xform will map from voxels to geometry
        drawing_xform = SRT3DTransform(
            scale=np.ones((3,)) * resolution, offset=np.array(bounds[0])
        )  # TODO i don't trust this
        obstacle: VoxelGrid = self.mesh.voxelized(resolution)  # TODO this is slow
        return Volume(obstacle.encoding.dense.T, drawing_xform)

    def visuals(self) -> list:
        """Return a 3D model to be displayed in the 3D visualization window."""

        if isinstance(self._config, str):
            return self._urdf_visuals()
        elif self._config is not None:
            args = deepcopy(self._config)
            args.pop("children", {})
            args.setdefault("name", "geometry")
            objects = []
            parent = None
            if "type" in args:
                parent = _VISUALS[args.pop("type")](**args)
                objects.append(parent)
            for kid in self._children:
                for kid_viz in kid.visuals():
                    if parent is not None:
                        kid_viz.mesh.parent = parent.mesh
                    objects.append(kid_viz)
            return objects
        elif self.mesh is not None:
            vertices = self.mesh.vertices
            faces = self.mesh.faces
            mesh = visuals.Mesh(vertices=vertices, faces=faces, color=self.color, shading="smooth")
            mesh.transform = self.transform.to_vispy()
            return [mesh]
        return []

    def _urdf_visuals(self):
        from pymp import Planner
        import hppfcl

        urdf = self._config
        srdf = f"{urdf[:-5]}.srdf"
        end_effector = ET.parse(srdf).getroot().find("end_effector").attrib["name"]
        joints = [j.attrib["name"] for j in ET.parse(urdf).getroot().findall("joint") if j.attrib["type"] != "fixed"]
        planner = Planner(urdf, joints, end_effector, srdf)
        objects = []
        for obj in planner.scene.collision_model.geometryObjects:
            geom = obj.geometry
            if isinstance(geom, hppfcl.Cylinder):
                conf = {
                    "type": "cylinder",
                    "radius": geom.radius,
                    "height": 2.0 * geom.halfLength,
                    "close_top": True,
                    "close_bottom": True,
                }
            elif isinstance(geom, hppfcl.Cone):
                conf = {
                    "type": "cone",
                    "bottom_radius": geom.radius,
                    "top_radius": 0,
                    "height": 2.0 * geom.halfLength,
                    "close_bottom": True,
                }
            elif isinstance(geom, hppfcl.Box):
                conf = {"type": "box", "size": 2.0 * geom.halfSide}
            else:
                raise ValueError(f"Unsupported geometry type: {type(geom)}")
            xform = np.dot(
                np.array(planner.scene.model.jointPlacements[obj.parentJoint]),
                np.array(obj.placement),
            )
            conf["transform"] = Qt.QtGui.QMatrix4x4(xform.reshape((-1,)))
            objects.append({obj.name: conf})

        root = objects.pop(0)
        last = root
        while objects:
            obj = objects.pop(0)
            list(last.values())[0].setdefault("children", {}).update(obj)
            last = obj
        # TODO wrong structure now
        return []

    def make_box(self, args) -> trimesh.Trimesh:
        return trimesh.creation.box(args.pop("size"))

    def make_cone(self, args) -> trimesh.Trimesh:
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

    def transformed_to(self, other_transform, from_self_to_other, name):
        """
        Return a new Geometry that is a transformed version of this one. The mesh will be transformed by the
        from_self_to_other transform, while the new geometry itself will have the other_transform.
        """
        mesh = self.mesh.copy()
        mesh.apply_transform(from_self_to_other.full_matrix.T)
        return Geometry(mesh=mesh, transform=other_transform, name=name, color=self.color)


class Visual(Qt.QObject):
    def __init__(self, transform=None):
        super().__init__()
        self.drawingTransform = MatrixTransform(SRTTransform3D(transform).matrix().T)
        self._deviceTransform = MatrixTransform()

    def handleTransformUpdate(self, dev, _):
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
