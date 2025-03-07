import argparse
import json
from functools import lru_cache
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import classification_report, confusion_matrix, precision_recall_curve, auc, roc_curve
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

import pyqtgraph as pg
from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
from acq4.util.healthy_cell_detector.train_rf_classifier import extract_features, get_features_and_labels
from acq4.util.healthy_cell_detector.utils import extract_region, cell_centers
from acq4.util.imaging.object_detection import get_cellpose_masks


class NeuronClassifier(nn.Module):
    def __init__(self, input_size=64, hidden_sizes=None, dropout=0.5):
        """
        Neural network classifier for healthy neurons

        Parameters:
        -----------
        input_size : int
            Size of input feature vector
        hidden_sizes : list
            List of hidden layer sizes
        dropout : float
            Dropout probability
        """
        if hidden_sizes is None:
            hidden_sizes = [128, 64, 32]
        super().__init__()

        layers = []
        prev_size = input_size

        # Add hidden layers
        for h_size in hidden_sizes:
            layers.append(nn.Linear(prev_size, h_size))
            layers.append(nn.BatchNorm1d(h_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            prev_size = h_size

        # Output layer
        layers.append(nn.Linear(prev_size, 1))
        layers.append(nn.Sigmoid())

        self.model = nn.Sequential(*layers)

    def forward(self, x):
        return self.model(x)


class ThresholdedNeuronClassifier:
    def __init__(self, model, threshold=0.5):
        """
        Wrapper for neural network that applies a custom threshold for classification

        Parameters:
        -----------
        model : nn.Module
            PyTorch neural network model
        threshold : float
            Classification threshold
        """
        self.model = model
        self.threshold = threshold
        self.device = next(model.parameters()).device

    def predict(self, X):
        """
        Predict class labels

        Parameters:
        -----------
        X : numpy.ndarray
            Input features

        Returns:
        --------
        numpy.ndarray
            Predicted class labels (0 or 1)
        """
        X_tensor = torch.tensor(X, dtype=torch.float32).to(self.device)
        with torch.no_grad():
            probas = self.model(X_tensor).cpu().numpy().flatten()
        return (probas >= self.threshold).astype(int)

    def predict_proba(self, X):
        """
        Predict class probabilities

        Parameters:
        -----------
        X : numpy.ndarray
            Input features

        Returns:
        --------
        numpy.ndarray
            Predicted probabilities (shape: [n_samples, 2])
        """
        X_tensor = torch.tensor(X, dtype=torch.float32).to(self.device)
        with torch.no_grad():
            pos_probs = self.model(X_tensor).cpu().numpy().flatten()
            neg_probs = 1 - pos_probs
        return np.column_stack([neg_probs, pos_probs])


def train_neural_classifier(features, labels, device="cuda", class_weight=None):
    """
    Train a neural network classifier

    Parameters:
    -----------
    features : numpy.ndarray
        Feature vectors
    labels : numpy.ndarray
        Class labels (0 or 1)
    device : str
        Device to use for training ('cuda' or 'cpu')
    class_weight : float or None
        Weight for the positive class to handle imbalance

    Returns:
    --------
    dict
        Results including the model, test data, and predictions
    """
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, stratify=labels, random_state=42
    )

    # Convert to PyTorch tensors
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
    y_train_tensor = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
    X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
    y_test_tensor = torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)

    # Create data loaders
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

    # Initialize model
    input_size = features.shape[1]
    model = NeuronClassifier(input_size=input_size).to(device)

    # Calculate class weights if not provided
    if class_weight is None:
        pos_count = np.sum(y_train)
        neg_count = len(y_train) - pos_count
        class_weight = neg_count / pos_count

    pos_weight = torch.tensor([class_weight], device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    # Using BCEWithLogitsLoss with pos_weight instead of regular BCE
    # This means we need to remove the Sigmoid in the model for training
    model.model = nn.Sequential(*list(model.model.children())[:-1])

    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
    # optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
    n_epochs = 1000
    # scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, "min", patience=n_epochs // 10, factor=0.5, verbose=True)
    scheduler = optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=0.01, epochs=n_epochs, steps_per_epoch=len(train_loader)
    )
    # Train the model
    best_val_loss = float("inf")
    best_model_state = None
    patience = 50
    counter = 0

    print("Training neural network classifier...")
    for epoch in tqdm(range(n_epochs), desc="Training", leave=True):
        model.train()
        train_loss = 0.0

        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)

            # Forward pass
            outputs = model(inputs)
            loss = criterion(outputs, targets)

            # Backward and optimize
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * inputs.size(0)

        train_loss /= len(train_loader.dataset)

        # Validate on test set
        model.eval()
        with torch.no_grad():
            X_test_device = X_test_tensor.to(device)
            y_test_device = y_test_tensor.to(device)
            val_outputs = model(X_test_device)
            val_loss = criterion(val_outputs, y_test_device).item()

        print(f"Epoch {epoch + 1}/{n_epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

        # Learning rate scheduler
        scheduler.step(val_loss)

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()
            counter = 0
        else:
            counter += 1
            if counter >= patience:
                print(f"Early stopping at epoch {epoch + 1}")
                break

    # Load best model
    model.load_state_dict(best_model_state)

    # Add Sigmoid back for inference if using BCEWithLogitsLoss
    if class_weight is not None:
        model.eval()
        # Wrap the model so it returns probabilities
        model = nn.Sequential(model, nn.Sigmoid())

    # Get predictions
    model.eval()
    with torch.no_grad():
        y_pred_prob = model(X_test_tensor.to(device)).cpu().numpy().flatten()

    # Find optimal threshold for precision-recall tradeoff
    precision, recall, thresholds = precision_recall_curve(y_test, y_pred_prob)

    # Find threshold that gives best F1 score
    f1_scores = 2 * (precision[:-1] * recall[:-1]) / (precision[:-1] + recall[:-1] + 1e-10)
    best_f1_idx = np.argmax(f1_scores)
    best_f1_threshold = thresholds[best_f1_idx]

    # Target precision
    target_precision = 0.6
    valid_indices = precision[:-1] >= target_precision

    if sum(valid_indices) > 0:
        # Find the threshold that gives the best recall while meeting precision requirement
        best_idx = np.argmax(recall[:-1][valid_indices])
        optimal_threshold = thresholds[valid_indices][best_idx]
    else:
        # If no threshold meets our precision target, use the F1 threshold
        optimal_threshold = best_f1_threshold

    print(f"Optimal threshold: {optimal_threshold:.3f}")

    # Apply the optimal threshold
    y_pred = (y_pred_prob >= optimal_threshold).astype(int)

    print("\nClassification Report with optimized threshold:")
    print(classification_report(y_test, y_pred))

    # Create the thresholded model wrapper
    thresholded_model = ThresholdedNeuronClassifier(model, optimal_threshold)

    return {
        "model": thresholded_model,
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "y_pred_prob": y_pred_prob,
        "threshold": optimal_threshold,
    }


def evaluate_classifier(y_true, y_pred):
    """Calculate and return evaluation metrics"""
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    false_positive_rate = fp / (fp + tn)

    return {
        "precision": precision_score(y_true, y_pred),
        "recall": recall_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
        "false_positive_rate": false_positive_rate,
        "false_negatives": fn,
        "false_positives": fp,
    }


def visualize_training(model_result):
    """Create visualization plots for model evaluation"""
    y_test = model_result["y_test"]
    y_pred_prob = model_result["y_pred_prob"]

    # Plot ROC curve
    fpr, tpr, _ = roc_curve(y_test, y_pred_prob)
    roc_auc = auc(fpr, tpr)

    plt.figure(figsize=(10, 8))
    plt.plot(fpr, tpr, color="darkorange", lw=2, label=f"ROC curve (area = {roc_auc:.2f})")
    plt.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("Receiver Operating Characteristic")
    plt.legend(loc="lower right")
    plt.savefig("nn_roc_curve.png")
    plt.show()

    # Plot precision-recall curve
    precision, recall, thresholds = precision_recall_curve(y_test, y_pred_prob)
    plt.figure(figsize=(10, 8))
    plt.plot(recall, precision, color="blue", lw=2)
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Precision-Recall Curve")
    plt.grid(True)
    plt.savefig("nn_precision_recall_curve.png")
    plt.show()

    # Plot threshold vs metrics
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.plot(thresholds, precision[:-1], "b--", label="Precision")
    plt.plot(thresholds, recall[:-1], "g-", label="Recall")
    plt.axvline(x=model_result["threshold"], color="r", linestyle="--", label="Optimal Threshold")
    plt.xlabel("Threshold")
    plt.ylabel("Score")
    plt.title("Precision and Recall vs. Threshold")
    plt.legend()
    plt.grid(True)

    # Calculate FPR at different thresholds
    fpr = []
    for threshold in thresholds:
        y_pred = (y_pred_prob >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        fpr.append(fp / (fp + tn))

    plt.subplot(1, 2, 2)
    plt.plot(thresholds, fpr, "r-", label="False Positive Rate")
    plt.axvline(x=model_result["threshold"], color="r", linestyle="--", label="Optimal Threshold")
    plt.xlabel("Threshold")
    plt.ylabel("False Positive Rate")
    plt.title("False Positive Rate vs. Threshold")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.savefig("nn_threshold_metrics.png")
    plt.show()


def save_classifier(classifier, path):
    """Save the trained classifier to a file"""
    torch.save(
        {
            "threshold": classifier.threshold,
            "model_state_dict": classifier.model.state_dict(),
            "input_size": next(classifier.model.parameters()).shape[1],
        },
        path,
    )
    print(f"Neural classifier saved to {path}")


@lru_cache(maxsize=1)
def load_classifier(path, device="cuda"):
    """Load a trained neural classifier from a file"""
    checkpoint = torch.load(path, map_location=device)
    input_size = checkpoint.get("input_size", 64)
    model = NeuronClassifier(input_size=input_size).to(device)
    model = nn.Sequential(model, nn.Sigmoid())

    # Check if it's the full model or just the sequential part
    try:
        model.load_state_dict(checkpoint["model_state_dict"])
    except RuntimeError:
        # Might be the wrapper model
        model.model.load_state_dict(checkpoint["model_state_dict"])

    model.eval()

    return ThresholdedNeuronClassifier(model, checkpoint["threshold"])


def get_health_ordered_cells(
    image: np.ndarray,
    classifier: ThresholdedNeuronClassifier,
    autoencoder: NeuronAutoencoder,
    diameter: int,
    xy_scale: float,
    z_scale: float,
    device="cuda",
):
    """
    Use a trained classifier to identify healthy neurons in new images

    Parameters:
    -----------
    image
        3D image data
    classifier
        Trained classifier for healthy neuron detection
    autoencoder
        Trained autoencoder for feature extraction
    diameter
        Expected diameter of neurons for cellpose
    xy_scale
        Scale factor for xy dimensions
    z_scale
        Scale factor for z dimension
    device
        Device to use for autoencoder inference

    Returns:
    --------
    results : list of coordinates
        List of neuron coordinates ordered by health status
    """
    masks = get_cellpose_masks(image, diameter)
    cells = np.array(list(cell_centers(masks, diameter)))
    if len(cells) == 0:
        return []
    regions = [extract_region(image, center, xy_scale, z_scale) for center in cells]
    features = extract_features(regions, autoencoder, device)
    probabilities = classifier.predict_proba(features)[:, 1]  # Probability of being healthy

    # Sort cells by probability of being healthy
    return cells[np.argsort(-probabilities)]


def compare_models(rf_results, nn_results):
    """Compare RandomForest and Neural Network results"""
    plt.figure(figsize=(12, 10))

    # ROC curve comparison
    plt.subplot(2, 2, 1)
    # RandomForest ROC
    rf_fpr, rf_tpr, _ = roc_curve(rf_results["y_test"], rf_results["y_pred_prob"])
    rf_auc = auc(rf_fpr, rf_tpr)
    plt.plot(rf_fpr, rf_tpr, "b-", label=f"RandomForest (AUC = {rf_auc:.3f})")

    # Neural Network ROC
    nn_fpr, nn_tpr, _ = roc_curve(nn_results["y_test"], nn_results["y_pred_prob"])
    nn_auc = auc(nn_fpr, nn_tpr)
    plt.plot(nn_fpr, nn_tpr, "r-", label=f"Neural Network (AUC = {nn_auc:.3f})")

    plt.plot([0, 1], [0, 1], "k--")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curve Comparison")
    plt.legend()

    # Precision-Recall curve comparison
    plt.subplot(2, 2, 2)
    # RandomForest P-R
    rf_precision, rf_recall, _ = precision_recall_curve(rf_results["y_test"], rf_results["y_pred_prob"])
    plt.plot(rf_recall, rf_precision, "b-", label="RandomForest")

    # Neural Network P-R
    nn_precision, nn_recall, _ = precision_recall_curve(nn_results["y_test"], nn_results["y_pred_prob"])
    plt.plot(nn_recall, nn_precision, "r-", label="Neural Network")

    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Precision-Recall Curve Comparison")
    plt.legend()

    # Metrics comparison
    plt.subplot(2, 2, 3)
    metrics = ["Precision", "Recall", "F1", "FPR"]
    rf_metrics = [
        precision_score(rf_results["y_test"], rf_results["y_pred"]),
        recall_score(rf_results["y_test"], rf_results["y_pred"]),
        f1_score(rf_results["y_test"], rf_results["y_pred"]),
        sum(rf_results["y_pred"] != rf_results["y_test"]) / len(rf_results["y_test"]),
    ]
    nn_metrics = [
        precision_score(nn_results["y_test"], nn_results["y_pred"]),
        recall_score(nn_results["y_test"], nn_results["y_pred"]),
        f1_score(nn_results["y_test"], nn_results["y_pred"]),
        sum(nn_results["y_pred"] != nn_results["y_test"]) / len(nn_results["y_test"]),
    ]

    x = np.arange(len(metrics))
    width = 0.35

    plt.bar(x - width / 2, rf_metrics, width, label="RandomForest")
    plt.bar(x + width / 2, nn_metrics, width, label="Neural Network")
    plt.xticks(x, metrics)
    plt.ylabel("Score")
    plt.title("Performance Metrics Comparison")
    plt.legend()

    # Confusion matrix comparison (as text)
    plt.subplot(2, 2, 4)
    plt.axis("off")

    rf_cm = confusion_matrix(rf_results["y_test"], rf_results["y_pred"])
    nn_cm = confusion_matrix(nn_results["y_test"], nn_results["y_pred"])

    cm_text = (
        f"RandomForest Confusion Matrix:\n"
        f"TN: {rf_cm[0, 0]}, FP: {rf_cm[0, 1]}\n"
        f"FN: {rf_cm[1, 0]}, TP: {rf_cm[1, 1]}\n\n"
        f"Neural Network Confusion Matrix:\n"
        f"TN: {nn_cm[0, 0]}, FP: {nn_cm[0, 1]}\n"
        f"FN: {nn_cm[1, 0]}, TP: {nn_cm[1, 1]}"
    )

    plt.text(0.5, 0.5, cm_text, ha="center", va="center", fontsize=12)

    plt.tight_layout()
    plt.savefig("model_comparison.png")
    plt.show()


def train_neural_classifier_with_params(
    X_train,
    y_train,
    X_test,
    y_test,
    dropout=0.5,
    hidden_sizes=None,
    optimizer_name="adam",
    weight_decay=1e-5,
    scheduler_name="onecycle",
    device="cuda",
    class_weight=None,
    n_epochs=1000,
    patience=50,
):
    """
    Train a neural network classifier with specific hyperparameters

    Parameters:
    -----------
    X_train, y_train : training data
    X_test, y_test : test data
    dropout : float
        Dropout probability
    hidden_sizes : list
        List of hidden layer sizes
    optimizer_name : str
        Name of optimizer (adam, adamw, sgd, rmsprop)
    weight_decay : float
        L2 regularization strength
    scheduler_name : str
        Name of learning rate scheduler (onecycle, reduce_plateau, cosine)
    device : str
        Device to use for training ('cuda' or 'cpu')
    class_weight : float or None
        Weight for the positive class to handle imbalance
    n_epochs : int
        Maximum number of training epochs
    patience : int
        Early stopping patience

    Returns:
    --------
    dict
        Results including the model, predictions, and metrics
    """
    if hidden_sizes is None:
        hidden_sizes = [128, 64, 32]

    # Convert to PyTorch tensors
    X_train_tensor = torch.tensor(X_train, dtype=torch.float32)
    y_train_tensor = torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
    X_test_tensor = torch.tensor(X_test, dtype=torch.float32)
    y_test_tensor = torch.tensor(y_test, dtype=torch.float32).unsqueeze(1)

    # Create data loaders
    train_dataset = TensorDataset(X_train_tensor, y_train_tensor)
    train_loader = DataLoader(train_dataset, batch_size=64, shuffle=True)

    # Initialize model
    input_size = X_train.shape[1]
    model = NeuronClassifier(input_size=input_size, hidden_sizes=hidden_sizes, dropout=dropout).to(device)

    # Calculate class weights if not provided
    if class_weight is None:
        pos_count = np.sum(y_train)
        neg_count = len(y_train) - pos_count
        class_weight = neg_count / pos_count

    # Loss and optimizer
    if class_weight is not None:
        pos_weight = torch.tensor([class_weight], device=device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        # Using BCEWithLogitsLoss with pos_weight instead of regular BCE
        # This means we need to remove the Sigmoid in the model for training
        model.model = nn.Sequential(*list(model.model.children())[:-1])
    else:
        criterion = nn.BCELoss()

    # Create optimizer
    if optimizer_name.lower() == "adam":
        optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=weight_decay)
    elif optimizer_name.lower() == "adamw":
        optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=weight_decay)
    elif optimizer_name.lower() == "sgd":
        optimizer = optim.SGD(model.parameters(), lr=0.01, momentum=0.9, weight_decay=weight_decay)
    elif optimizer_name.lower() == "rmsprop":
        optimizer = optim.RMSprop(model.parameters(), lr=0.001, weight_decay=weight_decay)
    else:
        raise ValueError(f"Unsupported optimizer: {optimizer_name}")

    # Create scheduler
    if scheduler_name.lower() == "onecycle":
        scheduler = optim.lr_scheduler.OneCycleLR(
            optimizer, max_lr=0.01, epochs=n_epochs, steps_per_epoch=len(train_loader)
        )
    elif scheduler_name.lower() == "reduce_plateau":
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode="min", patience=n_epochs // 10, factor=0.5, verbose=True
        )
    elif scheduler_name.lower() == "cosine":
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)
    else:
        raise ValueError(f"Unsupported scheduler: {scheduler_name}")

    # Train the model
    best_val_loss = float("inf")
    best_model_state = None
    counter = 0

    for epoch in range(n_epochs):
        model.train()
        train_loss = 0.0

        for inputs, targets in train_loader:
            inputs, targets = inputs.to(device), targets.to(device)

            # Forward pass
            outputs = model(inputs)
            loss = criterion(outputs, targets)

            # Backward and optimize
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * inputs.size(0)

        train_loss /= len(train_loader.dataset)

        # Validate on test set
        model.eval()
        with torch.no_grad():
            X_test_device = X_test_tensor.to(device)
            y_test_device = y_test_tensor.to(device)
            val_outputs = model(X_test_device)
            val_loss = criterion(val_outputs, y_test_device).item()

        if epoch % 10 == 0:  # Print less frequently to avoid overloading logs
            print(f"Epoch {epoch + 1}/{n_epochs}, Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

        # Learning rate scheduler
        if scheduler_name.lower() == "reduce_plateau":
            scheduler.step(val_loss)
        else:
            scheduler.step()

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()
            counter = 0
        else:
            counter += 1
            if counter >= patience:
                print(f"Early stopping at epoch {epoch + 1}")
                break

    # Load best model
    model.load_state_dict(best_model_state)

    # Add Sigmoid back for inference if using BCEWithLogitsLoss
    if class_weight is not None:
        model.eval()
        # Wrap the model so it returns probabilities
        model = nn.Sequential(model, nn.Sigmoid())

    # Get predictions
    model.eval()
    with torch.no_grad():
        y_pred_prob = model(X_test_tensor.to(device)).cpu().numpy().flatten()

    # Find optimal threshold
    precision, recall, thresholds = precision_recall_curve(y_test, y_pred_prob)
    f1_scores = 2 * (precision[:-1] * recall[:-1]) / (precision[:-1] + recall[:-1] + 1e-10)
    best_f1_idx = np.argmax(f1_scores)
    best_f1_threshold = thresholds[best_f1_idx]

    # Target precision
    target_precision = 0.6
    valid_indices = precision[:-1] >= target_precision

    if sum(valid_indices) > 0:
        best_idx = np.argmax(recall[:-1][valid_indices])
        optimal_threshold = thresholds[valid_indices][best_idx]
    else:
        optimal_threshold = best_f1_threshold

    # Apply the optimal threshold
    y_pred = (y_pred_prob >= optimal_threshold).astype(int)

    # Create the thresholded model wrapper
    thresholded_model = ThresholdedNeuronClassifier(model, optimal_threshold)

    return {
        "model": thresholded_model,
        "y_test": y_test,
        "y_pred": y_pred,
        "y_pred_prob": y_pred_prob,
        "threshold": optimal_threshold,
        "val_loss": best_val_loss,
    }


def grid_search_hyperparameters(features, labels, device, output_dir, class_weight=None):
    """
    Perform grid search over hyperparameters for neural network classifier

    Parameters:
    -----------
    features : numpy.ndarray
        Feature vectors
    labels : numpy.ndarray
        Class labels (0 or 1)
    device : str
        Device to use for training ('cuda' or 'cpu')
    output_dir : str
        Directory to save models and results
    class_weight : float or None
        Weight for the positive class to handle imbalance

    Returns:
    --------
    str
        Path to the CSV file with results
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Define hyperparameter grid
    param_grid = {
        "dropout": [0.3, 0.5, 0.7],
        "hidden_sizes": [
            # [32],
            [64],
            [128, 64],
            # [256, 128, 64],
            # [128, 64, 32],
            [64, 32, 16],
        ],
        "optimizer": ["adam", "adamw"],  # , 'sgd', 'rmsprop'],
        "weight_decay": [1e-6, 1e-5, 1e-4],
        "scheduler": ["onecycle", "reduce_plateau"],  # , 'cosine'],
    }

    # Calculate total number of combinations
    total_combinations = (
        len(param_grid["dropout"])
        * len(param_grid["hidden_sizes"])
        * len(param_grid["optimizer"])
        * len(param_grid["weight_decay"])
        * len(param_grid["scheduler"])
    )

    print(f"Running grid search with {total_combinations} hyperparameter combinations")

    # Save hyperparameter grid for reference
    with open(Path(output_dir) / "param_grid.json", "w") as f:
        # Convert hidden_sizes to strings for JSON serialization
        serializable_grid = param_grid.copy()
        serializable_grid["hidden_sizes"] = [str(h) for h in param_grid["hidden_sizes"]]
        json.dump(serializable_grid, f, indent=2)

    # Create CSV file for results
    results_path = Path(output_dir) / "grid_search_results.csv"
    with open(results_path, "w") as f:
        # Write header
        f.write("model_name,dropout,hidden_sizes,optimizer,weight_decay,scheduler,auc,precision,recall,f1,")
        f.write("false_positive_rate,threshold,val_loss,train_time,specificity,avg_precision,false_negatives,")
        f.write("false_positives,true_negatives,true_positives\n")

    # Create split for consistent evaluation
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, stratify=labels, random_state=42
    )

    # Iterate through all hyperparameter combinations
    model_count = 0
    for dropout in tqdm(param_grid["dropout"], desc="Dropout"):
        for hidden_sizes in tqdm(param_grid["hidden_sizes"], desc="Hidden Sizes", leave=False):
            for optimizer_name in tqdm(param_grid["optimizer"], desc="Optimizer", leave=False):
                for weight_decay in tqdm(param_grid["weight_decay"], desc="Weight Decay", leave=False):
                    for scheduler_name in tqdm(param_grid["scheduler"], desc="Scheduler", leave=False):
                        model_count += 1
                        print(f"\nTraining model {model_count}/{total_combinations}")
                        print(
                            f"Parameters: dropout={dropout}, hidden_sizes={hidden_sizes}, "
                            f"optimizer={optimizer_name}, weight_decay={weight_decay}, "
                            f"scheduler={scheduler_name}"
                        )

                        # Create descriptive model name
                        hidden_str = "_".join(str(h) for h in hidden_sizes)
                        wd_str = f"{weight_decay:.0e}".replace("+", "")
                        model_name = f"nn_d{dropout}_h{hidden_str}_o{optimizer_name}_wd{wd_str}_s{scheduler_name}"
                        model_file = Path(output_dir) / f"{model_name}.pt"

                        # Train model with specific hyperparameters
                        try:
                            import time

                            start_time = time.time()

                            result = train_neural_classifier_with_params(
                                X_train,
                                y_train,
                                X_test,
                                y_test,
                                dropout=dropout,
                                hidden_sizes=hidden_sizes,
                                optimizer_name=optimizer_name,
                                weight_decay=weight_decay,
                                scheduler_name=scheduler_name,
                                device=device,
                                class_weight=class_weight,
                            )

                            train_time = time.time() - start_time

                            # Extract metrics
                            y_pred_prob = result["y_pred_prob"]
                            y_pred = result["y_pred"]

                            # Calculate AUC
                            fpr, tpr, _ = roc_curve(y_test, y_pred_prob)
                            auc_value = auc(fpr, tpr)

                            # Calculate precision-recall AUC
                            precision_curve, recall_curve, _ = precision_recall_curve(y_test, y_pred_prob)
                            avg_precision = auc(recall_curve, precision_curve)

                            # Calculate other metrics
                            precision = precision_score(y_test, y_pred)
                            recall = recall_score(y_test, y_pred)
                            f1 = f1_score(y_test, y_pred)

                            # Calculate confusion matrix elements
                            tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
                            fpr_value = fp / (fp + tn)
                            specificity = tn / (tn + fp)

                            # Save model
                            save_classifier(result["model"], model_file)

                            # Write results to CSV
                            with open(results_path, "a") as f:
                                f.write(f'{model_name},{dropout},"{hidden_sizes}",{optimizer_name},{weight_decay},')
                                f.write(f"{scheduler_name},{auc_value},{precision},{recall},{f1},{fpr_value},")
                                f.write(f"{result['threshold']},{result.get('val_loss', 'N/A')},{train_time},")
                                f.write(f"{specificity},{avg_precision},{fn},{fp},{tn},{tp}\n")

                            print(f"Model saved to {model_file}")
                            print(
                                f"AUC: {auc_value:.4f}, F1: {f1:.4f}, Precision: {precision:.4f}, Recall: {recall:.4f}"
                            )

                        except Exception as e:
                            print(f"Error training model with parameters: {e}")
                            # Write failure to CSV
                            with open(results_path, "a") as f:
                                f.write(f'{model_name},{dropout},"{hidden_sizes}",{optimizer_name},{weight_decay},')
                                f.write(f"{scheduler_name},FAILED,FAILED,FAILED,FAILED,FAILED,FAILED,FAILED,")
                                f.write(f"FAILED,FAILED,FAILED,FAILED,FAILED,FAILED,FAILED\n")

    print(f"\nGrid search completed. Results saved to {results_path}")
    return results_path


def visualize_grid_search_results(results_path):
    """
    Create visualization of grid search results

    Parameters:
    -----------
    results_path : str
        Path to the CSV file with results
    """
    # Load results
    df = pd.read_csv(results_path)

    # Filter out failed runs
    df = df[df["auc"] != "FAILED"]
    df["auc"] = df["auc"].astype(float)
    df["f1"] = df["f1"].astype(float)
    df["precision"] = df["precision"].astype(float)
    df["recall"] = df["recall"].astype(float)

    # Create plots
    plt.figure(figsize=(15, 10))

    # Plot histogram of AUC values
    plt.subplot(2, 2, 1)
    plt.hist(df["auc"], bins=20)
    plt.xlabel("AUC")
    plt.ylabel("Count")
    plt.title("Distribution of AUC Values")

    # Plot dropout vs AUC
    plt.subplot(2, 2, 2)
    dropout_groups = df.groupby("dropout")["auc"].mean()
    plt.bar(dropout_groups.index.astype(str), dropout_groups.values)
    plt.xlabel("Dropout")
    plt.ylabel("Average AUC")
    plt.title("Dropout vs Average AUC")

    # Plot optimizer vs AUC
    plt.subplot(2, 2, 3)
    optimizer_groups = df.groupby("optimizer")["auc"].mean()
    plt.bar(optimizer_groups.index, optimizer_groups.values)
    plt.xlabel("Optimizer")
    plt.ylabel("Average AUC")
    plt.title("Optimizer vs Average AUC")
    plt.xticks(rotation=45)

    # Plot scheduler vs AUC
    plt.subplot(2, 2, 4)
    scheduler_groups = df.groupby("scheduler")["auc"].mean()
    plt.bar(scheduler_groups.index, scheduler_groups.values)
    plt.xlabel("Scheduler")
    plt.ylabel("Average AUC")
    plt.title("Scheduler vs Average AUC")

    plt.tight_layout()
    plt.savefig(Path(results_path).parent / "grid_search_summary.png")

    # Plot top models ROC curves
    plt.figure(figsize=(12, 8))

    # Get top 5 models by AUC
    top_models = df.sort_values("auc", ascending=False).head(5)

    # Need to load models and compute ROC curves
    # This would typically be done in a follow-up analysis
    # Just showing the concept here

    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("ROC Curves for Top 5 Models")
    plt.legend()
    plt.grid(True)
    plt.savefig(Path(results_path).parent / "top_models_roc.png")


def main():
    app = pg.mkQApp()
    parser = argparse.ArgumentParser(description="Train a neural network classifier to detect healthy cells.")
    parser.add_argument("image_paths", type=Path, nargs="+", help="Path to 3D image files")
    parser.add_argument("output", type=str, help="Output file for model", default="healthy-neuron-nn-classifier.pt")
    parser.add_argument(
        "--annotation-suffix",
        "-a",
        type=str,
        help="Each image will have a corresponding annotation file with this suffix",
        default="_seg.npy",
    )
    parser.add_argument("--no-training", action="store_true", help="Skip training and only evaluate the model")
    parser.add_argument("--autoencoder", type=str, help="Path to autoencoder model")
    parser.add_argument("--diameter", type=int, default=35, help="Expected diameter of neurons for cellpose")
    parser.add_argument("--px", type=float, default=0.32e-6, help="Meters per pixel")
    parser.add_argument("--z", type=float, default=1e-6, help="Meters per z-slice")
    parser.add_argument(
        "--class-weight",
        type=float,
        default=None,
        help="Weight for positive class (higher values emphasize healthy cells)",
    )
    parser.add_argument("--rf-model", type=str, default=None, help="Path to trained RandomForest model for comparison")
    parser.add_argument(
        "--device",
        type=str,
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Device to use for training ('cuda' or 'cpu')",
    )
    parser.add_argument(
        "--grid-search",
        action="store_true",
        help="Perform grid search over hyperparameters",
    )
    parser.add_argument(
        "--grid-output-dir",
        type=str,
        default="hyperparam_search",
        help="Directory to store grid search results and models",
    )
    parser.add_argument(
        "--analyze-grid-results",
        type=str,
        help="Path to existing grid search results for analysis",
    )

    args = parser.parse_args()

    # Check if CUDA is available
    device = args.device
    print(f"Using device: {device}")

    if args.analyze_grid_results:
        print(f"Analyzing grid search results from {args.analyze_grid_results}")
        visualize_grid_search_results(args.analyze_grid_results)

        # Load and print top models
        results_df = pd.read_csv(args.analyze_grid_results)
        if not results_df.empty:
            print("\nTop 10 models by AUC:")
            top_auc = results_df.sort_values("auc", ascending=False).head(10)
            print(top_auc[["model_name", "auc", "precision", "recall", "f1"]])

            print("\nTop 10 models by F1:")
            top_f1 = results_df.sort_values("f1", ascending=False).head(10)
            print(top_f1[["model_name", "auc", "precision", "recall", "f1"]])
        return

    # Load autoencoder model
    autoencoder = NeuronAutoencoder().to(device)
    autoencoder.load_state_dict(torch.load(args.autoencoder, map_location=device)["model_state_dict"])
    autoencoder.eval()

    # Extract features and labels
    print("Extracting features and labels...")
    features, labels = get_features_and_labels(
        args.image_paths, args.annotation_suffix, autoencoder, args.diameter, args.px, args.z
    )

    print(f"Total samples: {len(features)}")
    print(f"Healthy cells: {np.sum(labels == 1)} ({np.mean(labels == 1) * 100:.1f}%)")
    print(f"Unhealthy cells: {np.sum(labels == 0)} ({np.mean(labels == 0) * 100:.1f}%)")

    if args.grid_search:
        print("\nPerforming grid search over hyperparameters...")
        results_path = grid_search_hyperparameters(
            features, labels, device, args.grid_output_dir, class_weight=args.class_weight
        )
        print(f"\nGrid search completed. Results saved to {results_path}")

        # Show top models
        try:
            results_df = pd.read_csv(results_path)
            if not results_df.empty:
                print("\nTop 5 models by AUC:")
                top_auc = results_df.sort_values("auc", ascending=False).head(5)
                print(top_auc[["model_name", "auc", "precision", "recall", "f1"]])
        except Exception as e:
            print(f"Could not read results CSV to show top models: {e}")
        return

    if args.no_training:
        model = load_classifier(args.output, device=device)
        nn_results = {
            "model": model,
            "X_test": features,
            "y_test": labels,
            "y_pred": model.predict(features),
            "y_pred_prob": model.predict_proba(features)[:, 1],
        }
    else:
        # Train neural network classifier
        nn_results = train_neural_classifier(features, labels, device=device, class_weight=args.class_weight)

        # Save the model
        save_classifier(nn_results["model"], args.output)

    # Evaluate and print metrics
    metrics = evaluate_classifier(nn_results["y_test"], nn_results["y_pred"])
    print("\nDetailed Neural Network Evaluation Metrics:")
    for metric, value in metrics.items():
        print(f"{metric}: {value}")

    # Compare with RandomForest if provided
    if args.rf_model:
        print("\nComparing with RandomForest classifier...")
        from sklearn.model_selection import train_test_split

        # Load RandomForest model
        rf_classifier = joblib.load(args.rf_model)

        # Use the same test set for fair comparison
        X_train, X_test, y_train, y_test = train_test_split(
            features, labels, test_size=0.2, stratify=labels, random_state=42
        )

        rf_pred_prob = rf_classifier.predict_proba(X_test)[:, 1]
        rf_pred = rf_classifier.predict(X_test)

        rf_results = {"y_test": y_test, "y_pred": rf_pred, "y_pred_prob": rf_pred_prob}

        # Compare models
        compare_models(rf_results, nn_results)

        print("\nRandomForest Metrics:")
        rf_metrics = evaluate_classifier(y_test, rf_pred)
        for metric, value in rf_metrics.items():
            print(f"{metric}: {value}")

        print("\nNeural Network Metrics:")
        for metric, value in metrics.items():
            print(f"{metric}: {value}")

    # Create visualizations
    visualize_training(nn_results)


if __name__ == "__main__":
    main()
