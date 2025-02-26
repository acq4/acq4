import argparse
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_curve, auc
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split, StratifiedKFold, GridSearchCV
from tqdm import tqdm

from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
from acq4.util.healthy_cell_detector.utils import extract_region, detect_and_extract_normalized_neurons
from acq4.util.imaging.object_detection import detect_neurons, get_cellpose_masks


def extract_features(regions, autoencoder, device='cuda'):
    autoencoder.eval()
    features = []

    # Process in batches to avoid memory issues
    batch_size = 32
    with torch.no_grad():
        for i in range(0, len(regions), batch_size):
            batch = torch.tensor(regions[i:i+batch_size]).to(device)
            batch_features = autoencoder.encode(batch).cpu().numpy()
            features.append(batch_features)

    return np.vstack(features)


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


def train_classifier(features, labels):
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.2, random_state=42, stratify=labels
    )

    # Set up cross-validation for hyperparameter tuning
    param_grid = {
        'n_estimators': [50, 100, 200],
        'max_depth': [None, 10, 20, 30],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4]
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    # GridSearchCV with small parameter grid due to limited data
    grid_search = GridSearchCV(
        RandomForestClassifier(random_state=42, class_weight='balanced'),
        param_grid=param_grid,
        cv=cv,
        scoring='f1',
        n_jobs=-1
    )

    grid_search.fit(X_train, y_train)
    best_model = grid_search.best_estimator_

    # Evaluate on test set
    y_pred = best_model.predict(X_test)
    y_pred_prob = best_model.predict_proba(X_test)[:, 1]

    print(f"Best parameters: {grid_search.best_params_}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    # Calculate and plot ROC curve
    fpr, tpr, _ = roc_curve(y_test, y_pred_prob)
    roc_auc = auc(fpr, tpr)

    plt.figure(figsize=(10, 8))
    plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (area = {roc_auc:.2f})')
    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('Receiver Operating Characteristic')
    plt.legend(loc="lower right")
    plt.show()

    # Calculate feature importance
    importances = best_model.feature_importances_
    indices = np.argsort(importances)[::-1]

    plt.figure(figsize=(10, 8))
    plt.title("Feature Importances")
    plt.bar(range(len(importances)), importances[indices], align="center")
    plt.xticks(range(len(importances)), indices)
    plt.xlim([-1, min(10, len(importances))])
    plt.show()

    return best_model, X_test, y_test, y_pred, y_pred_prob


def evaluate_classifier(y_true, y_pred):
    return {
        "precision": precision_score(y_true, y_pred),
        "recall": recall_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred),
    }


def save_classifier(classifier, path):
    """
    Save the trained Random Forest classifier to a file

    Parameters:
    -----------
    classifier : RandomForestClassifier
        Trained classifier to save
    path : str
        Path where to save the classifier
    """
    joblib.dump(classifier, path)
    print(f"Classifier saved to {path}")


def load_classifier(path):
    """
    Load a trained Random Forest classifier from a file

    Parameters:
    -----------
    path : str
        Path to the saved classifier

    Returns:
    --------
    classifier : RandomForestClassifier
        Loaded classifier
    """
    return joblib.load(path)


def healthy_neuron_classification_pipeline(images, labels, diameter, xy_scale, z_scale, autoencoder, save_path):
    """
    End-to-end pipeline for healthy neuron classification

    Parameters:
    -----------
    images : list
        List of slice images
    labels : numpy.ndarray
        Masks for known healthy neurons
    diameter : float
        Expected diameter of neurons for cellpose
    xy_scale : float
        Scale factor for xy dimensions
    z_scale : float
        Scale factor for z dimension
    autoencoder : Autoencoder
        Pretrained autoencoder
    save_path : str
        Path to save the trained classifier

    Returns:
    --------
    classifier : RandomForestClassifier
        Trained classifier
    evaluation_metrics : dict
        Dictionary containing evaluation metrics
    """
    all_regions = []
    all_masks = []

    # Process each image
    for img in tqdm(images, desc="Processing images"):
        mask = get_cellpose_masks(img, diameter, xy_scale, z_scale)
        regions = detect_and_extract_normalized_neurons(img, autoencoder, diameter, xy_scale, z_scale)
        all_regions.append(regions)
        all_masks.append(mask)

    # Combine regions from all images
    regions = np.vstack(all_regions)

    # Extract features
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    features = extract_features(regions, autoencoder, device)

    # Train classifier
    classifier, X_test, y_test, y_pred, y_pred_prob = train_classifier(features, labels)

    # Compute evaluation metrics
    evaluation_metrics = {
        'accuracy': (y_pred == y_test).mean(),
        'confusion_matrix': confusion_matrix(y_test, y_pred),
        'classification_report': classification_report(y_test, y_pred, output_dict=True)
    }

    # Save classifier if path is provided
    if save_path:
        save_classifier(classifier, save_path)

    return classifier, evaluation_metrics


def classify_new_images(image_paths, classifier, autoencoder, diameter, xy_scale, z_scale, device='cuda'):
    """
    Use a trained classifier to identify healthy neurons in new images

    Parameters:
    -----------
    image_paths : list
        List of paths to new neuron images
    classifier : RandomForestClassifier
        Trained classifier
    autoencoder : Autoencoder
        Trained autoencoder for feature extraction
    diameter : float
        Expected diameter of neurons for cellpose
    xy_scale : float
        Scale factor for xy dimensions
    z_scale : float
        Scale factor for z dimension
    device : str
        Device to use for autoencoder inference

    Returns:
    --------
    results : list of dicts
        List of dictionaries containing results for each image
    """
    results = []

    for img_path in tqdm(image_paths, desc="Classifying new images"):
        img = np.load(img_path)  # Adjust loading method as needed
        regions, mask = detect_neurons(img, diameter, xy_scale, z_scale)

        # Extract features
        features = extract_features(regions, autoencoder, device)

        # Predict
        predictions = classifier.predict(features)
        probabilities = classifier.predict_proba(features)[:, 1]  # Probability of being healthy

        # Create a mask of only healthy neurons
        healthy_mask = np.zeros_like(mask)
        healthy_indices = [i for i, pred in enumerate(predictions) if pred == 1]

        for i, cell_idx in enumerate(np.unique(mask)[1:]):  # Skip 0 (background)
            if i in healthy_indices:
                healthy_mask[mask == cell_idx] = cell_idx

        results.append({
            'image_path': img_path,
            'all_neurons_mask': mask,
            'healthy_neurons_mask': healthy_mask,
            'predictions': predictions,
            'probabilities': probabilities,
            'num_total': len(predictions),
            'num_healthy': sum(predictions)
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Train a classifier to detect healthy cells.")
    parser.add_argument("image_paths", type=Path, nargs="+", help="Path to 3D image files")
    parser.add_argument("output", type=str, help="Output file for model", default="healthy-neuron-classifier.joblib")
    parser.add_argument(
        "--annotation-suffix",
        "-a",
        type=str,
        help="Each image will have a corresponding annotation file with this suffix",
        default="_seg.npy",
    )
    parser.add_argument("--autoencoder", type=str, help="Path to autoencoder model")
    parser.add_argument("--px", type=float, default=0.32, help="Microns per pixel")
    parser.add_argument("--z", type=float, default=1, help="Microns per z-slice")
    args = parser.parse_args()
    autoencoder = NeuronAutoencoder()
    autoencoder.load_state_dict(torch.load(args.autoencoder)["model_state_dict"])
    classifier = build_classifier()


if __name__ == "__main__":
    main()
