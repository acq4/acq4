import argparse
from pathlib import Path

import numpy as np
from scipy import ndimage
from skimage import measure
from tifffile import tifffile
import pyqtgraph as pg


def main():
    parser = argparse.ArgumentParser(description="Analyze feature strength")
    parser.add_argument("dir", type=str, help="Directory containing cell images and masks")
    parser.add_argument("--annotation-suffix", "-a", type=str, help="Suffix of annotated files", default="_seg.npy")
    args = parser.parse_args()

    data: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for annotations_path in Path(args.dir).glob(f"*{args.annotation_suffix}"):
        healthy = np.load(annotations_path, allow_pickle=True).tolist()["masks"]
        img = tifffile.imread(str(annotations_path).replace(args.annotation_suffix, ".tiff"))
        if healthy.shape != img.shape:
            raise ValueError(f"Image and mask shapes do not match for {annotations_path}")
        from cellpose import models

        model = models.Cellpose(gpu=True, model_type="cyto3")
        img_data = img[:, np.newaxis, :, 0:-2]  # add channel dimension, weird the shape
        masks_pred, flows, styles, diams = model.eval(
            [img_data],
            diameter=35,
            # niter=2000,
            channel_axis=1,
            z_axis=0,
            stitch_threshold=0.25,
        )
        mask = masks_pred[0]  # each distinct cell gets an id: 1, 2, ...
        data.append((img[..., 0:-2], healthy[..., 0:-2], mask))

    healthy: list[dict] = []
    unhealthy: list[dict] = []

    for img, annotated, mask in data:
        cell_num = 1
        while np.any(this_mask := mask == cell_num):
            features = extract_explicit_cell_features(img, mask, cell_num)
            _, is_healthy = find_healthy_overlap(annotated, this_mask)
            if is_healthy:
                healthy.append(features)
            else:
                unhealthy.append(features)
            cell_num += 1

    # plot each feature
    win = pg.GraphicsLayoutWidget(show=True)
    win.setWindowTitle("Green: healthy")
    for feat in healthy[0].keys():
        healthy_feat = np.array([d[feat] for d in healthy])
        unhealthy_feat = np.array([d[feat] for d in unhealthy])

        plot = win.addPlot(title=feat)
        plot.addItem(make_bar_graph(healthy_feat, brush=(0, 255, 0, 128)))
        plot.addItem(make_bar_graph(unhealthy_feat, brush=(255, 0, 0, 128)))
    return win


def make_bar_graph(data, brush):
    y, x = np.histogram(data, bins="auto")
    if len(data) != 0:
        y = y / len(data)
    return pg.BarGraphItem(x0=x[:-1], x1=x[1:], height=y, pen=(255, 255, 255, 128), brush=brush)


if __name__ == "__main__":
    pg.mkQApp()
    app = main()
    pg.exec()


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
