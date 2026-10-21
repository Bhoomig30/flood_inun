# FloodWatch India — Flood Intelligence Platform

**India-wide flood intelligence platform** built on the project's real CWC
datasets. The dashboard serves any location in India: search it, use device
location, or click the map — the nearest real CWC rainfall and river stations,
model scope, and availability notices all update from a single selected-location
state.

**Honest scope:** the temporal Random Forest forecast (6h/12h/24h) is calibrated
on the **Naraj/Cuttack (Mahanadi basin) historical study data** — it is NOT an
India-wide calibrated model, and the UI says so for every other location.
Satellite evidence and past-flood events are also study-region datasets and are
labelled as such.

## India-wide station registry (real data)

`data/india_cwc/stations.json` — **842 CWC stations across 28 states** (808
telemetry rainfall stations, 2021–2025, state-wise; 34 river-discharge
stations, 1970–2025), built directly from the real CWC CSVs hosted with the
project's dataset (Hugging Face: `bhoomig0630/flood-inundation-upload`,
`ml/data/external/...`). No stations invented, no values imputed. Rebuild with:

```bash
python3 scripts/build_india_registry.py --src ml/data/external
```

<!-- # AI-Driven Flood Inundation Analysis & Decision Support System

A local, judge-friendly decision-support dashboard demonstrating a
traceable flood-analysis workflow. **Demonstration case: Mahanadi
Basin, Odisha** (Naraj gauge currently selected) — the system itself is
region-independent by design; another CWC forecast site's data can be
substituted without redesigning the application (see "Architecture
note" below). Built entirely from datasets already verified earlier in
this project. **No fabricated flood predictions, danger levels, or
unvalidated accuracy figures are shown anywhere.**

## What this is (and isn't)

A **flood inundation analysis and decision-support prototype**, not an
operational forecasting system. Every number and layer on screen is labelled:

- **OBSERVED** — a direct measurement (CWC gauge reading, SRTM elevation,
  Sentinel-1 scene metadata)
- **HISTORICAL** — an official past record from a third party (NDEM/NRSC
  inundation extent for a real August 2022 date)
- **DERIVED** — computed here from verified inputs, shown clearly as such
  (calibrated SAR sigma0, the SAR candidate flood mask, NDEM inundated-area
  statistics, the relative elevation scenario)
- **REFERENCE** — an independent dataset used only to evaluate a derived
  result (NDEM, used to validate — not create — the SAR candidate mask)
- **PENDING** — explicitly not yet available (18-Aug noise correction,
  the CWC/DEM vertical-datum crosswalk, the exposure/infrastructure layer)

## Run it locally

No build step, no npm install at runtime, no database, **no internet
connection required** — Leaflet and Chart.js are vendored locally under
`vendor/` (map basemap tiles still need internet, like any web map; all
other functionality works fully offline):

```bash
cd naraj_dashboard
python3 -m http.server 8080
```

Open **http://localhost:8080**.

## Features (upgrade from the first prototype)

1. **Multi-station view** — all 58 real CWC stations shown as map
   markers (from the verified CWC dataset). Naraj, Alipingal, and
   Nimapara are the three "focus" stations with full daily charts and
   click-to-select (via map marker or sidebar chip); the other 55 show
   verified summary stats on click.
2. **Historical event explorer** — the August 2022 timeline (16/18/19/21)
   drives both the map layer and the evidence card; every field is
   status-tagged.
3. **Pre-flood/during-flood SAR comparison** — a swipe or opacity-blend
   comparison of real, uncalibrated Sentinel-1 VV digital numbers for
   6-Aug vs 18-Aug at the Naraj barrage, with verified orbit/coverage
   metadata alongside. Explicitly captioned as not a flood
   classification.
4. **Historical inundation view with DERIVED area** — the four verified
   NDEM layers, each with an inundated area computed directly from the
   polygon geometry (projected CRS, not fabricated), labelled DERIVED.
5. **Terrain-based scenario (prototype only)** — an interactive DEM
   threshold demo using *relative* elevation (meters above the AOI's
   lowest point), deliberately **not** converted to or compared against
   any CWC gauge reading, because that vertical-datum crosswalk is still
   unresolved.
6. **Data confidence panel** — one glance at what's VERIFIED vs PENDING
   across every input, plus an expandable full-provenance panel for
   anyone who wants the underlying detail.
7. **Exposure analysis UI** — the interface exists and is wired up, but
   contains no data, because no verified infrastructure/exposure layer
   exists in this project. Shown as "Pending data," not populated with
   anything invented.
8. **Judge-facing summary strip** — always visible: selected station,
   event/date, observed CWC level, satellite evidence, historical
   inundation availability, processing status, and confidence — updates
   live as you interact with the map/timeline/station selector.

## Data provenance (source of every file in `data/`)

| File(s) | Derived from | Verified in |
|---|---|---|
| `data/cwc/*.json`, `data/cwc_stations.geojson` | `rwl_manual_hr_cwc_005_2021_2025.csv` (verified CWC dataset) — all 58 stations, full daily series for the 3 focus stations | `data_quality_report.md`, `station_summary.csv` |
| `data/dem/*` | SRTM tile N20E085 (verified), AOI-clipped, color-mapped for display only — source `.bil` unmodified | `DATA_ACQUISITION_STATUS.md` §1A |
| `data/naraj_gauge.geojson`, `data/naraj_aoi.geojson` | Naraj coordinates from the CWC CSV; AOI box as defined in `DATA_ACQUISITION_PLAN.md` | `DATA_ACQUISITION_PLAN.md` §A |
| `data/ndem/*.geojson`, `data/ndem_inundated_area.json` | Verified NDEM/NRSC inundation layers (unmodified geometry); area is computed (DERIVED), not copied from any report | `DATA_ACQUISITION_STATUS.md` §3 |
| `data/sentinel1/*_footprint.geojson`, `scenes_metadata.json` | Verified `manifest.safe` fields for the 6-Aug and 18-Aug products | `S1_18AUG2022_PIXEL_VALIDATION.md`, `SENTINEL_PRE_FLOOD_SCENE_COMPARISON.md` |
| `data/sentinel1/naraj_crop_*.png` | Raw, uncalibrated VV digital numbers cropped near Naraj from the verified 6-Aug/18-Aug measurement TIFFs, percentile-stretched for display only | Same as above; TIFFs themselves not modified, only read |
| `data/terrain_scenario_grid.json` | Verified SRTM DEM, downsampled, converted to *relative* elevation (meters above AOI minimum) — no datum conversion applied | `DATA_ACQUISITION_STATUS.md` §1A.6 |
| `data/confidence_panel.json`, `data/exposure_layers.json`, `data/data_sources.json` | Hand-written summaries matching the verified reports; `exposure_layers.json` intentionally has an empty `available_layers` list | — |

**No source dataset (CWC CSV, SRTM `.bil`, NDEM GeoJSONs, Sentinel-1 SAFE
files) was modified or overwritten** — everything under `data/` is either
an unmodified copy or an explicitly-labelled derived product.

## Architecture note: adding the SAR flood mask later

`data/layers.json` drives the map-layer list and sidebar toggles. It
already includes a placeholder entry (`sar_flood_mask_06_18aug`) with
`"file": null`. **To activate it once calibration is complete:** set
`"file"` to the calibrated flood-mask GeoJSON's path and change
`"status"` to `"DERIVED"`. It will appear in the sidebar and on the map
automatically — no HTML/CSS/JS changes needed. The same pattern applies
to the exposure layer (`data/exposure_layers.json`) once verified
infrastructure data exists.

## Explicitly not built (by design, per project scope)

Authentication, deployment config, a database, user accounts, chatbot/AI
features.
 -->
# FloodWatch – Flood Intelligence Dashboard

## Overview

FloodWatch is an integrated flood intelligence and decision-support
dashboard developed for flood monitoring and forecasting.

The system combines:

- CWC rainfall observations
- CWC river/water-level observations
- Historical flood information
- Sentinel-1 SAR flood evidence
- DEM/terrain information
- Machine-learning based flood forecasting
- Interactive GIS visualization

## System Architecture

CWC Rainfall
       +
CWC River Levels
       +
Historical Flood Data
       ↓
Feature Engineering
       ↓
Random Forest Models
       ↓
6h / 12h / 24h Flood Forecast

Sentinel-1 SAR + DEM
       ↓
Flood Inundation Analysis
       ↓
Interactive GIS Dashboard

## Machine Learning

Three Random Forest models are trained for:

- 6-hour flood forecasting
- 12-hour flood forecasting
- 24-hour flood forecasting

The models use rainfall, water levels, temporal features,
lag features, changes, rolling statistics and historical flood
information.

## Data

The forecasting dataset was constructed from CWC observations
covering 2021–2025.

The final forecast dataset contains:

- 43,800 rows
- 71 input features
- 6-hour target
- 12-hour target
- 24-hour target

**Provenance:** this dataset is published on Hugging Face at
[`bhoomig0630/flood-inundation-upload`](https://huggingface.co/datasets/bhoomig0630/flood-inundation-upload)
(`ml/data/forecast/forecast_dataset.csv`) and was built by the `ml/src/`
pipeline in [`Bhoomig30/flood_inun`](https://github.com/Bhoomig30/flood_inun)
from real CWC records (10 rain gauges + the Naraj/Alipingal/Nimapara water
levels, 2021–2025). **No synthetic rows.** The serving Random Forests
(`ml_train.py` → `data/ml_models/hf_forecast_*.pkl`) train directly on that
file — see `README_FORECASTING.md` for the chronological-split methodology
and honest holdout skill report.

**Past-floods register:** `data/events_all_years.json` lists **25 real flood
events across 2021–2025** — every span where the real CWC record shows Naraj
above the 24.28 m danger level — plus the 4 satellite-verified NDEM events of
August 2022 (flagged `NDEM verified`/`SAR`). Events without digitized
satellite extents honestly show "Not available" rather than borrowing
another date's flood layer; the map clears any stale layer when such an
event is selected.

## API

Start the API:

```powershell
cd naraj_dashboard
python .\api\main.py