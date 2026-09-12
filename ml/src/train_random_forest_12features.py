from pathlib import Path

import numpy as np

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    jaccard_score,
)
import joblib


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

TRAIN_DIR = DATA / "training_12"
MODEL_DIR = DATA / "models"

MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 80)
print("RANDOM FOREST FLOOD-INUNDATION MODEL — 12 FEATURES")
print("=" * 80)

print("\nLoading datasets...")

X_train = np.load(
    TRAIN_DIR / "X_train.npy",
    mmap_mode="r"
)

y_train = np.load(
    TRAIN_DIR / "y_train.npy",
    mmap_mode="r"
)

X_val = np.load(
    TRAIN_DIR / "X_val.npy",
    mmap_mode="r"
)

y_val = np.load(
    TRAIN_DIR / "y_val.npy",
    mmap_mode="r"
)

X_test = np.load(
    TRAIN_DIR / "X_test.npy",
    mmap_mode="r"
)

y_test = np.load(
    TRAIN_DIR / "y_test.npy",
    mmap_mode="r"
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
    "WorldCover",
    "RiverDistance",
    "RiverMask",
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
print("TRAINING RANDOM FOREST — 12 FEATURES")
print("=" * 80)

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=None,
    min_samples_split=2,
    min_samples_leaf=1,
    max_features="sqrt",
    class_weight=None,
    n_jobs=-1,
    random_state=42,
    verbose=1,
)


print("\nTraining...")

model.fit(X_train, y_train)

print("\nTraining complete.")


# ============================================================
# VALIDATION
# ============================================================

print("\n" + "=" * 80)
print("VALIDATION RESULTS")
print("=" * 80)

y_val_pred = model.predict(X_val)

accuracy = accuracy_score(y_val, y_val_pred)
precision = precision_score(
    y_val,
    y_val_pred,
    zero_division=0
)
recall = recall_score(
    y_val,
    y_val_pred,
    zero_division=0
)
f1 = f1_score(
    y_val,
    y_val_pred,
    zero_division=0
)
iou = jaccard_score(
    y_val,
    y_val_pred,
    zero_division=0
)

print(f"Accuracy : {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall   : {recall:.4f}")
print(f"F1-score : {f1:.4f}")
print(f"IoU      : {iou:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_val,
        y_val_pred,
        target_names=["Non-Flood", "Flood"],
        zero_division=0
    )
)

print("Confusion matrix:")
print(confusion_matrix(y_val, y_val_pred))


# ============================================================
# TEST
# ============================================================

print("\n" + "=" * 80)
print("TEST RESULTS")
print("=" * 80)

y_test_pred = model.predict(X_test)

accuracy = accuracy_score(y_test, y_test_pred)
precision = precision_score(
    y_test,
    y_test_pred,
    zero_division=0
)
recall = recall_score(
    y_test,
    y_test_pred,
    zero_division=0
)
f1 = f1_score(
    y_test,
    y_test_pred,
    zero_division=0
)
iou = jaccard_score(
    y_test,
    y_test_pred,
    zero_division=0
)

print(f"Accuracy : {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall   : {recall:.4f}")
print(f"F1-score : {f1:.4f}")
print(f"IoU      : {iou:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_test,
        y_test_pred,
        target_names=["Non-Flood", "Flood"],
        zero_division=0
    )
)

print("Confusion matrix:")
print(confusion_matrix(y_test, y_test_pred))


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

print("\n" + "=" * 80)
print("FEATURE IMPORTANCE")
print("=" * 80)

importance = model.feature_importances_

feature_importance = sorted(
    zip(feature_names, importance),
    key=lambda x: x[1],
    reverse=True
)

for name, value in feature_importance:
    print(f"{name:<18}: {value:.6f}")


# ============================================================
# SAVE MODEL
# ============================================================

model_path = MODEL_DIR / "random_forest_flood_12features.pkl"

joblib.dump(model, model_path)

print("\n" + "=" * 80)
print("MODEL SAVED")
print("=" * 80)

print(model_path)

print("\nDONE.")