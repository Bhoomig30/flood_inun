from pathlib import Path
import re
import rasterio


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


# ============================================================
# FUNCTIONS
# ============================================================

def scene_id(path):
    name = path.stem

    if name.endswith("_image"):
        name = name[:-6]

    return name


def tile_name_from_coordinate(lat, lon):
    """
    Convert a coordinate to an ESA WorldCover
    3-degree x 3-degree tile name.

    Example:
        26.5 N, 93.2 E
        -> N24E093
    """

    lat_tile = int(lat // 3) * 3
    lon_tile = int(lon // 3) * 3

    lat_prefix = "N" if lat_tile >= 0 else "S"
    lon_prefix = "E" if lon_tile >= 0 else "W"

    lat_value = abs(lat_tile)
    lon_value = abs(lon_tile)

    return (
        f"{lat_prefix}{lat_value:02d}"
        f"{lon_prefix}{lon_value:03d}"
    )


# ============================================================
# EXISTING WORLDCOVER TILES
# ============================================================

existing_tiles = set()

pattern = re.compile(
    r"ESA_WorldCover_10m_2021_v200_"
    r"([NS]\d{2}[EW]\d{3})_Map\.tif$"
)

for path in WORLDCOVER_DIR.rglob("*.tif"):

    match = pattern.match(path.name)

    if match:

        existing_tiles.add(
            match.group(1)
        )


# ============================================================
# SENTINEL SCENES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)


print("=" * 80)
print("SEN1FLOODS11 → ESA WORLDCOVER TILE REQUIREMENTS")
print("=" * 80)

print(
    "\nSentinel scenes:",
    len(images)
)

print(
    "Existing unique WorldCover tiles:",
    len(existing_tiles)
)


# ============================================================
# REQUIRED TILES
# ============================================================

required_tiles = set()

scene_requirements = {}


for image in images:

    sid = scene_id(image)

    with rasterio.open(image) as src:

        bounds = src.bounds

        # ----------------------------------------------------
        # Determine every 3-degree WorldCover tile touched
        # by the scene bounding box.
        # ----------------------------------------------------

        min_lat_tile = int(bounds.bottom // 3) * 3
        max_lat_tile = int(bounds.top // 3) * 3

        min_lon_tile = int(bounds.left // 3) * 3
        max_lon_tile = int(bounds.right // 3) * 3

        tiles = set()

        lat = min_lat_tile

        while lat <= max_lat_tile:

            lon = min_lon_tile

            while lon <= max_lon_tile:

                tile = tile_name_from_coordinate(
                    lat + 0.01,
                    lon + 0.01
                )

                tiles.add(tile)

                lon += 3

            lat += 3


    scene_requirements[sid] = tiles

    required_tiles.update(tiles)


# ============================================================
# MISSING
# ============================================================

missing_tiles = (
    required_tiles
    - existing_tiles
)


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 80)
print("WORLD COVER TILE SUMMARY")
print("=" * 80)

print(
    "\nUnique tiles required:",
    len(required_tiles)
)

print(
    "Already available:",
    len(
        required_tiles & existing_tiles
    )
)

print(
    "Missing:",
    len(missing_tiles)
)


# ============================================================
# ALL REQUIRED
# ============================================================

print("\n")
print("=" * 80)
print("ALL REQUIRED TILES")
print("=" * 80)

for tile in sorted(required_tiles):

    status = (
        "✓ EXISTS"
        if tile in existing_tiles
        else "❌ MISSING"
    )

    print(
        f"{status:12} {tile}"
    )


# ============================================================
# MISSING ONLY
# ============================================================

print("\n")
print("=" * 80)
print("MISSING WORLDCOVER TILES")
print("=" * 80)

if missing_tiles:

    for tile in sorted(missing_tiles):

        print(
            " ",
            tile
        )

else:

    print(
        "✓ No missing tiles."
    )


# ============================================================
# SCENE COVERAGE
# ============================================================

fully_covered = 0
partially_covered = 0
not_covered = 0


for sid, tiles in scene_requirements.items():

    available = (
        tiles & existing_tiles
    )

    if available == tiles:

        fully_covered += 1

    elif available:

        partially_covered += 1

    else:

        not_covered += 1


print("\n")
print("=" * 80)
print("SCENE COVERAGE")
print("=" * 80)

print(
    "\nFully covered:",
    fully_covered
)

print(
    "Partially covered:",
    partially_covered
)

print(
    "Not covered:",
    not_covered
)


# ============================================================
# FINISH
# ============================================================

print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)