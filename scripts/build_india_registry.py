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
DEFAULT_FLAG_REPORT = PROJECT_ROOT / "docs" / "REGISTRY_COORDINATE_FLAGS.md"

# Coarse per-state envelopes (lat_min, lat_max, lon_min, lon_max). These are
# deliberately generous operational boxes, NOT political boundaries, so that a
# real station near a state edge is not flagged. They are only used to catch
# coordinates that cannot belong to the recorded state at all.
STATE_BBOX = {
    "Andhra Pradesh": (12.3, 20.1, 76.3, 85.5),
    "Arunachal Pradesh": (26.4, 29.6, 91.3, 97.6),
    "Assam": (23.8, 28.1, 89.4, 96.2),
    "Bihar": (24.1, 27.7, 83.1, 88.5),
    "Chhattisgarh": (17.6, 24.3, 80.1, 84.6),
    "Dadra And Nagar Haveli": (19.9, 20.6, 72.7, 73.6),
    "Delhi": (28.2, 29.0, 76.7, 77.5),
    "Gujarat": (19.9, 24.9, 67.9, 74.7),
    "Haryana": (27.4, 31.1, 74.3, 77.8),
    "Himachal Pradesh": (30.2, 33.4, 75.4, 79.2),
    "Jammu & Kashmir": (31.5, 35.5, 73.0, 80.5),
    "Jharkhand": (21.8, 25.5, 83.2, 88.1),
    "Karnataka": (11.4, 18.6, 73.9, 78.7),
    "Kerala": (8.1, 13.0, 74.7, 77.6),
    "Ladakh": (32.0, 36.1, 75.9, 80.6),
    "Madhya Pradesh": (20.9, 27.0, 73.9, 82.9),
    "Maharashtra": (15.5, 22.2, 72.5, 81.0),
    "Manipur": (23.7, 25.8, 92.9, 94.9),
    "Nagaland": (25.1, 27.1, 93.2, 95.4),
    "Odisha": (17.7, 22.7, 81.2, 87.6),
    "Rajasthan": (22.9, 30.3, 69.4, 78.4),
    "Sikkim": (26.9, 28.3, 87.9, 89.0),
    "Tamil Nadu": (7.9, 13.7, 76.1, 80.5),
    "Telangana": (15.7, 20.0, 77.0, 81.4),
    "Tripura": (22.8, 24.7, 91.0, 92.5),
    "Uttar Pradesh": (23.7, 30.6, 76.9, 84.8),
    "Uttarakhand": (28.6, 31.6, 77.4, 81.2),
    "West Bengal": (21.4, 27.4, 85.7, 90.0),
}

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


def coordinate_flag(state, lat, lon):
    """Return a data-quality flag when coordinates cannot be in the state."""
    box = STATE_BBOX.get((state or "").strip())
    if box is None or lat is None or lon is None:
        return None
    lat_min, lat_max, lon_min, lon_max = box
    reasons = []
    if not (lat_min <= lat <= lat_max):
        reasons.append(f"latitude {lat} outside {lat_min}-{lat_max}")
    if not (lon_min <= lon <= lon_max):
        reasons.append(f"longitude {lon} outside {lon_min}-{lon_max}")
    if not reasons:
        return None
    return {
        "coordinate_state_mismatch": True,
        "note": "location in source data looks inconsistent with the recorded state",
        "state_bbox": [lat_min, lat_max, lon_min, lon_max],
        "detail": "; ".join(reasons),
    }


def apply_coordinate_flags(rows):
    """Set/clear data_quality.coordinate flags in place; return flagged rows."""
    flagged = []
    for s in rows:
        flag = coordinate_flag(s.get("state"), s.get("latitude"), s.get("longitude"))
        if flag:
            s["data_quality"] = flag
            flagged.append(s)
        else:
            s.pop("data_quality", None)
    return flagged


def write_flag_report(path, flagged, total):
    lines = [
        "# Registry coordinate flags",
        "",
        "Generated by `scripts/build_india_registry.py` from the committed registry "
        "(generated 2026-09-14). The check compares each station's recorded "
        "coordinates with a **coarse per-state bounding box**; it flags only "
        "coordinates that cannot belong to the recorded state. It is a data-quality "
        "check, not a correction: no coordinate has been changed.",
        "",
        f"Stations checked: **{total}** · flagged: **{len(flagged)}**",
        "",
    ]
    if flagged:
        lines += [
            "| Station | State | Recorded latitude | Recorded longitude | Why flagged |",
            "| --- | --- | --- | --- | --- |",
        ]
        for s in flagged:
            dq = s.get("data_quality") or {}
            lines.append(
                "| {station} | {state} | {lat} | {lon} | outside the state envelope: {detail} |".format(
                    station=s.get("station"),
                    state=s.get("state"),
                    lat=s.get("latitude"),
                    lon=s.get("longitude"),
                    detail=dq.get("detail", ""),
                )
            )
        lines += [
            "",
            "These stations are kept in the registry and shown in the UI with a "
            "warning; the map is not recentred on them and their coordinates are "
            "not corrected from memory. Correct them only against an authoritative "
            "gauge list.",
        ]
    else:
        lines.append("No station coordinates fall outside their state envelope.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")


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
    ap.add_argument(
        "--report",
        default=str(DEFAULT_FLAG_REPORT),
        help="Markdown report of stations whose coordinates do not fit their state",
    )
    ap.add_argument(
        "--flag-only",
        action="store_true",
        help="Re-check the existing registry (no source CSVs needed) and rewrite "
        "it with data-quality flags plus the report",
    )
    args = ap.parse_args()

    if args.flag_only:
        out_path = Path(args.out)
        payload = json.loads(out_path.read_text("utf-8"))
        rows = payload.get("stations") or []
        flagged = apply_coordinate_flags(rows)
        payload.setdefault("data_quality", {})["coordinate_check"] = {
            "method": "coarse per-state bounding box",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "stations_checked": len(rows),
            "flagged": len(flagged),
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
        write_flag_report(Path(args.report), flagged, len(rows))
        print(
            f"Re-checked {len(rows)} stations: {len(flagged)} flagged "
            f"(report: {args.report})."
        )
        return

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
    flagged = apply_coordinate_flags(out_stations)

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
        "data_quality": {
            "coordinate_check": {
                "method": "coarse per-state bounding box",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "stations_checked": len(out_stations),
                "flagged": len(flagged),
            }
        },
        "stations": out_stations,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), "utf-8")
    write_flag_report(Path(args.report), flagged, len(out_stations))
    print(
        f"Wrote {out_path}: {rain_n} rainfall + {river_n} river stations "
        f"across {len(states)} states; {len(flagged)} coordinate flags."
    )


if __name__ == "__main__":
    main()
