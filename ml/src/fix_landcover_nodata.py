from pathlib import Path
import rasterio


ML_DIR = Path(__file__).resolve().parents[1]

LANDCOVER_DIR = (
    ML_DIR
    / "data"
    / "landcover_features"
)


SCENES = [
    "1017769",
    "1076204",
    "273873",
    "305760",
    "401863",
    "707886",
    "772630",
    "952958",
]


print("=" * 80)
print("FIXING LAND-COVER NODATA METADATA")
print("=" * 80)


for scene in SCENES:

    path = LANDCOVER_DIR / f"{scene}_landcover.tif"

    print(f"\n{scene}")

    if not path.exists():

        print("  ❌ File not found")
        continue

    # --------------------------------------------------------
    # Open original
    # --------------------------------------------------------

    with rasterio.open(path) as src:

        profile = src.profile.copy()
        data = src.read()

    # --------------------------------------------------------
    # Set 0 as NoData
    # --------------------------------------------------------

    profile.update(
        nodata=0
    )

    # --------------------------------------------------------
    # Rewrite file
    # --------------------------------------------------------

    temporary = path.with_suffix(
        ".tmp.tif"
    )

    with rasterio.open(
        temporary,
        "w",
        **profile
    ) as dst:

        dst.write(data)

    temporary.replace(path)

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    with rasterio.open(path) as check:

        print(
            "  NoData:",
            check.nodata
        )

        print(
            "  Size:",
            check.width,
            "x",
            check.height
        )

        print(
            "  CRS:",
            check.crs
        )

    print("  ✓ Fixed")


print("\n")
print("=" * 80)
print("NODATA FIX COMPLETE")
print("=" * 80)