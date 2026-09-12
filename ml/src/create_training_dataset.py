from pathlib import Path
import numpy as np
import rasterio


# ============================================================
# CONFIGURATION
# ============================================================

DRY_RUN = True

EXPECTED_SIZE = 512
EXPECTED_BANDS = 8

VALID_WORLDCOVER_CLASSES = {
    10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100
}


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"
DEM_DIR = ML_DIR / "data" / "dem_features"
LANDCOVER_DIR = ML_DIR / "data" / "landcover_features"
RIVER_DIR = ML_DIR / "data" / "river_features"
LABEL_DIR = ML_DIR / "data" / "labels"

OUTPUT_DIR = ML_DIR / "data" / "training_dataset"


# ============================================================
# START
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 MULTIMODAL TRAINING DATASET")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)

print("\nDEM directory:")
print(DEM_DIR)

print("\nLand-cover directory:")
print(LANDCOVER_DIR)

print("\nRiver feature directory:")
print(RIVER_DIR)

print("\nLabel directory:")
print(LABEL_DIR)

print("\nOutput directory:")
print(OUTPUT_DIR)

print("\nDRY RUN:", DRY_RUN)


# ============================================================
# CHECK DIRECTORIES
# ============================================================

directories = {
    "images": IMAGE_DIR,
    "DEM": DEM_DIR,
    "landcover": LANDCOVER_DIR,
    "river": RIVER_DIR,
    "labels": LABEL_DIR,
}

for name, directory in directories.items():

    if not directory.exists():

        print(
            f"\n❌ {name} directory not found:"
        )

        print(directory)

        raise SystemExit


# ============================================================
# FIND SENTINEL IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    f"\nSentinel scenes: {len(images)}"
)


if len(images) == 0:

    print("\n❌ No Sentinel images found.")

    raise SystemExit


# ============================================================
# FEATURE PATHS
# ============================================================

def feature_path(
    directory,
    scene_id,
    suffix
):

    return (
        directory
        / f"{scene_id}_{suffix}.tif"
    )


# ============================================================
# CHECK ONE RASTER
# ============================================================

def inspect_raster(
    path,
    expected_bands=1
):

    if not path.exists():

        return False, "Missing file"

    try:

        with rasterio.open(path) as src:

            if src.width != EXPECTED_SIZE:

                return False, (
                    f"Width {src.width}"
                )

            if src.height != EXPECTED_SIZE:

                return False, (
                    f"Height {src.height}"
                )

            if src.count != expected_bands:

                return False, (
                    f"Bands {src.count}"
                )

            if src.crs is None:

                return False, "Missing CRS"

            data = src.read()

            if data.size == 0:

                return False, "Empty raster"

            if not np.isfinite(
                data.astype(np.float64)
            ).any():

                return False, (
                    "No finite values"
                )

    except Exception as error:

        return False, str(error)

    return True, "Valid"


# ============================================================
# CHECK LABEL
# ============================================================

def inspect_label(path):

    if not path.exists():

        return False, "Missing label"

    try:

        with rasterio.open(path) as src:

            if src.width != EXPECTED_SIZE:

                return False, (
                    f"Width {src.width}"
                )

            if src.height != EXPECTED_SIZE:

                return False, (
                    f"Height {src.height}"
                )

            if src.count != 1:

                return False, (
                    f"Bands {src.count}"
                )

            data = src.read(1)

            if data.size == 0:

                return False, "Empty label"

            unique = np.unique(data)

            return True, unique

    except Exception as error:

        return False, str(error)


# ============================================================
# DRY RUN / DATASET VALIDATION
# ============================================================

print("\n")
print("=" * 80)
print("SCENE FEATURE VALIDATION")
print("=" * 80)


valid_scenes = []
invalid_scenes = []


