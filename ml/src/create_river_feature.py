# from pathlib import Path

# import numpy as np
# import geopandas as gpd
# import rasterio
# from rasterio.features import rasterize
# from scipy.ndimage import distance_transform_edt


# # ============================================================
# # SETTINGS
# # ============================================================

# ML_DIR = Path(__file__).resolve().parents[1]

# # Existing SEN1FLOODS11 images
# IMAGE_DIR = ML_DIR / "data" / "images"

# # HydroRIVERS
# HYDRO_DIR = (
#     ML_DIR
#     / "data"
#     / "external"
#     / "hydrorivers"
# )

# GDB_PATH = (
#     HYDRO_DIR
#     / "HydroRIVERS_v10_as.gdb"
# )

# # Output directory
# OUTPUT_DIR = (
#     ML_DIR
#     / "data"
#     / "river_features"
# )

# OUTPUT_DIR.mkdir(
#     parents=True,
#     exist_ok=True
# )

# # Test image
# IMAGE_NAME = "1010394_image.tif"

# # Safety limit
# MAX_RIVERS = 100000


# # ============================================================
# # START
# # ============================================================

# print("=" * 80)
# print("HYDRORIVERS → RIVER DISTANCE FEATURE")
# print("=" * 80)


# # ============================================================
# # CHECK IMAGE
# # ============================================================

# image_path = IMAGE_DIR / IMAGE_NAME

# if not image_path.exists():

#     print("\n❌ Image not found:")
#     print(image_path)

#     print("\nAvailable images:")

#     for file in list(
#         IMAGE_DIR.glob("*.tif")
#     )[:20]:

#         print(" ", file.name)

#     raise SystemExit


# print("\n✓ Image found:")
# print(image_path)


# # ============================================================
# # CHECK HYDRORIVERS
# # ============================================================

# if not GDB_PATH.exists():

#     print("\n❌ HydroRIVERS GDB not found:")
#     print(GDB_PATH)

#     raise SystemExit


# print("\n✓ HydroRIVERS found:")
# print(GDB_PATH)


# # ============================================================
# # READ IMAGE SPATIAL INFORMATION
# # ============================================================

# print("\n")
# print("=" * 80)
# print("READING FLOOD IMAGE")
# print("=" * 80)


# with rasterio.open(image_path) as src:

#     width = src.width
#     height = src.height

#     transform = src.transform

#     image_crs = src.crs

#     bounds = src.bounds

#     resolution = src.res


# print("\nImage size:")
# print(
#     f"{width} × {height}"
# )

# print("\nCRS:")
# print(image_crs)

# print("\nResolution:")
# print(resolution)

# print("\nBounds:")
# print(bounds)


# # ============================================================
# # CHECK CRS
# # ============================================================

# if image_crs is None:

#     print(
#         "\n❌ Image does not contain CRS information."
#     )

#     raise SystemExit


# # ============================================================
# # OPEN HYDRORIVERS
# # ============================================================

# print("\n")
# print("=" * 80)
# print("LOADING HYDRORIVERS")
# print("=" * 80)


# LAYER_NAME = "HydroRIVERS_v10_as"


# try:

#     rivers = gpd.read_file(
#         GDB_PATH,
#         layer=LAYER_NAME,
#         bbox=(
#             bounds.left,
#             bounds.bottom,
#             bounds.right,
#             bounds.top
#         )
#     )

# except Exception as e:

#     print(
#         "\n❌ Could not read HydroRIVERS."
#     )

#     print("\nError:")
#     print(e)

#     raise SystemExit


# print(
#     "\nRiver segments intersecting scene:"
# )

# print(
#     len(rivers)
# )


# # ============================================================
# # HANDLE NO RIVERS
# # ============================================================

# if len(rivers) == 0:

#     print(
#         "\n⚠ No HydroRIVERS segments "
#         "were found inside this image."
#     )

#     print(
#         "Creating an empty river mask "
#         "and infinite-distance raster."
#     )


# # ============================================================
# # REPROJECT HYDRORIVERS
# # ============================================================

# if len(rivers) > 0:

#     print(
#         "\nReprojecting HydroRIVERS "
#         "to image CRS..."
#     )

#     rivers = rivers.to_crs(
#         image_crs
#     )


# # ============================================================
# # LIMIT NUMBER OF RIVERS
# # ============================================================

# if len(rivers) > MAX_RIVERS:

#     print(
#         f"\n⚠ Found {len(rivers)} river segments."
#     )

