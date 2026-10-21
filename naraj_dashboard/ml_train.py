#!/usr/bin/env python3
"""
FloodWatch v3 — train calibrated Random Forest flood classifiers from the
REAL project dataset hosted on Hugging Face.

Data source (no synthetic data):
    bhoomig0630/flood-inundation-upload  ->  ml/data/forecast/forecast_dataset.csv
    Built by this project's own pipeline (github.com/Bhoomig30/flood_inun,
    ml/src/build_forecast_dataset.py) from CWC records:
      - 10 CWC rain-gauge stations (2021-2025), Odisha
      - 3 CWC water-level stations: Naraj, Alipingal, Nimapara
    Targets: flood_next_{6,12,24}h = Naraj level > 24.28 m (95th percentile)
    within the next horizon. 22 real flood events across 5 monsoons.

Training conventions follow the project's ml/src/train_flood_forecast.py:
    - strict chronological 70/15/15 split (no shuffling)
    - RandomForestClassifier(300, depth 18, min_samples_leaf 3, balanced)
    - median imputer
Plus v3 upgrades:
    - sigmoid (Platt) probability calibration fitted on the validation slice
    - TimeSeriesSplit CV inside the training window for stability
    - honest skill reporting: Brier / AUC / PR-AUC / recall-precision /
      false-alarm rate — accuracy deliberately not headline-reported
Outputs:
    data/ml_models/hf_forecast_{6,12,24}h.pkl   (model+imputer+calibrator bundle)
    data/ml_models/hf_forecast_metadata.json    (provenance + skill)
"""

from pathlib import Path
import json
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    brier_score_loss,
    roc_auc_score,
    average_precision_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
)

HERE = Path(__file__).resolve().parent
DATASET = HERE / "data" / "hf" / "forecast_dataset.csv"
MODEL_DIR = HERE / "data" / "ml_models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)

HF_ID = "bhoomig0630/flood-inundation-upload"
GH_REPO = "Bhoomig30/flood_inun"

HORIZONS = [6, 12, 24]
RANDOM_STATE = 42
MODEL_PARAMS = {
    "n_estimators": 300,
    "max_depth": 18,
    "min_samples_leaf": 3,
    "class_weight": "balanced",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}
HIGH_RISK_P = 0.60  # dashboard "HIGH" band threshold for hit-rate reporting


def fail(msg):
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# ============================================================
# LOAD REAL DATASET (no synthetic fallback, by design)
# ============================================================

print("=" * 78)
print("FLOODWATCH v3 — REAL-DATA TRAINING (Hugging Face dataset)")
print(f"  dataset : {HF_ID}")
print(f"  pipeline: github.com/{GH_REPO} ml/src/build_forecast_dataset.py")
print("=" * 78)

if not DATASET.exists():
    fail(
        f"Real dataset not found at {DATASET}.\n"
        "Download it (do NOT substitute synthetic data):\n"
        f"  curl -L -o data/hf/forecast_dataset.csv "
        f"'https://huggingface.co/datasets/{HF_ID}/resolve/main/ml/data/forecast/forecast_dataset.csv'"
    )

df = pd.read_csv(DATASET, parse_dates=["timestamp"])
df = df.sort_values("timestamp").reset_index(drop=True)

TARGETS = [f"flood_next_{h}h" for h in HORIZONS]
FEATURES = [c for c in df.columns if c not in set(TARGETS + ["timestamp", "historical_flood"])]

for c in FEATURES:
    df[c] = pd.to_numeric(df[c], errors="coerce")

print(f"\nRows: {len(df):,}   Features: {len(FEATURES)}   Targets: {TARGETS}")
print(f"Time: {df.timestamp.min()}  ->  {df.timestamp.max()}")
if df[FEATURES].isna().any().any():
    print(f"NaN cells: {int(df[FEATURES].isna().sum().sum())} (imputer handles)")


def count_events(mask):
    m = mask.astype(bool)
    if m.sum() == 0:
        return 0
    return int((m != m.shift(fill_value=False)).sum())


# ============================================================
# CHRONOLOGICAL 70/15/15 SPLIT (project convention — no shuffle)
# ============================================================

n = len(df)
train_end = int(n * 0.70)
val_end = int(n * 0.85)

train_df = df.iloc[:train_end].copy()
val_df = df.iloc[train_end:val_end].copy()
test_df = df.iloc[val_end:].copy()

print("\n" + "=" * 78)
print("CHRONOLOGICAL SPLIT (no shuffling — prevents future leakage)")
print("=" * 78)
SPLIT_PERIODS = {}
for name, part in (("train", train_df), ("val", val_df), ("test", test_df)):
    ev = count_events(part["flood_next_6h"])
    SPLIT_PERIODS[name] = f"{part.timestamp.min()} -> {part.timestamp.max()}"
    print(
        f"  {name:5s}: {len(part):6,} rows  {part.timestamp.min()} -> {part.timestamp.max()}"
        f"   flood_next_6h events: {ev}"
    )


# ============================================================
# TRAIN EACH HORIZON
# ============================================================

