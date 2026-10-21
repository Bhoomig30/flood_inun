from pathlib import Path
import fiona
import geopandas as gpd

# ============================================================
# HYDRORIVERS CHECKER
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

GDB_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "hydrorivers"
    / "HydroRIVERS_v10_as.gdb"
)

print("=" * 80)
print("HYDRORIVERS GEODATABASE CHECK")
print("=" * 80)

print("\nGDB location:")
print(GDB_DIR)

# ------------------------------------------------------------
# CHECK PATH
# ------------------------------------------------------------

if not GDB_DIR.exists():

    print("\n❌ ERROR: Geodatabase not found.")
    print(GDB_DIR)
    raise SystemExit

print("\n✅ Geodatabase found.")


# ------------------------------------------------------------
# LIST LAYERS USING FIONA
# ------------------------------------------------------------

print("\n")
print("=" * 80)
print("AVAILABLE LAYERS")
print("=" * 80)

try:

    layers = fiona.listlayers(
        str(GDB_DIR)
    )

    print(f"\nNumber of layers: {len(layers)}")

    for i, layer in enumerate(layers):

        print(
            f"{i + 1}. {layer}"
        )

except Exception as e:

    print("\n❌ Fiona could not read the GDB.")

    print("\nError:")
    print(e)

    raise SystemExit


# ------------------------------------------------------------
# INSPECT EACH LAYER
# ------------------------------------------------------------

print("\n")
print("=" * 80)
print("LAYER DETAILS")
print("=" * 80)

for layer in layers:

    print("\n" + "-" * 80)

    print("Layer:")
    print(layer)

    try:

        gdf = gpd.read_file(
            str(GDB_DIR),
            layer=layer
        )

        print(
            "Features:",
            len(gdf)
        )

        print(
            "CRS:",
            gdf.crs
        )

        print(
            "Geometry:",
            gdf.geometry.geom_type.value_counts().to_dict()
        )

        print("\nColumns:")

        for column in gdf.columns:

            print(
                "  -",
                column
            )

        print("\nFirst 3 records:")

        print(
            gdf.head(3).to_string()
        )

    except Exception as e:

        print(
            "\n❌ Could not read layer:"
        )

        print(e)


# ------------------------------------------------------------
# COMPLETE
# ------------------------------------------------------------

print("\n")
print("=" * 80)
print("HYDRORIVERS CHECK COMPLETE")
print("=" * 80)