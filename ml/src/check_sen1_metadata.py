from pathlib import Path
import json


# ============================================================
# PATH
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

METADATA_FILE = (
    ML_DIR
    / "data"
    / "sen1_metadata"
    / "Sen1Floods11_Metadata.geojson"
)


# ============================================================
# CHECK FILE
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 METADATA CHECK")
print("=" * 80)

print("\nMetadata file:")
print(METADATA_FILE)


if not METADATA_FILE.exists():

    print("\n❌ Metadata file not found.")

    raise SystemExit(1)


print("\n✓ Metadata file found.")


# ============================================================
# LOAD GEOJSON
# ============================================================

with open(
    METADATA_FILE,
    "r",
    encoding="utf-8"
) as f:

    data = json.load(f)


# ============================================================
# BASIC STRUCTURE
# ============================================================

print("\n")
print("=" * 80)
print("GEOJSON STRUCTURE")
print("=" * 80)

print(
    "\nType:"
)

print(
    data.get("type")
)

print(
    "\nTop-level keys:"
)

for key in data.keys():

    print(
        " ",
        key
    )


# ============================================================
# FEATURES
# ============================================================

features = data.get(
    "features",
    []
)

print(
    "\nNumber of features:"
)

print(
    len(features)
)


if not features:

    print(
        "\n❌ No features found."
    )

    raise SystemExit(1)


# ============================================================
# FIRST FEATURE
# ============================================================

first = features[0]

print("\n")
print("=" * 80)
print("FIRST FEATURE")
print("=" * 80)

print(
    "\nFeature keys:"
)

for key in first.keys():

    print(
        " ",
        key
    )


# ============================================================
# PROPERTIES
# ============================================================

properties = first.get(
    "properties",
    {}
)

print("\n")
print("=" * 80)
print("PROPERTY FIELDS")
print("=" * 80)

if properties:

    for key, value in properties.items():

        print(
            f"{key}: {value}"
        )

else:

    print(
        "No properties found."
    )


# ============================================================
# GEOMETRY
# ============================================================

geometry = first.get(
    "geometry"
)

print("\n")
print("=" * 80)
print("GEOMETRY")
print("=" * 80)

if geometry:

    print(
        "Type:",
        geometry.get("type")
    )

    coordinates = geometry.get(
        "coordinates"
    )

    print(
        "Coordinates:",
        coordinates
    )

else:

    print(
        "No geometry found."
    )


# ============================================================
# SAMPLE FEATURES
# ============================================================

print("\n")
print("=" * 80)
print("FIRST 5 FEATURES")
print("=" * 80)

for i, feature in enumerate(
    features[:5],
    start=1
):

    print(
        f"\nFeature {i}:"
    )

    print(
        feature.get(
            "properties",
            {}
        )
    )


# ============================================================
# FINISH
# ============================================================

print("\n")
print("=" * 80)
print("METADATA CHECK COMPLETE")
print("=" * 80)