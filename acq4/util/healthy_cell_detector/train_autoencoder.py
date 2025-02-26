import argparse
import signal
from pathlib import Path
from typing import Optional, List

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tifffile import tifffile
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm

import pyqtgraph as pg
from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
from acq4.util.healthy_cell_detector.utils import detect_and_extract_normalized_neurons
from pyqtgraph.Qt import QtCore, QtWidgets


class NeuronDataset(Dataset):
    def __init__(self, regions: List[np.ndarray]):
        self.regions = regions

    def __len__(self):
        return len(self.regions)

    def __getitem__(self, idx):
        region = self.regions[idx]
        return torch.FloatTensor(region[None])  # Add channel dimension


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
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Collect all regions from all images
    all_regions = []
    for path in tqdm(image_paths, desc="Loading images"):
        img = tifffile.imread(str(path))
        regions = detect_and_extract_normalized_neurons(img, xy_scale=px, z_scale=z)
        all_regions.extend(regions)
    print(f"Collected {len(all_regions)} neuron regions for training")

    # Create dataset and dataloader
    dataset = NeuronDataset(all_regions)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)

    # Initialize model and training components
    model = NeuronAutoencoder().to(device)
    if save_path and save_path.exists():
        model.load_state_dict(torch.load(save_path)["model_state_dict"])
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=10, verbose=True)
    criterion = nn.MSELoss()

    # Training loop
    best_loss = float("inf")
    epoch = -1

    def do_save(sig, frame):
        nonlocal best_loss, epoch
        torch.save(
            {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "loss": best_loss,
            },
            save_path,
        )
        print(f"Saved model to {save_path}")
        if sig:
            raise KeyboardInterrupt
    signal.signal(signal.SIGINT, do_save)

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
        scheduler.step(avg_loss)
        tqdm.write(f"Epoch {epoch}, Loss: {avg_loss:.4f}")

        # Save best model
        if save_path and avg_loss < best_loss:
            best_loss = avg_loss
            do_save(None, None)

    return model


def visualize_reconstructions(model: NeuronAutoencoder, regions: List[np.ndarray], num_examples: int = 5):
    """
    Visualize original and reconstructed neurons to assess autoencoder quality using pyqtgraph.

    This version uses pyqtgraph for faster, interactive visualization.
    You can zoom, pan, and adjust contrast in real-time!
    """
    # Set pyqtgraph to use white background for better contrast
    pg.setConfigOption('background', 'w')
    pg.setConfigOption('foreground', 'k')

    # Create the application if it doesn't exist
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    # Create a colormap that works well for neuroscience data
    colormap = pg.colormap.get('viridis')

    model.eval()
    device = next(model.parameters()).device
    windows = []  # Keep references to windows to prevent Python garbage collection

    with torch.no_grad():
        for i in range(min(num_examples, len(regions))):
            # Process data
            i = np.random.choice(range(regions.shape[0]))
            region = regions[i]
            region_norm = (region - region.min()) / (region.max() - region.min() + 1e-8)
            region_tensor = torch.FloatTensor(region_norm[None, None]).to(device)

            reconstructed, _ = model(region_tensor)
            reconstructed = reconstructed.cpu().numpy()[0, 0]

            # Show middle z-slice of original and reconstruction
            z_mid = region.shape[0] // 2

            # Create main window
            win = QtWidgets.QMainWindow()
            win.setWindowTitle(f"Neuron Comparer - Brain Cell #{i + 1}")
            win.resize(1000, 500)

            # Create central widget and main layout
            central_widget = QtWidgets.QWidget()
            win.setCentralWidget(central_widget)
            main_layout = QtWidgets.QVBoxLayout()
            central_widget.setLayout(main_layout)

            # Create image layout
            image_layout = QtWidgets.QHBoxLayout()

            # Create original image view
            original_label = QtWidgets.QLabel("🧠 Original Neuron")
            original_label.setAlignment(QtCore.Qt.AlignCenter)
            original_label.setStyleSheet("font-weight: bold; font-size: 14px;")

            original_view = pg.ImageView()
            original_view.setImage(region_norm[z_mid, :, :])
            original_view.ui.histogram.gradient.setColorMap(colormap)

            # Create reconstruction image view with fun label
            recon_label = QtWidgets.QLabel("🔄 Reconstructed Neuron")
            recon_label.setAlignment(QtCore.Qt.AlignCenter)
            recon_label.setStyleSheet("font-weight: bold; font-size: 14px;")

            recon_view = pg.ImageView()
            recon_view.setImage(reconstructed[z_mid, :, :])
            recon_view.ui.histogram.gradient.setColorMap(colormap)

            # Link the views so they zoom/pan together
            original_view.view.linkView(original_view.view.XAxis, recon_view.view)
            original_view.view.linkView(original_view.view.YAxis, recon_view.view)

            # Create left layout
            left_layout = QtWidgets.QVBoxLayout()
            left_layout.addWidget(original_label)
            left_layout.addWidget(original_view)

            # Create right layout
            right_layout = QtWidgets.QVBoxLayout()
            right_layout.addWidget(recon_label)
            right_layout.addWidget(recon_view)

            # Add left and right layouts to image layout
            image_layout.addLayout(left_layout)
            image_layout.addLayout(right_layout)

            # Add tip label at bottom
            tip_label = QtWidgets.QLabel("✨ Tip: Use mouse wheel to zoom, drag to pan! ✨")
            tip_label.setAlignment(QtCore.Qt.AlignCenter)
            tip_label.setStyleSheet("color: purple; font-style: italic;")

            # Add layouts to main layout
            main_layout.addLayout(image_layout)
            main_layout.addWidget(tip_label)

            # Show window
            win.show()
            windows.append(win)  # Keep reference to prevent garbage collection

    # Start Qt event loop if not already running
    if app is not None and not (hasattr(app, '_in_event_loop') and app._in_event_loop):
        print("🔬 Interactive neuron visualization running! Close windows to continue...")
        app.exec_()

    return windows


def main():
    parser = argparse.ArgumentParser("Train neuron autoencoder")
    parser.add_argument("image_paths", type=Path, nargs="+", help="Path to 3D image files")
    parser.add_argument("save_path", type=Path, help="Path to save trained model")
    parser.add_argument("--px", type=float, default=0.32, help="Microns per pixel")
    parser.add_argument("--z", type=float, default=1, help="Microns per z-slice")
    parser.add_argument("--num-epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Training batch size")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Adam optimizer learning rate")
    parser.add_argument("--viz-only", action="store_true", help="Visualize reconstructions only")
    args = parser.parse_args()

    if args.viz_only:
        model = NeuronAutoencoder()
        model.load_state_dict(torch.load(args.save_path)["model_state_dict"])
    else:
        del args.viz_only
        model = train_autoencoder(**vars(args))

    # Get some test regions for visualization
    test_img = tifffile.imread(args.image_paths[0])
    test_regions = detect_and_extract_normalized_neurons(test_img, xy_scale=args.px, z_scale=args.z)

    return visualize_reconstructions(model, test_regions)


if __name__ == "__main__":
    app = pg.mkQApp()
    win = main()
