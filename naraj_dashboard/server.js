// ============================================================================
// FLOODWATCH — PREVIEW / API SERVER (plain Node, no dependencies)
// Serves the static dashboard AND the prediction API on one port.
// Runs anywhere Node runs (Freebuff preview is Node-only).
// ============================================================================

const http = require("http");
const fs = require("fs");
const path = require("path");
const {
  predictor,
  stationByKey,
  STATIONS,
} = require("./prediction_engine.js");
const locationService = require("./location_service.js");
const { locationLookup } = locationService;
const { mlBridge } = require("./ml_bridge.js");

// Resolve a station definition from a query param (default: Naraj).
function stationDef(key) {
  const def = stationByKey(key);
  return STATIONS.find((s) => s.key === def.key) || STATIONS[0];
}

// Cached model metadata for /api/model/info
// v3 models are trained on the REAL Hugging Face dataset
// (bhoomig0630/flood-inundation-upload, built from CWC 2021-2025 records
// by the project's own ml/src/build_forecast_dataset.py pipeline).
let modelInfoCache = null;
function modelInfo() {
  if (modelInfoCache) return modelInfoCache;
  let meta = null;
  try {
    meta = JSON.parse(
      fs.readFileSync(path.join(__dirname, "data", "ml_models", "hf_forecast_metadata.json"), "utf8")
    );
  } catch (err) {
    meta = null;
  }
  modelInfoCache = {
    status: meta ? "trained" : "unavailable",
    trained_at: meta ? meta.trained_at : null,
    version: meta ? meta.version : null,
    data_source: meta ? meta.data_source : null,
    dataset: meta ? meta.dataset : null,
    label_rule: meta
      ? `Naraj level exceeds ${meta.dataset ? meta.dataset.flood_threshold_m : 24.28} m (95th percentile of the 2021-2025 record) within the next horizon`
      : null,
    n_rows: meta && meta.dataset ? meta.dataset.rows : null,
    splits: meta ? meta.split : null,
    features: meta ? meta.features : [],
    horizons: meta ? meta.models : {},
    notes: meta
      ? meta.notes || [
          "Trained ONLY on the real CWC-derived dataset (no synthetic data).",
          "Skill is reported on a strict chronological holdout — the final 15% of the record, never seen during training.",
          "A frozen CWC gauge (constant level for days) has features nearly identical to safe hours, so the ML component can under-read plateaus at exactly the danger level; the statistical engine covers that case in the ensemble.",
        ]
      : ["Run ml_train.py (requires data/hf/forecast_dataset.csv from the Hugging Face dataset) to train the models."],
    ml_bridge: mlBridge.status(),
  };
  return modelInfoCache;
}

const PORT = Number(process.env.PORT) || 8080;
const HOST = process.env.HOST || "0.0.0.0";
const ROOT = __dirname;

// ---------------------------------------------------------------------------
// PROCESS RESILIENCE — the server must never die from a stray async error.
// (A single unhandled rejection used to kill the whole dashboard mid-session.)
// ---------------------------------------------------------------------------
process.on("uncaughtException", (err) => {
  console.error("[uncaughtException] server kept alive:", err && err.stack ? err.stack : err);
});
process.on("unhandledRejection", (reason) => {
  console.error("[unhandledRejection] server kept alive:", reason && reason.stack ? reason.stack : reason);
});

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".map": "application/json",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function sendJSON(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Content-Length": Buffer.byteLength(body),
  });
  res.end(body);
}

function serveStatic(res, urlPath) {
  let rel = decodeURIComponent(urlPath);
  if (rel === "/" || rel === "") rel = "/index.html";

  // Security: stay inside ROOT
  const full = path.normalize(path.join(ROOT, rel));
  if (!full.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end("Forbidden");
  }

  fs.stat(full, (err, stat) => {
    if (err || !stat.isFile()) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      return res.end("Not found: " + rel);
    }
    const ext = path.extname(full).toLowerCase();
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      "Content-Length": stat.size,
      "Cache-Control": "no-cache",
    });
    fs.createReadStream(full).pipe(res);
  });
}

const server = http.createServer((req, res) => {
  handleRequest(req, res).catch((err) => {
    console.error("[request error]", req.url, err && err.stack ? err.stack : err);
    if (!res.headersSent) {
      try {
        res.writeHead(500, { "Content-Type": "application/json; charset=utf-8" });
      } catch (e) {}
    }
    try {
      res.end(JSON.stringify({ status: "error", error: "Internal server error: " + (err && err.message ? err.message : String(err)) }));
    } catch (e) {}
  });
});

