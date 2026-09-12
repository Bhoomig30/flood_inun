from pathlib import Path
import zipfile


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = ML_DIR / "data"

OUTPUT_DIR = DATA_DIR / "sen1_metadata"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# FIND SEN1FLOODS11 ZIP
# ============================================================

zip_files = list(
    DATA_DIR.rglob(
        "Sen1Floods11-master.zip"
    )
)


if not zip_files:

    print(
        "❌ Sen1Floods11-master.zip not found."
    )

    raise SystemExit(1)


ZIP_PATH = zip_files[0]


print("=" * 80)
print("SEN1FLOODS11 METADATA EXTRACTION")
print("=" * 80)

print("\nZIP:")
print(ZIP_PATH)


# ============================================================
# EXTRACT METADATA
# ============================================================

METADATA_NAME = (
    "Sen1Floods11-master/"
    "Sen1Floods11_Metadata.geojson"
)


with zipfile.ZipFile(
    ZIP_PATH,
    "r"
) as z:

    files = z.namelist()

    if METADATA_NAME not in files:

        print(
            "\n❌ Metadata file not found:"
        )

        print(
            METADATA_NAME
        )

        print("\nAvailable files:")

        for file in files:

            print(
                " ",
                file
            )

        raise SystemExit(1)

    output_path = (
        OUTPUT_DIR
        / "Sen1Floods11_Metadata.geojson"
    )

    with z.open(
        METADATA_NAME
    ) as source, open(
        output_path,
        "wb"
    ) as target:

        target.write(
            source.read()
        )


# ============================================================
# RESULT
# ============================================================

print("\n✓ Metadata extracted successfully.")

print("\nSaved to:")
print(output_path)

print("\n")
print("=" * 80)
print("EXTRACTION COMPLETE")
print("=" * 80)