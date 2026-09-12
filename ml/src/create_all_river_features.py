from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio

from shapely.geometry import box
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

HYDRORIVERS_GDB = (
    ML_DIR
    / "data"
    / "external"
    / "hydrorivers"
    / "HydroRIVERS_v10_as.gdb"
)

OUTPUT_DIR = ML_DIR / "data" / "river_features"

LAYER_NAME = "HydroRIVERS_v10_as"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# PROCESS ONE SCENE
# ============================================================

def process_scene(image_path, rivers):

    print("\n" + "=" * 80)
    print(f"PROCESSING: {image_path.name}")
    print("=" * 80)

    scene_id = image_path.stem.replace(
        "_image",
        ""
    )

    mask_path = (
        OUTPUT_DIR
        / f"{scene_id}_river_mask.tif"
    )

    distance_path = (
        OUTPUT_DIR
        / f"{scene_id}_river_distance.tif"
    )

    # --------------------------------------------------------
    # Read image
    # --------------------------------------------------------

    with rasterio.open(image_path) as src:

        width = src.width
        height = src.height

        transform = src.transform
        image_crs = src.crs
        bounds = src.bounds

        print(
            f"Size: {width} x {height}"
        )

        print(
            f"CRS: {image_crs}"
        )

    if image_crs is None:

        print(
            "❌ Image has no CRS."
        )

        return False

    # ========================================================
    # CREATE SCENE BOUNDING BOX
    # ========================================================

    scene_polygon = box(
        bounds.left,
        bounds.bottom,
        bounds.right,
        bounds.top
    )

    scene_gdf = gpd.GeoDataFrame(
        {
            "geometry": [
                scene_polygon
            ]
        },
        crs=image_crs
    )

    # --------------------------------------------------------
    # Transform scene bbox to HydroRIVERS CRS
    # --------------------------------------------------------

    scene_gdf_rivers_crs = scene_gdf.to_crs(
        rivers.crs
    )

    scene_geometry = (
        scene_gdf_rivers_crs
        .geometry
        .iloc[0]
    )

    # ========================================================
    # FIND RIVERS
    # ========================================================

    selected = rivers[
        rivers.geometry.intersects(
            scene_geometry
        )
    ].copy()

    print(
        f"River segments found: "
        f"{len(selected)}"
    )

    # ========================================================
    # NO RIVER CASE
    # ========================================================

    if len(selected) == 0:

        print(
            "⚠ No HydroRIVERS segments "
            "found inside this scene."
        )

        river_mask = np.zeros(
            (height, width),
            dtype=np.uint8
        )

        distance_m = np.full(
            (height, width),
            -1.0,
            dtype=np.float32
        )

    # ========================================================
    # RIVER FOUND
    # ========================================================

    else:

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Create a local UTM CRS automatically.
        #
        # This guarantees distance calculations are in meters.
        # ----------------------------------------------------

        center_lon = (
            bounds.left
            + bounds.right
        ) / 2.0

        center_lat = (
            bounds.bottom
            + bounds.top
        ) / 2.0

        zone = int(
            (center_lon + 180) / 6
        ) + 1

        if center_lat >= 0:

            epsg = 32600 + zone

        else:

            epsg = 32700 + zone

        local_crs = (
            f"EPSG:{epsg}"
        )

        print(
            f"Local projected CRS: "
            f"{local_crs}"
        )

        # ----------------------------------------------------
        # Reproject rivers to UTM
        # ----------------------------------------------------

        rivers_utm = selected.to_crs(
            local_crs
        )

        # ----------------------------------------------------
        # Create image grid in UTM
        #
        # We calculate the approximate UTM bounds and pixel
        # resolution from the original geographic image.
        # ----------------------------------------------------

        image_box = gpd.GeoDataFrame(
            {
                "geometry": [
                    scene_polygon
                ]
            },
            crs=image_crs
        )

        image_box_utm = image_box.to_crs(
            local_crs
        )

        utm_bounds = (
            image_box_utm
            .total_bounds
        )

        min_x = utm_bounds[0]
        min_y = utm_bounds[1]
        max_x = utm_bounds[2]
        max_y = utm_bounds[3]

        width_m = (
            max_x - min_x
        )

        height_m = (
            max_y - min_y
        )

        pixel_x_m = (
            width_m / width
        )

        pixel_y_m = (
            height_m / height
        )

        print(
            f"Pixel size: "
            f"{pixel_x_m:.2f} m × "
            f"{pixel_y_m:.2f} m"
        )

        # ----------------------------------------------------
        # UTM transform
        # ----------------------------------------------------

        from rasterio.transform import from_bounds

        utm_transform = from_bounds(
            min_x,
            min_y,
            max_x,
            max_y,
            width,
            height
        )

        # ----------------------------------------------------
        # Rasterize rivers in UTM
        # ----------------------------------------------------

        shapes = []

        for geometry in rivers_utm.geometry:

            if (
                geometry is not None
                and not geometry.is_empty
            ):

                shapes.append(
                    (
                        geometry,
                        1
                    )
                )

        river_mask = rasterize(
            shapes=shapes,
            out_shape=(
                height,
                width
            ),
            transform=utm_transform,
            fill=0,
            dtype=np.uint8,
            all_touched=True
        )

        river_pixels = int(
            np.sum(
                river_mask > 0
            )
        )

        print(
            f"River pixels: "
            f"{river_pixels}"
        )

        # ----------------------------------------------------
        # Distance in METERS
        # ----------------------------------------------------

        distance_m = (
            distance_transform_edt(
                river_mask == 0,
                sampling=(
                    pixel_y_m,
                    pixel_x_m
                )
            )
            .astype(
                np.float32
            )
        )

        print(
            f"Distance minimum: "
            f"{distance_m.min():.2f} m"
        )

        print(
            f"Distance maximum: "
            f"{distance_m.max():.2f} m"
        )

        print(
            f"Distance mean: "
            f"{distance_m.mean():.2f} m"
        )

    # ========================================================
    # SAVE RIVER MASK
    # ========================================================

    mask_profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "uint8",
        "crs": image_crs,
        "transform": transform,
        "compress": "lzw",
        "nodata": 0
    }

    with rasterio.open(
        mask_path,
        "w",
        **mask_profile
    ) as dst:

        dst.write(
            river_mask,
            1
        )

    # ========================================================
    # SAVE DISTANCE
    # ========================================================

    distance_profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": 1,
        "dtype": "float32",
        "crs": image_crs,
        "transform": transform,
        "compress": "lzw",
        "nodata": -1
    }

    with rasterio.open(
        distance_path,
        "w",
        **distance_profile
    ) as dst:

        dst.write(
            distance_m,
            1
        )

    print(
        "\n✓ River mask saved:"
    )

    print(mask_path)

    print(
        "\n✓ River-distance raster saved:"
    )

    print(distance_path)

    return True


