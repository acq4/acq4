import numpy as np
from numba import njit
from scipy.ndimage import map_coordinates
from tqdm import tqdm

from acq4.util.imaging.object_detection import get_cellpose_masks


def cell_centers(masks, diameter):
    for cell_num, _z, _y, _x in find_points_in_each_cell(masks, masks.max()):
        yield get_center_fast(masks, cell_num, _z, _y, _x, expected_diameter=diameter)


def detect_and_extract_normalized_neurons(img, diameter: int = 35, xy_scale: float = 0.32e-6, z_scale: float = 1e-6):
    regions = []
    masks = get_cellpose_masks(img, diameter)
    for center in tqdm(cell_centers(masks, diameter), desc="Extracting cell regions"):
        region = extract_region(img, center, xy_scale, z_scale)
        regions.append(region)
    return np.array(regions)


@njit
def get_center_fast(data, cell_num, seed_z, seed_y, seed_x, expected_diameter=35):
    z_sum, y_sum, x_sum = 0, 0, 0
    count = 0

    # Expand around the seed point
    # Using a set would be nice but numba doesn't support it
    # So we'll use a 3D boolean array just big enough
    max_size = int(expected_diameter * 5 / 3)  # A bit larger to be safe
    visited = np.zeros((max_size, max_size, max_size), dtype=np.bool_)
    to_check = np.zeros((max_size**2 * max_size, 3), dtype=np.int32)
    n_to_check = 1
    to_check[0] = [seed_z, seed_y, seed_x]
    if data[seed_z, seed_y, seed_x] != cell_num:
        raise ValueError("Seed point is not in the cell")

    while n_to_check > 0:
        z, y, x = to_check[n_to_check - 1]
        n_to_check -= 1

        if data[z, y, x] == cell_num:
            z_sum += z
            y_sum += y
            x_sum += x
            count += 1

            # Add neighbors if in bounds and not visited
            for dz in (-1, 0, 1):
                nz = z + dz
                if nz < 0 or nz >= data.shape[0]:
                    continue
                for dy in (-1, 0, 1):
                    ny = y + dy
                    if ny < 0 or ny >= data.shape[1]:
                        continue
                    for dx in (-1, 0, 1):
                        nx = x + dx
                        if nx < 0 or nx >= data.shape[2]:
                            continue

                        # Convert to local coordinates for visited array
                        local_z = nz - seed_z + max_size // 2
                        local_y = ny - seed_y + max_size // 2
                        local_x = nx - seed_x + max_size // 2

                        if (
                            0 <= local_z < max_size
                            and 0 <= local_y < max_size
                            and 0 <= local_x < max_size
                            and not visited[local_z, local_y, local_x]
                        ):
                            visited[local_z, local_y, local_x] = True
                            to_check[n_to_check] = [nz, ny, nx]
                            n_to_check += 1

    return np.array([z_sum // count, y_sum // count, x_sum // count])


@njit
def find_points_in_each_cell(mask, max_cells=1000):
    # Dict-like structure: [cell_num, z, y, x]

    seeds = np.zeros((max_cells, 4), dtype=np.int32)
    n_seeds = 0
    found_cells = np.zeros(max_cells, dtype=np.int32)

    xy_step = 15
    z_step = 3
    for z in range(0, mask.shape[0], z_step):
        for y in range(0, mask.shape[1], xy_step):
            for x in range(0, mask.shape[2], xy_step):
                if n_seeds >= max_cells:
                    return seeds
                val = mask[z, y, x]
                if val > 0 and found_cells[val] == 0:
                    n_seeds += 1
                    seeds[n_seeds - 1] = [val, z, y, x]
                    found_cells[val] = n_seeds

    return seeds[:n_seeds]  # Return just the filled portion


def create_coordinate_grids(input_xy_resolution, input_z_resolution):
    """Pre-compute the coordinate grids (only needs to be done once)"""
    # Define the output dimensions
    z_out = np.linspace(-2, 2, 5)  # 5 z-layers centered at 0
    y_out = np.linspace(-31, 31, 63)  # 63 pixels centered at 0
    x_out = np.linspace(-31, 31, 63)  # 63 pixels centered at 0

    # Create meshgrid for output coordinates
    Z_out, Y_out, X_out = np.meshgrid(z_out, y_out, x_out, indexing="ij")

    # Scale output coordinates to input pixel space (without center offset)
    Z_scales = Z_out * input_z_resolution
    Y_scales = Y_out * input_xy_resolution
    X_scales = X_out * input_xy_resolution

    return Z_scales, Y_scales, X_scales


@njit
def fast_pad(data, pad_width):
    """Faster padding implementation using Numba"""
    padded_shape = (
        data.shape[0] + pad_width[0][0] + pad_width[0][1],
        data.shape[1] + pad_width[1][0] + pad_width[1][1],
        data.shape[2] + pad_width[2][0] + pad_width[2][1],
    )
    padded_data = np.zeros(padded_shape, dtype=data.dtype)

    # Copy the data into the padded array
    z_start, y_start, x_start = pad_width[0][0], pad_width[1][0], pad_width[2][0]
    padded_data[
        z_start : z_start + data.shape[0], y_start : y_start + data.shape[1], x_start : x_start + data.shape[2]
    ] = data

    return padded_data


def extract_region_optimized(data: np.ndarray, center_coords, Z_scales, Y_scales, X_scales):
    """
    Extract a padded, normalized 20µm cube of data around specified center coordinates.

    Args:
        data (np.ndarray): Input 3D array in Z-Y-X order
        center_coords (tuple): (z, y, x) coordinates in idx space
        Z_scales, Y_scales, X_scales: Pre-computed coordinate scaling grids

    Returns:
        np.ndarray: Normalized chunk of shape (5, 63, 63)
    """
    # pixel coordinates
    z_px, y_px, x_px = center_coords

    # Add center offsets to pre-computed scales
    Z_in = Z_scales + z_px
    Y_in = Y_scales + y_px
    X_in = X_scales + x_px

    # Calculate required padding
    z_min, z_max = int(np.floor(Z_in.min())), int(np.ceil(Z_in.max()))
    y_min, y_max = int(np.floor(Y_in.min())), int(np.ceil(Y_in.max()))
    x_min, x_max = int(np.floor(X_in.min())), int(np.ceil(X_in.max()))

    if (
        z_min >= 0
        and z_max < data.shape[0]
        and y_min >= 0
        and y_max < data.shape[1]
        and x_min >= 0
        and x_max < data.shape[2]
    ):
        # if we're fully inside the data, use direct array indexing
        coords = np.stack([Z_in.ravel(), Y_in.ravel(), X_in.ravel()], axis=0)
    else:
        pad_width = (
            (max(0, -z_min), max(0, z_max - data.shape[0] + 1)),
            (max(0, -y_min), max(0, y_max - data.shape[1] + 1)),
            (max(0, -x_min), max(0, x_max - data.shape[2] + 1)),
        )

        # Only pad if necessary
        if any(p[0] > 0 or p[1] > 0 for p in pad_width):
            data = fast_pad(data, pad_width)

            # Adjust coordinates for padded array
            Z_in_pad = Z_in + pad_width[0][0]
            Y_in_pad = Y_in + pad_width[1][0]
            X_in_pad = X_in + pad_width[2][0]

            # Use map_coordinates for faster interpolation
            coords = np.stack([Z_in_pad.ravel(), Y_in_pad.ravel(), X_in_pad.ravel()], axis=0)
        else:
            # Use map_coordinates directly on the data without padding
            coords = np.stack([Z_in.ravel(), Y_in.ravel(), X_in.ravel()], axis=0)

    result = map_coordinates(data, coords, order=1, mode="constant")
    # Normalize to [0,1] range
    _min = result.min()
    _max = result.max()
    if _min == _max:
        result = result.astype(np.float32) - _min
    else:
        result = (result - _min) / (_max - _min)
    return result.astype(np.float32).reshape((1, 5, 63, 63))  # Add channel dimension


def setup_extractor(input_xy_resolution, input_z_resolution):
    """Setup function that returns a faster extraction function"""
    Z_scales, Y_scales, X_scales = create_coordinate_grids(input_xy_resolution, input_z_resolution)

    def extract_region_fast(data, center_coords):
        return extract_region_optimized(data, center_coords, Z_scales, Y_scales, X_scales)

    return extract_region_fast


region_extractors = {}


def extract_region(data, center_coords, input_xy_resolution, input_z_resolution):
    global region_extractors

    key = (input_xy_resolution, input_z_resolution)
    if key not in region_extractors:
        region_extractors[key] = setup_extractor(input_xy_resolution, input_z_resolution)
    return region_extractors[key](data, center_coords)
