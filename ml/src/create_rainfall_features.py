from pathlib import Path
from datetime import timedelta
import pandas as pd
import numpy as np
import rasterio


# ============================================================
# CONFIGURATION
# ============================================================

DRY_RUN = True

# Maximum distance between Sentinel scene center
# and CWC rainfall station
MAX_DISTANCE_KM = 50

# Rainfall time window around Sentinel-1 acquisition date
DATE_WINDOW_DAYS = 3


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]

IMAGE_DIR = (
    ML_DIR
    / "data"
    / "images"
)

RAINFALL_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "rainfall"
    / "CWC_Rainfall_India_2021_2025"
    / "state_wise"
)

OUTPUT_DIR = (
    ML_DIR
    / "data"
    / "rainfall_features"
)


# ============================================================
# START
# ============================================================

print("=" * 80)
print("SEN1FLOODS11 → CWC RAINFALL FEATURE PREPARATION")
print("=" * 80)

print("\nImage directory:")
print(IMAGE_DIR)

print("\nRainfall directory:")
print(RAINFALL_DIR)

print("\nOutput directory:")
print(OUTPUT_DIR)

print("\nDRY RUN:", DRY_RUN)


# ============================================================
# CHECK DIRECTORIES
# ============================================================

if not IMAGE_DIR.exists():

    print("\n❌ Image directory not found.")
    raise SystemExit


if not RAINFALL_DIR.exists():

    print("\n❌ Rainfall directory not found.")
    raise SystemExit


# ============================================================
# FIND SENTINEL SCENES
# ============================================================

images = sorted(
    IMAGE_DIR.glob("*_image.tif")
)

print(
    f"\nSatellite scenes: {len(images)}"
)


# ============================================================
# FIND RAINFALL FILES
# ============================================================

rainfall_files = sorted(
    RAINFALL_DIR.glob("*.csv")
)

print(
    f"Rainfall state files: {len(rainfall_files)}"
)


if len(rainfall_files) == 0:

    print(
        "\n❌ No rainfall CSV files found."
    )

    raise SystemExit


# ============================================================
# LOAD RAINFALL DATA
# ============================================================

print("\nLoading CWC rainfall data...")

rainfall_frames = []

required_columns = {
    "Station",
    "State",
    "District",
    "Latitude",
    "Longitude",
    "Data Acquisition Time",
    "Telemetry Hourly Rainfall (mm)"
}


for index, file in enumerate(
    rainfall_files,
    start=1
):

    print(
        f"  [{index}/{len(rainfall_files)}] "
        f"{file.name}"
    )

    try:

        df = pd.read_csv(
            file
        )

    except Exception as error:

        print(
            f"    ❌ Could not read: {error}"
        )

        continue


    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:

        print(
            "    ⚠ Missing columns:",
            missing
        )

        continue


    # Keep only required columns
    df = df[
        list(required_columns)
    ].copy()


    rainfall_frames.append(
        df
    )


if not rainfall_frames:

    print(
        "\n❌ No usable rainfall files."
    )

    raise SystemExit


rainfall = pd.concat(
    rainfall_frames,
    ignore_index=True
)


# ============================================================
# CLEAN RAINFALL DATA
# ============================================================

print("\nCleaning rainfall data...")


rainfall[
    "Data Acquisition Time"
] = pd.to_datetime(
    rainfall["Data Acquisition Time"],
    format="%d-%m-%Y %H:%M",
    errors="coerce"
)


rainfall[
    "Telemetry Hourly Rainfall (mm)"
] = pd.to_numeric(
    rainfall[
        "Telemetry Hourly Rainfall (mm)"
    ],
    errors="coerce"
)


rainfall["Latitude"] = pd.to_numeric(
    rainfall["Latitude"],
    errors="coerce"
)


rainfall["Longitude"] = pd.to_numeric(
    rainfall["Longitude"],
    errors="coerce"
)


rainfall = rainfall.dropna(
    subset=[
        "Data Acquisition Time",
        "Latitude",
        "Longitude",
        "Telemetry Hourly Rainfall (mm)"
    ]
).copy()


print(
    "Usable rainfall observations:",
    len(rainfall)
)


print(
    "Rainfall date range:",
    rainfall["Data Acquisition Time"].min(),
    "to",
    rainfall["Data Acquisition Time"].max()
)


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)

    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        +
        np.cos(lat1)
        * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return (
        6371.0
        * 2
        * np.arcsin(
            np.sqrt(a)
        )
    )


# ============================================================
# SCENE CENTER
# ============================================================

def get_scene_center(
    image_path
):

    with rasterio.open(
        image_path
    ) as src:

        bounds = src.bounds

        center_lon = (
            bounds.left
            + bounds.right
        ) / 2

        center_lat = (
            bounds.bottom
            + bounds.top
        ) / 2

    return (
        center_lat,
        center_lon
    )


# ============================================================
# MATCH ONE SCENE
# ============================================================

