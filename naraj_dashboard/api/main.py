from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from math import radians, sin, cos, sqrt, atan2, isfinite
import csv
import json


# ============================================================
# FLOODWATCH / NARAJ FLOOD INTELLIGENCE API
# ============================================================

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = DASHBOARD_DIR.parent
ML_DIR = PROJECT_DIR / "ml"


# ============================================================
# CONFIGURATION
# ============================================================

HOST = "127.0.0.1"
PORT = 8000

EARTH_RADIUS_KM = 6371.0

RAINFALL_MAX_DISTANCE_KM = 250.0
RIVER_MAX_DISTANCE_KM = 250.0


# ============================================================
# DATA DIRECTORIES
# ============================================================

RAINFALL_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "rainfall"
    / "CWC_Rainfall_India_2021_2025"
    / "state_wise"
)

RIVER_DIR = (
    ML_DIR
    / "data"
    / "external"
    / "river_discharge"
    / "river_discharge"
)


# ============================================================
# ML FORECAST FILE
# ============================================================

FORECAST_FILE = (
    ML_DIR
    / "data"
    / "forecast"
    / "latest_forecast.json"
)


# ============================================================
# CWC COLUMN NAMES
# ============================================================

RAINFALL_VALUE_COLUMN = (
    "Telemetry Hourly Rainfall (mm)"
)

RIVER_VALUE_COLUMN = (
    "Telemetry Hourly River Water Discharge (m3/sec)"
)


# ============================================================
# UTILITY: CLEAN NUMBER
# ============================================================

def clean_number(value):

    try:

        if value is None:
            return None

        text = str(value).strip()

        if text == "":
            return None

        if text.lower() in {
            "nan",
            "none",
            "null",
            "na",
            "n/a",
            "-"
        }:
            return None

        number = float(text)

        if not isfinite(number):
            return None

        return number

    except (
        ValueError,
        TypeError
    ):

        return None


# ============================================================
# UTILITY: TIMESTAMP KEY
# ============================================================

def timestamp_key(timestamp):

    try:

        timestamp = str(
            timestamp
        ).strip()

        if not timestamp:
            return None

        parts = timestamp.split()

        if len(parts) < 2:
            return None

        date_part = parts[0]
        time_part = parts[1]

        day, month, year = (
            date_part.split("-")
        )

        hour, minute = (
            time_part.split(":")[:2]
        )

        return (
            int(year),
            int(month),
            int(day),
            int(hour),
            int(minute)
        )

    except Exception:

        return None


# ============================================================
# HAVERSINE DISTANCE
# ============================================================

