from pathlib import Path
import json

import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import unary_union


# ============================================================
# PATHS
# ============================================================

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

SCENE_ID = "1017769"

FLOOD_MASK = (
    DATA
    / "predictions"
    / f"{SCENE_ID}_predicted_flood.tif"
)

OUTPUT_DIR = DATA / "geojson"
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_FILE = (
    OUTPUT_DIR
    / f"{SCENE_ID}_flood.geojson"
)


# ============================================================
# START
# ============================================================

print("=" * 80)
print("FLOOD MASK → GEOJSON")
print("=" * 80)

print("\nScene:", SCENE_ID)

if not FLOOD_MASK.exists():
    raise FileNotFoundError(
        f"Flood mask not found:\n{FLOOD_MASK}"
    )

print("OK Flood mask:", FLOOD_MASK.name)


# ============================================================
# LOAD FLOOD MASK
# ============================================================

print("\n" + "=" * 80)
print("LOADING FLOOD MASK")
print("=" * 80)

with rasterio.open(FLOOD_MASK) as src:

    mask = src.read(1)

    transform = src.transform
    crs = src.crs

    height = src.height
    width = src.width

    bounds = src.bounds


print("Size:", width, "x", height)
print("CRS:", crs)
print("Bounds:", bounds)
print("Classes:", np.unique(mask))


# ============================================================
# CHECK CRS
# ============================================================

if crs is None:
    raise ValueError(
        "Flood mask does not have a CRS."
    )

if crs.to_epsg() != 4326:

    raise ValueError(
        f"Expected EPSG:4326 but found {crs}"
    )


# ============================================================
# FLOOD STATISTICS
# ============================================================

flood_mask = (
    mask == 1
)

flood_pixels = int(
    flood_mask.sum()
)

total_pixels = mask.size

flood_percentage = (
    flood_pixels
    / total_pixels
    * 100
)

print("\n" + "=" * 80)
print("FLOOD STATISTICS")
print("=" * 80)

print("Total pixels:", total_pixels)
print("Flood pixels:", flood_pixels)

print(
    f"Flood percentage: "
    f"{flood_percentage:.2f}%"
)


# ============================================================
# EXTRACT FLOOD POLYGONS
# ============================================================

print("\n" + "=" * 80)
print("EXTRACTING FLOOD POLYGONS")
print("=" * 80)

polygons = []

count = 0

for geometry, value in shapes(
    mask.astype(np.uint8),
    mask=flood_mask,
    transform=transform
):

    if value != 1:
        continue

    polygon = shape(geometry)

    if polygon.is_empty:
        continue

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        continue

    polygons.append(polygon)

    count += 1


print("Raw flood polygons:", count)


# ============================================================
# CHECK POLYGONS
# ============================================================

if not polygons:

    raise RuntimeError(
        "No flood polygons were generated."
    )


# ============================================================
# MERGE POLYGONS
# ============================================================

print("\nMerging connected flood regions...")

merged = unary_union(polygons)

if merged.is_empty:

    raise RuntimeError(
        "Merged flood geometry is empty."
    )


# ============================================================
# CONVERT TO GEOJSON FEATURES
# ============================================================

features = []

if merged.geom_type == "Polygon":

    geometries = [merged]

elif merged.geom_type == "MultiPolygon":

    geometries = list(merged.geoms)

else:

    geometries = []

    for polygon in polygons:

        if polygon.geom_type == "Polygon":
            geometries.append(polygon)

        elif polygon.geom_type == "MultiPolygon":

            geometries.extend(
                list(polygon.geoms)
            )


print(
    "Final polygons:",
    len(geometries)
)


for index, polygon in enumerate(
    geometries,
    start=1
):

    if polygon.is_empty:
        continue

    area = polygon.area

    feature = {
        "type": "Feature",
        "properties": {
            "scene_id": SCENE_ID,
            "flood_class": 1,
            "polygon_id": index,
            "area_degrees2": float(area),
        },
        "geometry": mapping(
            polygon
        ),
    }

    features.append(feature)


# ============================================================
# CREATE FEATURE COLLECTION
# ============================================================

geojson = {
    "type": "FeatureCollection",

    "name": (
        f"{SCENE_ID}_flood_inundation"
    ),

    "crs": {
        "type": "name",
        "properties": {
            "name": "EPSG:4326"
        }
    },

    "properties": {
        "scene_id": SCENE_ID,
        "total_pixels": int(total_pixels),
        "flood_pixels": int(flood_pixels),
        "flood_percentage": float(
            flood_percentage
        ),
        "source": (
            "Random Forest "
            "12-feature flood model"
        ),
        "threshold": 0.65,
    },

    "features": features,
}


# ============================================================
# SAVE GEOJSON
# ============================================================

print("\n" + "=" * 80)
print("SAVING GEOJSON")
print("=" * 80)

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        geojson,
        f,
        indent=2
    )


print("Saved:")
print(OUTPUT_FILE)


# ============================================================
# FINAL VERIFICATION
# ============================================================

print("\n" + "=" * 80)
print("FINAL VERIFICATION")
print("=" * 80)

with open(
    OUTPUT_FILE,
    "r",
    encoding="utf-8"
) as f:

    check = json.load(f)


print(
    "GeoJSON type:",
    check["type"]
)

print(
    "Features:",
    len(check["features"])
)

print(
    "CRS:",
    check["crs"]["properties"]["name"]
)

print(
    "Scene:",
    check["properties"]["scene_id"]
)

print(
    "Flood percentage:",
    f"{check['properties']['flood_percentage']:.2f}%"
)


print("\n" + "=" * 80)
print("GEOJSON EXPORT COMPLETE")
print("=" * 80)

print("\nOutput:")
print(OUTPUT_FILE)

print("\nDONE.")