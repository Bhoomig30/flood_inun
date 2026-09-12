from pathlib import Path
import rasterio
import numpy as np


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = (
    ML_DIR
    / "data"
    / "images"
)

LANDCOVER_DIR = (
    ML_DIR
    / "data"
    / "landcover_features"
)


# ============================================================
# ESA WORLDCOVER VALID CLASSES
# ============================================================

VALID_CLASSES = {
    10,   # Tree cover
    20,   # Shrubland
    30,   # Grassland
    40,   # Cropland
    50,   # Built-up
    60,   # Bare / sparse vegetation
    70,   # Snow and ice
    80,   # Permanent water bodies
    90,   # Herbaceous wetland
    95,   # Mangroves
    100   # Moss and lichen
}


# ============================================================
# START
# ============================================================

print("=" * 80)
print("LAND-COVER FEATURE VERIFICATION")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)

print("\nLand-cover directory:")
print(LANDCOVER_DIR)


# ============================================================
# CHECK DIRECTORIES
# ============================================================

if not IMAGE_DIR.exists():

    print("\n❌ Image directory not found:")
    print(IMAGE_DIR)
    raise SystemExit


if not LANDCOVER_DIR.exists():

    print("\n❌ Land-cover directory not found:")
    print(LANDCOVER_DIR)
    raise SystemExit


# ============================================================
# FIND SATELLITE IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    f"\nSatellite images: {len(images)}"
)


# ============================================================
# COUNTERS
# ============================================================

total_scenes = len(images)

valid_scenes = 0
invalid_scenes = 0
missing_scenes = 0
empty_scenes = 0
invalid_class_scenes = 0


# ============================================================
# VERIFY EACH SCENE
# ============================================================

for index, image_path in enumerate(
    images,
    start=1
):

    scene_id = image_path.stem.replace(
        "_image",
        ""
    )

    landcover_path = (
        LANDCOVER_DIR
        / f"{scene_id}_landcover.tif"
    )


    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    print(
        f"\n[{index}/{total_scenes}] {scene_id}"
    )


    # --------------------------------------------------------
    # Check land-cover file
    # --------------------------------------------------------

    if not landcover_path.exists():

        print(
            "  ❌ Missing land-cover file"
        )

        missing_scenes += 1
        invalid_scenes += 1

        continue


    try:

        # ====================================================
        # Open satellite image
        # ====================================================

        with rasterio.open(image_path) as src_img:

            image_width = src_img.width
            image_height = src_img.height
            image_crs = src_img.crs
            image_transform = src_img.transform


        # ====================================================
        # Open land-cover raster
        # ====================================================

        with rasterio.open(
            landcover_path
        ) as src_lc:

            # ------------------------------------------------
            # Basic metadata
            # ------------------------------------------------

            width = src_lc.width
            height = src_lc.height
            crs = src_lc.crs
            transform = src_lc.transform
            nodata = src_lc.nodata


            # ------------------------------------------------
            # Check dimensions
            # ------------------------------------------------

            if (
                width != image_width
                or height != image_height
            ):

                print(
                    "  ❌ Dimension mismatch"
                )

                print(
                    f"  Image: {image_width} × "
                    f"{image_height}"
                )

                print(
                    f"  Land-cover: {width} × "
                    f"{height}"
                )

                invalid_scenes += 1
                continue


            # ------------------------------------------------
            # Check CRS
            # ------------------------------------------------

            if crs != image_crs:

                print(
                    "  ❌ CRS mismatch"
                )

                print(
                    f"  Image CRS: {image_crs}"
                )

                print(
                    f"  Land-cover CRS: {crs}"
                )

                invalid_scenes += 1
                continue


            # ------------------------------------------------
            # Read with NoData masking
            # ------------------------------------------------
            #
            # IMPORTANT:
            # 0 is now declared as NoData
            # for the affected WorldCover rasters.
            #
            # Therefore masked=True removes those
            # pixels from class validation.
            #

            data = src_lc.read(
                1,
                masked=True
            )


            # ------------------------------------------------
            # Get valid pixels only
            # ------------------------------------------------

            valid_data = data.compressed()


            # ------------------------------------------------
            # Empty check
            # ------------------------------------------------

            if valid_data.size == 0:

                print(
                    "  ❌ Empty land-cover file"
                )

                empty_scenes += 1
                invalid_scenes += 1

                continue


            # ------------------------------------------------
            # Unique WorldCover classes
            # ------------------------------------------------

            unique_values = sorted(
                set(
                    int(value)
                    for value in valid_data
                )
            )


            # ------------------------------------------------
            # Check invalid classes
            # ------------------------------------------------

            invalid_values = [
                value
                for value in unique_values
                if value not in VALID_CLASSES
            ]


            # ------------------------------------------------
            # Invalid class
            # ------------------------------------------------

            if invalid_values:

                print(
                    "  ❌ Invalid WorldCover values: "
                    f"{invalid_values}"
                )

                invalid_class_scenes += 1
                invalid_scenes += 1

                print(
                    f"  Size: {width} × {height}"
                )

                print(
                    f"  CRS: {crs}"
                )

                print(
                    f"  NoData: {nodata}"
                )

                print(
                    f"  Classes: {unique_values}"
                )

                continue


            # ------------------------------------------------
            # Valid scene
            # ------------------------------------------------

            print(
                "  ✓ Valid"
            )

            print(
                f"  Size: {width} × {height}"
            )

            print(
                f"  CRS: {crs}"
            )

            print(
                f"  NoData: {nodata}"
            )

            print(
                f"  Classes: {unique_values}"
            )

            valid_scenes += 1


    except Exception as error:

        print(
            "  ❌ Error while reading file"
        )

        print(
            f"  {error}"
        )

        invalid_scenes += 1


# ============================================================
# FINAL RESULT
# ============================================================

print("\n")
print("=" * 80)
print("FINAL LAND-COVER VERIFICATION")
print("=" * 80)

print(
    f"\nTotal scenes: {total_scenes}"
)

print(
    f"Valid land-cover scenes: {valid_scenes}"
)

print(
    f"Invalid scenes: {invalid_scenes}"
)

print(
    f"Missing land-cover files: {missing_scenes}"
)

print(
    f"Empty land-cover files: {empty_scenes}"
)

print(
    f"Scenes with invalid class values: "
    f"{invalid_class_scenes}"
)


# ============================================================
# FINAL STATUS
# ============================================================

if (
    valid_scenes == total_scenes
    and missing_scenes == 0
    and empty_scenes == 0
    and invalid_class_scenes == 0
):

    print("\n")
    print("✅ LAND-COVER FEATURES ARE VALID")

    print("\nAll land-cover features:")

    print("  ✓ exist")

    print("  ✓ have matching dimensions")

    print("  ✓ have matching CRS")

    print("  ✓ contain valid ESA WorldCover classes")

    print("  ✓ correctly handle NoData")


else:

    print("\n")
    print("⚠ LAND-COVER FEATURES NEED ATTENTION")


print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)