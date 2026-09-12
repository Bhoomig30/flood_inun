from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import rasterio


# ============================================================
# PATHS
# ============================================================

# This file is inside:
# flood-inundation-main/ml/src/

ML_DIR = Path(__file__).resolve().parent.parent

IMAGE_DIR = ML_DIR / "data" / "images"
LABEL_DIR = ML_DIR / "data" / "labels"

OUTPUT_DIR = ML_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# FIND FIRST IMAGE
# ============================================================

images = sorted(IMAGE_DIR.glob("*_image.tif"))

if not images:
    raise RuntimeError(
        f"No images found in {IMAGE_DIR}"
    )

image_path = images[0]

sample_id = image_path.name.replace("_image.tif", "")

label_path = LABEL_DIR / f"{sample_id}_label.tif"

if not label_path.exists():
    raise RuntimeError(
        f"Label not found:\n{label_path}"
    )


print("=" * 60)
print("VISUALIZING SEN1FLOODS11 SAMPLE")
print("=" * 60)

print("Image:", image_path.name)
print("Label:", label_path.name)


# ============================================================
# READ IMAGE
# ============================================================

with rasterio.open(image_path) as src:

    image = src.read().astype(np.float32)


print("\nImage shape:", image.shape)


# ============================================================
# READ LABEL
# ============================================================

with rasterio.open(label_path) as src:

    label = src.read(1)


print("Label shape:", label.shape)
print("Label values:", np.unique(label))


# ============================================================
# CHANNEL NAMES
# ============================================================

channel_names = [
    "Sentinel-1 VV",
    "Sentinel-1 VH",
    "Sentinel-2 Green",
    "Sentinel-2 Red",
    "Sentinel-2 NIR",
    "Sentinel-2 SWIR",
    "DEM",
    "Precipitation"
]


# ============================================================
# PLOT
# ============================================================

fig, axes = plt.subplots(
    3,
    3,
    figsize=(15, 15)
)


# ------------------------------------------------------------
# Display the 8 channels
# ------------------------------------------------------------

for i in range(8):

    ax = axes.flat[i]

    band = image[i]

    # Robust display range.
    # This prevents extreme pixels from making the
    # visualization completely dark/bright.

    valid = np.isfinite(band)

    if np.any(valid):

        low = np.percentile(band[valid], 2)
        high = np.percentile(band[valid], 98)

        if high > low:

            display_band = np.clip(
                band,
                low,
                high
            )

        else:

            display_band = band

    else:

        display_band = band

    ax.imshow(
        display_band,
        cmap="gray"
    )

    ax.set_title(
        f"Channel {i + 1}: {channel_names[i]}"
    )

    ax.axis("off")


# ------------------------------------------------------------
# Display flood label
# ------------------------------------------------------------

ax = axes.flat[8]

# Convert label to visualization:
#
# -1 = ignored/no-data
#  0 = non-flood
#  1 = flood

label_display = np.ma.masked_where(
    label == -1,
    label
)

ax.imshow(
    label_display,
    cmap="gray",
    vmin=0,
    vmax=1
)

ax.set_title(
    "Flood Label (-1 ignored, 0 non-flood, 1 flood)"
)

ax.axis("off")


# ============================================================
# SAVE FIGURE
# ============================================================

plt.tight_layout()

output_file = OUTPUT_DIR / "sample_visualization.png"

plt.savefig(
    output_file,
    dpi=150,
    bbox_inches="tight"
)

plt.show()

print("\nVisualization saved to:")
print(output_file)

print("\nDone!")