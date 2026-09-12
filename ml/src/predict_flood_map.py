from pathlib import Path

import joblib
import numpy as np
import rasterio


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

SCENE_ID = "1017769"

IMAGE = DATA / "images" / f"{SCENE_ID}_image.tif"
DEM = DATA / "dem_features" / f"{SCENE_ID}_dem.tif"
LANDCOVER = DATA / "landcover_features" / f"{SCENE_ID}_landcover.tif"
RIVER_DISTANCE = DATA / "river_features" / f"{SCENE_ID}_river_distance.tif"
RIVER_MASK = DATA / "river_features" / f"{SCENE_ID}_river_mask.tif"

MODEL = DATA / "models" / "random_forest_flood_12features.pkl"

OUTPUT_DIR = DATA / "predictions"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FLOOD_OUTPUT = OUTPUT_DIR / f"{SCENE_ID}_predicted_flood.tif"
PROB_OUTPUT = OUTPUT_DIR / f"{SCENE_ID}_flood_probability.tif"


# ============================================================
# OPTIMIZED FLOOD THRESHOLD
# ============================================================

# Validation optimization selected 0.65
FLOOD_THRESHOLD = 0.65


# ============================================================
# CHECK FILES
# ============================================================

print("=" * 80)
print("FLOOD INUNDATION MAP GENERATION")
print("=" * 80)

print("\nScene:", SCENE_ID)
print("Flood probability threshold:", FLOOD_THRESHOLD)

files = {
    "Sentinel-1": IMAGE,
    "DEM": DEM,
    "WorldCover": LANDCOVER,
    "River distance": RIVER_DISTANCE,
    "River mask": RIVER_MASK,
    "Model": MODEL,
}

for name, path in files.items():

    if not path.exists():
        raise FileNotFoundError(
            f"{name} file not found:\n{path}"
        )

    print(f"OK {name}: {path.name}")


# ============================================================
# LOAD FEATURES
# ============================================================

print("\n" + "=" * 80)
print("LOADING FEATURES")
print("=" * 80)


# ------------------------------------------------------------
# Sentinel-1
# ------------------------------------------------------------

with rasterio.open(IMAGE) as src:

    image = src.read().astype(np.float32)

    profile = src.profile.copy()
    transform = src.transform
    crs = src.crs

    height = src.height
    width = src.width


print("\nSentinel-1:")
print("Bands:", image.shape[0])
print("Size:", width, "x", height)
print("CRS:", crs)


# ------------------------------------------------------------
# DEM
# ------------------------------------------------------------

with rasterio.open(DEM) as src:
    dem = src.read(1).astype(np.float32)


# ------------------------------------------------------------
# WorldCover
# ------------------------------------------------------------

with rasterio.open(LANDCOVER) as src:
    landcover = src.read(1).astype(np.float32)


# ------------------------------------------------------------
# River distance
# ------------------------------------------------------------

with rasterio.open(RIVER_DISTANCE) as src:
    river_distance = src.read(1).astype(np.float32)


# ------------------------------------------------------------
# River mask
# ------------------------------------------------------------

with rasterio.open(RIVER_MASK) as src:
    river_mask = src.read(1).astype(np.float32)


print("DEM:", dem.shape)
print("WorldCover:", landcover.shape)
print("River distance:", river_distance.shape)
print("River mask:", river_mask.shape)


# ============================================================
# BUILD 12-FEATURE MATRIX
# ============================================================

print("\n" + "=" * 80)
print("BUILDING 12-FEATURE MATRIX")
print("=" * 80)


# Sentinel-1:
# B1 B2 B3 B4 B5 B6 B7 B8
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
]).astype(np.float32)


print("Feature matrix:", X.shape)


# ============================================================
# VALID PIXEL CHECK
# ============================================================

print("\nChecking feature values...")

valid = np.isfinite(X).all(axis=1)

print("Total pixels:", len(X))
print("Valid pixels:", int(valid.sum()))
print("Invalid pixels:", int((~valid).sum()))


if valid.sum() == 0:
    raise RuntimeError(
        "No valid pixels available for prediction."
    )


X_valid = X[valid]


# ============================================================
# LOAD RANDOM FOREST
# ============================================================

print("\n" + "=" * 80)
print("LOADING RANDOM FOREST")
print("=" * 80)

model = joblib.load(MODEL)

print("Model loaded:")
print(type(model).__name__)


