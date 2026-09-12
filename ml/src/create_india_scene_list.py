from pathlib import Path
import json

import rasterio
from shapely.geometry import shape, box


ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

METADATA_FILE = (
    ML_DIR
    / "data"
    / "sen1_metadata"
    / "Sen1Floods11_Metadata.geojson"
)

OUTPUT_FILE = (
    ML_DIR
    / "data"
    / "india_scenes_covered.csv"
)


# ------------------------------------------------------------
# LOAD INDIA METADATA
# ------------------------------------------------------------

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
        "India feature not found."
    )


india_polygon = shape(
    india_feature["geometry"]
)


# ------------------------------------------------------------
# FIND SCENES
# ------------------------------------------------------------

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)


india_scenes = []


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

    if india_polygon.intersects(
        scene_box
    ):

        india_scenes.append(
            image_path.name
        )


# ------------------------------------------------------------
# SAVE
# ------------------------------------------------------------

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:

    f.write("scene\n")

    for scene in india_scenes:

        f.write(
            f"{scene}\n"
        )


# ------------------------------------------------------------
# RESULT
# ------------------------------------------------------------

print("=" * 80)
print("INDIA SCENE LIST")
print("=" * 80)

print(
    f"\nTotal India scenes: "
    f"{len(india_scenes)}"
)

print(
    f"\nSaved to:"
)

print(
    OUTPUT_FILE
)

print("\nFirst 20:")

for scene in india_scenes[:20]:

    print(
        " ",
        scene
    )

print("\nDone.")