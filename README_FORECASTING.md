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

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/location?latitude=..&longitude=..` | Nearest real CWC rainfall + river stations with `distance_km`, latest observations, `no_nearby_station` status when nothing is within radius (300 km rainfall / 400 km river), plus `model_scope` |
| `GET /api/stations/india_cwc?q=&type=rainfall\|river&state=&latitude=&longitude=&limit=` | India-wide registry with filters + distance sort |
| `GET /api/forecast?station=naraj\|alipingal\|nimapara` | 6/12/24h ensemble (statistical engine + RF for Naraj), honest scope labels |
| `GET /api/model/info` | Training metadata, HF/GitHub provenance, holdout skill |
| `GET /api/stations/india?q=&basin=&state=` | Curated river-gauge registry (basin explorer) |
| `GET /api/levels/recent?station=`, `/api/forecast/backtest`, `/api/health` | Chart series, causal evaluation, health |

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
