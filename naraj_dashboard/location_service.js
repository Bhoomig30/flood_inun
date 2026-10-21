// ============================================================================
// FLOODWATCH — INDIA-WIDE LOCATION SERVICE (Node)
//
// Finds the nearest REAL CWC monitoring stations to any coordinates in India,
// using the registry built directly from the project's real CWC datasets:
//
//   data/india_cwc/stations.json
//     - rainfall stations from CWC_Rainfall_India_2021_2025/state_wise/*.csv
//     - river-discharge stations from river_discharge/*.csv
//
// Nothing is invented: every station, coordinate and observation comes from
// those CSVs. If no station exists within the configured radius, the service
// returns an explicit "no_nearby_station" status instead of an unrelated
// far-away station.
//
// The Mahanadi/Cuttack verified 58-station GeoJSON and the three focus
// stations remain available as STUDY-REGION context only (they carry the
// verified hourly series used by the forecast model).
// ============================================================================

const fs = require("fs");
const path = require("path");

const DATA_DIR = path.join(__dirname, "data");
const REGISTRY_FILE = path.join(DATA_DIR, "india_cwc", "stations.json");
const STATIONS_FILE = path.join(DATA_DIR, "cwc_stations.geojson");

// Maximum search radius per station kind (km). Beyond this we report
// "no_nearby_station" honestly rather than showing an unrelated station.
const MAX_RAINFALL_KM = 300;
const MAX_RIVER_KM = 400;

const EARTH_RADIUS_KM = 6371.0;

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function readJsonSafe(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (err) {
    return null;
  }
}

// ---------------------------------------------------------------------------
// India-wide station registry (built by scripts/build_india_registry.py from
// the real CWC CSVs; see the "source" block inside the JSON for provenance).
// ---------------------------------------------------------------------------

let registryCache = null;
function loadRegistry() {
  if (registryCache) return registryCache;
  const data = readJsonSafe(REGISTRY_FILE);
  registryCache = {
    stations: (data && Array.isArray(data.stations) ? data.stations : []),
    meta: data
      ? { generated_at: data.generated_at, source: data.source, counts: data.counts }
      : null,
  };
  if (!registryCache.stations.length) {
    console.warn(
      "[location_service] India CWC registry missing/empty — run " +
      "python3 scripts/build_india_registry.py (real CWC datasets required)."
    );
  }
  return registryCache;
}

// Latest valid observation per station (kept at module scope for fast lookups).
// Physical validity: CWC telemetry CSVs contain occasional negative
// placeholder/sensor-error values (a discharge or rainfall reading can never
// be negative). They are treated as invalid observations — never displayed,
// never summed, never allowed to steer a trend.
function isValidObsValue(value) {
  return Number.isFinite(value) && value >= 0;
}

