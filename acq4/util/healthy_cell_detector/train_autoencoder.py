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
        return torch.FloatTensor(self.regions[idx])


def train_autoencoder(
    image_paths: List[Path],
    save_path: Optional[Path] = None,
    batch_size: int = 32,
    num_epochs: int = 50,
    px: float = 0.32e-6,
    z: float = 1e-6,
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
        px: Meters per pixel
        z: Meters per z-slice
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
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")

    # Create the application if it doesn't exist
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    # Create a colormap that works well for neuroscience data
    colormap = pg.colormap.get("viridis")

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
    if app is not None and not (hasattr(app, "_in_event_loop") and app._in_event_loop):
        print("🔬 Interactive neuron visualization running! Close windows to continue...")
        app.exec_()

    return windows


def visualize_z_stack_comparison(model: NeuronAutoencoder, regions: List[np.ndarray], seed: int = 42, test_mode: bool = False):
    """
    Visualize all z-layers of original and reconstructed neurons in a horizontal row.
    
    Shows all original z-layers in one row, with reconstructions in a row below.

    Args:
        model: Trained autoencoder model
        regions: List of neuron regions to visualize
        seed: Random seed for consistent cell order
        test_mode: If True, use random noise instead of real data (for UI testing)

    Returns:
        Reference to Qt application window
    """
    # Set random seed for reproducible cell ordering
    np.random.seed(seed)

    # Set pyqtgraph to use white background for better contrast
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")

    # Create the application if it doesn't exist
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])

    # Create a colormap that works well for neuroscience data
    colormap = pg.colormap.get("viridis")

    # Ensure model is in eval mode (if not in test mode)
    if not test_mode and model is not None:
        model.eval()
        device = next(model.parameters()).device
    
    # Create main window
    main_window = QtWidgets.QMainWindow()
    main_window.setWindowTitle("Z-Stack Neuron Autoencoder Viewer")
    main_window.resize(1000, 500)  # Slightly smaller to ensure images fill space

    # Create central widget
    central_widget = QtWidgets.QWidget()
    main_layout = QtWidgets.QVBoxLayout()
    central_widget.setLayout(main_layout)

    # Header with title
    header = QtWidgets.QLabel("🧠 Z-Stack Neuron Autoencoder Viewer")
    header.setAlignment(QtCore.Qt.AlignCenter)
    header.setStyleSheet("font-weight: bold; font-size: 18px; margin: 10px;")
    main_layout.addWidget(header)

    # Create a widget for the image display
    display_widget = QtWidgets.QWidget()
    display_layout = QtWidgets.QVBoxLayout()
    display_widget.setLayout(display_layout)
    
    # Create rows for original and reconstructed images
    original_row = QtWidgets.QWidget()
    original_layout = QtWidgets.QHBoxLayout()
    original_layout.setContentsMargins(5, 5, 5, 5)
    original_layout.setSpacing(5)
    original_row.setLayout(original_layout)
    
    recon_row = QtWidgets.QWidget()
    recon_layout = QtWidgets.QHBoxLayout()
    recon_layout.setContentsMargins(5, 5, 5, 5)
    recon_layout.setSpacing(5)
    recon_row.setLayout(recon_layout)
    
    # Add row labels
    original_label = QtWidgets.QLabel("Original:")
    original_label.setStyleSheet("font-weight: bold; font-size: 14px;")
    original_layout.addWidget(original_label)
    
    recon_label = QtWidgets.QLabel("Reconstructed:")
    recon_label.setStyleSheet("font-weight: bold; font-size: 14px;")
    recon_layout.addWidget(recon_label)
    
    # Add rows to display layout
    display_layout.addWidget(original_row)
    display_layout.addWidget(recon_row)
    
    # Add display widget to main layout
    main_layout.addWidget(display_widget)

    # Create a widget for the controls
    control_widget = QtWidgets.QWidget()
    control_layout = QtWidgets.QHBoxLayout()
    control_widget.setLayout(control_layout)

    # Create cell counter label
    cell_counter = QtWidgets.QLabel("Cell 1/?")
    cell_counter.setStyleSheet("font-weight: bold; font-size: 14px;")

    # Create next button with an index tracker
    next_button = QtWidgets.QPushButton("🔍 Next Random Cell")
    next_button.setStyleSheet("font-size: 14px; padding: 5px 15px;")

    # Add controls to layout
    control_layout.addWidget(cell_counter)
    control_layout.addStretch()
    control_layout.addWidget(next_button)

    # Add control widget to main layout
    main_layout.addWidget(control_widget)

    # Set central widget
    main_window.setCentralWidget(central_widget)

    # Track current cell index
    if test_mode:
        cell_indices = list(range(10))  # Just use 10 fake cells for testing
    else:
        cell_indices = list(range(len(regions)))
    np.random.shuffle(cell_indices)
    current_index = [0]  # Using list for mutable reference

    # Create placeholders for image views
    image_views = []

    def update_cell_display():
        # Clear existing views
        for i in reversed(range(original_layout.count())):
            if i > 0:  # Keep the label
                widget = original_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()
                    
        for i in reversed(range(recon_layout.count())):
            if i > 0:  # Keep the label
                widget = recon_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

        # Clear image views list
        image_views.clear()

        # Get current cell index
        idx = cell_indices[current_index[0]]

        # Process data
        if test_mode:
            # Generate random noise for testing
            num_z_layers = 5  # Fixed number of z-layers for testing
            region_norm = np.random.rand(num_z_layers, 64, 64)  # Random noise
            reconstructed = np.random.rand(num_z_layers, 64, 64)  # Random noise
        else:
            # Get real data
            region = regions[idx]
            region_norm = (region - region.min()) / (region.max() - region.min() + 1e-8)
            region_tensor = torch.FloatTensor(region_norm).to(device)
            
            # Create batch dimension if needed
            if len(region_tensor.shape) == 3:
                region_tensor = region_tensor.unsqueeze(0)
            
            # Get reconstruction
            with torch.no_grad():
                reconstructed, _ = model(region_tensor)
                reconstructed = reconstructed.cpu().numpy()[0]
            
            num_z_layers = region.shape[0]

        # Update counter
        if test_mode:
            cell_counter.setText(f"Test Cell {current_index[0] + 1}/10")
        else:
            cell_counter.setText(f"Cell {current_index[0] + 1}/{len(cell_indices)}")

        # Add each z-layer to the rows
        for z in range(num_z_layers):
            # Create original image view
            original_view = pg.ImageView()
            original_view.ui.histogram.hide()
            original_view.ui.roiBtn.hide()
            original_view.ui.menuBtn.hide()
            original_view.setImage(region_norm[z])
            original_view.getView().setDefaultPadding(0)
            original_view.getView().setAspectLocked(True)
            
            # Set fixed size to ensure images fill their space
            original_view.setMinimumSize(120, 120)
            original_view.setMaximumSize(200, 200)
            
            # Adjust view to fill the available space
            original_view.getView().setRange(QtCore.QRectF(0, 0, region_norm[z].shape[0], region_norm[z].shape[1]), padding=0)
            
            # Create z-layer label for original
            z_label = QtWidgets.QLabel(f"Z{z}")
            z_label.setAlignment(QtCore.Qt.AlignCenter)
            z_label.setStyleSheet("font-size: 12px;")
            
            # Create a container for the image and its label
            orig_container = QtWidgets.QWidget()
            orig_container_layout = QtWidgets.QVBoxLayout()
            orig_container_layout.setContentsMargins(2, 2, 2, 2)
            orig_container_layout.setSpacing(2)
            orig_container.setLayout(orig_container_layout)
            orig_container_layout.addWidget(z_label)
            orig_container_layout.addWidget(original_view)
            
            # Create reconstructed image view
            recon_view = pg.ImageView()
            recon_view.ui.histogram.hide()
            recon_view.ui.roiBtn.hide()
            recon_view.ui.menuBtn.hide()
            recon_view.setImage(reconstructed[z])
            recon_view.getView().setDefaultPadding(0)
            recon_view.getView().setAspectLocked(True)
            
            # Set fixed size to ensure images fill their space
            recon_view.setMinimumSize(120, 120)
            recon_view.setMaximumSize(200, 200)
            
            # Adjust view to fill the available space
            recon_view.getView().setRange(QtCore.QRectF(0, 0, reconstructed[z].shape[0], reconstructed[z].shape[1]), padding=0)
            
            # Create z-layer label for reconstruction
            recon_z_label = QtWidgets.QLabel(f"Z{z}")
            recon_z_label.setAlignment(QtCore.Qt.AlignCenter)
            recon_z_label.setStyleSheet("font-size: 12px;")
            
            # Create a container for the image and its label
            recon_container = QtWidgets.QWidget()
            recon_container_layout = QtWidgets.QVBoxLayout()
            recon_container_layout.setContentsMargins(2, 2, 2, 2)
            recon_container_layout.setSpacing(2)
            recon_container.setLayout(recon_container_layout)
            recon_container_layout.addWidget(recon_z_label)
            recon_container_layout.addWidget(recon_view)

            # Link views for synchronized zooming/panning
            original_view.getView().linkView(original_view.getView().XAxis, recon_view.getView())
            original_view.getView().linkView(original_view.getView().YAxis, recon_view.getView())

            # Store references to image views to prevent garbage collection
            image_views.append((original_view, recon_view))

            # Add views to layout
            original_layout.addWidget(orig_container)
            recon_layout.addWidget(recon_container)

    # Define action for next button
    def next_cell():
        current_index[0] = (current_index[0] + 1) % len(cell_indices)
        update_cell_display()

    # Connect button to action
    next_button.clicked.connect(next_cell)

    # Initial display
    update_cell_display()

    # Show window
    main_window.show()

    # Start Qt event loop if not already running
    if app is not None and not (hasattr(app, "_in_event_loop") and app._in_event_loop):
        print("🔬 Interactive z-stack visualization running! Close window to continue...")
        app.exec_()

    return main_window


