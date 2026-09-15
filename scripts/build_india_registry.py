#!/usr/bin/env python3
"""
FloodWatch — India-wide CWC station registry builder.

Reads the REAL CWC datasets (no synthetic data):

  1. CWC_Rainfall_India_2021_2025/state_wise/*.csv   (telemetry hourly rainfall)
  2. river_discharge/river_discharge/*.csv           (telemetry hourly discharge)

and produces a compact station registry:

  naraj_dashboard/data/india_cwc/stations.json

For every station it records: name, state, district, river, basin,
coordinates, observation count, first/last observation timestamps, and the
LATEST observation (value + time) found in the CSVs. Nothing is invented:
stations that appear in the CSVs are the only stations in the registry.

Usage (from the project root):
    python3 scripts/build_india_registry.py
    python3 scripts/build_india_registry.py --src /path/to/external_dir
    python3 scripts/build_india_registry.py --src ml/data/external --out naraj_dashboard/data/india_cwc/stations.json
"""

import argparse
import csv
import heapq
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Per-station recent-observation series kept in the registry so the API can
# compute honest trends / accumulations for the PRESENT CONDITION panel.
# 72 hourly samples = 3 days of the freshest real observations.
RECENT_SERIES_LEN = 72

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = PROJECT_ROOT / "naraj_dashboard" / "data" / "india_cwc" / "stations.json"

RAINFALL_VALUE_COL = "Telemetry Hourly Rainfall (mm)"
RIVER_VALUE_COL = "Telemetry Hourly River Water Discharge (m3/sec)"

# Candidate source roots (first one that exists wins).
DEFAULT_SRC_CANDIDATES = [
    PROJECT_ROOT / "ml" / "data" / "external",
    PROJECT_ROOT / "naraj_dashboard" / "ml" / "data" / "external",
    Path("/tmp/hf_data"),
]


def parse_ts(raw):
    """CWC timestamps look like 'DD-MM-YYYY HH:MM' or 'DD-MM-YYYY HH:MM:SS'."""
    try:
        parts = str(raw).strip().split()
        if len(parts) < 2:
            return None
        day, month, year = parts[0].split("-")
        hm = parts[1].split(":")
        return datetime(
            int(year), int(month), int(day),
            int(hm[0]), int(hm[1]) if len(hm) > 1 else 0,
            int(hm[2]) if len(hm) > 2 else 0,
        )
    except Exception:
        return None


