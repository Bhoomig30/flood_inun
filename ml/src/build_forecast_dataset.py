from pathlib import Path
import json
import math

import numpy as np
import pandas as pd


# ============================================================
# FLOODWATCH FUTURE FORECAST DATASET BUILDER
# ============================================================
#
# Builds a time-series dataset for future flood-risk prediction.
#
# Data used:
#   1. CWC rainfall stations
#   2. Naraj water level
#   3. Alipingal water level
#   4. Nimapara water level
#
# Forecast targets:
#   flood_next_6h
#   flood_next_12h
#   flood_next_24h
#
# IMPORTANT:
# This version DOES NOT depend on Sen1Floods11 scene metadata.
# ============================================================


# ============================================================
# PATHS
# ============================================================

ML_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ML_DIR / "data"

RAINFALL_DIR = (
    DATA_DIR
    / "external"
    / "rainfall"
    / "CWC_Rainfall_India_2021_2025"
    / "state_wise"
)

RIVER_DIR = (
    DATA_DIR
    / "external"
    / "river_discharge"
    / "river_discharge"
)

DASHBOARD_DATA = (
    ML_DIR.parent
    / "naraj_dashboard"
    / "data"
)

CWC_LEVEL_DIR = DASHBOARD_DATA / "cwc"

FORECAST_DIR = DATA_DIR / "forecast"
FORECAST_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = FORECAST_DIR / "forecast_dataset.csv"
STATION_FILE = FORECAST_DIR / "forecast_stations.csv"
SUMMARY_FILE = FORECAST_DIR / "forecast_dataset_summary.json"


# ============================================================
# TARGET LOCATION
# ============================================================

TARGET_LAT = 20.50
TARGET_LON = 85.95


# ============================================================
# WATER-LEVEL STATIONS
# ============================================================

WATER_LEVEL_FILES = {
    "Naraj": CWC_LEVEL_DIR / "naraj_daily_2021_2025.json",
    "Alipingal": CWC_LEVEL_DIR / "alipingal_daily_2021_2025.json",
    "Nimapara": CWC_LEVEL_DIR / "nimapara_daily_2021_2025.json",
}


# ============================================================
# RAINFALL STATION SEARCH
# ============================================================

MAX_RAIN_DISTANCE_KM = 100.0

MAX_RAIN_STATIONS = 10


# ============================================================
# TIME SETTINGS
# ============================================================

# CWC rainfall is irregular/hourly in the supplied files.
# We convert everything to hourly timestamps.

TIME_FREQ = "1h"

# Minimum amount of rainfall observations needed
# before calculating a rolling rainfall feature.
MIN_RAIN_OBS = 1


# ============================================================
# FLOOD LABEL THRESHOLD
# ============================================================
#
# We create an operational historical flood target from
# Naraj water-level behaviour.
#
# The exact threshold can later be calibrated against the
# official danger level.
#
# For now:
#   flood = unusually high water level relative to history
#
# We use a rolling quantile so the model does not depend
# on a hard-coded government danger level.
# ============================================================

FLOOD_QUANTILE = 0.95


# ============================================================
# FORECAST HORIZONS
# ============================================================

HORIZONS = [6, 12, 24]


# ============================================================
# HELPERS
# ============================================================

