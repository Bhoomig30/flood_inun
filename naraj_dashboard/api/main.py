from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2, isfinite
import csv
import json
import os


# ============================================================
# FLOODWATCH / NARAJ FLOOD INTELLIGENCE API (v2)
# Serves the dashboard AND the API on one port.
#
# Prediction features are built ONLY from verified data in
# naraj_dashboard/data/ (CWC daily + hourly water levels and
# the dated NDEM events). External CWC CSVs under ml/data are
# used when present, but are no longer required.
# ============================================================

DASHBOARD_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = DASHBOARD_DIR.parent
ML_DIR = PROJECT_DIR / "ml"
DATA_DIR = DASHBOARD_DIR / "data"

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 8000))

EARTH_RADIUS_KM = 6371.0
RAINFALL_MAX_DISTANCE_KM = 300.0
RIVER_MAX_DISTANCE_KM = 400.0

HORIZONS = [6, 12, 24]

FORECAST_FILE = ML_DIR / "data" / "forecast" / "latest_forecast.json"

# Verified project data used by the built-in prediction engine.
DAILY_FILE = DATA_DIR / "cwc" / "naraj_daily_2021_2025.json"
HOURLY_FILE = DATA_DIR / "cwc" / "naraj_august2022_hourly.json"
EVENTS_FILE = DATA_DIR / "events_august2022.json"

# Verified focus stations — mirrors prediction_engine.js
STATION_DEFS = {
    "naraj": {
        "key": "naraj",
        "name": "Naraj",
        "river": "Mahanadi",
        "daily": DATA_DIR / "cwc" / "naraj_daily_2021_2025.json",
        "hourly": DATA_DIR / "cwc" / "naraj_august2022_hourly.json",
        "latitude": 20.4717,
        "longitude": 85.7656,
        "region": "Cuttack, Odisha (Mahanadi basin)",
    },
    "alipingal": {
        "key": "alipingal",
        "name": "Alipingal",
        "river": "Dhaniya",
        "daily": DATA_DIR / "cwc" / "alipingal_daily_2021_2025.json",
        "hourly": DATA_DIR / "cwc" / "alipingal_august2022_hourly.json",
        "latitude": 20.1289,
        "longitude": 86.1355,
        "region": "Jagatsinghpur, Odisha (Dhaniya basin)",
    },
    "nimapara": {
        "key": "nimapara",
        "name": "Nimapara",
        "river": "Dandia",
        "daily": DATA_DIR / "cwc" / "nimapara_daily_2021_2025.json",
        "hourly": DATA_DIR / "cwc" / "nimapara_august2022_hourly.json",
        "latitude": 20.0833,
        "longitude": 86.0,
        "region": "Puri, Odisha (Dandia basin)",
    },
}

# Static file types
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".geojson": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".map": "application/json",
}


# ============================================================
# UTILITIES
# ============================================================

def clean_number(value):
    try:
        if value is None:
            return None
        text = str(value).strip()
        if text == "" or text.lower() in {
            "nan", "none", "null", "na", "n/a", "-"
        }:
            return None
        number = float(text)
        return number if isfinite(number) else None
    except (ValueError, TypeError):
        return None


