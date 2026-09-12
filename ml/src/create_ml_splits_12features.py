from pathlib import Path
import numpy as np
import rasterio

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

IMAGE_DIR = DATA / "images"
DEM_DIR = DATA / "dem_features"
LC_DIR = DATA / "landcover_features"
RIVER_DIR = DATA / "river_features"
LABEL_DIR = DATA / "labels"
SPLIT_DIR = DATA / "split"

OUTPUT_DIR = DATA / "training_12"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_PIXELS_PER_SCENE = 10000
VAL_PIXELS_PER_SCENE = 5000
TEST_PIXELS_PER_SCENE = 5000

BALANCE_TRAIN = True
RANDOM_SEED = 42

rng = np.random.default_rng(RANDOM_SEED)


def read_split(filename):
    with open(SPLIT_DIR / filename, "r", encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip()]


train_ids = read_split("train.txt")
val_ids = read_split("val.txt")
test_ids = read_split("test.txt")


def load_scene(scene_id):

    paths = {
        "image": IMAGE_DIR / f"{scene_id}_image.tif",
        "dem": DEM_DIR / f"{scene_id}_dem.tif",
        "landcover": LC_DIR / f"{scene_id}_landcover.tif",
        "river_distance": RIVER_DIR / f"{scene_id}_river_distance.tif",
        "river_mask": RIVER_DIR / f"{scene_id}_river_mask.tif",
        "label": LABEL_DIR / f"{scene_id}_label.tif",
    }

    for name, path in paths.items():
        if not path.exists():
            raise FileNotFoundError(f"{name}: {path}")

    with rasterio.open(paths["image"]) as src:
        image = src.read().astype(np.float32)
        profile = src.profile.copy()

    with rasterio.open(paths["dem"]) as src:
        dem = src.read(1).astype(np.float32)

    with rasterio.open(paths["landcover"]) as src:
        landcover = src.read(1).astype(np.float32)

    with rasterio.open(paths["river_distance"]) as src:
        river_distance = src.read(1).astype(np.float32)

    with rasterio.open(paths["river_mask"]) as src:
        river_mask = src.read(1).astype(np.float32)

    with rasterio.open(paths["label"]) as src:
        label = src.read(1)

    if image.shape != (8, 512, 512):
        raise ValueError(f"{scene_id}: image shape {image.shape}")

    for name, arr in [
        ("DEM", dem),
        ("WorldCover", landcover),
        ("River distance", river_distance),
        ("River mask", river_mask),
        ("Label", label),
    ]:
        if arr.shape != (512, 512):
            raise ValueError(
                f"{scene_id}: {name} shape {arr.shape}"
            )

    return (
        image,
        dem,
        landcover,
        river_distance,
        river_mask,
        label,
    )


def process_scene(scene_id, max_pixels, balance):

    (
        image,
        dem,
        landcover,
        river_distance,
        river_mask,
        label,
    ) = load_scene(scene_id)

    # Flatten all spatial dimensions
    image = image.reshape(8, -1).T
    dem = dem.reshape(-1)
    landcover = landcover.reshape(-1)
    river_distance = river_distance.reshape(-1)
    river_mask = river_mask.reshape(-1)
    label = label.reshape(-1)

    # Only labels 0 and 1 are valid
    valid = (label == 0) | (label == 1)

    image = image[valid]
    dem = dem[valid]
    landcover = landcover[valid]
    river_distance = river_distance[valid]
    river_mask = river_mask[valid]
    label = label[valid]

    # Remove invalid numeric feature values
    valid_features = (
        np.isfinite(image).all(axis=1)
        & np.isfinite(dem)
        & np.isfinite(landcover)
        & np.isfinite(river_distance)
        & np.isfinite(river_mask)
    )

    image = image[valid_features]
    dem = dem[valid_features]
    landcover = landcover[valid_features]
    river_distance = river_distance[valid_features]
    river_mask = river_mask[valid_features]
    label = label[valid_features]

    if len(label) == 0:
        return None, None

    # Balance training pixels
    if balance:

        flood = np.where(label == 1)[0]
        nonflood = np.where(label == 0)[0]

        if len(flood) > 0 and len(nonflood) > 0:

            n = min(len(flood), len(nonflood))

            flood = rng.choice(
                flood,
                n,
                replace=False
            )

            nonflood = rng.choice(
                nonflood,
                n,
                replace=False
            )

            indices = np.concatenate([flood, nonflood])
            rng.shuffle(indices)

            image = image[indices]
            dem = dem[indices]
            landcover = landcover[indices]
            river_distance = river_distance[indices]
            river_mask = river_mask[indices]
            label = label[indices]

    # Limit pixels per scene
    if len(label) > max_pixels:

        indices = rng.choice(
            len(label),
            max_pixels,
            replace=False
        )

        image = image[indices]
        dem = dem[indices]
        landcover = landcover[indices]
        river_distance = river_distance[indices]
        river_mask = river_mask[indices]
        label = label[indices]

    # 12 FEATURES
    #
    # 1-8  Sentinel-1
    # 9    DEM
    # 10   WorldCover
    # 11   River distance
    # 12   River mask

    X = np.column_stack([
        image,
        dem,
        landcover,
        river_distance,
        river_mask
    ]).astype(np.float32)

    y = label.astype(np.uint8)

    return X, y


def create_dataset(scene_ids, name, pixels_per_scene, balance):

    X_parts = []
    y_parts = []

    print()
    print("=" * 80)
    print(name.upper())
    print("=" * 80)

    for i, scene_id in enumerate(scene_ids, 1):

        try:

            X, y = process_scene(
                scene_id,
                pixels_per_scene,
                balance
            )

            if X is None:
                print(f"[{i}/{len(scene_ids)}] {scene_id} SKIPPED")
                continue

            X_parts.append(X)
            y_parts.append(y)

            print(
                f"[{i}/{len(scene_ids)}] {scene_id} "
                f"pixels={len(y):,} "
                f"flood={(y == 1).sum():,} "
                f"nonflood={(y == 0).sum():,}"
            )

        except Exception as e:
            print(
                f"[{i}/{len(scene_ids)}] "
                f"{scene_id} ERROR: {e}"
            )

    if not X_parts:
        raise RuntimeError(f"No valid scenes for {name}")

    X = np.concatenate(X_parts)
    y = np.concatenate(y_parts)

    np.save(OUTPUT_DIR / f"X_{name}.npy", X)
    np.save(OUTPUT_DIR / f"y_{name}.npy", y)

    print()
    print(f"{name} X shape: {X.shape}")
    print(f"{name} y shape: {y.shape}")

    print(
        f"Flood: {(y == 1).sum():,}"
    )

    print(
        f"Non-flood: {(y == 0).sum():,}"
    )

    return X, y


print("=" * 80)
print("CREATING 12-FEATURE FLOOD ML DATASET")
print("=" * 80)

print("Train scenes:", len(train_ids))
print("Validation scenes:", len(val_ids))
print("Test scenes:", len(test_ids))

X_train, y_train = create_dataset(
    train_ids,
    "train",
    TRAIN_PIXELS_PER_SCENE,
    True
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

print()
print("=" * 80)
print("12-FEATURE DATASET COMPLETE")
print("=" * 80)

print("Train:", X_train.shape, y_train.shape)
print("Val  :", X_val.shape, y_val.shape)
print("Test :", X_test.shape, y_test.shape)

print()
print("Features:")
print("1-8  Sentinel-1")
print("9    DEM")
print("10   WorldCover")
print("11   River distance")
print("12   River mask")

print()
print("Output:", OUTPUT_DIR)