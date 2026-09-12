from pathlib import Path
import numpy as np
import rasterio

# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

IMAGE_DIR = DATA / "images"
DEM_DIR = DATA / "dem_features"
LC_DIR = DATA / "landcover_features"
LABEL_DIR = DATA / "labels"
SPLIT_DIR = DATA / "split"

OUTPUT_DIR = DATA / "training"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# SETTINGS
# ============================================================

# Number of pixels sampled from each scene
TRAIN_PIXELS_PER_SCENE = 10000
VAL_PIXELS_PER_SCENE = 5000
TEST_PIXELS_PER_SCENE = 5000

# Maximum flood/non-flood ratio
# 1.0 = perfectly balanced
BALANCE_TRAIN = True

RANDOM_SEED = 42

rng = np.random.default_rng(RANDOM_SEED)


# ============================================================
# READ SPLITS
# ============================================================

def read_split(filename):
    path = SPLIT_DIR / filename

    with open(path, "r", encoding="utf-8") as f:
        ids = [
            line.strip()
            for line in f
            if line.strip()
        ]

    return ids


train_ids = read_split("train.txt")
val_ids = read_split("val.txt")
test_ids = read_split("test.txt")


print("=" * 80)
print("CREATING SCENE-BASED ML DATASETS")
print("=" * 80)

print()
print("Train scenes:", len(train_ids))
print("Validation scenes:", len(val_ids))
print("Test scenes:", len(test_ids))


# ============================================================
# LOAD ONE SCENE
# ============================================================

def load_scene(scene_id):

    image_path = IMAGE_DIR / f"{scene_id}_image.tif"
    dem_path = DEM_DIR / f"{scene_id}_dem.tif"
    lc_path = LC_DIR / f"{scene_id}_landcover.tif"
    label_path = LABEL_DIR / f"{scene_id}_label.tif"

    if not image_path.exists():
        raise FileNotFoundError(image_path)

    if not dem_path.exists():
        raise FileNotFoundError(dem_path)

    if not lc_path.exists():
        raise FileNotFoundError(lc_path)

    if not label_path.exists():
        raise FileNotFoundError(label_path)

    with rasterio.open(image_path) as src:
        image = src.read().astype(np.float32)

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float32)

    with rasterio.open(lc_path) as src:
        landcover = src.read(1)

    with rasterio.open(label_path) as src:
        label = src.read(1)

    return image, dem, landcover, label


# ============================================================
# SAMPLE PIXELS
# ============================================================

def process_scene(scene_id, max_pixels, balance=False):

    image, dem, landcover, label = load_scene(scene_id)

    # --------------------------------------------------------
    # Shape check
    # --------------------------------------------------------

    if image.shape[0] != 8:
        raise ValueError(
            f"{scene_id}: expected 8 Sentinel bands, "
            f"got {image.shape[0]}"
        )

    if image.shape[1:] != dem.shape:
        raise ValueError(f"{scene_id}: image/DEM shape mismatch")

    if image.shape[1:] != landcover.shape:
        raise ValueError(
            f"{scene_id}: image/landcover shape mismatch"
        )

    if image.shape[1:] != label.shape:
        raise ValueError(
            f"{scene_id}: image/label shape mismatch"
        )

    # --------------------------------------------------------
    # Flatten
    # --------------------------------------------------------

    image = image.reshape(8, -1).T
    dem = dem.reshape(-1)
    landcover = landcover.reshape(-1)
    label = label.reshape(-1)

    # --------------------------------------------------------
    # Valid label pixels
    #
    # Sen1Floods11 labels:
    #   -1 = invalid
    #    0 = non-flood
    #    1 = flood
    # --------------------------------------------------------

    valid = (label == 0) | (label == 1)

    image = image[valid]
    dem = dem[valid]
    landcover = landcover[valid]
    label = label[valid]

    if len(label) == 0:
        return None, None

    # --------------------------------------------------------
    # Remove invalid feature values
    # --------------------------------------------------------

    finite = (
        np.isfinite(image).all(axis=1)
        & np.isfinite(dem)
        & np.isfinite(landcover)
    )

    image = image[finite]
    dem = dem[finite]
    landcover = landcover[finite]
    label = label[finite]

    if len(label) == 0:
        return None, None

    # --------------------------------------------------------
    # Balance flood / non-flood
    # --------------------------------------------------------

    if balance:

        flood_idx = np.where(label == 1)[0]
        nonflood_idx = np.where(label == 0)[0]

        if len(flood_idx) > 0 and len(nonflood_idx) > 0:

            n = min(len(flood_idx), len(nonflood_idx))

            flood_idx = rng.choice(
                flood_idx,
                size=n,
                replace=False
            )

            nonflood_idx = rng.choice(
                nonflood_idx,
                size=n,
                replace=False
            )

            indices = np.concatenate(
                [flood_idx, nonflood_idx]
            )

            rng.shuffle(indices)

            image = image[indices]
            dem = dem[indices]
            landcover = landcover[indices]
            label = label[indices]

    # --------------------------------------------------------
    # Limit pixels per scene
    # --------------------------------------------------------

    if len(label) > max_pixels:

        indices = rng.choice(
            len(label),
            size=max_pixels,
            replace=False
        )

        image = image[indices]
        dem = dem[indices]
        landcover = landcover[indices]
        label = label[indices]

    # --------------------------------------------------------
    # Build 10-feature matrix
    #
    # 8 Sentinel bands
    # 1 DEM
    # 1 WorldCover
    # --------------------------------------------------------

    X = np.column_stack([
        image,
        dem,
        landcover
    ]).astype(np.float32)

    y = label.astype(np.uint8)

    return X, y


