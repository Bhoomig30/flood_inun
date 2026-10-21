#!/usr/bin/env python3
"""
Honest held-out TEST metrics for the flood-mapping model.

Reads  ml/data/test_predictions/test_scene_results_threshold_065.csv  (one row per test tile)
and     ml/data/split/test.txt, checks that every test tile is accounted for, then reports:
  * mean / median per-tile IoU and F1     (every tile counts equally; near-flood-free tiles hurt)
  * pooled IoU / precision / recall / F1  (all pixels together; dominated by big flooded tiles)
  * the same for tiles with >= 1% true flood (where IoU is meaningful)
  * per-event breakdown, if ml/data/scene_events.csv exists (run build_scene_events.py first)

Writes naraj_dashboard/data/ai_flood/test_set_metrics.json for the dashboard.
Report BOTH the per-tile and the pooled numbers and say which is which.
"""
import json
from pathlib import Path

import pandas as pd

ML = Path(__file__).resolve().parents[1]
DATA = ML / "data"
RESULTS = DATA / "test_predictions" / "test_scene_results_threshold_065.csv"
OUT = ML.parent / "naraj_dashboard" / "data" / "ai_flood" / "test_set_metrics.json"


def pooled(d):
    tp, fp, fn = int(d.true_positives.sum()), int(d.false_positives.sum()), int(d.false_negatives.sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"iou": round(tp / (tp + fp + fn), 4) if tp + fp + fn else 0.0, "precision": round(prec, 4),
            "recall": round(rec, 4), "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0}


def per_tile(d):
    return {"mean_iou": round(float(d.iou.mean()), 4), "median_iou": round(float(d.iou.median()), 4),
            "mean_f1": round(float(d.f1.mean()), 4), "mean_precision": round(float(d.precision.mean()), 4),
            "mean_recall": round(float(d.recall.mean()), 4), "tiles": int(len(d))}


df = pd.read_csv(RESULTS)
df["scene"] = df["scene"].astype(str)
test_ids = [x.strip().replace("_image.tif", "") for x in open(DATA / "split" / "test.txt") if x.strip()]
missing = sorted(set(test_ids) - set(df.scene))
extra = sorted(set(df.scene) - set(test_ids))

report = {
    "evaluated_on": "held-out TEST split (never used for training or threshold tuning)",
    "model": "Random Forest, 12 features",
    "threshold": float(df.threshold.iloc[0]),
    "threshold_tuned_on": "validation split",
    "test_tiles_in_split": len(test_ids),
    "test_tiles_scored": int(len(df)),
    "test_tiles_missing_from_results": missing,
    "tiles_not_in_test_split": extra,
    "per_tile": per_tile(df),
    "pooled_pixels": pooled(df),
    "tiles_iou_below_0_5": int((df.iou < 0.5).sum()),
    "tiles_with_under_1pct_flood": int((df.actual_flood_pct < 1).sum()),
    "tiles_with_1pct_or_more_flood": {**per_tile(df[df.actual_flood_pct >= 1]),
                                       "pooled": pooled(df[df.actual_flood_pct >= 1])},
    "note": "Per-tile IoU treats every tile equally, so tiles with almost no flooding pull it down. "
            "Pooled IoU weights tiles by pixels and is dominated by large flooded tiles. Report both.",
}

ev_file = DATA / "scene_events.csv"
if ev_file.exists():
    ev = pd.read_csv(ev_file, dtype={"scene": str})
    m = df.merge(ev[["scene", "iso", "country", "s1_date"]], on="scene", how="left")
    report["per_event"] = {}
    for iso, g in m.groupby("iso", dropna=False):
        report["per_event"][str(iso)] = {"country": str(g.country.iloc[0]), "s1_date": str(g.s1_date.iloc[0]),
                                          "per_tile": per_tile(g), "pooled_pixels": pooled(g)}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(report, indent=2))

print(f"Test tiles in split: {len(test_ids)}   scored: {len(df)}   missing: {missing}   extra: {extra}")
print(f"\nPER-TILE  (n={len(df)}):  mean IoU {report['per_tile']['mean_iou']:.3f}  median {report['per_tile']['median_iou']:.3f}"
      f"  mean F1 {report['per_tile']['mean_f1']:.3f}")
print(f"POOLED pixels:           IoU {report['pooled_pixels']['iou']:.3f}  precision {report['pooled_pixels']['precision']:.3f}"
      f"  recall {report['pooled_pixels']['recall']:.3f}  F1 {report['pooled_pixels']['f1']:.3f}")
t = report["tiles_with_1pct_or_more_flood"]
print(f"Tiles with >=1% flood (n={t['tiles']}): mean IoU {t['mean_iou']:.3f}  pooled IoU {t['pooled']['iou']:.3f}")
print(f"Tiles with IoU < 0.5: {report['tiles_iou_below_0_5']}/{len(df)}   tiles with <1% flood: {report['tiles_with_under_1pct_flood']}")
if "per_event" in report:
    print("\nPer event:")
    for iso, r in report["per_event"].items():
        print(f"  {iso:8s} tiles {r['per_tile']['tiles']:3d}  mean IoU {r['per_tile']['mean_iou']:.3f}  pooled IoU {r['pooled_pixels']['iou']:.3f}")
print(f"\nSaved -> {OUT}")
