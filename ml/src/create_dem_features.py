from pathlib import Path
import math
import requests
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import reproject, Resampling
from shapely.geometry import box


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = ML_DIR / "data" / "images"

CACHE_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "dem_cache"
)

OUTPUT_DIR = (
    ML_DIR
    / "data"
    / "dem_features"
)

CACHE_DIR.mkdir(
    parents=True,
    exist_ok=True
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# SETTINGS
# ============================================================

# IMPORTANT:
# First run with True.
# Change to False only after inspecting the tile list.
DRY_RUN = False


# Copernicus GLO-30 public AWS bucket
BASE_URL = (
    "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
)


# ============================================================
# SCENE ID
# ============================================================

def scene_id(path):

    name = path.stem

    if name.endswith("_image"):
        name = name[:-6]

    return name


# ============================================================
# GET SCENE INFORMATION
# ============================================================

def get_scene_info(path):

    with rasterio.open(path) as src:

        return {
            "bounds": src.bounds,
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
            "transform": src.transform,
        }


# ============================================================
# COPERNICUS 1° TILE
# ============================================================

def tile_name(lon, lat):

    # Tile containing coordinate.
    lon_tile = math.floor(lon)
    lat_tile = math.floor(lat)

    ns = "N" if lat_tile >= 0 else "S"
    ew = "E" if lon_tile >= 0 else "W"

    return (
        f"Copernicus_DSM_COG_10_"
        f"{ns}{abs(lat_tile):02d}_00_"
        f"{ew}{abs(lon_tile):03d}_00_DEM"
    )


# ============================================================
# REQUIRED TILES FOR SCENE
# ============================================================

def required_tiles(bounds):

    # Small epsilon prevents an exact tile boundary
    # from unnecessarily selecting the neighboring tile.
    eps = 1e-10

    min_lon = math.floor(bounds.left + eps)
    max_lon = math.floor(bounds.right - eps)

    min_lat = math.floor(bounds.bottom + eps)
    max_lat = math.floor(bounds.top - eps)

    tiles = []

    for lat in range(
        min_lat,
        max_lat + 1
    ):

        for lon in range(
            min_lon,
            max_lon + 1
        ):

            tiles.append(
                tile_name(
                    lon + 0.5,
                    lat + 0.5
                )
            )

    return sorted(set(tiles))


# ============================================================
# DOWNLOAD ONE TILE
# ============================================================

def download_tile(tile):

    local_path = (
        CACHE_DIR
        / f"{tile}.tif"
    )

    if local_path.exists():

        print(
            f"    ✓ Cached: {tile}"
        )

        return local_path


    # Public bucket structure:
    #
    # Copernicus_DSM_COG_10_Nxx_00_Exxx_00_DEM/
    #
    # containing:
    #
    # Copernicus_DSM_COG_10_Nxx_00_Exxx_00_DEM.tif

    url = (
        f"{BASE_URL}/"
        f"{tile}/"
        f"{tile}.tif"
    )

    print(
        f"    Downloading: {tile}"
    )

    try:

        response = requests.get(
            url,
            stream=True,
            timeout=180
        )

        if response.status_code != 200:

            print(
                f"    ❌ HTTP {response.status_code}"
            )

            return None

        temporary = (
            CACHE_DIR
            / f"{tile}.download"
        )

        with open(
            temporary,
            "wb"
        ) as f:

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):

                if chunk:

                    f.write(chunk)

        temporary.replace(
            local_path
        )

        print(
            f"    ✓ Saved: {local_path.name}"
        )

        return local_path

    except Exception as e:

        print(
            f"    ❌ Download error: {e}"
        )

        return None


# ============================================================
# CREATE SCENE DEM
# ============================================================

def create_scene_dem(
    scene_path,
    dem_paths,
    output_path
):

    with rasterio.open(
        scene_path
    ) as scene:

        bounds = scene.bounds

        dst_crs = scene.crs
        dst_transform = scene.transform

        dst_width = scene.width
        dst_height = scene.height


        sources = []

        try:

            for path in dem_paths:

                src = rasterio.open(path)

                sources.append(src)


            if not sources:

                return False


            # ------------------------------------------------
            # MERGE DEM TILES
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

            destination = np.full(
                (
                    dst_height,
                    dst_width
                ),
                np.nan,
                dtype=np.float32
            )


            # ------------------------------------------------
            # REPROJECT TO SENTINEL GRID
            # ------------------------------------------------

            reproject(
                source=mosaic,
                destination=destination,

                src_transform=mosaic_transform,
                src_crs=src_crs,

                dst_transform=dst_transform,
                dst_crs=dst_crs,

                src_nodata=(
                    sources[0].nodata
                ),

                dst_nodata=np.nan,

                resampling=Resampling.bilinear
            )


            # ------------------------------------------------
            # SAVE
            # ------------------------------------------------

            profile = {
                "driver": "GTiff",
                "height": dst_height,
                "width": dst_width,
                "count": 1,
                "dtype": "float32",
                "crs": dst_crs,
                "transform": dst_transform,
                "nodata": np.nan,
                "compress": "deflate",
                "predictor": 3
            }


            with rasterio.open(
                output_path,
                "w",
                **profile
            ) as dst:

                dst.write(
                    destination,
                    1
                )


            return True


        finally:

            for src in sources:

                src.close()