# ============================================================
# MAIN
# ============================================================

print("=" * 80)
print("HYDRORIVERS → CORRECTED METER DISTANCE FEATURES")
print("=" * 80)


# ============================================================
# CHECK DATA
# ============================================================

if not IMAGE_DIR.exists():

    raise FileNotFoundError(
        f"Image directory not found:\n"
        f"{IMAGE_DIR}"
    )


if not HYDRORIVERS_GDB.exists():

    raise FileNotFoundError(
        f"HydroRIVERS GDB not found:\n"
        f"{HYDRORIVERS_GDB}"
    )


# ============================================================
# FIND IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob(
        "*_image.tif"
    )
)

print(
    f"\nSentinel-1 images found: "
    f"{len(images)}"
)


if len(images) == 0:

    raise RuntimeError(
        "No *_image.tif files found."
    )


# ============================================================
# LOAD HYDRORIVERS
# ============================================================

print("\n")
print("=" * 80)
print("LOADING HYDRORIVERS")
print("=" * 80)


rivers = gpd.read_file(
    HYDRORIVERS_GDB,
    layer=LAYER_NAME
)


print(
    f"HydroRIVERS features: "
    f"{len(rivers)}"
)

print(
    f"HydroRIVERS CRS: "
    f"{rivers.crs}"
)


# ============================================================
# PROCESS ALL IMAGES
# ============================================================

successful = 0
failed = 0


for index, image_path in enumerate(
    images,
    start=1
):

    print(
        f"\n[{index}/{len(images)}]"
    )

    try:

        result = process_scene(
            image_path,
            rivers
        )

        if result:

            successful += 1

        else:

            failed += 1

    except Exception as error:

        failed += 1

        print(
            "\n❌ ERROR:"
        )

        print(error)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n\n")
print("=" * 80)
print("CORRECTED HYDRORIVERS PROCESSING COMPLETE")
print("=" * 80)

print(
    f"\nTotal images: "
    f"{len(images)}"
)

print(
    f"Successful: "
    f"{successful}"
)

print(
    f"Failed: "
    f"{failed}"
)

print(
    "\nOutput:"
)

print(
    OUTPUT_DIR
)

print(
    "\n✓ Finished!"
)