def clean_num(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a", "-"}:
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return num


def scan_csv(path, value_col, kind):
    """Stream one CSV, returning per-station aggregates (dict keyed by station)."""
    stations = {}
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                name = (row.get("Station") or "").strip()
                lat = clean_num(row.get("Latitude"))
                lon = clean_num(row.get("Longitude"))
                if not name or lat is None or lon is None:
                    continue
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    continue

                key = (name, round(lat, 5), round(lon, 5))
                st = stations.get(key)
                if st is None:
                    st = stations[key] = {
                        "kind": kind,
                        "station": name,
                        "state": (row.get("State") or "").strip(),
                        "district": (row.get("District") or "").strip(),
                        "river": (row.get("River") or "").strip(),
                        "basin": (row.get("Basin") or "").strip(),
                        "latitude": round(lat, 5),
                        "longitude": round(lon, 5),
                        "n_obs": 0,
                        "first_obs": None,
                        "last_obs": None,
                        "latest": None,
                        "_recent": [],  # bounded min-heap of (dt, value)
                        "_first_dt": None,
                        "_last_dt": None,
                        "_latest_dt": None,
                    }

                value = clean_num(row.get(value_col))
                if value is None:
                    continue
                ts_raw = (row.get("Data Acquisition Time") or "").strip()
                dt = parse_ts(ts_raw)
                st["n_obs"] += 1
                if dt is None:
                    continue
                iso = dt.isoformat()
                if st["_first_dt"] is None or dt < st["_first_dt"]:
                    st["_first_dt"] = dt
                    st["first_obs"] = iso
                if st["_last_dt"] is None or dt > st["_last_dt"]:
                    st["_last_dt"] = dt
                    st["last_obs"] = iso
                if st["_latest_dt"] is None or dt > st["_latest_dt"]:
                    st["_latest_dt"] = dt
                    st["latest"] = {"time": iso, "value": value}
                # Bounded recent-series buffer (freshest RECENT_SERIES_LEN obs).
                if len(st["_recent"]) < RECENT_SERIES_LEN:
                    heapq.heappush(st["_recent"], (dt, value))
                elif dt > st["_recent"][0][0]:
                    heapq.heapreplace(st["_recent"], (dt, value))
    except Exception as exc:
        print(f"  ! CSV error {path.name}: {exc}", file=sys.stderr)
    return stations


def fmt_station(st):
    unit = "mm" if st["kind"] == "rainfall" else "m3/s"
    recent = sorted(st["_recent"], key=lambda p: p[0])
    return {
        "kind": st["kind"],
        "station": st["station"],
        "state": st["state"],
        "district": st["district"],
        "river": st["river"],
        "basin": st["basin"],
        "latitude": st["latitude"],
        "longitude": st["longitude"],
        "n_obs": st["n_obs"],
        "first_obs": st["first_obs"],
        "last_obs": st["last_obs"],
        "latest_observation": (
            {"time": st["latest"]["time"], "value": st["latest"]["value"], "unit": unit}
            if st["latest"]
            else None
        ),
        "recent_observations": [
            {"time": dt.isoformat(), "value": value} for dt, value in recent
        ],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        default=None,
        help="Path to the external datasets dir containing "
        "rainfall/CWC_Rainfall_India_2021_2025/state_wise and "
        "river_discharge/river_discharge",
    )
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    if args.src:
        src = Path(args.src)
    else:
        src = next((c for c in DEFAULT_SRC_CANDIDATES if c.exists()), None)
        if src is None:
            print(
                "ERROR: could not find the external datasets. Pass --src pointing "
                "at the folder that contains rainfall/CWC_Rainfall_India_2021_2025 "
                "and river_discharge (on the author machine: "
                "ml/data/external).",
                file=sys.stderr,
            )
            sys.exit(1)

    rainfall_dir = (
        src / "rainfall" / "CWC_Rainfall_India_2021_2025" / "state_wise"
    )
    if not rainfall_dir.exists():
        # flat layout fallback (e.g. a downloads dir with the raw CSVs)
        flat = src / "rainfall"
        rainfall_dir = flat if flat.exists() else rainfall_dir
    river_dir = src / "river_discharge" / "river_discharge"
    if not river_dir.exists():
        flat_river = src / "river_discharge"
        if not flat_river.exists():
            # flat layout fallback: river CSVs directly under src
            flat_river = src
        river_dir = flat_river

    print(f"Source: {src}")
    stations = {}

    rainfall_files = sorted(rainfall_dir.glob("*.csv")) if rainfall_dir.exists() else []
    print(f"Rainfall CSVs: {len(rainfall_files)}")
    for f in rainfall_files:
        for key, st in scan_csv(f, RAINFALL_VALUE_COL, "rainfall").items():
            cur = stations.get(key)
            if cur is None or st["n_obs"] > cur["n_obs"]:
                stations[key] = st

    river_files = sorted(river_dir.glob("*.csv")) if river_dir.exists() else []
    print(f"River-discharge CSVs: {len(river_files)}")
    for f in river_files:
        for key, st in scan_csv(f, RIVER_VALUE_COL, "river").items():
            cur = stations.get(key)
            if cur is None or st["n_obs"] > cur["n_obs"]:
                stations[key] = st

    out_stations = sorted(
        (fmt_station(st) for st in stations.values()),
        key=lambda s: (s["kind"], s["state"], s["station"]),
    )

    rain_n = sum(1 for s in out_stations if s["kind"] == "rainfall")
    river_n = sum(1 for s in out_stations if s["kind"] == "river")
    states = sorted({s["state"] for s in out_stations if s["state"]})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "rainfall": "CWC NWDP telemetry hourly rainfall, 2021-2025 "
            "(CWC_Rainfall_India_2021_2025/state_wise)",
            "river": "CWC NWDP telemetry hourly river water discharge, 1970-2025 "
            "(river_discharge)",
            "hosted": "https://huggingface.co/datasets/bhoomig0630/flood-inundation-upload",
            "note": "Built ONLY from the real CWC CSVs. No stations invented, "
            "no values imputed.",
        },
        "counts": {
            "rainfall_stations": rain_n,
            "river_stations": river_n,
            "total": rain_n + river_n,
            "states": len(states),
        },
        "states": states,
        "stations": out_stations,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    print(
        f"Wrote {out_path}: {rain_n} rainfall + {river_n} river stations "
        f"across {len(states)} states."
    )


if __name__ == "__main__":
    main()
