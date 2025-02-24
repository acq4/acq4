import argparse

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from numba import njit
from scipy import ndimage
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import map_coordinates
from skimage import measure
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score
from torch.utils.data import Dataset


def extract_explicit_cell_features(data: np.ndarray, mask: np.ndarray, cell_num: int) -> dict:
    """Extract features relevant for neuron health classification."""
    cell_mask = mask == cell_num
    cell_data = data * cell_mask

    # Get region properties
    props = measure.regionprops(cell_data.astype(int), intensity_image=data)[0]

    return {
        # Basic morphology
        "volume": np.sum(cell_mask),
        "surface_area": np.sum(ndimage.binary_dilation(cell_mask) ^ cell_mask),
        "sphericity": props.extent,
        # Shape complexity
        "aspect_ratio": max(
            props.major_axis_length / props.minor_axis_length if props.minor_axis_length > 0 else 1.0, 1.0
        ),
        # "solidity": props.solidity,  # Area / ConvexHull area
        # "perimeter_complexity": props.perimeter / np.cbrt(props.area),  # Scale-invariant
        # Intensity features
        "mean_intensity": props.mean_intensity,
        "intensity": props.intensity_image.reshape((-1,))[0],
        # Boundary features
        "boundary_contrast": _compute_boundary_contrast(data, cell_mask),
        "boundary_uniformity": _compute_boundary_uniformity(data, cell_mask),
    }


def _compute_boundary_contrast(data: np.ndarray, mask: np.ndarray) -> float:
    """Compute average intensity difference across cell boundary."""
    boundary = ndimage.binary_dilation(mask) ^ mask
    outer_boundary = ndimage.binary_dilation(boundary) ^ boundary

    boundary_intensity = data[boundary].mean()
    outer_intensity = data[outer_boundary].mean()

    return abs(boundary_intensity - outer_intensity)


def _compute_boundary_uniformity(data: np.ndarray, mask: np.ndarray) -> float:
    """Compute how uniform the boundary intensity is."""
    boundary = ndimage.binary_dilation(mask) ^ mask
    return data[boundary].std()


class NeuronRegionDataset(Dataset):
    def __init__(self, raw_data: np.ndarray, mask: np.ndarray, region_size=(45, 45, 20)):
        self.data = raw_data
        self.mask = mask
        self.region_size = region_size
        self.centers = self._get_cell_centers()

    def _get_cell_centers(self):
        centers = []
        cell_num = 1
        while np.any(self.mask == cell_num):
            coords = np.array(np.where(self.mask == cell_num)).mean(axis=1).astype(int)
            centers.append(coords)
            cell_num += 1
        return centers

    def __len__(self):
        return len(self.centers)

    def __getitem__(self, idx):
        center = self.centers[idx]
        half = [p // 2 for p in self.region_size]
        region = self.data[
            max(0, center[0] - half[0]) : center[0] + half[0],
            max(0, center[1] - half[1]) : center[1] + half[1],
            max(0, center[2] - half[2]) : center[2] + half[2],
        ]
        # Pad if necessary
        if region.shape != self.region_size:
            region = np.pad(region, [(0, max(0, self.region_size[i] - region.shape[i])) for i in range(3)])
        return torch.FloatTensor(region[None])  # Add channel dimension


def train_autoencoder(model, dataloader, num_epochs=50):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    optimizer = optim.Adam(model.parameters())
    criterion = nn.MSELoss()

    for epoch in range(num_epochs):
        total_loss = 0
        for batch in dataloader:
            batch = batch.to(device)
            optimizer.zero_grad()
            reconstructed, _ = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if epoch % 10 == 0:
            print(f"Epoch {epoch}, Loss: {total_loss/len(dataloader)}")


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
    z_start:z_start + data.shape[0],
    y_start:y_start + data.shape[1],
    x_start:x_start + data.shape[2]
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
    if (z_min >= 0 and z_max < data.shape[0] and
            y_min >= 0 and y_max < data.shape[1] and
            x_min >= 0 and x_max < data.shape[2]):
        # Use map_coordinates directly on the data without padding
        coords = np.stack([Z_in.ravel(), Y_in.ravel(), X_in.ravel()], axis=0)
        result = map_coordinates(data, coords, order=1, mode='constant')
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
    result = map_coordinates(data, coords, order=1, mode='constant')
    return result.reshape((5, 63, 63))


# Example usage with pre-computation
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


def match_cells_and_extract_features(raw_data, cellpose_mask, annotation_mask, model, iou_threshold=0.5):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model.eval()

    features = []
    labels = []

    cell_num = 1
    while np.any(cellpose_mask == cell_num):
        cp_mask = cellpose_mask == cell_num

        # Get cell region
        coords = np.array(np.where(cp_mask)).mean(axis=1).astype(int)
        region = extract_region(raw_data, coords)

        # Get features
        with torch.no_grad():
            region_tensor = torch.FloatTensor(region[None, None]).to(device)
            _, latent = model(region_tensor)
            features.append(latent.cpu().numpy())

        best_iou, healthy_label = find_healthy_overlap(annotation_mask, cp_mask)

        if best_iou >= iou_threshold:
            labels.append(healthy_label)

        cell_num += 1

    return np.vstack(features), np.array(labels)


def find_healthy_overlap(healthy_masks, region_of_interest):
    # Find matching annotation if any
    best_iou = 0
    is_healthy = False
    ann_num = 1
    while np.any(healthy_masks == ann_num):
        ann_mask = healthy_masks == ann_num
        intersection = np.sum(region_of_interest & ann_mask)
        union = np.sum(region_of_interest | ann_mask)
        iou = intersection / union if union > 0 else 0
        if iou > best_iou:
            best_iou = iou
            is_healthy = True
        ann_num += 1
    healthy_label = 1 if is_healthy else 0
    return best_iou, healthy_label


def build_classifier():
    # Using Random Forest with settings favoring precision
    return RandomForestClassifier(
        n_estimators=100, class_weight="balanced", max_depth=10, random_state=42  # Prevent overfitting
    )


def evaluate_classifier(y_true, y_pred):
    return {
        "precision": precision_score(y_true, y_pred),
        "recall": recall_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
    }


def main():
    parser = argparse.ArgumentParser(description="Train a classifier to detect healthy cells.")
    parser.add_argument("dir", type=str, help="Directory containing cell images and masks")
    parser.add_argument("output", type=str, help="Output file for model", default="classifier.pkl")
    parser.add_argument("--annotation-suffix", "-a", type=str, help="Suffix of annotated files", default="_seg.npy")
    parser.add_argument("--train-autoencoder", type="store_true", help="Train an autoencoder")
    parser.add_argument("--autoencoder", type=str, help="Path to autoencoder model")
    args = parser.parse_args()
    if args.train_autoencoder:
        train_autoencoder(...)
    else:
        # TODO train_classifier()
        pass


if __name__ == "__main__":
    main()
