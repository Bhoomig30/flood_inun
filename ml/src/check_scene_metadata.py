from pathlib import Path
import rasterio


# ============================================================
# PATH
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"


# ============================================================
# FIND FIRST IMAGE
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

if not images:
    raise RuntimeError("No *_image.tif files found.")


image_path = images[0]


# ============================================================
# READ METADATA
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 IMAGE METADATA")
print("=" * 80)

print("\nImage:")
print(image_path)

with rasterio.open(image_path) as src:

    print("\n")
    print("=" * 80)
    print("BASIC INFORMATION")
    print("=" * 80)

    print("Width:", src.width)
    print("Height:", src.height)
    print("CRS:", src.crs)
    print("Bounds:", src.bounds)
    print("Transform:", src.transform)
    print("Count:", src.count)

    print("\n")
    print("=" * 80)
    print("RASTER TAGS")
    print("=" * 80)

    tags = src.tags()

    if tags:

        for key, value in tags.items():

            print(
                f"{key}: {value}"
            )

    else:

        print(
            "No dataset-level tags found."
        )

    print("\n")
    print("=" * 80)
    print("BAND TAGS")
    print("=" * 80)

    for band in range(
        1,
        src.count + 1
    ):

        band_tags = src.tags(
            band
        )

        print(
            f"\nBand {band}:"
        )

        if band_tags:

            for key, value in band_tags.items():

                print(
                    f"  {key}: {value}"
                )

        else:

            print(
                "  No tags"
            )


print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)