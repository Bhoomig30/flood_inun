# Naraj backtest — held-out test period

This page reports measured results on the model's chronological test split, **2025-04-01 06:00:00 → 2025-12-30 23:00:00 UTC** (6,570 hourly rows). The Random Forests (`rf_hf_v3`, committed `.pkl` files) never trained on these rows. This is a historical backtest, not a forecast.

- Flood threshold: **24.28 m** (95th percentile of the 2021–2025 record).
- HIGH band: probability ≥ 0.75.
- Decision cutoff used for yes/no: 0.50.
- Baseline: *persistence threshold* — predict a flood if the current level is already ≥ 24.28 m. It uses no rainfall or upstream gauges.
- Outcomes are the dataset's `flood_next_*h` labels; the script verifies they equal “max level in the next h hours ≥ threshold” (0 mismatches).

Reproduce with `.venv/bin/python scripts/backtest_metrics.py`.

## Results by horizon

| Horizon | Positives | Model HIGH hours | P(crossing | HIGH) | Model recall @0.5 | Model precision @0.5 | Model F1 @0.5 | Model missed crossings | Baseline recall | Baseline precision | Baseline F1 | Baseline missed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6h | 755 | 602 | 99.0% | 80.4% | 98.7% | 0.8861 | 148 | 94.4% | 99.0% | 0.9668 | 42 |
| 12h | 797 | 579 | 99.0% | 75.0% | 98.7% | 0.8525 | 199 | 89.5% | 99.0% | 0.9400 | 84 |
| 24h | 881 | 588 | 98.8% | 68.4% | 98.7% | 0.8083 | 278 | 80.9% | 99.0% | 0.8907 | 168 |

## How often the model was right when it said HIGH

- **6h:** 602 hours were HIGH (9.2% of the period). A crossing followed in 596 of them, so **99.0%** of HIGH alerts were correct. Those HIGH hours covered 596 of 755 crossings (78.9%).
- **12h:** 579 hours were HIGH (8.8% of the period). A crossing followed in 573 of them, so **99.0%** of HIGH alerts were correct. Those HIGH hours covered 573 of 797 crossings (71.9%).
- **24h:** 588 hours were HIGH (9.0% of the period). A crossing followed in 581 of them, so **98.8%** of HIGH alerts were correct. Those HIGH hours covered 581 of 881 crossings (66.0%).

## How often it missed a crossing

- **6h:** 148 of 755 crossings (19.6%) had model probability below 0.5; 159 were below the HIGH band.
- **12h:** 199 of 797 crossings (25.0%) had model probability below 0.5; 224 were below the HIGH band.
- **24h:** 278 of 881 crossings (31.6%) had model probability below 0.5; 300 were below the HIGH band.

## Model vs baseline

| Horizon | Model ROC-AUC | Baseline ROC-AUC | Model Brier | Baseline Brier | Model wrong, baseline right | Baseline wrong, model right |
|---|---|---|---|---|---|---|
| 6h | 0.9921 | 0.9716 | 0.0227 | 0.0075 | 108 | 1 |
| 12h | 0.9899 | 0.9467 | 0.0301 | 0.0139 | 117 | 1 |
| 24h | 0.9824 | 0.9040 | 0.0420 | 0.0267 | 112 | 1 |

### Where the baseline wins

- **6h:** precision (99.0% vs 98.7%); recall (94.4% vs 80.4%); F1 (0.9668 vs 0.8861); Brier (0.0075 vs 0.0227); missed crossings (42 vs 148).
- **12h:** precision (99.0% vs 98.7%); recall (89.5% vs 75.0%); F1 (0.9400 vs 0.8525); Brier (0.0139 vs 0.0301); missed crossings (84 vs 199).
- **24h:** precision (99.0% vs 98.7%); recall (80.9% vs 68.4%); F1 (0.8907 vs 0.8083); Brier (0.0267 vs 0.0420); missed crossings (168 vs 278).

The persistence baseline is hard to beat here because Naraj behaves like a slowly rising river: once the level is already above 24.28 m it almost never drops below it within 24 hours, so “still flooded ⇒ still flooded” is highly accurate. Its 0.5 decision also catches more crossings than the Random Forest at the same cutoff, because the RF is deliberately conservative and keeps many flood rows below 50% probability.

Where the RF is better is ranking: its ROC-AUC and PR-AUC are higher at every horizon, i.e. it separates rising from receding hours better than the current level alone, particularly for the 24 h window. Its Brier score is worse, so its probabilities are less calibrated than the baseline's hard 0/1 rule (which is favoured by the very high base rate inside flood windows).

## Caveats

- Single station (Naraj) and 881 positive 24 h windows; one test split, so differences of a few cases are not meaningful.
- The threshold is also the training label definition, and the baseline uses the current level, which is one of the model's strongest features.
- Each horizon excludes its final h rows, where the future window is incomplete. The published reference numbers in `hf_forecast_baseline.json` used all 6,570 rows, so small differences against those figures are expected.
- The reference JSON's `hit_rate_at_HIGH` is the share of crossings that fell in the HIGH band (e.g. 0.7885 at 6 h), not P(crossing | HIGH). The table above reports the latter.
- The UI shows individual hours from this split; it does not extend the model beyond the dataset.