for index, image_path in enumerate(
    images,
    start=1
):

    scene_id = image_path.stem.replace(
        "_image",
        ""
    )

    print(
        f"\n[{index}/{len(images)}] "
        f"{scene_id}"
    )


    # --------------------------------------------------------
    # Sentinel-1
    # --------------------------------------------------------

    ok, info = inspect_raster(
        image_path,
        EXPECTED_BANDS
    )

    if not ok:

        print(
            "  ❌ Sentinel:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue

    print(
        "  ✓ Sentinel-1: 8 bands"
    )


    # --------------------------------------------------------
    # DEM
    # --------------------------------------------------------

    dem_path = feature_path(
        DEM_DIR,
        scene_id,
        "dem"
    )

    ok, info = inspect_raster(
        dem_path,
        1
    )

    if not ok:

        print(
            "  ❌ DEM:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue

    print(
        "  ✓ DEM"
    )


    # --------------------------------------------------------
    # WorldCover
    # --------------------------------------------------------

    landcover_path = feature_path(
        LANDCOVER_DIR,
        scene_id,
        "landcover"
    )

    ok, info = inspect_raster(
        landcover_path,
        1
    )

    if not ok:

        print(
            "  ❌ Land-cover:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue


    # Validate classes
    with rasterio.open(
        landcover_path
    ) as src:

        landcover = src.read(1)

        classes = set(
            np.unique(
                landcover
            ).tolist()
        )

        classes.discard(
            0
        )

        invalid_classes = (
            classes
            - VALID_WORLDCOVER_CLASSES
        )

        if invalid_classes:

            print(
                "  ❌ Invalid WorldCover:",
                invalid_classes
            )

            invalid_scenes.append(
                scene_id
            )

            continue

    print(
        "  ✓ WorldCover"
    )


    # --------------------------------------------------------
    # River distance
    # --------------------------------------------------------

    river_distance_path = feature_path(
        RIVER_DIR,
        scene_id,
        "river_distance"
    )

    ok, info = inspect_raster(
        river_distance_path,
        1
    )

    if not ok:

        print(
            "  ❌ River distance:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue

    print(
        "  ✓ River distance"
    )


    # --------------------------------------------------------
    # River mask
    # --------------------------------------------------------

    river_mask_path = feature_path(
        RIVER_DIR,
        scene_id,
        "river_mask"
    )

    ok, info = inspect_raster(
        river_mask_path,
        1
    )

    if not ok:

        print(
            "  ❌ River mask:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue

    print(
        "  ✓ River mask"
    )


    # --------------------------------------------------------
    # Label
    # --------------------------------------------------------

    label_path = feature_path(
        LABEL_DIR,
        scene_id,
        "label"
    )

    ok, info = inspect_label(
        label_path
    )

    if not ok:

        print(
            "  ❌ Label:",
            info
        )

        invalid_scenes.append(
            scene_id
        )

        continue

    print(
        "  ✓ Flood label"
    )


    valid_scenes.append(
        scene_id
    )


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)

print(
    "\nTotal Sentinel scenes:",
    len(images)
)

print(
    "Valid multimodal scenes:",
    len(valid_scenes)
)

print(
    "Invalid scenes:",
    len(invalid_scenes)
)


if invalid_scenes:

    print(
        "\nInvalid scene IDs:"
    )

    for scene_id in invalid_scenes:

        print(
            " ",
            scene_id
        )


# ============================================================
# STOP AFTER DRY RUN
# ============================================================

if DRY_RUN:

    print("\n")
    print("=" * 80)
    print("DRY RUN COMPLETE")
    print("=" * 80)

    print(
        "\nNo training files were created."
    )

    print(
        "\nIf the validation looks correct,"
    )

    print(
        "change:"
    )

    print(
        "    DRY_RUN = False"
    )

    print(
        "\nand run the script again."
    )

    raise SystemExit


# ============================================================
# CREATE OUTPUT DIRECTORY
# ============================================================

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CREATE MULTIMODAL DATA
# ============================================================

print("\n")
print("=" * 80)
print("CREATING TRAINING DATA")
print("=" * 80)


created = 0
failed = 0


for index, scene_id in enumerate(
    valid_scenes,
    start=1
):

    print(
        f"\n[{index}/{len(valid_scenes)}] "
        f"{scene_id}"
    )

    try:

        image_path = (
            IMAGE_DIR
            / f"{scene_id}_image.tif"
        )

        dem_path = feature_path(
            DEM_DIR,
            scene_id,
            "dem"
        )

        landcover_path = feature_path(
            LANDCOVER_DIR,
            scene_id,
            "landcover"
        )

        river_distance_path = feature_path(
            RIVER_DIR,
            scene_id,
            "river_distance"
        )

        river_mask_path = feature_path(
            RIVER_DIR,
            scene_id,
            "river_mask"
        )

        label_path = feature_path(
            LABEL_DIR,
            scene_id,
            "label"
        )


        # ----------------------------------------------------
        # Read all rasters
        # ----------------------------------------------------

        with rasterio.open(
            image_path
        ) as src:

            sar = src.read(
                out_dtype="float32"
            )

            profile = src.profile.copy()


        with rasterio.open(
            dem_path
        ) as src:

            dem = src.read(
                1,
                out_dtype="float32"
            )


        with rasterio.open(
            landcover_path
        ) as src:

            landcover = src.read(
                1,
                out_dtype="float32"
            )


        with rasterio.open(
            river_distance_path
        ) as src:

            river_distance = src.read(
                1,
                out_dtype="float32"
            )


        with rasterio.open(
            river_mask_path
        ) as src:

            river_mask = src.read(
                1,
                out_dtype="float32"
            )


        with rasterio.open(
            label_path
        ) as src:

            label = src.read(
                1,
                out_dtype="uint8"
            )


        # ----------------------------------------------------
        # Validate shapes
        # ----------------------------------------------------

        shape = (
            EXPECTED_SIZE,
            EXPECTED_SIZE
        )

        if sar.shape != (
            EXPECTED_BANDS,
            *shape
        ):

            raise ValueError(
                f"SAR shape: {sar.shape}"
            )

        for name, array in [
            ("DEM", dem),
            ("WorldCover", landcover),
            ("River distance", river_distance),
            ("River mask", river_mask),
            ("Label", label),
        ]:

            if array.shape != shape:

                raise ValueError(
                    f"{name} shape: "
                    f"{array.shape}"
                )


        # ----------------------------------------------------
        # Handle NaN / infinite values
        # ----------------------------------------------------

        sar = np.nan_to_num(
            sar,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )

        dem = np.nan_to_num(
            dem,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )

        river_distance = np.nan_to_num(
            river_distance,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )

        river_mask = np.nan_to_num(
            river_mask,
            nan=0.0,
            posinf=0.0,
            neginf=0.0
        )


        # ----------------------------------------------------
        # Normalize WorldCover
        #
        # Convert class codes into a normalized feature.
        #
        # 0 remains nodata.
        # ----------------------------------------------------

        landcover_feature = (
            landcover / 100.0
        )


        # ----------------------------------------------------
        # Normalize DEM
        # ----------------------------------------------------

        dem_min = np.percentile(
            dem,
            1
        )

        dem_max = np.percentile(
            dem,
            99
        )

        if dem_max > dem_min:

            dem_feature = (
                np.clip(
                    dem,
                    dem_min,
                    dem_max
                )
                - dem_min
            ) / (
                dem_max
                - dem_min
            )

        else:

            dem_feature = np.zeros_like(
                dem,
                dtype=np.float32
            )


        # ----------------------------------------------------
        # Normalize river distance
        # ----------------------------------------------------

        distance_max = np.percentile(
            river_distance,
            99
        )

        if distance_max > 0:

            river_distance_feature = (
                np.clip(
                    river_distance,
                    0,
                    distance_max
                )
                / distance_max
            )

        else:

            river_distance_feature = (
                np.zeros_like(
                    river_distance,
                    dtype=np.float32
                )
            )


        # ----------------------------------------------------
        # Ensure float32
        # ----------------------------------------------------

        sar = sar.astype(
            np.float32
        )

        dem_feature = dem_feature.astype(
            np.float32
        )

        landcover_feature = (
            landcover_feature.astype(
                np.float32
            )
        )

        river_distance_feature = (
            river_distance_feature.astype(
                np.float32
            )
        )

        river_mask = river_mask.astype(
            np.float32
        )


        # ----------------------------------------------------
        # Combine channels
        #
        # 8 SAR
        # 1 DEM
        # 1 WorldCover
        # 1 River distance
        # 1 River mask
        #
        # TOTAL = 12 channels
        # ----------------------------------------------------

        features = np.concatenate(
            [
                sar,

                dem_feature[
                    np.newaxis,
                    ...
                ],

                landcover_feature[
                    np.newaxis,
                    ...
                ],

                river_distance_feature[
                    np.newaxis,
                    ...
                ],

                river_mask[
                    np.newaxis,
                    ...
                ],
            ],
            axis=0
        )


        # ----------------------------------------------------
        # Save features
        # ----------------------------------------------------

        feature_profile = profile.copy()

        feature_profile.update(
            driver="GTiff",
            dtype="float32",
            count=12,
            compress="deflate",
            predictor=2,
            nodata=None
        )


        feature_output = (
            OUTPUT_DIR
            / f"{scene_id}_features.tif"
        )


        with rasterio.open(
            feature_output,
            "w",
            **feature_profile
        ) as dst:

            dst.write(
                features
            )


        # ----------------------------------------------------
        # Save label
        # ----------------------------------------------------

        label_profile = profile.copy()

        label_profile.update(
            driver="GTiff",
            dtype="uint8",
            count=1,
            compress="deflate",
            nodata=0
        )


        label_output = (
            OUTPUT_DIR
            / f"{scene_id}_label.tif"
        )


        with rasterio.open(
            label_output,
            "w",
            **label_profile
        ) as dst:

            dst.write(
                label,
                1
            )


        print(
            "  ✓ Features:",
            feature_output.name
        )

        print(
            "  ✓ Label:",
            label_output.name
        )

        created += 1


    except Exception as error:

        print(
            "  ❌ FAILED:",
            error
        )

        failed += 1


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("TRAINING DATASET CREATION COMPLETE")
print("=" * 80)

print(
    "\nValid scenes:",
    len(valid_scenes)
)

print(
    "Created:",
    created
)

print(
    "Failed:",
    failed
)

print(
    "\nOutput directory:"
)

print(
    OUTPUT_DIR
)

print(
    "\nEach feature raster contains:"
)

print(
    "  Band 1-8  : Sentinel-1"
)

print(
    "  Band 9    : DEM"
)

print(
    "  Band 10   : WorldCover"
)

print(
    "  Band 11   : River distance"
)

print(
    "  Band 12   : River mask"
)

print(
    "\nLabels are stored separately."
)

print(
    "Done."
)