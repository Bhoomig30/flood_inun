from pathlib import Path

import joblib
import numpy as np
import rasterio

from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    jaccard_score,
)


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

IMAGE_DIR = DATA / "images"
DEM_DIR = DATA / "dem_features"
LC_DIR = DATA / "landcover_features"
RIVER_DIR = DATA / "river_features"
LABEL_DIR = DATA / "labels"

VAL_FILE = DATA / "split" / "val.txt"

MODEL_PATH = (
    DATA / "models" /
    "random_forest_flood_12features.pkl"
)


# ============================================================
# THRESHOLDS
# ============================================================

THRESHOLDS = [
    0.30,
    0.35,
    0.40,
    0.45,
    0.50,
    0.55,
    0.60,
    0.65,
    0.70,
    0.75,
]


# ============================================================
# LOAD VALIDATION SCENES
# ============================================================

print("=" * 80)
print("FLOOD PROBABILITY THRESHOLD OPTIMIZATION")
print("=" * 80)

with open(
    VAL_FILE,
    "r",
    encoding="utf-8"
) as f:

    scene_ids = [
        line.strip()
        for line in f
        if line.strip()
    ]

print("\nValidation scenes:", len(scene_ids))


# ============================================================
# LOAD MODEL
# ============================================================

print("\nLoading model...")

model = joblib.load(MODEL_PATH)

print("Model:", type(model).__name__)


# ============================================================
# PROCESS VALIDATION SCENES
# ============================================================

all_true = []
all_probability = []

successful = 0
failed = 0


for index, scene_id in enumerate(
    scene_ids,
    1
):

    print(
        f"\n[{index}/{len(scene_ids)}] {scene_id}"
    )

    try:

        image_path = (
            IMAGE_DIR /
            f"{scene_id}_image.tif"
        )

        dem_path = (
            DEM_DIR /
            f"{scene_id}_dem.tif"
        )

        lc_path = (
            LC_DIR /
            f"{scene_id}_landcover.tif"
        )

        river_distance_path = (
            RIVER_DIR /
            f"{scene_id}_river_distance.tif"
        )

        river_mask_path = (
            RIVER_DIR /
            f"{scene_id}_river_mask.tif"
        )

        label_path = (
            LABEL_DIR /
            f"{scene_id}_label.tif"
        )

        required = [
            image_path,
            dem_path,
            lc_path,
            river_distance_path,
            river_mask_path,
            label_path,
        ]

        missing = [
            str(p)
            for p in required
            if not p.exists()
        ]

        if missing:

            print("  Missing files:")
            for p in missing:
                print("   ", p)

            failed += 1
            continue

        # ----------------------------------------------------
        # Read Sentinel-1
        # ----------------------------------------------------

        with rasterio.open(
            image_path
        ) as src:

            image = src.read().astype(
                np.float32
            )

        # ----------------------------------------------------
        # Read DEM
        # ----------------------------------------------------

        with rasterio.open(
            dem_path
        ) as src:

            dem = src.read(1).astype(
                np.float32
            )

        # ----------------------------------------------------
        # Read WorldCover
        # ----------------------------------------------------

        with rasterio.open(
            lc_path
        ) as src:

            landcover = src.read(1).astype(
                np.float32
            )

        # ----------------------------------------------------
        # Read river distance
        # ----------------------------------------------------

        with rasterio.open(
            river_distance_path
        ) as src:

            river_distance = src.read(1).astype(
                np.float32
            )

        # ----------------------------------------------------
        # Read river mask
        # ----------------------------------------------------

        with rasterio.open(
            river_mask_path
        ) as src:

            river_mask = src.read(1).astype(
                np.float32
            )

        # ----------------------------------------------------
        # Read ground truth
        # ----------------------------------------------------

        with rasterio.open(
            label_path
        ) as src:

            label = src.read(1)

        # ----------------------------------------------------
        # Build 12 features
        # ----------------------------------------------------

        height, width = label.shape

        s1 = image.reshape(
            8,
            -1
        ).T

        X = np.column_stack([
            s1,
            dem.reshape(-1),
            landcover.reshape(-1),
            river_distance.reshape(-1),
            river_mask.reshape(-1),
        ]).astype(np.float32)

        y = label.reshape(-1)

        # ----------------------------------------------------
        # Valid pixels
        # ----------------------------------------------------

        valid = (
            (y == 0) |
            (y == 1)
        )

        valid &= np.isfinite(
            X
        ).all(axis=1)

        if valid.sum() == 0:

            print(
                "  No valid pixels - skipped"
            )

            failed += 1
            continue

        X_valid = X[valid]

        y_valid = y[valid].astype(
            np.uint8
        )

        # ----------------------------------------------------
        # Flood probability
        # ----------------------------------------------------

        probability = model.predict_proba(
            X_valid
        )[:, 1]

        all_true.append(
            y_valid
        )

        all_probability.append(
            probability
        )

        successful += 1

        print(
            f"  Valid pixels: {len(y_valid):,}"
        )

    except Exception as e:

        print(
            f"  ERROR: {e}"
        )

        failed += 1


