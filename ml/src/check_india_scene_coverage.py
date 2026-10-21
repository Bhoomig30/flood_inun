from pathlib import Path
import json

import rasterio
from shapely.geometry import shape, box


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

METADATA_FILE = (
    ML_DIR
    / "data"
    / "sen1_metadata"
    / "Sen1Floods11_Metadata.geojson"
)


# ============================================================
# LOAD METADATA
# ============================================================

with open(
    METADATA_FILE,
    "r",
    encoding="utf-8"
) as f:
    metadata = json.load(f)


india_feature = None

for feature in metadata["features"]:

    properties = feature.get(
        "properties",
        {}
    )

    if properties.get("ISO_CC") == "IND":

        india_feature = feature
        break


if india_feature is None:

    raise RuntimeError(
        "India metadata feature not found."
    )


india_polygon = shape(
    india_feature["geometry"]
)


print("=" * 80)
print("INDIA SEN1FLOODS11 SCENE COVERAGE CHECK")
print("=" * 80)

print(
    "\nIndia metadata date:"
)

print(
    india_feature["properties"].get(
        "s1_date"
    )
)

print(
    "\nIndia metadata polygon bounds:"
)

print(
    india_polygon.bounds
)


# ============================================================
# FIND IMAGES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    "\nSatellite scenes:"
)

print(
    len(images)
)


# ============================================================
# CHECK COVERAGE
# ============================================================

inside = 0
outside = 0

examples_inside = []
examples_outside = []


for image_path in images:

    with rasterio.open(
        image_path
    ) as src:

        scene_box = box(
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top
        )

    intersects = (
        india_polygon.intersects(
            scene_box
        )
    )

    if intersects:

        inside += 1

        if len(examples_inside) < 10:

            examples_inside.append(
                image_path.name
            )

    else:

        outside += 1

        if len(examples_outside) < 10:

            examples_outside.append(
                image_path.name
            )


# ============================================================
# RESULTS
# ============================================================

print("\n")
print("=" * 80)
print("RESULT")
print("=" * 80)

print(
    f"\nScenes intersecting India metadata polygon: "
    f"{inside}"
)

print(
    f"Scenes outside India metadata polygon: "
    f"{outside}"
)


print(
    "\nExamples inside:"
)

for name in examples_inside:

    print(
        " ",
        name
    )


print(
    "\nExamples outside:"
)

for name in examples_outside:

    print(
        " ",
        name
    )


print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)