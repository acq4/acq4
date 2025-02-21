import argparse

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from scipy import ndimage
from skimage import measure
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, f1_score
from torch.utils.data import Dataset
from scipy.interpolate import RegularGridInterpolator


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


def extract_region(data, center_coords, input_xy_resolution, input_z_resolution):
    """
    Extract a normalized chunk of data around specified center coordinates.

    Args:
        data (np.ndarray): Input 3D array in Z-Y-X order
        center_coords (tuple): (z, y, x) coordinates in µm
        input_xy_resolution (float): Input resolution in µm/pixel for X-Y plane
        input_z_resolution (float): Input resolution in µm/step for Z dimension

    Returns:
        np.ndarray: Normalized chunk of shape (5, 63, 63)
    """
    # Convert physical coordinates to pixel coordinates
    z_px, y_px, x_px = (
        center_coords[0] / input_z_resolution,
        center_coords[1] / input_xy_resolution,
        center_coords[2] / input_xy_resolution,
    )

    # Define the output dimensions
    output_shape = (5, 63, 63)  # Z, Y, X

    # Calculate pixel ranges for output
    z_out = np.linspace(-2, 2, 5)  # 5 z-layers centered at 0
    y_out = np.linspace(-31, 31, 63)  # 63 pixels centered at 0
    x_out = np.linspace(-31, 31, 63)  # 63 pixels centered at 0

    # Create meshgrid for output coordinates
    Z_out, Y_out, X_out = np.meshgrid(z_out, y_out, x_out, indexing="ij")

    # Scale output coordinates to input pixel space
    Z_in = Z_out + z_px
    Y_in = Y_out + y_px
    X_in = X_out + x_px

    # Calculate required padding
    z_min, z_max = int(np.floor(Z_in.min())), int(np.ceil(Z_in.max()))
    y_min, y_max = int(np.floor(Y_in.min())), int(np.ceil(Y_in.max()))
    x_min, x_max = int(np.floor(X_in.min())), int(np.ceil(X_in.max()))

    pad_width = [
        [max(0, -z_min), max(0, z_max - data.shape[0] + 1)],
        [max(0, -y_min), max(0, y_max - data.shape[1] + 1)],
        [max(0, -x_min), max(0, x_max - data.shape[2] + 1)],
    ]

    # Pad data with zeros
    padded_data = np.pad(data, pad_width, mode="constant", constant_values=0)

    # Adjust coordinates for padded array
    Z_in_pad = Z_in + pad_width[0][0]  # Shift by padding amount
    Y_in_pad = Y_in + pad_width[1][0]
    X_in_pad = X_in + pad_width[2][0]

    # Create interpolator with padded data
    z_coords = np.arange(padded_data.shape[0])
    y_coords = np.arange(padded_data.shape[1])
    x_coords = np.arange(padded_data.shape[2])

    interpolator = RegularGridInterpolator(
        (z_coords, y_coords, x_coords), padded_data, method="linear", bounds_error=True
    )

    # Prepare points for interpolation
    points = np.stack([Z_in_pad, Y_in_pad, X_in_pad], axis=-1)

    # Interpolate
    return interpolator(points.reshape(-1, 3)).reshape(output_shape)


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
