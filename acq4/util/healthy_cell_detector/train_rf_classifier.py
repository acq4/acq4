import argparse
from pathlib import Path

import joblib
import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_curve, auc, precision_recall_curve
from sklearn.metrics import precision_score, recall_score, f1_score
from sklearn.model_selection import train_test_split, StratifiedKFold, GridSearchCV
from tifffile import tifffile

from acq4.util.healthy_cell_detector.models import NeuronAutoencoder
from acq4.util.healthy_cell_detector.utils import extract_region, cell_centers
from acq4.util.imaging.object_detection import get_cellpose_masks


def extract_features(regions, autoencoder, device="cuda"):
    autoencoder.eval()
    features = []

    # Process in batches to avoid memory issues
    batch_size = 32
    with torch.no_grad():
        for i in range(0, len(regions), batch_size):
            batch = torch.tensor(regions[i : i + batch_size]).to(device)
            batch_features = autoencoder.encode(batch).cpu().numpy()
            features.append(batch_features)

    return np.vstack(features)


def get_features_and_labels(image_paths, annotation_suffix, autoencoder, diameter, xy_scale, z_scale):
    features = []
    labels = []

    for img_path in image_paths:
        img = tifffile.imread(img_path)

        annotation_path = img_path.with_name(img_path.stem + annotation_suffix)
        annotation = np.load(annotation_path, allow_pickle=True).item()["masks"]
        healthy_cells = cell_centers(annotation, diameter)
        healthy_regions = [extract_region(img, center, xy_scale, z_scale) for center in healthy_cells]
        healthy_features = extract_features(healthy_regions, autoencoder)
        features.append(healthy_features)
        labels.append(np.ones(len(healthy_features)))

        # unhealthy cells are those whose centers are not within diameter of a healthy cell
        masks = get_cellpose_masks(img, diameter)
        any_cells = cell_centers(masks, diameter)
        unhealthy_cells = [
            cell for cell in any_cells
            if all(np.linalg.norm(np.array(cell) - np.array(good_cell)) > diameter for good_cell in healthy_cells)
        ]
        unhealthy_regions = [extract_region(img, center, xy_scale, z_scale) for center in unhealthy_cells]
        unhealthy_features = extract_features(unhealthy_regions, autoencoder)
        features.append(unhealthy_features)
        labels.append(np.zeros(len(unhealthy_features)))

    return np.vstack(features), np.hstack(labels)


def train_classifier(features, labels):
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(features, labels, test_size=0.2, stratify=labels)

    # Define a custom scorer that focuses on precision for class 1.0
    from sklearn.metrics import make_scorer, precision_score

    # Create scorer that specifically targets precision for the positive class (1.0)
    positive_precision_scorer = make_scorer(
        precision_score,
        pos_label=1.0,  # Focus on the positive class
        zero_division=0,  # Handle cases with no predicted positives
    )

    # Set up cross-validation for hyperparameter tuning
    param_grid = {
        "n_estimators": [100, 200, 300],
        "max_depth": [None, 10, 20, 30],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf": [1, 2, 4],
        "class_weight": ["balanced", {0.0: 1, 1.0: 5}, {0.0: 1, 1.0: 10}],  # Add class weight options
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True)

    # GridSearchCV with scoring focused on positive class precision
    grid_search = GridSearchCV(
        RandomForestClassifier(), param_grid=param_grid, cv=cv, scoring=positive_precision_scorer, n_jobs=-1
    )

    grid_search.fit(X_train, y_train)
    best_model = grid_search.best_estimator_

    # Get raw prediction probabilities
    y_pred_prob = best_model.predict_proba(X_test)[:, 1]

    # Find optimal threshold for precision-recall tradeoff
    precision, recall, thresholds = precision_recall_curve(y_test, y_pred_prob)

    # We want to maximize precision while maintaining some minimal recall
    # Let's find the threshold that gives at least 0.6 precision for class 1.0
    target_precision = 0.6
    valid_indices = precision[:-1] >= target_precision

    if sum(valid_indices) > 0:
        # Find the threshold that gives the best recall while meeting precision requirement
        best_idx = np.argmax(recall[:-1][valid_indices])
        optimal_threshold = thresholds[valid_indices][best_idx]
    else:
        # If no threshold meets our precision target, use a high threshold
        optimal_threshold = 0.8  # Conservative threshold

    print(f"Optimal threshold for class 1.0 prediction: {optimal_threshold:.3f}")

    # Apply the optimal threshold
    y_pred = (y_pred_prob >= optimal_threshold).astype(int)

    print("\nClassification Report with optimized threshold:")
    print(classification_report(y_test, y_pred))

    thresholded_model = ThresholdClassifier(best_model, optimal_threshold)

    return thresholded_model, X_test, y_test, y_pred, y_pred_prob


