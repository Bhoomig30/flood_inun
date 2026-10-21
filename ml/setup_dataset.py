from pathlib import Path
from zipfile import ZipFile
import shutil


# ============================================================
# 1. DOWNLOAD LOCATION
# ============================================================

DOWNLOADS = Path(r"C:\Users\Bhoomi Gupta\Downloads")


# ============================================================
# 2. AUTOMATICALLY FIND THE CORRECT PROJECT ROOT
#
# setup_dataset.py is inside:
#
# flood-inundation-main/
# └── ml/
#     └── setup_dataset.py
#
# Therefore parent.parent = flood-inundation-main
# ============================================================

PROJECT = Path(__file__).resolve().parent.parent


# ============================================================
# 3. ZIP FILES
#
# sen1.zip = images
# sen2.zip = labels
# sen3.zip = train/val/test split
# ============================================================

IMAGE_ZIP = DOWNLOADS / "sen1.zip"
LABEL_ZIP = DOWNLOADS / "sen2.zip"
SPLIT_ZIP = DOWNLOADS / "sen3.zip"


# ============================================================
# 4. DESTINATION FOLDERS
# ============================================================

IMAGE_DIR = PROJECT / "ml" / "data" / "images"
LABEL_DIR = PROJECT / "ml" / "data" / "labels"
SPLIT_DIR = PROJECT / "ml" / "data" / "split"


# Create folders if they don't exist
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
LABEL_DIR.mkdir(parents=True, exist_ok=True)
SPLIT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 5. EXTRACT IMAGES
# ============================================================

def extract_images():

    print("\n" + "=" * 60)
    print("EXTRACTING IMAGES")
    print("=" * 60)

    if not IMAGE_ZIP.exists():
        print(f"\nERROR: Image ZIP not found:")
        print(IMAGE_ZIP)
        return

    with ZipFile(IMAGE_ZIP, "r") as z:

        files = [
            f for f in z.namelist()
            if Path(f).name.lower().endswith("_image.tif")
        ]

        print(f"Found {len(files)} image files")

        for i, file in enumerate(files, 1):

            output = IMAGE_DIR / Path(file).name

            # Skip if already copied
            if output.exists():
                continue

            with z.open(file) as source:
                with open(output, "wb") as target:
                    shutil.copyfileobj(source, target)

            if i % 100 == 0 or i == len(files):
                print(f"Images copied: {i}/{len(files)}")


# ============================================================
# 6. EXTRACT LABELS
# ============================================================

def extract_labels():

    print("\n" + "=" * 60)
    print("EXTRACTING LABELS")
    print("=" * 60)

    if not LABEL_ZIP.exists():
        print(f"\nERROR: Label ZIP not found:")
        print(LABEL_ZIP)
        return

    with ZipFile(LABEL_ZIP, "r") as z:

        files = [
            f for f in z.namelist()
            if Path(f).name.lower().endswith("_label.tif")
        ]

        print(f"Found {len(files)} label files")

        for i, file in enumerate(files, 1):

            output = LABEL_DIR / Path(file).name

            # Skip if already copied
            if output.exists():
                continue

            with z.open(file) as source:
                with open(output, "wb") as target:
                    shutil.copyfileobj(source, target)

            if i % 100 == 0 or i == len(files):
                print(f"Labels copied: {i}/{len(files)}")


# ============================================================
# 7. EXTRACT TRAIN / VALIDATION / TEST FILES
# ============================================================

def extract_splits():

    print("\n" + "=" * 60)
    print("EXTRACTING SPLITS")
    print("=" * 60)

    if not SPLIT_ZIP.exists():
        print(f"\nERROR: Split ZIP not found:")
        print(SPLIT_ZIP)
        return

    with ZipFile(SPLIT_ZIP, "r") as z:

        wanted = {
            "train.txt",
            "val.txt",
            "test.txt"
        }

        found = set()

        for file in z.namelist():

            filename = Path(file).name

            if filename in wanted:

                output = SPLIT_DIR / filename

                with z.open(file) as source:
                    with open(output, "wb") as target:
                        shutil.copyfileobj(source, target)

                print(f"Copied: {filename}")

                found.add(filename)

        missing = wanted - found

        if missing:
            print("\nWARNING: These split files were not found:")
            for file in missing:
                print(f"  - {file}")


# ============================================================
# 8. MAIN PROGRAM
# ============================================================

print("\n")
print("=" * 60)
print("SEN1FLOODS11 DATASET SETUP")
print("=" * 60)

print("\nProject location:")
print(PROJECT)

print("\nZIP files:")
print(f"Images : {IMAGE_ZIP}")
print(f"Labels : {LABEL_ZIP}")
print(f"Splits : {SPLIT_ZIP}")


# Check ZIP files before starting
print("\nChecking ZIP files...")

if not IMAGE_ZIP.exists():
    print("\nERROR: sen1.zip was not found.")
    print("Expected location:")
    print(IMAGE_ZIP)
    raise SystemExit(1)

if not LABEL_ZIP.exists():
    print("\nERROR: sen2.zip was not found.")
    print("Expected location:")
    print(LABEL_ZIP)
    raise SystemExit(1)

if not SPLIT_ZIP.exists():
    print("\nERROR: sen3.zip was not found.")
    print("Expected location:")
    print(SPLIT_ZIP)
    raise SystemExit(1)

print("All ZIP files found.")


# Extract everything
extract_images()
extract_labels()
extract_splits()


# ============================================================
# 9. FINAL CHECK
# ============================================================

image_count = len(list(IMAGE_DIR.glob("*_image.tif")))
label_count = len(list(LABEL_DIR.glob("*_label.tif")))

train_exists = (SPLIT_DIR / "train.txt").exists()
val_exists = (SPLIT_DIR / "val.txt").exists()
test_exists = (SPLIT_DIR / "test.txt").exists()


print("\n")
print("=" * 60)
print("DATASET SETUP COMPLETE")
print("=" * 60)

print(f"\nImages : {image_count}")
print(f"Labels : {label_count}")

print("\nSplit files:")
print(f"train.txt : {'YES' if train_exists else 'NO'}")
print(f"val.txt   : {'YES' if val_exists else 'NO'}")
print(f"test.txt  : {'YES' if test_exists else 'NO'}")

print("\nImages location:")
print(IMAGE_DIR)

print("\nLabels location:")
print(LABEL_DIR)

print("\nSplit location:")
print(SPLIT_DIR)


# ============================================================
# 10. BASIC VALIDATION
# ============================================================

if image_count == label_count:
    print("\n✓ Number of images and labels match.")
else:
    print("\n⚠ WARNING: Image and label counts do NOT match.")

if train_exists and val_exists and test_exists:
    print("✓ Train/validation/test splits found.")
else:
    print("⚠ WARNING: One or more split files are missing.")

print("\nDone!")