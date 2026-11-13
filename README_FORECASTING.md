# FloodWatch India — what changed and how to run

## Architecture: one selected location drives everything

```
USER SELECTS LOCATION (search / geolocation / map click / station click)
        ↓
FloodWatchState.selectedLocation      ← app.js, single source of truth
        ↓  setSelectedLocation()  (the ONLY entry point)
┌────────────────────────────────────────────────────────┐
│ every Leaflet map recenters (registered in FloodWatchState.maps) │
│ stale user/station markers removed (locationLayers cleared)      │
│ /api/location → nearest real CWC rainfall + river stations       │
│ rainfall / river cards update (or honest "none nearby")          │
│ AI-forecast scope message for the selected location              │
│ satellite / past-floods availability notices                     │
└────────────────────────────────────────────────────────┘
        ↓
dashboard updates — no page reload, no stale markers/layers
```

## Real data sources (no synthetic data anywhere)

| Dataset | Scope | Used by |
| --- | --- | --- |
| `data/india_cwc/stations.json` | **India-wide**: 842 CWC stations / 28 states, built from the real state-wise rainfall CSVs (2021–2025) + river-discharge CSVs (1970–2025) on the project's Hugging Face dataset (`bhoomig0630/flood-inundation-upload`) | `/api/location`, India Stations pane, station markers |
| `data/cwc/*` Naraj/Alipingal/Nimapara | Study region (Mahanadi), verified hourly/daily series | forecast model + "Historical study stations" chart (clearly labelled) |
| `data/events_all_years.json` | Study-region flood events 2021–2025 (real CWC-derived) + 4 satellite-verified NDEM events | Past Floods pane (labelled study-region) |
| SAR/DEM/NDEM rasters | Study region AOI | Flood Map & Satellite panes (labelled; hidden by default) |

The **AI forecast model is calibrated for the Naraj/Cuttack study region only**.
For any other location the dashboard shows:
"AI forecast model currently calibrated for the Naraj/Cuttack study region.
Location-specific prediction is not available for this location yet."
No India-wide probability is ever fabricated.

## Run

### Node server (dashboard + API, one port)

```bash
cd naraj_dashboard
npm start            # or: node server.js   (PORT/HOST env optional)
# → http://127.0.0.1:8080
```

### Python API (same feature set, port 8000 by default)

```bash
cd naraj_dashboard
python3 api/main.py            # PORT env overrides
# → http://127.0.0.1:8000
```

### Frontend via Live Server / any static host

`index.html` auto-detects same-origin (`window.FLOODWATCH_API_BASE = ""`), so
opening it through the API server (either of the above) is enough. If you serve
the folder statically elsewhere, set `FLOODWATCH_API_BASE` to the API origin in
`index.html` (one line) — CORS is already `*` on both servers.

### Rebuild the India station registry (only if the CWC CSVs change)

```bash
python3 scripts/build_india_registry.py --src ml/data/external
# (downloads layout also supported; see --help)
```

## Models

The dashboard's forecast bundles live in `naraj_dashboard/data/ml_models/`:
`hf_forecast_6h.pkl`, `hf_forecast_12h.pkl`, `hf_forecast_24h.pkl`, plus
`hf_forecast_metadata.json`. They were built with **scikit-learn 1.7.x**, so keep
the `>=1.3,<1.8` pin in `requirements.txt` — pickling/unpickling across a major
minor boundary is not guaranteed, and `ml_train.py` uses an API that 1.8+ removed.
Retrain with `python naraj_dashboard/ml_train.py` (reads the tracked
`naraj_dashboard/data/hf/forecast_dataset.csv`).

**Current state of this repo:** those three `.pkl` files **are tracked in git**
(`git ls-files | grep pkl` lists them), so a fresh clone already has them. They were
added with `git add -f` because `.gitignore` excludes `*.pkl` — meaning any bundle
you regenerate is **ignored by git** and will not show up as a change unless you
force-add it again.

If the bundles are missing or need regenerating:

```bash
# 1) Train from the dataset that ships with the repo
#    (naraj_dashboard/data/hf/forecast_dataset.csv, tracked, 43,800 rows)
pip install -r requirements.txt
python naraj_dashboard/ml_train.py      # writes the 3 bundles + metadata

# 2) Or download the Hugging Face copies
pip install huggingface_hub             # not in requirements.txt
python ml/hf_data.py download --pattern "ml/data/models/*"
```

Downloading from Hugging Face fetches `ml/data/models/flood_forecast_{6,12,24}h.pkl`
(and their imputers) — the older bundle path, *not* the `hf_forecast_*.pkl` files
this dashboard loads, so you still need `ml_train.py` for a working dashboard.
The same folder also holds the large spatial models
(`random_forest_flood.pkl` 1.8 GB, `random_forest_flood_12features.pkl` 2.9 GB).
A download of everything is several GB; use `--pattern` to narrow it.

