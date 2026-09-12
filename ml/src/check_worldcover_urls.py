from pathlib import Path
import requests


ML_DIR = Path(__file__).resolve().parents[1]

WORLD_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "esa_worldcover"
)


MISSING_TILES = [
    "N00E045",
    "N03E042",
    "N03E045",
    "N03E078",
    "N06E003",
    "N06E006",
    "N06E081",
    "N06W003",
    "N09E003",
    "N09W003",
    "N12E105",
    "N30E069",
    "N33E069",
    "N36W003",
    "N36W096",
    "N39W096",
    "S15W066",
    "S18W066",
    "S24W057",
    "S24W060",
    "S27W057",
    "S27W060",
]


BASE_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/"
    "v200/2021/map/"
)


print("=" * 80)
print("ESA WORLDCOVER TILE AVAILABILITY CHECK")
print("=" * 80)


available = []
missing = []
errors = []


for index, tile in enumerate(
    MISSING_TILES,
    start=1
):

    filename = (
        f"ESA_WorldCover_10m_2021_v200_"
        f"{tile}_Map.tif"
    )

    url = BASE_URL + filename

    print(
        f"\n[{index}/{len(MISSING_TILES)}] {tile}"
    )

    try:

        response = requests.head(
            url,
            timeout=30
        )

        print(
            "  HTTP:",
            response.status_code
        )

        if response.status_code == 200:

            size = response.headers.get(
                "Content-Length"
            )

            print(
                "  Size:",
                size
            )

            available.append(
                (tile, url, size)
            )

        elif response.status_code == 404:

            print(
                "  ❌ Not found"
            )

            missing.append(
                tile
            )

        else:

            print(
                "  ⚠ Unexpected response"
            )

            errors.append(
                (
                    tile,
                    response.status_code
                )
            )

    except Exception as e:

        print(
            "  ❌ Error:",
            e
        )

        errors.append(
            (
                tile,
                str(e)
            )
        )


print("\n")
print("=" * 80)
print("FINAL RESULT")
print("=" * 80)


print(
    "\nAvailable:",
    len(available)
)

for tile, url, size in available:

    print(
        f"  ✓ {tile}  ({size} bytes)"
    )


print(
    "\nNot found:",
    len(missing)
)

for tile in missing:

    print(
        f"  ❌ {tile}"
    )


print(
    "\nErrors:",
    len(errors)
)

for item in errors:

    print(
        " ",
        item
    )


print("\n")
print("=" * 80)
print("CHECK COMPLETE")
print("=" * 80)