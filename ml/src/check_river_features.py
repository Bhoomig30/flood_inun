from pathlib import Path

import numpy as np
import rasterio


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

RIVER_DIR = ML_DIR / "data" / "river_features"


# ============================================================
# SETTINGS
# ============================================================

TOLERANCE = 1e-8


# ============================================================
# START
# ============================================================

print("=" * 80)
print("HYDRORIVERS OUTPUT VERIFICATION")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)

print("\nRiver feature directory:")
print(RIVER_DIR)


# ============================================================
# CHECK DIRECTORIES
# ============================================================

if not IMAGE_DIR.exists():

    raise FileNotFoundError(
        f"Image directory not found:\n{IMAGE_DIR}"
    )


if not RIVER_DIR.exists():

    raise FileNotFoundError(
        f"River feature directory not found:\n{RIVER_DIR}"
    )


# ============================================================
# FIND SATELLITE IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    f"\nTotal satellite images found: "
    f"{len(images)}"
)


if len(images) == 0:

    raise RuntimeError(
        "No *_image.tif files found."
    )


# ============================================================
# COUNTERS
# ============================================================

valid = 0

invalid = 0

missing_mask = []

missing_distance = []

shape_errors = []

crs_errors = []

transform_errors = []

data_errors = []

no_river_scenes = []

river_scenes = []


# ============================================================
# CHECK EACH SCENE
# ============================================================

for index, image_path in enumerate(
    images,
    start=1
):

    scene_id = image_path.stem.replace(
        "_image",
        ""
    )

    mask_path = (
        RIVER_DIR
        / f"{scene_id}_river_mask.tif"
    )

    distance_path = (
        RIVER_DIR
        / f"{scene_id}_river_distance.tif"
    )


    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    if (
        index <= 5
        or index % 50 == 0
        or index == len(images)
    ):

        print(
            f"\nChecking "
            f"[{index}/{len(images)}]: "
            f"{scene_id}"
        )


    # ========================================================
    # FILE EXISTENCE
    # ========================================================

    if not mask_path.exists():

        missing_mask.append(
            scene_id
        )

        invalid += 1

        continue


    if not distance_path.exists():

        missing_distance.append(
            scene_id
        )

        invalid += 1

        continue


    # ========================================================
    # READ ALL THREE RASTERS
    # ========================================================

    try:

        with rasterio.open(
            image_path
        ) as image:

            image_width = image.width
            image_height = image.height

            image_shape = (
                image.height,
                image.width
            )

            image_crs = image.crs

            image_transform = (
                image.transform
            )


        with rasterio.open(
            mask_path
        ) as mask:

            mask_width = mask.width
            mask_height = mask.height

            mask_shape = (
                mask.height,
                mask.width
            )

            mask_crs = mask.crs

            mask_transform = (
                mask.transform
            )

            mask_data = mask.read(1)

            mask_nodata = mask.nodata


        with rasterio.open(
            distance_path
        ) as distance:

            distance_width = distance.width
            distance_height = distance.height

            distance_shape = (
                distance.height,
                distance.width
            )

            distance_crs = distance.crs

            distance_transform = (
                distance.transform
            )

            distance_data = distance.read(1)

            distance_nodata = distance.nodata


    except Exception as error:

        data_errors.append(
            (
                scene_id,
                str(error)
            )
        )

        invalid += 1

        continue


    # ========================================================
    # CHECK DIMENSIONS
    # ========================================================

    if image_shape != mask_shape:

        shape_errors.append(
            (
                scene_id,
                "Image vs river mask",
                image_shape,
                mask_shape
            )
        )

        invalid += 1

        continue


    if image_shape != distance_shape:

        shape_errors.append(
            (
                scene_id,
                "Image vs river distance",
                image_shape,
                distance_shape
            )
        )

        invalid += 1

        continue


    # ========================================================
    # CHECK CRS
    # ========================================================

    if image_crs != mask_crs:

        crs_errors.append(
            (
                scene_id,
                "Image vs river mask",
                image_crs,
                mask_crs
            )
        )

        invalid += 1

        continue


    if image_crs != distance_crs:

        crs_errors.append(
            (
                scene_id,
                "Image vs river distance",
                image_crs,
                distance_crs
            )
        )

        invalid += 1

        continue


    # ========================================================
    # CHECK TRANSFORM
    # ========================================================

    transform_mask_difference = max(
        abs(
            a - b
        )
        for a, b in zip(
            image_transform,
            mask_transform
        )
    )


    transform_distance_difference = max(
        abs(
            a - b
        )
        for a, b in zip(
            image_transform,
            distance_transform
        )
    )


    if (
        transform_mask_difference
        > TOLERANCE
    ):

        transform_errors.append(
            (
                scene_id,
                "Image vs river mask",
                transform_mask_difference
            )
        )

        invalid += 1

        continue


    if (
        transform_distance_difference
        > TOLERANCE
    ):

        transform_errors.append(
            (
                scene_id,
                "Image vs river distance",
                transform_distance_difference
            )
        )

        invalid += 1

        continue


    # ========================================================
    # CHECK RIVER MASK
    # ========================================================

    river_pixels = int(
        np.sum(
            mask_data > 0
        )
    )


    # ========================================================
    # CHECK DISTANCE VALUES
    # ========================================================

    # We treat -1 as "no river information".
    valid_distance = distance_data[
        distance_data >= 0
    ]


    # --------------------------------------------------------
    # No river in scene
    # --------------------------------------------------------

    if river_pixels == 0:

        no_river_scenes.append(
            scene_id
        )

    else:

        river_scenes.append(
            scene_id
        )


    # --------------------------------------------------------
    # Distance should never be negative except nodata.
    # --------------------------------------------------------

    negative_real_values = distance_data[
        distance_data < 0
    ]


    # All negative values should be nodata.
    if len(negative_real_values) > 0:

        # -1 is expected nodata.
        unexpected_negative = negative_real_values[
            negative_real_values != -1
        ]

        if len(unexpected_negative) > 0:

            data_errors.append(
                (
                    scene_id,
                    "Unexpected negative "
                    "distance values"
                )
            )

            invalid += 1

            continue


    # --------------------------------------------------------
    # If rivers exist, distance must contain valid values.
    # --------------------------------------------------------

    if river_pixels > 0:

        if len(valid_distance) == 0:

            data_errors.append(
                (
                    scene_id,
                    "River pixels exist but "
                    "distance raster has no "
                    "valid values"
                )
            )

            invalid += 1

            continue


        # Distance at river pixels should be approximately 0.
        river_distance_values = distance_data[
            mask_data > 0
        ]

        if len(river_distance_values) > 0:

            max_river_distance = float(
                np.max(
                    np.abs(
                        river_distance_values
                    )
                )
            )

            if max_river_distance > 1.0:

                data_errors.append(
                    (
                        scene_id,
                        "River pixels do not "
                        "have approximately "
                        "zero distance",
                        max_river_distance
                    )
                )

                invalid += 1

                continue


    # ========================================================
    # SCENE IS VALID
    # ========================================================

    valid += 1


    # ========================================================
    # PRINT SAMPLE RESULTS
    # ========================================================

    if (
        index <= 5
    ):

        print(
            f"  Size: "
            f"{image_width} × "
            f"{image_height}"
        )

        print(
            f"  CRS: "
            f"{image_crs}"
        )

        print(
            f"  River pixels: "
            f"{river_pixels}"
        )


        if len(valid_distance) > 0:

            print(
                f"  Distance min: "
                f"{valid_distance.min():.2f} m"
            )

            print(
                f"  Distance max: "
                f"{valid_distance.max():.2f} m"
            )

            print(
                f"  Distance mean: "
                f"{valid_distance.mean():.2f} m"
            )

        else:

            print(
                "  Distance: "
                "no valid river distance"
            )


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("FINAL HYDRORIVERS VERIFICATION")
print("=" * 80)


