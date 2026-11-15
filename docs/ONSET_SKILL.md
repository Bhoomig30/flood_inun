# Onset skill — Naraj, below-threshold hours

Onsets only: the current level is **below 24.28 m** and the positive label means the level crosses the threshold within the horizon. Rows already above the threshold (where a persistence rule is trivially right) are excluded.

- Test period: **2025-04-01 06:00:00 → 2025-12-30 23:00:00 UTC**.
- Validation period (tuning only): **2024-07-01 11:00:00 → 2025-04-01 05:00:00 UTC**.
- Model: committed `rf_hf_v3` bundles, unchanged; no retraining.
- RF cutoff: maximises F2 (recall-weighted) on validation onsets.
- Baseline: `projected level = level + k × recent rise`, best family member by F1 on validation onsets, triggered when the projection reaches the threshold.

| Horizon | Onset rows (test) | True onsets | RF ROC-AUC | Baseline ROC-AUC | RF PR-AUC | Baseline PR-AUC | RF recall @0.5 | RF precision @0.5 | RF recall @tuned | RF precision @tuned | Baseline alert recall | Baseline alert precision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6h | 5844 | 42 | 0.8705 | 0.9425 | 0.0843 | 0.0618 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 12h | 5838 | 84 | 0.9252 | 0.9528 | 0.1439 | 0.1521 | 0.0% | 0.0% | 14.3% | 57.1% | 0.0% | 0.0% |
| 24h | 5826 | 168 | 0.9316 | 0.9594 | 0.2122 | 0.3043 | 0.0% | 0.0% | 1.8% | 20.0% | 0.0% | 0.0% |

### Chosen operating points (validation only)

- **6h:** RF cutoff 0.048 (validation F2 0.671); baseline `double_rise_24h` triggered at projected level ≥ threshold (validation F1 0.240).
- **12h:** RF cutoff 0.047 (validation F2 0.708); baseline `double_rise_24h` triggered at projected level ≥ threshold (validation F1 0.471).
- **24h:** RF cutoff 0.085 (validation F2 0.789); baseline `linear_rise_24h` triggered at projected level ≥ threshold (validation F1 0.727).

### Does the RF beat the baseline on onsets?

- **6h:** ROC-AUC 0.8705 vs 0.9425 (-0.0720); PR-AUC 0.0843 vs 0.0618 (+0.0225); F1 at the tuned cutoffs 0.000 vs 0.000 (+0.000). **RF beats the baseline on 1 of 3 measures.**
- **12h:** ROC-AUC 0.9252 vs 0.9528 (-0.0276); PR-AUC 0.1439 vs 0.1521 (-0.0082); F1 at the tuned cutoffs 0.229 vs 0.000 (+0.229). **RF beats the baseline on 1 of 3 measures.**
- **24h:** ROC-AUC 0.9316 vs 0.9594 (-0.0278); PR-AUC 0.2122 vs 0.3043 (-0.0921); F1 at the tuned cutoffs 0.033 vs 0.000 (+0.033). **RF beats the baseline on 1 of 3 measures.**

The validation-tuned RF cutoff does not transfer cleanly: the median probability on true test onsets is far lower than on validation onsets (0.0026 vs 0.0714 at 6 h, 0.0035 vs 0.1596 at 12 h, 0.0043 vs 0.2754 at 24 h), so a fixed probability cutoff fires on very few test onsets. The validation-selected baseline rule also fails to fire correctly on the test period (no true positives at 6/12/24 h at its natural trigger), which is why the RF's F1 looks better even though its ranking is not.

Plainly: **the RF does not beat the best simple baseline on onsets overall.** The baseline ranks test onsets better on ROC-AUC at every horizon and on PR-AUC at 12 h and 24 h; the RF is ahead on PR-AUC only at 6 h. Neither approach is operationally reliable for onset detection in this test period: RF recall at the default 0.5 cutoff is 0% at every horizon, and at the validation-tuned cutoffs it is 0.0%/14.3%/1.8% (alerts 7/21/15).
