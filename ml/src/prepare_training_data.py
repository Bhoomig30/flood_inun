from pathlib import Path
import numpy as np
import rasterio
from tqdm import tqdm

# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

IMAGE_DIR = DATA / "images"
DEM_DIR = DATA / "dem_features"
LANDCOVER_DIR = DATA / "landcover_features"
LABEL_DIR = DATA / "labels"

OUTPUT_DIR = DATA / "training"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONFIGURATION
# ============================================================

EXPECTED_BANDS = 8
HEIGHT = 512
WIDTH = 512

# Label values
INVALID_LABEL = -1
NON_FLOOD = 0
FLOOD = 1

# ============================================================
# HELPERS
# ============================================================

def read_raster(path):
    with rasterio.open(path) as src:
        data = src.read()
        profile = src.profile.copy()
    return data, profile


def check_alignment(reference_profile, other_profile, name):
    if reference_profile["width"] != other_profile["width"]:
        raise ValueError(f"{name}: width mismatch")

    if reference_profile["height"] != other_profile["height"]:
        raise ValueError(f"{name}: height mismatch")

    if reference_profile["crs"] != other_profile["crs"]:
        raise ValueError(f"{name}: CRS mismatch")

    if not np.allclose(
        reference_profile["transform"],
        other_profile["transform"],
        atol=1e-9
    ):
        raise ValueError(f"{name}: transform mismatch")


# ============================================================
# FIND SCENES
# ============================================================

image_files = sorted(IMAGE_DIR.glob("*_image.tif"))

print("=" * 80)
print("PREPARING FLOOD INUNDATION ML DATASET")
print("=" * 80)

print(f"Sentinel images : {len(image_files)}")
print(f"DEM directory   : {DEM_DIR}")
print(f"Land-cover dir  : {LANDCOVER_DIR}")
print(f"Label directory : {LABEL_DIR}")
print()

# ============================================================
# STORAGE
# ============================================================

X_list = []
Y_list = []

valid_scenes = 0
skipped_scenes = 0

total_pixels = 0
valid_pixels = 0
flood_pixels = 0
non_flood_pixels = 0

# ============================================================
# PROCESS SCENES
# ============================================================