def haversine_km(
    lat1,
    lon1,
    lat2,
    lon2
):

    lat1 = radians(
        float(lat1)
    )

    lon1 = radians(
        float(lon1)
    )

    lat2 = radians(
        float(lat2)
    )

    lon2 = radians(
        float(lon2)
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    return (
        EARTH_RADIUS_KM
        * c
    )


# ============================================================
# READ CSV
# ============================================================

def read_csv_rows(path):

    with open(
        path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as file:

        reader = csv.DictReader(
            file
        )

        for row in reader:

            yield row


# ============================================================
# LOAD RAINFALL STATIONS
# ============================================================

def load_rainfall_stations():

    stations = {}

    files = sorted(
        RAINFALL_DIR.glob("*.csv")
    )

    print(
        "\nLoading rainfall stations..."
    )

    print(
        "Files found:",
        len(files)
    )

    for file in files:

        try:

            for row in read_csv_rows(
                file
            ):

                station = (
                    row.get(
                        "Station"
                    )
                    or ""
                ).strip()

                latitude = clean_number(
                    row.get(
                        "Latitude"
                    )
                )

                longitude = clean_number(
                    row.get(
                        "Longitude"
                    )
                )

                if not station:
                    continue

                if (
                    latitude is None
                    or longitude is None
                ):
                    continue

                key = (
                    station,
                    round(
                        latitude,
                        6
                    ),
                    round(
                        longitude,
                        6
                    )
                )

                if key not in stations:

                    stations[key] = {

                        "station":
                            station,

                        "agency":
                            (
                                row.get(
                                    "Agency"
                                )
                                or "CWC"
                            ),

                        "state":
                            (
                                row.get(
                                    "State"
                                )
                                or ""
                            ),

                        "district":
                            (
                                row.get(
                                    "District"
                                )
                                or ""
                            ),

                        "river":
                            (
                                row.get(
                                    "River"
                                )
                                or ""
                            ),

                        "latitude":
                            latitude,

                        "longitude":
                            longitude
                    }

        except Exception as exc:

            print(
                "Rainfall file error:",
                file.name,
                exc
            )

    result = list(
        stations.values()
    )

    print(
        "Rainfall stations loaded:",
        len(result)
    )

    return result


# ============================================================
# LOAD RIVER STATIONS
# ============================================================

def load_river_stations():

    stations = {}

    files = sorted(
        RIVER_DIR.glob("*.csv")
    )

    print(
        "\nLoading river stations..."
    )

    print(
        "Files found:",
        len(files)
    )

    for file in files:

        try:

            for row in read_csv_rows(
                file
            ):

                station = (
                    row.get(
                        "Station"
                    )
                    or ""
                ).strip()

                latitude = clean_number(
                    row.get(
                        "Latitude"
                    )
                )

                longitude = clean_number(
                    row.get(
                        "Longitude"
                    )
                )

                if not station:
                    continue

                if (
                    latitude is None
                    or longitude is None
                ):
                    continue

                key = (
                    station,
                    round(
                        latitude,
                        6
                    ),
                    round(
                        longitude,
                        6
                    )
                )

                if key not in stations:

                    stations[key] = {

                        "station":
                            station,

                        "agency":
                            (
                                row.get(
                                    "Agency"
                                )
                                or "CWC"
                            ),

                        "state":
                            (
                                row.get(
                                    "State"
                                )
                                or ""
                            ),

                        "district":
                            (
                                row.get(
                                    "District"
                                )
                                or ""
                            ),

                        "river":
                            (
                                row.get(
                                    "River"
                                )
                                or ""
                            ),

                        "basin":
                            (
                                row.get(
                                    "Basin"
                                )
                                or ""
                            ),

                        "latitude":
                            latitude,

                        "longitude":
                            longitude
                    }

        except Exception as exc:

            print(
                "River file error:",
                file.name,
                exc
            )

    result = list(
        stations.values()
    )

    print(
        "River stations loaded:",
        len(result)
    )

    return result


# ============================================================
# LOAD LATEST RAINFALL OBSERVATIONS
# ============================================================

def load_latest_rainfall():

    latest = {}

    files = sorted(
        RAINFALL_DIR.glob("*.csv")
    )

    print(
        "\nLoading latest rainfall observations..."
    )

    for file in files:

        try:

            for row in read_csv_rows(
                file
            ):

                station = (
                    row.get(
                        "Station"
                    )
                    or ""
                ).strip()

                latitude = clean_number(
                    row.get(
                        "Latitude"
                    )
                )

                longitude = clean_number(
                    row.get(
                        "Longitude"
                    )
                )

                rainfall = clean_number(
                    row.get(
                        RAINFALL_VALUE_COLUMN
                    )
                )

                timestamp = (
                    row.get(
                        "Data Acquisition Time",
                        ""
                    )
                    or ""
                ).strip()

                if not station:
                    continue

                if (
                    latitude is None
                    or longitude is None
                ):
                    continue

                if rainfall is None:
                    continue

                if not timestamp:
                    continue

                key = (
                    station,
                    round(
                        latitude,
                        6
                    ),
                    round(
                        longitude,
                        6
                    )
                )

                current_key = timestamp_key(
                    timestamp
                )

                if current_key is None:
                    continue

                candidate = {

                    "station":
                        station,

                    "state":
                        (
                            row.get(
                                "State"
                            )
                            or ""
                        ),

                    "district":
                        (
                            row.get(
                                "District"
                            )
                            or ""
                        ),

                    "river":
                        (
                            row.get(
                                "River"
                            )
                            or ""
                        ),

                    "latitude":
                        latitude,

                    "longitude":
                        longitude,

                    "observation_time":
                        timestamp,

                    "rainfall_mm":
                        rainfall,

                    "source":
                        "CWC NWDP",

                    "dataset_period":
                        "2021-2025",

                    "_timestamp_key":
                        current_key
                }

                if (
                    key not in latest
                    or
                    current_key
                    >
                    latest[key][
                        "_timestamp_key"
                    ]
                ):

                    latest[key] = candidate

        except Exception as exc:

            print(
                "Rainfall observation error:",
                file.name,
                exc
            )

    for item in latest.values():

        item.pop(
            "_timestamp_key",
            None
        )

    print(
        "Valid rainfall observations:",
        len(latest)
    )

    return latest


# ============================================================
# LOAD LATEST RIVER OBSERVATIONS
# ============================================================

def load_latest_river():

    latest = {}

    files = sorted(
        RIVER_DIR.glob("*.csv")
    )

    print(
        "\nLoading latest river observations..."
    )

    for file in files:

        try:

            for row in read_csv_rows(
                file
            ):

                station = (
                    row.get(
                        "Station"
                    )
                    or ""
                ).strip()

                latitude = clean_number(
                    row.get(
                        "Latitude"
                    )
                )

                longitude = clean_number(
                    row.get(
                        "Longitude"
                    )
                )

                discharge = clean_number(
                    row.get(
                        RIVER_VALUE_COLUMN
                    )
                )

                timestamp = (
                    row.get(
                        "Data Acquisition Time",
                        ""
                    )
                    or ""
                ).strip()

                if not station:
                    continue

                if (
                    latitude is None
                    or longitude is None
                ):
                    continue

                if discharge is None:
                    continue

                if not timestamp:
                    continue

                current_key = timestamp_key(
                    timestamp
                )

                if current_key is None:
                    continue

                key = (
                    station,
                    round(
                        latitude,
                        6
                    ),
                    round(
                        longitude,
                        6
                    )
                )

                candidate = {

                    "station":
                        station,

                    "state":
                        (
                            row.get(
                                "State"
                            )
                            or ""
                        ),

                    "district":
                        (
                            row.get(
                                "District"
                            )
                            or ""
                        ),

                    "river":
                        (
                            row.get(
                                "River"
                            )
                            or ""
                        ),

                    "basin":
                        (
                            row.get(
                                "Basin"
                            )
                            or ""
                        ),

                    "latitude":
                        latitude,

                    "longitude":
                        longitude,

                    "observation_time":
                        timestamp,

                    "discharge_m3s":
                        discharge,

                    "source":
                        "CWC",

                    "dataset_period":
                        "1970-2025",

                    "_timestamp_key":
                        current_key
                }

                if (
                    key not in latest
                    or
                    current_key
                    >
                    latest[key][
                        "_timestamp_key"
                    ]
                ):

                    latest[key] = candidate

        except Exception as exc:

            print(
                "River observation error:",
                file.name,
                exc
            )

    for item in latest.values():

        item.pop(
            "_timestamp_key",
            None
        )

    print(
        "Valid river observations:",
        len(latest)
    )

    return latest


# ============================================================
# FIND NEAREST STATION
# ============================================================

def find_nearest_station(
    stations,
    observations,
    latitude,
    longitude,
    max_distance_km=None
):

    best_station = None
    best_observation = None
    best_distance = float(
        "inf"
    )

    for station in stations:

        key = (
            station["station"],
            round(
                station["latitude"],
                6
            ),
            round(
                station["longitude"],
                6
            )
        )

        observation = observations.get(
            key
        )

        if observation is None:
            continue

        distance = haversine_km(
            latitude,
            longitude,
            station["latitude"],
            station["longitude"]
        )

        if (
            max_distance_km is not None
            and
            distance > max_distance_km
        ):
            continue

        if (
            distance < best_distance
        ):

            best_distance = distance

            best_station = station

            best_observation = observation

    if best_station is None:

        return (
            None,
            None
        )

    station_result = dict(
        best_station
    )

    station_result[
        "distance_km"
    ] = round(
        best_distance,
        3
    )

    return (
        station_result,
        best_observation
    )


# ============================================================
# LOAD ML FORECAST
# ============================================================

def load_latest_forecast():

    if not FORECAST_FILE.exists():

        return {

            "status":
                "unavailable",

            "mode":
                "forecast_file_missing",

            "forecast":
                {},

            "warning":
                (
                    "ML forecast file was not found."
                )
        }

    try:

        with open(
            FORECAST_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        return data

    except Exception as exc:

        return {

            "status":
                "error",

            "mode":
                "forecast_load_error",

            "forecast":
                {},

            "error":
                str(exc)
        }


# ============================================================
# STARTUP
# ============================================================

print()
print("=" * 80)
print(
    "FLOODWATCH NARAJ FLOOD INTELLIGENCE API"
)
print("=" * 80)

print()
print(
    "Project:",
    PROJECT_DIR
)

print(
    "ML directory:",
    ML_DIR
)

print(
    "Rainfall directory:",
    RAINFALL_DIR
)

print(
    "River directory:",
    RIVER_DIR
)

print(
    "Forecast:",
    FORECAST_FILE
)


if not RAINFALL_DIR.exists():

    print()
    print(
        "WARNING: Rainfall directory does not exist."
    )


if not RIVER_DIR.exists():

    print()
    print(
        "WARNING: River directory does not exist."
    )


RAINFALL_STATIONS = (
    load_rainfall_stations()
)

RIVER_STATIONS = (
    load_river_stations()
)

LATEST_RAINFALL = (
    load_latest_rainfall()
)

LATEST_RIVER = (
    load_latest_river()
)

print()
print(
    "Data loading complete."
)


# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(
    BaseHTTPRequestHandler
):


    # ========================================================
    # JSON RESPONSE
    # ========================================================

    def send_json(
        self,
        data,
        status=200
    ):

        body = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False
        ).encode(
            "utf-8"
        )

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "*"
        )

        self.send_header(
            "Content-Length",
            str(
                len(body)
            )
        )

        self.end_headers()

        self.wfile.write(
            body
        )


    # ========================================================
    # OPTIONS
    # ========================================================

    def do_OPTIONS(self):

        self.send_response(
            204
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "*"
        )

        self.end_headers()


    # ========================================================
    # GET
    # ========================================================

    def do_GET(self):

        parsed = urlparse(
            self.path
        )

        path = parsed.path

        params = parse_qs(
            parsed.query
        )


        # ====================================================
        # ROOT / HEALTH CHECK
        # ====================================================

        if path == "/":

            forecast = (
                load_latest_forecast()
            )

            self.send_json({

                "status":
                    "online",

                "service":
                    "FloodWatch Flood Intelligence API",

                "api_version":
                    "1.0",

                "rainfall_dataset":
                    "CWC NWDP 2021-2025",

                "river_dataset":
                    "CWC telemetry 1970-2025",

                "rainfall_stations":
                    len(
                        RAINFALL_STATIONS
                    ),

                "river_stations":
                    len(
                        RIVER_STATIONS
                    ),

                "rainfall_observations":
                    len(
                        LATEST_RAINFALL
                    ),

                "river_observations":
                    len(
                        LATEST_RIVER
                    ),

                "forecast_status":
                    forecast.get(
                        "status",
                        "unknown"
                    ),

                "endpoints": [

                    "/",

                    "/api/forecast",

                    "/api/location"
                    "?latitude=20.5"
                    "&longitude=85.95"
                ]

            })

            return


        # ====================================================
        # ML FORECAST
        # ====================================================

        if path == "/api/forecast":

            forecast = (
                load_latest_forecast()
            )

            self.send_json(
                forecast
            )

            return


        # ====================================================
        # LOCATION
        # ====================================================

        if path == "/api/location":

            try:

                latitude = float(
                    params[
                        "latitude"
                    ][0]
                )

                longitude = float(
                    params[
                        "longitude"
                    ][0]
                )

            except Exception:

                self.send_json(
                    {

                        "status":
                            "error",

                        "error":
                            (
                                "latitude and longitude "
                                "are required."
                            )
                    },
                    400
                )

                return


            # =================================================
            # VALIDATE LATITUDE
            # =================================================

            if not (
                -90
                <= latitude
                <= 90
            ):

                self.send_json(
                    {

                        "status":
                            "error",

                        "error":
                            "Invalid latitude."
                    },
                    400
                )

                return


            # =================================================
            # VALIDATE LONGITUDE
            # =================================================

            if not (
                -180
                <= longitude
                <= 180
            ):

                self.send_json(
                    {

                        "status":
                            "error",

                        "error":
                            "Invalid longitude."
                    },
                    400
                )

                return


            # =================================================
            # RAINFALL STATION
            # =================================================

            (
                rainfall_station,
                rainfall_observation
            ) = find_nearest_station(
                RAINFALL_STATIONS,
                LATEST_RAINFALL,
                latitude,
                longitude,
                RAINFALL_MAX_DISTANCE_KM
            )


            rainfall_status = (
                "nearest_valid_observation"
            )


            if rainfall_station is None:

                (
                    rainfall_station,
                    rainfall_observation
                ) = find_nearest_station(
                    RAINFALL_STATIONS,
                    LATEST_RAINFALL,
                    latitude,
                    longitude,
                    None
                )

                rainfall_status = (
                    "nearest_available_observation"
                )


            if rainfall_station:

                rainfall_station[
                    "observation_status"
                ] = rainfall_status


                if (
                    rainfall_station[
                        "distance_km"
                    ]
                    >
                    RAINFALL_MAX_DISTANCE_KM
                ):

                    rainfall_station[
                        "distance_warning"
                    ] = (
                        "Nearest valid CWC rainfall "
                        "station is more than "
                        "250 km away."
                    )


            # =================================================
            # RIVER STATION
            # =================================================

            (
                river_station,
                river_observation
            ) = find_nearest_station(
                RIVER_STATIONS,
                LATEST_RIVER,
                latitude,
                longitude,
                RIVER_MAX_DISTANCE_KM
            )


            river_status = (
                "nearest_valid_observation"
            )


            if river_station is None:

                (
                    river_station,
                    river_observation
                ) = find_nearest_station(
                    RIVER_STATIONS,
                    LATEST_RIVER,
                    latitude,
                    longitude,
                    None
                )

                river_status = (
                    "nearest_available_observation"
                )


            if river_station:

                river_station[
                    "observation_status"
                ] = river_status


                if (
                    river_station[
                        "distance_km"
                    ]
                    >
                    RIVER_MAX_DISTANCE_KM
                ):

                    river_station[
                        "distance_warning"
                    ] = (
                        "Nearest valid CWC river "
                        "station is more than "
                        "250 km away."
                    )


            # =================================================
            # RESPONSE
            # =================================================

            response = {

                "status":
                    "success",

                "location": {

                    "latitude":
                        latitude,

                    "longitude":
                        longitude
                },


                "rainfall": {

                    "nearest_station":
                        rainfall_station,

                    "latest_observation":
                        rainfall_observation
                },


                "river": {

                    "nearest_station":
                        river_station,

                    "latest_observation":
                        river_observation
                },


                "data_notice":
                    (
                        "CWC observations are based "
                        "on locally available "
                        "historical datasets. "
                        "They should not be interpreted "
                        "as guaranteed live conditions."
                    ),


                "location_data_notice":
                    (
                        "The selected stations are "
                        "the nearest available CWC "
                        "stations with valid observations. "
                        "Distance should be considered "
                        "when interpreting local conditions."
                    )

            }


            self.send_json(
                response
            )

            return


        # ====================================================
        # UNKNOWN ENDPOINT
        # ====================================================

        self.send_json(
            {

                "status":
                    "error",

                "error":
                    "Endpoint not found.",

                "path":
                    path

            },
            404
        )


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    server = ThreadingHTTPServer(
        (
            HOST,
            PORT
        ),
        Handler
    )

    print()
    print("=" * 80)
    print(
        "SERVER RUNNING"
    )
    print("=" * 80)

    print()
    print(
        "Base API:"
    )

    print(
        f"http://{HOST}:{PORT}"
    )

    print()
    print(
        "ML Forecast:"
    )

    print(
        f"http://{HOST}:{PORT}/api/forecast"
    )

    print()
    print(
        "Location:"
    )

    print(
        f"http://{HOST}:{PORT}"
        "/api/location"
        "?latitude=20.5"
        "&longitude=85.95"
    )

    print()
    print(
        "Press CTRL+C to stop."
    )

    print("=" * 80)

    try:

        server.serve_forever()

    except KeyboardInterrupt:

        print()
        print(
            "Stopping server..."
        )

        server.server_close()