#     print(
#         f"Limiting processing to "
#         f"{MAX_RIVERS} segments."
#     )

#     rivers = rivers.iloc[
#         :MAX_RIVERS
#     ].copy()


# # ============================================================
# # RASTERIZE RIVERS
# # ============================================================

# print("\n")
# print("=" * 80)
# print("RASTERIZING RIVER NETWORK")
# print("=" * 80)


# river_raster = np.zeros(
#     (height, width),
#     dtype=np.uint8
# )


# if len(rivers) > 0:

#     shapes = []

#     for geometry in rivers.geometry:

#         if geometry is None:

#             continue

#         if geometry.is_empty:

#             continue

#         shapes.append(
#             (
#                 geometry,
#                 1
#             )
#         )


#     if len(shapes) > 0:

#         river_raster = rasterize(
#             shapes=shapes,
#             out_shape=(
#                 height,
#                 width
#             ),
#             transform=transform,
#             fill=0,
#             dtype=np.uint8,
#             all_touched=True
#         )


# river_pixels = int(
#     np.sum(
#         river_raster == 1
#     )
# )


# print(
#     "\nRiver pixels:"
# )

# print(
#     river_pixels
# )


# # ============================================================
# # CALCULATE DISTANCE TO RIVER
# # ============================================================

# print("\n")
# print("=" * 80)
# print("CALCULATING DISTANCE TO NEAREST RIVER")
# print("=" * 80)


# if river_pixels > 0:

#     # distance_transform_edt calculates the
#     # distance from zero pixels to the nearest
#     # non-zero pixel.
#     #
#     # Since river pixels = 1,
#     # this gives distance from land pixels
#     # to the nearest river pixel.

#     distance_pixels = (
#         distance_transform_edt(
#             river_raster == 0
#         )
#     )

# else:

#     distance_pixels = np.full(
#         (
#             height,
#             width
#         ),
#         np.inf,
#         dtype=np.float32
#     )


# # ============================================================
# # PIXEL DISTANCE → MAP DISTANCE
# # ============================================================

# pixel_size_x = abs(
#     transform.a
# )

# pixel_size_y = abs(
#     transform.e
# )


# average_pixel_size = (
#     pixel_size_x
#     + pixel_size_y
# ) / 2.0


# distance_map = (
#     distance_pixels
#     * average_pixel_size
# )


# distance_map = distance_map.astype(
#     np.float32
# )


# # ============================================================
# # NOTE ABOUT EPSG:4326
# # ============================================================

# if image_crs.is_geographic:

#     distance_unit = "degrees"

#     print(
#         "\n⚠ Image CRS is geographic:"
#     )

#     print(
#         "EPSG:4326"
#     )

#     print(
#         "Distance is currently stored "
#         "in degrees, NOT meters."
#     )

# else:

#     distance_unit = "map units"

#     print(
#         "\n✓ Image CRS is projected."
#     )


# print(
#     "\nDistance unit:"
# )

# print(
#     distance_unit
# )


# # ============================================================
# # SAVE RIVER MASK
# # ============================================================

# river_mask_path = (
#     OUTPUT_DIR
#     / IMAGE_NAME.replace(
#         "_image.tif",
#         "_river_mask.tif"
#     )
# )


# with rasterio.open(
#     image_path
# ) as src:

#     profile = src.profile.copy()


# profile.update(
#     {
#         "driver": "GTiff",
#         "count": 1,
#         "dtype": "uint8",
#         "nodata": 0,
#         "compress": "lzw"
#     }
# )


# with rasterio.open(
#     river_mask_path,
#     "w",
#     **profile
# ) as dst:

#     dst.write(
#         river_raster,
#         1
#     )


# print("\n✓ River mask saved:")
# print(
#     river_mask_path
# )


# # ============================================================
# # SAVE DISTANCE RASTER
# # ============================================================

# distance_path = (
#     OUTPUT_DIR
#     / IMAGE_NAME.replace(
#         "_image.tif",
#         "_river_distance.tif"
#     )
# )


# profile.update(
#     {
#         "driver": "GTiff",
#         "count": 1,
#         "dtype": "float32",
#         "nodata": -9999,
#         "compress": "lzw"
#     }
# )


# distance_output = (
#     distance_map.copy()
# )


# distance_output[
#     ~np.isfinite(
#         distance_output
#     )
# ] = -9999


# with rasterio.open(
#     distance_path,
#     "w",
#     **profile
# ) as dst:

#     dst.write(
#         distance_output,
#         1
#     )


# print(
#     "\n✓ River-distance raster saved:"
# )

