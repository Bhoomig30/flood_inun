from pathlib import Path

import rasterio
from shapely.geometry import box


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

SEN5_DEM_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "sen5"
    / "sen5"
    / "data_8channel"
    / "dem"
)

IMAGE_DIR = (
    ML_DIR
    / "data"
    / "images"
)


# ============================================================
# LOAD SEN5 BOUNDS
# ============================================================

sen5_files = sorted(
    SEN5_DEM_DIR.glob(
        "*_dem.tif"
    )
)

image_files = sorted(
    IMAGE_DIR.glob(
        "*_image.tif"
    )
)


print("=" * 80)
print("SEN5 ↔ SEN1FLOODS11 SPATIAL OVERLAP CHECK")
print("=" * 80)

print(
    f"\nSEN5 DEM samples: {len(sen5_files)}"
)

print(
    f"SEN1FLOODS11 images: {len(image_files)}"
)


# ============================================================
# BUILD SEN5 BOUNDS
# ============================================================

sen5_bounds = []

for path in sen5_files:

    with rasterio.open(path) as src:

        geom = box(
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top
        )

        sen5_bounds.append(
            (
                path.name,
                geom
            )
        )


# ============================================================
# CHECK OVERLAP
# ============================================================

overlap_pairs = []

scenes_with_overlap = set()

sen5_with_overlap = set()


for image_path in image_files:

    with rasterio.open(image_path) as src:

        image_geom = box(
            src.bounds.left,
            src.bounds.bottom,
            src.bounds.right,
            src.bounds.top
        )

    for sen5_name, sen5_geom in sen5_bounds:

        if image_geom.intersects(
            sen5_geom
        ):

            overlap_pairs.append(
                (
                    image_path.name,
                    sen5_name
                )
            )

            scenes_with_overlap.add(
                image_path.name
            )

            sen5_with_overlap.add(
                sen5_name
            )


# ============================================================
# RESULTS
# ============================================================

print("\n")
print("=" * 80)
print("RESULT")
print("=" * 80)

print(
    "\nOverlapping scene/SEN5 pairs:",
    len(overlap_pairs)
)

print(
    "SEN1 scenes with overlap:",
    len(scenes_with_overlap)
)

print(
    "SEN5 samples with overlap:",
    len(sen5_with_overlap)
)


# ============================================================
# SHOW EXAMPLES
# ============================================================

print("\n")
print("=" * 80)
print("FIRST 20 OVERLAPPING PAIRS")
print("=" * 80)

for scene, sen5 in overlap_pairs[:20]:

    print(
        f"{scene}  <-->  {sen5}"
    )


# ============================================================
# FINISH
# ============================================================

print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)