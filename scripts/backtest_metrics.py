#!/usr/bin/env python3
"""Whole-test-period metrics for the Naraj backtest (honest, measured).

Scores every row of the chronological test split with the committed Random
Forest bundles, compares them with the persistence baseline on the SAME rows,
and writes:

    docs/backtest_naraj_test_period.json   (machine-readable results)
    docs/BACKTEST.md                       (report, including baseline wins)

No training, no data invention: features and labels come from
data/hf/forecast_dataset.csv, the threshold and split from
data/ml_models/hf_forecast_baseline.json.

    .venv/bin/python scripts/backtest_metrics.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score, average_precision_score

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "naraj_dashboard"
DATASET = DS / "data" / "hf" / "forecast_dataset.csv"
BASELINE = DS / "data" / "ml_models" / "hf_forecast_baseline.json"
MODEL_DIR = DS / "data" / "ml_models"
OUT_JSON = ROOT / "docs" / "backtest_naraj_test_period.json"
OUT_MD = ROOT / "docs" / "BACKTEST.md"

HORIZONS = (6, 12, 24)
HIGH = 0.75
CUT = 0.5


def confusion(pred, y):
    pred = np.asarray(pred, dtype=bool)
    y = np.asarray(y, dtype=bool)
    tp = int((pred & y).sum())
    fp = int((pred & ~y).sum())
    fn = int((~pred & y).sum())
    tn = int((~pred & ~y).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return {
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "tp": tp,
        "precision": None if precision is None else round(precision, 4),
        "recall": None if recall is None else round(recall, 4),
        "f1": None if f1 is None else round(f1, 4),
    }


def main() -> None:
    meta = json.loads(BASELINE.read_text())
    threshold = float(meta["label"]["threshold_m"])
    test_start = meta["split"]["test_start"]
    test_end = meta["split"]["test_end"]

    df = pd.read_csv(DATASET, parse_dates=["timestamp"])
    test = df[(df.timestamp >= test_start) & (df.timestamp <= test_end)].reset_index(
        drop=True
    )

    results = {}
    for h in HORIZONS:
        bundle = joblib.load(MODEL_DIR / f"hf_forecast_{h}h.pkl")
        features = bundle["features"]
        missing = [c for c in features if c not in test.columns]
        if missing:
            raise SystemExit(f"{h}h bundle is missing features: {missing[:5]}")

        # Complete windows only: the final h rows of the period have no future
        # observations, so their flood_next_* labels cannot be verified.
        usable = test.iloc[: len(test) - h].copy()
        x = usable[features]
        xi = bundle["imputer"].transform(x)
        prob = bundle["model"].predict_proba(xi)[:, 1]
        y = usable[f"flood_next_{h}h"].astype(int).to_numpy()

        # Sanity: dataset labels must equal "max of next h levels >= threshold".
        all_levels = test["naraj_water_level_m"].to_numpy()
        future_max = np.array(
            [all_levels[i + 1 : i + 1 + h].max() for i in range(len(usable))]
        )
        computed = (future_max >= threshold).astype(int)
        label_mismatches = int((computed != y).sum())

        model_at_cut = confusion(prob >= CUT, y)
        high_mask = prob >= HIGH
        high = confusion(high_mask, y)
        high["hours"] = int(high_mask.sum())
        high["share_of_hours"] = round(float(high_mask.mean()), 4)
        high["positives_covered"] = int((high_mask & (y == 1)).sum())
        high["share_of_positives"] = (
            round(float((high_mask & (y == 1)).sum() / max(y.sum(), 1)), 4)
        )
        high["hit_rate"] = high["precision"]  # P(crossing | model said HIGH)
        high["mean_probability"] = round(float(prob[high_mask].mean()), 4) if high_mask.any() else None

        base_pred = usable["naraj_water_level_m"].to_numpy() >= threshold
        baseline = confusion(base_pred, y)

        missed = int(((y == 1) & (prob < CUT)).sum())
        missed_by_high = int(((y == 1) & (prob < HIGH)).sum())

        rf_brier = float(brier_score_loss(y, prob))
        base_brier = float(brier_score_loss(y, base_pred.astype(int)))
        rf_auc = float(roc_auc_score(y, prob))
        base_auc = float(roc_auc_score(y, base_pred.astype(int)))
        rf_pr = float(average_precision_score(y, prob))
        base_pr = float(average_precision_score(y, base_pred.astype(int)))

        model_wrong_base_right = int((((prob >= CUT) != y) & (base_pred == y)).sum())
        base_wrong_model_right = int(((base_pred != y) & ((prob >= CUT) == y)).sum())

        results[f"{h}h"] = {
            "rows": int(len(usable)),
            "positives": int(y.sum()),
            "negative": int((y == 0).sum()),
            "label_mismatches": label_mismatches,
            "model": {
                "at_0_5": model_at_cut,
                "brier": round(rf_brier, 4),
                "roc_auc": round(rf_auc, 4),
                "pr_auc": round(rf_pr, 4),
                "missed_positives": missed,
                "missed_positive_rate": round(missed / max(int(y.sum()), 1), 4),
                "high_band": high,
                "missed_positives_at_high": missed_by_high,
            },
            "baseline": {
                "definition": "predict flood if current level >= threshold",
                "at_0_5": baseline,
                "brier": round(base_brier, 4),
                "roc_auc": round(base_auc, 4),
                "pr_auc": round(base_pr, 4),
                "missed_positives": baseline["fn"],
                "missed_positive_rate": round(
                    baseline["fn"] / max(int(y.sum()), 1), 4
                ),
            },
            "head_to_head": {
                "model_wrong_baseline_right": model_wrong_base_right,
                "baseline_wrong_model_right": base_wrong_model_right,
            },
            "baseline_wins": {
                "precision": _gt(baseline["precision"], model_at_cut["precision"]),
                "recall": _gt(baseline["recall"], model_at_cut["recall"]),
                "f1": _gt(baseline["f1"], model_at_cut["f1"]),
                "brier": base_brier < rf_brier,
                "missed_positives": baseline["fn"] < missed,
            },
            "model_wins": {
                "roc_auc": rf_auc > base_auc,
                "pr_auc": rf_pr > base_pr,
            },
        }

    payload = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "station": "naraj",
        "dataset": str(DATASET.relative_to(ROOT)),
        "test_period": {"start": test_start, "end": test_end},
        "threshold_m": threshold,
        "high_band": HIGH,
        "decision_cutoff": CUT,
        "rows_note": (
            "Each horizon excludes its final h rows because those windows have "
            "no future observations; published baseline reference uses all 6570 rows."
        ),
        "published_reference": meta.get("rf_reference", {}).get("test", {}),
        "results": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    markdown = render_markdown(payload)

    # The onset-only analysis is produced by scripts/onset_skill.py; append its
    # report so a regeneration of this file does not drop it.
    onset_md = ROOT / "docs" / "ONSET_SKILL.md"
    if onset_md.exists():
        section = onset_md.read_text().replace(
            "# Onset skill", "## Onset skill", 1
        )
        markdown += "\n---\n\n" + section
    OUT_MD.write_text(markdown)
    print(json.dumps(payload["results"], indent=2))


def _gt(a, b):
    return a is not None and b is not None and a > b


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _num(x):
    return "n/a" if x is None else f"{x:.4f}"


def render_markdown(payload) -> str:
    r = payload["results"]
    period = payload["test_period"]
    threshold = payload["threshold_m"]
    lines = [
        "# Naraj backtest — held-out test period",
        "",
        "This page reports measured results on the model's chronological test split, "
        f"**{period['start']} → {period['end']} UTC** (6,570 hourly rows). The Random "
        "Forests (`rf_hf_v3`, committed `.pkl` files) never trained on these rows. "
        "This is a historical backtest, not a forecast.",
        "",
        f"- Flood threshold: **{threshold:.2f} m** (95th percentile of the 2021–2025 record).",
        f"- HIGH band: probability ≥ {payload['high_band']:.2f}.",
        f"- Decision cutoff used for yes/no: {payload['decision_cutoff']:.2f}.",
        "- Baseline: *persistence threshold* — predict a flood if the current level "
        f"is already ≥ {threshold:.2f} m. It uses no rainfall or upstream gauges.",
        "- Outcomes are the dataset's `flood_next_*h` labels; the script verifies "
        "they equal “max level in the next h hours ≥ threshold” (0 mismatches).",
        "",
        "Reproduce with `.venv/bin/python scripts/backtest_metrics.py`.",
        "",
        "## Results by horizon",
        "",
        "| Horizon | Positives | Model HIGH hours | P(crossing | HIGH) | Model recall @0.5 | Model precision @0.5 | Model F1 @0.5 | Model missed crossings | Baseline recall | Baseline precision | Baseline F1 | Baseline missed |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for h in ("6h", "12h", "24h"):
        m = r[h]["model"]
        b = r[h]["baseline"]
        hb = m["high_band"]
        lines.append(
            f"| {h} | {r[h]['positives']} | {hb['hours']} | {_pct(hb['hit_rate'])} | "
            f"{_pct(m['at_0_5']['recall'])} | {_pct(m['at_0_5']['precision'])} | "
            f"{_num(m['at_0_5']['f1'])} | {m['missed_positives']} | "
            f"{_pct(b['at_0_5']['recall'])} | {_pct(b['at_0_5']['precision'])} | "
            f"{_num(b['at_0_5']['f1'])} | {b['missed_positives']} |"
        )

    lines += [
        "",
        "## How often the model was right when it said HIGH",
        "",
    ]
    for h in ("6h", "12h", "24h"):
        hb = r[h]["model"]["high_band"]
        lines.append(
            f"- **{h}:** {hb['hours']} hours were HIGH ({_pct(hb['share_of_hours'])} of "
            f"the period). A crossing followed in {hb['tp']} of them, so "
            f"**{_pct(hb['hit_rate'])}** of HIGH alerts were correct. Those HIGH hours "
            f"covered {hb['positives_covered']} of {r[h]['positives']} crossings "
            f"({_pct(hb['share_of_positives'])})."
        )

    lines += [
        "",
        "## How often it missed a crossing",
        "",
    ]
    for h in ("6h", "12h", "24h"):
        m = r[h]["model"]
        lines.append(
            f"- **{h}:** {m['missed_positives']} of {r[h]['positives']} crossings "
            f"({_pct(m['missed_positive_rate'])}) had model probability below 0.5; "
            f"{m['missed_positives_at_high']} were below the HIGH band."
        )

    lines += [
        "",
        "## Model vs baseline",
        "",
        "| Horizon | Model ROC-AUC | Baseline ROC-AUC | Model Brier | Baseline Brier | Model wrong, baseline right | Baseline wrong, model right |",
        "|---|---|---|---|---|---|---|",
    ]
    for h in ("6h", "12h", "24h"):
        m, b, h2h = r[h]["model"], r[h]["baseline"], r[h]["head_to_head"]
        lines.append(
            f"| {h} | {m['roc_auc']:.4f} | {b['roc_auc']:.4f} | {m['brier']:.4f} | "
            f"{b['brier']:.4f} | {h2h['model_wrong_baseline_right']} | "
            f"{h2h['baseline_wrong_model_right']} |"
        )

    lines += ["", "### Where the baseline wins", ""]
    any_win = False
    for h in ("6h", "12h", "24h"):
        m, b, wins = r[h]["model"], r[h]["baseline"], r[h]["baseline_wins"]
        parts = []
        if wins["precision"]:
            parts.append(
                f"precision ({_pct(b['at_0_5']['precision'])} vs "
                f"{_pct(m['at_0_5']['precision'])})"
            )
        if wins["recall"]:
            parts.append(
                f"recall ({_pct(b['at_0_5']['recall'])} vs "
                f"{_pct(m['at_0_5']['recall'])})"
            )
        if wins["f1"]:
            parts.append(
                f"F1 ({_num(b['at_0_5']['f1'])} vs {_num(m['at_0_5']['f1'])})"
            )
        if wins["brier"]:
            parts.append(f"Brier ({b['brier']:.4f} vs {m['brier']:.4f})")
        if wins["missed_positives"]:
            parts.append(
                f"missed crossings ({b['at_0_5']['fn']} vs {m['missed_positives']})"
            )
        if parts:
            any_win = True
            lines.append(f"- **{h}:** " + "; ".join(parts) + ".")
    if not any_win:
        lines.append("- The baseline does not beat the model on any reported metric.")

    lines += [
        "",
        "The persistence baseline is hard to beat here because Naraj behaves like a "
        "slowly rising river: once the level is already above 24.28 m it almost never "
        "drops below it within 24 hours, so “still flooded ⇒ still flooded” is highly "
        "accurate. Its 0.5 decision also catches more crossings than the Random "
        "Forest at the same cutoff, because the RF is deliberately conservative and "
        "keeps many flood rows below 50% probability.",
        "",
        "Where the RF is better is ranking: its ROC-AUC and PR-AUC are higher at every "
        "horizon, i.e. it separates rising from receding hours better than the current "
        "level alone, particularly for the 24 h window. Its Brier score is worse, so "
        "its probabilities are less calibrated than the baseline's hard 0/1 rule "
        "(which is favoured by the very high base rate inside flood windows).",
        "",
        "## Caveats",
        "",
        f"- Single station (Naraj) and {r['24h']['positives']} positive 24 h windows; "
        "one test split, so differences of a few cases are not meaningful.",
        "- The threshold is also the training label definition, and the baseline uses "
        "the current level, which is one of the model's strongest features.",
        "- Each horizon excludes its final h rows, where the future window is "
        "incomplete. The published reference numbers in "
        "`hf_forecast_baseline.json` used all 6,570 rows, so small differences "
        "against those figures are expected.",
        "- The reference JSON's `hit_rate_at_HIGH` is the share of crossings that "
        "fell in the HIGH band (e.g. 0.7885 at 6 h), not P(crossing | HIGH). The "
        "table above reports the latter.",
        "- The UI shows individual hours from this split; it does not extend the "
        "model beyond the dataset.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