async function handleRequest(req, res) {
  // Normalize doubled slashes (e.g. "//") so URL parsing never throws.
  const safeUrl = String(req.url || "/").replace(/\/{2,}/g, "/");
  const parsed = new URL(safeUrl, "http://localhost");
  const pathname = parsed.pathname;

  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    });
    return res.end();
  }

  if (req.method !== "GET") {
    return sendJSON(res, 405, { status: "error", error: "Method not allowed" });
  }

  // ------------------------------------------------------------------
  // API: health
  // ------------------------------------------------------------------
  if (pathname === "/api" || pathname === "/api/health") {
    // Registry status (cached load; cheap after first read).
    let registryStatus = { stations: 0, states: 0, loaded: false };
    try {
      const reg = locationService.loadRegistry();
      if (reg && Array.isArray(reg.stations) && reg.stations.length) {
        const counts = (reg.meta && reg.meta.counts) || {};
        registryStatus = {
          loaded: true,
          stations: counts.total || reg.stations.length,
          states: counts.states || 0,
          generated_at: (reg.meta && reg.meta.generated_at) || null,
        };
      }
    } catch (err) { /* registry optional — reported as not loaded */ }
    let modelInfoStatus = null;
    try {
      const mi = modelInfo();
      modelInfoStatus = {
        trained_at: (mi && mi.trained_at) || null,
        horizons: mi && mi.horizons ? Object.keys(mi.horizons) : [],
        version: (mi && mi.version) || null,
      };
    } catch (err) { /* model info optional */ }
    let datasetStatus = { data_notice: null };
    try {
      datasetStatus.data_notice = locationLookup(20.5, 85.95).data_notice;
    } catch (err) { /* non-fatal */ }
    return sendJSON(res, 200, {
      status: "online",
      service: "FloodWatch Flood Intelligence API",
      api_version: "2.2",
      version: "2.2.0",
      server_time: new Date().toISOString(),
      forecast_engine: predictor.loaded ? "ready" : "not_loaded",
      forecast_status: predictor.loaded ? "ready" : "not_loaded",
      ml_model: modelInfoStatus,
      station_registry: registryStatus,
      datasets: {
        india_cwc_registry: registryStatus.loaded ? "available" : "unavailable",
        study_region_records: "available",
        note: datasetStatus.data_notice,
      },
      endpoints: [
        "/ (dashboard)",
        "/api/forecast?reference_time=<optional ISO time>",
        "/api/forecast?latitude=..&longitude=.. (coverage-gated)",
        "/api/current-condition?latitude=..&longitude=..",
        "/api/forecast/coverage?latitude=..&longitude=..",
        "/api/forecast/backtest",
        "/api/levels/recent",
        "/api/model/info",
        "/api/location?latitude=..&longitude=..",
        "/api/stations",
        "/api/stations/india?q=..&basin=..&state=..",
        "/api/stations/india_cwc?q=..&type=rainfall|river&state=..&latitude=..&longitude=..",
        "/api/health",
      ],
    });
  }

  // ------------------------------------------------------------------
  // API: 6/12/24h prediction (statistical engine + ML ensemble info)
  // ------------------------------------------------------------------
  if (pathname === "/api/forecast") {
    const referenceTime = parsed.searchParams.get("reference_time");
    const stationKey = parsed.searchParams.get("station");

    // COVERAGE GATE: optional latitude/longitude. When the caller supplies a
    // location OUTSIDE the Naraj/Cuttack calibration radius, the trained
    // study model is NOT applied — we return an explicit, honest refusal
    // instead of a misattributed probability.
    // NOTE: presence must be checked on the RAW strings — Number(null) is 0,
    // which would silently turn "no coordinates" into (0,0) and wrongly gate
    // station-key forecasts like /api/forecast?station=naraj.
    const latRaw = parsed.searchParams.get("latitude");
    const lonRaw = parsed.searchParams.get("longitude");
    const coordsSupplied =
      latRaw !== null && lonRaw !== null && latRaw !== "" && lonRaw !== "";
    const qLat = Number(latRaw);
    const qLon = Number(lonRaw);
    const hasCoords =
      coordsSupplied &&
      Number.isFinite(qLat) && Number.isFinite(qLon) &&
      qLat >= -90 && qLat <= 90 && qLon >= -180 && qLon <= 180;
    if (hasCoords) {
      const coverage = locationService.forecastCoverage(qLat, qLon);
      if (!coverage.available) {
        return sendJSON(res, 200, {
          status: "outside_model_calibration",
          forecast: null,
          coverage,
          present_condition_note:
            "Present-condition observations for this location are served by " +
            "/api/current-condition and remain available.",
          warning:
            "The trained Random Forest is calibrated on the Naraj/Cuttack " +
            "study region only. No fabricated probability is returned for " +
            "other locations.",
        });
      }
    }

    const result = predictor.predict(referenceTime, stationKey);

    // Attach ML ensemble output when the bridge is available.
    // The pooled Random Forests are SERVED through the Naraj feature
    // pipeline (ml_serve.py TARGET), so the ML component is only blended
    // for Naraj — other stations get the statistical engine, honestly
    // labelled, rather than a misattributed ML probability.
    const mlCapableStation = !stationKey || stationByKey(stationKey).key === "naraj";
    if (result.status === "success") {
      result.ml = mlBridge.status();
      result.ml_capable = mlCapableStation;
      if (mlBridge.status().available && mlCapableStation) {
        // Align the ML component to the SAME as-of moment as the statistical
        // engine (result.reference_time) so the ensemble never mixes moments —
        // e.g. live mode serves the engine's latest verified observation
        // (2022-08-31), and the ML row for that exact hour is used, not a
        // later row from the 2021-2025 dataset.
        const mlRef = referenceTime || result.reference_time || null;
        const ml = await mlBridge.predict(mlRef);
        if (ml.ok && ml.horizons) {
          result.ml_enabled = true;
          result.ml_result = { as_of: ml.as_of, horizons: ml.horizons };
          for (const h of ["6h", "12h", "24h"]) {
            const mlP01 =
              ml.horizons[h] && Number.isFinite(ml.horizons[h].probability)
                ? ml.horizons[h].probability
                : null;
            if (mlP01 !== null && result.forecast[h]) {
              // Ensemble: 60% statistical engine (level/percentile physics,
              // recession-aware) + 40% calibrated Random Forest trained on
              // the real 2021-2025 CWC dataset (22 flood events, 5 monsoons).
              // The v3 RF has a measured 0.3-0.5% mean false-alarm rate on
              // safe holdout hours, so no recession discount is needed.
              const mlP = Math.round(mlP01 * 10000) / 100; // -> percent, 2dp
              const mlWeight = 0.4;
              const blended =
                (1 - mlWeight) * result.forecast[h].flood_probability_percent +
                mlWeight * mlP;
              result.forecast[h].ml_probability_percent = mlP;
              result.forecast[h].ml_weight = mlWeight;
              result.forecast[h].flood_probability_percent =
                Math.round(blended * 100) / 100;
              result.forecast[h].risk = predictor.riskBand(
                result.forecast[h].flood_probability_percent
              );
            }
          }
          const probs = ["6h", "12h", "24h"].map(
            (h) => result.forecast[h].flood_probability_percent
          );
          result.overall_risk = predictor.riskBand(Math.max(...probs));
        }
      }
    }

    return sendJSON(res, 200, result);
  }

  // ------------------------------------------------------------------
  // API: causal backtest against the verified NDEM events
  // ------------------------------------------------------------------
  if (pathname === "/api/forecast/backtest") {
    return sendJSON(res, 200, predictor.backtest());
  }

  // ------------------------------------------------------------------
  // API: available forecast stations
  // ------------------------------------------------------------------
  if (pathname === "/api/stations") {
    return sendJSON(res, 200, {
      status: "success",
      stations: predictor.stationList(),
    });
  }

  // Pan-India curated station registry (with optional q / basin / state filters)
  if (pathname === "/api/stations/india") {
    const q = (parsed.searchParams.get("q") || "").trim().toLowerCase();
    const basin = parsed.searchParams.get("basin") || "all";
    const state = parsed.searchParams.get("state") || "all";
    let stations = [];
    try {
      const raw = fs.readFileSync(
        path.join(__dirname, "data", "india_stations.json"),
        "utf8"
      );
      stations = (JSON.parse(raw).stations || []).filter((s) => {
        if (basin !== "all" && s.basin !== basin) return false;
        if (state !== "all" && s.state !== state) return false;
        if (q) {
          const hay = (s.name + " " + s.river + " " + s.state + " " + (s.district || "")).toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });
    } catch (err) {
      return sendJSON(res, 200, {
        status: "unavailable",
        error: "Registry file missing: " + err.message,
        stations: [],
      });
    }
    return sendJSON(res, 200, { status: "success", count: stations.length, stations });
  }

  // ------------------------------------------------------------------
  // API: recent observed hourly levels (last 72h of the record)
  // ------------------------------------------------------------------
  if (pathname === "/api/levels/recent") {
    predictor.load();
    const stationKey = parsed.searchParams.get("station");
    const def = stationDef(stationKey);
    const st = predictor.loaded ? predictor.stations[def.key] : null;
    if (!st) {
      return sendJSON(res, 200, { timestamps: [], levels: [] });
    }
    const hr = st.hourly.slice(-72);
    return sendJSON(res, 200, {
      station: def.name,
      station_key: def.key,
      monsoon_p95_m: Number(st.calibration.monsoon_p95_m.toFixed(2)),
      timestamps: hr.map((r) => r.time.toISOString()),
      levels: hr.map((r) => r.level),
    });
  }

  // ------------------------------------------------------------------
  // API: model metadata (training info for the UI panel)
  // ------------------------------------------------------------------
  if (pathname === "/api/model/info") {
    return sendJSON(res, 200, modelInfo());
  }

  // ------------------------------------------------------------------
  // API: export the current forecast as JSON or CSV
  // ------------------------------------------------------------------
  if (pathname === "/api/forecast/export") {
    const referenceTime = parsed.searchParams.get("reference_time");
    const stationKey = parsed.searchParams.get("station");
    const format = (parsed.searchParams.get("format") || "json").toLowerCase();
    const result = predictor.predict(referenceTime, stationKey);

    if (format === "csv") {
      const rows = [
        "horizon,flood_probability_percent,risk,projected_rise_m,ml_probability_percent",
      ];
      for (const h of ["6h", "12h", "24h"]) {
        const f = result.forecast[h] || {};
        rows.push(
          [
            h,
            f.flood_probability_percent !== undefined
              ? f.flood_probability_percent
              : "",
            f.risk || "",
            f.projected_rise_m !== undefined ? f.projected_rise_m : "",
            f.ml_probability_percent !== undefined ? f.ml_probability_percent : "",
          ].join(",")
        );
      }
      rows.push("");
      rows.push("# project,FloodWatch — India Flood Intelligence Platform");
      rows.push("# forecast_type,Historical-data AI forecast (NOT a live government warning)");
      rows.push("# model_name," + (result.model_name || "FloodWatch Future Flood Forecast"));
      rows.push("# algorithm," + (result.algorithm || "Random Forest"));
      rows.push("# model_scope," + (result.study_region || "Naraj/Cuttack, Odisha (NOT India-wide calibrated)"));
      rows.push("# station," + (result.location ? result.location.station : "Naraj") + " (CWC verified data)");
      rows.push(
        "# location_coordinates," +
          ((result.location && result.location.latitude) || "") + "," +
          ((result.location && result.location.longitude) || "")
      );
      rows.push("# observation_time," + (result.reference_time || ""));
      rows.push("# data_source,CWC historical telemetry (rainfall + water level), Hugging Face bhoomig0630/flood-inundation-upload");
      rows.push(
        "# warning," +
          (result.warning ||
            "Generated from historical CWC data — not a live government flood warning.")
      );
      const csv = rows.join("\n");
      res.writeHead(200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition":
          'attachment; filename="floodwatch_forecast.csv"',
        "Access-Control-Allow-Origin": "*",
      });
      return res.end(csv);
    }

    return sendJSON(res, 200, result);
  }

  // ------------------------------------------------------------------
  // API: nearest CWC stations (from verified dashboard data + CSVs)
  // ------------------------------------------------------------------
  if (pathname === "/api/location") {
    const latitude = Number(parsed.searchParams.get("latitude"));
    const longitude = Number(parsed.searchParams.get("longitude"));

    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      latitude < -90 ||
      latitude > 90 ||
      longitude < -180 ||
      longitude > 180
    ) {
      return sendJSON(res, 400, {
        status: "error",
        error: "Valid latitude and longitude are required.",
      });
    }

    return sendJSON(res, 200, locationLookup(latitude, longitude));
  }

  // ------------------------------------------------------------------
  // API: PRESENT CONDITION — analytical status from REAL observations
  // only (independent of the ML forecast model).
  // ------------------------------------------------------------------
  if (pathname === "/api/current-condition") {
    const latitude = Number(parsed.searchParams.get("latitude"));
    const longitude = Number(parsed.searchParams.get("longitude"));

    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      latitude < -90 ||
      latitude > 90 ||
      longitude < -180 ||
      longitude > 180
    ) {
      return sendJSON(res, 400, {
        status: "error",
        error: "Valid latitude and longitude are required.",
      });
    }

    return sendJSON(res, 200, locationService.currentCondition(latitude, longitude));
  }

  // ------------------------------------------------------------------
  // API: forecast coverage — where the trained model may honestly apply.
  // ------------------------------------------------------------------
  if (pathname === "/api/forecast/coverage") {
    const latitude = Number(parsed.searchParams.get("latitude"));
    const longitude = Number(parsed.searchParams.get("longitude"));
    if (
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude) ||
      latitude < -90 ||
      latitude > 90 ||
      longitude < -180 ||
      longitude > 180
    ) {
      return sendJSON(res, 400, {
        status: "error",
        error: "Valid latitude and longitude are required.",
      });
    }
    return sendJSON(res, 200, {
      status: "success",
      coverage: locationService.forecastCoverage(latitude, longitude),
    });
  }

  // ------------------------------------------------------------------
  // API: India-wide CWC registry (built from the real CWC datasets by
  // scripts/build_india_registry.py). Filters: q, type (rainfall|river),
  // state; optional latitude/longitude adds distance_km from a location.
  // ------------------------------------------------------------------
  if (pathname === "/api/stations/india_cwc") {
    const { loadRegistry, haversineKm } = require("./location_service.js");
    const reg = loadRegistry();
    if (!reg.stations.length) {
      return sendJSON(res, 200, {
        status: "unavailable",
        error:
          "India registry missing — run scripts/build_india_registry.py with the real CWC datasets.",
        stations: [],
      });
    }
    const q = (parsed.searchParams.get("q") || "").trim().toLowerCase();
    const type = (parsed.searchParams.get("type") || "all").toLowerCase();
    const state = parsed.searchParams.get("state") || "all";
    const lat = Number(parsed.searchParams.get("latitude"));
    const lon = Number(parsed.searchParams.get("longitude"));
    const useDist = Number.isFinite(lat) && Number.isFinite(lon);
    const limit = Math.min(Number(parsed.searchParams.get("limit")) || 2000, 2000);

    let out = [];
    for (const s of reg.stations) {
      if (type !== "all" && s.kind !== type) continue;
      if (state !== "all" && s.state !== state) continue;
      if (q) {
        const hay = [s.station, s.river, s.basin, s.state, s.district]
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) continue;
      }
      const row = Object.assign({}, s, { has_observation: !!s.latest_observation });
      if (useDist) {
        row.distance_km =
          Math.round(haversineKm(lat, lon, s.latitude, s.longitude) * 100) / 100;
      }
      out.push(row);
    }
    if (useDist) out.sort((a, b) => a.distance_km - b.distance_km);

    return sendJSON(res, 200, {
      status: "success",
      count: out.length,
      registry_meta: reg.meta,
      stations: out.slice(0, limit),
    });
  }

  // ------------------------------------------------------------------
  // Static files
  // ------------------------------------------------------------------
  serveStatic(res, pathname);
}

// Last-resort per-request guard: client disconnects must not crash (EPIPE/ECONNRESET)
server.on("request", (req, res) => {
  res.on("error", () => {});
  req.on("error", () => {});
});

server.listen(PORT, HOST, () => {
  console.log("FloodWatch server running at http://" + HOST + ":" + PORT);
  // Warm the predictor so first request is fast.
  predictor.load();
  if (predictor.loaded) {
    const totals = Object.values(predictor.stations).reduce(
      (acc, st) => ({
        daily: acc.daily + st.calibration.daily_records,
        hourly: acc.hourly + st.calibration.hourly_records,
      }),
      { daily: 0, hourly: 0 }
    );
    console.log(
      "Prediction engine ready (" +
        Object.keys(predictor.stations).length +
        " stations: " +
        totals.daily +
        " daily + " +
        totals.hourly +
        " hourly verified CWC records)."
    );
  } else {
    console.warn("Prediction engine failed to load: " + predictor.loadError);
  }
  // Start the ML bridge in the background (optional; statistical engine
  // works without it).
  mlBridge.start();
});