# print(
#     distance_path
# )


# # ============================================================
# # FINAL SUMMARY
# # ============================================================

# print("\n")
# print("=" * 80)
# print("HYDRORIVERS FEATURE CREATION COMPLETE")
# print("=" * 80)

# print("\nInput image:")
# print(
#     IMAGE_NAME
# )

# print("\nImage dimensions:")
# print(
#     f"{width} × {height}"
# )

# print("\nImage CRS:")
# print(
#     image_crs
# )

# print("\nRiver segments:")
# print(
#     len(rivers)
# )

# print("\nRiver pixels:")
# print(
#     river_pixels
# )

# print("\nDistance unit:")
# print(
#     distance_unit
# )

# print("\nOutput directory:")
# print(
#     OUTPUT_DIR
# )

# print("\nCreated files:")

# print(
#     "1.",
#     river_mask_path.name
# )

# print(
#     "2.",
#     distance_path.name
# )

# print("\n✓ Done!")
from pathlib import Path

import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from scipy.ndimage import distance_transform_edt


# ============================================================
# HYDRORIVERS → RIVER DISTANCE FEATURE
# ============================================================

# ------------------------------------------------------------
# PROJECT PATHS
# ------------------------------------------------------------

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

HYDRO_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "hydrorivers"
)

GDB_PATH = (
    HYDRO_DIR
    / "HydroRIVERS_v10_as.gdb"
)

