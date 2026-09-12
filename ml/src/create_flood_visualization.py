from pathlib import Path

import numpy as np
import rasterio
import matplotlib.pyplot as plt


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

SCENE_ID = "1017769"

IMAGE = DATA / "images" / f"{SCENE_ID}_image.tif"
FLOOD_MASK = DATA / "predictions" / f"{SCENE_ID}_predicted_flood.tif"
PROBABILITY = DATA / "predictions" / f"{SCENE_ID}_flood_probability.tif"

OUTPUT_DIR = DATA / "visualizations"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PNG = OUTPUT_DIR / f"{SCENE_ID}_flood_visualization.png"


# ============================================================
# START
# ============================================================

print("=" * 80)
print("FLOOD INUNDATION VISUALIZATION")
print("=" * 80)

print("\nScene:", SCENE_ID)


# ============================================================
# CHECK FILES
# ============================================================

for name, path in {
    "Sentinel-1": IMAGE,
    "Flood mask": FLOOD_MASK,
    "Probability": PROBABILITY,
}.items():

    if not path.exists():
        raise FileNotFoundError(
            f"{name} file not found:\n{path}"
        )

    print(f"OK {name}: {path.name}")


# ============================================================
# LOAD SENTINEL-1
# ============================================================

print("\n" + "=" * 80)
print("LOADING SENTINEL-1")
print("=" * 80)

with rasterio.open(IMAGE) as src:

    image = src.read().astype(np.float32)

    image_crs = src.crs
    image_transform = src.transform

print("Bands:", image.shape[0])
print("Height:", image.shape[1])
print("Width:", image.shape[2])
print("CRS:", image_crs)


# ============================================================
# LOAD FLOOD MASK
# ============================================================

print("\n" + "=" * 80)
print("LOADING FLOOD MASK")
print("=" * 80)

with rasterio.open(FLOOD_MASK) as src:

    flood_mask = src.read(1)

    mask_crs = src.crs

print("Shape:", flood_mask.shape)
print("CRS:", mask_crs)
print("Classes:", np.unique(flood_mask))


# ============================================================
# LOAD PROBABILITY
# ============================================================

print("\n" + "=" * 80)
print("LOADING FLOOD PROBABILITY")
print("=" * 80)

with rasterio.open(PROBABILITY) as src:

    probability = src.read(1).astype(np.float32)

print("Shape:", probability.shape)
print("Minimum:", float(probability.min()))
print("Maximum:", float(probability.max()))


# ============================================================
# VALIDATE DIMENSIONS
# ============================================================

if image.shape[1:] != flood_mask.shape:
    raise ValueError(
        "Sentinel-1 and flood mask dimensions do not match."
    )

if flood_mask.shape != probability.shape:
    raise ValueError(
        "Flood mask and probability dimensions do not match."
    )


# ============================================================
# FLOOD STATISTICS
# ============================================================

flood = flood_mask == 1

flood_pixels = int(flood.sum())
total_pixels = flood.size

flood_percentage = (
    flood_pixels /
    total_pixels *
    100
)

print("\n" + "=" * 80)
print("FLOOD STATISTICS")
print("=" * 80)

print("Total pixels:", total_pixels)
print("Flood pixels:", flood_pixels)
print(f"Flood percentage: {flood_percentage:.2f}%")


# ============================================================
# NORMALIZATION
# ============================================================

def stretch_band(band):

    band = np.nan_to_num(
        band,
        nan=0.0,
        posinf=0.0,
        neginf=0.0
    )

    low = np.percentile(band, 2)
    high = np.percentile(band, 98)

    if high <= low:

        return np.zeros_like(
            band,
            dtype=np.float32
        )

    band = np.clip(
        band,
        low,
        high
    )

    return (
        band - low
    ) / (
        high - low
    )


# ============================================================
# CREATE FALSE-COLOR IMAGE
# ============================================================

print("\n" + "=" * 80)
print("CREATING SATELLITE VISUALIZATION")
print("=" * 80)

# Sentinel-1 channels used:
#
# Channel 3 -> Green
# Channel 4 -> Red
# Channel 5 -> NIR
#
# This follows the existing project's visualization approach.

green = stretch_band(image[2])
red = stretch_band(image[3])
nir = stretch_band(image[4])

false_color = np.stack(
    [
        nir,
        red,
        green
    ],
    axis=-1
)


# ============================================================
# FLOOD OVERLAY
# ============================================================

overlay = false_color.copy()

# Make flooded pixels visually distinct.
#
# The RGB values below create a strong flood overlay.
# Only flooded pixels are changed.

overlay[flood, 0] = 1.0
overlay[flood, 1] = 0.0
overlay[flood, 2] = 0.0


# ============================================================
# CREATE FIGURE
# ============================================================

print("\nCreating figure...")

fig, axes = plt.subplots(
    2,
    2,
    figsize=(14, 11)
)


# ============================================================
# 1. SATELLITE IMAGE
# ============================================================

axes[0, 0].imshow(false_color)

axes[0, 0].set_title(
    "Sentinel-1 False Color"
)

axes[0, 0].axis("off")


# ============================================================
# 2. FLOOD PROBABILITY
# ============================================================

im = axes[0, 1].imshow(
    probability,
    vmin=0,
    vmax=1
)

axes[0, 1].set_title(
    "Flood Probability"
)

axes[0, 1].axis("off")

fig.colorbar(
    im,
    ax=axes[0, 1],
    fraction=0.046,
    pad=0.04
)


# ============================================================
# 3. BINARY FLOOD MASK
# ============================================================

axes[1, 0].imshow(
    flood_mask,
    vmin=0,
    vmax=1
)

axes[1, 0].set_title(
    f"Predicted Flood Mask\n"
    f"{flood_percentage:.2f}% of pixels"
)

axes[1, 0].axis("off")


# ============================================================
# 4. SATELLITE + FLOOD OVERLAY
# ============================================================

axes[1, 1].imshow(overlay)

axes[1, 1].set_title(
    "Flood Inundation Overlay"
)

axes[1, 1].axis("off")


# ============================================================
# FIGURE TITLE
# ============================================================

fig.suptitle(
    f"Flood Inundation Analysis — Scene {SCENE_ID}",
    fontsize=16
)

plt.tight_layout()


# ============================================================
# SAVE
# ============================================================

print("\n" + "=" * 80)
print("SAVING VISUALIZATION")
print("=" * 80)

plt.savefig(
    OUTPUT_PNG,
    dpi=200,
    bbox_inches="tight"
)

plt.close(fig)

print("Saved:")
print(OUTPUT_PNG)


# ============================================================
# COMPLETE
# ============================================================

print("\n" + "=" * 80)
print("VISUALIZATION COMPLETE")
print("=" * 80)

print("\nOutput:")
print(OUTPUT_PNG)

print("\nFlood percentage:")
print(f"{flood_percentage:.2f}%")

print("\nDONE.")