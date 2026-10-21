from pathlib import Path

import numpy as np
import rasterio
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    jaccard_score,
    confusion_matrix,
)


BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

SCENE_ID = "1017769"

PREDICTION = (
    DATA / "predictions" /
    f"{SCENE_ID}_predicted_flood.tif"
)

LABEL = (
    DATA / "labels" /
    f"{SCENE_ID}_label.tif"
)


print("=" * 80)
print("FLOOD MAP VALIDATION")
print("=" * 80)

print("\nScene:", SCENE_ID)


# ============================================================
# CHECK FILES
# ============================================================

if not PREDICTION.exists():
    raise FileNotFoundError(
        f"Prediction not found:\n{PREDICTION}"
    )

if not LABEL.exists():
    raise FileNotFoundError(
        f"Label not found:\n{LABEL}"
    )


# ============================================================
# READ PREDICTION
# ============================================================

with rasterio.open(PREDICTION) as src:

    prediction = src.read(1)

    pred_shape = prediction.shape
    pred_crs = src.crs
    pred_transform = src.transform


# ============================================================
# READ GROUND TRUTH
# ============================================================

with rasterio.open(LABEL) as src:

    label = src.read(1)

    label_shape = label.shape
    label_crs = src.crs
    label_transform = src.transform


print("\nPrediction:")
print("Shape:", pred_shape)
print("CRS:", pred_crs)
print("Classes:", np.unique(prediction))

print("\nGround truth:")
print("Shape:", label_shape)
print("CRS:", label_crs)
print("Classes:", np.unique(label))


# ============================================================
# GEOMETRIC CHECK
# ============================================================

if pred_shape != label_shape:
    raise ValueError(
        f"Shape mismatch: "
        f"{pred_shape} vs {label_shape}"
    )

if pred_crs != label_crs:
    raise ValueError(
        f"CRS mismatch: "
        f"{pred_crs} vs {label_crs}"
    )


# ============================================================
# VALID LABEL PIXELS
# ============================================================

# SEN1FLOODS11 labels:
# -1 = invalid / ignored
#  0 = non-flood
#  1 = flood

valid = (label == 0) | (label == 1)

y_true = label[valid].astype(np.uint8)
y_pred = prediction[valid].astype(np.uint8)


print("\n" + "=" * 80)
print("VALID PIXELS")
print("=" * 80)

print("Total pixels:", prediction.size)
print("Valid pixels:", len(y_true))
print("Ignored pixels:", int((~valid).sum()))


# ============================================================
# FLOOD COVERAGE
# ============================================================

actual_flood = int((y_true == 1).sum())
predicted_flood = int((y_pred == 1).sum())

actual_flood_pct = (
    actual_flood / len(y_true)
) * 100

predicted_flood_pct = (
    predicted_flood / len(y_pred)
) * 100


print("\nActual flood pixels:", actual_flood)
print(
    f"Actual flood percentage: "
    f"{actual_flood_pct:.2f}%"
)

print("\nPredicted flood pixels:", predicted_flood)
print(
    f"Predicted flood percentage: "
    f"{predicted_flood_pct:.2f}%"
)


# ============================================================
# METRICS
# ============================================================

accuracy = accuracy_score(
    y_true,
    y_pred
)

precision = precision_score(
    y_true,
    y_pred,
    zero_division=0
)

recall = recall_score(
    y_true,
    y_pred,
    zero_division=0
)

f1 = f1_score(
    y_true,
    y_pred,
    zero_division=0
)

iou = jaccard_score(
    y_true,
    y_pred,
    zero_division=0
)


# ============================================================
# RESULTS
# ============================================================

print("\n" + "=" * 80)
print("SCENE-LEVEL RESULTS")
print("=" * 80)

print(f"Accuracy : {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall   : {recall:.4f}")
print(f"F1-score : {f1:.4f}")
print(f"IoU      : {iou:.4f}")


# ============================================================
# CONFUSION MATRIX
# ============================================================

cm = confusion_matrix(
    y_true,
    y_pred
)

print("\nConfusion matrix:")
print(cm)

tn, fp, fn, tp = cm.ravel()

print("\nTrue Negatives :", tn)
print("False Positives:", fp)
print("False Negatives:", fn)
print("True Positives :", tp)


# ============================================================
# ERROR ANALYSIS
# ============================================================

print("\n" + "=" * 80)
print("ERROR ANALYSIS")
print("=" * 80)

print(
    f"False-positive rate: "
    f"{fp / (fp + tn):.4f}"
)

print(
    f"False-negative rate: "
    f"{fn / (fn + tp):.4f}"
)

print(
    f"Flood detection recall: "
    f"{tp / (tp + fn):.4f}"
)


# ============================================================
# FINAL
# ============================================================

print("\n" + "=" * 80)
print("VALIDATION COMPLETE")
print("=" * 80)