# ============================================================
# GENERATE FLOOD PROBABILITY
# ============================================================

print("\n" + "=" * 80)
print("GENERATING FLOOD PROBABILITY")
print("=" * 80)

print(
    f"Predicting probability for "
    f"{len(X_valid):,} valid pixels..."
)


# IMPORTANT:
# We use predict_proba instead of predict()
# because the optimized threshold is 0.65.

probability = model.predict_proba(
    X_valid
)[:, 1]


# ============================================================
# CREATE FLOOD MASK USING 0.65
# ============================================================

print("\n" + "=" * 80)
print("GENERATING FLOOD PREDICTION")
print("=" * 80)

print(
    f"Using flood probability threshold: "
    f"{FLOOD_THRESHOLD}"
)


prediction_valid = (
    probability >= FLOOD_THRESHOLD
).astype(np.uint8)


# ============================================================
# RECONSTRUCT FULL-SIZE ARRAYS
# ============================================================

prediction = np.zeros(
    len(X),
    dtype=np.uint8
)

prediction[valid] = prediction_valid


probability_full = np.zeros(
    len(X),
    dtype=np.float32
)

probability_full[valid] = probability


prediction = prediction.reshape(
    height,
    width
)

probability_full = probability_full.reshape(
    height,
    width
)


# ============================================================
# PREDICTION STATISTICS
# ============================================================

flood_pixels = int(
    (prediction == 1).sum()
)

total_pixels = prediction.size

flood_percentage = (
    flood_pixels /
    total_pixels *
    100
)


print("\n" + "=" * 80)
print("PREDICTION STATISTICS")
print("=" * 80)

print("Total pixels:", total_pixels)
print("Flood pixels:", flood_pixels)

print(
    f"Flood percentage: "
    f"{flood_percentage:.2f}%"
)

print(
    f"Probability min: "
    f"{probability.min():.4f}"
)

print(
    f"Probability max: "
    f"{probability.max():.4f}"
)

print(
    f"Probability mean: "
    f"{probability.mean():.4f}"
)


# ============================================================
# SAVE FLOOD MASK
# ============================================================

print("\n" + "=" * 80)
print("SAVING FLOOD MASK")
print("=" * 80)


mask_profile = profile.copy()

mask_profile.update(
    dtype="uint8",
    count=1,
    compress="lzw",
    nodata=0
)


with rasterio.open(
    FLOOD_OUTPUT,
    "w",
    **mask_profile
) as dst:

    dst.write(
        prediction,
        1
    )


print("Saved:")
print(FLOOD_OUTPUT)


# ============================================================
# SAVE FLOOD PROBABILITY
# ============================================================

print("\n" + "=" * 80)
print("SAVING FLOOD PROBABILITY")
print("=" * 80)


prob_profile = profile.copy()

prob_profile.update(
    dtype="float32",
    count=1,
    compress="lzw"
)


with rasterio.open(
    PROB_OUTPUT,
    "w",
    **prob_profile
) as dst:

    dst.write(
        probability_full.astype(
            np.float32
        ),
        1
    )


print("Saved:")
print(PROB_OUTPUT)


# ============================================================
# FINAL VERIFICATION
# ============================================================

print("\n" + "=" * 80)
print("FINAL VERIFICATION")
print("=" * 80)


with rasterio.open(
    FLOOD_OUTPUT
) as src:

    mask_check = src.read(1)

    print("\nFlood mask:")
    print(
        "Size:",
        src.width,
        "x",
        src.height
    )

    print("CRS:", src.crs)
    print("Bounds:", src.bounds)
    print("Dtype:", src.dtypes[0])
    print(
        "Classes:",
        np.unique(mask_check)
    )


with rasterio.open(
    PROB_OUTPUT
) as src:

    prob_check = src.read(1)

    print("\nProbability:")
    print(
        "Size:",
        src.width,
        "x",
        src.height
    )

    print("CRS:", src.crs)
    print("Dtype:", src.dtypes[0])

    print(
        "Min:",
        float(prob_check.min())
    )

    print(
        "Max:",
        float(prob_check.max())
    )


print("\n" + "=" * 80)
print("FLOOD MAP GENERATION COMPLETE")
print("=" * 80)

print("\nFlood mask:")
print(FLOOD_OUTPUT)

print("\nProbability map:")
print(PROB_OUTPUT)

print("\nThreshold used:", FLOOD_THRESHOLD)

print("\nDONE.")