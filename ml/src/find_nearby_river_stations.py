from pathlib import Path
import math
import pandas as pd


# ============================================================
# FIND NEARBY CWC RIVER STATIONS
# ============================================================

BASE = Path(__file__).resolve().parents[1]

RIVER_DIR = (
    BASE
    / "data"
    / "external"
    / "river_discharge"
    / "river_discharge"
)

# Naraj approximate coordinates
TARGET_LAT = 20.50
TARGET_LON = 85.95

EARTH_RADIUS_KM = 6371.0


def distance_km(lat1, lon1, lat2, lon2):
    """Haversine distance."""

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return (
        EARTH_RADIUS_KM
        * 2
        * math.asin(math.sqrt(a))
    )


print("=" * 80)
print("CWC RIVER STATIONS NEAR NARAJ")
print("=" * 80)

print()
print("Target:")
print("Latitude :", TARGET_LAT)
print("Longitude:", TARGET_LON)
print()

files = list(RIVER_DIR.glob("*.csv"))

print("River files found:", len(files))
print()

if not files:
    raise FileNotFoundError(
        f"No river CSV files found in:\n{RIVER_DIR}"
    )


rows = []


for file in files:

    print("Reading:", file.name)

    try:

        df = pd.read_csv(
            file,
            usecols=[
                "Station",
                "State",
                "District",
                "River",
                "Basin",
                "Latitude",
                "Longitude",
            ],
        )

        df["Latitude"] = pd.to_numeric(
            df["Latitude"],
            errors="coerce",
        )

        df["Longitude"] = pd.to_numeric(
            df["Longitude"],
            errors="coerce",
        )

        df = df.dropna(
            subset=[
                "Station",
                "Latitude",
                "Longitude",
            ]
        )

        # One row per station/location
        stations = (
            df.groupby(
                [
                    "Station",
                    "State",
                    "District",
                    "River",
                    "Basin",
                    "Latitude",
                    "Longitude",
                ],
                dropna=False,
            )
            .size()
            .reset_index(name="observations")
        )

        for _, row in stations.iterrows():

            dist = distance_km(
                TARGET_LAT,
                TARGET_LON,
                float(row["Latitude"]),
                float(row["Longitude"]),
            )

            rows.append(
                {
                    "distance_km": dist,
                    "station": row["Station"],
                    "state": row["State"],
                    "district": row["District"],
                    "river": row["River"],
                    "basin": row["Basin"],
                    "latitude": row["Latitude"],
                    "longitude": row["Longitude"],
                    "observations": int(
                        row["observations"]
                    ),
                }
            )

    except Exception as e:

        print(
            "WARNING:",
            file.name,
            "->",
            str(e),
        )


# ============================================================
# RESULTS
# ============================================================

result = pd.DataFrame(rows)

if result.empty:
    raise RuntimeError(
        "No river stations could be read."
    )


# Remove duplicate station/location combinations
result = result.drop_duplicates(
    subset=[
        "station",
        "latitude",
        "longitude",
    ]
)


result = result.sort_values(
    "distance_km"
)


print()
print("=" * 80)
print("30 NEAREST RIVER STATIONS")
print("=" * 80)
print()

print(
    result.head(30).to_string(
        index=False
    )
)


# ============================================================
# SAVE RESULTS
# ============================================================

output = (
    BASE
    / "data"
    / "forecast"
    / "nearby_river_stations.csv"
)

output.parent.mkdir(
    parents=True,
    exist_ok=True,
)

result.head(30).to_csv(
    output,
    index=False,
)

print()
print("=" * 80)
print("SAVED")
print("=" * 80)
print(output)