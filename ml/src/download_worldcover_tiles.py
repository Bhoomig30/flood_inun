from pathlib import Path
import requests


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

WORLD_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "esa_worldcover"
)

WORLD_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# MISSING TILES
# ============================================================

TILES = [
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


# ============================================================
# START
# ============================================================

print("=" * 80)
print("ESA WORLDCOVER TILE DOWNLOADER")
print("=" * 80)

print("\nOutput directory:")
print(WORLD_DIR)

print("\nTiles to download:", len(TILES))


downloaded = 0
existing = 0
failed = 0


# ============================================================
# DOWNLOAD
# ============================================================

for index, tile in enumerate(TILES, start=1):

    filename = (
        f"ESA_WorldCover_10m_2021_v200_"
        f"{tile}_Map.tif"
    )

    output = WORLD_DIR / filename

    url = BASE_URL + filename

    print("\n" + "-" * 80)

    print(
        f"[{index}/{len(TILES)}] {tile}"
    )

    # --------------------------------------------------------
    # ALREADY EXISTS
    # --------------------------------------------------------

    if output.exists():

        size_mb = (
            output.stat().st_size
            / (1024 * 1024)
        )

        print(
            f"✓ Already exists "
            f"({size_mb:.2f} MB)"
        )

        existing += 1

        continue


    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    print("Downloading...")

    temporary = output.with_suffix(
        ".download"
    )

    try:

        with requests.get(
            url,
            stream=True,
            timeout=120
        ) as response:

            response.raise_for_status()

            total_size = int(
                response.headers.get(
                    "Content-Length",
                    0
                )
            )

            downloaded_bytes = 0

            with open(
                temporary,
                "wb"
            ) as file:

                for chunk in response.iter_content(
                    chunk_size=1024 * 1024
                ):

                    if not chunk:
                        continue

                    file.write(chunk)

                    downloaded_bytes += len(
                        chunk
                    )

                    if total_size:

                        percent = (
                            downloaded_bytes
                            / total_size
                            * 100
                        )

                        print(
                            f"\r  Progress: "
                            f"{percent:6.2f}%",
                            end=""
                        )

        print()

        # ----------------------------------------------------
        # BASIC SIZE CHECK
        # ----------------------------------------------------

        if (
            total_size > 0
            and temporary.stat().st_size
            != total_size
        ):

            raise RuntimeError(
                "Downloaded file size does not "
                "match Content-Length."
            )


        # ----------------------------------------------------
        # FINALIZE
        # ----------------------------------------------------

        temporary.replace(
            output
        )

        size_mb = (
            output.stat().st_size
            / (1024 * 1024)
        )

        print(
            f"✓ Saved "
            f"({size_mb:.2f} MB)"
        )

        downloaded += 1


    except Exception as e:

        print(
            "\n❌ FAILED:",
            e
        )

        failed += 1

        if temporary.exists():

            temporary.unlink()


# ============================================================
# FINAL
# ============================================================

print("\n")
print("=" * 80)
print("WORLD COVER DOWNLOAD COMPLETE")
print("=" * 80)

print(
    "\nDownloaded:",
    downloaded
)

print(
    "Already existed:",
    existing
)

print(
    "Failed:",
    failed
)

print(
    "\nWorldCover directory:"
)

print(
    WORLD_DIR
)


if failed == 0:

    print(
        "\n✅ All requested WorldCover tiles "
        "are available."
    )

else:

    print(
        "\n⚠ Some WorldCover tiles failed."
    )