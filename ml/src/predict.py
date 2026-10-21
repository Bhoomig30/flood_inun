from pathlib import Path

import numpy as np
import torch
import rasterio
import matplotlib.pyplot as plt

from unet_small import UNetSmall


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parent.parent

IMAGE_DIR = ML_DIR / "data" / "images"

MODEL_PATH = (
    ML_DIR
    / "models"
    / "flood_unet_baseline.pth"
)

OUTPUT_DIR = ML_DIR / "outputs"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# SETTINGS
# ============================================================

DEVICE = torch.device(
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)

# Change this if you want another test image.
IMAGE_NAME = "1010394_image.tif"


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_image(image):

    image = image.astype(
        np.float32
    )

    image = np.nan_to_num(
        image,
        nan=0.0,
        posinf=0.0,
        neginf=0.0
    )

    for c in range(
        image.shape[0]
    ):

        band = image[c]

        low = np.percentile(
            band,
            2
        )

        high = np.percentile(
            band,
            98
        )

        if high > low:

            band = np.clip(
                band,
                low,
                high
            )

            band = (
                band - low
            ) / (
                high - low
            )

        else:

            band = np.zeros_like(
                band
            )

        image[c] = band

    image = np.nan_to_num(
        image,
        nan=0.0,
        posinf=1.0,
        neginf=0.0
    )

    return image


# ============================================================
# LOAD MODEL
# ============================================================

print("=" * 70)
print("FLOOD PREDICTION")
print("=" * 70)

print(
    "\nDevice:",
    DEVICE
)

print(
    "\nLoading model..."
)

model = UNetSmall(
    in_channels=8,
    out_channels=2
)

checkpoint = torch.load(
    MODEL_PATH,
    map_location=DEVICE
)

if "model_state_dict" in checkpoint:

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

else:

    model.load_state_dict(
        checkpoint
    )

model = model.to(
    DEVICE
)

model.eval()

print("✓ Model loaded")


# ============================================================
# LOAD IMAGE
# ============================================================

image_path = (
    IMAGE_DIR
    / IMAGE_NAME
)

if not image_path.exists():

    raise FileNotFoundError(
        f"Image not found:\n{image_path}"
    )


print(
    "\nLoading image:"
)

print(
    image_path
)


with rasterio.open(
    image_path
) as src:

    image = src.read()

    profile = src.profile

    transform = src.transform

    crs = src.crs


print(
    "\nOriginal image shape:",
    image.shape
)


# ============================================================
# CHECK CHANNELS
# ============================================================

if image.shape[0] != 8:

    raise ValueError(
        "Expected 8 channels, "
        f"but found {image.shape[0]}"
    )


# ============================================================
# NORMALIZE
# ============================================================

image_normalized = normalize_image(
    image
)


print(
    "Normalized range:",
    image_normalized.min(),
    "to",
    image_normalized.max()
)


# ============================================================
# CONVERT TO TENSOR
# ============================================================

tensor = torch.from_numpy(
    image_normalized.copy()
).float()


tensor = tensor.unsqueeze(
    0
)


tensor = tensor.to(
    DEVICE
)


# ============================================================
# PREDICTION
# ============================================================

print(
    "\nRunning flood prediction..."
)


with torch.no_grad():

    output = model(
        tensor
    )

    prediction = torch.argmax(
        output,
        dim=1
    )


prediction = (
    prediction[0]
    .cpu()
    .numpy()
)


# ============================================================
# FLOOD MASK
# ============================================================

flood_mask = (
    prediction == 1
)


flood_pixels = (
    flood_mask.sum()
)


total_pixels = (
    flood_mask.size
)


flood_percentage = (
    flood_pixels
    / total_pixels
    * 100
)


print(
    "\nFlood pixels:",
    flood_pixels
)

print(
    "Total pixels:",
    total_pixels
)

print(
    f"Predicted flooded area: "
    f"{flood_percentage:.2f}%"
)


# ============================================================
# SAVE FLOOD MASK
# ============================================================

mask_path = (
    OUTPUT_DIR
    / "predicted_flood_mask.tif"
)


mask_profile = profile.copy()

mask_profile.update(
    {
        "count": 1,
        "dtype": "uint8",
        "nodata": 0
    }
)


with rasterio.open(
    mask_path,
    "w",
    **mask_profile
) as dst:

    dst.write(
        flood_mask.astype(
            np.uint8
        ),
        1
    )


print(
    "\n✓ Flood mask saved:"
)

print(
    mask_path
)


# ============================================================
# VISUALIZATION
# ============================================================

# Available optical channels:
#
# Channel 3 = Green
# Channel 4 = Red
# Channel 5 = NIR
#
# Since the dataset does not contain Blue,
# we use NIR / Red / Green false-color visualization.


def stretch_band(band):

    low = np.percentile(
        band,
        2
    )

    high = np.percentile(
        band,
        98
    )

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


nir = stretch_band(
    image_normalized[4]
)

red = stretch_band(
    image_normalized[3]
)

green = stretch_band(
    image_normalized[2]
)


false_color = np.stack(
    [
        nir,
        red,
        green
    ],
    axis=-1
)


# ============================================================
# CREATE FIGURE
# ============================================================

fig, axes = plt.subplots(
    1,
    3,
    figsize=(15, 5)
)


# ------------------------------------------------------------
# Satellite image
# ------------------------------------------------------------

axes[0].imshow(
    false_color
)

axes[0].set_title(
    "Satellite Image\n(NIR-Red-Green)"
)

axes[0].axis(
    "off"
)


# ------------------------------------------------------------
# Prediction
# ------------------------------------------------------------

axes[1].imshow(
    flood_mask,
    cmap="Blues"
)

axes[1].set_title(
    "Predicted Flood Mask"
)

axes[1].axis(
    "off"
)


# ------------------------------------------------------------
# Overlay
# ------------------------------------------------------------

axes[2].imshow(
    false_color
)

axes[2].imshow(
    flood_mask,
    cmap="Reds",
    alpha=0.45
)

axes[2].set_title(
    f"Flood Prediction\n"
    f"{flood_percentage:.2f}%"
)

axes[2].axis(
    "off"
)


plt.tight_layout()


# ============================================================
# SAVE FIGURE
# ============================================================

visualization_path = (
    OUTPUT_DIR
    / "flood_prediction.png"
)


plt.savefig(
    visualization_path,
    dpi=200,
    bbox_inches="tight"
)


plt.close()


print(
    "\n✓ Visualization saved:"
)

print(
    visualization_path
)


print(
    "\nPrediction complete!"
)