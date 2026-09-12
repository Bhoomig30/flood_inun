from pathlib import Path

import rasterio


# ============================================================
# SETTINGS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

OUTPUT_FILE = (
    ML_DIR
    / "data"
    / "india_scenes.txt"
)


# Approximate geographic bounding box of India.
#
# longitude: 68°E to 97°E
# latitude : 6°N to 37°N
#
# We use a slightly wider box to avoid accidentally
# excluding scenes close to the boundary.

INDIA_MIN_LON = 67.0
INDIA_MAX_LON = 98.0

INDIA_MIN_LAT = 5.0
INDIA_MAX_LAT = 38.0


# ============================================================
# START
# ============================================================

print("=" * 80)
print("FINDING SEN1FLOODS11 SCENES IN INDIA")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)


if not IMAGE_DIR.exists():

    print("\n❌ Image directory not found.")
    raise SystemExit


# ============================================================
# FIND IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    f"\nTotal images found: {len(images)}"
)


if len(images) == 0:

    print(
        "\n❌ No *_image.tif files found."
    )

    raise SystemExit


# ============================================================
# CHECK EACH IMAGE
# ============================================================

india_scenes = []

errors = 0


for index, image_path in enumerate(
    images,
    start=1
):

    try:

        with rasterio.open(
            image_path
        ) as src:

            bounds = src.bounds

            crs = src.crs


        # ----------------------------------------------------
        # We expect geographic coordinates.
        # ----------------------------------------------------

        if crs is None:

            print(
                f"\n⚠ No CRS: "
                f"{image_path.name}"
            )

            continue


        # ----------------------------------------------------
        # Check whether image overlaps India.
        #
        # We test the image bounding box rather than only
        # its center, so scenes crossing a boundary aren't
        # accidentally missed.
        # ----------------------------------------------------

        overlaps_india = not (
            bounds.right < INDIA_MIN_LON
            or
            bounds.left > INDIA_MAX_LON
            or
            bounds.top < INDIA_MIN_LAT
            or
            bounds.bottom > INDIA_MAX_LAT
        )


        if overlaps_india:

            india_scenes.append(
                image_path
            )

            print(
                f"\n✓ INDIA: "
                f"{image_path.name}"
            )

            print(
                f"  Bounds: "
                f"{bounds}"
            )


        # Progress every 50 images
        elif index % 50 == 0:

            print(
                f"Checked "
                f"{index}/{len(images)} images..."
            )


    except Exception as e:

        errors += 1

        print(
            f"\n⚠ Error reading "
            f"{image_path.name}:"
        )

        print(e)


# ============================================================
# SAVE RESULTS
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    for image_path in india_scenes:

        f.write(
            image_path.name
            + "\n"
        )


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("RESULT")
print("=" * 80)

print(
    f"\nTotal SEN1FLOODS11 images: "
    f"{len(images)}"
)

print(
    f"Indian/India-overlapping scenes: "
    f"{len(india_scenes)}"
)

print(
    f"Errors: "
    f"{errors}"
)


# ============================================================
# LIST RESULTS
# ============================================================

print("\n")
print("=" * 80)
print("INDIAN SCENES")
print("=" * 80)


if len(india_scenes) == 0:

    print(
        "\n⚠ No Indian scenes were found."
    )

else:

    for i, image_path in enumerate(
        india_scenes,
        start=1
    ):

        print(
            f"{i:3}. "
            f"{image_path.name}"
        )


# ============================================================
# OUTPUT
# ============================================================

print("\n")
print("=" * 80)

print(
    "✓ Results saved to:"
)

print(
    OUTPUT_FILE
)

print("=" * 80)