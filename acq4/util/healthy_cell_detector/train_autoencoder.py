import argparse
from pathlib import Path
from typing import Optional, List

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tifffile import tifffile
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm

from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
from acq4.util.healthy_cell_detector.train import extract_region


class NeuronDataset(Dataset):
    def __init__(self, regions: List[np.ndarray]):
        self.regions = regions

    def __len__(self):
        return len(self.regions)

    def __getitem__(self, idx):
        region = self.regions[idx]
        # Normalize to [0,1] range
        _min = region.min()
        _max = region.max()
        if _min == _max:
            region = region - _min
        else:
            region = (region - _min) / (_max - _min)
        return torch.FloatTensor(region[None])  # Add channel dimension


def detect_and_extract_normalized_neurons(img, model, diameter: int = 35, px: float = 0.32, z: float = 2):
    img = img[..., 0:-2]  # weird the shape or cellpose chokes TODO: figure out how to avoid this
    img_data = img[:, np.newaxis, :, :]  # add channel dimension, weird the shape
    masks_pred, flows, styles, diams = model.eval(
        [img_data],
        diameter=diameter,
        # niter=2000,
        channel_axis=1,
        z_axis=0,
        stitch_threshold=0.25,
    )
    mask = masks_pred[0]  # each distinct cell gets an id: 1, 2, ...
    regions = []
    for cell_num in tqdm(range(1, mask.max() + 1), desc="Extracting regions", leave=False):
        coords = np.array(np.where(mask == cell_num)).mean(axis=1).astype(int)
        region = extract_region(img, coords, px, z)
        regions.append(region)

    return regions, mask


def train_autoencoder(
    image_paths: List[Path],
    save_path: Optional[Path] = None,
    batch_size: int = 32,
    num_epochs: int = 50,
    px: float = 0.32,
    z: float = 2,
    learning_rate: float = 1e-3,
    device: Optional[torch.device] = None,
) -> NeuronAutoencoder:
    """
    Train autoencoder on neuron regions from multiple images.

    Args:
        image_paths: List of paths to 3D image files
        save_path: Where to save the trained model
        batch_size: Training batch size
        num_epochs: Number of training epochs
        px: Microns per pixel
        z: Microns per z-slice
        learning_rate: Learning rate for Adam optimizer
        device: torch device (will detect GPU if None)
    """
    from cellpose import models

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Collect all regions from all images
    all_regions = []
    model = models.Cellpose(gpu=True, model_type="cyto3")
    for path in tqdm(image_paths, desc="Loading images"):
        img = tifffile.imread(str(path))
        regions, _ = detect_and_extract_normalized_neurons(img, model, px=px, z=z)
        all_regions.extend(regions)
    print(f"Collected {len(all_regions)} neuron regions for training")

    # Create dataset and dataloader
    dataset = NeuronDataset(all_regions)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)

    # Initialize model and training components
    model = NeuronAutoencoder(latent_dim=32).to(device)
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.MSELoss()

    # Training loop
    best_loss = float("inf")
    for epoch in tqdm(range(num_epochs), desc="Training"):
        model.train()
        total_loss = 0

        for batch in dataloader:
            batch = batch.to(device)

            optimizer.zero_grad()
            reconstructed, _ = model(batch)
            loss = criterion(reconstructed, batch)

            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        avg_loss = total_loss / len(dataloader)
        tqdm.write(f"Epoch {epoch}, Loss: {avg_loss:.4f}")

        # Save best model
        if save_path and avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "optimizer_state_dict": optimizer.state_dict(),
                    "loss": best_loss,
                },
                save_path,
            )

    return model


def visualize_reconstructions(model: NeuronAutoencoder, regions: List[np.ndarray], num_examples: int = 5):
    """
    Visualize original and reconstructed neurons to assess autoencoder quality.
    """
    import matplotlib.pyplot as plt

    model.eval()
    device = next(model.parameters()).device

    with torch.no_grad():
        for i in range(min(num_examples, len(regions))):
            region = regions[i]
            region_norm = (region - region.min()) / (region.max() - region.min() + 1e-8)
            region_tensor = torch.FloatTensor(region_norm[None, None]).to(device)

            reconstructed, _ = model(region_tensor)
            reconstructed = reconstructed.cpu().numpy()[0, 0]

            # Show middle z-slice of original and reconstruction
            z_mid = region.shape[2] // 2

            plt.figure(figsize=(10, 5))
            plt.subplot(121)
            plt.imshow(region_norm[:, :, z_mid])
            plt.title("Original")
            plt.axis("off")

            plt.subplot(122)
            plt.imshow(reconstructed[:, :, z_mid])
            plt.title("Reconstructed")
            plt.axis("off")

            plt.show()
    return plt


def main():
    from cellpose import models

    parser = argparse.ArgumentParser("Train neuron autoencoder")
    parser.add_argument("image_paths", type=Path, nargs="+", help="Path to 3D image files")
    parser.add_argument("save_path", type=Path, help="Path to save trained model")
    parser.add_argument("--px", type=float, default=0.32, help="Microns per pixel")
    parser.add_argument("--z", type=float, default=2, help="Microns per z-slice")
    parser.add_argument("--num-epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Training batch size")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Adam optimizer learning rate")
    args = parser.parse_args()

    model = train_autoencoder(**vars(args))

    # Get some test regions for visualization
    test_img = np.load(args.image_paths[0])  # Load first image
    cyto3 = models.Cellpose(gpu=True, model_type="cyto3")
    test_regions, _ = detect_and_extract_normalized_neurons(test_img, cyto3)

    return visualize_reconstructions(model, test_regions)


if __name__ == "__main__":
    win = main()
