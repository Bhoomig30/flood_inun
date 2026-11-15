#!/usr/bin/env python3
"""Onset-only skill for the Naraj model (held-out test period).

Onsets are the hard, actionable case: the river is still BELOW the 24.28 m
threshold and the question is whether it will cross within 6/12/24 h. Rows
already above the threshold are excluded, so a persistence rule cannot win
trivially.

Everything is measured with the committed Random Forest bundles (no training).
Model cutoffs and the baseline rule are tuned on the VALIDATION slice only
(2024-07-01 11:00 → 2025-04-01 05:00); the test slice is used for reporting only.

RF cutoff: maximises F2 (recall-weighted) on validation onsets.
Baseline: family of "projected level" rules level + k * recent_rise, selected by
the highest F1 on validation onsets at its natural trigger (projected level at
or above the threshold).

Writes docs/onset_naraj_test_period.json and docs/ONSET_SKILL.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_fscore_support,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "naraj_dashboard"
DATASET = DS / "data" / "hf" / "forecast_dataset.csv"
BASELINE = DS / "data" / "ml_models" / "hf_forecast_baseline.json"
MODEL_DIR = DS / "data" / "ml_models"
OUT_JSON = ROOT / "docs" / "onset_naraj_test_period.json"
OUT_MD = ROOT / "docs" / "ONSET_SKILL.md"

HORIZONS = (6, 12, 24)
RF_GRID = np.round(np.arange(0.001, 0.91, 0.001), 3)


def counting_metrics(score, y, cutoff):
    pred = np.asarray(score) >= cutoff
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, pred, average="binary", zero_division=0
    )
    return {
        "cutoff": round(float(cutoff), 3),
        "alerts": int(pred.sum()),
        "tp": int((pred & (y == 1)).sum()),
        "fp": int((pred & (y == 0)).sum()),
        "fn": int((~pred & (y == 1)).sum()),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
    }


def best_cutoff_f2(score, y, grid):
    best = None
    for c in grid:
        pred = score >= c
        tp = int((pred & (y == 1)).sum())
        fp = int((pred & (y == 0)).sum())
        fn = int((~pred & (y == 1)).sum())
        if tp == 0:
            f2 = 0.0
        else:
            precision = tp / (tp + fp)
            recall = tp / (tp + fn)
            f2 = 5 * precision * recall / (4 * precision + recall)
        key = (f2, c)
        if best is None or key > best[0]:
            best = (key, {**counting_metrics(score, y, c), "f2": round(float(f2), 4)})
    return best[1]


def skill(score, y):
    return {
        "roc_auc": round(float(roc_auc_score(y, score)), 4),
        "pr_auc": round(float(average_precision_score(y, score)), 4),
    }


def baseline_candidates(frame, h):
    """Simple rules from the current level and recent rise, in projected metres."""
    level = frame["naraj_water_level_m"]
    out = {}
    for window in (3, 6, 12, 24):
        change = frame[f"naraj_water_level_m_change_{window}h"]
        for factor, name in ((0.5, "half"), (1.0, "linear"), (2.0, "double")):
            out[f"{name}_rise_{window}h"] = level + factor * (h / window) * change
    return out


def main() -> None:
    meta = json.loads(BASELINE.read_text())
    threshold = float(meta["label"]["threshold_m"])
    test_start = meta["split"]["test_start"]
    test_end = meta["split"]["test_end"]

    df = pd.read_csv(DATASET, parse_dates=["timestamp"])
    n = len(df)
    val = df.iloc[int(n * 0.70) : int(n * 0.85)].reset_index(drop=True)
    test = df.iloc[int(n * 0.85) :].reset_index(drop=True)
    val_period = (str(val.timestamp.iloc[0]), str(val.timestamp.iloc[-1]))

    results = {}
    for h in HORIZONS:
        bundle = joblib.load(MODEL_DIR / f"hf_forecast_{h}h.pkl")
        features = bundle["features"]
        label = f"flood_next_{h}h"

        val_on = val[val["naraj_water_level_m"] < threshold].copy()
        # The test slice's final h rows have no future observations.
        test_on = test.iloc[: len(test) - h]
        test_on = test_on[test_on["naraj_water_level_m"] < threshold].copy()
        y_val = val_on[label].astype(int).to_numpy()
        y_test = test_on[label].astype(int).to_numpy()

        prob_val = bundle["model"].predict_proba(
            bundle["imputer"].transform(val_on[features])
        )[:, 1]
        prob_test = bundle["model"].predict_proba(
            bundle["imputer"].transform(test_on[features])
        )[:, 1]

        rf_cut = best_cutoff_f2(prob_val, y_val, RF_GRID)
        rf_050 = counting_metrics(prob_test, y_test, 0.5)
        rf_tuned = counting_metrics(prob_test, y_test, rf_cut["cutoff"])

        # ---- baseline family, selected on validation onsets -------------------
        val_candidates = baseline_candidates(val_on, h)
        test_candidates = baseline_candidates(test_on, h)
        candidates = []
        for name, score_val in val_candidates.items():
            if score_val.isna().any():
                continue
            margin_val = (score_val - threshold).to_numpy()
            val_natural = counting_metrics(margin_val, y_val, 0.0)
            margin_test = (test_candidates[name] - threshold).to_numpy()
            candidates.append(
                {
                    "name": name,
                    "validation_at_natural_rule": val_natural,
                    "validation_skill": skill(margin_val, y_val),
                    "test_at_natural_rule": counting_metrics(margin_test, y_test, 0.0),
                    "test_skill": skill(margin_test, y_test),
                }
            )
        # Best simple baseline: highest validation F1 at the natural rule;
        # ties broken by validation PR-AUC.
        best = sorted(
            candidates,
            key=lambda c: (
                c["validation_at_natural_rule"]["f1"],
                c["validation_skill"]["pr_auc"],
            ),
            reverse=True,
        )[0]
        base_test = best["test_at_natural_rule"]
        base_skill = best["test_skill"]

        v = {
            "rf_beats_baseline_roc_auc": bool(
                skill(prob_test, y_test)["roc_auc"] > base_skill["roc_auc"]
            ),
            "rf_beats_baseline_pr_auc": bool(
                skill(prob_test, y_test)["pr_auc"] > base_skill["pr_auc"]
            ),
            "rf_beats_baseline_f1": bool(rf_tuned["f1"] > base_test["f1"]),
        }
        v["roc_auc_delta"] = round(
            skill(prob_test, y_test)["roc_auc"] - base_skill["roc_auc"], 4
        )
        v["pr_auc_delta"] = round(
            skill(prob_test, y_test)["pr_auc"] - base_skill["pr_auc"], 4
        )
        v["f1_delta"] = round(rf_tuned["f1"] - base_test["f1"], 4)
        wins = sum(v["rf_beats_baseline_" + m] for m in ("roc_auc", "pr_auc", "f1"))
        v["summary"] = (
            "RF beats the baseline on all three measures"
            if wins == 3
            else f"RF beats the baseline on {wins} of 3 measures"
        )

        results[f"{h}h"] = {
            "onsets": {
                "validation_rows": int(len(val_on)),
                "validation_positives": int(y_val.sum()),
                "test_rows": int(len(test_on)),
                "test_positives": int(y_test.sum()),
                "test_base_rate": round(float(y_test.mean()), 4),
                "validation_median_probability_on_onsets": round(
                    float(np.median(prob_val[y_val == 1])), 4
                ),
                "test_median_probability_on_onsets": round(
                    float(np.median(prob_test[y_test == 1])), 4
                ),
            },
            "rf": {
                "validation_skill": skill(prob_val, y_val),
                "validation_cutoff_f2": rf_cut,
                "test_skill": skill(prob_test, y_test),
                "at_0_5": rf_050,
                "at_tuned_cutoff": rf_tuned,
            },
            "baseline": {
                "selected": best["name"],
                "selection": (
                    "highest F1 on validation onsets at the natural trigger "
                    "(projected level >= threshold)"
                ),
                "validation_skill": best["validation_skill"],
                "validation_at_natural_rule": best["validation_at_natural_rule"],
                "test_skill": base_skill,
                "test_at_natural_rule": base_test,
                "family": candidates,
            },
            "verdict": v,
        }

    payload = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "station": "naraj",
        "definition": (
            "Onset = current level < threshold; positive label = flood_next_*h "
            "(threshold crossed within the following h hours)."
        ),
        "threshold_m": threshold,
        "test_period": {"start": test_start, "end": test_end},
        "validation_period": {"start": val_period[0], "end": val_period[1]},
        "tuning": (
            "RF cutoff maximises F2 on validation onsets; the baseline rule is the "
            "family member with the highest F1 on validation onsets at its natural "
            "trigger. The test slice is never used for tuning."
        ),
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    OUT_MD.write_text(render_markdown(payload))
    print(
        json.dumps(
            {
                h: {
                    "onsets": r["onsets"],
                    "rf_test": r["rf"]["test_skill"],
                    "rf_at_0_5": r["rf"]["at_0_5"],
                    "rf_at_tuned": r["rf"]["at_tuned_cutoff"],
                    "baseline": r["baseline"]["selected"],
                    "baseline_test": r["baseline"]["test_skill"],
                    "baseline_rule": r["baseline"]["test_at_natural_rule"],
                    "verdict": r["verdict"],
                }
                for h, r in results.items()
            },
            indent=2,
        )
    )


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def render_markdown(payload) -> str:
    r = payload["results"]
    tp = payload["test_period"]
    vp = payload["validation_period"]
    lines = [
        "# Onset skill — Naraj, below-threshold hours",
        "",
        f"Onsets only: the current level is **below {payload['threshold_m']:.2f} m** and "
        "the positive label means the level crosses the threshold within the horizon. "
        "Rows already above the threshold (where a persistence rule is trivially right) "
        "are excluded.",
        "",
        f"- Test period: **{tp['start']} → {tp['end']} UTC**.",
        f"- Validation period (tuning only): **{vp['start']} → {vp['end']} UTC**.",
        "- Model: committed `rf_hf_v3` bundles, unchanged; no retraining.",
        "- RF cutoff: maximises F2 (recall-weighted) on validation onsets.",
        "- Baseline: `projected level = level + k × recent rise`, best family member "
        "by F1 on validation onsets, triggered when the projection reaches the "
        "threshold.",
        "",
        "| Horizon | Onset rows (test) | True onsets | RF ROC-AUC | Baseline ROC-AUC | RF PR-AUC | Baseline PR-AUC | RF recall @0.5 | RF precision @0.5 | RF recall @tuned | RF precision @tuned | Baseline alert recall | Baseline alert precision |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for h in ("6h", "12h", "24h"):
        x = r[h]
        rf, b = x["rf"], x["baseline"]
        lines.append(
            f"| {h} | {x['onsets']['test_rows']} | {x['onsets']['test_positives']} | "
            f"{rf['test_skill']['roc_auc']:.4f} | {b['test_skill']['roc_auc']:.4f} | "
            f"{rf['test_skill']['pr_auc']:.4f} | {b['test_skill']['pr_auc']:.4f} | "
            f"{_pct(rf['at_0_5']['recall'])} | {_pct(rf['at_0_5']['precision'])} | "
            f"{_pct(rf['at_tuned_cutoff']['recall'])} | "
            f"{_pct(rf['at_tuned_cutoff']['precision'])} | "
            f"{_pct(b['test_at_natural_rule']['recall'])} | "
            f"{_pct(b['test_at_natural_rule']['precision'])} |"
        )

    lines += ["", "### Chosen operating points (validation only)", ""]
    for h in ("6h", "12h", "24h"):
        x = r[h]
        lines.append(
            f"- **{h}:** RF cutoff {x['rf']['at_tuned_cutoff']['cutoff']:.3f} "
            f"(validation F2 {x['rf']['validation_cutoff_f2']['f2']:.3f}); baseline "
            f"`{x['baseline']['selected']}` triggered at projected level ≥ threshold "
            f"(validation F1 {x['baseline']['validation_at_natural_rule']['f1']:.3f})."
        )

    lines += ["", "### Does the RF beat the baseline on onsets?", ""]
    for h in ("6h", "12h", "24h"):
        x = r[h]
        rf, b, v = x["rf"], x["baseline"], x["verdict"]
        lines.append(
            f"- **{h}:** ROC-AUC {rf['test_skill']['roc_auc']:.4f} vs "
            f"{b['test_skill']['roc_auc']:.4f} ({v['roc_auc_delta']:+.4f}); PR-AUC "
            f"{rf['test_skill']['pr_auc']:.4f} vs {b['test_skill']['pr_auc']:.4f} "
            f"({v['pr_auc_delta']:+.4f}); F1 at the tuned cutoffs "
            f"{rf['at_tuned_cutoff']['f1']:.3f} vs "
            f"{b['test_at_natural_rule']['f1']:.3f} ({v['f1_delta']:+.3f}). "
            f"**{v['summary']}.**"
        )

    lines += [
        "",
        "The validation-tuned RF cutoff does not transfer cleanly: the median "
        "probability on true test onsets is far lower than on validation onsets "
        f"({r['6h']['onsets']['test_median_probability_on_onsets']:.4f} vs "
        f"{r['6h']['onsets']['validation_median_probability_on_onsets']:.4f} at 6 h, "
        f"{r['12h']['onsets']['test_median_probability_on_onsets']:.4f} vs "
        f"{r['12h']['onsets']['validation_median_probability_on_onsets']:.4f} at 12 h, "
        f"{r['24h']['onsets']['test_median_probability_on_onsets']:.4f} vs "
        f"{r['24h']['onsets']['validation_median_probability_on_onsets']:.4f} at 24 h), "
        "so a fixed probability cutoff fires on very few test onsets. The "
        "validation-selected baseline rule also fails to fire correctly on the test "
        "period (no true positives at 6/12/24 h at its natural trigger), which is why "
        "the RF's F1 looks better even though its ranking is not.",
        "",
        "Plainly: **the RF does not beat the best simple baseline on onsets overall.** "
        "The baseline ranks test onsets better on ROC-AUC at every horizon and on "
        "PR-AUC at 12 h and 24 h; the RF is ahead on PR-AUC only at 6 h. Neither "
        "approach is operationally reliable for onset detection in this test period: "
        "RF recall at the default 0.5 cutoff is 0% at every horizon, and at the "
        "validation-tuned cutoffs it is "
        + "/".join(
            f"{_pct(r[h]['rf']['at_tuned_cutoff']['recall'])}" for h in ("6h", "12h", "24h")
        )
        + " (alerts "
        + "/".join(str(r[h]["rf"]["at_tuned_cutoff"]["alerts"]) for h in ("6h", "12h", "24h"))
        + ").",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
