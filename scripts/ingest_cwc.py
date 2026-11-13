#!/usr/bin/env python3
"""Scheduled CWC ingestion for FloodWatch.

Pulls the newest available CWC observations, merges them into the stores the
dashboard/ML service read, rebuilds the forecast feature frame, and records an
honest freshness report so the API never presents stale data as current.

  python3 scripts/ingest_cwc.py --once
  python3 scripts/ingest_cwc.py --once --levels-csv /path/rwl_manual_hr_cwc.csv
  python3 scripts/ingest_cwc.py --watch --interval-minutes 360

Sources
  --source hf    (default) rainfall from the project's Hugging Face dataset
  --levels-csv   CWC water-level export: local path or http(s) URL
  --rain-csv     CWC hourly rainfall export: local path or http(s) URL

The CWC manual water-level export is NOT part of the Hugging Face dataset, so a
level refresh requires --levels-csv (or a reachable URL) to be supplied. When no
newer level observation exists the run still completes, refreshes rainfall, and
reports the dataset as stale rather than silently reusing old anchor times.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "naraj_dashboard"
CWC_DIR = DASHBOARD / "data" / "cwc"
DATASET_DASHBOARD = DASHBOARD / "data" / "hf" / "forecast_dataset.csv"
STATUS_FILE = CWC_DIR / "ingestion_status.json"
CACHE_DIR = ROOT / ".cache" / "cwc_ingest"
BUILDER = ROOT / "ml" / "src" / "build_forecast_dataset.py"
BUILDER_OUTPUT = ROOT / "ml" / "data" / "forecast" / "forecast_dataset.csv"

HF_BASE = "https://huggingface.co/datasets/bhoomig0630/flood-inundation-upload/resolve/main"
RAIN_HF_PATH = "ml/data/external/rainfall/CWC_Rainfall_India_2021_2025/state_wise/Odisha_2021_2025.csv"
RAIN_LOCAL = ROOT / "ml" / "data" / "external" / "rainfall" / "CWC_Rainfall_India_2021_2025" / "state_wise" / "Odisha_2021_2025.csv"

# Dashboard station key -> CWC station name (matched case-insensitively)
STATIONS = {"naraj": "Naraj", "alipingal": "Alipingal", "nimapara": "Nimapara"}

TIME_FORMATS = (
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%d-%m-%Y",
)


def log(msg: str) -> None:
    print(f"[ingest_cwc] {msg}", flush=True)


def is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def fetch(source: str, label: str, max_age_hours: float | None = None) -> Path:
    """Return a local path for a local path or http(s) URL.

    Remote files are cached and revalidated with ETag/Last-Modified so a
    scheduled run does not re-download a 55 MB rainfall export every time.
    """
    if not is_url(source):
        path = Path(source).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"{label} not found: {path}")
        return path

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / (label + "_" + source.rstrip("/").rsplit("/", 1)[-1])
    meta_path = dest.with_suffix(dest.suffix + ".meta.json")
    meta = {}
    if dest.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            meta = {}

    if dest.exists() and max_age_hours is not None and meta.get("fetched_utc"):
        try:
            fetched = datetime.fromisoformat(meta["fetched_utc"])
            age_h = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0
            if age_h < max_age_hours:
                log(f"{label}: cache is {age_h:.1f}h old (< {max_age_hours:g}h), reusing {dest.name}")
                return dest
        except ValueError:
            pass

    headers = {}
    if dest.exists() and meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if dest.exists() and meta.get("last_modified"):
        headers["If-Modified-Since"] = meta["last_modified"]

    request = urllib.request.Request(source, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=180) as resp:
            if dest.exists() and resp.status == 304:
                log(f"{label}: cached copy is current ({dest.name})")
                return dest
            tmp = dest.with_suffix(dest.suffix + ".part")
            log(f"downloading {label} -> {dest.name}")
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            tmp.replace(dest)
            meta_path.write_text(json.dumps({
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "fetched_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }, indent=1) + "\n", encoding="utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 304 and dest.exists():
            log(f"{label}: cached copy is current ({dest.name})")
            return dest
        raise
    return dest


def open_rows(path: Path):
    """Yield dict rows; tolerate BOM/utf-8/latin-1 encodings."""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            fh = path.open("r", encoding=encoding, newline="")
            reader = csv.DictReader(fh)
            rows = list(reader)
            fh.close()
            return reader.fieldnames or [], rows
        except UnicodeDecodeError as exc:  # pragma: no cover - depends on input
            last_error = exc
    raise RuntimeError(f"could not decode {path.name}: {last_error}")


def find_col(fields, *needles, exclude=()):
    lowered = [(f or "").strip().lower() for f in fields]
    for needle in needles:
        for name, low in zip(fields, lowered):
            if needle in low and not any(bad in low for bad in exclude):
                return name
    return None


def parse_time(value: str):
    text = (value or "").strip()
    if not text:
        return None
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_levels(path: Path):
    """Parse a CWC water-level export into {station_key: [(datetime, level_m)]}."""
    fields, rows = open_rows(path)
    if not fields:
        raise RuntimeError(f"{path.name}: empty CSV")

    station_col = find_col(fields, "station")
    time_col = find_col(fields, "data acquisition time", "observation time", "date time", "timestamp", "date")
    level_col = find_col(fields, "water level", "rl (m)", "level (m)")
    if level_col is None:
        discharge_col = find_col(fields, "discharge")
        if discharge_col:
            raise RuntimeError(
                f"{path.name}: contains river discharge ({discharge_col}), not water level. "
                "The forecast model needs the CWC manual hourly water-level export."
            )
    if not station_col or not time_col or not level_col:
        raise RuntimeError(
            f"{path.name}: could not identify columns "
            f"(station={station_col!r}, time={time_col!r}, level={level_col!r}); "
            f"header was {fields[:6]}"
        )

    wanted = {name.lower(): key for key, name in STATIONS.items()}
    series = {key: [] for key in STATIONS}
    rejected = 0
    for row in rows:
        key = wanted.get((row.get(station_col) or "").strip().lower())
        if key is None:
            continue
        when = parse_time(row.get(time_col, ""))
        raw = (row.get(level_col) or "").strip()
        if when is None or not raw:
            rejected += 1
            continue
        try:
            level = float(raw)
        except ValueError:
            rejected += 1
            continue
        if not (-50.0 <= level <= 500.0):  # CWC sentinels like -8909
            rejected += 1
            continue
        series[key].append((when, level))

    log(f"parsed {path.name}: level column {level_col!r}, rejected rows {rejected}")
    return series


def daily_means(points):
    buckets = {}
    for when, level in points:
        buckets.setdefault(when.date().isoformat(), []).append(level)
    return {day: sum(vals) / len(vals) for day, vals in buckets.items()}


def merge_station_daily(station_key: str, points, dry_run: bool):
    """Append new daily means to data/cwc/<station>_daily_*.json (history preserved)."""
    path = CWC_DIR / f"{station_key}_daily_2021_2025.json"
    if not path.exists():
        return {"file": path.name, "added": 0, "status": "missing_store", "error": f"{path} not found"}

    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    records = doc.get("records") or []
    existing = {str(r.get("date")) for r in records}
    store_latest = max(existing) if existing else None
    if not points:
        return {
            "file": path.name,
            "records_before": len(existing),
            "added": 0,
            "latest_observation": store_latest,
            "status": "no_observations_in_source",
        }

    means = daily_means(points)
    new_days = sorted(day for day in means if day not in existing)
    payload = [{"date": day, "water_level_m": round(means[day], 2)} for day in new_days]

    if payload and not dry_run:
        records.extend(payload)
        records.sort(key=lambda r: str(r.get("date")))
        doc["records"] = records
        # Preserve the store's existing serialization so a merge adds only the
        # new records instead of re-indenting the whole historical file.
        if "\n" in raw.strip():
            text = json.dumps(doc, indent=1)
        else:
            text = json.dumps(doc)
        if raw.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")

    latest = max(existing | set(means)) if (existing or means) else None
    return {
        "file": path.name,
        "records_before": len(existing),
        "added": len(payload),
        "first_added": payload[0]["date"] if payload else None,
        "last_added": payload[-1]["date"] if payload else None,
        "latest_observation": latest,
        "status": "updated" if payload else "already_current",
    }


def stage_rainfall(rain_source: str | None):
    """Place the rainfall CSV where build_forecast_dataset.py expects it."""
    if not rain_source:
        return None, "not provided"
    origin = f"{HF_BASE}/{RAIN_HF_PATH}" if rain_source.lower() == "hf" else rain_source
    local = fetch(origin, "rainfall", max_age_hours=6.0)
    RAIN_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    if local.resolve() != RAIN_LOCAL.resolve():
        shutil.copyfile(local, RAIN_LOCAL)
    return RAIN_LOCAL, origin


def last_timestamp(path: Path):
    """Return the first CSV field of the last row, without reading the file whole."""
    if not path.exists():
        return None
    with open(path, "rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 8192))
        tail = fh.read().decode("utf-8", "replace").strip().splitlines()
    return tail[-1].split(",", 1)[0].strip() if tail else None


def rebuild_dataset() -> dict:
    """Re-run the feature builder and refresh the dashboard's dataset copy."""
    if not BUILDER.exists():
        return {"rebuilt": False, "error": f"builder missing: {BUILDER}"}
    try:  # the builder needs pandas/numpy; fail with guidance instead of a traceback
        import pandas  # noqa: F401
    except ImportError:
        return {
            "rebuilt": False,
            "error": "pandas is not installed for this interpreter",
            "hint": "run with the project venv: .venv/bin/python scripts/ingest_cwc.py",
        }
    log("rebuilding forecast features (ml/src/build_forecast_dataset.py)")
    proc = subprocess.run(
        [sys.executable, str(BUILDER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        return {"rebuilt": False, "error": "builder failed", "detail": tail}
    if not BUILDER_OUTPUT.exists():
        return {"rebuilt": False, "error": f"builder produced no output at {BUILDER_OUTPUT}"}

    builder_lines = BUILDER_OUTPUT.read_text(encoding="utf-8").splitlines()
    if not builder_lines:
        return {"rebuilt": False, "error": "builder output is empty"}
    header, rows_out = builder_lines[0], builder_lines[1:]
    rebuilt_latest = rows_out[-1].split(",", 1)[0] if rows_out else None

    DATASET_DASHBOARD.parent.mkdir(parents=True, exist_ok=True)
    existing_latest = last_timestamp(DATASET_DASHBOARD)
    if existing_latest and rebuilt_latest and rebuilt_latest <= existing_latest:
        return {
            "rebuilt": True,
            "appended": 0,
            "latest_row": existing_latest,
            "note": "rebuilt features hold no rows newer than the served dataset; file left unchanged",
        }

    new_rows = [r for r in rows_out if existing_latest is None or r.split(",", 1)[0] > existing_latest]
    if DATASET_DASHBOARD.exists():
        current = DATASET_DASHBOARD.read_bytes()
        needs_header = not current.strip()
        with open(DATASET_DASHBOARD, "a", encoding="utf-8") as fh:
            if current and not current.endswith(b"\n"):
                fh.write("\n")
            if needs_header:
                fh.write(header + "\n")
            for row in new_rows:
                fh.write(row + "\n")
    else:
        DATASET_DASHBOARD.write_text("\n".join([header] + new_rows) + "\n", encoding="utf-8")

    return {
        "rebuilt": True,
        "appended": len(new_rows),
        "latest_row": last_timestamp(DATASET_DASHBOARD),
        "note": "appended only rows newer than the served dataset (history untouched)",
    }


def run_once(args) -> dict:
    CWC_DIR.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    rain_path, rain_origin = stage_rainfall(args.rain_csv or "hf")

    level_series = {}
    levels_origin = args.levels_csv or None
    if args.levels_csv:
        level_path = fetch(args.levels_csv, "levels")
        level_series = parse_levels(level_path)
    else:
        blockers.append(
            "no water-level source supplied (--levels-csv); the CWC manual hourly "
            "water-level export is not in the Hugging Face dataset"
        )

    stations = {}
    added_total = 0
    latest_seen = None
    for key in STATIONS:
        result = merge_station_daily(key, level_series.get(key, []), args.dry_run)
        stations[key] = result
        added_total += result.get("added", 0)
        if result.get("latest_observation") and (
            latest_seen is None or result["latest_observation"] > latest_seen
        ):
            latest_seen = result["latest_observation"]

    age_days = None
    if latest_seen:
        age_days = round((datetime.now(timezone.utc).date() - datetime.fromisoformat(latest_seen).date()).days, 1)

    stale = age_days is None or age_days > args.stale_after_days
    if stale and latest_seen:
        blockers.append(
            f"newest water-level observation is {latest_seen} ({age_days} days old); "
            "supply a current CWC export via --levels-csv to move the forecast anchor"
        )

    dataset = {"rebuilt": False, "skipped": "no new observations"}
    if args.dry_run:
        dataset = {"rebuilt": False, "skipped": "dry run"}
    elif args.skip_rebuild:
        dataset = {"rebuilt": False, "skipped": "--skip-rebuild"}
    elif added_total > 0 or args.force_rebuild:
        dataset = rebuild_dataset()
    elif stale:
        dataset = {"rebuilt": False, "skipped": "no new observations (anchor unchanged)"}

    status = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"rainfall": rain_origin, "rainfall_staged_to": str(rain_path) if rain_path else None,
                   "water_levels": levels_origin},
        "rainfall_rows": None,
        "stations": stations,
        "observations_added": added_total,
        "latest_observation": latest_seen,
        "age_days": age_days,
        "stale": stale,
        "stale_after_days": args.stale_after_days,
        "dataset": dataset,
        "blockers": blockers,
    }

    if not args.dry_run:
        STATUS_FILE.write_text(json.dumps(status, indent=1) + "\n", encoding="utf-8")

    return status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run one ingestion pass (default)")
    ap.add_argument("--watch", action="store_true", help="run forever on --interval-minutes")
    ap.add_argument("--interval-minutes", type=float, default=360.0, help="watch interval (default 360)")
    ap.add_argument("--levels-csv", help="CWC manual hourly water-level CSV (path or URL)")
    ap.add_argument("--rain-csv", help="CWC hourly rainfall CSV (path or URL); default: HF Odisha")
    ap.add_argument("--dry-run", action="store_true", help="parse and report without writing")
    ap.add_argument("--force-rebuild", action="store_true", help="rebuild features even with no new rows")
    ap.add_argument("--skip-rebuild", action="store_true", help="merge observations only; do not rebuild features")
    ap.add_argument("--stale-after-days", type=float, default=2.0, help="age that flags data as stale")
    args = ap.parse_args()

    if args.watch:
        log(f"watch mode: every {args.interval_minutes:g} min (Ctrl-C to stop)")
        while True:
            try:
                status = run_once(args)
                log(json.dumps({k: status[k] for k in ("latest_observation", "age_days", "stale", "observations_added")}))
            except Exception as exc:  # keep the scheduler alive, surface the error
                log(f"run failed: {exc}")
            sys.stdout.flush()
            time.sleep(max(60.0, args.interval_minutes * 60.0))

    status = run_once(args)
    print(json.dumps(status, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
