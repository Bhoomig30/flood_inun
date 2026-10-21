from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import rasterio

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    jaccard_score,
    confusion_matrix,
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

IMAGE_DIR = DATA / "images"
DEM_DIR = DATA / "dem_features"
LANDCOVER_DIR = DATA / "landcover_features"
RIVER_DIR = DATA / "river_features"
LABEL_DIR = DATA / "labels"

SPLIT_FILE = DATA / "split" / "test.txt"

MODEL_PATH = (
    DATA / "models" /
    "random_forest_flood_12features.pkl"
)

OUTPUT_DIR = DATA / "test_predictions"
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

RESULTS_FILE = (
    OUTPUT_DIR /
    "test_scene_results_threshold_065.csv"
)

# ------------------------------------------------------------
# Optimized threshold
# ------------------------------------------------------------

FLOOD_THRESHOLD = 0.65


# ============================================================
# HEADER
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 TEST-SCENE EVALUATION")
print("12-FEATURE RANDOM FOREST")
print("OPTIMIZED FLOOD THRESHOLD = 0.65")
print("=" * 80)


# ============================================================
# CHECK PATHS
# ============================================================

print("\n" + "=" * 80)
print("CHECKING DATA")
print("=" * 80)

required_paths = {
    "Image directory": IMAGE_DIR,
    "DEM directory": DEM_DIR,
    "Land-cover directory": LANDCOVER_DIR,
    "River directory": RIVER_DIR,
    "Label directory": LABEL_DIR,
    "Test split": SPLIT_FILE,
    "Model": MODEL_PATH,
}

for name, path in required_paths.items():

    if not path.exists():

        raise FileNotFoundError(
            f"{name} not found:\n{path}"
        )

    print(f"OK {name}: {path}")


# ============================================================
# LOAD TEST SCENE IDS
# ============================================================

print("\n" + "=" * 80)
print("LOADING TEST SCENES")
print("=" * 80)


with open(
    SPLIT_FILE,
    "r",
    encoding="utf-8"
) as f:

    scene_ids = [
        line.strip()
        for line in f
        if line.strip()
    ]


print(
    f"Test scenes: {len(scene_ids)}"
)

print(
    f"Flood threshold: {FLOOD_THRESHOLD}"
)


# ============================================================
# LOAD MODEL
# ============================================================

print("\n" + "=" * 80)
print("LOADING RANDOM FOREST")
print("=" * 80)


model = joblib.load(
    MODEL_PATH
)


print(
    "Model:",
    type(model).__name__
)


# ============================================================
# FEATURE NAMES
# ============================================================

