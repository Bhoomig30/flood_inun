#!/usr/bin/env python3
"""Persistence baselines for the FloodWatch 6/12/24 h forecast.

The Random Forest's strongest features are Naraj water-level lags, so a fair
question is how much skill it adds over simply persisting the current level
(or a linear rise) and thresholding it. This script scores both baselines on
the SAME chronological holdout that ml_train.py uses (last 15% of rows) and
writes the comparison next to the model metadata.

  python ml/src/baseline_skill.py

Output: naraj_dashboard/data/ml_models/hf_forecast_baseline.json
No model is trained here and no committed artifact is modified.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
DASH = ROOT / "naraj_dashboard"
MODEL_DIR = DASH / "data" / "ml_models"
DATASET = DASH / "data" / "hf" / "forecast_dataset.csv"
META = MODEL_DIR / "hf_forecast_metadata.json"
OUT = MODEL_DIR / "hf_forecast_baseline.json"

HORIZONS = (6, 12, 24)
LEVEL_COL = "naraj_water_level_m"


def skill(y, p):
    """Mirror ml_train.skill_block so the numbers are directly comparable."""
    y = y.astype(int)
    pred = (p >= 0.5).astype(int)
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
    out["recall"] = round(float(recall_score(y, pred, zero_division=0)), 4)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel().tolist()
    out["confusion_at_0.5"] = {"tn": tn, "fp": fp, "fn": fn, "tp": tp}
    return out


def main() -> int:
    if not DATASET.exists():
        raise SystemExit(f"dataset not found: {DATASET}")

    meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    threshold = float((meta.get("dataset") or {}).get("flood_threshold_m", 24.28))
    rule = (meta.get("dataset") or {}).get("flood_threshold_rule", "Naraj 95th percentile")

    df = pd.read_csv(DATASET, parse_dates=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    n = len(df)
    val_end = int(n * 0.85)  # identical to ml_train.py: test = rows[val_end:]
    test = df.iloc[val_end:].copy()

    if LEVEL_COL not in test.columns:
        raise SystemExit(f"{LEVEL_COL} missing from dataset")

    baselines = {
        "persistence_threshold": {
            "definition": f"predict flood if the current {LEVEL_COL} >= {threshold} m (no rise assumed)",
            "test": {},
        },
        "persistence_linear_rise": {
            "definition": f"predict flood if {LEVEL_COL} + its observed {{{{h}}}}h change >= {threshold} m "
            "(linear extrapolation of the recent trend, clipped at no change)",
            "test": {},
        },
    }

    for h in HORIZONS:
        target = f"flood_next_{h}h"
        y = test[target]

        p_flat = (test[LEVEL_COL] >= threshold).astype(float)
        baselines["persistence_threshold"]["test"][f"{h}h"] = skill(y, p_flat)

        change_col = f"naraj_water_level_m_change_{h}h"
        missing = 0
        if change_col in test.columns:
            change = test[change_col]
            missing = int(change.isna().sum())
            change = change.fillna(0.0).clip(lower=0.0)
        else:
            change = pd.Series(0.0, index=test.index)
            missing = int(len(test))
        p_rise = ((test[LEVEL_COL] + change) >= threshold).astype(float)
        block = skill(y, p_rise)
        block["change_feature"] = change_col if change_col in test.columns else None
        block["change_nan_filled_zero"] = missing
        baselines["persistence_linear_rise"]["test"][f"{h}h"] = block

    # RF reference straight from the committed metadata (same split, same rows)
    rf = {}
    for h in HORIZONS:
        entry = ((meta.get("models") or {}).get(f"{h}h") or {}).get("test")
        if entry:
            if entry.get("rows") != len(test):
                raise SystemExit(
                    f"split mismatch for {h}h: metadata rows={entry.get('rows')} vs test rows={len(test)}"
                )
            rf[f"{h}h"] = entry

    comparison = {}
    for h in HORIZONS:
        key = f"{h}h"
        if key not in rf:
            continue
        base_scores = {name: b["test"][key] for name, b in baselines.items() if key in b["test"]}
        best_name, best = max(base_scores.items(), key=lambda kv: (kv[1].get("roc_auc") or 0, kv[1].get("f1") or 0))
        comparison[key] = {
            "best_baseline": best_name,
            "baseline_roc_auc": best.get("roc_auc"),
            "rf_roc_auc": rf[key].get("roc_auc"),
            "roc_auc_gain_over_baseline": round((rf[key].get("roc_auc") or 0) - (best.get("roc_auc") or 0), 4),
            "baseline_brier": best.get("brier"),
            "rf_brier": rf[key].get("brier"),
            "brier_gain_over_baseline": round((best.get("brier") or 0) - (rf[key].get("brier") or 0), 4),
            "baseline_f1": best.get("f1"),
            "rf_f1": rf[key].get("f1"),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": {
            "path": str(DATASET.relative_to(ROOT)),
            "rows": int(n),
            "start": str(df.timestamp.min()),
            "end": str(df.timestamp.max()),
        },
        "split": {
            "method": "chronological (70/15/15, identical to ml_train.py)",
            "test_rows": int(len(test)),
            "test_start": str(test.timestamp.min()),
            "test_end": str(test.timestamp.max()),
        },
        "label": {"threshold_m": threshold, "rule": rule},
        "baselines": baselines,
        "rf_reference": {
            "source": "hf_forecast_metadata.json test block (same split and rows)",
            "test": rf,
        },
        "comparison": comparison,
        "note": "Baselines are deliberately simple rules on the current level and its recent change; "
        "they carry no rainfall or upstream-gauge information.",
    }

    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    print(f"test rows: {len(test)}  ({test.timestamp.min()} -> {test.timestamp.max()})")
    print(f"threshold: {threshold} m  ({rule})\n")
    print(f"{'horizon':8s} {'baseline':24s} {'AUC':>7s} {'Brier':>7s} {'F1':>7s}   {'RF AUC':>7s} {'gain':>7s}")
    for h in HORIZONS:
        key = f"{h}h"
        for name, block in baselines.items():
            t = block["test"][key]
            gain = comparison.get(key, {}).get("roc_auc_gain_over_baseline") if name == comparison.get(key, {}).get("best_baseline") else ""
            print(
                f"{key:8s} {name:24s} {t.get('roc_auc', float('nan')):7.4f} {t['brier']:7.4f} "
                f"{t.get('f1', float('nan')):7.4f}   {rf.get(key, {}).get('roc_auc', float('nan')):7.4f} {gain!s:>7s}"
            )
    print(f"\nwritten -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
