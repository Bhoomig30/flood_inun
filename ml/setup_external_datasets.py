from pathlib import Path
import zipfile
import shutil

# ============================================================
# FLOOD INUNDATION PROJECT
# EXTERNAL DATASET SETUP
# ============================================================

print("=" * 70)
print("EXTERNAL DATASET SETUP")
print("=" * 70)

# ------------------------------------------------------------
# PROJECT LOCATION
# ------------------------------------------------------------

# This script is located at:
#
# flood-inundation-main/
#     flood-inundation-main/
#         ml/
#             setup_external_datasets.py
#
# Therefore this automatically finds the correct ml folder.

ML_DIR = Path(__file__).resolve().parent

DATA_DIR = ML_DIR / "data"

EXTERNAL_DIR = DATA_DIR / "external"

EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# DOWNLOADS FOLDER
# ------------------------------------------------------------

DOWNLOADS = Path.home() / "Downloads"

print("\nDownloads:")
print(DOWNLOADS)

print("\nML project:")
print(ML_DIR)

print("\nExternal datasets:")
print(EXTERNAL_DIR)


# ------------------------------------------------------------
# EXACT DATASET NAMES
# ------------------------------------------------------------

DATASETS = {

    "rainfall": {
        "file": "CWC_Rainfall_India_2021_2025.zip",
        "folder": "rainfall"
    },

    "hydrorivers": {
        "file": "HydroRIVERS_v10_as.gdb.zip",
        "folder": "hydrorivers"
    },

    "river_discharge": {
        "file": "river_discharge.zip",
        "folder": "river_discharge"
    },

    "esa_worldcover": {
        "file": "india_flood_project.zip",
        "folder": "esa_worldcover"
    },

    "sen5": {
        "file": "sen5.zip",
        "folder": "sen5"
    }
}


# ------------------------------------------------------------
# EXTRACT FUNCTION
# ------------------------------------------------------------

def extract_zip(zip_file, destination):

    print("\n" + "=" * 70)
    print("EXTRACTING")
    print("=" * 70)

    print("\nZIP:")
    print(zip_file)

    print("\nDESTINATION:")
    print(destination)

    destination.mkdir(
        parents=True,
        exist_ok=True
    )

    try:

        with zipfile.ZipFile(zip_file, "r") as zip_ref:

            files = zip_ref.infolist()

            total = len(files)

            print(f"\nFiles inside ZIP: {total}")

            for i, file in enumerate(files, start=1):

                zip_ref.extract(
                    file,
                    destination
                )

                if i % 100 == 0 or i == total:

                    print(
                        f"Extracted {i}/{total}",
                        end="\r"
                    )

        print("\n\nExtraction completed successfully.")

        return True

    except zipfile.BadZipFile:

        print("\nERROR: ZIP file is corrupted.")

        return False

    except Exception as e:

        print(f"\nERROR: {e}")

        return False


# ------------------------------------------------------------
# PROCESS ONE DATASET
# ------------------------------------------------------------

def process_dataset(name, information):

    zip_name = information["file"]

    folder_name = information["folder"]

    zip_path = DOWNLOADS / zip_name

    destination = EXTERNAL_DIR / folder_name

    print("\n\n")
    print("#" * 70)
    print(f"# {name.upper()}")
    print("#" * 70)

    print("\nLooking for:")
    print(zip_path)

    # --------------------------------------------------------
    # Check ZIP
    # --------------------------------------------------------

    if not zip_path.exists():

        print("\n✗ ZIP FILE NOT FOUND")

        print("\nPlease check:")
        print(zip_path)

        return False


    print("\n✓ ZIP FILE FOUND")


    # --------------------------------------------------------
    # Check whether already extracted
    # --------------------------------------------------------

    if destination.exists():

        existing_files = list(
            destination.rglob("*")
        )

        if len(existing_files) > 0:

            print("\n⚠ Dataset folder already contains files:")

            print(destination)

            answer = input(
                "\nExtract again? (y/n): "
            ).strip().lower()

            if answer != "y":

                print("Skipping dataset.")

                return True


    # --------------------------------------------------------
    # Extract
    # --------------------------------------------------------

    return extract_zip(
        zip_path,
        destination
    )


# ------------------------------------------------------------
# PROCESS ALL DATASETS
# ------------------------------------------------------------

results = {}

for name, information in DATASETS.items():

    results[name] = process_dataset(
        name,
        information
    )


# ------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------

print("\n\n")
print("=" * 70)
print("DATASET SETUP SUMMARY")
print("=" * 70)

for name, status in results.items():

    if status:

        print(
            f"✓ {name:20} SUCCESS"
        )

    else:

        print(
            f"✗ {name:20} FAILED"
        )


# ------------------------------------------------------------
# FILE COUNTS
# ------------------------------------------------------------

print("\n")
print("=" * 70)
print("EXTRACTED DATASET FILE COUNTS")
print("=" * 70)

for name, information in DATASETS.items():

    folder = (
        EXTERNAL_DIR /
        information["folder"]
    )

    if folder.exists():

        count = sum(
            1
            for p in folder.rglob("*")
            if p.is_file()
        )

        print(
            f"{information['folder']:20} : {count} files"
        )


# ------------------------------------------------------------
# FINAL LOCATIONS
# ------------------------------------------------------------

print("\n")
print("=" * 70)
print("FINAL DATASET LOCATIONS")
print("=" * 70)

for name, information in DATASETS.items():

    folder = (
        EXTERNAL_DIR /
        information["folder"]
    )

    print(f"\n{name}:")
    print(folder)


print("\n")
print("=" * 70)
print("SETUP COMPLETE")
print("=" * 70)

print("\nYour datasets are now inside:")

print(EXTERNAL_DIR)

print("\nYou can see them directly in VS Code Explorer.")

print("\nDone!")