def main():
    parser = argparse.ArgumentParser("Train neuron autoencoder")
    parser.add_argument("image_paths", type=Path, nargs="+", help="Path to 3D image files")
    parser.add_argument("save_path", type=Path, help="Path to save trained model")
    parser.add_argument("--px", type=float, default=0.32e-6, help="Meters per pixel")
    parser.add_argument("--z", type=float, default=1e-6, help="Meters per z-slice")
    parser.add_argument("--num-epochs", type=int, default=50, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Training batch size")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="Adam optimizer learning rate")
    parser.add_argument("--viz-only", action="store_true", help="Visualize reconstructions only")
    parser.add_argument("--test-ui", action="store_true", help="Test UI with random noise images")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for visualization")
    args = parser.parse_args()

    # Test UI mode - bypass real work and show random noise
    if args.test_ui:
        print("🧪 Testing UI with random noise images...")
        return visualize_z_stack_comparison(None, [], seed=args.seed, test_mode=True)
    
    if args.viz_only:
        model = NeuronAutoencoder()
        model.load_state_dict(torch.load(args.save_path)["model_state_dict"])
    else:
        model = train_autoencoder(**{k: v for k, v in vars(args).items() if k not in ["viz_only", "test_ui", "seed"]})

    # Get some test regions for visualization
    test_img = tifffile.imread(args.image_paths[0])
    test_regions = detect_and_extract_normalized_neurons(test_img, xy_scale=args.px, z_scale=args.z)

    # Use the visualization function
    return visualize_z_stack_comparison(model, test_regions, seed=args.seed)


if __name__ == "__main__":
    app = pg.mkQApp()
    win = main()
