# Next steps — decisions and missing inputs

This document is a **plan**, not an implementation. Every item below needs either
data, access, or a decision that does not exist in the repository today. Nothing
here invents figures, stations, or coverage.

Status references are to the current branch (`audit/close-gaps`): two trained RF
models (6/12/24 h calibrated forecast on 71 CWC features; 12-feature spatial
inundation model), a persistence-baseline report, a stale-data indicator, and the
`scripts/ingest_cwc.py` scaffolding.

---

## 1. Live CWC ingestion

**What is needed**
- A machine-readable stream of hourly water level (and ideally rainfall) for
  Naraj, Alipingal and Nimapara, newer than the last record in the repo
  (daily series ends `2025-12-31`, hourly calibration file covers August 2022).
- A scheduler that runs `scripts/ingest_cwc.py` (already supports `--once`,
  `--watch --interval-minutes`, `--levels-csv <path-or-url>`, `--dry-run`) and
  alerts when a run yields no new rows.
- Agreement on acceptable use (rate limits, attribution) for whichever source is
  chosen.

**What is missing / unverified**
- The CWC **manual hourly water-level export** that produced
  `data/cwc/*_daily_2021_2025.json` is **not** in the Hugging Face dataset
  (3,344 files checked; zero `rwl*` paths).
- Hugging Face only hosts rainfall telemetry (state-wise, 2021–2025) and river
  **discharge** (`river_discharge_tele_hr_cwc_od_1970_2025.csv`, m³/s — not a
  level, and not what the model was trained on).
- Live CWC endpoints were unreachable from this sandbox when probed on
  2026-11-12: `ffs.india-water.gov.in` and `indiawris.gov.in` timed out,
  `cwc.gov.in` returned HTTP 401, `api.data.gov.in` timed out. **No credentials
  or portal account are configured.**
- Without a source, `ingestion_status.json` reports `stale: true` and
  `/api/health` exposes the blocker. That is working as designed, not a bug.

**Effort estimate** — 3–5 days once a source is confirmed (adapter, validation
against the historical record, scheduler + alerting, backfill test). Add ~1 week
if a portal export must be scraped behind a login.

**First concrete step**
Obtain one authorised URL or export that returns hourly Naraj level for a date
after 2025-12-31, then run:

```bash
python3 scripts/ingest_cwc.py --once --levels-csv <that url or file> --dry-run
```

A dry run that reports `observations_added > 0` proves the path before anything
is written.

**Decision required from you:** which access route (CWC portal login, India-WRIS
API key, a manual periodic export, or a paid data vendor).

**Why this item now matters twice:** the dashboard headline is the Random Forest
anchored to the dataset's last row, and the statistical engine is reported
separately under `legacy_engine` because its hourly history stops at
2022-08-31. **Extending the engine's hourly water-level history is the follow-up
that would allow re-blending** the two components on a shared, current anchor.
Until hourly records past 2022-08-31 exist (from the same CWC source), any blend
would mix a three-year-old river state with the RF's current row, which is why
the headline is single-source today.

### Why the in-repo CSV cannot supply the engine's hourly history (investigated 2026-11-13)

The obvious shortcut — point the engine at `data/hf/forecast_dataset.csv` — was
investigated and rejected. The engine needs, per station, an hourly series of
`{timestamp, water_level_m}` (it derives `rise_6/12/24h`, `trend_3h`, the
forecast cone and the per-horizon `max_rise` calibration from it), plus the
daily series it already has.

What the CSV actually contains for `naraj_water_level_m`:

| Check | Result |
| --- | --- |
| Rows / range | 43,800 rows, 2021-01-01 00:00 → 2025-12-30 23:00, hourly index, no duplicates, no missing hours |
| Nulls | 0 |
| Distinct values per day | **exactly 1 on all 1,825 days** |
| Unchanged consecutive hours | 42,420 of 43,799 (longest plateau 215 h) |

So the column is a **daily series broadcast to an hourly index**, not hourly
observations. Feeding it to the engine would make every sub-daily rise
zero except at the daily step and would recompute `max_rise` from daily steps —
a silent modelling change, not a data reuse.

The genuine hourly source is `rwl_manual_hr_cwc_005_2021_2025.csv`, named in
`data_sources.json` ("21,257 observations for Naraj", ≈48% of the hours) and in
the `source` field of `data/cwc/*.json`. **That file is not in the repository**
(no `*rwl*` or `*manual_hr*` file anywhere on disk, tracked or ignored), and its
partial coverage means gaps could only be filled by guessing. The only genuinely
hourly files present are `data/cwc/{naraj,alipingal,nimapara}_august2022_hourly.json`
(721 records each; Naraj has 347 distinct values and 535 hour-to-hour changes).

**Outcome:** not implemented. Removing the 2022 anchor needs either the original
hourly export or live hourly ingestion (item above). When that exists, the
engine can rebuild its hourly series per station; tests would then assert its
`reference_time` reaches 2025-12-30 23:00 while the RF headline is unchanged.

---

## 2. Models for stations other than Naraj

**What is needed**
- Per-station hourly water-level series long enough for a chronological split
  (the Naraj model uses 43,800 hourly rows, ≈5 years), plus each station's
  danger level (the Naraj label uses 24.28 m = 95th percentile of 2021–2025).
- A decision on scope: per-station models, or one pooled model with station
  embeddings/features.

**What is missing / unverified**
- Only **three** stations have verified series in the repo
  (`data/cwc/{naraj,alipingal,nimapara}_daily_2021_2025.json` + an August-2022
  hourly file each). Only **Naraj** has a trained model.