FEATURE_NAMES = [
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
# RESULTS STORAGE
# ============================================================

results = []


# ============================================================
# PROCESS EACH TEST SCENE
# ============================================================

for index, scene_id in enumerate(
    scene_ids,
    1
):

    print("\n" + "=" * 80)

    print(
        f"[{index}/{len(scene_ids)}] SCENE: {scene_id}"
    )

    print("=" * 80)


    # --------------------------------------------------------
    # Paths
    # --------------------------------------------------------

    image_path = (
        IMAGE_DIR /
        f"{scene_id}_image.tif"
    )

    dem_path = (
        DEM_DIR /
        f"{scene_id}_dem.tif"
    )

    landcover_path = (
        LANDCOVER_DIR /
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
        landcover_path,
        river_distance_path,
        river_mask_path,
        label_path,
    ]


    missing = [
        p for p in required
        if not p.exists()
    ]


    if missing:

        print("\nMissing files:")

        for p in missing:
            print(
                " ",
                p
            )

        print(
            "Skipping scene."
        )

        continue


    try:

        # ====================================================
        # LOAD SENTINEL-1
        # ====================================================

        with rasterio.open(
            image_path
        ) as src:

            image = src.read().astype(
                np.float32
            )

            profile = src.profile.copy()

            height = src.height
            width = src.width


        # ====================================================
        # LOAD DEM
        # ====================================================

        with rasterio.open(
            dem_path
        ) as src:

            dem = src.read(1).astype(
                np.float32
            )


        # ====================================================
        # LOAD WORLDCOVER
        # ====================================================

        with rasterio.open(
            landcover_path
        ) as src:

            landcover = src.read(1).astype(
                np.float32
            )


        # ====================================================
        # LOAD RIVER DISTANCE
        # ====================================================

        with rasterio.open(
            river_distance_path
        ) as src:

            river_distance = src.read(1).astype(
                np.float32
            )


        # ====================================================
        # LOAD RIVER MASK
        # ====================================================

        with rasterio.open(
            river_mask_path
        ) as src:

            river_mask = src.read(1).astype(
                np.float32
            )


        # ====================================================
        # LOAD GROUND TRUTH
        # ====================================================

        with rasterio.open(
            label_path
        ) as src:

            label = src.read(1)


        # ====================================================
        # CHECK DIMENSIONS
        # ====================================================

        if label.shape != (
            height,
            width
        ):

            raise ValueError(
                f"Label shape {label.shape} "
                f"does not match image "
                f"{(height, width)}"
            )


        # ====================================================
        # BUILD 12 FEATURES
        # ====================================================

        s1_features = image.reshape(
            image.shape[0],
            -1
        ).T


        X = np.column_stack([
            s1_features,
            dem.reshape(-1),
            landcover.reshape(-1),
            river_distance.reshape(-1),
            river_mask.reshape(-1),
        ]).astype(
            np.float32
        )


        y = label.reshape(-1)


        # ====================================================
        # VALID PIXELS
        # ====================================================

        valid = (
            (y == 0) |
            (y == 1)
        )


        valid &= np.isfinite(
            X
        ).all(
            axis=1
        )


        valid_pixels = int(
            valid.sum()
        )


        ignored_pixels = int(
            (~valid).sum()
        )


        if valid_pixels == 0:

            print(
                "No valid pixels. Skipping."
            )

            continue


        X_valid = X[valid]

        y_true = y[valid].astype(
            np.uint8
        )


        # ====================================================
        # PREDICT FLOOD PROBABILITY
        # ====================================================

        print(
            f"Valid pixels: "
            f"{valid_pixels:,}"
        )

        print(
            "Generating flood probabilities..."
        )


        probability = model.predict_proba(
            X_valid
        )[:, 1]


        # ====================================================
        # APPLY OPTIMIZED THRESHOLD
        # ====================================================

        y_pred = (
            probability >= FLOOD_THRESHOLD
        ).astype(
            np.uint8
        )


        # ====================================================
        # METRICS
        # ====================================================

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


        # ====================================================
        # CONFUSION MATRIX
        # ====================================================

        cm = confusion_matrix(
            y_true,
            y_pred,
            labels=[0, 1]
        )


        tn = int(
            cm[0, 0]
        )

        fp = int(
            cm[0, 1]
        )

        fn = int(
            cm[1, 0]
        )

        tp = int(
            cm[1, 1]
        )


        # ====================================================
        # FLOOD AREAS
        # ====================================================

        actual_flood = int(
            (y_true == 1).sum()
        )


        predicted_flood = int(
            (y_pred == 1).sum()
        )


        actual_flood_pct = (
            actual_flood /
            valid_pixels
        ) * 100


        predicted_flood_pct = (
            predicted_flood /
            valid_pixels
        ) * 100


        # ====================================================
        # ERROR RATES
        # ====================================================

        false_positive_rate = (
            fp /
            (fp + tn)
            if (fp + tn) > 0
            else 0.0
        )


        false_negative_rate = (
            fn /
            (fn + tp)
            if (fn + tp) > 0
            else 0.0
        )


        # ====================================================
        # CREATE FULL PREDICTION RASTER
        # ====================================================

        full_prediction = np.zeros(
            len(y),
            dtype=np.uint8
        )


        full_prediction[valid] = y_pred


        full_prediction = (
            full_prediction.reshape(
                height,
                width
            )
        )


        # ====================================================
        # SAVE PREDICTION RASTER
        # ====================================================

        prediction_path = (
            OUTPUT_DIR /
            f"{scene_id}_predicted_flood_065.tif"
        )


        output_profile = profile.copy()


        output_profile.update(
            dtype="uint8",
            count=1,
            compress="lzw",
            nodata=0
        )


        with rasterio.open(
            prediction_path,
            "w",
            **output_profile
        ) as dst:

            dst.write(
                full_prediction,
                1
            )


        # ====================================================
        # PRINT SCENE RESULTS
        # ====================================================

        print("\nScene results:")

        print(
            f"Accuracy : {accuracy:.4f}"
        )

        print(
            f"Precision: {precision:.4f}"
        )

        print(
            f"Recall   : {recall:.4f}"
        )

        print(
            f"F1-score : {f1:.4f}"
        )

        print(
            f"IoU      : {iou:.4f}"
        )

        print(
            f"Actual flood: "
            f"{actual_flood_pct:.2f}%"
        )

        print(
            f"Predicted flood: "
            f"{predicted_flood_pct:.2f}%"
        )

        print(
            f"False-positive rate: "
            f"{false_positive_rate:.4f}"
        )

        print(
            f"False-negative rate: "
            f"{false_negative_rate:.4f}"
        )


        print(
            f"Prediction saved: "
            f"{prediction_path.name}"
        )


        # ====================================================
        # STORE RESULTS
        # ====================================================

        results.append({

            "scene": scene_id,

            "valid_pixels": valid_pixels,

            "ignored_pixels": ignored_pixels,

            "actual_flood_pixels": actual_flood,

            "predicted_flood_pixels": predicted_flood,

            "actual_flood_pct":
                actual_flood_pct,

            "predicted_flood_pct":
                predicted_flood_pct,

            "accuracy":
                accuracy,

            "precision":
                precision,

            "recall":
                recall,

            "f1":
                f1,

            "iou":
                iou,

            "true_negatives":
                tn,

            "false_positives":
                fp,

            "false_negatives":
                fn,

            "true_positives":
                tp,

            "false_positive_rate":
                false_positive_rate,

            "false_negative_rate":
                false_negative_rate,

            "threshold":
                FLOOD_THRESHOLD,
        })


    except Exception as e:

        print(
            f"\nERROR processing "
            f"{scene_id}:"
        )

        print(e)

        continue


# ============================================================
# CHECK RESULTS
# ============================================================

if not results:

    raise RuntimeError(
        "No test scenes were successfully evaluated."
    )


# ============================================================
# CREATE RESULTS DATAFRAME
# ============================================================

df = pd.DataFrame(
    results
)


# ============================================================
# SAVE CSV
# ============================================================

df.to_csv(
    RESULTS_FILE,
    index=False
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n" + "=" * 80)
print("FINAL TEST-SET RESULTS")
print("=" * 80)


print(
    "\nScenes evaluated:",
    len(df)
)


print(
    "Threshold:",
    FLOOD_THRESHOLD
)


# ------------------------------------------------------------
# Mean metrics
# ------------------------------------------------------------

mean_accuracy = df[
    "accuracy"
].mean()


mean_precision = df[
    "precision"
].mean()


mean_recall = df[
    "recall"
].mean()


mean_f1 = df[
    "f1"
].mean()


mean_iou = df[
    "iou"
].mean()


median_iou = df[
    "iou"
].median()


print("\nMean scene-level metrics:")

print(
    f"Accuracy : {mean_accuracy:.4f}"
)

print(
    f"Precision: {mean_precision:.4f}"
)

print(
    f"Recall   : {mean_recall:.4f}"
)

print(
    f"F1-score : {mean_f1:.4f}"
)

print(
    f"IoU      : {mean_iou:.4f}"
)


print("\nMedian scene-level IoU:")

print(
    f"{median_iou:.4f}"
)


# ============================================================
# FLOOD AREA SUMMARY
# ============================================================

mean_actual_flood = df[
    "actual_flood_pct"
].mean()


mean_predicted_flood = df[
    "predicted_flood_pct"
].mean()


print("\nFlood-area statistics:")

print(
    f"Mean actual flood area: "
    f"{mean_actual_flood:.2f}%"
)

print(
    f"Mean predicted flood area: "
    f"{mean_predicted_flood:.2f}%"
)


# ============================================================
# ERROR SUMMARY
# ============================================================

mean_fpr = df[
    "false_positive_rate"
].mean()


mean_fnr = df[
    "false_negative_rate"
].mean()


print("\nError statistics:")

print(
    f"Mean false-positive rate: "
    f"{mean_fpr:.4f}"
)

print(
    f"Mean false-negative rate: "
    f"{mean_fnr:.4f}"
)


# ============================================================
# BEST SCENES
# ============================================================

print("\n" + "=" * 80)
print("BEST 10 SCENES BY IoU")
print("=" * 80)


best = df.sort_values(
    "iou",
    ascending=False
).head(10)


print(
    best[
        [
            "scene",
            "iou",
            "f1",
            "precision",
            "recall",
            "actual_flood_pct",
            "predicted_flood_pct",
        ]
    ].to_string(
        index=False
    )
)


# ============================================================
# WORST SCENES
# ============================================================

print("\n" + "=" * 80)
print("WORST 10 SCENES BY IoU")
print("=" * 80)


worst = df.sort_values(
    "iou",
    ascending=True
).head(10)


print(
    worst[
        [
            "scene",
            "iou",
            "f1",
            "precision",
            "recall",
            "actual_flood_pct",
            "predicted_flood_pct",
        ]
    ].to_string(
        index=False
    )
)


# ============================================================
# SCENES WITH HIGH IOU
# ============================================================

print("\n" + "=" * 80)
print("IOU DISTRIBUTION")
print("=" * 80)


print(
    "IoU >= 0.90:",
    int(
        (df["iou"] >= 0.90).sum()
    )
)


print(
    "IoU >= 0.75:",
    int(
        (df["iou"] >= 0.75).sum()
    )
)


print(
    "IoU >= 0.50:",
    int(
        (df["iou"] >= 0.50).sum()
    )
)


print(
    "IoU < 0.50:",
    int(
        (df["iou"] < 0.50).sum()
    )
)


# ============================================================
# RESULTS FILE
# ============================================================

print("\n" + "=" * 80)
print("RESULTS SAVED")
print("=" * 80)


print(
    RESULTS_FILE
)


print("\n" + "=" * 80)
print("TEST-SCENE EVALUATION COMPLETE")
print("=" * 80)