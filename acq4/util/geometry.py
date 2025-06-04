from __future__ import annotations

import itertools
from functools import cached_property
from threading import RLock
from typing import List, Callable, Optional, Dict, Any, Generator, Tuple

import numba
import numpy as np
import trimesh
from trimesh.voxel import VoxelGrid

import pyqtgraph as pg
import pyqtgraph.opengl as gl
from acq4.util.approx import ApproxDict, ApproxSet
from coorx import SRT3DTransform, Transform, NullTransform, TTransform, Point, AffineTransform
from pyqtgraph import debug
from pyqtgraph.debug import Profiler
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


@numba.jit(nopython=True, nogil=True)
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


def find_intersected_voxels_broadphase(line_start, line_end, voxel_space_max):
    # Create an axis-aligned bounding box for the line
    min_point = np.minimum(line_start, line_end)
    max_point = np.maximum(line_start, line_end)

    # Determine total bounds
    start_voxel = np.maximum(np.floor(min_point).astype(int), 0)
    end_voxel = np.minimum(np.ceil(max_point).astype(int), voxel_space_max)

    # Calculate simplified line equation: p = start + t * (end - start)
    direction = line_end - line_start

    # Use plane-sweeping technique:
    # For each plane perpendicular to longest axis, find intersecting voxels
    main_axis = np.argmax(np.abs(direction))

    # If the line is nearly vertical along the axis
    if abs(direction[main_axis]) < 1e-10:
        # Just check voxels along the line
        for x in range(start_voxel[0], end_voxel[0] + 1):
            for y in range(start_voxel[1], end_voxel[1] + 1):
                for z in range(start_voxel[2], end_voxel[2] + 1):
                    if line_intersects_voxel(line_start, line_end, np.array([x, y, z])):
                        yield (x, y, z)
        return

    # For each slice along main axis
    for slice_pos in range(start_voxel[main_axis], end_voxel[main_axis] + 1):
        # Find where line intersects this slice
        t = (slice_pos - line_start[main_axis]) / direction[main_axis]

        # Skip if this slice is outside line segment
        if t < 0 or t > 1:
            continue

        # Find intersection point with this slice
        intersection = line_start + t * direction

        # Only check voxels near the intersection point
        intersection_voxel = np.floor(intersection).astype(int)

        # Check a small neighborhood (3x3) around intersection point
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                for dz in range(-1, 2):
                    voxel = intersection_voxel + np.array([dx, dy, dz])

                    # Skip out-of-bounds voxels
                    if np.any(voxel < 0) or np.any(voxel > voxel_space_max):
                        continue

                    # Use existing intersection test for correctness
                    if line_intersects_voxel(line_start, line_end, voxel):
                        yield tuple(voxel)


def find_intersected_voxels_3ddda(line_start, line_end, voxel_space_max):
    # Initialize current voxel at start position
    current_voxel = np.floor(line_start).astype(int)

    # Direction and delta distances
    direction = line_end - line_start
    length = np.linalg.norm(direction)

    # Normalized direction
    if length > 1e-10:
        direction = direction / length
    else:
        # Just yield the start voxel if line is very short
        yield tuple(np.clip(current_voxel, 0, voxel_space_max))
        return

    # Step direction for each axis
    step = np.sign(direction).astype(int)

    # Calculate t values for next voxel boundaries
    next_boundary = current_voxel + np.maximum(step, 0)
    t_max = np.divide(next_boundary - line_start, direction, where=abs(direction) > 1e-10, out=np.full(3, np.inf))

    # Delta t for moving one voxel along each axis
    delta_t = np.divide(step, direction, where=abs(direction) > 1e-10, out=np.full(3, np.inf))

    # Traverse voxels until we reach end
    remaining_length = length

    while remaining_length > 0:
        # Yield current voxel if in bounds
        if np.all(current_voxel >= 0) and np.all(current_voxel <= voxel_space_max):
            # Verify intersection with existing function for correctness
            if line_intersects_voxel(line_start, line_end, current_voxel):
                yield tuple(current_voxel)

        # Find closest axis boundary
        axis = np.argmin(t_max)

        # Move to next voxel
        remaining_length -= abs(delta_t[axis]) * abs(direction[axis])
        current_voxel[axis] += step[axis]
        t_max[axis] += abs(delta_t[axis])


