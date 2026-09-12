from pathlib import Path
import rasterio
import geopandas as gpd

# ============================================================
# EXTERNAL DATASET INSPECTOR
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]
EXTERNAL_DIR = ML_DIR / "data" / "external"

print("=" * 80)
print("FLOOD INUNDATION PROJECT - EXTERNAL DATASET INSPECTION")
print("=" * 80)

print("\nExternal dataset directory:")
print(EXTERNAL_DIR)


# ============================================================
# 1. LIST ALL FILES
# ============================================================

print("\n")
print("=" * 80)
print("1. DATASET FILE INVENTORY")
print("=" * 80)

for dataset_dir in sorted(EXTERNAL_DIR.iterdir()):

    if not dataset_dir.is_dir():
        continue

    print("\n" + "-" * 70)
    print(f"DATASET: {dataset_dir.name}")
    print("-" * 70)

    files = [
        p for p in dataset_dir.rglob("*")
        if p.is_file()
    ]

    print(f"Total files: {len(files)}")

    extensions = {}

    for file in files:

        ext = file.suffix.lower()

        if ext == "":
            ext = "[no extension]"

        extensions[ext] = extensions.get(ext, 0) + 1

    print("\nFile types:")

    for ext, count in sorted(extensions.items()):

        print(f"  {ext:15} : {count}")


# ============================================================
# 2. INSPECT RASTER FILES
# ============================================================

print("\n")
print("=" * 80)
print("2. RASTER DATASET INSPECTION")
print("=" * 80)

raster_extensions = {
    ".tif",
    ".tiff",
    ".img",
    ".vrt"
}

raster_count = 0

for dataset_dir in sorted(EXTERNAL_DIR.iterdir()):

    if not dataset_dir.is_dir():
        continue

    for file in dataset_dir.rglob("*"):

        if not file.is_file():
            continue

        if file.suffix.lower() not in raster_extensions:
            continue

        raster_count += 1

        print("\n" + "-" * 70)
        print(f"Dataset : {dataset_dir.name}")
        print(f"File    : {file.name}")
        print(f"Path    : {file}")

        try:

            with rasterio.open(file) as src:

                print(f"Width   : {src.width}")
                print(f"Height  : {src.height}")
                print(f"Bands   : {src.count}")
                print(f"CRS     : {src.crs}")
                print(f"Data type: {src.dtypes}")

                print(
                    f"Resolution: "
                    f"{src.res}"
                )

                print(
                    f"Bounds  : "
                    f"{src.bounds}"
                )

        except Exception as e:

            print(f"Could not read raster: {e}")


if raster_count == 0:

    print("\nNo raster files found.")


# ============================================================
# 3. INSPECT VECTOR DATA
# ============================================================

print("\n")
print("=" * 80)
print("3. VECTOR DATASET INSPECTION")
print("=" * 80)

vector_extensions = {
    ".shp",
    ".geojson",
    ".gpkg"
}

vector_count = 0

for dataset_dir in sorted(EXTERNAL_DIR.iterdir()):

    if not dataset_dir.is_dir():
        continue

    for file in dataset_dir.rglob("*"):

        if not file.is_file():
            continue

        if file.suffix.lower() not in vector_extensions:
            continue

        vector_count += 1

        print("\n" + "-" * 70)
        print(f"Dataset : {dataset_dir.name}")
        print(f"File    : {file.name}")

        try:

            gdf = gpd.read_file(file)

            print(f"Rows    : {len(gdf)}")
            print(f"Columns : {len(gdf.columns)}")

            print(f"CRS     : {gdf.crs}")

            print("\nColumns:")

            for column in gdf.columns:

                print(
                    f"  - {column}"
                )

        except Exception as e:

            print(
                f"Could not read vector file: {e}"
            )


# ============================================================
# 4. INSPECT GEODATABASES
# ============================================================

print("\n")
print("=" * 80)
print("4. GEODATABASE INSPECTION")
print("=" * 80)

gdb_directories = list(
    EXTERNAL_DIR.rglob("*.gdb")
)

if len(gdb_directories) == 0:

    print("\nNo .gdb directory found.")

else:

    for gdb in gdb_directories:

        print("\n" + "-" * 70)
        print(f"Geodatabase: {gdb}")
        print("-" * 70)

        try:

            layers = gpd.list_layers(gdb)

            print("\nLayers:")

            for layer in layers:

                print(
                    f"  {layer[0]:40} "
                    f"{layer[1]}"
                )

        except Exception as e:

            print(
                f"Could not inspect GDB: {e}"
            )


# ============================================================
# 5. INSPECT CSV / TXT FILES
# ============================================================

print("\n")
print("=" * 80)
print("5. TABULAR DATASET INSPECTION")
print("=" * 80)

tabular_extensions = {
    ".csv",
    ".txt",
    ".tsv"
}

for dataset_dir in sorted(EXTERNAL_DIR.iterdir()):

    if not dataset_dir.is_dir():
        continue

    for file in dataset_dir.rglob("*"):

        if not file.is_file():
            continue

        if file.suffix.lower() not in tabular_extensions:
            continue

        print("\n" + "-" * 70)
        print(f"Dataset : {dataset_dir.name}")
        print(f"File    : {file.name}")
        print(f"Size    : {file.stat().st_size / 1024:.2f} KB")

        try:

            with open(
                file,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                lines = []

                for _ in range(5):

                    line = f.readline()

                    if not line:
                        break

                    lines.append(
                        line.strip()
                    )

            print("\nFirst lines:")

            for line in lines:

                print(
                    "  " + line[:200]
                )

        except Exception as e:

            print(
                f"Could not read file: {e}"
            )


# ============================================================
# COMPLETE
# ============================================================

print("\n")
print("=" * 80)
print("INSPECTION COMPLETE")
print("=" * 80)

print(
    "\nNext step: use these results to align "
    "rainfall, river, DEM, WorldCover and satellite data."
)