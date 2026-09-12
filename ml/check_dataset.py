from pathlib import Path
import rasterio
import numpy as np


# ============================================================
# PROJECT LOCATION
# ============================================================

# check_dataset.py is directly inside ml/
# Therefore its parent is the ml folder.

ML_DIR = Path(__file__).resolve().parent

IMAGE_DIR = ML_DIR / "data" / "images"
LABEL_DIR = ML_DIR / "data" / "labels"
SPLIT_DIR = ML_DIR / "data" / "split"


print("=" * 70)
print("SEN1FLOODS11 DATASET VERIFICATION")
print("=" * 70)

print("\nML folder:")
print(ML_DIR)

print("\nData folder:")
print(ML_DIR / "data")


# ============================================================
# COUNT FILES
# ============================================================

images = sorted(IMAGE_DIR.glob("*_image.tif"))
labels = sorted(LABEL_DIR.glob("*_label.tif"))

print("\n" + "=" * 70)
print("FILE COUNTS")
print("=" * 70)

print("Images :", len(images))
print("Labels :", len(labels))


# ============================================================
# CHECK SPLIT FILES
# ============================================================

print("\n" + "=" * 70)
print("SPLIT FILES")
print("=" * 70)

for name in ["train.txt", "val.txt", "test.txt"]:

    path = SPLIT_DIR / name

    if path.exists():

        lines = [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip()
        ]

        print(f"{name:10} : FOUND ({len(lines)} entries)")

    else:

        print(f"{name:10} : MISSING")


# ============================================================
# STOP IF NO IMAGES
# ============================================================

if not images:

    print("\nERROR: No image files found.")
    print("\nPython is looking here:")
    print(IMAGE_DIR)

    raise SystemExit(1)


# ============================================================
# CHECK FIRST IMAGE
# ============================================================

image_path = images[0]

print("\n" + "=" * 70)
print("FIRST IMAGE")
print("=" * 70)

print("File:", image_path.name)

with rasterio.open(image_path) as src:

    image = src.read()

    print("Width :", src.width)
    print("Height:", src.height)
    print("Bands :", src.count)
    print("Shape :", image.shape)
    print("Data type:", image.dtype)
    print("CRS:", src.crs)

    print("\nBand statistics:")

    for i in range(src.count):

        band = image[i]

        print(
            f"Band {i + 1}: "
            f"min={np.nanmin(band):.4f}, "
            f"max={np.nanmax(band):.4f}, "
            f"mean={np.nanmean(band):.4f}"
        )


# ============================================================
# CHECK FIRST LABEL
# ============================================================

if not labels:

    print("\nERROR: No label files found.")
    print(LABEL_DIR)

    raise SystemExit(1)


label_path = labels[0]

print("\n" + "=" * 70)
print("FIRST LABEL")
print("=" * 70)

print("File:", label_path.name)

with rasterio.open(label_path) as src:

    label = src.read(1)

    print("Width :", src.width)
    print("Height:", src.height)
    print("Bands :", src.count)
    print("Shape :", label.shape)
    print("Data type:", label.dtype)

    unique_values = np.unique(label)

    print("Unique values:", unique_values)


# ============================================================
# CHECK IMAGE / LABEL PAIRING
# ============================================================

print("\n" + "=" * 70)
print("IMAGE / LABEL PAIRING")
print("=" * 70)

image_ids = {
    p.name.replace("_image.tif", "")
    for p in images
}

label_ids = {
    p.name.replace("_label.tif", "")
    for p in labels
}

missing_labels = image_ids - label_ids
missing_images = label_ids - image_ids

print("Images without labels:", len(missing_labels))
print("Labels without images:", len(missing_images))


# ============================================================
# FINAL VERIFICATION
# ============================================================

print("\n" + "=" * 70)
print("VERIFICATION RESULT")
print("=" * 70)

if len(images) == len(labels):

    print("✓ Image count matches label count.")

else:

    print("❌ Image/label counts do not match.")


if len(missing_labels) == 0 and len(missing_images) == 0:

    print("✓ Every image has a corresponding label.")

else:

    print("❌ Some image/label pairs are missing.")


with rasterio.open(image_path) as src:

    if src.count == 8:

        print("✓ Image contains exactly 8 channels.")

    else:

        print(f"❌ Expected 8 channels, found {src.count}.")


    if src.width == 512 and src.height == 512:

        print("✓ Image size is 512 × 512.")

    else:

        print(
            f"⚠ Image size is "
            f"{src.width} × {src.height}."
        )


with rasterio.open(label_path) as src:

    if src.width == 512 and src.height == 512:

        print("✓ Label size is 512 × 512.")

    else:

        print(
            f"⚠ Label size is "
            f"{src.width} × {src.height}."
        )


print("\nDataset verification finished.")