def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two geographic coordinates."""

    R = 6371.0

    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))

    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 2 * R * math.asin(math.sqrt(a))


def find_column(df, candidates):
    """Find the first matching column."""

    lower = {
        str(c).strip().lower(): c
        for c in df.columns
    }

    for candidate in candidates:

        key = candidate.strip().lower()

        if key in lower:
            return lower[key]

    return None


# ============================================================
# LOAD RAINFALL
# ============================================================

def load_rainfall():

    print("\n" + "=" * 80)
    print("LOADING CWC RAINFALL")
    print("=" * 80)

    files = sorted(RAINFALL_DIR.glob("*.csv"))

    print("Rainfall files:", len(files))

    if not files:
        raise RuntimeError(
            f"No rainfall CSV files found:\n{RAINFALL_DIR}"
        )

    frames = []

    for index, file in enumerate(files, 1):

        print(
            f"[{index}/{len(files)}] {file.name}"
        )

        try:

            df = pd.read_csv(
                file,
                low_memory=False
            )

            station_col = find_column(
                df,
                [
                    "Station",
                    "station"
                ]
            )

            state_col = find_column(
                df,
                [
                    "State",
                    "state"
                ]
            )

            district_col = find_column(
                df,
                [
                    "District",
                    "district"
                ]
            )

            lat_col = find_column(
                df,
                [
                    "Latitude",
                    "latitude"
                ]
            )

            lon_col = find_column(
                df,
                [
                    "Longitude",
                    "longitude"
                ]
            )

            time_col = find_column(
                df,
                [
                    "Data Acquisition Time",
                    "data acquisition time",
                    "Date",
                    "datetime",
                    "timestamp"
                ]
            )

            rainfall_col = find_column(
                df,
                [
                    "Telemetry Hourly Rainfall (mm)",
                    "rainfall_mm",
                    "Rainfall",
                    "rainfall"
                ]
            )

            required = [
                station_col,
                lat_col,
                lon_col,
                time_col,
                rainfall_col
            ]

            if any(x is None for x in required):

                print(
                    "  Skipping: required columns missing"
                )

                continue

            d = pd.DataFrame()

            d["station"] = (
                df[station_col]
                .astype(str)
                .str.strip()
            )

            d["state"] = (
                df[state_col].astype(str).str.strip()
                if state_col
                else ""
            )

            d["district"] = (
                df[district_col].astype(str).str.strip()
                if district_col
                else ""
            )

            d["lat"] = pd.to_numeric(
                df[lat_col],
                errors="coerce"
            )

            d["lon"] = pd.to_numeric(
                df[lon_col],
                errors="coerce"
            )

            d["time"] = pd.to_datetime(
                df[time_col],
                errors="coerce",
                dayfirst=True
            )

            d["rainfall_mm"] = pd.to_numeric(
                df[rainfall_col],
                errors="coerce"
            )

            d = d.dropna(
                subset=[
                    "station",
                    "lat",
                    "lon",
                    "time",
                    "rainfall_mm"
                ]
            )

            d = d[
                d["rainfall_mm"] >= 0
            ].copy()

            if len(d):
                frames.append(d)

        except Exception as e:

            print(
                "  ERROR:",
                str(e)
            )

    if not frames:
        raise RuntimeError(
            "No usable rainfall observations found."
        )

    rainfall = pd.concat(
        frames,
        ignore_index=True
    )

    rainfall = rainfall.sort_values("time")

    print(
        "\nValid rainfall observations:",
        f"{len(rainfall):,}"
    )

    print(
        "Rainfall range:",
        rainfall["time"].min(),
        "->",
        rainfall["time"].max()
    )

    return rainfall


# ============================================================
# FIND NEARBY RAINFALL STATIONS
# ============================================================

def find_nearby_rain_stations(rainfall):

    print("\n" + "=" * 80)
    print("FINDING NEARBY RAINFALL STATIONS")
    print("=" * 80)

    stations = (
        rainfall[
            [
                "station",
                "state",
                "district",
                "lat",
                "lon"
            ]
        ]
        .drop_duplicates()
        .copy()
    )

    rows = []

    for _, row in stations.iterrows():

        try:

            distance = haversine_km(
                TARGET_LAT,
                TARGET_LON,
                row["lat"],
                row["lon"]
            )

            if distance <= MAX_RAIN_DISTANCE_KM:

                rows.append(
                    {
                        "station": row["station"],
                        "state": row["state"],
                        "district": row["district"],
                        "latitude": row["lat"],
                        "longitude": row["lon"],
                        "distance_km": distance
                    }
                )

        except Exception:
            continue

    nearby = pd.DataFrame(rows)

    if nearby.empty:
        raise RuntimeError(
            "No rainfall stations found within "
            f"{MAX_RAIN_DISTANCE_KM} km."
        )

    nearby = (
        nearby
        .sort_values("distance_km")
        .drop_duplicates("station")
        .head(MAX_RAIN_STATIONS)
        .reset_index(drop=True)
    )

    print("\nSelected rainfall stations:")

    print(
        nearby.to_string(
            index=False
        )
    )

    nearby.to_csv(
        STATION_FILE,
        index=False
    )

    return nearby


# ============================================================
# BUILD RAINFALL TIME SERIES
# ============================================================

def build_rainfall_series(
    rainfall,
    station
):

    d = rainfall[
        rainfall["station"] == station
    ].copy()

    if d.empty:
        return pd.Series(
            dtype=float
        )

    d = (
        d.groupby("time")["rainfall_mm"]
        .mean()
        .sort_index()
    )

    # Remove duplicate timestamps.
    d = d[
        ~d.index.duplicated(
            keep="last"
        )
    ]

    # Hourly reindex.
    full_index = pd.date_range(
        d.index.min().floor("h"),
        d.index.max().ceil("h"),
        freq=TIME_FREQ
    )

    d = d.reindex(full_index)

    # Missing CWC observations are NOT treated as rainfall.
    # We leave them as NaN initially.
    return d


# ============================================================
# LOAD WATER LEVEL
# ============================================================

def load_water_level(
    station,
    path
):

    print(
        f"Loading water-level station: {station}"
    )

    if not path.exists():

        print(
            "  Missing:",
            path
        )

        return pd.Series(
            dtype=float
        )

    try:

        obj = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        records = obj.get(
            "records",
            []
        )

        if not records:
            return pd.Series(
                dtype=float
            )

        df = pd.DataFrame(
            records
        )

        df["time"] = pd.to_datetime(
            df["date"],
            errors="coerce"
        )

        df["water_level_m"] = pd.to_numeric(
            df["water_level_m"],
            errors="coerce"
        )

        df = df.dropna(
            subset=[
                "time",
                "water_level_m"
            ]
        )

        df = (
            df.groupby("time")[
                "water_level_m"
            ]
            .mean()
            .sort_index()
        )

        print(
            f"  Records: {len(df):,}"
        )

        print(
            "  Range:",
            df.index.min(),
            "->",
            df.index.max()
        )

        return df

    except Exception as e:

        print(
            "  ERROR:",
            e
        )

        return pd.Series(
            dtype=float
        )


# ============================================================
# BUILD COMBINED TIME SERIES
# ============================================================

def build_combined_series(
    rainfall,
    nearby_stations
):

    print("\n" + "=" * 80)
    print("BUILDING COMBINED TIME SERIES")
    print("=" * 80)

    series = []

    # --------------------------------------------------------
    # Rainfall stations
    # --------------------------------------------------------

    for i, row in nearby_stations.iterrows():

        station = row["station"]

        s = build_rainfall_series(
            rainfall,
            station
        )

        if s.empty:
            continue

        # Rename to station-specific column.
        column_name = (
            "rain_"
            + str(i + 1)
            + "_mm"
        )

        s.name = column_name

        series.append(s)

    # --------------------------------------------------------
    # Water levels
    # --------------------------------------------------------

    for station, path in WATER_LEVEL_FILES.items():

        s = load_water_level(
            station,
            path
        )

        if s.empty:
            continue

        # Daily data -> hourly forward fill.
        s = s.resample(
            TIME_FREQ
        ).mean()

        s = s.ffill()

        s.name = (
            station.lower()
            + "_water_level_m"
        )

        series.append(s)

    if not series:
        raise RuntimeError(
            "No time-series data could be built."
        )

    combined = pd.concat(
        series,
        axis=1
    ).sort_index()

    print(
        "\nCombined columns:"
    )

    for c in combined.columns:
        print(
            " ",
            c
        )

    print(
        "\nCombined range:",
        combined.index.min(),
        "->",
        combined.index.max()
    )

    return combined


# ============================================================
# FEATURE ENGINEERING
# ============================================================

def create_features(
    combined
):

    print("\n" + "=" * 80)
    print("CREATING FORECAST FEATURES")
    print("=" * 80)

    df = combined.copy()

    # --------------------------------------------------------
    # Rainfall columns
    # --------------------------------------------------------

    rainfall_columns = [
        c
        for c in df.columns
        if c.startswith("rain_")
    ]

    # Missing rainfall observations are filled with 0
    # AFTER station alignment.
    for c in rainfall_columns:

        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

        df[c] = df[c].fillna(0)

    # --------------------------------------------------------
    # Aggregate rainfall across selected stations
    # --------------------------------------------------------

    if rainfall_columns:

        df["rainfall_mean_mm"] = (
            df[rainfall_columns]
            .mean(axis=1)
        )

        df["rainfall_max_mm"] = (
            df[rainfall_columns]
            .max(axis=1)
        )

    else:

        df["rainfall_mean_mm"] = 0.0
        df["rainfall_max_mm"] = 0.0

    # --------------------------------------------------------
    # Rolling rainfall
    # --------------------------------------------------------

    for hours in [1, 3, 6, 12, 24]:

        df[
            f"rainfall_{hours}h"
        ] = (
            df["rainfall_mean_mm"]
            .rolling(
                hours,
                min_periods=MIN_RAIN_OBS
            )
            .sum()
        )

    df[
        "rainfall_intensity_3h"
    ] = (
        df["rainfall_3h"] / 3.0
    )

    df[
        "rainfall_intensity_24h"
    ] = (
        df["rainfall_24h"] / 24.0
    )

    # --------------------------------------------------------
    # Water-level features
    # --------------------------------------------------------

    level_columns = [
        c
        for c in df.columns
        if c.endswith(
            "_water_level_m"
        )
    ]

    for c in level_columns:

        df[c] = pd.to_numeric(
            df[c],
            errors="coerce"
        )

        # Forward fill small gaps.
        df[c] = df[c].ffill()

        # Lag values.
        for lag in [1, 3, 6, 12, 24]:

            df[
                f"{c}_lag_{lag}h"
            ] = df[c].shift(lag)

        # Trends.
        df[
            f"{c}_change_3h"
        ] = (
            df[c]
            - df[c].shift(3)
        )

        df[
            f"{c}_change_6h"
        ] = (
            df[c]
            - df[c].shift(6)
        )

        df[
            f"{c}_change_12h"
        ] = (
            df[c]
            - df[c].shift(12)
        )

        df[
            f"{c}_change_24h"
        ] = (
            df[c]
            - df[c].shift(24)
        )

        # Rolling means.
        for hours in [3, 6, 12, 24]:

            df[
                f"{c}_rolling_{hours}h"
            ] = (
                df[c]
                .rolling(
                    hours,
                    min_periods=1
                )
                .mean()
            )

    # --------------------------------------------------------
    # Combined regional water level
    # --------------------------------------------------------

    if level_columns:

        df[
            "regional_water_level_m"
        ] = (
            df[level_columns]
            .mean(axis=1)
        )

        df[
            "regional_water_level_change_6h"
        ] = (
            df["regional_water_level_m"]
            - df[
                "regional_water_level_m"
            ].shift(6)
        )

        df[
            "regional_water_level_change_24h"
        ] = (
            df["regional_water_level_m"]
            - df[
                "regional_water_level_m"
            ].shift(24)
        )

    # --------------------------------------------------------
    # Calendar features
    # --------------------------------------------------------

    df["hour"] = df.index.hour

    df["day_of_year"] = (
        df.index.dayofyear
    )

    df["month"] = (
        df.index.month
    )

    # Cyclic encoding.
    df["hour_sin"] = np.sin(
        2 * np.pi * df["hour"] / 24
    )

    df["hour_cos"] = np.cos(
        2 * np.pi * df["hour"] / 24
    )

    df["month_sin"] = np.sin(
        2 * np.pi * df["month"] / 12
    )

    df["month_cos"] = np.cos(
        2 * np.pi * df["month"] / 12
    )

    return df


# ============================================================
# CREATE HISTORICAL FLOOD TARGET
# ============================================================

def create_flood_target(df):

    print("\n" + "=" * 80)
    print("CREATING HISTORICAL FLOOD TARGET")
    print("=" * 80)

    target_column = (
        "naraj_water_level_m"
    )

    if target_column not in df.columns:

        raise RuntimeError(
            "Naraj water-level series was not found."
        )

    # --------------------------------------------------------
    # Historical threshold
    # --------------------------------------------------------

    valid_levels = (
        df[target_column]
        .dropna()
    )

    if valid_levels.empty:

        raise RuntimeError(
            "Naraj water-level data contains no valid values."
        )

    threshold = float(
        valid_levels.quantile(
            FLOOD_QUANTILE
        )
    )

    print(
        f"Naraj {FLOOD_QUANTILE * 100:.0f}th "
        f"percentile threshold:",
        threshold,
        "m"
    )

    df[
        "historical_flood"
    ] = (
        df[target_column]
        >= threshold
    ).astype(int)

    print(
        "Historical flood-positive hours:",
        int(
            df[
                "historical_flood"
            ].sum()
        )
    )

    return df, threshold


# ============================================================
# CREATE FUTURE TARGETS
# ============================================================

def create_future_targets(df):

    print("\n" + "=" * 80)
    print("CREATING 6H / 12H / 24H FUTURE TARGETS")
    print("=" * 80)

    for horizon in HORIZONS:

        # Any flood-positive observation inside
        # the future horizon becomes a positive label.

        future_columns = []

        for step in range(
            1,
            horizon + 1
        ):

            future_columns.append(
                df[
                    "historical_flood"
                ].shift(-step)
            )

        future_matrix = pd.concat(
            future_columns,
            axis=1
        )

        target_name = (
            f"flood_next_{horizon}h"
        )

        df[target_name] = (
            future_matrix
            .max(axis=1)
            .astype("float")
        )

        positives = (
            df[target_name] == 1
        ).sum()

        print(
            f"{target_name}:",
            int(positives),
            "positive samples"
        )

    return df


# ============================================================
# BUILD MODEL DATASET
# ============================================================

def prepare_dataset(df):

    print("\n" + "=" * 80)
    print("PREPARING FINAL DATASET")
    print("=" * 80)

    target_columns = [
        f"flood_next_{h}h"
        for h in HORIZONS
    ]

    # Remove rows that don't have future labels.
    df = df.dropna(
        subset=target_columns
    ).copy()

    # --------------------------------------------------------
    # Replace infinite values.
    # --------------------------------------------------------

    df = df.replace(
        [np.inf, -np.inf],
        np.nan
    )

    # --------------------------------------------------------
    # Feature columns.
    # --------------------------------------------------------

    excluded = set(
        target_columns
        + [
            "historical_flood"
        ]
    )

    feature_columns = [
        c
        for c in df.columns
        if c not in excluded
    ]

    # --------------------------------------------------------
    # Numeric conversion.
    # --------------------------------------------------------

    for c in feature_columns:

        if not pd.api.types.is_numeric_dtype(
            df[c]
        ):

            df[c] = pd.to_numeric(
                df[c],
                errors="coerce"
            )

    # --------------------------------------------------------
    # Keep useful rows.
    # --------------------------------------------------------

    df = df.dropna(
        subset=feature_columns,
        how="all"
    )

    # Fill remaining feature gaps
    # using time-aware forward/backward fill.
    df[feature_columns] = (
        df[feature_columns]
        .ffill()
        .bfill()
    )

    # --------------------------------------------------------
    # Add timestamp as explicit column.
    # --------------------------------------------------------

    df.insert(
        0,
        "timestamp",
        df.index
    )

    # --------------------------------------------------------
    # Target integer type.
    # --------------------------------------------------------

    for c in target_columns:

        df[c] = (
            df[c]
            .astype(int)
        )

    return (
        df,
        feature_columns,
        target_columns
    )


# ============================================================
# SAVE DATASET
# ============================================================

def save_outputs(
    df,
    feature_columns,
    target_columns,
    flood_threshold
):

    print("\n" + "=" * 80)
    print("SAVING FORECAST DATASET")
    print("=" * 80)

    # --------------------------------------------------------
    # CSV
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False
    )

    print(
        "Dataset:",
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    metadata = {
        "project": "FloodWatch",
        "dataset_type": "future_flood_forecasting",
        "target_location": {
            "latitude": TARGET_LAT,
            "longitude": TARGET_LON
        },
        "rainfall_station_count": int(
            len(
                [
                    c
                    for c in df.columns
                    if c.startswith("rain_")
                ]
            )
        ),
        "water_level_stations": [
            s
            for s in WATER_LEVEL_FILES
            if (
                s.lower()
                + "_water_level_m"
            ) in df.columns
        ],
        "features": feature_columns,
        "targets": target_columns,
        "forecast_horizons_hours": HORIZONS,
        "flood_definition": {
            "method": "Naraj water-level historical percentile",
            "quantile": FLOOD_QUANTILE,
            "threshold_m": flood_threshold
        },
        "warning": (
            "Targets are historical statistical flood-risk "
            "labels for research/model development. "
            "They are not official government flood warnings."
        )
    }

    SUMMARY_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
            default=str
        ),
        encoding="utf-8"
    )

    print(
        "Metadata:",
        SUMMARY_FILE
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 80)
    print("FLOODWATCH FUTURE FORECAST DATASET")
    print("=" * 80)

    print(
        "\nTarget:",
        TARGET_LAT,
        TARGET_LON
    )

    # --------------------------------------------------------
    # Check directories.
    # --------------------------------------------------------

    for path in [
        RAINFALL_DIR,
        CWC_LEVEL_DIR
    ]:

        if not path.exists():

            raise FileNotFoundError(
                f"Required directory not found:\n{path}"
            )

    # --------------------------------------------------------
    # Load rainfall.
    # --------------------------------------------------------

    rainfall = load_rainfall()

    # --------------------------------------------------------
    # Find nearby stations.
    # --------------------------------------------------------

    nearby_stations = (
        find_nearby_rain_stations(
            rainfall
        )
    )

    # --------------------------------------------------------
    # Build combined time series.
    # --------------------------------------------------------

    combined = build_combined_series(
        rainfall,
        nearby_stations
    )

    # --------------------------------------------------------
    # Feature engineering.
    # --------------------------------------------------------

    features = create_features(
        combined
    )

    # --------------------------------------------------------
    # Historical flood target.
    # --------------------------------------------------------

    features, threshold = (
        create_flood_target(
            features
        )
    )

    # --------------------------------------------------------
    # Future targets.
    # --------------------------------------------------------

    features = create_future_targets(
        features
    )

    # --------------------------------------------------------
    # Final dataset.
    # --------------------------------------------------------

    dataset, feature_columns, target_columns = (
        prepare_dataset(
            features
        )
    )

    # --------------------------------------------------------
    # Save.
    # --------------------------------------------------------

    save_outputs(
        dataset,
        feature_columns,
        target_columns,
        threshold
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    print("\n" + "=" * 80)
    print("DATASET COMPLETE")
    print("=" * 80)

    print(
        "Rows:",
        f"{len(dataset):,}"
    )

    print(
        "Columns:",
        len(dataset.columns)
    )

    print(
        "Features:",
        len(feature_columns)
    )

    print(
        "Targets:",
        ", ".join(target_columns)
    )

    print(
        "\nTarget distribution:"
    )

    for target in target_columns:

        counts = (
            dataset[target]
            .value_counts()
            .sort_index()
            .to_dict()
        )

        print(
            f"  {target}:",
            counts
        )

    print(
        "\nOutput:"
    )

    print(
        OUTPUT_FILE
    )

    print("\nREADY FOR MODEL TRAINING.")


if __name__ == "__main__":
    main()