class ThresholdClassifier:
    def __init__(self, base_classifier, threshold):
        self.base_classifier = base_classifier
        self.threshold = threshold

    def predict(self, X):
        probas = self.base_classifier.predict_proba(X)[:, 1]
        return (probas >= self.threshold).astype(int)

    def predict_proba(self, X):
        return self.base_classifier.predict_proba(X)


def evaluate_classifier(y_true, y_pred):
    from sklearn.metrics import confusion_matrix

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


def visualize_precision_recall_tradeoff(y_test, y_pred_prob):
    from sklearn.metrics import precision_recall_curve
    import matplotlib.pyplot as plt

    precision, recall, thresholds = precision_recall_curve(y_test, y_pred_prob)

    # Calculate false positive rate at each threshold
    fpr = []
    for threshold in thresholds:
        y_pred = (y_pred_prob >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        fpr.append(fp / (fp + tn))

    # Add the last precision and recall points
    thresholds = np.append(thresholds, 1.0)
    fpr.append(0)  # At threshold 1.0, FPR should be 0

    # Plot precision-recall curve
    plt.figure(figsize=(12, 5))

    plt.subplot(1, 2, 1)
    plt.plot(thresholds, precision[:-1], "b--", label="Precision")
    plt.plot(thresholds, recall[:-1], "g-", label="Recall")
    plt.xlabel("Threshold")
    plt.ylabel("Score")
    plt.title("Precision and Recall vs. Threshold")
    plt.legend()
    plt.grid(True)

    plt.subplot(1, 2, 2)
    plt.plot(thresholds, fpr, "r-", label="False Positive Rate")
    plt.xlabel("Threshold")
    plt.ylabel("False Positive Rate")
    plt.title("False Positive Rate vs. Threshold")
    plt.legend()
    plt.grid(True)

    plt.tight_layout()
    plt.show()

    # Return the data for further analysis if needed
    return {"thresholds": thresholds, "precision": precision, "recall": recall, "false_positive_rate": fpr}


def save_classifier(classifier, path):
    """
    Save the trained classifier to a file

    Parameters:
    -----------
    classifier : Classifier object
        Trained classifier to save
    path : str
        Path where to save the classifier
    """
    joblib.dump(classifier, path)
    print(f"Classifier saved to {path}")


def visualize_training(best_model, y_pred_prob, y_test):
    # Calculate and plot ROC curve
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


def get_health_ordered_cells(image, classifier, autoencoder, diameter, xy_scale, z_scale, device="cuda"):
    """
    Use a trained classifier to identify healthy neurons in new images

    Parameters:
    -----------
    image : numpy.ndarray
        3D image data
    classifier : Classifier object with predict_proba method
        Trained classifier for healthy neuron detection
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
    results : list of coordinates
        List of neuron coordinates ordered by health status
    """
    masks = get_cellpose_masks(image, diameter)
    cells = np.array(list(cell_centers(masks, diameter)))
    regions = [extract_region(image, center, xy_scale, z_scale) for center in cells]
    features = extract_features(regions, autoencoder, device)
    probabilities = classifier.predict_proba(features)[:, 1]  # Probability of being healthy

    # Sort cells by probability of being healthy
    return cells[np.argsort(-probabilities)]


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
    parser.add_argument("--diameter", type=int, default=35, help="Expected diameter of neurons for cellpose")
    parser.add_argument("--px", type=float, default=0.32e-6, help="Meters per pixel")
    parser.add_argument("--z", type=float, default=1e-6, help="Meters per z-slice")
    parser.add_argument(
        "--target-precision", type=float, default=0.6, help="Target precision for the positive class (healthy cells)"
    )
    args = parser.parse_args()

    autoencoder = NeuronAutoencoder().to("cuda" if torch.cuda.is_available() else "cpu")
    autoencoder.load_state_dict(torch.load(args.autoencoder)["model_state_dict"])
    autoencoder.eval()

    features, labels = get_features_and_labels(
        args.image_paths, args.annotation_suffix, autoencoder, args.diameter, args.px, args.z
    )

    classifier, x_test, y_test, y_pred, y_pred_prob = train_classifier(features, labels)
    save_classifier(classifier, args.output)

    # Evaluate and print metrics
    metrics = evaluate_classifier(y_test, y_pred)
    print("\nDetailed Evaluation Metrics:")
    for metric, value in metrics.items():
        print(f"{metric}: {value}")

    # Create additional visualizations
    visualize_training(classifier.base_classifier, y_pred_prob, y_test)
    visualize_precision_recall_tradeoff(y_test, y_pred_prob)


if __name__ == "__main__":
    main()
