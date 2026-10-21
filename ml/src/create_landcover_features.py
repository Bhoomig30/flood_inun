from pathlib import Path
import math
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

WORLDCOVER_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "esa_worldcover"
)

OUTPUT_DIR = (
    ML_DIR
    / "data"
    / "landcover_features"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# SETTINGS
# ============================================================

DRY_RUN = False


# ============================================================
# SCENE ID
# ============================================================

def scene_id(path):

    name = path.stem

    if name.endswith("_image"):
        name = name[:-6]

    return name


# ============================================================
# FIND WORLDCOVER TILES
# ============================================================

worldcover_files = sorted(
    WORLDCOVER_DIR.rglob(
        "ESA_WorldCover_10m_2021_v200_*_Map.tif"
    )
)

print("=" * 80)
print("SEN1FLOODS11 → ESA WORLDCOVER LAND-COVER FEATURES")
print("=" * 80)

print("\nSentinel image directory:")
print(IMAGE_DIR)

print("\nWorldCover directory:")
print(WORLDCOVER_DIR)

print("\nWorldCover tiles found:")
print(len(worldcover_files))


if not worldcover_files:

    raise SystemExit(
        "❌ No ESA WorldCover GeoTIFF files found."
    )


# ============================================================
# SCENES
# ============================================================

images = sorted(
    IMAGE_DIR.glob(
        "*_image.tif"
    )
)

print(
    "\nSatellite scenes:",
    len(images)
)


# ============================================================
# TILE INFORMATION
# ============================================================

print("\n")
print("=" * 80)
print("WORLDCOVER TILES")
print("=" * 80)

for path in worldcover_files:

    print(
        " ",
        path.name
    )


# ============================================================
# LOAD WORLD COVER DATASET INFO
# ============================================================

tile_info = []

for path in worldcover_files:

    with rasterio.open(path) as src:

        tile_info.append(
            {
                "path": path,
                "bounds": src.bounds,
                "crs": src.crs
            }
        )


# ============================================================
# CHECK SCENE INTERSECTION
# ============================================================

def get_intersecting_tiles(
    scene_bounds,
    scene_crs
):

    result = []

    for tile in tile_info:

        bounds = tile["bounds"]

        if (
            scene_bounds.right > bounds.left
            and scene_bounds.left < bounds.right
            and scene_bounds.top > bounds.bottom
            and scene_bounds.bottom < bounds.top
        ):

            result.append(
                tile["path"]
            )

    return result


# ============================================================
# SCENE ANALYSIS
# ============================================================

scene_tiles = {}

all_required_tiles = set()

for image in images:

    sid = scene_id(image)

    with rasterio.open(image) as src:

        tiles = get_intersecting_tiles(
            src.bounds,
            src.crs
        )

    scene_tiles[sid] = tiles

    for tile in tiles:

        all_required_tiles.add(
            tile
        )


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("SCENE / WORLDCOVER COVERAGE")
print("=" * 80)

covered = 0
not_covered = 0

for sid in list(scene_tiles.keys())[:20]:

    tiles = scene_tiles[sid]

    print(
        f"\n{sid}"
    )

    if tiles:

        covered += 1

        for tile in tiles:

            print(
                "  ✓",
                tile.name
            )

    else:

        not_covered += 1

        print(
            "  ⚠ No WorldCover tile"
        )


# ============================================================
# COMPLETE COVERAGE COUNT
# ============================================================

covered = sum(
    1
    for tiles in scene_tiles.values()
    if tiles
)

not_covered = len(images) - covered


print("\n")
print("=" * 80)
print("COVERAGE SUMMARY")
print("=" * 80)

print(
    "\nScenes with WorldCover:",
    covered
)

print(
    "Scenes without WorldCover:",
    not_covered
)

print(
    "Unique WorldCover tiles used:",
    len(all_required_tiles)
)


# ============================================================
# DRY RUN
# ============================================================

if DRY_RUN:

    print("\n")
    print("=" * 80)
    print("DRY RUN COMPLETE")
    print("=" * 80)

    print(
        "\nNo land-cover files were created."
    )

    print(
        "\nIf the coverage looks correct,"
    )

    print(
        "change:"
    )

    print(
        "    DRY_RUN = False"
    )

    print(
        "and run this script again."
    )

    raise SystemExit


# ============================================================
# CREATE LAND-COVER FEATURE
# ============================================================

print("\n")
print("=" * 80)
print("CREATING SCENE-ALIGNED LAND-COVER FEATURES")
print("=" * 80)

created = 0
skipped = 0
failed = 0


for index, image in enumerate(
    images,
    start=1
):

    sid = scene_id(image)

    output = (
        OUTPUT_DIR
        / f"{sid}_landcover.tif"
    )

    print(
        f"\n[{index}/{len(images)}] {sid}"
    )


    # --------------------------------------------------------
    # EXISTING
    # --------------------------------------------------------

    if output.exists():

        print(
            "  ✓ Already exists"
        )

        skipped += 1

        continue


    tiles = scene_tiles[sid]


    if not tiles:

        print(
            "  ⚠ No WorldCover coverage"
        )

        failed += 1

        continue


    try:

        # ----------------------------------------------------
        # READ SENTINEL GRID
        # ----------------------------------------------------

        with rasterio.open(
            image
        ) as scene:

            dst_width = scene.width
            dst_height = scene.height

            dst_transform = scene.transform
            dst_crs = scene.crs

            bounds = scene.bounds


        # ----------------------------------------------------
        # OPEN WORLD COVER TILES
        # ----------------------------------------------------

        sources = []

        for tile in tiles:

            sources.append(
                rasterio.open(tile)
            )


        try:

            # ------------------------------------------------
            # MERGE
            # ------------------------------------------------

            mosaic, mosaic_transform = merge(
                sources,
                bounds=(
                    bounds.left,
                    bounds.bottom,
                    bounds.right,
                    bounds.top
                )
            )


            src_crs = sources[0].crs


            # ------------------------------------------------
            # DESTINATION
            # ------------------------------------------------

            destination = np.zeros(
                (
                    dst_height,
                    dst_width
                ),
                dtype=np.uint8
            )


            # ------------------------------------------------
            # RESAMPLE
            #
            # IMPORTANT:
            # WorldCover is categorical.
            # Therefore use NEAREST.
            # ------------------------------------------------

            reproject(
                source=mosaic,
                destination=destination,

                src_transform=mosaic_transform,
                src_crs=src_crs,

                dst_transform=dst_transform,
                dst_crs=dst_crs,

                resampling=Resampling.nearest
            )


            # ------------------------------------------------
            # SAVE
            # ------------------------------------------------

            profile = {
                "driver": "GTiff",
                "height": dst_height,
                "width": dst_width,
                "count": 1,
                "dtype": "uint8",
                "crs": dst_crs,
                "transform": dst_transform,

                "compress": "deflate"
            }


            with rasterio.open(
                output,
                "w",
                **profile
            ) as dst:

                dst.write(
                    destination,
                    1
                )


        finally:

            for src in sources:

                src.close()


        print(
            "  ✓ Created:",
            output.name
        )

        created += 1


    except Exception as e:

        print(
            "  ❌ Error:",
            e
        )

        failed += 1


# ============================================================
# FINAL
# ============================================================

print("\n")
print("=" * 80)
print("LAND-COVER FEATURE CREATION COMPLETE")
print("=" * 80)

print(
    "\nSentinel scenes:",
    len(images)
)

print(
    "WorldCover tiles:",
    len(worldcover_files)
)

print(
    "Features created:",
    created
)

print(
    "Already existing:",
    skipped
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
    "\nDone."
)