for index, image_path in enumerate(image_files, start=1):

    scene_id = image_path.stem.replace("_image", "")

    dem_path = DEM_DIR / f"{scene_id}_dem.tif"
    lc_path = LANDCOVER_DIR / f"{scene_id}_landcover.tif"
    label_path = LABEL_DIR / f"{scene_id}_label.tif"

    print(f"[{index}/{len(image_files)}] {scene_id}", end=" ")

    # --------------------------------------------------------
    # Check files
    # --------------------------------------------------------

    if not dem_path.exists():
        print("❌ DEM missing")
        skipped_scenes += 1
        continue

    if not lc_path.exists():
        print("❌ Land-cover missing")
        skipped_scenes += 1
        continue

    if not label_path.exists():
        print("❌ Label missing")
        skipped_scenes += 1
        continue

    try:

        # ----------------------------------------------------
        # Sentinel-1
        # ----------------------------------------------------

        with rasterio.open(image_path) as src:
            image = src.read().astype(np.float32)
            image_profile = src.profile.copy()

        if image.shape != (EXPECTED_BANDS, HEIGHT, WIDTH):
            print(f"❌ Image shape {image.shape}")
            skipped_scenes += 1
            continue

        # ----------------------------------------------------
        # DEM
        # ----------------------------------------------------

        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            dem_profile = src.profile.copy()

        # ----------------------------------------------------
        # WorldCover
        # ----------------------------------------------------

        with rasterio.open(lc_path) as src:
            landcover = src.read(1).astype(np.float32)
            lc_profile = src.profile.copy()

        # ----------------------------------------------------
        # Label
        # ----------------------------------------------------

        with rasterio.open(label_path) as src:
            label = src.read(1)
            label_profile = src.profile.copy()

        # ----------------------------------------------------
        # Alignment checks
        # ----------------------------------------------------

        check_alignment(image_profile, dem_profile, "DEM")
        check_alignment(image_profile, lc_profile, "WorldCover")
        check_alignment(image_profile, label_profile, "Label")

        if dem.shape != (HEIGHT, WIDTH):
            print("❌ DEM shape mismatch")
            skipped_scenes += 1
            continue

        if landcover.shape != (HEIGHT, WIDTH):
            print("❌ WorldCover shape mismatch")
            skipped_scenes += 1
            continue

        if label.shape != (HEIGHT, WIDTH):
            print("❌ Label shape mismatch")
            skipped_scenes += 1
            continue

        # ----------------------------------------------------
        # Create valid-pixel mask
        # ----------------------------------------------------

        valid_mask = (
            (label == NON_FLOOD) |
            (label == FLOOD)
        )

        # Remove invalid numerical values
        valid_mask &= np.all(np.isfinite(image), axis=0)
        valid_mask &= np.isfinite(dem)
        valid_mask &= np.isfinite(landcover)

        total_pixels += label.size
        valid_pixels += np.sum(valid_mask)

        # ----------------------------------------------------
        # Count classes
        # ----------------------------------------------------

        flood_count = np.sum((label == FLOOD) & valid_mask)
        non_flood_count = np.sum((label == NON_FLOOD) & valid_mask)

        flood_pixels += flood_count
        non_flood_pixels += non_flood_count

        # ----------------------------------------------------
        # Stack features
        # ----------------------------------------------------

        features = np.concatenate(
            [
                image,
                dem[np.newaxis, :, :],
                landcover[np.newaxis, :, :]
            ],
            axis=0
        )

        # ----------------------------------------------------
        # Convert:
        #
        # (10, 512, 512)
        #
        # to:
        #
        # (valid_pixels, 10)
        # ----------------------------------------------------

        X = features[:, valid_mask].T.astype(np.float32)

        y = label[valid_mask].astype(np.uint8)

        X_list.append(X)
        Y_list.append(y)

        valid_scenes += 1

        print(
            f"✓ valid={len(y):,} "
            f"flood={flood_count:,} "
            f"non-flood={non_flood_count:,}"
        )

    except Exception as e:

        print(f"❌ ERROR: {e}")
        skipped_scenes += 1


# ============================================================
# COMBINE ALL SCENES
# ============================================================

print()
print("=" * 80)
print("COMBINING DATA")
print("=" * 80)

if not X_list:
    raise RuntimeError("No valid scenes were processed.")

X_all = np.concatenate(X_list, axis=0)
Y_all = np.concatenate(Y_list, axis=0)

print("X shape:", X_all.shape)
print("Y shape:", Y_all.shape)

# ============================================================
# SAVE
# ============================================================

X_path = OUTPUT_DIR / "X.npy"
Y_path = OUTPUT_DIR / "y.npy"

np.save(X_path, X_all)
np.save(Y_path, Y_all)

# ============================================================
# SUMMARY
# ============================================================

print()
print("=" * 80)
print("TRAINING DATASET COMPLETE")
print("=" * 80)

print(f"Total scenes       : {len(image_files)}")
print(f"Valid scenes       : {valid_scenes}")
print(f"Skipped scenes     : {skipped_scenes}")

print(f"Total pixels       : {total_pixels:,}")
print(f"Valid pixels       : {valid_pixels:,}")

print(f"Flood pixels       : {flood_pixels:,}")
print(f"Non-flood pixels   : {non_flood_pixels:,}")

print()
print("Features per pixel : 10")
print("  8 × Sentinel-1")
print("  1 × DEM")
print("  1 × WorldCover")

print()
print("X shape:", X_all.shape)
print("Y shape:", Y_all.shape)

print()
print("Saved:")
print(X_path)
print(Y_path)

print()
print("DONE.")