function stationLatestObs(station) {
  const lo = station.latest_observation;
  if (lo && isValidObsValue(lo.value)) return lo;
  // Registry "latest" is invalid (or missing): fall back to the newest valid
  // value in the recent series. Still real data, just not the raw last row.
  const series = station.recent_observations || [];
  for (let i = series.length - 1; i >= 0; i--) {
    if (isValidObsValue(series[i].value)) {
      return {
        time: series[i].time,
        value: series[i].value,
        unit: station.kind === "river" ? "m3/s" : "mm",
      };
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Verified Mahanadi study-region stations (58, from data/cwc_stations.geojson)
// ---------------------------------------------------------------------------

let verifiedStations = null;
function loadVerifiedStations() {
  if (verifiedStations) return verifiedStations;
  const gj = readJsonSafe(STATIONS_FILE);
  verifiedStations = [];
  if (gj && Array.isArray(gj.features)) {
    for (const f of gj.features) {
      const p = f.properties || {};
      const coords = (f.geometry && f.geometry.coordinates) || [];
      if (coords.length < 2) continue;
      verifiedStations.push({
        station: p.name,
        river: p.local_river || p.river || "",
        state: p.state || "",
        district: p.district || "",
        latitude: coords[1],
        longitude: coords[0],
        is_focus_station: !!p.is_focus_station,
        is_mainstem: !!p.is_mainstem,
        n_obs: p.n_obs,
        date_range_start: p.date_range_start,
        date_range_end: p.date_range_end,
        min_wl_m: p.min_wl_m,
        max_wl_m: p.max_wl_m,
        mean_wl_m: p.mean_wl_m,
      });
    }
  }
  return verifiedStations;
}

// Latest water-level observation per focus station (verified hourly files).
const FOCUS_FILES = {
  Naraj: "data/cwc/naraj_august2022_hourly.json",
  Alipingal: "data/cwc/alipingal_august2022_hourly.json",
  Nimapara: "data/cwc/nimapara_august2022_hourly.json",
};

let focusObservations = null;
function loadFocusObservations() {
  if (focusObservations) return focusObservations;
  focusObservations = {};
  for (const [name, rel] of Object.entries(FOCUS_FILES)) {
    const data = readJsonSafe(path.join(__dirname, rel));
    if (!data || !Array.isArray(data.records) || !data.records.length) continue;
    const last = data.records[data.records.length - 1];
    focusObservations[name] = {
      station: name,
      observation_time: last.timestamp || last.date,
      water_level_m: Number(last.water_level_m),
      source: data.source || "CWC (verified)",
    };
  }
  return focusObservations;
}

// ---------------------------------------------------------------------------
// Nearest-station search over the registry
// ---------------------------------------------------------------------------

function nearestFromRegistry(kind, latitude, longitude, maxKm) {
  const { stations } = loadRegistry();
  let best = null;
  let bestDist = Infinity;
  let bestWithObs = null;
  let bestWithObsDist = Infinity;
  for (const s of stations) {
    if (kind && s.kind !== kind) continue;
    const d = haversineKm(latitude, longitude, s.latitude, s.longitude);
    if (d < bestDist) {
      bestDist = d;
      best = s;
    }
    if (
      s.latest_observation &&
      isValidObsValue(s.latest_observation.value) &&
      d < bestWithObsDist
    ) {
      bestWithObsDist = d;
      bestWithObs = s;
    }
  }
  if (!best || bestDist > maxKm) {
    return {
      status: "no_nearby_station",
      max_radius_km: maxKm,
      message:
        "No nearby CWC " +
        (kind === "rainfall" ? "rainfall" : "river") +
        " monitoring station is available within " + maxKm + " km of this location.",
    };
  }
  // Prefer the nearest station that actually carries a valid observation in
  // the real dataset; fall back to the bare nearest (which may have NaN-only
  // rows in the CSVs) with an explicit status.
  const chosen =
    bestWithObs && bestWithObsDist <= maxKm ? bestWithObs : best;
  const chosenDist =
    chosen === bestWithObs ? bestWithObsDist : bestDist;
  const obs = stationLatestObs(chosen);
  return {
    status: "success",
    station: {
      station: chosen.station,
      kind: chosen.kind,
      state: chosen.state,
      district: chosen.district,
      river: chosen.river,
      basin: chosen.basin,
      latitude: chosen.latitude,
      longitude: chosen.longitude,
      n_obs: chosen.n_obs,
      first_obs: chosen.first_obs,
      last_obs: chosen.last_obs,
      recent_observations: chosen.recent_observations || [],
    },
    distance_km: Number(chosenDist.toFixed(3)),
    observation_status: obs
      ? "valid_observation"
      : "station_in_registry_but_no_valid_observation_in_dataset",
    latest_observation: obs
      ? {
          time: obs.time,
          value: obs.value,
          unit: obs.unit,
          rainfall_mm: kind === "rainfall" ? obs.value : undefined,
          discharge_m3s: kind === "river" ? obs.value : undefined,
          observation_time: obs.time,
          source: "CWC NWDP telemetry (real historical dataset)",
          dataset_period: kind === "rainfall" ? "2021-2025" : "1970-2025",
        }
      : null,
  };
}

// Nearest verified Mahanadi study-region station (context only).
function nearestVerified(latitude, longitude) {
  const stations = loadVerifiedStations();
  let best = null;
  let bestDist = Infinity;
  for (const s of stations) {
    const d = haversineKm(latitude, longitude, s.latitude, s.longitude);
    if (d < bestDist) {
      bestDist = d;
      best = s;
    }
  }
  if (!best) return null;
  return Object.assign({}, best, {
    distance_km: Number(bestDist.toFixed(3)),
    observation_status: "nearest_verified_study_region_station",
  });
}

// ---------------------------------------------------------------------------
// PRESENT CONDITION — analytical status from REAL observations only.
// Rule-based (documented thresholds), explicitly NOT machine learning and
// explicitly NOT a forecast. FLOODING is never issued by this heuristic:
// that status is reserved for observed flood evidence.
// ---------------------------------------------------------------------------

// IMD standard rainfall classes: 64.5-115.5 mm/24h = "heavy", >=115.5 =
// "very heavy". Used as the WATCH/ALERT thresholds below.
const RAINFALL_WATCH_MM_24H = 64.5;
const RAINFALL_ALERT_MM_24H = 115.5;

// Dataset-level freshness: how far a station's newest observation may lag the
// dataset's newest observation before we flag it as potentially stale.
const STALE_AFTER_DAYS = 10;

// Consistent DATA-QUALITY states (thresholds defined once, here):
//   FRESH       newest obs is within 24h of the dataset's newest record
//   RECENT      within 7 days of the dataset's newest record
//   STALE       within 10 days (STALE_AFTER_DAYS) — flagged in the UI
//   ARCHIVED    older than that; still real data, shown as historical
//   UNAVAILABLE no timestamps at all
const QUALITY_FRESH_HOURS = 24;
const QUALITY_RECENT_DAYS = 7;

function qualityFor(ageDays) {
  if (!Number.isFinite(ageDays)) return "UNAVAILABLE";
  if (ageDays <= QUALITY_FRESH_HOURS / 24) return "FRESH";
  if (ageDays <= QUALITY_RECENT_DAYS) return "RECENT";
  if (ageDays <= STALE_AFTER_DAYS) return "STALE";
  return "ARCHIVED";
}

function datasetMaxTime(kind) {
  const { stations } = loadRegistry();
  let max = null;
  for (const s of stations) {
    if (kind && s.kind !== kind) continue;
    const t = s.last_obs ? new Date(s.last_obs).getTime() : NaN;
    if (Number.isFinite(t) && (max === null || t > max)) max = t;
  }
  return max;
}

function trendDirection(values, relBand) {
  // Compare the mean of the freshest half of the series against the mean of
  // the older half. Band is relative (e.g. 0.05 = 5%).
  if (!Array.isArray(values) || values.length < 4) return null;
  const half = Math.floor(values.length / 2);
  const older = values.slice(0, half);
  const newer = values.slice(values.length - half);
  const mean = (arr) => arr.reduce((a, b) => a + b, 0) / arr.length;
  const oldMean = mean(older);
  const newMean = mean(newer);
  if (!Number.isFinite(oldMean) || oldMean <= 0) {
    // Flat-zero baseline (e.g. dry gauge): any positive new water is a rise.
    if (newMean > 0) return { direction: "RISING", change_percent: null };
    return { direction: "STABLE", change_percent: 0 };
  }
  const change = (newMean - oldMean) / oldMean;
  if (change > relBand) return { direction: "RISING", change_percent: Number((change * 100).toFixed(1)) };
  if (change < -relBand) return { direction: "FALLING", change_percent: Number((change * 100).toFixed(1)) };
  return { direction: "STABLE", change_percent: Number((change * 100).toFixed(1)) };
}

function freshnessFor(station) {
  const max = datasetMaxTime(station.kind);
  if (!station.last_obs || max === null) {
    return {
      freshness: "unknown",
      quality: "UNAVAILABLE",
      note: "No observation timestamps available.",
    };
  }
  const ageDays = (max - new Date(station.last_obs).getTime()) / 86400000;
  const latest = station.latest_observation;
  const out = {
    latest_observation_time: latest ? latest.time : null,
    hours_behind_dataset_newest: Number(ageDays === 0 ? 0 : (ageDays * 24).toFixed(1)),
    quality: qualityFor(ageDays),
  };
  if (ageDays <= STALE_AFTER_DAYS) {
    out.freshness = "dataset_current";
    out.note = "Among the newest observations available in the dataset.";
  } else {
    out.freshness = "stale";
    out.note = "Data may be stale — newest record for this station lags the dataset by " + ageDays.toFixed(0) + " days.";
  }
  return out;
}

function rainfallPresent(stationResult) {
  if (!stationResult || stationResult.status !== "success" || !stationResult.station) {
    return {
      available: false,
      status: stationResult && stationResult.status === "no_nearby_station" ? "no_nearby_station" : "unavailable",
      message: stationResult && stationResult.message
        ? stationResult.message
        : "Rainfall observation data unavailable for this location.",
    };
  }
  const st = stationResult.station;
  const series = st.recent_observations || [];
  const latest = stationLatestObs(st);
  const values = series.map((p) => p.value).filter((v) => isValidObsValue(v));

  // 24h accumulation = sum of the freshest VALID observations within the last
  // real 24 hours of THIS station's record (honest span reported).
  // Requires a minimum sample density: a sparse record (long gaps between the
  // freshest rows) cannot produce a meaningful 24h accumulation, and reporting
  // a one-sample sum would be misleading. FALLS BACK to the latest hourly
  // value instead — never fabricated.
  let accumulation = null;
  let accumulation_span_hours = null;
  if (series.length >= 2) {
    const lastT = new Date(series[series.length - 1].time).getTime();
    let sum = 0;
    let windowSamples = 0;
    let spanStart = null;
    for (let i = series.length - 1; i >= 0; i--) {
      const t = new Date(series[i].time).getTime();
      if (lastT - t > 24 * 3600 * 1000) break;
      if (!isValidObsValue(series[i].value)) continue;
      sum += series[i].value;
      windowSamples += 1;
      // Loop runs newest→oldest, so the final assignment is the oldest valid
      // sample inside the window — exactly what the span should cover.
      spanStart = series[i].time;
    }
    if (spanStart && windowSamples >= 4) {
      accumulation = Number(sum.toFixed(1));
      accumulation_span_hours = Number(((lastT - new Date(spanStart).getTime()) / 3600000).toFixed(1));
    }
  }

  // Trend: sum of freshest 6 obs vs previous 6 obs (relative band 10%).
  const sums = [];
  for (let i = 0; i + 5 < values.length; i += 6) {
    sums.push(values.slice(i, i + 6).reduce((a, b) => a + b, 0));
  }
  const trend = trendDirection(sums, 0.10);

  let condition = "NORMAL";
  const basis = [];
  if (accumulation !== null) {
    if (accumulation >= RAINFALL_ALERT_MM_24H) {
      condition = "ALERT";
      basis.push("24h rainfall accumulation " + accumulation + " mm (IMD very-heavy threshold)");
    } else if (accumulation >= RAINFALL_WATCH_MM_24H) {
      condition = "WATCH";
      basis.push("24h rainfall accumulation " + accumulation + " mm (IMD heavy threshold)");
    } else {
      basis.push("24h rainfall accumulation " + accumulation + " mm (below heavy-rainfall threshold)");
    }
  } else if (latest && typeof latest.value === "number") {
    basis.push("latest hourly rainfall " + latest.value + " mm (no 24h window available)");
  }

  return {
    available: true,
    station: stationResult.station,
    distance_km: stationResult.distance_km,
    latest_observation: latest,
    trend: trend
      ? { direction: trend.direction, change_percent: trend.change_percent, basis: "sum of freshest 6 observations vs previous 6" }
      : null,
    accumulation_24h_mm: accumulation,
    accumulation_span_hours: accumulation_span_hours,
    value_type: "REAL OBSERVATION",
    freshness: freshnessFor(st),
    condition_contribution: { condition, basis },
  };
}

function riverPresent(stationResult) {
  if (!stationResult || stationResult.status !== "success" || !stationResult.station) {
    return {
      available: false,
      status: stationResult && stationResult.status === "no_nearby_station" ? "no_nearby_station" : "unavailable",
      message: stationResult && stationResult.message
        ? stationResult.message
        : "River monitoring data unavailable for this location.",
    };
  }
  const st = stationResult.station;
  const series = st.recent_observations || [];
  const latest = stationLatestObs(st);
  const values = series.map((p) => p.value).filter((v) => isValidObsValue(v));

  // Discharge trend: freshest 3 obs mean vs previous 3 obs mean (5% band).
  const trend = trendDirection(values, 0.05);

  // Surge ratio vs the station's own recent median (honest, station-relative;
  // the registry carries discharge, not gauge level + danger level).
  let surge = null;
  if (values.length >= 6) {
    const sorted = values.slice().sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)];
    if (median > 0 && latest && typeof latest.value === "number") {
      surge = Number((latest.value / median).toFixed(2));
    }
  }

  let condition = "NORMAL";
  const basis = [];
  if (surge !== null && trend) {
    if (surge >= 2 && trend.direction === "RISING") {
      condition = "ALERT";
      basis.push("discharge " + surge + "x the station's recent median and rising");
    } else if (surge >= 1.5) {
      condition = "WATCH";
      basis.push("discharge " + surge + "x the station's recent median");
    } else {
      basis.push("discharge " + surge + "x the station's recent median");
    }
  } else if (latest) {
    basis.push("latest discharge " + latest.value + " " + latest.unit + " (insufficient series for trend/surge)");
  }

  return {
    available: true,
    station: stationResult.station,
    distance_km: stationResult.distance_km,
    latest_observation: latest,
    trend: trend
      ? { direction: trend.direction, change_percent: trend.change_percent, basis: "mean of freshest 3 observations vs previous 3" }
      : null,
    discharge_surge_vs_recent_median: surge,
    value_type: "REAL OBSERVATION",
    freshness: freshnessFor(st),
    condition_contribution: { condition, basis },
    note: "Registry carries CWC discharge (m3/s), not gauge level + danger level, so no absolute flood-level claim is made for India-wide stations.",
  };
}

function currentCondition(latitude, longitude) {
  const rainfall = nearestFromRegistry("rainfall", latitude, longitude, MAX_RAINFALL_KM);
  const river = nearestFromRegistry("river", latitude, longitude, MAX_RIVER_KM);

  const rainP = rainfallPresent(rainfall);
  const riverP = riverPresent(river);

  // Combine contributions: the worst observed signal wins. FLOODING is never
  // issued by this heuristic (it would require observed flood evidence).
  const rank = { NORMAL: 0, WATCH: 1, ALERT: 2 };
  let status = "UNAVAILABLE";
  const basis = [];
  if (rainP.available && rainP.condition_contribution) {
    basis.push(...rainP.condition_contribution.basis);
    if (rank[rainP.condition_contribution.condition] > (rank[status] || -1)) {
      status = rainP.condition_contribution.condition;
    }
  }
  if (riverP.available && riverP.condition_contribution) {
    basis.push(...riverP.condition_contribution.basis);
    if (rank[riverP.condition_contribution.condition] > (rank[status] || -1)) {
      status = riverP.condition_contribution.condition;
    }
  }
  if (status === "UNAVAILABLE" && (rainP.available || riverP.available)) status = "NORMAL";

  // Structured, explainable reasons ("Why this status?"). Derived ONLY from
  // real computed evidence — no invented explanations. Empty when nothing is
  // available, so the UI can honestly say "no sufficient evidence".
  const reasons = [];
  if (rainP.available) {
    if (rainP.trend && rainP.trend.direction === "RISING") {
      reasons.push("Rainfall increased in the recent observation window" +
        (rainP.trend.change_percent != null ? " (+" + rainP.trend.change_percent + "% vs previous window)" : ""));
    }
    if (typeof rainP.accumulation_24h_mm === "number") {
      reasons.push("24h rainfall accumulation " + rainP.accumulation_24h_mm + " mm at " +
        rainP.station.station + " (" + (rainP.distance_km != null ? rainP.distance_km + " km away" : "nearest") + ")");
    } else if (rainP.latest_observation && typeof rainP.latest_observation.value === "number") {
      reasons.push("Latest hourly rainfall " + rainP.latest_observation.value + " mm at " +
        rainP.station.station + " (sparse record — no reliable 24h window)");
    }
  }
  if (riverP.available) {
    if (riverP.trend && riverP.trend.direction === "RISING") {
      reasons.push("River discharge is rising at " + riverP.station.station +
        (riverP.trend.change_percent != null ? " (+" + riverP.trend.change_percent + "%)" : ""));
    }
    if (typeof riverP.discharge_surge_vs_recent_median === "number") {
      reasons.push("Discharge is " + riverP.discharge_surge_vs_recent_median +
        "× the station's own recent median");
    }
  }
  if (!reasons.length) {
    reasons.push("No sufficient observational evidence available for this location.");
  }

  // Data-quality summary across whatever stations back this condition.
  const qualities = [rainP, riverP]
    .filter((p) => p.available && p.freshness && p.freshness.quality)
    .map((p) => p.freshness.quality);
  const qualityRank = { UNAVAILABLE: 0, ARCHIVED: 1, STALE: 2, RECENT: 3, FRESH: 4 };
  const dataQuality = qualities.length
    ? qualities.reduce((worst, q) =>
        qualityRank[q] < qualityRank[worst] ? q : worst, "FRESH")
    : "UNAVAILABLE";

  return {
    status: rainP.available || riverP.available ? "success" : "no_data_for_location",
    location: { latitude, longitude },
    timestamp: new Date().toISOString(),
    source: "CWC NWDP telemetry datasets (real, historical) via FloodWatch registry",
    present_condition: {
      status,
      label: "FloodWatch Analytical Status",
      analytical: true,
      rule_note:
        "FloodWatch Analytical Status — an analytical indicator based on " +
        "available observations and documented rule-based thresholds (IMD " +
        "rainfall classes, station-relative discharge surge). It is NOT an " +
        "official government warning, NOT machine learning, NOT a forecast. " +
        "FLOODING status is reserved for observed flood evidence.",
      basis,
      reasons,
    },
    data_quality: dataQuality,
    rainfall: rainP,
    river: riverP,
    value_types: {
      rainfall: "REAL OBSERVATION (CWC telemetry, historical dataset)",
      river: "REAL OBSERVATION (CWC telemetry, historical dataset)",
    },
    data_notice:
      "Observations come from the project's real CWC datasets — the newest " +
      "records available, not guaranteed live readings.",
  };
}

// ---------------------------------------------------------------------------
// FORECAST COVERAGE — where the trained model may honestly be applied.
// The Random Forest + statistical ensemble is calibrated on the Naraj/
// Cuttack study region ONLY. Single gate shared by both servers so the UI
// can never present study output as location-specific.
// ---------------------------------------------------------------------------

const CALIBRATION_RADIUS_KM = 150;
const CALIBRATED_CENTER = { latitude: 20.4717, longitude: 85.7656, station: "Naraj" };

function forecastCoverage(latitude, longitude) {
  const km = haversineKm(latitude, longitude, CALIBRATED_CENTER.latitude, CALIBRATED_CENTER.longitude);
  const available = km <= CALIBRATION_RADIUS_KM;
  return {
    available,
    model: {
      name: "FloodWatch Future Flood Forecast",
      algorithm: "Random Forest (71 features) + statistical ensemble",
      horizons: ["6h", "12h", "24h"],
    },
    calibration: "Naraj/Cuttack study region, Odisha (Mahanadi basin)",
    calibration_center: CALIBRATED_CENTER,
    calibration_radius_km: CALIBRATION_RADIUS_KM,
    distance_to_calibrated_center_km: Number(km.toFixed(1)),
    message: available
      ? "Selected location is inside the calibrated study region."
      : "AI forecast unavailable for this location with the current calibrated model (trained for the Naraj/Cuttack study region only).",
  };
}

// ---------------------------------------------------------------------------
// MAIN LOOKUP — /api/location
// ---------------------------------------------------------------------------

function locationLookup(latitude, longitude) {
  const focus = loadFocusObservations();
  const verified = nearestVerified(latitude, longitude);

  const rainfall = nearestFromRegistry("rainfall", latitude, longitude, MAX_RAINFALL_KM);
  const river = nearestFromRegistry("river", latitude, longitude, MAX_RIVER_KM);

  // Model scope honesty: the RF forecast is calibrated for the Naraj/Cuttack
  // study region only. Distance to Naraj decides whether location-specific
  // AI probabilities may be shown at all.
  const naraj = focus.Naraj
    ? loadVerifiedStations().find((s) => s.station === "Naraj")
    : null;
  const narajKm = naraj
    ? haversineKm(latitude, longitude, naraj.latitude, naraj.longitude)
    : Infinity;

  return {
    status: "success",
    location: { latitude, longitude },
    rainfall,
    river,
    study_region: {
      nearest_station: verified,
      focus_observations: focus,
      note:
        "Verified hourly/daily series and the forecast model exist only for the " +
        "Naraj/Cuttack (Mahanadi) study region. This block is study-region " +
        "context, not India-wide monitoring.",
    },
    model_scope: {
      calibrated_region: "Naraj / Cuttack study region, Odisha (Mahanadi basin)",
      calibrated_center: naraj
        ? { latitude: naraj.latitude, longitude: naraj.longitude }
        : null,
      distance_to_calibrated_center_km: Number.isFinite(narajKm)
        ? Number(narajKm.toFixed(1))
        : null,
      location_specific_forecast_available:
        Number.isFinite(narajKm) && narajKm <= 150,
    },
    registry_meta: loadRegistry().meta,
    data_notice:
      "All stations and observations come from the project's real CWC datasets " +
      "(rainfall 2021-2025, river discharge 1970-2025). They are historical " +
      "records, not guaranteed live conditions.",
  };
}

module.exports = {
  locationLookup,
  currentCondition,
  forecastCoverage,
  haversineKm,
  loadRegistry,
  loadVerifiedStations,
  loadFocusObservations,
};