# ============================================================
# COMBINE VALIDATION DATA
# ============================================================

if not all_true:

    raise RuntimeError(
        "No validation scenes were successfully processed."
    )

y_true = np.concatenate(
    all_true
)

probabilities = np.concatenate(
    all_probability
)


print("\n" + "=" * 80)
print("VALIDATION DATA READY")
print("=" * 80)

print(
    f"\nScenes successfully processed: "
    f"{successful}/{len(scene_ids)}"
)

print(
    f"Scenes failed/skipped: "
    f"{failed}"
)

print(
    f"Total valid pixels: "
    f"{len(y_true):,}"
)

print(
    f"Actual flood pixels: "
    f"{int((y_true == 1).sum()):,}"
)

print(
    f"Actual flood percentage: "
    f"{(y_true == 1).mean() * 100:.2f}%"
)


# ============================================================
# THRESHOLD TESTING
# ============================================================

print("\n" + "=" * 80)
print("THRESHOLD RESULTS")
print("=" * 80)

print(
    "\nThreshold | Precision | Recall | F1 | IoU | Flood %"
)

print("-" * 80)


results = []


for threshold in THRESHOLDS:

    y_pred = (
        probabilities >= threshold
    ).astype(np.uint8)

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

    flood_percentage = (
        y_pred.mean() * 100
    )

    results.append({
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "iou": iou,
        "flood_percentage": flood_percentage,
    })

    print(
        f"{threshold:9.2f} | "
        f"{precision:9.4f} | "
        f"{recall:6.4f} | "
        f"{f1:6.4f} | "
        f"{iou:6.4f} | "
        f"{flood_percentage:7.2f}%"
    )


# ============================================================
# FIND BEST THRESHOLDS
# ============================================================

best_f1 = max(
    results,
    key=lambda x: x["f1"]
)

best_iou = max(
    results,
    key=lambda x: x["iou"]
)


# ============================================================
# FINAL RECOMMENDATION
# ============================================================

print("\n" + "=" * 80)
print("OPTIMAL THRESHOLD")
print("=" * 80)

print("\nBest threshold by F1:")
print(
    f"Threshold : {best_f1['threshold']:.2f}"
)
print(
    f"Precision : {best_f1['precision']:.4f}"
)
print(
    f"Recall    : {best_f1['recall']:.4f}"
)
print(
    f"F1        : {best_f1['f1']:.4f}"
)
print(
    f"IoU       : {best_f1['iou']:.4f}"
)
print(
    f"Flood %   : {best_f1['flood_percentage']:.2f}%"
)


print("\nBest threshold by IoU:")
print(
    f"Threshold : {best_iou['threshold']:.2f}"
)
print(
    f"Precision : {best_iou['precision']:.4f}"
)
print(
    f"Recall    : {best_iou['recall']:.4f}"
)
print(
    f"F1        : {best_iou['f1']:.4f}"
)
print(
    f"IoU       : {best_iou['iou']:.4f}"
)
print(
    f"Flood %   : {best_iou['flood_percentage']:.2f}%"
)


# ============================================================
# CURRENT 0.50 BASELINE
# ============================================================

baseline = next(
    r for r in results
    if r["threshold"] == 0.50
)

print("\n" + "=" * 80)
print("CURRENT 0.50 BASELINE")
print("=" * 80)

print(
    f"Precision : {baseline['precision']:.4f}"
)

print(
    f"Recall    : {baseline['recall']:.4f}"
)

print(
    f"F1        : {baseline['f1']:.4f}"
)

print(
    f"IoU       : {baseline['iou']:.4f}"
)

print(
    f"Flood %   : {baseline['flood_percentage']:.2f}%"
)


# ============================================================
# IMPROVEMENT
# ============================================================

print("\n" + "=" * 80)
print("IMPROVEMENT OVER 0.50")
print("=" * 80)

print(
    f"\nF1 improvement: "
    f"{(best_f1['f1'] - baseline['f1']):+.4f}"
)

print(
    f"IoU improvement: "
    f"{(best_iou['iou'] - baseline['iou']):+.4f}"
)


print("\n" + "=" * 80)
print("THRESHOLD OPTIMIZATION COMPLETE")
print("=" * 80)