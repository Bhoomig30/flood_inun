from pathlib import Path
import pandas as pd


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

RAINFALL_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "rainfall"
    / "CWC_Rainfall_India_2021_2025"
)

STATE_DIR = RAINFALL_DIR / "state_wise"


# ============================================================
# START
# ============================================================

print("=" * 80)
print("CWC RAINFALL DATASET CHECK")
print("=" * 80)

print("\nDataset directory:")
print(RAINFALL_DIR)

print("\nState-wise directory:")
print(STATE_DIR)


# ============================================================
# CHECK DIRECTORIES
# ============================================================

if not RAINFALL_DIR.exists():

    print("\n❌ CWC rainfall directory not found.")

    raise SystemExit(1)


if not STATE_DIR.exists():

    print("\n❌ state_wise directory not found.")

    print("\nAvailable folders/files:")

    for item in RAINFALL_DIR.iterdir():
        print(" ", item)

    raise SystemExit(1)


print("\n✓ CWC rainfall directory found.")
print("✓ state_wise directory found.")


# ============================================================
# FIND STATE CSV FILES
# ============================================================

csv_files = sorted(
    STATE_DIR.glob("*.csv")
)

print("\n")
print("=" * 80)
print("STATE-WISE RAINFALL FILES")
print("=" * 80)

print(
    f"\nCSV files found: {len(csv_files)}"
)

for i, file in enumerate(
    csv_files,
    start=1
):

    print(
        f"{i:2}. {file.name}"
    )


# ============================================================
# CHECK EXPECTED COLUMNS
# ============================================================

required_columns = [
    "Latitude",
    "Longitude",
    "Data Acquisition Time",
    "Telemetry Hourly Rainfall (mm)"
]


# ============================================================
# INSPECT ONE SAMPLE
# ============================================================

if not csv_files:

    print("\n❌ No state CSV files found.")

    raise SystemExit(1)


sample_file = next(
    (
        f
        for f in csv_files
        if f.name.lower()
        == "assam_2021_2025.csv"
    ),
    csv_files[0]
)


print("\n")
print("=" * 80)
print("SAMPLE FILE")
print("=" * 80)

print(
    f"\nUsing:"
)

print(sample_file)


try:

    df = pd.read_csv(
        sample_file,
        nrows=10,
        low_memory=False
    )

except Exception as error:

    print("\n❌ Could not read sample CSV.")

    print(error)

    raise SystemExit(1)


# ============================================================
# COLUMNS
# ============================================================

print("\n")
print("=" * 80)
print("COLUMNS")
print("=" * 80)

for column in df.columns:

    print(
        f"  - {column}"
    )


# ============================================================
# REQUIRED COLUMNS
# ============================================================

print("\n")
print("=" * 80)
print("REQUIRED COLUMN CHECK")
print("=" * 80)

missing = [
    column
    for column in required_columns
    if column not in df.columns
]


if missing:

    print(
        "\n❌ Missing required columns:"
    )

    for column in missing:

        print(
            " ",
            column
        )

else:

    print(
        "\n✓ All required rainfall columns found."
    )


# ============================================================
# SAMPLE DATA
# ============================================================

print("\n")
print("=" * 80)
print("FIRST 5 RECORDS")
print("=" * 80)

print(
    df.head().to_string(
        index=False
    )
)


# ============================================================
# DATA TYPES
# ============================================================

print("\n")
print("=" * 80)
print("DATA TYPES")
print("=" * 80)

print(
    df.dtypes
)


# ============================================================
# BASIC VALIDATION
# ============================================================

print("\n")
print("=" * 80)
print("BASIC VALIDATION")
print("=" * 80)

print(
    "\nLatitude range:"
)

print(
    df["Latitude"].min(),
    "to",
    df["Latitude"].max()
)

print(
    "\nLongitude range:"
)

print(
    df["Longitude"].min(),
    "to",
    df["Longitude"].max()
)

print(
    "\nRainfall range:"
)

print(
    df[
        "Telemetry Hourly Rainfall (mm)"
    ].min(),

    "to",

    df[
        "Telemetry Hourly Rainfall (mm)"
    ].max(),

    "mm"
)


# ============================================================
# DATE CHECK
# ============================================================

df[
    "Data Acquisition Time"
] = pd.to_datetime(
    df[
        "Data Acquisition Time"
    ],
    dayfirst=True,
    errors="coerce"
)


print(
    "\nDate range in sample:"
)

print(
    df[
        "Data Acquisition Time"
    ].min(),

    "to",

    df[
        "Data Acquisition Time"
    ].max()
)


# ============================================================
# FINAL
# ============================================================

print("\n")
print("=" * 80)
print("CWC RAINFALL CHECK COMPLETE")
print("=" * 80)

print(
    "\n✓ Dataset is extracted."
)

print(
    "✓ State-wise CSV files detected."
)

print(
    "✓ Rainfall station coordinates detected."
)

print(
    "✓ Rainfall timestamps detected."
)

print(
    "✓ Hourly rainfall values detected."
)

print(
    "\nNext step:"
)

print(
    "Match CWC rainfall observations with "
    "the Sentinel-1 flood scenes."
)