def match_rainfall(
    scene_date,
    scene_lat,
    scene_lon
):

    start_date = (
        scene_date
        - timedelta(
            days=DATE_WINDOW_DAYS
        )
    )

    end_date = (
        scene_date
        + timedelta(
            days=DATE_WINDOW_DAYS
        )
    )


    # --------------------------------------------------------
    # Temporal filter
    # --------------------------------------------------------

    candidates = rainfall[
        (
            rainfall[
                "Data Acquisition Time"
            ] >= start_date
        )
        &
        (
            rainfall[
                "Data Acquisition Time"
            ] <= end_date
        )
    ].copy()


    if candidates.empty:

        return None


    # --------------------------------------------------------
    # Spatial distance
    # --------------------------------------------------------

    candidates[
        "distance_km"
    ] = haversine_km(
        scene_lat,
        scene_lon,
        candidates["Latitude"].values,
        candidates["Longitude"].values
    )


    # --------------------------------------------------------
    # Spatial filter
    # --------------------------------------------------------

    candidates = candidates[
        candidates[
            "distance_km"
        ]
        <= MAX_DISTANCE_KM
    ].copy()


    if candidates.empty:

        return None


    # --------------------------------------------------------
    # Aggregate rainfall
    # --------------------------------------------------------

    # Distance-weighted rainfall.
    #
    # Closer stations receive more weight.
    #

    candidates[
        "weight"
    ] = 1.0 / (
        candidates[
            "distance_km"
        ]
        + 1.0
    )


    weighted_rainfall = (
        (
            candidates[
                "Telemetry Hourly Rainfall (mm)"
            ]
            * candidates["weight"]
        ).sum()
        /
        candidates["weight"].sum()
    )


    # --------------------------------------------------------
    # Maximum observed rainfall
    # --------------------------------------------------------

    max_rainfall = (
        candidates[
            "Telemetry Hourly Rainfall (mm)"
        ].max()
    )


    # --------------------------------------------------------
    # Mean observed rainfall
    # --------------------------------------------------------

    mean_rainfall = (
        candidates[
            "Telemetry Hourly Rainfall (mm)"
        ].mean()
    )


    # --------------------------------------------------------
    # Number of stations
    # --------------------------------------------------------

    station_count = (
        candidates[
            "Station"
        ].nunique()
    )


    # --------------------------------------------------------
    # Nearest station
    # --------------------------------------------------------

    nearest = candidates.loc[
        candidates[
            "distance_km"
        ].idxmin()
    ]


    return {
        "rainfall_weighted_mm":
            float(weighted_rainfall),

        "rainfall_mean_mm":
            float(mean_rainfall),

        "rainfall_max_mm":
            float(max_rainfall),

        "rainfall_station_count":
            int(station_count),

        "nearest_station":
            str(nearest["Station"]),

        "nearest_station_distance_km":
            float(nearest["distance_km"])
    }


# ============================================================
# PROCESS SCENES
# ============================================================

print("\n")
print("=" * 80)
print("SCENE / RAINFALL MATCHING")
print("=" * 80)


results = []

matched = 0
unmatched = 0


for index, image_path in enumerate(
    images,
    start=1
):

    scene_id = image_path.stem.replace(
        "_image",
        ""
    )


    # --------------------------------------------------------
    # Scene center
    # --------------------------------------------------------

    try:

        scene_lat, scene_lon = (
            get_scene_center(
                image_path
            )
        )

    except Exception as error:

        print(
            f"\n[{index}/{len(images)}] "
            f"{scene_id}"
        )

        print(
            "  ❌ Could not read scene:",
            error
        )

        unmatched += 1

        continue


    # --------------------------------------------------------
    # Scene date
    # --------------------------------------------------------

    # Sentinel-1 scene filenames do not contain
    # the acquisition date, so first check whether
    # metadata is available in the extracted
    # Sen1Floods11 metadata.
    #
    # For now we use the scene ID as a placeholder
    # and report that temporal matching requires
    # scene metadata.
    #

    print(
        f"\n[{index}/{len(images)}] "
        f"{scene_id}"
    )

    print(
        f"  Center: "
        f"{scene_lat:.6f}, "
        f"{scene_lon:.6f}"
    )

    print(
        "  ⚠ Scene acquisition date not yet "
        "resolved from current image filename."
    )


# ============================================================
# FINISH
# ============================================================

print("\n")
print("=" * 80)
print("RAINFALL MATCHING DRY RUN COMPLETE")
print("=" * 80)

print(
    "\nSatellite scenes:",
    len(images)
)

print(
    "Rainfall observations:",
    len(rainfall)
)

print(
    "\nIMPORTANT:"
)

print(
    "The CWC rainfall data is available and valid,"
)

print(
    "but we should NOT create rainfall features yet."
)

print(
    "We first need the exact Sentinel-1 acquisition"
)

print(
    "date for each of the 446 scenes."
)

print(
    "\nThis prevents incorrect temporal matching."
)