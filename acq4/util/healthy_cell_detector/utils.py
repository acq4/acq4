import numpy as np
from numba import njit
from scipy.ndimage import map_coordinates
from tqdm import tqdm


def detect_and_extract_normalized_neurons(img, model, diameter: int = 35, xy_scale: float = 0.32, z_scale: float = 2):
    img = img[..., 0:-2]  # weird the shape or cellpose chokes TODO: figure out how to avoid this
    img_data = img[:, np.newaxis, :, :]  # add channel dimension
    masks_pred, flows, styles, diams = model.eval(
        [img_data],  # add batch dimension
        diameter=diameter,
        channel_axis=1,
        z_axis=0,
        stitch_threshold=0.25,
    )
    mask = masks_pred[0]  # each distinct cell gets an id: 1, 2, ...
    regions = []
    for cell_num, _z, _y, _x in tqdm(find_points_in_each_cell(mask, mask.max()), desc="Extracting cell regions"):
        center = get_center_fast(mask, cell_num, _z, _y, _x, expected_diameter=diameter)
        region = extract_region(img, center, xy_scale, z_scale).astype(np.float32)
        # Normalize to [0,1] range
        _min = region.min()
        _max = region.max()
        if _min == _max:
            region = region - _min
        else:
            region = (region - _min) / (_max - _min)
        regions.append(region)
    return np.array(regions)


@njit
def get_center_fast(data, cell_num, seed_z, seed_y, seed_x, expected_diameter=35):
    # Start with sparse search - step size of 4 in each dimension
    z_sum, y_sum, x_sum = 0, 0, 0
    count = 0

    # Now expand around the seed point
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

    # Early return check - if we're fully inside the data, use direct array indexing
    if (
        z_min >= 0
        and z_max < data.shape[0]
        and y_min >= 0
        and y_max < data.shape[1]
        and x_min >= 0
        and x_max < data.shape[2]
    ):
        # Use map_coordinates directly on the data without padding
        coords = np.stack([Z_in.ravel(), Y_in.ravel(), X_in.ravel()], axis=0)
        result = map_coordinates(data, coords, order=1, mode="constant")
        return result.reshape((5, 63, 63))

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
    return result.reshape((5, 63, 63))


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