# ============================================================
# PROCESS SPLIT
# ============================================================

def create_dataset(
    scene_ids,
    name,
    pixels_per_scene,
    balance=False
):

    X_list = []
    y_list = []

    print()
    print("=" * 80)
    print(f"PROCESSING {name.upper()}")
    print("=" * 80)

    for i, scene_id in enumerate(scene_ids, 1):

        try:

            X, y = process_scene(
                scene_id,
                pixels_per_scene,
                balance
            )

            if X is None:
                print(
                    f"[{i}/{len(scene_ids)}] "
                    f"{scene_id} SKIPPED"
                )
                continue

            X_list.append(X)
            y_list.append(y)

            print(
                f"[{i}/{len(scene_ids)}] "
                f"{scene_id} "
                f"pixels={len(y):,} "
                f"flood={int((y == 1).sum()):,} "
                f"non-flood={int((y == 0).sum()):,}"
            )

        except Exception as e:

            print(
                f"[{i}/{len(scene_ids)}] "
                f"{scene_id} ERROR: {e}"
            )

    if not X_list:
        raise RuntimeError(
            f"No valid scenes found for {name}"
        )

    X = np.concatenate(X_list, axis=0)
    y = np.concatenate(y_list, axis=0)

    print()
    print(f"{name} X:", X.shape)
    print(f"{name} y:", y.shape)
    print(
        f"{name} flood:",
        int((y == 1).sum())
    )
    print(
        f"{name} non-flood:",
        int((y == 0).sum())
    )

    np.save(
        OUTPUT_DIR / f"X_{name}.npy",
        X
    )

    np.save(
        OUTPUT_DIR / f"y_{name}.npy",
        y
    )

    return X, y


# ============================================================
# CREATE DATASETS
# ============================================================

X_train, y_train = create_dataset(
    train_ids,
    "train",
    TRAIN_PIXELS_PER_SCENE,
    BALANCE_TRAIN
)

X_val, y_val = create_dataset(
    val_ids,
    "val",
    VAL_PIXELS_PER_SCENE,
    False
)

X_test, y_test = create_dataset(
    test_ids,
    "test",
    TEST_PIXELS_PER_SCENE,
    False
)


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 80)
print("ML DATASET CREATION COMPLETE")
print("=" * 80)

print()
print("TRAIN")
print(" X:", X_train.shape)
print(" y:", y_train.shape)

print()
print("VALIDATION")
print(" X:", X_val.shape)
print(" y:", y_val.shape)

print()
print("TEST")
print(" X:", X_test.shape)
print(" y:", y_test.shape)

print()
print("Saved to:")
print(OUTPUT_DIR)

print()
print("Files:")
print("  X_train.npy")
print("  y_train.npy")
print("  X_val.npy")
print("  y_val.npy")
print("  X_test.npy")
print("  y_test.npy")

print()
print("DONE.")