# ============================================================
# START
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 → COPERNICUS GLO-30 DEM")
print("=" * 80)

print(
    "\nSentinel directory:"
)

print(
    IMAGE_DIR
)

print(
    "\nDEM cache:"
)

print(
    CACHE_DIR
)

print(
    "\nDEM output:"
)

print(
    OUTPUT_DIR
)

print(
    "\nDRY RUN:",
    DRY_RUN
)


# ============================================================
# FIND SCENES
# ============================================================

images = sorted(
    IMAGE_DIR.glob(
        "*_image.tif"
    )
)

print(
    f"\nSatellite scenes: {len(images)}"
)

if not images:

    raise SystemExit(
        "❌ No Sentinel scenes found."
    )


# ============================================================
# BUILD SCENE → TILE MAP
# ============================================================

scene_map = {}

all_tiles = set()


for image in images:

    sid = scene_id(image)

    info = get_scene_info(
        image
    )

    tiles = required_tiles(
        info["bounds"]
    )

    scene_map[sid] = {
        "image": image,
        "tiles": tiles,
        "info": info
    }

    all_tiles.update(
        tiles
    )


# ============================================================
# SHOW FIRST SCENES
# ============================================================

print("\n")
print("=" * 80)
print("FIRST 10 SCENE TILE REQUIREMENTS")
print("=" * 80)

for sid in list(scene_map.keys())[:10]:

    print(
        f"\n{sid}"
    )

    print(
        "  Tiles:"
    )

    for tile in scene_map[sid]["tiles"]:

        print(
            "   ",
            tile
        )


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("DEM TILE SUMMARY")
print("=" * 80)

print(
    f"\nUnique GLO-30 tiles required: "
    f"{len(all_tiles)}"
)

for tile in sorted(all_tiles):

    print(
        " ",
        tile
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
        "\nNo DEM tiles downloaded."
    )

    print(
        "No DEM features created."
    )

    print(
        "\nIf the tile names look correct,"
    )

    print(
        "change:"
    )

    print(
        "    DRY_RUN = False"
    )

    print(
        "and run the script again."
    )

    raise SystemExit


# ============================================================
# DOWNLOAD
# ============================================================

print("\n")
print("=" * 80)
print("DOWNLOADING GLO-30 TILES")
print("=" * 80)

downloaded = {}


for tile in sorted(all_tiles):

    path = download_tile(
        tile
    )

    if path:

        downloaded[tile] = path


print(
    "\nAvailable DEM tiles:",
    len(downloaded),
    "/",
    len(all_tiles)
)


# ============================================================
# CREATE SCENE DEMs
# ============================================================

print("\n")
print("=" * 80)
print("CREATING SCENE-ALIGNED DEM FEATURES")
print("=" * 80)

created = 0
failed = 0
existing = 0


for index, (
    sid,
    data
) in enumerate(
    scene_map.items(),
    start=1
):

    print(
        f"\n[{index}/{len(scene_map)}] {sid}"
    )


    output = (
        OUTPUT_DIR
        / f"{sid}_dem.tif"
    )


    if output.exists():

        print(
            "  ✓ Already exists"
        )

        existing += 1

        continue


    missing = [
        tile
        for tile in data["tiles"]
        if tile not in downloaded
    ]


    if missing:

        print(
            "  ⚠ Missing tiles:"
        )

        for tile in missing:

            print(
                "   ",
                tile
            )

        failed += 1

        continue


    dem_paths = [
        downloaded[tile]
        for tile in data["tiles"]
    ]


    try:

        success = create_scene_dem(
            data["image"],
            dem_paths,
            output
        )


        if success:

            print(
                "  ✓ Created:",
                output.name
            )

            created += 1

        else:

            print(
                "  ❌ Creation failed"
            )

            failed += 1


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
print("DEM FEATURE CREATION COMPLETE")
print("=" * 80)

print(
    "\nSentinel scenes:",
    len(images)
)

print(
    "Required DEM tiles:",
    len(all_tiles)
)

print(
    "Available DEM tiles:",
    len(downloaded)
)

print(
    "DEM files created:",
    created
)

print(
    "Already existing:",
    existing
)

print(
    "Failed:",
    failed
)

print(
    "\nOutput:"
)

print(
    OUTPUT_DIR
)

print(
    "\nNext step:"
)

print(
    "Run a DEM verification script before using"
)

print(
    "the DEMs for ML training."
)

print(
    "\nDone."
)