def timestamp_key(timestamp):
    try:
        parts = str(timestamp).strip().split()
        if len(parts) < 2:
            return None
        day, month, year = parts[0].split("-")
        hour, minute = parts[1].split(":")[:2]
        return (int(year), int(month), int(day), int(hour), int(minute))
    except Exception:
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    lat1 = radians(float(lat1))
    lon1 = radians(float(lon1))
    lat2 = radians(float(lat2))
    lon2 = radians(float(lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return EARTH_RADIUS_KM * 2 * atan2(sqrt(a), sqrt(1 - a))


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            yield row


def round6(value):
    return round(float(value), 6)


# ============================================================
# BUILT-IN FLOOD PREDICTION ENGINE (verified data only)
# Mirrors prediction_engine.js exactly.
# ============================================================

class FloodPredictor:
    """6/12/24h flood-risk model built from verified CWC/NDEM data.

    Blend per horizon: 0.7 * signal + 0.3 * seasonal_prior, where
    signal = wRise * rise_term + (1-wRise) * level_term.
    """

    def __init__(self):
        self.loaded = False
        self.load_error = None
        self.daily = []
        self.hourly = []
        self.events = []
        self.calibration = None

    def load(self):
        if self.loaded or self.load_error:
            return
        try:
            events = json.loads(EVENTS_FILE.read_text(encoding="utf-8-sig"))
            self.events = events.get("events", [])

            self.stations = {}
            for key, defn in STATION_DEFS.items():
                daily = json.loads(defn["daily"].read_text(encoding="utf-8-sig"))
                hourly = json.loads(
                    defn["hourly"].read_text(encoding="utf-8-sig")
                )
                daily_rows = [
                    {"date": r["date"], "level": float(r["water_level_m"])}
                    for r in daily.get("records", [])
                    if clean_number(r.get("water_level_m")) is not None
                ]
                daily_rows.sort(key=lambda r: r["date"])
                hourly_rows = []
                for r in hourly.get("records", []):
                    try:
                        t = datetime.fromisoformat(r["timestamp"])
                        level = float(r["water_level_m"])
                    except (KeyError, ValueError, TypeError):
                        continue
                    hourly_rows.append({"time": t, "level": level})
                hourly_rows.sort(key=lambda r: r["time"])
                self.stations[key] = {
                    "def": defn,
                    "daily": daily_rows,
                    "hourly": hourly_rows,
                    "calibration": self.build_calibration(
                        daily_rows, hourly_rows
                    ),
                }
            self.loaded = True
        except Exception as exc:
            self.load_error = str(exc)

    def station_list(self):
        self.load()
        out = []
        for key, st in self.stations.items():
            defn = st["def"]
            cal = st["calibration"]
            out.append({
                "key": key,
                "name": defn["name"],
                "river": defn["river"],
                "region": defn["region"],
                "latitude": defn["latitude"],
                "longitude": defn["longitude"],
                "daily_records": cal["daily_records"],
                "hourly_records": cal["hourly_records"],
                "monsoon_p95_m": round(cal["monsoon_p95_m"], 2),
                "record_start": cal["record_start"],
                "record_end": cal["record_end"],
            })
        return out

    def build_calibration(self, daily, hourly_rows):
        levels = [r["level"] for r in daily]
        n = len(daily)

        monsoon_levels = sorted(
            r["level"] for r in daily
            if 6 <= int(r["date"][5:7]) <= 10
        )
        count = len(monsoon_levels)
        mean = sum(monsoon_levels) / max(count, 1)
        variance = (
            sum((v - mean) ** 2 for v in monsoon_levels) / max(count - 1, 1)
        )
        std = variance ** 0.5
        p95 = monsoon_levels[min(count - 1, max(0, int(0.95 * count)))]

        month_high = [0] * 12
        month_total = [0] * 12
        for r in daily:
            m = int(r["date"][5:7]) - 1
            month_total[m] += 1
            if r["level"] >= p95:
                month_high[m] += 1
        month_rate = [
            {
                "month": m + 1,
                "days": month_total[m],
                "high_days": month_high[m],
                "rate": (month_high[m] / month_total[m]) if month_total[m] else 0.0,
            }
            for m in range(12)
        ]

        hr = [r["level"] for r in hourly_rows]
        max_rise = {}
        for h in HORIZONS:
            max_rise[h] = max(
                (hr[i] - hr[i - h] for i in range(h, len(hr))), default=0.0
            )

        return {
            "monsoon_mean_m": mean,
            "monsoon_std_m": std,
            "monsoon_p95_m": p95,
            "monsoon_records": count,
            "max_rise": max_rise,
            "month_rate": month_rate,
            "daily_records": n,
            "hourly_records": len(hr),
            "hourly_start": (
                hourly_rows[0]["time"].isoformat() if hourly_rows else None
            ),
            "hourly_end": (
                hourly_rows[-1]["time"].isoformat() if hourly_rows else None
            ),
            "record_start": daily[0]["date"] if daily else None,
            "record_end": daily[-1]["date"] if daily else None,
        }

    def seasonal_prior(self, st, date_str):
        m = int(date_str[5:7]) - 1
        entry = st["calibration"]["month_rate"][m]
        rate = entry["rate"]
        floor = 0.04 if 5 <= m <= 9 else 0.01
        return min(max(rate * 1.6, floor), 0.5)

    def rise_term(self, st, rise, h):
        if not isfinite(rise) or rise <= 0:
            return 0.0
        scale = 0.75 * st["calibration"]["max_rise"][h]
        return min(rise / scale, 1.0)

    def level_term(self, st, level):
        mean = st["calibration"]["monsoon_mean_m"]
        std = max(st["calibration"]["monsoon_std_m"], 0.01)
        z = (level - mean) / std
        return min(max((z - 0.5) / 2.5, 0.0), 1.0)

    def level_z(self, st, level):
        mean = st["calibration"]["monsoon_mean_m"]
        std = max(st["calibration"]["monsoon_std_m"], 0.01)
        return (level - mean) / std

    def combine_for_horizon(self, st, h, rise, level, prior,
                            continuation_rise=0.0):
        r_term = self.rise_term(st, rise, h)
        l_term = self.level_term(st, level)

        # Trend continuation term (mirrors prediction_engine.js v2)
        c_term = 0.0
        if isfinite(continuation_rise) and continuation_rise > 0:
            horizon_cap = st["calibration"]["max_rise"][h]
            capped = min(continuation_rise, horizon_cap)
            c_term = min(capped / (0.75 * horizon_cap), 1.0)

        w_rise = 0.45 if h == 6 else 0.4 if h == 12 else 0.35
        w_cont = 0.2 if h == 6 else 0.18 if h == 12 else 0.15
        w_level = 1 - w_rise - w_cont

        signal = w_rise * r_term + w_cont * c_term + w_level * l_term
        probability = 100 * (0.7 * signal + 0.3 * prior)
        return min(100, max(2, probability))

    def forecast_cone(self, st, current_level, trend_per_3h):
        # Recession scale: median absolute daily change in the daily record.
        if not st.get("_recession_per_day"):
            levels = [r["level"] for r in st["daily"]]
            changes = sorted(
                abs(levels[i] - levels[i - 1]) for i in range(1, len(levels))
            )
            st["_recession_per_day"] = (
                changes[len(changes) // 2] if changes else 0.05
            )

        cone = []
        for h in HORIZONS:
            days_ahead = h / 24
            high = current_level + trend_per_3h * (h / 3)
            low = current_level - st["_recession_per_day"] * days_ahead
            cone.append({
                "h": h,
                "low": round(min(low, current_level), 2),
                "high": round(max(high, current_level), 2),
                "threshold": round(
                    current_level
                    + 0.75 * st["calibration"]["max_rise"][h], 2
                ),
            })
        return cone

    def risk_band(self, p):
        if p >= 75:
            return "HIGH"
        if p >= 25:
            return "MODERATE"
        return "LOW"

    def hourly_at_or_before(self, st, t):
        series = st["hourly"]
        lo, hi = 0, len(series) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if series[mid]["time"] <= t:
                best = series[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return best

    def predict(self, reference_time_str=None, station_key=None):
        self.load()
        if not self.loaded:
            return {
                "status": "error",
                "error": self.load_error or "Prediction data unavailable",
                "forecast": {},
            }

        key = (station_key or "naraj").lower()
        if key not in self.stations:
            key = "naraj"
        st = self.stations[key]
        defn = st["def"]
        cal = st["calibration"]

        requested = None
        if reference_time_str:
            try:
                requested = datetime.fromisoformat(
                    str(reference_time_str).replace("Z", "+00:00")
                )
            except ValueError:
                requested = None

        hourly_end = st["hourly"][-1]["time"]
        ref = requested if (requested and requested <= hourly_end) else hourly_end

        latest = self.hourly_at_or_before(st, ref)
        if latest is None:
            return {
                "status": "error",
                "error": (
                    "No hourly observation at or before the requested time. "
                    "Hourly coverage starts " + str(cal["hourly_start"])
                ),
                "forecast": {},
            }

        rises = {}
        for h in HORIZONS:
            past = self.hourly_at_or_before(
                st, latest["time"] - timedelta(hours=h)
            )
            rises[h] = latest["level"] - past["level"] if past else 0.0

        past3 = self.hourly_at_or_before(
            st, latest["time"] - timedelta(hours=3)
        )
        trend3h = latest["level"] - past3["level"] if past3 else 0.0

        date_str = latest["time"].strftime("%Y-%m-%d")
        prior = self.seasonal_prior(st, date_str)

        forecast = {}
        for h in HORIZONS:
            continuation = trend3h * (h / 3)
            probability = self.combine_for_horizon(
                st, h, rises[h], latest["level"], prior, continuation
            )
            forecast[f"{h}h"] = {
                "flood_probability_percent": round(probability, 2),
                "risk": self.risk_band(probability),
                "projected_rise_m": round(continuation, 2),
            }

        cone = self.forecast_cone(st, latest["level"], trend3h)
        max_prob = max(f["flood_probability_percent"] for f in forecast.values())

        monsoon_levels = sorted(
            r["level"] for r in st["daily"]
            if 6 <= int(r["date"][5:7]) <= 10
        )
        below = sum(1 for v in monsoon_levels if v <= latest["level"])

        return {
            "status": "success",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "requested_time": requested.isoformat() if requested else None,
            "reference_time": latest["time"].isoformat(),
            "station_key": key,
            "location": {
                "latitude": defn["latitude"],
                "longitude": defn["longitude"],
                "station": defn["name"],
                "station_key": key,
                "river": defn["river"],
            },
            "model_name": "FloodWatch Temporal Risk Model",
            "algorithm": (
                "Rise-rate + river-level + seasonal-prior blend "
                "(calibrated on verified CWC data)"
            ),
            "study_region": defn["region"],
            "feature_count": 4,
            "observed": {
                "water_level_m": round(latest["level"], 2),
                "monsoon_percentile": round(
                    100 * below / max(len(monsoon_levels), 1), 1
                ),
                "z_vs_monsoon_mean": round(
                    self.level_z(st, latest["level"]), 2
                ),
                "rise_6h_m": round(rises[6], 2),
                "rise_12h_m": round(rises[12], 2),
                "rise_24h_m": round(rises[24], 2),
                "trend_3h_m": round(trend3h, 2),
            },
            "overall_risk": self.risk_band(max_prob),
            "forecast": forecast,
            "forecast_cone": cone,
            "calibration": {
                "monsoon_mean_m": round(cal["monsoon_mean_m"], 3),
                "monsoon_std_m": round(cal["monsoon_std_m"], 3),
                "monsoon_p95_m": round(cal["monsoon_p95_m"], 3),
                "max_rise": {
                    k: round(v, 2) for k, v in cal["max_rise"].items()
                },
                "record_start": cal["record_start"],
                "record_end": cal["record_end"],
                "hourly_start": cal["hourly_start"],
                "hourly_end": cal["hourly_end"],
                "daily_records": cal["daily_records"],
                "hourly_records": cal["hourly_records"],
            },
            "warning": (
                "AI/ML forecast built from verified CWC historical "
                "observations. Not a live government flood warning."
            ),
        }

    def backtest(self):
        self.load()
        if not self.loaded:
            return {"status": "error", "error": self.load_error or "data unavailable"}

        naraj = self.stations.get("naraj")
        if naraj is None:
            return {"status": "error", "error": "Naraj data unavailable"}

        results = []
        for ev in self.events:
            try:
                target = datetime.fromisoformat(
                    ev["target_time_utc"].replace("Z", "+00:00")
                )
            except (KeyError, ValueError, TypeError):
                continue
            issue_time = target - timedelta(hours=24)
            snapshot = self.hourly_at_or_before(naraj, issue_time)
            if snapshot is None:
                continue

            rises = {}
            for h in HORIZONS:
                past = self.hourly_at_or_before(
                    naraj, snapshot["time"] - timedelta(hours=h)
                )
                rises[h] = snapshot["level"] - past["level"] if past else 0.0
            prior = self.seasonal_prior(
                naraj, snapshot["time"].strftime("%Y-%m-%d")
            )

            probabilities = {
                f"{h}h": round(
                    self.combine_for_horizon(
                        naraj, h, rises[h], snapshot["level"], prior
                    ),
                    2,
                )
                for h in HORIZONS
            }
            results.append({
                "event_id": ev.get("id"),
                "event_date": ev.get("date"),
                "target_time_utc": ev.get("target_time_utc"),
                "forecast_issued_at": snapshot["time"].isoformat(),
                "observed_level_at_issue_m": round(snapshot["level"], 2),
                "observed_rise_24h_before_m": round(rises[24], 2),
                "probabilities": probabilities,
                "outcome": "flood",
            })

        metrics = {}
        for h in HORIZONS:
            key = f"{h}h"
            brier = logloss = 0.0
            for r in results:
                p = r["probabilities"][key] / 100
                brier += (p - 1) ** 2
                pc = min(max(p, 1e-6), 1 - 1e-6)
                logloss += -(math_log(pc))
            metrics[key] = {
                "brier_score": round(brier / len(results), 4),
                "log_loss": round(logloss / len(results), 4),
                "mean_probability": round(
                    sum(r["probabilities"][key] for r in results) / len(results), 2
                ),
            }

        return {
            "status": "success",
            "description": (
                "Causal evaluation: each forecast uses only observations "
                "available 24 hours before the event. All rows are the dated "
                "NDEM flood events of August 2022. With only 4 events these "
                "metrics are indicative, not a validated accuracy figure."
            ),
            "n_events": len(results),
            "metrics": metrics,
            "rows": results,
        }


def math_log(value):
    import math
    return math.log(value)


PREDICTOR = FloodPredictor()


# ============================================================
# ML ENSEMBLE (v3 models trained on the real Hugging Face dataset)
# Loads the same joblib bundles as ml_serve.py — native here, no subprocess.
# Only blended for Naraj (the RFs are Naraj-target models), 60/40 with the
# statistical engine, as-of aligned to the engine's reference_time.
# ============================================================

ML_MODELS = {"bundles": None, "dataframe": None, "error": None}


def ml_load():
    """Load model bundles + dataset once; on failure record the reason."""
    if ML_MODELS["bundles"] is not None or ML_MODELS["error"]:
        return
    try:
        import joblib
        import pandas as pd

        models = {}
        for h in (6, 12, 24):
            models[h] = joblib.load(DATA_DIR / "ml_models" / f"hf_forecast_{h}h.pkl")
        df = pd.read_csv(
            DATA_DIR / "hf" / "forecast_dataset.csv", parse_dates=["timestamp"]
        ).sort_values("timestamp").reset_index(drop=True)
        ML_MODELS["bundles"] = models
        ML_MODELS["dataframe"] = df
        print("ML ensemble loaded (v3 HF dataset models, %d rows)" % len(df))
    except Exception as exc:  # ML is optional; statistical engine must not break
        ML_MODELS["error"] = f"{type(exc).__name__}: {exc}"
        print("ML ensemble unavailable:", ML_MODELS["error"])


def ml_predict(reference_time_iso):
    """Return {h: probability 0..1} or (None, reason)."""
    ml_load()
    if ML_MODELS["bundles"] is None:
        return None, ML_MODELS["error"]
    try:
        import pandas as pd

        df = ML_MODELS["dataframe"]
        if reference_time_iso:
            ts = pd.Timestamp(reference_time_iso)
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
            idx = df.index[df["timestamp"] == ts]
            if len(idx) == 0:
                return None, f"reference_time {ts} outside the real dataset range"
            row = df.loc[idx[-1]]
        else:
            row = df.iloc[-1]
        features = ML_MODELS["bundles"][6]["features"]
        # keep column names (imputer was fitted on a DataFrame)
        x = row[features].to_frame().T
        out = {}
        for h, bundle in ML_MODELS["bundles"].items():
            xi = bundle["imputer"].transform(x)
            out[f"{h}h"] = float(bundle["model"].predict_proba(xi)[0, 1])
        return out, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def apply_ml_ensemble(result):
    """Mirror server.js: blend 40% RF into the statistical forecast for Naraj."""
    if result.get("status") != "success":
        return result
    capable = result.get("station_key", "naraj") == "naraj"
    result["ml_capable"] = capable
    if not capable:
        result["ml"] = {"available": ML_MODELS["bundles"] is not None,
                        "model_version": None, "reason": None}
        return result
    probs, err = ml_predict(result.get("reference_time"))
    result["ml"] = {
        "available": ML_MODELS["bundles"] is not None,
        "model_version": "rf_hf_v3" if ML_MODELS["bundles"] is not None else None,
        "reason": err or ML_MODELS["error"],
    }
    if probs is None:
        return result
    result["ml_enabled"] = True
    result["ml_result"] = {"as_of": result["reference_time"], "horizons": {
        h: {"probability": round(p, 4), "source": "rf_hf_v3"} for h, p in probs.items()
    }}
    ml_weight = 0.4
    for h, p01 in probs.items():
        f = result["forecast"].get(h)
        if not f:
            continue
        ml_p = round(p01 * 10000) / 100  # -> percent, 2dp
        blended = (1 - ml_weight) * f["flood_probability_percent"] + ml_weight * ml_p
        f["ml_probability_percent"] = ml_p
        f["ml_weight"] = ml_weight
        f["flood_probability_percent"] = round(blended, 2)
        f["risk"] = PREDICTOR.risk_band(f["flood_probability_percent"])
    max_p = max(f["flood_probability_percent"] for f in result["forecast"].values())
    result["overall_risk"] = PREDICTOR.risk_band(max_p)
    return result


def build_model_info():
    """Mirror server.js /api/model/info from the v3 training metadata."""
    meta_path = DATA_DIR / "ml_models" / "hf_forecast_metadata.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        meta = None
    if not meta:
        return {
            "status": "unavailable",
            "notes": [
                "Run ml_train.py (requires data/hf/forecast_dataset.csv from "
                "the Hugging Face dataset) to train the models."
            ],
            "ml_bridge": {"available": ML_MODELS["bundles"] is not None,
                          "reason": ML_MODELS["error"]},
        }
    ds = meta.get("dataset", {})
    return {
        "status": "trained",
        "trained_at": meta.get("trained_at"),
        "version": meta.get("version"),
        "data_source": meta.get("data_source"),
        "dataset": ds,
        "label_rule": (
            f"Naraj level exceeds {ds.get('flood_threshold_m', 24.28)} m "
            "(95th percentile of the 2021-2025 record) within the next horizon"
        ),
        "n_rows": ds.get("rows"),
        "splits": meta.get("split"),
        "features": meta.get("features", []),
        "horizons": meta.get("models", {}),
        "notes": meta.get("notes") or [
            "Trained ONLY on the real CWC-derived dataset (no synthetic data)."
        ],
        "ml_bridge": {
            "available": ML_MODELS["bundles"] is not None,
            "model_version": "rf_hf_v3" if ML_MODELS["bundles"] else None,
            "reason": ML_MODELS["error"],
        },
    }


def india_stations_response(params):
    """Mirror server.js /api/stations/india with q/basin/state filters."""
    q = (params.get("q", [""])[0] or "").strip().lower()
    basin = params.get("basin", ["all"])[0] or "all"
    state = params.get("state", ["all"])[0] or "all"
    try:
        raw = json.loads(
            (DATA_DIR / "india_stations.json").read_text(encoding="utf-8")
        )
    except Exception as exc:
        return {
            "status": "unavailable",
            "error": f"Registry file missing: {exc}",
            "stations": [],
        }
    stations = []
    for s in raw.get("stations", []):
        if basin != "all" and s.get("basin") != basin:
            continue
        if state != "all" and s.get("state") != state:
            continue
        if q:
            hay = " ".join(
                str(s.get(k, "")) for k in ("name", "river", "state", "district")
            ).lower()
            if q not in hay:
                continue
        stations.append(s)
    return {"status": "success", "count": len(stations), "stations": stations}


def levels_recent_response(params):
    """Mirror server.js /api/levels/recent: last 72 hourly points."""
    PREDICTOR.load()
    key = (params.get("station", ["naraj"])[0] or "naraj").strip().lower()
    if key not in PREDICTOR.stations:
        return {"status": "error", "error": f"Unknown station '{key}'"}
    st = PREDICTOR.stations[key]
    series = st["hourly"][-72:]
    defn = st["def"]
    p95 = st.get("calibration", {}).get("monsoon_p95_m")
    return {
        "station": defn["name"],
        "station_key": key,
        "timestamps": [r["time"].isoformat() + "Z" for r in series],
        "levels": [round(r["level"], 2) for r in series],
        "monsoon_p95_m": round(p95, 2) if p95 is not None else None,
    }


# ============================================================
# INDIA-WIDE CWC STATION REGISTRY (real data)
# Built by scripts/build_india_registry.py from the project's
# REAL CWC datasets (state-wise rainfall 2021-2025 + river
# discharge 1970-2025). No stations invented, no values imputed.
# ============================================================

INDIA_REGISTRY_FILE = DATA_DIR / "india_cwc" / "stations.json"


def load_india_registry():
    try:
        return json.loads(INDIA_REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"India registry unavailable: {exc}")
        return None


INDIA_REGISTRY = load_india_registry()


def _registry_stations(kind=None):
    if not INDIA_REGISTRY:
        return []
    out = []
    for s in INDIA_REGISTRY.get("stations", []):
        if kind and s.get("kind") != kind:
            continue
        if s.get("latitude") is None or s.get("longitude") is None:
            continue
        out.append(s)
    return out


def nearest_india_station(kind, latitude, longitude, max_km):
    """Nearest registry station of `kind`, preferring one with a valid
    observation. Returns (payload, status) where status is 'success' or
    'no_nearby_station' — never an arbitrary far-away station."""
    stations = _registry_stations(kind)
    if not stations:
        return {
            "status": "no_nearby_station",
            "max_radius_km": max_km,
            "message": "India-wide CWC station registry is not available. "
            "Run scripts/build_india_registry.py with the real CWC datasets.",
        }, "no_nearby_station"

    best = best_with_obs = None
    best_d = best_obs_d = float("inf")
    for s in stations:
        d = haversine_km(latitude, longitude, s["latitude"], s["longitude"])
        if d < best_d:
            best_d, best = d, s
        latest_obs = s.get("latest_observation")
        if (
            latest_obs
            and isinstance(latest_obs.get("value"), (int, float))
            and latest_obs["value"] >= 0
            and d < best_obs_d
        ):
            best_obs_d, best_with_obs = d, s

    if best is None or best_d > max_km:
        return {
            "status": "no_nearby_station",
            "max_radius_km": max_km,
            "message": f"No nearby CWC {kind} monitoring station is available "
            f"within {max_km:g} km of this location.",
        }, "no_nearby_station"

    chosen, dist = (
        (best_with_obs, best_obs_d)
        if best_with_obs is not None and best_obs_d <= max_km
        else (best, best_d)
    )
    obs = _station_latest_obs(chosen)
    payload = {
        "status": "success",
        "station": {
            "station": chosen.get("station"),
            "kind": chosen.get("kind"),
            "state": chosen.get("state"),
            "district": chosen.get("district"),
            "river": chosen.get("river"),
            "basin": chosen.get("basin"),
            "latitude": chosen.get("latitude"),
            "longitude": chosen.get("longitude"),
            "n_obs": chosen.get("n_obs"),
            "first_obs": chosen.get("first_obs"),
            "last_obs": chosen.get("last_obs"),
            "recent_observations": chosen.get("recent_observations", []),
        },
        "distance_km": round(dist, 3),
        "observation_status": (
            "valid_observation"
            if obs
            else "station_in_registry_but_no_valid_observation_in_dataset"
        ),
        "latest_observation": (
            {
                "time": obs.get("time"),
                "value": obs.get("value"),
                "unit": obs.get("unit"),
                "rainfall_mm": obs.get("value") if kind == "rainfall" else None,
                "discharge_m3s": obs.get("value") if kind == "river" else None,
                "observation_time": obs.get("time"),
                "source": "CWC NWDP telemetry (real historical dataset)",
                "dataset_period": "2021-2025" if kind == "rainfall" else "1970-2025",
            }
            if obs
            else None
        ),
    }
    return payload, "success"


# ------------------------------------------------------------
# PRESENT CONDITION — analytical status from REAL observations
# only. Rule-based, NOT machine learning, NOT a forecast.
# Mirrors naraj_dashboard/location_service.js exactly.


def _station_latest_obs(station):
    """Newest PHYSICALLY VALID observation for a registry station.

    CWC telemetry CSVs contain occasional negative placeholder/sensor-error
    values (discharge or rainfall can never be negative). They are treated as
    invalid observations — never displayed, never summed, never allowed to
    steer a trend. Falls back to the newest valid value in the recent series
    (still real data, just not the raw last row).
    """
    latest = station.get("latest_observation")
    if (
        latest
        and isinstance(latest.get("value"), (int, float))
        and latest["value"] >= 0
    ):
        return latest
    for point in reversed(station.get("recent_observations", [])):
        value = point.get("value")
        if isinstance(value, (int, float)) and value >= 0:
            return {
                "time": point.get("time"),
                "value": value,
                "unit": "m3/s" if station.get("kind") == "river" else "mm",
            }
    return None
# ------------------------------------------------------------

RAINFALL_WATCH_MM_24H = 64.5   # IMD heavy-rainfall class (24h)
RAINFALL_ALERT_MM_24H = 115.5  # IMD very-heavy-rainfall class (24h)
STALE_AFTER_DAYS = 10


def _dataset_max_time(kind=None):
    stations = _registry_stations(kind) if kind else (
        (INDIA_REGISTRY or {}).get("stations", [])
    )
    newest = None
    for s in stations:
        t = s.get("last_obs")
        if t:
            ts = _parse_iso(t)
            if ts and (newest is None or ts > newest):
                newest = ts
    return newest


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _trend_direction(values, rel_band):
    if not isinstance(values, list) or len(values) < 4:
        return None
    half = len(values) // 2
    older = values[:half]
    newer = values[len(values) - half:]
    old_mean = sum(older) / len(older) if older else 0
    new_mean = sum(newer) / len(newer) if newer else 0
    if old_mean <= 0:
        if new_mean > 0:
            return {"direction": "RISING", "change_percent": None}
        return {"direction": "STABLE", "change_percent": 0}
    change = (new_mean - old_mean) / old_mean
    if change > rel_band:
        return {"direction": "RISING", "change_percent": round(change * 100, 1)}
    if change < -rel_band:
        return {"direction": "FALLING", "change_percent": round(change * 100, 1)}
    return {"direction": "STABLE", "change_percent": round(change * 100, 1)}


# Consistent DATA-QUALITY states (mirrors location_service.js):
#   FRESH <=1 day of dataset newest, RECENT <=7d, STALE <=10d, ARCHIVED older.
QUALITY_FRESH_HOURS = 24
QUALITY_RECENT_DAYS = 7


def _quality_for(age_days):
    if age_days is None:
        return "UNAVAILABLE"
    if age_days <= QUALITY_FRESH_HOURS / 24:
        return "FRESH"
    if age_days <= QUALITY_RECENT_DAYS:
        return "RECENT"
    if age_days <= STALE_AFTER_DAYS:
        return "STALE"
    return "ARCHIVED"


def _freshness_for(station):
    newest = _dataset_max_time(station.get("kind"))
    last = _parse_iso(station.get("last_obs"))
    if not last or newest is None:
        return {
            "freshness": "unknown",
            "quality": "UNAVAILABLE",
            "note": "No observation timestamps available.",
        }
    age_days = (newest - last).total_seconds() / 86400
    latest = station.get("latest_observation")
    out = {
        "latest_observation_time": latest.get("time") if latest else None,
        "hours_behind_dataset_newest": round(age_days * 24, 1),
        "quality": _quality_for(age_days),
    }
    if age_days <= STALE_AFTER_DAYS:
        out["freshness"] = "dataset_current"
        out["note"] = "Among the newest observations available in the dataset."
    else:
        out["freshness"] = "stale"
        out["note"] = (
            f"Data may be stale — newest record for this station lags the "
            f"dataset by {age_days:.0f} days."
        )
    return out


def _unavailable(kind, station_result):
    return {
        "available": False,
        "status": (
            "no_nearby_station"
            if station_result and station_result.get("status") == "no_nearby_station"
            else "unavailable"
        ),
        "message": (
            station_result.get("message")
            if station_result and station_result.get("message")
            else (
                f"{'Rainfall' if kind == 'rainfall' else 'River monitoring'} "
                "observation data unavailable for this location."
            )
        ),
    }


def _rainfall_present(station_result):
    if (
        not station_result
        or station_result.get("status") != "success"
        or not station_result.get("station")
    ):
        return _unavailable("rainfall", station_result)

    st = station_result["station"]
    series = st.get("recent_observations", [])
    latest = _station_latest_obs(st)
    values = [
        p["value"]
        for p in series
        if isinstance(p.get("value"), (int, float)) and p["value"] >= 0
    ]

    # 24h accumulation over VALID observations only; requires minimum sample
    # density (>=4) so a sparse record falls back to the latest hourly value
    # instead of a misleading one-sample sum. Never fabricated.
    accumulation = None
    accumulation_span_hours = None
    if len(series) >= 2:
        last_t = _parse_iso(series[-1]["time"])
        total = 0.0
        window_samples = 0
        span_start = None
        for point in reversed(series):
            t = _parse_iso(point["time"])
            if last_t is None or t is None or (last_t - t).total_seconds() > 24 * 3600:
                break
            value = point.get("value")
            if not isinstance(value, (int, float)) or value < 0:
                continue
            total += value
            window_samples += 1
            span_start = point["time"]
        if span_start and window_samples >= 4:
            accumulation = round(total, 1)
            span_t = _parse_iso(span_start)
            accumulation_span_hours = round(
                (last_t - span_t).total_seconds() / 3600, 1
            )

    sums = [
        sum(values[i:i + 6])
        for i in range(0, max(0, len(values) - 5), 6)
    ]
    trend = _trend_direction(sums, 0.10)

    condition = "NORMAL"
    basis = []
    if accumulation is not None:
        if accumulation >= RAINFALL_ALERT_MM_24H:
            condition = "ALERT"
            basis.append(
                f"24h rainfall accumulation {accumulation} mm "
                "(IMD very-heavy threshold)"
            )
        elif accumulation >= RAINFALL_WATCH_MM_24H:
            condition = "WATCH"
            basis.append(
                f"24h rainfall accumulation {accumulation} mm "
                "(IMD heavy threshold)"
            )
        else:
            basis.append(
                f"24h rainfall accumulation {accumulation} mm "
                "(below heavy-rainfall threshold)"
            )
    elif latest and isinstance(latest.get("value"), (int, float)):
        basis.append(
            f"latest hourly rainfall {latest['value']} mm "
            "(no 24h window available)"
        )

    return {
        "available": True,
        "station": station_result.get("station"),
        "distance_km": station_result.get("distance_km"),
        "latest_observation": latest,
        "trend": (
            {
                "direction": trend["direction"],
                "change_percent": trend["change_percent"],
                "basis": "sum of freshest 6 observations vs previous 6",
            }
            if trend
            else None
        ),
        "accumulation_24h_mm": accumulation,
        "accumulation_span_hours": accumulation_span_hours,
        "value_type": "REAL OBSERVATION",
        "freshness": _freshness_for(st),
        "condition_contribution": {"condition": condition, "basis": basis},
    }


def _river_present(station_result):
    if (
        not station_result
        or station_result.get("status") != "success"
        or not station_result.get("station")
    ):
        return _unavailable("river", station_result)

    st = station_result["station"]
    series = st.get("recent_observations", [])
    latest = _station_latest_obs(st)
    values = [
        p["value"]
        for p in series
        if isinstance(p.get("value"), (int, float)) and p["value"] >= 0
    ]

    trend = _trend_direction(values, 0.05)

    surge = None
    if len(values) >= 6:
        median = sorted(values)[len(values) // 2]
        if median > 0 and latest and isinstance(latest.get("value"), (int, float)):
            surge = round(latest["value"] / median, 2)

    condition = "NORMAL"
    basis = []
    if surge is not None and trend:
        if surge >= 2 and trend["direction"] == "RISING":
            condition = "ALERT"
            basis.append(
                f"discharge {surge}x the station's recent median and rising"
            )
        elif surge >= 1.5:
            condition = "WATCH"
            basis.append(f"discharge {surge}x the station's recent median")
        else:
            basis.append(f"discharge {surge}x the station's recent median")
    elif latest:
        basis.append(
            f"latest discharge {latest.get('value')} {latest.get('unit')} "
            "(insufficient series for trend/surge)"
        )

    return {
        "available": True,
        "station": station_result.get("station"),
        "distance_km": station_result.get("distance_km"),
        "latest_observation": latest,
        "trend": (
            {
                "direction": trend["direction"],
                "change_percent": trend["change_percent"],
                "basis": "mean of freshest 3 observations vs previous 3",
            }
            if trend
            else None
        ),
        "discharge_surge_vs_recent_median": surge,
        "value_type": "REAL OBSERVATION",
        "freshness": _freshness_for(st),
        "condition_contribution": {"condition": condition, "basis": basis},
        "note": (
            "Registry carries CWC discharge (m3/s), not gauge level + danger "
            "level, so no absolute flood-level claim is made for India-wide "
            "stations."
        ),
    }


def current_condition(latitude, longitude):
    rainfall_result, _ = nearest_india_station(
        "rainfall", latitude, longitude, RAINFALL_MAX_DISTANCE_KM
    )
    river_result, _ = nearest_india_station(
        "river", latitude, longitude, RIVER_MAX_DISTANCE_KM
    )
    rain_p = _rainfall_present(rainfall_result)
    river_p = _river_present(river_result)

    rank = {"NORMAL": 0, "WATCH": 1, "ALERT": 2}
    status = "UNAVAILABLE"
    basis = []
    for part in (rain_p, river_p):
        if part.get("available") and part.get("condition_contribution"):
            basis.extend(part["condition_contribution"]["basis"])
            contributed = part["condition_contribution"]["condition"]
            if rank.get(contributed, 0) > rank.get(status, -1):
                status = contributed
    if status == "UNAVAILABLE" and (rain_p.get("available") or river_p.get("available")):
        status = "NORMAL"

    # Structured reasons ("Why this status?") — real evidence only, mirrors
    # location_service.js exactly.
    reasons = []
    if rain_p.get("available"):
        trend = rain_p.get("trend") or {}
        if trend.get("direction") == "RISING":
            pct = trend.get("change_percent")
            reasons.append(
                "Rainfall increased in the recent observation window"
                + (f" (+{pct}% vs previous window)" if pct is not None else "")
            )
        if isinstance(rain_p.get("accumulation_24h_mm"), (int, float)):
            reasons.append(
                f"24h rainfall accumulation {rain_p['accumulation_24h_mm']} mm "
                f"at {rain_p['station']['station']}"
                + (
                    f" ({rain_p['distance_km']} km away)"
                    if rain_p.get("distance_km") is not None
                    else " (nearest)"
                )
            )
        elif rain_p.get("latest_observation", {}).get("value") is not None:
            reasons.append(
                f"Latest hourly rainfall {rain_p['latest_observation']['value']} mm "
                f"at {rain_p['station']['station']} (sparse record — no reliable 24h window)"
            )
    if river_p.get("available"):
        trend = river_p.get("trend") or {}
        if trend.get("direction") == "RISING":
            pct = trend.get("change_percent")
            reasons.append(
                f"River discharge is rising at {river_p['station']['station']}"
                + (f" (+{pct}%)" if pct is not None else "")
            )
        if isinstance(
            river_p.get("discharge_surge_vs_recent_median"), (int, float)
        ):
            reasons.append(
                f"Discharge is {river_p['discharge_surge_vs_recent_median']}× "
                "the station's own recent median"
            )
    if not reasons:
        reasons.append("No sufficient observational evidence available for this location.")

    quality_rank = {"UNAVAILABLE": 0, "ARCHIVED": 1, "STALE": 2, "RECENT": 3, "FRESH": 4}
    qualities = [
        p["freshness"]["quality"]
        for p in (rain_p, river_p)
        if p.get("available") and p.get("freshness", {}).get("quality")
    ]
    data_quality = (
        min(qualities, key=lambda q: quality_rank.get(q, 0))
        if qualities
        else "UNAVAILABLE"
    )

    return {
        "status": (
            "success"
            if (rain_p.get("available") or river_p.get("available"))
            else "no_data_for_location"
        ),
        "location": {"latitude": latitude, "longitude": longitude},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "CWC NWDP telemetry datasets (real, historical) via FloodWatch registry",
        "present_condition": {
            "status": status,
            "label": "FloodWatch Analytical Status",
            "analytical": True,
            "rule_note": (
                "FloodWatch Analytical Status — an analytical indicator based "
                "on available observations and documented rule-based "
                "thresholds (IMD rainfall classes, station-relative discharge "
                "surge). It is NOT an official government warning, NOT "
                "machine learning, NOT a forecast. FLOODING status is "
                "reserved for observed flood evidence."
            ),
            "basis": basis,
            "reasons": reasons,
        },
        "data_quality": data_quality,
        "rainfall": rain_p,
        "river": river_p,
        "value_types": {
            "rainfall": "REAL OBSERVATION (CWC telemetry, historical dataset)",
            "river": "REAL OBSERVATION (CWC telemetry, historical dataset)",
        },
        "data_notice": (
            "Observations come from the project's real CWC datasets — the "
            "newest records available, not guaranteed live readings."
        ),
    }


# ------------------------------------------------------------
# FORECAST COVERAGE — single honesty gate shared with the UI.
# ------------------------------------------------------------

CALIBRATION_RADIUS_KM = 150


def forecast_coverage(latitude, longitude):
    naraj_def = STATION_DEFS.get("naraj")
    if not naraj_def:
        return {
            "available": False,
            "model": {
                "name": "FloodWatch Future Flood Forecast",
                "algorithm": "Random Forest (71 features) + statistical ensemble",
                "horizons": ["6h", "12h", "24h"],
            },
            "calibration": "Naraj/Cuttack study region, Odisha (Mahanadi basin)",
            "calibration_center": None,
            "calibration_radius_km": CALIBRATION_RADIUS_KM,
            "distance_to_calibrated_center_km": None,
            "message": (
                "AI forecast unavailable for this location with the current "
                "calibrated model (trained for the Naraj/Cuttack study region "
                "only)."
            ),
        }
    km = haversine_km(
        latitude, longitude, naraj_def["latitude"], naraj_def["longitude"]
    )
    available = km <= CALIBRATION_RADIUS_KM
    return {
        "available": available,
        "model": {
            "name": "FloodWatch Future Flood Forecast",
            "algorithm": "Random Forest (71 features) + statistical ensemble",
            "horizons": ["6h", "12h", "24h"],
        },
        "calibration": "Naraj/Cuttack study region, Odisha (Mahanadi basin)",
        "calibration_center": {
            "latitude": naraj_def["latitude"],
            "longitude": naraj_def["longitude"],
            "station": "Naraj",
        },
        "calibration_radius_km": CALIBRATION_RADIUS_KM,
        "distance_to_calibrated_center_km": round(km, 1),
        "message": (
            "Selected location is inside the calibrated study region."
            if available
            else "AI forecast unavailable for this location with the current "
            "calibrated model (trained for the Naraj/Cuttack study region "
            "only)."
        ),
    }


def india_registry_meta():
    if not INDIA_REGISTRY:
        return None
    return {
        "generated_at": INDIA_REGISTRY.get("generated_at"),
        "source": INDIA_REGISTRY.get("source"),
        "counts": INDIA_REGISTRY.get("counts"),
        "states": INDIA_REGISTRY.get("states"),
    }


def india_registry_response(params):
    """India-wide station explorer: q/type/state filters + optional radius
    search around a coordinate (distance from the selected location)."""
    if not INDIA_REGISTRY:
        return {
            "status": "unavailable",
            "error": "India registry missing — run scripts/build_india_registry.py",
            "stations": [],
        }
    q = (params.get("q", [""])[0] or "").strip().lower()
    kind = (params.get("type", ["all"])[0] or "all").lower()
    state = (params.get("state", ["all"])[0] or "all")
    limit = min(int(params.get("limit", ["2000"])[0] or 2000), 2000)

    lat = lon = None
    try:
        if "latitude" in params and "longitude" in params:
            lat = float(params["latitude"][0])
            lon = float(params["longitude"][0])
    except (KeyError, ValueError, TypeError):
        lat = lon = None

    out = []
    for s in _registry_stations():
        if kind not in ("all", "") and s.get("kind") != kind:
            continue
        if state not in ("all", "") and s.get("state") != state:
            continue
        if q:
            hay = " ".join(
                str(s.get(k, ""))
                for k in ("station", "river", "basin", "state", "district")
            ).lower()
            if q not in hay:
                continue
        row = dict(s)
        row["has_observation"] = bool(s.get("latest_observation"))
        if lat is not None and lon is not None:
            row["distance_km"] = round(
                haversine_km(lat, lon, s["latitude"], s["longitude"]), 2
            )
        out.append(row)

    if lat is not None and lon is not None:
        out.sort(key=lambda s: s["distance_km"])

    return {
        "status": "success",
        "count": len(out),
        "filtered_count": len(out),
        "registry_meta": india_registry_meta(),
        "stations": out[:limit],
    }

# Warm up the predictor at startup so the first request is fast.
PREDICTOR.load()
if PREDICTOR.loaded:
    total_daily = sum(
        st["calibration"]["daily_records"]
        for st in PREDICTOR.stations.values()
    )
    total_hourly = sum(
        st["calibration"]["hourly_records"]
        for st in PREDICTOR.stations.values()
    )
    print(
        "Prediction engine ready ("
        f"{len(PREDICTOR.stations)} stations: "
        f"{total_daily} daily + {total_hourly} hourly verified records)."
    )
else:
    print(f"PREDICTION ENGINE FAILED TO LOAD: {PREDICTOR.load_error}")


# ============================================================
# STATIC FILE SERVING
# ============================================================

def serve_static(handler, path):
    rel = path
    if rel == "/" or rel == "":
        rel = "/index.html"
    full = (DASHBOARD_DIR / rel.lstrip("/")).resolve()
    try:
        full.relative_to(DASHBOARD_DIR)
    except ValueError:
        handler.send_error(403)
        return

    if not full.is_file():
        handler.send_error(404, f"Not found: {rel}")
        return

    mime = MIME_TYPES.get(full.suffix.lower(), "application/octet-stream")
    try:
        body = full.read_bytes()
    except OSError:
        handler.send_error(404)
        return

    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


# ============================================================
# HTTP HANDLER
# ============================================================

class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # keep the console quiet

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # --------------------------------------------------
        # Static dashboard files first (except /api/*)
        # --------------------------------------------------
        if not path.startswith("/api"):
            if path in ("/", "/index.html", "/research.html") or not path.startswith("/api"):
                serve_static(self, path)
                return

        # --------------------------------------------------
        # API ROUTES
        # --------------------------------------------------

        if path in ("/", "/api", "/api/health"):
            registry_counts = (
                INDIA_REGISTRY.get("counts", {}) if INDIA_REGISTRY else {}
            )
            self.send_json({
                "status": "online",
                "service": "FloodWatch Flood Intelligence API",
                "api_version": "2.2",
                "version": "2.2.0",
                "server_time": datetime.now(timezone.utc).isoformat(),
                "rainfall_dataset": "CWC NWDP 2021-2025 (real, India-wide)",
                "river_dataset": "CWC telemetry 1970-2025 (real, regional)",
                "station_registry": {
                    "loaded": bool(INDIA_REGISTRY),
                    "stations": registry_counts.get("total", 0),
                    "states": registry_counts.get("states", 0),
                    "generated_at": (
                        INDIA_REGISTRY.get("generated_at") if INDIA_REGISTRY else None
                    ),
                },
                "datasets": {
                    "india_cwc_registry": (
                        "available" if INDIA_REGISTRY else "unavailable"
                    ),
                    "study_region_records": "available",
                },
                "rainfall_stations": registry_counts.get("rainfall_stations", 0),
                "river_stations": registry_counts.get("river_stations", 0),
                "forecast_engine": (
                    "ready" if PREDICTOR.loaded else "unavailable"
                ),
                "forecast_status": (
                    "ready" if PREDICTOR.loaded else "unavailable"
                ),
                "endpoints": [
                    "/",
                    "/api/forecast?reference_time=<ISO time>&station=<naraj|alipingal|nimapara>",
                    "/api/forecast?latitude=..&longitude=.. (coverage-gated)",
                    "/api/current-condition?latitude=..&longitude=..",
                    "/api/forecast/coverage?latitude=..&longitude=..",
                    "/api/stations",
                    "/api/stations/india?q=..&basin=..&state=..",
                    "/api/stations/india_cwc?q=..&type=rainfall|river&state=.."
                    "&latitude=..&longitude=..",
                    "/api/levels/recent?station=..",
                    "/api/model/info",
                    "/api/forecast/backtest",
                    "/api/location?latitude=20.5&longitude=85.95",
                    "/api/health",
                ],
            })
            return

        if path == "/api/forecast":
            reference_time = params.get("reference_time", [None])[0]
            station_key = params.get("station", [None])[0]

            # COVERAGE GATE: optional latitude/longitude. Outside the Naraj/
            # Cuttack calibration radius the trained model is NOT applied —
            # an explicit honest refusal instead of a misattributed value.
            try:
                q_lat = float(params["latitude"][0])
                q_lon = float(params["longitude"][0])
                has_coords = -90 <= q_lat <= 90 and -180 <= q_lon <= 180
            except (KeyError, IndexError, ValueError, TypeError):
                q_lat = q_lon = None
                has_coords = False
            if has_coords:
                coverage = forecast_coverage(q_lat, q_lon)
                if not coverage["available"]:
                    self.send_json({
                        "status": "outside_model_calibration",
                        "forecast": None,
                        "coverage": coverage,
                        "present_condition_note": (
                            "Present-condition observations for this location "
                            "are served by /api/current-condition and remain "
                            "available."
                        ),
                        "warning": (
                            "The trained Random Forest is calibrated on the "
                            "Naraj/Cuttack study region only. No fabricated "
                            "probability is returned for other locations."
                        ),
                    })
                    return

            result = PREDICTOR.predict(reference_time, station_key)
            self.send_json(apply_ml_ensemble(result))
            return

        if path == "/api/current-condition":
            try:
                latitude = float(params["latitude"][0])
                longitude = float(params["longitude"][0])
            except (KeyError, IndexError, ValueError):
                self.send_json({
                    "status": "error",
                    "error": "latitude and longitude are required.",
                }, 400)
                return
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                self.send_json({
                    "status": "error",
                    "error": "Invalid latitude or longitude.",
                }, 400)
                return
            self.send_json(current_condition(latitude, longitude))
            return

        if path == "/api/forecast/coverage":
            try:
                latitude = float(params["latitude"][0])
                longitude = float(params["longitude"][0])
            except (KeyError, IndexError, ValueError):
                self.send_json({
                    "status": "error",
                    "error": "latitude and longitude are required.",
                }, 400)
                return
            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                self.send_json({
                    "status": "error",
                    "error": "Invalid latitude or longitude.",
                }, 400)
                return
            self.send_json({
                "status": "success",
                "coverage": forecast_coverage(latitude, longitude),
            })
            return

        if path == "/api/model/info":
            self.send_json(build_model_info())
            return

        if path == "/api/stations/india":
            self.send_json(india_stations_response(params))
            return

        if path == "/api/levels/recent":
            self.send_json(levels_recent_response(params))
            return

        if path == "/api/stations":
            self.send_json({
                "status": "success",
                "stations": PREDICTOR.station_list(),
            })
            return

        if path == "/api/forecast/backtest":
            self.send_json(PREDICTOR.backtest())
            return

        if path == "/api/location":
            try:
                latitude = float(params["latitude"][0])
                longitude = float(params["longitude"][0])
            except (KeyError, IndexError, ValueError):
                self.send_json({
                    "status": "error",
                    "error": "latitude and longitude are required.",
                }, 400)
                return

            if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
                self.send_json({
                    "status": "error",
                    "error": "Invalid latitude or longitude.",
                }, 400)
                return

            rainfall_result, _rf_status = nearest_india_station(
                "rainfall", latitude, longitude, RAINFALL_MAX_DISTANCE_KM
            )
            river_result, _rv_status = nearest_india_station(
                "river", latitude, longitude, RIVER_MAX_DISTANCE_KM
            )

            # Model-scope honesty: where is location-specific AI forecast
            # legitimately available?
            naraj_def = STATION_DEFS.get("naraj")
            naraj_km = (
                haversine_km(
                    latitude, longitude,
                    naraj_def["latitude"], naraj_def["longitude"],
                )
                if naraj_def
                else None
            )

            self.send_json({
                "status": "success",
                "location": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "rainfall": rainfall_result,
                "river": river_result,
                "model_scope": {
                    "calibrated_region": (
                        "Naraj / Cuttack study region, Odisha (Mahanadi basin)"
                    ),
                    "distance_to_calibrated_center_km": (
                        round(naraj_km, 1) if naraj_km is not None else None
                    ),
                    "location_specific_forecast_available": (
                        naraj_km is not None and naraj_km <= 150
                    ),
                },
                "registry_meta": india_registry_meta(),
                "data_notice": (
                    "All stations and observations come from the project's real "
                    "CWC datasets (rainfall 2021-2025, river discharge "
                    "1970-2025). They are historical records, not guaranteed "
                    "live conditions."
                ),
            })
            return

        if path == "/api/stations/india_cwc":
            self.send_json(india_registry_response(params))
            return

        self.send_json({
            "status": "error",
            "error": "Endpoint not found.",
            "path": path,
        }, 404)


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 70)
    print("FLOODWATCH FLOOD INTELLIGENCE API")
    print("=" * 70)
    print(f"Serving dashboard + API at http://{HOST}:{PORT}")
    print("Press CTRL+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()
