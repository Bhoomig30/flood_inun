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
const backtest = require("./backtest.js");

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
  // Persistence-baseline comparison (ml/src/baseline_skill.py), if generated.
  let baseline = null;
  try {
    baseline = JSON.parse(
      fs.readFileSync(path.join(__dirname, "data", "ml_models", "hf_forecast_baseline.json"), "utf8")
    );
  } catch (err) {
    baseline = null;
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
    baseline_skill: baseline
      ? {
          generated_at: baseline.generated_at,
          note: baseline.note,
          split: baseline.split,
          label: baseline.label,
          baselines: baseline.baselines,
          comparison: baseline.comparison,
        }
      : null,
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

// Comparable key for a timestamp regardless of whether it is ISO ("2022-08-31
// T00:00:00.000Z") or pandas-style ("2025-12-30 23:00:00"). Hour resolution is
// enough to decide whether two forecast components share an anchor.
function anchorKey(value) {
  if (!value) return null;
  const m = String(value).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!m) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}`;
}

// Same value, rendered for humans/labels ("2022-08-31 00:00").
function anchorLabel(value) {
  const key = anchorKey(value);
  return key ? key.replace("T", " ") : null;
}

// Latest row of the served dataset, used for the persistence indicator. Reads
// only the header and the tail of the CSV instead of loading the ~24 MB file.
let lastDatasetRowCache = null;
function datasetLastRow() {
  if (lastDatasetRowCache) return lastDatasetRowCache;
  const file = path.join(__dirname, "data", "hf", "forecast_dataset.csv");
  let fd = null;
  try {
    const size = fs.statSync(file).size;
    fd = fs.openSync(file, "r");
    const headBuf = Buffer.alloc(Math.min(8192, size));
    fs.readSync(fd, headBuf, 0, headBuf.length, 0);
    const header = headBuf.toString("utf8").split("\n")[0].replace(/\r$/, "").split(",");
    const tailLen = Math.min(65536, size);
    const tailBuf = Buffer.alloc(tailLen);
    fs.readSync(fd, tailBuf, 0, tailLen, size - tailLen);
    const lines = tailBuf.toString("utf8").split("\n").filter((l) => l.trim().length > 0);
    const values = lines[lines.length - 1].replace(/\r$/, "").split(",");
    const levelIdx = header.indexOf("naraj_water_level_m");
    if (levelIdx < 0) throw new Error("naraj_water_level_m column not found");
    lastDatasetRowCache = {
      timestamp: values[0],
      naraj_water_level_m: Number(values[levelIdx]),
    };
    return lastDatasetRowCache;
  } catch (err) {
    return null;
  } finally {
    if (fd !== null) {
      try {
        fs.closeSync(fd);
      } catch (e) {
        /* ignore */
      }
    }
  }
}

// Persistence check shown next to the ML probability: current Naraj level from
// the dataset's last row against the flood threshold the baseline used
// (hf_forecast_baseline.json -> label.threshold_m). Both are read from files.
function persistenceIndicator() {
  const info = modelInfo();
  const chain = info.baseline_skill && info.baseline_skill.label;
  const threshold = chain ? Number(chain.threshold_m) : NaN;
  const row = datasetLastRow();
  if (!row || !Number.isFinite(row.naraj_water_level_m) || !Number.isFinite(threshold)) {
    return { available: false, reason: "dataset row or baseline threshold unavailable" };
  }
  const level = row.naraj_water_level_m;
  return {
    available: true,
    station: "Naraj",
    level_m: level,
    level_as_of: row.timestamp,
    threshold_m: threshold,
    above_threshold: level >= threshold,
    margin_m: Math.round((level - threshold) * 100) / 100,
    level_source: "data/hf/forecast_dataset.csv (last row, naraj_water_level_m)",
    threshold_source: "data/ml_models/hf_forecast_baseline.json (label.threshold_m)",
  };
}

// ---------------------------------------------------------------------------
// FORECAST CAPABILITY TIERS
//   1 = trained RF headline (Naraj only)
//   2 = verified water-level series served by the legacy engine
//       (Naraj, Alipingal, Nimapara)
//   3 = registry metadata and rainfall observations only — NO probabilities
// Nothing outside the verified set may produce a forecast value.
// ---------------------------------------------------------------------------
const ML_MODEL_STATIONS = new Set(["naraj"]);
const VERIFIED_SERIES_STATIONS = new Set(["naraj", "alipingal", "nimapara"]);

function tierForStationKey(stationKey) {
  const key = String(stationKey || "").trim().toLowerCase();
  if (ML_MODEL_STATIONS.has(key)) return 1;
  if (VERIFIED_SERIES_STATIONS.has(key)) return 2;
  return 3;
}

function tierLabel(tier) {
  if (tier === 1) return "ML forecast";
  if (tier === 2) return "Observations + legacy engine";
  return "Station metadata only";
}

// Registry stations that correspond to a verified water-level series.
function verifiedKeyForName(name) {
  const n = String(name || "").trim().toLowerCase();
  return VERIFIED_SERIES_STATIONS.has(n) ? n : null;
}

function findRegistryStation(name, state) {
  if (!name) return null;
  let reg = { stations: [] };
  try {
    reg = locationService.loadRegistry();
  } catch (err) {
    return null;
  }
  const target = String(name).trim().toLowerCase();
  const matches = (reg.stations || []).filter(
    (s) => String(s.station || "").trim().toLowerCase() === target
  );
  if (!matches.length) return null;
  if (state) {
    const sameState = matches.filter(
      (s) => String(s.state || "").toLowerCase() === String(state).toLowerCase()
    );
    if (sameState.length) return sameState[0];
  }
  return matches[0];
}

function stationSummary(s) {
  if (!s) return null;
  return {
    name: s.station,
    state: s.state || null,
    district: s.district || null,
    river: s.river || null,
    kind: s.kind || null,
    latitude: s.latitude,
    longitude: s.longitude,
    n_obs: s.n_obs,
    latest_observation: s.latest_observation || null,
  };
}

// Resolve a `station` query param to a verified forecast key, or return a
// refusal payload so callers never receive another station's numbers.
function resolveForecastStation(stationParam, stateParam) {
  if (!stationParam) {
    return { key: "naraj", tier: 1, registry: findRegistryStation("Naraj", "Odisha") };
  }
  const direct = String(stationParam).trim().toLowerCase();
  if (VERIFIED_SERIES_STATIONS.has(direct)) {
    return { key: direct, tier: tierForStationKey(direct), registry: null };
  }
  const reg = findRegistryStation(stationParam, stateParam);
  if (reg) {
    const key = verifiedKeyForName(reg.station);
    if (key) return { key, tier: tierForStationKey(key), registry: reg };
    return { key: null, tier: 3, registry: reg };
  }
  return { key: null, tier: null, registry: null };
}

function unsupportedStationPayload(resolved) {
  if (!resolved.registry) {
    return {
      status: "unknown_station",
      forecast: null,
      forecast_tier: null,
      reason:
        "Station is not in the CWC registry used by this project, so no " +
        "observation or forecast can be shown.",
    };
  }
  return {
    status: "station_not_supported",
    forecast: null,
    forecast_tier: 3,
    forecast_tier_label: tierLabel(3),
    station: stationSummary(resolved.registry),
    ml_enabled: false,
    reason:
      "No verified hourly water-level series or trained forecast model " +
      "exists for this station in this project.",
    scope_note:
      "Forecasts are served for Naraj (trained Random Forest) and " +
      "Alipingal/Nimapara (verified series, legacy engine only).",
    warning:
      "This project does not invent probabilities for stations it was not " +
      "trained or verified on.",
  };
}

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
        const counts = reg.counts || (reg.meta && reg.meta.counts) || {};
        registryStatus = {
          loaded: true,
          stations: counts.total || reg.stations.length,
          states:
            counts.states ||
            (Array.isArray(reg.states) ? reg.states.length : 0),
          generated_at:
            reg.generated_at || (reg.meta && reg.meta.generated_at) || null,
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
    // Ingestion health: never present an old anchor as current observations.
    // The status file is a gitignored run snapshot, so a fresh clone has none.
    // In that case report "no ingestion run yet" and leave freshness unknown
    // instead of inventing a stale/current verdict.
    let dataFreshness = { status: "not_run" };
    let ingest = null;
    try {
      ingest = JSON.parse(
        fs.readFileSync(path.join(__dirname, "data", "cwc", "ingestion_status.json"), "utf8")
      );
    } catch (err) {
      ingest = null;
    }
    if (ingest) {
      dataFreshness = {
        status: ingest.status === "example" ? "example" : "reported",
        latest_observation: ingest.latest_observation || null,
        age_days: ingest.age_days === undefined ? null : ingest.age_days,
        stale: typeof ingest.stale === "boolean" ? ingest.stale : null,
        stale_after_days: ingest.stale_after_days,
        last_ingestion_utc: ingest.last_run_utc || null,
        water_levels_source: ingest.source ? ingest.source.water_levels : null,
        blockers: Array.isArray(ingest.blockers) ? ingest.blockers : [],
      };
    } else {
      dataFreshness = {
        status: "not_run",
        message: "no ingestion run yet",
        latest_observation: null,
        age_days: null,
        stale: null,
        hint:
          "run python3 scripts/ingest_cwc.py --once to refresh CWC observations; " +
          "see data/cwc/ingestion_status.example.json for the report shape",
      };
    }
    return sendJSON(res, 200, {
      status: "online",
      service: "FloodWatch Flood Intelligence API",
      api_version: "2.2",
      version: "2.2.0",
      server_time: new Date().toISOString(),
      forecast_engine: predictor.loaded ? "ready" : "not_loaded",
      forecast_status: predictor.loaded ? "ready" : "not_loaded",
      ml_model: modelInfoStatus,
      data_freshness: dataFreshness,
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
        "/api/backtest?station=naraj&time=<ISO time in the held-out test period>",
        "/api/backtest/moments",
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

    // TIER GATE: only stations with a verified series may return numbers.
    // The engine's stationByKey() defaults unknown keys to Naraj, so this
    // check must happen before predict() — otherwise any registry station
    // would silently receive Naraj's forecast.
    const resolved = resolveForecastStation(stationKey, parsed.searchParams.get("state"));
    if (!resolved.key) {
      return sendJSON(res, 200, unsupportedStationPayload(resolved));
    }
    const forecastKey = resolved.key;
    const result = predictor.predict(referenceTime, forecastKey);

    // HEADLINE = Random Forest only. The old 60/40 blend mixed an engine
    // anchored to Aug-2022 with an RF anchored to the dataset's last row, so
    // the number did not describe either moment. The engine's own result is
    // preserved verbatim under `legacy_engine` (see below) and never enters
    // the headline. The pooled RFs are SERVED through the Naraj feature
    // pipeline, so only Naraj can have an RF headline; other stations keep
    // the engine headline, explicitly labelled `headline_source`.
    result.forecast_tier = resolved.tier;
    result.forecast_tier_label = tierLabel(resolved.tier);
    if (resolved.registry) result.registry_station = stationSummary(resolved.registry);
    const mlCapableStation = forecastKey === "naraj";
    if (result.status === "success") {
      // Snapshot the engine result BEFORE it is replaced, so the legacy path
      // stays available and clearly separable in the response.
      const legacyLabelBasis = anchorLabel(result.reference_time) || "unknown";
      const legacyEngine = {
        label: "legacy engine, observation basis " + legacyLabelBasis,
        reference_time: result.reference_time,
        overall_risk: result.overall_risk,
        forecast: JSON.parse(JSON.stringify(result.forecast)),
        observed: JSON.parse(JSON.stringify(result.observed || {})),
        calibration_reference: result.calibration || null,
        note:
          "Rule-based rise/level/seasonal engine anchored to its Aug-2022 " +
          "hourly CWC series. Reported for comparison only; it is not part " +
          "of the headline probability.",
      };

      result.ml = mlBridge.status();
      result.ml_capable = mlCapableStation;
      result.headline_source = "legacy_engine";
      if (mlBridge.status().available && mlCapableStation) {
        // The ML model is anchored to the newest observation in the system,
        // which is the served dataset's last row (hf/forecast_dataset.csv,
        // ends 2025-12-30). An explicit ?reference_time= (back-testing) still
        // wins; null means "latest row".
        const mlRef =
          referenceTime || mlBridge.status().dataset_end || null;
        const ml = await mlBridge.predict(mlRef);
        if (ml.ok && ml.horizons) {
          result.ml_enabled = true;
          result.ml_result = { as_of: ml.as_of, horizons: ml.horizons };
          result.headline_source = "rf_model";
          for (const h of ["6h", "12h", "24h"]) {
            const mlP01 =
              ml.horizons[h] && Number.isFinite(ml.horizons[h].probability)
                ? ml.horizons[h].probability
                : null;
            if (mlP01 !== null && result.forecast[h]) {
              const mlP = Math.round(mlP01 * 10000) / 100; // -> percent, 2dp
              // Headline probability and band are the RF alone. The engine's
              // numbers stay in legacy_engine.forecast[h].
              result.forecast[h].ml_probability_percent = mlP;
              result.forecast[h].flood_probability_percent = mlP;
              result.forecast[h].risk = predictor.riskBand(mlP);
            }
          }
          const probs = ["6h", "12h", "24h"].map(
            (h) => result.forecast[h].flood_probability_percent
          );
          result.overall_risk = predictor.riskBand(Math.max(...probs));
        }
      }
      result.legacy_engine = legacyEngine;
      result.persistence = persistenceIndicator();
    }

    // ANCHORS: the headline (RF) and the legacy engine resolve "latest
    // observation" from different sources — the engine from its Aug-2022
    // hourly calibration file, the RF from the served dataset's last row
    // (2025-12-30). Label both; only the RF feeds the headline now.
    const engineAnchor = result.reference_time || null;
    const mlAsOf = (result.ml_result && result.ml_result.as_of) || null;
    const latestObs = mlAsOf || engineAnchor;
    const aligned = anchorKey(engineAnchor) === anchorKey(mlAsOf);
    if (result.status === "success") {
      result.forecast_anchors = {
        latest_observation: latestObs,
        latest_observation_source: mlAsOf ? "ml_dataset" : "statistical_engine",
        statistical_engine_reference_time: engineAnchor,
        statistical_engine_hourly_end:
          (result.calibration && result.calibration.hourly_end) || null,
        ml_as_of: mlAsOf,
        anchors_aligned: aligned,
        headline_source: result.headline_source || "legacy_engine",
        // Kept as a stable field: the headline is single-source, so no
        // long/short-horizon moment mixing happens in the reported number.
        ensemble_mixes_anchors: false,
        note:
          result.headline_source === "rf_model"
            ? "The headline probability comes from the RF model, anchored to " +
              "the dataset's latest row. The statistical engine (Aug-2022 " +
              "basis) is reported separately under legacy_engine and is not " +
              "blended into the headline."
            : "No ML model is served for this station, so the headline is the " +
              "legacy statistical engine (Aug-2022 basis), labelled as such.",
      };
    }

    // How old is the observation this forecast is anchored to? The cache/series
    // end in the past, so surface that instead of letting the card imply "now".
    const obsTime = latestObs;
    const STALE_AFTER_HOURS = 48;
    let ageHours = null;
    if (obsTime) {
      const t = new Date(obsTime).getTime();
      if (Number.isFinite(t)) ageHours = Math.round(((Date.now() - t) / 36e5) * 10) / 10;
    }
    result.observation_freshness = {
      latest_observation: obsTime,
      latest_observation_source: mlAsOf ? "ml_dataset" : "statistical_engine",
      age_hours: ageHours,
      age_days: ageHours === null ? null : Math.round((ageHours / 24) * 10) / 10,
      threshold_hours: STALE_AFTER_HOURS,
      stale: ageHours === null ? true : ageHours > STALE_AFTER_HOURS,
      note:
        mlAsOf
          ? "Age of the newest observation the forecast uses (the ML dataset's " +
            "latest row), not the current time."
          : "Age of the newest observation the forecast uses (the statistical " +
            "engine's hourly series ends here), not the current time.",
    };

    return sendJSON(res, 200, result);
  }

  // ------------------------------------------------------------------
  // API: causal backtest against the verified NDEM events
  // ------------------------------------------------------------------
  if (pathname === "/api/forecast/backtest") {
    return sendJSON(res, 200, predictor.backtest());
  }

  // ------------------------------------------------------------------
  // API: historical backtest on the held-out test period (Naraj only)
  // ------------------------------------------------------------------
  if (pathname === "/api/backtest" || pathname === "/api/backtest/moments") {
    const stationParam = parsed.searchParams.get("station");
    if (stationParam && String(stationParam).trim().toLowerCase() !== "naraj") {
      return sendJSON(res, 200, {
        status: "station_not_supported",
        station: stationParam,
        reason:
          "The backtest is available for Naraj only: it is the single station " +
          "with a trained Random Forest in this project.",
      });
    }

    async function backtestWithModel(time) {
      const described = backtest.describe(time);
      if (!described.ok) return { ok: false, payload: described };

      if (!mlBridge.status().available) {
        return {
          ok: false,
          payload: {
            status: "ml_unavailable",
            message:
              "The Random Forest bridge is not running, so no historical " +
              "probabilities can be shown.",
            ml: mlBridge.status(),
          },
        };
      }
      const ml = await mlBridge.predict(described.data.time);
      if (!ml.ok) {
        return {
          ok: false,
          payload: {
            status: "ml_unavailable",
            message: "The model could not score this timestamp.",
            error: ml.error || "unknown ML error",
          },
        };
      }

      const horizons = described.data.horizons;
      for (const h of ["6h", "12h", "24h"]) {
        const p = ml.horizons && ml.horizons[h] ? ml.horizons[h].probability : null;
        horizons[h].probability = p;
        horizons[h].probability_percent = p === null ? null : Number((p * 100).toFixed(2));
        horizons[h].risk =
          p === null ? null : predictor.riskBand(Number((p * 100).toFixed(2)));
      }

      return {
        ok: true,
        payload: Object.assign({ status: "success" }, described.data, {
          as_of: ml.as_of,
          model_version:
            (ml.horizons && ml.horizons["6h"] && ml.horizons["6h"].source) || null,
        }),
      };
    }

    if (pathname === "/api/backtest/moments") {
      const m = backtest.moments();
      const items = [];
      for (const item of m.moments) {
        const scored = await backtestWithModel(item.time);
        items.push({
          time: item.time,
          kind: item.kind,
          label: item.label,
          result: scored.payload,
        });
      }
      return sendJSON(res, 200, {
        status: items.some((i) => i.result.status === "success")
          ? "success"
          : "ml_unavailable",
        station: "naraj",
        test_period: m.period,
        threshold_m: m.threshold_m,
        note:
          "Historical backtest moments from the held-out test period — not forecasts.",
        items,
      });
    }

    const scored = await backtestWithModel(parsed.searchParams.get("time"));
    if (!scored.ok) {
      const status = scored.payload.status;
      const code = status === "out_of_range" || status === "invalid_time" ? 400 : 200;
      return sendJSON(res, code, scored.payload);
    }
    return sendJSON(res, 200, scored.payload);
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
    const levelsResolved = resolveForecastStation(stationKey, parsed.searchParams.get("state"));
    if (!levelsResolved.key) {
      return sendJSON(res, 200, {
        available: false,
        timestamps: [],
        levels: [],
        station: levelsResolved.registry ? stationSummary(levelsResolved.registry) : null,
        reason: levelsResolved.registry
          ? "No verified hourly water-level series exists for this station in this project."
          : "Station is not in the CWC registry used by this project.",
      });
    }
    const def = stationDef(levelsResolved.key);
    const st = predictor.loaded ? predictor.stations[def.key] : null;
    if (!st) {
      return sendJSON(res, 200, { available: false, timestamps: [], levels: [] });
    }
    const hr = st.hourly.slice(-72);
    return sendJSON(res, 200, {
      available: true,
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
    const exportResolved = resolveForecastStation(stationKey, parsed.searchParams.get("state"));
    if (!exportResolved.key) {
      return sendJSON(res, 200, unsupportedStationPayload(exportResolved));
    }
    const result = predictor.predict(referenceTime, exportResolved.key);
    result.forecast_tier = exportResolved.tier;
    result.forecast_tier_label = tierLabel(exportResolved.tier);

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
      const forecastKey = verifiedKeyForName(s.station);
      const tier = forecastKey ? tierForStationKey(forecastKey) : 3;
      const row = Object.assign({}, s, {
        has_observation: !!s.latest_observation,
        forecast_tier: tier,
        forecast_tier_label: tierLabel(tier),
        has_ml_model: forecastKey === "naraj",
        has_verified_series: !!forecastKey,
        forecast_station_key: forecastKey,
        data_status: tierLabel(tier),
      });
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