OUTPUT_DIR = (
    ML_DIR
    / "data"
    / "river_features"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# SELECT AN INDIAN SEN1FLOODS11 SCENE
# ============================================================

IMAGE_NAME = "1017769_image.tif"

LAYER_NAME = "HydroRIVERS_v10_as"

# Safety limit for river features
MAX_RIVERS = 100000


# ============================================================
# START
# ============================================================

print("=" * 80)
print("HYDRORIVERS → RIVER DISTANCE FEATURE")
print("=" * 80)


# ============================================================
# CHECK IMAGE
# ============================================================

image_path = IMAGE_DIR / IMAGE_NAME

if not image_path.exists():

    print("\n❌ Image not found:")
    print(image_path)

    print("\nAvailable images with similar names:")

    for file in IMAGE_DIR.glob("*_image.tif"):
        print(" ", file.name)

    raise SystemExit


print("\n✓ Image found:")
print(image_path)


# ============================================================
# CHECK HYDRORIVERS
# ============================================================

if not GDB_PATH.exists():

    print("\n❌ HydroRIVERS GDB not found:")
    print(GDB_PATH)

    raise SystemExit


print("\n✓ HydroRIVERS found:")
print(GDB_PATH)


# ============================================================
# READ IMAGE INFORMATION
# ============================================================

print("\n")
print("=" * 80)
print("READING FLOOD IMAGE")
print("=" * 80)


with rasterio.open(image_path) as src:

    width = src.width
    height = src.height

    transform = src.transform

    image_crs = src.crs

    bounds = src.bounds

    resolution = src.res


print("\nImage size:")
print(f"{width} × {height}")

print("\nCRS:")
print(image_crs)

print("\nResolution:")
print(resolution)

print("\nBounds:")
print(bounds)


# ============================================================
# CHECK CRS
# ============================================================

if image_crs is None:

    print(
        "\n❌ Image has no CRS information."
    )

    raise SystemExit


# ============================================================
# LOAD HYDRORIVERS
# ============================================================

print("\n")
print("=" * 80)
print("LOADING HYDRORIVERS")
print("=" * 80)


try:

    rivers = gpd.read_file(
        GDB_PATH,
        layer=LAYER_NAME,
        bbox=(
            bounds.left,
            bounds.bottom,
            bounds.right,
            bounds.top
        )
    )

except Exception as e:

    print("\n❌ Could not read HydroRIVERS.")

    print("\nError:")
    print(e)

    raise SystemExit


print("\nRiver segments intersecting scene:")
print(len(rivers))


# ============================================================
# CHECK WHETHER RIVERS EXIST
# ============================================================

if len(rivers) == 0:

    print(
        "\n⚠ No HydroRIVERS segments were found "
        "inside this scene."
    )

    print(
        "\nThis scene cannot produce a useful "
        "river-distance feature."
    )

    raise SystemExit


# ============================================================
# REPROJECT RIVERS
# ============================================================

print("\nReprojecting HydroRIVERS...")

rivers = rivers.to_crs(
    image_crs
)


# ============================================================
# LIMIT NUMBER OF RIVERS
# ============================================================

if len(rivers) > MAX_RIVERS:

    print(
        f"\n⚠ Found {len(rivers)} river segments."
    )

    print(
        f"Limiting to {MAX_RIVERS}."
    )

    rivers = rivers.iloc[
        :MAX_RIVERS
    ].copy()


# ============================================================
# RASTERIZE RIVERS
# ============================================================

print("\n")
print("=" * 80)
print("RASTERIZING RIVER NETWORK")
print("=" * 80)


river_raster = np.zeros(
    (height, width),
    dtype=np.uint8
)


shapes = []

for geometry in rivers.geometry:

    if geometry is None:
        continue

    if geometry.is_empty:
        continue

    shapes.append(
        (
            geometry,
            1
        )
    )


if len(shapes) == 0:

    print(
        "\n❌ No valid river geometries."
    )

    raise SystemExit


river_raster = rasterize(
    shapes=shapes,
    out_shape=(
        height,
        width
    ),
    transform=transform,
    fill=0,
    dtype=np.uint8,
    all_touched=True
)


river_pixels = int(
    np.sum(
        river_raster == 1
    )
)


print("\nRiver pixels:")
print(river_pixels)


if river_pixels == 0:

    print(
        "\n❌ HydroRIVERS intersected the "
        "bounding box, but no river pixels "
        "were rasterized."
    )

    raise SystemExit


# ============================================================
# DISTANCE TO NEAREST RIVER
# ============================================================

print("\n")
print("=" * 80)
print("CALCULATING DISTANCE TO NEAREST RIVER")
print("=" * 80)


distance_pixels = distance_transform_edt(
    river_raster == 0
)


# ============================================================
# CONVERT PIXELS TO MAP DISTANCE
# ============================================================

pixel_size_x = abs(
    transform.a
)

pixel_size_y = abs(
    transform.e
)

average_pixel_size = (
    pixel_size_x
    + pixel_size_y
) / 2.0


distance_map = (
    distance_pixels
    * average_pixel_size
)


distance_map = distance_map.astype(
    np.float32
)


# ============================================================
# DISTANCE UNIT
# ============================================================

if image_crs.is_geographic:

    distance_unit = "degrees"

    print(
        "\n⚠ Image uses geographic CRS EPSG:4326."
    )

    print(
        "Current distance is stored in degrees."
    )

else:

    distance_unit = "map_units"

    print(
        "\n✓ Image uses projected CRS."
    )


# ============================================================
# SAVE RIVER MASK
# ============================================================

river_mask_path = (
    OUTPUT_DIR
    / IMAGE_NAME.replace(
        "_image.tif",
        "_river_mask.tif"
    )
)


with rasterio.open(
    image_path
) as src:

    profile = src.profile.copy()


profile.update(
    {
        "driver": "GTiff",
        "count": 1,
        "dtype": "uint8",
        "nodata": 0,
        "compress": "lzw"
    }
)


with rasterio.open(
    river_mask_path,
    "w",
    **profile
) as dst:

    dst.write(
        river_raster,
        1
    )


print("\n✓ River mask saved:")
print(river_mask_path)


# ============================================================
# SAVE DISTANCE RASTER
# ============================================================

distance_path = (
    OUTPUT_DIR
    / IMAGE_NAME.replace(
        "_image.tif",
        "_river_distance.tif"
    )
)


profile.update(
    {
        "driver": "GTiff",
        "count": 1,
        "dtype": "float32",
        "nodata": -9999,
        "compress": "lzw"
    }
)


distance_output = distance_map.copy()


distance_output[
    ~np.isfinite(
        distance_output
    )
] = -9999


with rasterio.open(
    distance_path,
    "w",
    **profile
) as dst:

    dst.write(
        distance_output,
        1
    )


print("\n✓ River-distance raster saved:")
print(distance_path)


# ============================================================
# FINAL SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("HYDRORIVERS FEATURE CREATION COMPLETE")
print("=" * 80)

print("\nInput scene:")
print(IMAGE_NAME)

print("\nImage dimensions:")
print(f"{width} × {height}")

print("\nImage CRS:")
print(image_crs)

print("\nRiver segments:")
print(len(rivers))

print("\nRiver pixels:")
print(river_pixels)

print("\nDistance unit:")
print(distance_unit)

print("\nOutput directory:")
print(OUTPUT_DIR)

print("\nCreated files:")

print(
    "1.",
    river_mask_path.name
)

print(
    "2.",
    distance_path.name
)

print("\n✓ Done!")