print(
    f"\nTotal images: "
    f"{len(images)}"
)

print(
    f"Valid scenes: "
    f"{valid}"
)

print(
    f"Invalid scenes: "
    f"{invalid}"
)

print(
    f"Missing masks: "
    f"{len(missing_mask)}"
)

print(
    f"Missing distance files: "
    f"{len(missing_distance)}"
)

print(
    f"Scenes containing rivers: "
    f"{len(river_scenes)}"
)

print(
    f"Scenes without rivers: "
    f"{len(no_river_scenes)}"
)


# ============================================================
# SHOW ERRORS
# ============================================================

if missing_mask:

    print("\n❌ Missing river masks:")

    for scene in missing_mask[:20]:

        print(
            " ",
            scene
        )


if missing_distance:

    print("\n❌ Missing river-distance files:")

    for scene in missing_distance[:20]:

        print(
            " ",
            scene
        )


if shape_errors:

    print("\n❌ Shape errors:")

    for error in shape_errors[:10]:

        print(
            " ",
            error
        )


if crs_errors:

    print("\n❌ CRS errors:")

    for error in crs_errors[:10]:

        print(
            " ",
            error
        )


if transform_errors:

    print("\n❌ Transform errors:")

    for error in transform_errors[:10]:

        print(
            " ",
            error
        )


if data_errors:

    print("\n❌ Data errors:")

    for error in data_errors[:20]:

        print(
            " ",
            error
        )


# ============================================================
# FINAL VERDICT
# ============================================================

print("\n")
print("=" * 80)


if (
    invalid == 0
    and
    valid == len(images)
):

    print(
        "✅ HYDRORIVERS FEATURES ARE VALID"
    )

    print(
        "\nAll river masks and distance rasters:"
    )

    print(
        "  ✓ exist"
    )

    print(
        "  ✓ have matching dimensions"
    )

    print(
        "  ✓ have matching CRS"
    )

    print(
        "  ✓ have matching transforms"
    )

    print(
        "  ✓ contain valid distance data"
    )

else:

    print(
        "⚠ HYDRORIVERS VERIFICATION FOUND ISSUES"
    )

    print(
        "\nFix the reported issues before "
        "using these features for training."
    )


print("=" * 80)