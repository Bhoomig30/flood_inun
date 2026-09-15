#!/usr/bin/env python3
"""
FloodWatch — ML serving process (v3, REAL dataset).

Serves the calibrated Random Forests trained on the project's REAL Hugging
Face dataset (bhoomig0630/flood-inundation-upload -> ml/data/forecast/
forecast_dataset.csv, built from CWC 2021-2025 records by
github.com/Bhoomig30/flood_inun ml/src/build_forecast_dataset.py).

Protocol (JSON lines on stdin/stdout, consumed by ml_bridge.js):
    warm-up  -> {"data": {"ready": true, "models_loaded": ["6h","12h","24h"]}}
    request  -> {"id": N, "cmd": "predict", "reference_time": ISO|null}
    response -> {"id": N, "ok": true,
                 "as_of": "...",
                 "horizons": {
                   "6h":  {"probability": 0..1, "source": "rf_hf_v3"},
                   "12h": {...},
                   "24h": {...}}}

Feature pipeline: the HF dataset rows already contain all 71 engineered
features (10-station rainfall aggregates, 3-station water levels with
lags/changes/rollings, cyclic time encodings). Serving therefore looks up
the row matching `reference_time` (or the latest row when null) and feeds
its features to the models — exactly the features the models were trained
on. No synthetic inputs are ever generated; a missing timestamp is an
error, not an invention.
"""

import sys
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATASET = HERE / "data" / "hf" / "forecast_dataset.csv"
MODEL_DIR = HERE / "data" / "ml_models"
HORIZONS = [6, 12, 24]
MODEL_VERSION = "rf_hf_v3"


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def load_models():
    bundles = {}
    for h in HORIZONS:
        p = MODEL_DIR / f"hf_forecast_{h}h.pkl"
        if not p.exists():
            raise FileNotFoundError(f"missing model bundle: {p.name} (run ml_train.py)")
        bundles[h] = joblib.load(p)
    return bundles


def load_dataset():
    if not DATASET.exists():
        raise FileNotFoundError(
            f"{DATASET} not found. Download the REAL dataset from "
            "bhoomig0630/flood-inundation-upload (no synthetic substitute)."
        )
    df = pd.read_csv(DATASET, parse_dates=["timestamp"]).sort_values("timestamp")
    df = df.reset_index(drop=True)
    return df


BUNDLES = None
DF = None
FEATURES = None


def predict(reference_time):
    global BUNDLES, DF, FEATURES
    if reference_time is None or str(reference_time).strip().lower() in ("null", "none", ""):
        row = DF.iloc[-1]
        as_of = str(row["timestamp"])
    else:
        ts = pd.Timestamp(str(reference_time))
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        idx = DF.index[DF["timestamp"] == ts]
        if len(idx) == 0:
            return {
                "ok": False,
                "error": f"reference_time {ts} outside real dataset range "
                         f"[{DF.timestamp.iloc[0]} .. {DF.timestamp.iloc[-1]}]",
                "hint": "The real CWC dataset ends 2025-12-30 23:00; the latest "
                        "available observation is used for live forecasts.",
            }
        row = DF.iloc[idx[-1]]
        as_of = str(row["timestamp"])

    # keep column names (the imputer was fitted on a DataFrame)
    x = row[FEATURES].to_frame().T
    out = {}
    for h in HORIZONS:
        b = BUNDLES[h]
        xi = b["imputer"].transform(x)
        p = float(b["model"].predict_proba(xi)[0, 1])
        out[f"{h}h"] = {"probability": round(p, 4), "source": MODEL_VERSION}
    return {"ok": True, "as_of": as_of, "horizons": out}


def main_serve():
    global BUNDLES, DF, FEATURES
    try:
        BUNDLES = load_models()
        DF = load_dataset()
        FEATURES = BUNDLES[HORIZONS[0]]["features"]
        missing = [c for c in FEATURES if c not in DF.columns]
        if missing:
            raise RuntimeError(f"dataset missing feature columns: {missing[:5]}")
        emit({
            "data": {
                "ready": True,
                "models_loaded": [f"{h}h" for h in HORIZONS],
                "model_version": MODEL_VERSION,
                "dataset_rows": int(len(DF)),
                "dataset_end": str(DF.timestamp.iloc[-1]),
            }
        })
    except Exception as exc:  # startup failure -> bridge reports ML disabled
        emit({"data": {"ready": False, "error": str(exc)}})
        sys.stderr.write(f"[ml_serve] startup failed: {exc}\n")
        return

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("cmd") != "predict":
            emit({"id": msg.get("id"), "ok": False, "error": "unknown cmd"})
            continue
        try:
            result = predict(msg.get("reference_time"))
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        result["id"] = msg.get("id")
        emit(result)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        main_serve()
    else:
        # one-shot CLI debug mode: ml_serve.py [reference_time]
        BUNDLES = load_models()
        DF = load_dataset()
        FEATURES = BUNDLES[HORIZONS[0]]["features"]
        ref = sys.argv[1] if len(sys.argv) > 1 else None
        print(json.dumps(predict(ref), indent=2))