metadata = {
    "version": 3,
    "project": "FloodWatch",
    "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
    "model_type": "RandomForestClassifier + sigmoid calibration",
    "task": "future flood forecasting (probability that Naraj exceeds danger level)",
    "data_source": {
        "huggingface_dataset": HF_ID,
        "huggingface_file": "ml/data/forecast/forecast_dataset.csv",
        "github_repo": f"https://github.com/{GH_REPO}",
        "build_script": "ml/src/build_forecast_dataset.py",
        "raw_inputs": "CWC India 2021-2025: 10 rain gauges + Naraj/Alipingal/Nimapara water levels",
        "synthetic_data": False,
    },
    "dataset": {
        "rows": int(n),
        "features": len(FEATURES),
        "start": str(df.timestamp.min()),
        "end": str(df.timestamp.max()),
        "flood_threshold_m": 24.28,
        "flood_threshold_rule": "Naraj 95th percentile of 2021-2025 hourly record",
    },
    "features": FEATURES,
    "split": {
        "method": "chronological",
        "train": 0.70,
        "validation": 0.15,
        "test": 0.15,
        "periods": SPLIT_PERIODS,
    },
    "models": {},
}


def skill_block(y, p):
    """Honest skill metrics at operating point 0.5 + probabilistic scores."""
    pred = (p >= 0.5).astype(int)
    y = y.astype(int)
    out = {
        "rows": int(len(y)),
        "positives": int(y.sum()),
        "brier": round(float(brier_score_loss(y, p)), 4),
        "mean_predicted_p": round(float(p.mean()), 4),
    }
    if y.nunique() == 2:
        out["roc_auc"] = round(float(roc_auc_score(y, p)), 4)
        out["pr_auc"] = round(float(average_precision_score(y, p)), 4)
    if pred.sum() > 0:
        out["precision"] = round(float(precision_score(y, pred, zero_division=0)), 4)
        out["f1"] = round(float(f1_score(y, pred, zero_division=0)), 4)
    else:
        out["precision"] = None
        out["f1"] = None
    out["recall"] = round(float(recall_score(y, pred, zero_division=0)), 4)
    # dashboard band rates
    out["hit_rate_at_HIGH"] = (
        round(float(p[y == 1].mean()), 4) if (y == 1).any() else None
    )
    fa = float(p[y == 0].mean())
    out["false_alarm_mean_p_on_safe_hours"] = round(fa, 4)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel().tolist()
    out["confusion_at_0.5"] = {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
    return out


for horizon in HORIZONS:
    target = f"flood_next_{horizon}h"
    print("\n" + "=" * 78)
    print(f"HORIZON {horizon}h  (target {target})")
    print("=" * 78)

    X_tr, y_tr = train_df[FEATURES], train_df[target].astype(int)
    X_va, y_va = val_df[FEATURES], val_df[target].astype(int)
    X_te, y_te = test_df[FEATURES], test_df[target].astype(int)
    print(f"  positives  train={y_tr.sum()}  val={y_va.sum()}  test={y_te.sum()}")

    imputer = SimpleImputer(strategy="median")
    X_tr_i = imputer.fit_transform(X_tr)

    base = RandomForestClassifier(**MODEL_PARAMS)
    print("  fitting RandomForest ...")
    base.fit(X_tr_i, y_tr)

    # --- expanding-window CV inside the TRAIN window only (stability check)
    cv_briers = []
    tscv = TimeSeriesSplit(n_splits=3)
    Xall = df[FEATURES].iloc[:train_end]
    yall = df[target].iloc[:train_end].astype(int)
    for k, (a, b) in enumerate(tscv.split(Xall), 1):
        m = RandomForestClassifier(**MODEL_PARAMS)
        imp = SimpleImputer(strategy="median")
        Xa = imp.fit_transform(Xall.iloc[a])
        m.fit(Xa, yall.iloc[a])
        p = m.predict_proba(imp.transform(Xall.iloc[b]))[:, 1]
        cv_briers.append(round(float(brier_score_loss(yall.iloc[b], p)), 4))
    print(f"  train-window CV Brier folds: {cv_briers}")

    # --- probability calibration fitted on the VALIDATION slice
    print("  fitting sigmoid calibration on validation slice ...")
    calib = CalibratedClassifierCV(base, method="sigmoid", cv="prefit")
    calib.fit(imputer.transform(X_va), y_va)

    p_val = calib.predict_proba(imputer.transform(X_va))[:, 1]
    p_test = calib.predict_proba(imputer.transform(X_te))[:, 1]

    val_skill = skill_block(y_va, p_val)
    test_skill = skill_block(y_te, p_test)

    print("  validation:", json.dumps(val_skill))
    print("  test      :", json.dumps(test_skill))

    importance = (
        pd.DataFrame({"feature": FEATURES, "importance": base.feature_importances_})
        .sort_values("importance", ascending=False)
    )
    print("  top features:", importance.head(8).to_dict(orient="records"))

    bundle_path = MODEL_DIR / f"hf_forecast_{horizon}h.pkl"
    joblib.dump(
        {
            "horizon": horizon,
            "features": FEATURES,
            "imputer": imputer,
            "model": calib,          # calibrated wrapper over the RF
            "trained_at": metadata["trained_at"],
            "data_rows": int(n),
        },
        bundle_path,
    )
    print(f"  saved -> {bundle_path.name}")

    metadata["models"][f"{horizon}h"] = {
        "target": target,
        "bundle": bundle_path.name,
        "cv_brier_folds_train_window": cv_briers,
        "validation": val_skill,
        "test": test_skill,
        "top_features": importance.head(15).to_dict(orient="records"),
    }

# ============================================================
# SAVE METADATA
# ============================================================

meta_path = MODEL_DIR / "hf_forecast_metadata.json"
meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
print("\n" + "=" * 78)
print("DONE — models + metadata saved to", MODEL_DIR)
print(f"metadata: {meta_path.name}")
print("=" * 78)
