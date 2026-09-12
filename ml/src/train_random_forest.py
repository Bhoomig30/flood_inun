from pathlib import Path
import numpy as np
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    jaccard_score
)

# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
TRAINING = DATA / "training"
MODEL_DIR = DATA / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# LOAD DATA
# ============================================================

print("=" * 80)
print("RANDOM FOREST FLOOD-INUNDATION MODEL")
print("=" * 80)

print("\nLoading datasets...")

X_train = np.load(
    TRAINING / "X_train.npy"
)

y_train = np.load(
    TRAINING / "y_train.npy"
)

X_val = np.load(
    TRAINING / "X_val.npy"
)

y_val = np.load(
    TRAINING / "y_val.npy"
)

X_test = np.load(
    TRAINING / "X_test.npy"
)

y_test = np.load(
    TRAINING / "y_test.npy"
)

print("\nDataset shapes:")
print("Train:", X_train.shape, y_train.shape)
print("Validation:", X_val.shape, y_val.shape)
print("Test:", X_test.shape, y_test.shape)

# ============================================================
# FEATURE NAMES
# ============================================================

feature_names = [
    "S1_B1",
    "S1_B2",
    "S1_B3",
    "S1_B4",
    "S1_B5",
    "S1_B6",
    "S1_B7",
    "S1_B8",
    "DEM",
    "WorldCover"
]

# ============================================================
# CLASS DISTRIBUTION
# ============================================================

print("\nTraining class distribution:")
print("Flood:", int((y_train == 1).sum()))
print("Non-flood:", int((y_train == 0).sum()))

print("\nValidation class distribution:")
print("Flood:", int((y_val == 1).sum()))
print("Non-flood:", int((y_val == 0).sum()))

print("\nTest class distribution:")
print("Flood:", int((y_test == 1).sum()))
print("Non-flood:", int((y_test == 0).sum()))

# ============================================================
# RANDOM FOREST
# ============================================================

print("\n" + "=" * 80)
print("TRAINING RANDOM FOREST")
print("=" * 80)

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=25,
    min_samples_leaf=3,
    max_features="sqrt",
    class_weight="balanced",
    n_jobs=-1,
    random_state=42,
    verbose=1
)

print("\nTraining...")

model.fit(
    X_train,
    y_train
)

print("\nTraining complete.")

# ============================================================
# VALIDATION
# ============================================================

print("\n" + "=" * 80)
print("VALIDATION RESULTS")
print("=" * 80)

val_pred = model.predict(X_val)

val_accuracy = accuracy_score(
    y_val,
    val_pred
)

val_precision = precision_score(
    y_val,
    val_pred,
    zero_division=0
)

val_recall = recall_score(
    y_val,
    val_pred,
    zero_division=0
)

val_f1 = f1_score(
    y_val,
    val_pred,
    zero_division=0
)

val_iou = jaccard_score(
    y_val,
    val_pred,
    zero_division=0
)

print(f"\nAccuracy : {val_accuracy:.4f}")
print(f"Precision: {val_precision:.4f}")
print(f"Recall   : {val_recall:.4f}")
print(f"F1-score : {val_f1:.4f}")
print(f"IoU      : {val_iou:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_val,
        val_pred,
        target_names=[
            "Non-Flood",
            "Flood"
        ],
        zero_division=0
    )
)

print("\nConfusion matrix:")
print(
    confusion_matrix(
        y_val,
        val_pred
    )
)

# ============================================================
# TEST
# ============================================================

print("\n" + "=" * 80)
print("TEST RESULTS")
print("=" * 80)

test_pred = model.predict(X_test)

test_accuracy = accuracy_score(
    y_test,
    test_pred
)

test_precision = precision_score(
    y_test,
    test_pred,
    zero_division=0
)

test_recall = recall_score(
    y_test,
    test_pred,
    zero_division=0
)

test_f1 = f1_score(
    y_test,
    test_pred,
    zero_division=0
)

test_iou = jaccard_score(
    y_test,
    test_pred,
    zero_division=0
)

print(f"\nAccuracy : {test_accuracy:.4f}")
print(f"Precision: {test_precision:.4f}")
print(f"Recall   : {test_recall:.4f}")
print(f"F1-score : {test_f1:.4f}")
print(f"IoU      : {test_iou:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_test,
        test_pred,
        target_names=[
            "Non-Flood",
            "Flood"
        ],
        zero_division=0
    )
)

print("\nConfusion matrix:")
print(
    confusion_matrix(
        y_test,
        test_pred
    )
)

# ============================================================
# FEATURE IMPORTANCE
# ============================================================

print("\n" + "=" * 80)
print("FEATURE IMPORTANCE")
print("=" * 80)

importance = model.feature_importances_

ranking = sorted(
    zip(feature_names, importance),
    key=lambda x: x[1],
    reverse=True
)

for name, score in ranking:
    print(
        f"{name:12s}: {score:.6f}"
    )

# ============================================================
# SAVE MODEL
# ============================================================

model_path = MODEL_DIR / "random_forest_flood.pkl"

joblib.dump(
    model,
    model_path
)

print("\n" + "=" * 80)
print("MODEL SAVED")
print("=" * 80)

print(model_path)

print("\nDONE.")