@numba.jit(nopython=True, nogil=True)
def _compute_intersected_voxels(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> List[Tuple[int, int, int]]:
    """
    Compute all voxels intersected by a line segment with optimized bounds.
    Internal function optimized with Numba.

    Returns a list of (x, y, z) tuples representing intersected voxels.
    """
    # Compute bounding box of the line
    min_point = np.minimum(line_start, line_end)
    max_point = np.maximum(line_start, line_end)

    # Determine voxel range
    start_voxel = np.floor(min_point).astype(np.int64)
    start_voxel = np.maximum(start_voxel, 0)
    end_voxel = np.floor(max_point).astype(np.int64)
    end_voxel = np.minimum(end_voxel, voxel_space_max)

    # Direction and length
    direction = line_end - line_start
    line_length = np.sqrt(direction[0] ** 2 + direction[1] ** 2 + direction[2] ** 2)

    result = []

    # If the line is very short, use simplified approach
    if line_length < 1.0:
        for x in range(start_voxel[0], end_voxel[0] + 1):
            for y in range(start_voxel[1], end_voxel[1] + 1):
                for z in range(start_voxel[2], end_voxel[2] + 1):
                    if line_intersects_voxel(line_start, line_end, np.array([x, y, z])):
                        result.append((x, y, z))
        return result

    # Find dominant axis for optimization (axis with greatest change)
    abs_dir = np.abs(direction)
    dominant_axis = 0
    if abs_dir[1] > abs_dir[0] and abs_dir[1] > abs_dir[2]:
        dominant_axis = 1
    elif abs_dir[2] > abs_dir[0] and abs_dir[2] > abs_dir[1]:
        dominant_axis = 2

    # Other axes
    second_axis = (dominant_axis + 1) % 3
    third_axis = (dominant_axis + 2) % 3

    # For each primary position along dominant axis
    for primary in range(start_voxel[dominant_axis], end_voxel[dominant_axis] + 1):
        # Calculate where line enters and exits this slice
        if abs(direction[dominant_axis]) > 1e-10:
            # Calculate t-values where line enters/exits this slice
            t_min = (primary - line_start[dominant_axis]) / direction[dominant_axis]
            t_max = (primary + 1 - line_start[dominant_axis]) / direction[dominant_axis]

            # Ensure t_min <= t_max
            if t_min > t_max:
                t_min, t_max = t_max, t_min

            # Clip to line segment bounds
            t_min = max(0.0, t_min)
            t_max = min(1.0, t_max)

            # Calculate the points where the line enters and exits this slice
            point_min = line_start + t_min * direction
            point_max = line_start + t_max * direction

            # Calculate tighter bounds for secondary and tertiary axes in this slice
            secondary_min = int(np.floor(min(point_min[second_axis], point_max[second_axis])))
            secondary_max = int(np.floor(max(point_min[second_axis], point_max[second_axis])))
            tertiary_min = int(np.floor(min(point_min[third_axis], point_max[third_axis])))
            tertiary_max = int(np.floor(max(point_min[third_axis], point_max[third_axis])))

            # Apply global bounds constraints
            secondary_min = max(secondary_min, start_voxel[second_axis])
            secondary_max = min(secondary_max, end_voxel[second_axis])
            tertiary_min = max(tertiary_min, start_voxel[third_axis])
            tertiary_max = min(tertiary_max, end_voxel[third_axis])
        else:
            # Line is nearly parallel to the secondary-tertiary plane
            secondary_min = start_voxel[second_axis]
            secondary_max = end_voxel[second_axis]
            tertiary_min = start_voxel[third_axis]
            tertiary_max = end_voxel[third_axis]

        # Loop through the optimized secondary and tertiary bounds
        for secondary in range(secondary_min, secondary_max + 1):
            for tertiary in range(tertiary_min, tertiary_max + 1):
                # Construct voxel coordinates
                voxel = np.zeros(3, dtype=np.int64)
                voxel[dominant_axis] = primary
                voxel[second_axis] = secondary
                voxel[third_axis] = tertiary

                # Check if line intersects this voxel
                if line_intersects_voxel(line_start, line_end, voxel):
                    result.append((int(voxel[0]), int(voxel[1]), int(voxel[2])))

    return result


def find_intersected_voxels_numba(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> Generator[tuple[int, int, int], Any, None]:
    """
    Find all voxels intersected by a line segment with optimized search space.
    Uses Numba for acceleration and pre-computed bounds for secondary axes.

    Parameters:
    - line_start: Start point of the line segment
    - line_end: End point of the line segment
    - voxel_space_max: Maximum voxel coordinates in the space (assumes minimum is 0)

    Returns:
    - Generator of voxel coordinates intersected by the line
    """
    # Ensure inputs are the right type for Numba
    line_start_array = np.asarray(line_start, dtype=np.float64)
    line_end_array = np.asarray(line_end, dtype=np.float64)
    voxel_space_max_array = np.asarray(voxel_space_max, dtype=np.int64)

    # Call the internal Numba-optimized function
    intersected_voxels = _compute_intersected_voxels(line_start_array, line_end_array, voxel_space_max_array)

    # Yield the results
    for voxel in intersected_voxels:
        yield voxel


def find_intersected_voxels_supercover(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> Generator[tuple[int, int, int], Any, None]:
    """
    Find all voxels intersected by a line segment using the 3D Supercover algorithm.

    Parameters:
    - line_start: Start point of the line segment
    - line_end: End point of the line segment
    - voxel_space_max: Maximum voxel coordinates in the space (assumes minimum is 0)

    Returns:
    - Generator of voxel coordinates intersected by the line
    """
    # Initialize variables
    start = np.copy(line_start)
    end = np.copy(line_end)

    # Calculate direction and step
    direction = end - start
    step = np.sign(direction).astype(int)

    # Find absolute distances
    abs_direction = np.abs(direction)

    # Track current position
    current_voxel = np.floor(start).astype(int)

    # Handle special case: very short lines
    if np.allclose(start, end, rtol=1e-10, atol=1e-10):
        if np.all(current_voxel >= 0) and np.all(current_voxel <= voxel_space_max):
            yield tuple(current_voxel)
        return

    # Yield the starting voxel if valid
    if np.all(current_voxel >= 0) and np.all(current_voxel <= voxel_space_max):
        yield tuple(current_voxel)

    # Compute step sizes for each dimension
    # For supercover, we need to track both the voxel boundary and diagonal crossings
    tx = ty = tz = 0

    # Calculate initial tx, ty, tz values (time to next voxel boundary)
    if step[0] != 0:
        tx = (np.floor(start[0]) + max(0, step[0]) - start[0]) / direction[0]
    if step[1] != 0:
        ty = (np.floor(start[1]) + max(0, step[1]) - start[1]) / direction[1]
    if step[2] != 0:
        tz = (np.floor(start[2]) + max(0, step[2]) - start[2]) / direction[2]

    # Delta values (time to cross a whole voxel)
    delta_tx = abs(1.0 / direction[0]) if direction[0] != 0 else float("inf")
    delta_ty = abs(1.0 / direction[1]) if direction[1] != 0 else float("inf")
    delta_tz = abs(1.0 / direction[2]) if direction[2] != 0 else float("inf")

    # Length of the line segment
    line_length = np.linalg.norm(direction)
    traveled = 0

    # Main loop
    while traveled < line_length:
        # Determine which axis to step along (smallest tx, ty, or tz)
        if tx <= ty and tx <= tz:
            # Step along x axis
            current_voxel[0] += step[0]
            traveled = tx * line_length
            tx += delta_tx
        elif ty <= tx and ty <= tz:
            # Step along y axis
            current_voxel[1] += step[1]
            traveled = ty * line_length
            ty += delta_ty
        else:
            # Step along z axis
            current_voxel[2] += step[2]
            traveled = tz * line_length
            tz += delta_tz

        # If the current voxel is within bounds, yield it
        if np.all(current_voxel >= 0) and np.all(current_voxel <= voxel_space_max) and traveled <= line_length:
            # Verify with your existing function for correctness
            if line_intersects_voxel(line_start, line_end, current_voxel):
                yield tuple(current_voxel)

        # Supercover modification: Also check diagonal neighbors at boundaries
        # This ensures we don't miss any voxels the line passes through
        if np.isclose(tx, ty) or np.isclose(tx, tz) or np.isclose(ty, tz):
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    for dz in [-1, 0, 1]:
                        if dx == 0 and dy == 0 and dz == 0:
                            continue  # Skip the current voxel

                        neighbor = current_voxel + np.array([dx, dy, dz])
                        if np.all(neighbor >= 0) and np.all(neighbor <= voxel_space_max):
                            if line_intersects_voxel(line_start, line_end, neighbor):
                                yield tuple(neighbor)


def find_intersected_voxels_axial(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> Generator[tuple[int, int, int], Any, None]:
    """
    Find all voxels intersected by a line segment with optimized search space.

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

    # Get line direction for optimization
    direction = line_end - line_start
    line_length = np.linalg.norm(direction)

    # If the line is very short, just check immediate voxels
    if line_length < 1.0:
        for x in range(start_voxel[0], end_voxel[0] + 1):
            for y in range(start_voxel[1], end_voxel[1] + 1):
                for z in range(start_voxel[2], end_voxel[2] + 1):
                    if line_intersects_voxel(line_start, line_end, np.array([x, y, z])):
                        yield x, y, z
        return

    # Find dominant axis for optimization
    dominant_axis = np.argmax(np.abs(direction))
    second_axis = (dominant_axis + 1) % 3
    third_axis = (dominant_axis + 2) % 3

    # Sort voxels by distance along dominant axis for early termination possibilities
    for primary in range(start_voxel[dominant_axis], end_voxel[dominant_axis] + 1):
        # Calculate bounds for other axes at this primary position
        # This could be further optimized with more complex math
        for secondary in range(start_voxel[second_axis], end_voxel[second_axis] + 1):
            for tertiary in range(start_voxel[third_axis], end_voxel[third_axis] + 1):
                # Construct voxel coordinates based on axis ordering
                voxel = np.zeros(3, dtype=int)
                voxel[dominant_axis] = primary
                voxel[second_axis] = secondary
                voxel[third_axis] = tertiary

                # Use existing intersection test that's known to work correctly
                if line_intersects_voxel(line_start, line_end, voxel):
                    yield tuple(voxel)


@numba.njit(nogil=True)
def _line_intersects_voxel(
    line_start: np.ndarray, line_end: np.ndarray, voxel: np.ndarray, epsilon: float = 1e-6
) -> bool:
    """
    Tests if a line segment intersects with a voxel using the slab method.
    """
    # Voxel min and max bounds
    voxel_min = voxel.astype(np.float64)
    voxel_max = voxel_min + 1.0

    # Direction vector of the line
    direction = line_end - line_start

    # Initialize intersection interval to entire line
    t_enter = 0.0
    t_exit = 1.0

    # For each axis
    for i in range(3):
        # Check if line is parallel to the axis
        if np.abs(direction[i]) < epsilon:
            # Line is parallel to this axis, so check if it's within the voxel bounds
            if line_start[i] < voxel_min[i] - epsilon or line_start[i] > voxel_max[i] + epsilon:
                return False
            continue

        # Calculate intersection times with the two planes perpendicular to this axis
        t1 = (voxel_min[i] - line_start[i]) / direction[i]
        t2 = (voxel_max[i] - line_start[i]) / direction[i]

        # Ensure t1 <= t2
        if t1 > t2:
            t1, t2 = t2, t1

        # Update the overall intersection interval
        t_enter = max(t_enter, t1)
        t_exit = min(t_exit, t2)

        # If intervals don't overlap, no intersection
        if t_enter > t_exit + epsilon:
            return False

    # Check if the intersection interval is valid
    return t_exit >= 0 and t_enter <= 1


@numba.njit(nogil=True)
def _find_intersected_voxels_axial_core(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> List[Tuple[int, int, int]]:
    """
    Numba-optimized core function that returns a list of tuples.
    This maintains most of the original algorithm structure.
    """
    # Compute bounding box of the line
    min_point = np.minimum(line_start, line_end)
    max_point = np.maximum(line_start, line_end)

    # Determine voxel range - keeping your original type handling
    start_voxel = np.floor(min_point).astype(np.int64)
    start_voxel = np.maximum(start_voxel, 0)
    end_voxel = np.floor(max_point).astype(np.int64)
    end_voxel = np.minimum(end_voxel, voxel_space_max)

    # Pre-allocate a list for Numba
    result = numba.typed.List()

    # Get line direction for optimization
    direction = line_end - line_start
    line_length = np.linalg.norm(direction)

    # If the line is very short, just check immediate voxels
    if line_length < 1.0:
        for x in range(start_voxel[0], end_voxel[0] + 1):
            for y in range(start_voxel[1], end_voxel[1] + 1):
                for z in range(start_voxel[2], end_voxel[2] + 1):
                    voxel = np.array([x, y, z], dtype=np.int64)
                    if line_intersects_voxel(line_start, line_end, voxel):
                        result.append((x, y, z))
        return result

    # Find dominant axis for optimization
    dominant_axis = np.argmax(np.abs(direction))
    second_axis = (dominant_axis + 1) % 3
    third_axis = (dominant_axis + 2) % 3

    # Sort voxels by distance along dominant axis - preserving original algorithm
    for primary in range(start_voxel[dominant_axis], end_voxel[dominant_axis] + 1):
        for secondary in range(start_voxel[second_axis], end_voxel[second_axis] + 1):
            for tertiary in range(start_voxel[third_axis], end_voxel[third_axis] + 1):
                # Construct voxel coordinates based on axis ordering
                voxel = np.zeros(3, dtype=np.int64)
                voxel[dominant_axis] = primary
                voxel[second_axis] = secondary
                voxel[third_axis] = tertiary

                # Use existing intersection test
                if line_intersects_voxel(line_start, line_end, voxel):
                    result.append((int(voxel[0]), int(voxel[1]), int(voxel[2])))

    return result


def find_intersected_voxels_axial_numba(
    line_start: np.ndarray, line_end: np.ndarray, voxel_space_max: np.ndarray
) -> Generator[tuple[int, int, int], Any, None]:
    """
    Find all voxels intersected by a line segment with optimized search space.
    This maintains your original function interface.
    """
    # Call the JIT-optimized core function
    voxel_list = _find_intersected_voxels_axial_core(line_start, line_end, voxel_space_max)

    # Yield each voxel coordinate
    for voxel in voxel_list:
        yield voxel


def find_intersected_voxels_exhaustive(
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
    max_cost
        Maximum number of iterations before giving up.
    callback
        Used for debugging and visualization. Called with the current path at each iteration.
    """

    def heuristic(x, y):
        return np.linalg.norm(y - x)

    radius = np.linalg.norm(finish - start) / 5
    radius = max(radius, 100e-6)
    concentration_max = np.log(max_cost + 1)
    count = 10

    def neighbors(pt, cost_so_far):
        yield (radius * (finish - pt) / np.linalg.norm(finish - pt)) + pt
        cost_scale = np.log(1 + cost_so_far)
        concentration = max(0.2, concentration_max - (1.0 * cost_scale))
        points = generate_biased_sphere_points(count, radius**cost_scale, finish - pt, concentration)
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

        for neighbor in neighbors(current, cost):
            print(f"cost {cost}, neighbor {neighbor}")
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


def simplify_path(path, edge_cost: Callable, viz_callback: Callable | None):
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


class RRTNode:
    """Node in an RRT tree."""

    def __init__(self, position, parent=None):
        self.position = position
        self.parent = parent
        self.children = []

    def add_child(self, child):
        self.children.append(child)

    def path_to_root(self):
        """Return the path from this node to the root."""
        path = [self.position]
        node = self
        while node.parent is not None:
            node = node.parent
            path.append(node.position)
        return path[::-1]


def rrt_connect(
    start: np.ndarray,
    finish: np.ndarray,
    edge_cost: Callable,
    max_iterations: int = 2000,
    step_size: float = None,
    goal_sample_rate: float = 0.1,
    callback: Callable = None,
) -> List[np.ndarray]:
    """Find a path between *start* and *finish* using bidirectional RRT-Connect.

    Parameters
    ----------
    start
        Initial position.
    finish
        Final position.
    edge_cost
        Function that takes two points and returns the cost of moving between them.
        If the cost is np.inf, the edge is treated as impossible.
    max_iterations
        Maximum number of iterations before giving up.
    step_size
        Maximum distance to extend a branch. If None, calculated based on start-finish distance.
    goal_sample_rate
        Probability of sampling the goal position directly.
    callback
        Used for debugging and visualization. Called with the current path at each iteration.

    Returns
    -------
    path : List[np.ndarray]
        The path from start to finish, or raises ValueError if no path is found.
    """
    # Calculate step size if not provided
    if step_size is None:
        step_size = np.linalg.norm(finish - start) / 10
        step_size = max(step_size, 100e-6)  # Minimum step size

    # Initialize trees
    start_tree = {tuple(start): RRTNode(start)}
    goal_tree = {tuple(finish): RRTNode(finish)}

    # For alternating between trees
    trees = [start_tree, goal_tree]
    goals = [finish, start]

    # KD-trees for efficient nearest neighbor search
    from scipy.spatial import cKDTree

    for i in range(max_iterations):
        # Alternate between trees
        tree_idx = i % 2
        active_tree = trees[tree_idx]
        goal = goals[tree_idx]
        other_tree = trees[1 - tree_idx]

        # Sample random point (with bias toward goal)
        if np.random.random() < goal_sample_rate:
            random_point = goal
        else:
            # Sample with bias toward goal
            direction = goal - list(active_tree.values())[0].position
            distance = np.linalg.norm(direction)
            random_point = (
                generate_biased_sphere_points(1, distance * 1.5, direction, concentration=0.5)[0]
                + list(active_tree.values())[0].position
            )

        # Find nearest node in active tree
        positions = np.array([node.position for node in active_tree.values()])
        kdtree = cKDTree(positions)
        _, idx = kdtree.query(random_point)
        nearest_node = list(active_tree.values())[idx]

        # Extend tree toward random point
        direction = random_point - nearest_node.position
        distance = np.linalg.norm(direction)
        if distance > 0:
            direction = direction / distance
            new_position = nearest_node.position + min(step_size, distance) * direction

            # Check if the new edge is valid
            if edge_cost(nearest_node.position, new_position) < np.inf:
                # Add new node to tree
                new_node = RRTNode(new_position, nearest_node)
                nearest_node.add_child(new_node)
                active_tree[tuple(new_position)] = new_node

                # Check if we can connect to the other tree
                positions = np.array([node.position for node in other_tree.values()])
                if len(positions) > 0:
                    kdtree = cKDTree(positions)

                    # Handle both single and multiple nearest neighbor cases
                    k_neighbors = min(3, len(positions))
                    query_result = kdtree.query(new_position, k=k_neighbors)

                    # Unpack query results based on k value
                    if k_neighbors == 1:
                        distances = [query_result[0]]
                        indices = [query_result[1]]
                    else:
                        distances, indices = query_result

                    # Try to connect to closest nodes in other tree
                    for i in range(len(indices)):
                        dist = distances[i]
                        idx = indices[i]

                        if dist < step_size * 1.5:  # Only try to connect if reasonably close
                            connect_node = list(other_tree.values())[idx]
                            if edge_cost(new_position, connect_node.position) < np.inf:
                                # Found a path!
                                if tree_idx == 0:
                                    # Start tree to goal tree
                                    path = new_node.path_to_root() + connect_node.path_to_root()[::-1]
                                else:
                                    # Goal tree to start tree
                                    path = connect_node.path_to_root() + new_node.path_to_root()[::-1]

                                # Simplify the path
                                return simplify_path(path, edge_cost, callback)

                # Visualization callback
                if callback is not None and i < 10 or i % 10 == 0:  # Reduce callback frequency for performance
                    # Find best connection between trees for visualization
                    best_start = None
                    best_goal = None
                    best_dist = float("inf")

                    # Sample a few nodes from each tree to check connections
                    start_samples = list(active_tree.values())
                    if len(start_samples) > 10:
                        # Use a list to avoid numpy random choice issues with custom objects
                        indices = np.random.choice(len(start_samples), 10, replace=False)
                        start_samples = [start_samples[i] for i in indices]

                    goal_samples = list(other_tree.values())
                    if len(goal_samples) > 10:
                        indices = np.random.choice(len(goal_samples), 10, replace=False)
                        goal_samples = [goal_samples[i] for i in indices]

                    for s_node in start_samples:
                        for g_node in goal_samples:
                            dist = np.linalg.norm(s_node.position - g_node.position)
                            if dist < best_dist and edge_cost(s_node.position, g_node.position) < np.inf:
                                best_dist = dist
                                best_start = s_node
                                best_goal = g_node

                    if best_start is not None:
                        if tree_idx == 0:
                            vis_path = best_start.path_to_root() + best_goal.path_to_root()[::-1]
                        else:
                            vis_path = best_goal.path_to_root() + best_start.path_to_root()[::-1]
                        if callback:
                            callback(vis_path)

    raise ValueError("Pathfinding failed; no valid paths found after maximum iterations.")


def simplify_path_dp(path, edge_cost: Callable, viz_callback: Callable | None):
    if len(path) <= 3:
        return path

    # Douglas-Peucker-inspired algorithm for smoother paths
    result = [path[0]]
    i = 0
    while i < len(path) - 1:
        # Try to extend as far as possible
        for j in range(len(path) - 1, i, -1):
            if edge_cost(np.array(path[i]), np.array(path[j])) < np.inf:
                if j > i + 1:  # Skip intermediate points
                    result.append(path[j])
                    i = j
                else:
                    i += 1
                break
        else:
            # If no skip was possible, keep the next point
            i += 1
            if i < len(path):
                result.append(path[i])

    # Ensure the last point is included
    if np.any(result[-1] != path[-1]):
        result.append(path[-1])

    return result


class GeometryMotionPlanner:
    _cache = {}
    _cache_lock = RLock()

    @classmethod
    def clear_cache(cls):
        with cls._cache_lock:
            cls._cache = {}

    def __init__(self, geometries: Dict[Geometry, Transform], voxel_size: float = 200 * µm):
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

    def find_path(self, *args, **kwargs):
        if (mode := kwargs.pop("mode", "RRT Connect")) == "A*":
            return self.find_path_astar(*args, **kwargs)
        elif mode == "RRT Connect":
            return self.find_path_rrt(*args, **kwargs)
        else:
            raise ValueError(f"Invalid pathfinding mode: {mode}. Use 'A*' or 'RRT Connect'.")

    def find_path_astar(
        self,
        traveler: Geometry,
        to_global_from_traveler: Transform,
        start,
        stop,
        bounds=None,
        callback=None,
        visualizer: "VisualizePathPlan" = None,
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
        bounds : list[Plane]
            Planes that define the bounds of the space in which the path is to be found.
        visualizer : VisualizePathPlan or None
            If not None, a VisualizePathPlan to visualize the path planning process.

        Returns
        -------
        path : list
            List of global positions to get from start to stop
        """
        profile = debug.Profiler()
        start = Point(start, "global")
        stop = Point(stop, "global")
        bounds = [] if bounds is None else bounds
        if visualizer is not None:
            visualizer.startPath([start.coordinates, stop.coordinates], bounds)
        in_bounds, bound_plane = point_in_bounds(start.coordinates, bounds)
        if not in_bounds:
            raise ValueError(f"Starting point {start} is on the wrong side of the {bound_plane} boundary")
        profile.mark("basic setup")

        obstacles = self.make_convolved_obstacles(traveler, to_global_from_traveler, visualizer)
        profile.mark("made convolved obstacles")

        for i, _o in enumerate(obstacles):
            obst_volume, to_global_from_obst, obst_name = _o
            # obst = list(self.geometries.keys())[i]
            # users will sometimes drive the hardware to where the motion planner would consider things impossible
            # TODO pull pipette out along its axis to start
            # if obst_volume.contains_point(to_global_from_obst.inverse.map(start)):
            #     raise ValueError(f"Start point {start} is inside obstacle {obst.name}")
            if obst_volume.contains_point(to_global_from_obst.inverse.map(stop)):
                raise ValueError(f"Destination point {stop} is inside obstacle {obst_name}")

        profile.mark("voxelized all obstacles")

        def edge_cost(a: np.ndarray, b: np.ndarray):
            prof = Profiler(disabled=False)
            if not point_in_bounds(b, bounds)[0]:
                prof.mark("bounds check")
                return np.inf
            prof.mark("bounds check")
            a = Point(a, start.system)
            b = Point(b, start.system)
            for vol, to_global, _ in obstacles:
                intersects = vol.intersects_line(to_global.inverse.map(a), to_global.inverse.map(b))
                prof.mark(f"intersection check {to_global.systems[0].name}")
                if intersects:
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

    def find_path_rrt(
        self,
        traveler: Geometry,
        to_global_from_traveler: Transform,
        start,
        stop,
        bounds=None,
        callback=None,
        visualizer: "VisualizePathPlan" = None,
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
             RRT-Connect (bidirectional rapidly-exploring random tree)
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
        bounds : list[Plane]
            Planes that define the bounds of the space in which the path is to be found.
        visualizer : VisualizePathPlan or None
            If not None, a VisualizePathPlan to visualize the path planning process.

        Returns
        -------
        path : list
            List of global positions to get from start to stop
        """
        profile = debug.Profiler()
        start = Point(start, "global")
        stop = Point(stop, "global")
        bounds = [] if bounds is None else bounds
        if visualizer is not None:
            visualizer.startPath([start.coordinates, stop.coordinates], bounds)
        in_bounds, bound_plane = point_in_bounds(start.coordinates, bounds)
        if not in_bounds:
            raise ValueError(f"Starting point {start} is on the wrong side of the {bound_plane} boundary")
        profile.mark("basic setup")

        obstacles = self.make_convolved_obstacles(traveler, to_global_from_traveler, visualizer)
        profile.mark("made convolved obstacles")

        for i, _o in enumerate(obstacles):
            obst_volume, to_global_from_obst, obst_name = _o
            # obst = list(self.geometries.keys())[i]
            # users will sometimes drive the hardware to where the motion planner would consider things impossible
            # TODO pull pipette out along its axis to start
            # if obst_volume.contains_point(to_global_from_obst.inverse.map(start)):
            #     raise ValueError(f"Start point {start} is inside obstacle {obst.name}")
            if obst_volume.contains_point(to_global_from_obst.inverse.map(stop)):
                raise ValueError(f"Destination point {stop} is inside obstacle {obst_name}")

        profile.mark("voxelized all obstacles")

        def edge_cost_intersection(a: np.ndarray, b: np.ndarray):
            if not point_in_bounds(b, bounds)[0]:
                return np.inf
            a = Point(a, start.system)
            b = Point(b, start.system)
            for vol, to_global, _ in obstacles:
                if vol.intersects_line(to_global.inverse.map(a), to_global.inverse.map(b)):
                    return np.inf
            return np.linalg.norm(b - a)

        def edge_cost_walk(a: np.ndarray, b: np.ndarray):
            if not point_in_bounds(b, bounds)[0]:
                return np.inf
            a = Point(a, start.system)
            b = Point(b, start.system)
            edge_dist = np.linalg.norm(b - a)
            if edge_dist < self.voxel_size:
                step = b - a
                iterations = 1
            else:
                step = self.voxel_size * (b - a) / edge_dist
                iterations = int(np.ceil(edge_dist / self.voxel_size))

            curr = a
            for _ in range(iterations):
                for vol, to_global, _ in obstacles:
                    if vol.contains_point(to_global.inverse.map(curr)):
                        return np.inf
                curr = Point(curr.coordinates + step, start.system)
            return edge_dist

        # Calculate appropriate step size based on voxel size and distance
        distance = np.linalg.norm(stop.coordinates - start.coordinates)
        step_size = min(distance / 10, self.voxel_size * 5)
        step_size = max(step_size, self.voxel_size)

        # Use RRT-Connect for pathfinding
        path = rrt_connect(
            start.coordinates,
            stop.coordinates,
            edge_cost_intersection,
            max_iterations=4000,
            step_size=step_size,
            goal_sample_rate=0.2,
            callback=callback,
        )

        profile.mark("RRT-Connect")

        if callback:
            callback(path, skip=1)
        profile.finish()
        return path[1:] if len(path) > 1 else path

    def make_convolved_obstacles(self, traveler, to_global_from_traveler, visualizer=None):
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
                obst_volume = self._cache[cache_key]

            obstacles.append((obst_volume, to_global_from_obst, obst.name))
            if visualizer is not None:
                visualizer.addObstacle(obst.name, obst_volume, to_global_from_obst).raiseErrors(
                    "obstacle failed to render"
                )
        return obstacles


def point_in_bounds(point, bounds):
    """Return True if the given point is inside the given bounds.
    Also return the first plane that the point is outside of, if any."""
    for plane in bounds:
        if plane.distance_to_point(point) < 0:
            return False, plane
    return True, None


def convolve_kernel_onto_volume(volume: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    # Convert to proper types if needed
    volume_bool = volume.astype(bool)
    kernel_bool = kernel.astype(bool)

    # Get coordinates of True values
    volume_coords = np.array(np.where(volume_bool)).T
    kernel_coords = np.array(np.where(kernel_bool)).T

    # Output shape
    v_shape = volume.shape
    k_shape = kernel.shape
    out_shape = (v_shape[0] + k_shape[0] - 1, v_shape[1] + k_shape[1] - 1, v_shape[2] + k_shape[2] - 1)

    # Initialize output array
    result = np.zeros(out_shape, dtype=np.bool_)

    # For each True kernel position, add it to all True volume positions
    for kx, ky, kz in kernel_coords:
        # This creates an array of coordinates where the kernel's True position
        # is added to all True positions in the volume
        new_coords = volume_coords + np.array([kx, ky, kz])

        # Filter valid coordinates (those within bounds)
        valid_mask = np.all((new_coords >= 0) & (new_coords < out_shape), axis=1)
        valid_coords = new_coords[valid_mask]

        # Set those positions to True
        if len(valid_coords) > 0:
            result[valid_coords[:, 0], valid_coords[:, 1], valid_coords[:, 2]] = True

    return result


def convolve_kernel_onto_volume_scipy(volume: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    import scipy.signal
    return scipy.signal.convolve(volume.astype(int), kernel.astype(int), mode="full").astype(bool)


@numba.jit(nopython=True, nogil=True)
def convolve_kernel_onto_volume_numba(volume: np.ndarray, kernel: np.ndarray) -> np.ndarray:
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
        dest = convolve_kernel_onto_volume_numba(self.volume, kernel_array)
        draw_xform = TTransform(
            offset=-center,
            to_cs=self.transform.systems[0],
            from_cs=f"[convolved {name} in {self.transform.systems[1]}]",
        )
        return Volume(dest, self.transform * draw_xform)

    def intersects_line(self, a, b):
        """Return True if the line segment between *a* and *b* intersects with this volume. Points should be in the
        parent coordinate system of the volume"""
        line_voxels = find_intersected_voxels_axial(
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
        # this prevents two pipette tips from smashing into each other, but it makes it harder to deal
        # with larger objects. we can leave this commented until we start needing to handle 2 pipettes.
        # xformed_voxels.volume = np.pad(xformed_voxels.volume, 1, mode="constant")[1:, 1:, 1:]
        # xformed_voxels.volume = scipy.ndimage.binary_dilation(xformed_voxels.volume, iterations=1)
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

    def __hash__(self):
        # Normalize the direction vector
        direction_norm = np.linalg.norm(self.direction)
        if direction_norm < 1e-10:
            raise ValueError("Direction vector cannot be zero")
        unit_direction = self.direction / direction_norm

        # Compute the moment vector
        moment = np.cross(self.point, unit_direction)

        # Make the representation canonical by ensuring the
        # first non-zero component of direction is positive
        for i in range(3):
            if abs(unit_direction[i]) > 1e-10:
                if unit_direction[i] < 0:
                    unit_direction = -unit_direction
                    moment = -moment
                break

        return hash((tuple(unit_direction), tuple(moment)))

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
    def wireframe(cls, *planes: "Plane", innermost=True) -> List[tuple[np.ndarray, np.ndarray]]:
        """Given a set of intersecting planes, assumed to form a closed volume with side-length greater than 1e-9,
        make a wireframe of that volume. Returns a list of segment endpoints.
        """
        lines = set()
        segments = ApproxDict()
        for i, plane in enumerate(planes):
            for other in planes[i + 1 :]:
                line = plane.intersecting_line(other)
                if line is not None:
                    lines.add(line)

        for a, b, c in itertools.product(lines, lines, lines):
            if a == b or b == c or a == c:
                continue
            if (start := a.intersecting_point(b)) is not None and (end := a.intersecting_point(c)) is not None:
                if np.allclose(start, end, atol=1e-9):
                    continue
                if innermost and any(not p.allows_point(start) or not p.allows_point(end) for p in planes):
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

    def allows_point(self, pt: np.ndarray, tolerance=1e-9):
        """Return whether a point is on the correct side of the boundary"""
        return self.distance_to_point(pt) > -abs(tolerance)

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