`requirements.txt` pins `scikit-learn>=1.3,<1.8`. `ml_train.py` now calibrates with
`FrozenEstimator` (scikit-learn ≥ 1.6) and only falls back to the removed
`cv="prefit"` API on older versions, so it *runs* on 1.7 and 1.9. The upper bound
stays because 1.9 does not reproduce the committed numbers (6h holdout ROC-AUC
0.9955 vs 0.9921) and unpickling the 1.7.2-built bundles there raises
`InconsistentVersionWarning`. Retrain on 1.7.x to match `hf_forecast_metadata.json`.

Persistence-baseline check (optional, no training):

```bash
python ml/src/baseline_skill.py    # writes data/ml_models/hf_forecast_baseline.json
```

It scores a "flood if today's level is already above 24.28 m" rule on the same
chronological holdout and exposes the comparison at `/api/model/info`
(`baseline_skill`) and on the research page.

Smoke tests (start their own server on a free port):

```bash
python tests/test_forecast_api.py -v
```

### Scheduled CWC ingestion (keep the forecast anchor current)

`scripts/ingest_cwc.py` pulls the newest CWC observations, appends the new
records to `data/cwc/<station>_daily_2021_2025.json` (history is never
rewritten), rebuilds the 71-feature frame and appends only rows newer than the
served dataset, then writes `data/cwc/ingestion_status.json`. The ML service
reloads the frame on change, so no restart is needed.

```bash
python3 scripts/ingest_cwc.py --once --dry-run          # parse + report, change nothing
python3 scripts/ingest_cwc.py --once --levels-csv <path-or-url>
python3 scripts/ingest_cwc.py --watch --interval-minutes 360
npm run ingest:cwc                                      # same as --once
```

Cron example (every 6 hours):

```cron
0 */6 * * * cd /path/to/flood_inun && .venv/bin/python scripts/ingest_cwc.py --once >> artifacts/ingest.log 2>&1
```

Sources and limits:

| Input | Where it comes from |
| --- | --- |
| Hourly rainfall | `--rain-csv` (default: Odisha 2021-2025 export from the Hugging Face dataset, cached 6 h) |
| Hourly water levels | `--levels-csv` only — the CWC manual hourly water-level export is **not** in the Hugging Face dataset |

If no newer water-level export is supplied, the run completes, refreshes
rainfall, and reports `stale: true` with the blocker instead of reusing an old
anchor silently. `GET /api/health` exposes the same report under
`data_freshness` (`latest_observation`, `age_days`, `stale`, `blockers`).

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/location?latitude=..&longitude=..` | Nearest real CWC rainfall + river stations with `distance_km`, latest observations, `no_nearby_station` status when nothing is within radius (300 km rainfall / 400 km river), plus `model_scope` |
| `GET /api/stations/india_cwc?q=&type=rainfall\|river&state=&latitude=&longitude=&limit=` | India-wide registry with filters + distance sort |
| `GET /api/forecast?station=naraj\|alipingal\|nimapara` | 6/12/24h ensemble (statistical engine + RF for Naraj), honest scope labels |
| `GET /api/model/info` | Training metadata, HF/GitHub provenance, holdout skill |
| `GET /api/stations/india?q=&basin=&state=` | Curated river-gauge registry (basin explorer) |
| `GET /api/levels/recent?station=`, `/api/forecast/backtest`, `/api/health` | Chart series, causal evaluation, health |

### Forecast anchors

`/api/forecast` reports two as-of moments in `forecast_anchors`, because the two
components read different sources. The RF (`ml_result.as_of`) is anchored to the
last row of `data/hf/forecast_dataset.csv`; the statistical engine
(`reference_time`, from its Aug-2022 hourly file) cannot move past
`calibration.hourly_end` without hourly history. While those differ,
`anchors_aligned` is `false`, `ensemble_mixes_anchors` is `true`, and the blended
`flood_probability_percent` combines the two moments — the card labels both.
`observation_freshness.latest_observation` is the newest of the two (the ML row
when the bridge is active) and its age is reported against a 48 h threshold.
An explicit `?reference_time=` still pins both components, for back-testing.

## Key files

- `app.js` — single source of truth (`FloodWatchState`), location pipeline, forecast card, markers
- `public.js` — maps (India-wide default), panes, event timeline, India Stations registry explorer
- `location_service.js` — Node nearest-station lookup over the real registry
- `api/main.py` — Python API parity (same endpoints, same honesty rules)
- `server.js` — Node API + static serving
- `scripts/build_india_registry.py` — builds `data/india_cwc/stations.json` from the real CWC CSVs
- `research.html` + `research.js` — Technical View (architecture, SAR method, validation, model scope, limitations)

## Verification performed (headless browser against the real files)

- Searched Assam / Delhi / Kerala: map view moved, selected-location marker
  moved with each search, nearest real stations changed per location, Kerala
  honestly shows "no nearby CWC river station within 400 km"
- Station markers from the previous location removed before each new render
- Flood Map: study-region layers built but OFF by default; AI-scene button and
  layer toggles re-enable them; stale event layers cleared on event change
- Forecast card: real RF ensemble output, honest "Historical-data AI forecast …
  not a live government flood warning" status, scope message per location
- India Stations pane: 842/842 real stations, type/state filters, distance sort
- Research view: 6 tabs, 18 map layers, 4-step evolution timeline, station
  charts, validation metrics, confidence grid — zero page errors
