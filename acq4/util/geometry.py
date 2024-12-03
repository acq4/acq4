from __future__ import annotations

from typing import List, Tuple
from xml.etree import ElementTree as ET

import numpy as np
import trimesh
from coorx import SRT3DTransform

from acq4.util import Qt


def line_intersects_voxel(start, end, vox):
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


class Volume:
    def __init__(self, space: np.ndarray, transform: SRT3DTransform):
        self._space = space
        self._transform = transform

    def map_from_parent_to_local(self, obj):
        return self._transform.map(obj)


class Geometry:
    def __init__(self, config, defaults):
        self._config = config
        self._defaults = defaults

    def voxel_template(self, resolution: float) -> np.ndarray:
        # first determine the bounding box of the geometry
        limits = np.zeros((3, 2), dtype=float)
        for geom in self.get_geometries():
            for i in range(3):
                bounds = geom.mesh.bounds(i)
                limits[i][0] = min(limits[i][0], bounds[0])
                limits[i][1] = max(limits[i][1], bounds[1])
        space = np.zeros(np.ceil((limits[:, 1] - limits[:, 0]) / resolution).astype(int) + 1, dtype=bool)
        for geom in self.get_geometries():
            # fake device transform to fit in this space
            xform = SRT3DTransform(scale=np.ones(3) / resolution)
            geom.setDeviceTransform(xform.params)
            meshdata = geom.mesh.mesh.mesh_data  # todo ugh
            # xform = pg.SRTTransform3D({'scale': np.ones(3) / resolution})
            # geom.setDeviceTransform(xform)
            # meshdata = geom.mesh._mesh.mesh_data
            obstacle = trimesh.Trimesh(meshdata.get_vertices(), meshdata.get_faces()).voxelized(resolution)
            points = np.array([xform.map(pt) for pt in obstacle.points - limits[:, 0]])
            space[tuple(points.round().astype(int).T)] = True
        return space

    def global_path_intersects(self, path, resolution: float, traveling_object: Geometry = None) -> bool:
        """Return True if the path intersects this geometry, optionally convolving our geometry with the traveling
        object's shadow."""
        voxels = self.voxel_template(resolution)
        xform = self.base_transform(resolution)
        if traveling_object is not None:
            voxels = traveling_object.convolve_across(voxels, resolution)
            xform = traveling_object.base_transform(resolution) * xform
        path = np.array([xform.map(pt) for pt in path])
        for i in range(len(path) - 1):
            start = path[i]
            end = path[i + 1]
            for x, y, z in find_intersected_voxels(start, end, np.array(voxels.shape) - 1):  # todo shape).T?
                if voxels[x, y, z]:  # todo z, y, x?
                    return True
        return False

    def voxelize_into(self, space: np.ndarray, resolution: float, xform) -> np.ndarray:
        """Return a voxelized version of the geometry with the specified resolution."""
        for obj in self.get_geometries():
            obj.handleTransformUpdate(xform)

    def convolve_across(self, space: np.ndarray, resolution: float) -> np.ndarray:
        """For every True point in the space, insert this geometry's shadow."""
        voxels = self.voxel_template(resolution)
        dest = np.zeros_like(space)
        dest = np.pad(dest, [(0, d) for d in voxels.shape], constant_values=False)
        for x in range(space.shape[0]):
            for y in range(space.shape[1]):
                for z in range(space.shape[2]):
                    if space[x, y, z]:
                        dest[x : x + voxels.shape[0], y : y + voxels.shape[1], z : z + voxels.shape[2]] |= voxels
        return dest

    def get_geometries(self) -> list:
        """Return a 3D model to be displayed in the 3D visualization window."""
        from acq4.modules.Visualize3D import create_geometry

        if isinstance(self._config, str):
            from pymp import Planner
            import hppfcl

            urdf = self._config
            srdf = f"{urdf[:-5]}.srdf"
            end_effector = ET.parse(srdf).getroot().find("end_effector").attrib["name"]
            joints = [
                j.attrib["name"] for j in ET.parse(urdf).getroot().findall("joint") if j.attrib["type"] != "fixed"
            ]
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
            return create_geometry(defaults=self._defaults, **root)
        elif self._config:
            args = {**self._config}
            return create_geometry(defaults=self._defaults, **args)
        return []

    def base_transform(self, resolution: float) -> SRT3DTransform:
        return SRT3DTransform(scale=np.ones(3) / resolution)