- The 842-station India registry is built from rainfall telemetry and river
  **discharge**; it does not contain verified hourly *levels* or published danger
  levels, so "842 stations" is coverage, not model-readiness.
- No inventory exists of which registry stations have ≥2 years of hourly level.

**Effort estimate** — 1–2 weeks for a second station once its series and danger
level are verified (the training script is station-agnostic apart from the
target column and the feature list, which currently hard-codes
`naraj_*`/`alipingal_*`/`nimapara_*` columns); 4–6 weeks for a pooled
multi-station model with per-station validation.

**First concrete step**
Build a station-readiness table (station, series length, hourly vs daily, danger
level source) for the registry and pick the first station that passes all three.

**Decision required:** per-station vs pooled model, and which station is second.

---

## 3. Stage 3 — SAR / DEM / landcover features into the model

**What is needed**
- Aligned per-scene features (SAR backscatter stats, DEM elevation/slope,
  landcover fractions, distance to river) sampled at or near each forecast
  timestamp, joined to the hourly feature frame as additional columns.
- An imputation rule for hours with no overpass, and a measured ablation showing
  whether the added features improve the holdout beyond the persistence baseline.

**What is missing / unverified**
- `ml/data/` raw inputs are gitignored and **absent** in this checkout, so the
  feature builders (`ml/src/create_dem_features.py`,
  `create_landcover_features.py`, `create_river_feature.py`) cannot run as-is.
- The rasters exist on Hugging Face (`ml/data/external/dem_cache/*`,
  `esa_worldcover/*`, `sen5/*`) but total several GB and require
  `pip install huggingface_hub` (not in `requirements.txt`).
- Sentinel-1 revisit is ~6–12 days against an hourly forecast cadence: any SAR
  feature would be stale for most hours. This is a design constraint, not a bug
  to fix.

**Effort estimate** — 3–4 weeks (download/alignment 1 week, feature engineering
1–2 weeks, ablation and write-up 1 week).

**First concrete step**
Download one AOI subset and produce a single joined table for 2021–2025 where
SAR/DEM/landcover columns are non-null only near overpasses; report the share of
hours covered before any modelling.

**Decision required:** whether SAR-derived features are worth it given the
overpass gap, or whether DEM/landcover static features alone are the target.

---

## 4. Stage 6 — flood extent confidence

Four separable pieces, each blocked differently:

| Piece | What is needed | What is missing | Effort | First step |
| --- | --- | --- | --- | --- |
| Threshold optimisation | Labelled reference extents to sweep the 3 dB candidate threshold against | Only 4 satellite-verified NDEM events exist in the repo; no independent held-out mask | ~1 week | Score the existing candidate mask against the NDEM events, then sweep 1.5–4 dB and report IoU per event |
| Terrain correction | Full SAR terrain correction (range-Doppler) instead of the current approximate GCP-TPS geocoding | DEM + precise orbit files per scene; the pipeline currently documents GCP-TPS as approximate | 2–3 weeks | Reproduce one scene with a terrain-corrected processor and measure the pixel shift vs the current mask |
| CWC↔DEM vertical datum crosswalk | Survey/benchmark information linking CWC gauge datum to the DEM vertical datum | No datum documentation in the repo | 1–2 weeks | Obtain the gauge zero / benchmark sheet for Naraj from CWC |
| Train `ml/src/unet.py` | Labelled image/mask pairs plus GPU time | `ml/data/` absent; no trained segmentation weights; no GPU in this environment | 3–4 weeks | Assemble the labelled Sen1Floods11-style subset and run a single-epoch smoke train on CPU to validate the loader |

**Decision required:** whether extent work is in scope at all before Stage 7
(exposure) has verified data — extent without exposure produces no decision.

---

## 5. Stage 7 — exposure-based decision support

**What is needed**
- Verified population counts per administrative unit (with a documented,
  citable source and license).
- Infrastructure/asset layers (buildings, roads, utilities) with a known vintage.
- An intersection method (flood mask × exposure layer) and agreed thresholds for
  what counts as "affected".
- Explicit uncertainty: current candidate-mask precision is not yet characterised
  per pixel, so any exposure figure inherits that error.

**What is missing / unverified**
- **No exposure data has been obtained.** `data/exposure_layers.json` is a
  placeholder that says so, and the research page's Exposure tab labels itself
  "NEXT INTEGRATION LAYER".
- No license review, no unit-boundary geometry, no population raster, no asset
  inventory.

**Effort estimate** — 4–6 weeks (data acquisition and license review 2 weeks,
spatial join + QA 2 weeks, reporting 1–2 weeks).

**First concrete step**
Choose one authoritative source, record its provenance and license in
`data/data_sources.json`, and compute exposure for a single event only after the
extent mask has a measured precision against NDEM. Do not publish figures before
that.

**Decision required:** acceptable sources and licensing, and whether exposure is
computed for the study region only.

---

## Open decisions summary

| # | Decision | Blocks |
| --- | --- | --- |
| 1 | CWC access route (portal / API key / export / vendor) | Live ingestion, freshness |
| 2 | Per-station vs pooled models; second station | Multi-station coverage |
| 3 | SAR features given overpass gaps, or DEM/landcover only | Stage 3 |
| 4 | Extent work before exposure data exists | Stage 6 |
| 5 | Authoritative exposure sources and licence | Stage 7 |
| 6 | Regenerate the committed `.pkl` bundles on the new `FrozenEstimator` calibration path (holdout metrics are identical on 1.7.2, but the pickled objects differ), and/or keep the `<1.8` pin so the 1.7.2 artefacts stay loadable | Model artefacts |
