// ============================================================================
// FLOODWATCH — DASHBOARD APPLICATION LAYER (India-wide)
//
// ARCHITECTURE
//   User selects a location (search / geolocation / map click / station click)
//        ↓
//   FloodWatchState.selectedLocation  (SINGLE SOURCE OF TRUTH)
//        ↓  setSelectedLocation() — the ONLY state-changing entry point
//   ├─ every Leaflet map moves to the new coordinates
//   ├─ stale location-based markers/layers are removed first
//   ├─ /api/location runs → rainfall + river panels update (or honest "none")
//   ├─ AI-forecast card shows model scope for the selected location
//   └─ status line reports what is and is not available
//
// The Mahanadi/Naraj study region remains only as clearly-labelled
// historical-study data. Nothing here fabricates values.
// ============================================================================

// ---------------------------------------------------------------------------
// CONFIG + SINGLE SOURCE OF TRUTH
// ---------------------------------------------------------------------------

var API_BASE_URL =
  typeof window.FLOODWATCH_API_BASE === "string"
    ? window.FLOODWATCH_API_BASE
    : "";

// India-wide default view (never initialize to the study region).
var INDIA_DEFAULT = { latitude: 22.5, longitude: 79.0, zoom: 4.5 };
var LOCATION_ZOOM = 9;

// The one location state every consumer reads.
var FloodWatchState = {
  selectedLocation: null, // { latitude, longitude, name, state, country }
  locationResult: null,   // last /api/location payload
  maps: [],               // all Leaflet maps registered for recentering
  locationListeners: [],  // fns called after every location change
};

// Subscribe to location changes (used by panes living in public.js).
function onLocationChange(fn) {
  if (typeof fn === "function" && FloodWatchState.locationListeners.indexOf(fn) === -1) {
    FloodWatchState.locationListeners.push(fn);
  }
}
window.FloodWatchState.onLocationChange = onLocationChange;

// Centralized marker/layer references (cleared before every re-render).
var locationLayers = {
  userMarker: null,          // selected-location marker (one per map)
  rainfallMarkersLayer: null,
  riverMarkersLayer: null,
};

// Exposed for debugging/integration tests.
window.FloodWatchState = FloodWatchState;
FloodWatchState.locationLayers = locationLayers;

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showStatus(message, type) {
  var typeSafe = type || "info";
  var status = document.getElementById("location-status");
  if (!status) return;
  status.textContent = message;
  status.className =
    "location-status" + (typeSafe !== "info" ? " " + typeSafe : "");
}

function registerMap(map) {
  if (map && FloodWatchState.maps.indexOf(map) === -1) {
    FloodWatchState.maps.push(map);
  }
}

function getActiveMap() {
  // Prefer the overview map, then the flood map (both live in public.js).
  try {
    if (typeof map1 !== "undefined" && map1) return map1;
  } catch (e) { /* public.js not loaded yet */ }
  try {
    if (typeof map2 !== "undefined" && map2) return map2;
  } catch (e) { /* not loaded */ }
  return FloodWatchState.maps[0] || null;
}

function haversineKm(lat1, lon1, lat2, lon2) {
  var toRad = function (d) { return (d * Math.PI) / 180; };
  var dLat = toRad(lat2 - lat1);
  var dLon = toRad(lon2 - lon1);
  var a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
  return 6371.0 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// MAP MARKERS (centralized; stale markers always removed first)
// ---------------------------------------------------------------------------

var USER_ICON = function () {
  return L.divIcon({
    className: "",
    html:
      '<div style="width:16px;height:16px;border-radius:50%;' +
      'background:#1769aa;border:3px solid white;' +
      'box-shadow:0 0 0 1px rgba(0,0,0,0.35);"></div>',
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });
};

function removeLocationLayers() {
  // Remove stale markers from every registered map before re-rendering.
  FloodWatchState.maps.forEach(function (map) {
    if (locationLayers.userMarker && map.hasLayer(locationLayers.userMarker)) {
      map.removeLayer(locationLayers.userMarker);
    }
    if (locationLayers.rainfallMarkersLayer && map.hasLayer(locationLayers.rainfallMarkersLayer)) {
      map.removeLayer(locationLayers.rainfallMarkersLayer);
    }
    if (locationLayers.riverMarkersLayer && map.hasLayer(locationLayers.riverMarkersLayer)) {
      map.removeLayer(locationLayers.riverMarkersLayer);
    }
  });
  locationLayers.userMarker = null;
  locationLayers.rainfallMarkersLayer = null;
  locationLayers.riverMarkersLayer = null;
}

function ensureUserMarker(map, latitude, longitude, name) {
  locationLayers.userMarker = L.marker([latitude, longitude], {
    icon: USER_ICON(),
  }).addTo(map);
  locationLayers.userMarker.bindPopup(
    "<b>Selected location</b><br>" +
      escapeHtml(name || "Selected location") +
      "<br>" +
      Number(latitude).toFixed(4) +
      ", " +
      Number(longitude).toFixed(4)
  );
}

function renderStationMarker(map, layerKey, station, observation, kind, distanceKm) {
  if (!map || !station) return;
  if (
    typeof station.latitude !== "number" ||
    typeof station.longitude !== "number"
  ) {
    return;
  }

  if (!locationLayers[layerKey]) {
    locationLayers[layerKey] = L.layerGroup().addTo(map);
  }

  var color = kind === "rainfall" ? "#198754" : "#0f6b78";
  var icon = kind === "rainfall" ? "🌧" : "🌊";
  var obsText = "No valid observation in the real dataset";
  if (observation && typeof observation.value === "number") {
    obsText =
      observation.value +
      " " +
      (observation.unit || "") +
      " · " +
      String(observation.time || "").replace("T", " ").slice(0, 16) +
      " UTC";
  }

  L.circleMarker([station.latitude, station.longitude], {
    radius: 7,
    color: color,
    fillColor: color,
    fillOpacity: 0.85,
    weight: 2,
  })
    .bindPopup(
      "<b>" + icon + " CWC " + (kind === "rainfall" ? "Rainfall" : "River") +
        " Station</b><br><strong>" + escapeHtml(station.station) + "</strong>" +
        (station.district ? "<br>" + escapeHtml(station.district) : "") +
        (station.state ? ", " + escapeHtml(station.state) : "") +
        (typeof distanceKm === "number" ? "<br>Distance: " + distanceKm + " km" : "") +
        "<br>" + escapeHtml(obsText) +
        '<br><small>Real CWC historical dataset</small>'
    )
    .addTo(locationLayers[layerKey]);
}

// ---------------------------------------------------------------------------
// PANEL RENDERING (explicit empty/error states, never stale data)
// ---------------------------------------------------------------------------

function stationLine(station, distanceKm) {
  var line = "<strong>" + escapeHtml(station.station) + "</strong>";
  if (station.river && station.river !== "-") line += " · " + escapeHtml(station.river);
  if (station.district) line += "<br>" + escapeHtml(station.district);
  if (station.state) {
    line += (station.district ? ", " : "<br>") + escapeHtml(station.state);
  }
  if (typeof distanceKm === "number") {
    line += "<br>Distance: " + escapeHtml(String(distanceKm)) + " km";
  }
  return line;
}

function observationLine(obs, unitLabel) {
  if (!obs || typeof obs.value !== "number") {
    return '<div class="cwc-notice">Station exists in the CWC network but has ' +
      "no valid observation in the real dataset.</div>";
  }
  var when = String(obs.time || "").replace("T", " ").slice(0, 16);
  return (
    '<div class="cwc-meta">Observed: ' + escapeHtml(when) + " UTC" +
    " · " + escapeHtml(String(obs.dataset_period || "historical")) + " dataset" +
    "</div>"
  );
}

function renderRainfallPanel(rainfall) {
  var card = document.getElementById("rainfall-card");
  if (!card) return;

  if (!rainfall || rainfall.status !== "success" || !rainfall.station) {
    var message =
      rainfall && rainfall.message
        ? rainfall.message
        : "No nearby CWC rainfall station is available.";
    card.innerHTML =
      "<h3>🌧️ Rainfall</h3>" +
      '<div class="cwc-notice">' + escapeHtml(message) + "</div>";
    return;
  }

  var station = rainfall.station;
  var obs = rainfall.latest_observation;
  var value =
    obs && typeof obs.value === "number"
      ? obs.value.toFixed(2) + " mm"
      : "No valid observation";

  card.innerHTML =
    "<h3>🌧️ Rainfall — nearest CWC station</h3>" +
    '<div class="cwc-value">' + escapeHtml(value) + "</div>" +
    '<div class="cwc-meta">' + stationLine(station, rainfall.distance_km) + "</div>" +
    observationLine(obs) +
    '<div class="cwc-meta"><small>Source: CWC NWDP telemetry (real historical dataset)</small></div>';
}

function renderRiverPanel(river) {
  var card = document.getElementById("river-card");
  if (!card) return;

  if (!river || river.status !== "success" || !river.station) {
    var message =
      river && river.message
        ? river.message
        : "No nearby CWC river station is available.";
    card.innerHTML =
      "<h3>🌊 River Condition</h3>" +
      '<div class="cwc-notice">' + escapeHtml(message) + "</div>";
    return;
  }

  var station = river.station;
  var obs = river.latest_observation;
  var value =
    obs && typeof obs.value === "number"
      ? obs.value.toFixed(1) + " m³/s"
      : "No valid observation";

  card.innerHTML =
    "<h3>🌊 River Condition — nearest CWC station</h3>" +
    '<div class="cwc-value">' + escapeHtml(value) + "</div>" +
    '<div class="cwc-meta">' + stationLine(station, river.distance_km) + "</div>" +
    observationLine(obs) +
    '<div class="cwc-meta"><small>Source: CWC NWDP telemetry (real historical dataset)</small></div>';
}

// ---------------------------------------------------------------------------
// PRESENT CONDITION (OBSERVED) — real observations only, independent of the
// ML forecast. Uses /api/current-condition (rule-based analytical status).
// ---------------------------------------------------------------------------

function fmtObsTime(iso) {
  if (!iso) return "—";
  return String(iso).slice(0, 16).replace("T", " ") + " UTC";
}

function pcTrendText(trend) {
  if (!trend || !trend.direction) return "";
  var dir = trend.direction;
  var pct = trend.change_percent;
  var suffix =
    typeof pct === "number" ? " (" + (pct > 0 ? "+" : "") + pct + "%)" : "";
  return dir + suffix;
}

function renderPresentCondition(cc) {
  var statusEl = document.getElementById("present-condition-status");
  var valueEl = document.getElementById("pc-status-value");
  var basisEl = document.getElementById("pc-basis");
  var noteEl = document.getElementById("pc-unavailable-note");
  if (!valueEl) return;

  if (!cc) {
    if (statusEl) statusEl.textContent = "Present condition unavailable — FloodWatch API not running.";
    valueEl.textContent = "—";
    valueEl.className = "overall-risk-value unknown";
    if (basisEl) basisEl.innerHTML = "";
    if (noteEl) { noteEl.hidden = false; noteEl.textContent = "Data unavailable for this location."; }
    return;
  }

  var pc = cc.present_condition || {};
  var rain = cc.rainfall || {};
  var river = cc.river || {};

  // Overall status pill.
  var st = String(pc.status || "UNAVAILABLE").toUpperCase();
  valueEl.textContent = st;
  valueEl.className =
    "overall-risk-value " +
    (st === "ALERT" ? "high" : st === "WATCH" ? "moderate" : st === "FLOODING" ? "high" : "low");

  if (statusEl) {
    statusEl.textContent =
      "Built from the latest real CWC observations for the selected location. " +
      "Not a forecast — see the AI Future Forecast card below for model output.";
  }

  // Basis lines (why this status).
  if (basisEl) {
    var bits = (pc.basis || []).map(function (b) {
      return "<div>• " + escapeHtml(String(b)) + "</div>";
    });
    if (cc.data_notice) {
      bits.push('<div class="pc-rule-note">' + escapeHtml(cc.data_notice) + "</div>");
    }
    basisEl.innerHTML = bits.join("") || '<div class="pc-rule-note">No observational basis available.</div>';
  }

  // "Why this status?" — structured reasons from real evidence only.
  var whyEl = document.getElementById("pc-why-list");
  if (whyEl) {
    var reasons = pc.reasons || [];
    whyEl.innerHTML = reasons.length
      ? reasons
          .map(function (r) {
            return '<div>✓ ' + escapeHtml(String(r)) + "</div>";
          })
          .join("")
      : '<div class="pc-rule-note">No sufficient evidence available.</div>';
  }

  // Data-quality chip (FRESH / RECENT / STALE / ARCHIVED / UNAVAILABLE).
  var qualityEl = document.getElementById("pc-quality");
  if (qualityEl) {
    var q = String(cc.data_quality || "UNAVAILABLE").toUpperCase();
    qualityEl.textContent = q;
    qualityEl.className = "pc-quality pc-quality-" + q.toLowerCase();
  }

  // Rainfall stat (REAL OBSERVATION).
  var rainEl = document.getElementById("pc-rainfall");
  var rainTrendEl = document.getElementById("pc-rainfall-trend");
  if (rainEl) {
    if (rain.available) {
      var acc = rain.accumulation_24h_mm;
      var latest = rain.latest_observation;
      rainEl.textContent =
        typeof acc === "number"
          ? acc.toFixed(1) + " mm / " + (rain.accumulation_span_hours ? rain.accumulation_span_hours.toFixed(0) + "h" : "24h")
          : latest && typeof latest.value === "number"
            ? latest.value.toFixed(1) + " mm (latest hourly)"
            : "No valid observation";
      if (rainTrendEl) {
        rainTrendEl.textContent = pcTrendText(rain.trend);
        rainTrendEl.className = "pc-trend" + (rain.trend && rain.trend.direction === "RISING" ? " rising" : rain.trend && rain.trend.direction === "FALLING" ? " falling" : "");
      }
    } else {
      rainEl.textContent = "—";
      if (rainTrendEl) rainTrendEl.textContent = rain.message || "No nearby CWC rainfall station found.";
    }
  }

  // River stat (REAL OBSERVATION).
  var riverEl = document.getElementById("pc-river");
  var riverTrendEl = document.getElementById("pc-river-trend");
  if (riverEl) {
    if (river.available) {
      var rObs = river.latest_observation;
      var surge = river.discharge_surge_vs_recent_median;
      riverEl.textContent =
        rObs && typeof rObs.value === "number"
          ? rObs.value.toFixed(1) + " m³/s" + (typeof surge === "number" ? " (" + surge + "× recent median)" : "")
          : "No valid observation";
      if (riverTrendEl) {
        riverTrendEl.textContent = pcTrendText(river.trend);
        riverTrendEl.className = "pc-trend" + (river.trend && river.trend.direction === "RISING" ? " rising" : river.trend && river.trend.direction === "FALLING" ? " falling" : "");
      }
    } else {
      riverEl.textContent = "—";
      if (riverTrendEl) riverTrendEl.textContent = river.message || "River monitoring data unavailable for this location.";
    }
  }

  // Nearest station + distance.
  var stationEl = document.getElementById("pc-station");
  var distEl = document.getElementById("pc-station-distance");
  var nearest = rain.available ? rain : river.available ? river : null;
  if (stationEl) {
    stationEl.textContent = nearest && nearest.station ? nearest.station.station : "—";
  }
  if (distEl) {
    distEl.textContent =
      nearest && typeof nearest.distance_km === "number"
        ? nearest.distance_km.toFixed(1) + " km · " + ((nearest.station && nearest.station.kind) || "")
        : "";
  }

  // Last updated + freshness (honest staleness).
  var updatedEl = document.getElementById("pc-updated");
  var freshEl = document.getElementById("pc-freshness");
  var fresh = (rain.available && rain.freshness) || (river.available && river.freshness) || null;
  if (updatedEl) {
    updatedEl.textContent = fresh && fresh.latest_observation_time ? fmtObsTime(fresh.latest_observation_time) : "—";
  }
  if (freshEl) {
    freshEl.textContent = fresh && fresh.note ? fresh.note : "";
    freshEl.className = "pc-trend" + (fresh && fresh.freshness === "stale" ? " stale" : "");
  }

  // Explicit unavailable note when neither observation type exists.
  if (noteEl) {
    if (cc.status === "no_data_for_location" || (!rain.available && !river.available)) {
      noteEl.hidden = false;
      noteEl.textContent = "Data unavailable for this location. " +
        (rain.message || "") + (river.message ? " " + river.message : "");
    } else {
      noteEl.hidden = true;
    }
  }

  renderLocationCoverage(cc);
}

// ---------------------------------------------------------------------------
// LOCATION DATA COVERAGE — scientific transparency: what is genuinely
// available for the selected location (REAL availability, never fabricated).
// ---------------------------------------------------------------------------
function renderLocationCoverage(cc) {
  var list = document.getElementById("pc-coverage-list");
  if (!list) return;
  var sel = FloodWatchState.selectedLocation || {};
  var rain = (cc && cc.rainfall) || {};
  var river = (cc && cc.river) || {};
  var insideStudy =
    typeof haversineKm === "function" &&
    Number.isFinite(sel.latitude) &&
    haversineKm(sel.latitude, sel.longitude, 20.4717, 85.7656) <= 150;

  var rows = {
    rainfall: rain.available ? "AVAILABLE" : "UNAVAILABLE",
    river: river.available ? "AVAILABLE" : "UNAVAILABLE",
    satellite: insideStudy
      ? "AVAILABLE (study region)"
      : "UNAVAILABLE for this location",
    flood_extent: insideStudy
      ? "AVAILABLE (study region)"
      : "UNAVAILABLE for this location",
    historical_events: insideStudy
      ? "AVAILABLE (study region)"
      : "UNAVAILABLE for this location",
    ai_forecast: insideStudy ? "SUPPORTED" : "OUTSIDE CALIBRATION",
  };

  var LABELS = {
    rainfall: "Rainfall",
    river: "River",
    satellite: "Satellite",
    flood_extent: "Flood extent",
    historical_events: "Historical events",
    ai_forecast: "AI forecast",
  };
  list.querySelectorAll("li[data-cov]").forEach(function (li) {
    var key = li.getAttribute("data-cov");
    var val = rows[key] || "—";
    var state = val.indexOf("UNAVAILABLE") === 0 || val === "OUTSIDE CALIBRATION"
      ? "no"
      : "yes";
    li.innerHTML =
      "<span>" +
      escapeHtml(LABELS[key] || key) +
      ":</span> <strong class=\"cov-" + state + "\">" +
      escapeHtml(val) +
      "</strong>";
  });
}

async function loadPresentCondition(latitude, longitude) {
  try {
    var response = await fetch(
      API_BASE_URL +
        "/api/current-condition?latitude=" + encodeURIComponent(latitude) +
        "&longitude=" + encodeURIComponent(longitude)
    );
    if (!response.ok) throw new Error("HTTP " + response.status);
    var data = await response.json();
    renderPresentCondition(data);
  } catch (error) {
    console.error("Present condition error:", error);
    renderPresentCondition(null);
  }
}

function renderModelScope(modelScope) {
  var el = document.getElementById("forecast-location");
  var note = document.getElementById("forecast-coverage-note");
  var outside = false;
  if (modelScope) {
    outside = modelScope.location_specific_forecast_available === false;
  }
  if (note) {
    // A tier-3 station has no forecast at all, so the "study forecast below"
    // coverage note would misdescribe the card.
    note.hidden = forecastTier3Station ? true : !outside;
  }
  if (!el) return;
  if (forecastTier3Station) {
    el.textContent =
      "📍 Selected station: " + (forecastTier3Station.station || "") +
      (forecastTier3Station.state ? ", " + forecastTier3Station.state : "") +
      " — no verified water-level series or trained model exists for this " +
      "station in this project.";
    return;
  }
  if (!modelScope) {
    el.textContent = "";
    return;
  }
  if (modelScope.location_specific_forecast_available) {
    el.textContent =
      "📍 Selected location is inside the calibrated study region (" +
      (modelScope.distance_to_calibrated_center_km != null
        ? modelScope.distance_to_calibrated_center_km + " km to Naraj)"
        : ")");
  } else {
    el.textContent =
      "📍 AI forecast model currently calibrated for the Naraj/Cuttack study " +
      "region. Location-specific prediction is not available for this location " +
      "yet" +
      (modelScope.distance_to_calibrated_center_km != null
        ? " (" + modelScope.distance_to_calibrated_center_km + " km away)."
        : ".");
  }
}

// ---------------------------------------------------------------------------
// LOCATION UPDATE — THE single pipeline every selector funnels into
// ---------------------------------------------------------------------------

function setSelectedLocation(latitude, longitude, name, options) {
  var opts = options || {};

  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    latitude < -90 || latitude > 90 ||
    longitude < -180 || longitude > 180
  ) {
    showStatus("Invalid location. Please try another place in India.", "error");
    return Promise.resolve();
  }

  FloodWatchState.selectedLocation = {
    latitude: latitude,
    longitude: longitude,
    name: name || "",
    state: opts.state || "",
    country: opts.country || "India",
  };

  // A new location is not a station selection: drop any tier-3 station
  // context so the forecast card can never describe a station the user has
  // navigated away from. Station selection passes keepStationForecast and
  // reloads the forecast itself.
  if (!opts.keepStationForecast) {
    clearStationForecastContext();
  }

  // 1. Move every registered map, and remove stale location-based layers.
  //    suppressRecenter keeps the map still when the station's recorded
  //    coordinates are known to be inconsistent with its state.
  FloodWatchState.maps.forEach(function (map) {
    if (opts.suppressRecenter) return;
    map.setView([latitude, longitude], opts.zoom || LOCATION_ZOOM);
  });
  removeLocationLayers();
  var primary = getActiveMap();
  if (primary) {
    ensureUserMarker(primary, latitude, longitude, name);
  }

  // 2. Refresh every location-dependent panel. The pipeline resolves only
  // after the present-condition render completes, so callers (and the
  // "Location loaded" announcement) never race the visible data.
  return fetchLocationData(latitude, longitude)
    .then(function () {
      return loadPresentCondition(latitude, longitude);
    })
    .then(function () {
      updateLocationScopedNotices();
      // Notify subscribers (India Stations pane, coverage filters, ...).
      FloodWatchState.locationListeners.forEach(function (fn) {
        try {
          fn(FloodWatchState.selectedLocation);
        } catch (err) {
          console.error("Location listener error:", err);
        }
      });
      // The forecast card is location-scoped: after a search/geolocation the
      // study forecast must be re-rendered for the new place, not left on a
      // previously selected station.
      if (!opts.keepStationForecast) {
        loadFloodForecast();
      }
      if (opts.announce !== false) {
        showStatus(
          "Location loaded: " + (name || latitude.toFixed(3) + ", " + longitude.toFixed(3)),
          "success"
        );
      }
    });
}

// Honest per-location availability notices for panes whose real data is
// study-region-scoped (satellite evidence, past-flood events).
function updateLocationScopedNotices() {
  var sel = FloodWatchState.selectedLocation;
  if (!sel) return;

  var insideStudy =
    haversineKm(sel.latitude, sel.longitude, 20.4717, 85.7656) <= 150;

  var satNote = document.getElementById("sat-location-status");
  if (satNote) {
    if (insideStudy) {
      satNote.className = "sat-event-banner sat-event-ok";
      satNote.textContent =
        "✓ Selected location is inside the Naraj/Cuttack study region — the " +
        "processed Sentinel-1 scenes below cover this area.";
    } else {
      satNote.className = "sat-event-banner sat-event-warn";
      satNote.textContent =
        "Satellite evidence is not currently available for this location. " +
        "Processed scenes cover the Naraj/Cuttack study region only (below).";
    }
  }

  var pfNote = document.getElementById("pastfloods-location-status");
  if (pfNote) {
    if (insideStudy) {
      pfNote.className = "sat-event-banner sat-event-ok";
      pfNote.textContent =
        "✓ Selected location is inside the study region — the events below " +
        "pertain to this area.";
    } else {
      pfNote.className = "sat-event-banner sat-event-warn";
      pfNote.textContent =
        "The historical flood-event record in this project covers the " +
        "Naraj/Cuttack (Mahanadi) study region only — no event inventory is " +
        "claimed for this location.";
    }
  }
}

async function fetchLocationData(latitude, longitude) {
  try {
    var url =
      API_BASE_URL +
      "/api/location?latitude=" +
      encodeURIComponent(latitude) +
      "&longitude=" +
      encodeURIComponent(longitude);

    var response = await fetch(url);
    if (!response.ok) {
      throw new Error("Location API returned HTTP " + response.status);
    }

    var data = await response.json();
    FloodWatchState.locationResult = data;

    renderRainfallPanel(data.rainfall);
    renderRiverPanel(data.river);
    renderModelScope(data.model_scope);

    // Fresh markers for the new location only (stale ones already removed).
    var map = getActiveMap();
    if (map) {
      if (data.rainfall && data.rainfall.status === "success") {
        renderStationMarker(
          map, "rainfallMarkersLayer",
          data.rainfall.station, data.rainfall.latest_observation, "rainfall",
          data.rainfall.distance_km
        );
      }
      if (data.river && data.river.status === "success") {
        renderStationMarker(
          map, "riverMarkersLayer",
          data.river.station, data.river.latest_observation, "river",
          data.river.distance_km
        );
      }
    }

    var nearestBits = [];
    if (data.rainfall && data.rainfall.status === "success") {
      nearestBits.push("rainfall: " + data.rainfall.station.station);
    } else {
      nearestBits.push("rainfall: none nearby");
    }
    if (data.river && data.river.status === "success") {
      nearestBits.push("river: " + data.river.station.station);
    } else {
      nearestBits.push("river: none nearby");
    }
    showStatus("Nearest CWC stations — " + nearestBits.join(" · "), "success");
  } catch (error) {
    console.error("Location data error:", error);

    renderRainfallPanel(null);
    renderRiverPanel(null);
    renderModelScope(null);
    showStatus(
      "FloodWatch API is not running — CWC station lookup is unavailable. " +
        "Start it with: npm start (or python3 api/main.py). Map still works.",
      "error"
    );
  }
}

// ---------------------------------------------------------------------------
// LOCATION SEARCH (OpenStreetMap Nominatim)
// ---------------------------------------------------------------------------

async function searchLocation(query) {
  var trimmed = String(query || "").trim();
  if (!trimmed) {
    showStatus("Please enter a location.", "error");
    return;
  }

  showStatus("Searching location...", "loading");

  try {
    var url =
      "https://nominatim.openstreetmap.org/search" +
      "?format=json&limit=1&countrycodes=in&q=" +
      encodeURIComponent(trimmed);

    var response = await fetch(url, {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      throw new Error("Search HTTP " + response.status);
    }

    var results = await response.json();
    if (!Array.isArray(results) || results.length === 0) {
      showStatus("Location not found. Try another city or state in India.", "error");
      return;
    }

    var latitude = Number(results[0].lat);
    var longitude = Number(results[0].lon);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      throw new Error("Invalid coordinates returned");
    }

    var displayName = results[0].display_name || trimmed;
    var state = "";
    var parts = displayName.split(",").map(function (s) { return s.trim(); });
    if (parts.length >= 3) state = parts[parts.length - 3];

    var input = document.getElementById("location-search");
    if (input) input.value = displayName;

    await setSelectedLocation(latitude, longitude, displayName, { state: state });
  } catch (error) {
    console.error("Location search error:", error);
    showStatus("Could not find that location. Try another city.", "error");
  }
}

// ---------------------------------------------------------------------------
// BROWSER GEOLOCATION ("Use My Location")
// ---------------------------------------------------------------------------

function initializeGeolocation() {
  var button = document.getElementById("use-my-location");
  if (!button) return;

  button.addEventListener("click", function () {
    if (!navigator.geolocation) {
      showStatus("Geolocation is not supported by this browser.", "error");
      return;
    }

    showStatus("Getting your location...", "loading");
    button.disabled = true;

    navigator.geolocation.getCurrentPosition(
      async function (position) {
        var latitude = position.coords.latitude;
        var longitude = position.coords.longitude;
        button.disabled = false;
        await setSelectedLocation(latitude, longitude, "My location");
      },
      function (error) {
        console.error("Geolocation error:", error);
        button.disabled = false;

        var message = "Unable to determine your location.";
        if (error.code === error.PERMISSION_DENIED) {
          message = "Location permission was denied.";
        } else if (error.code === error.POSITION_UNAVAILABLE) {
          message = "Your location is unavailable.";
        } else if (error.code === error.TIMEOUT) {
          message = "Location request timed out.";
        }
        showStatus(message, "error");
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 300000 }
    );
  });
}

// ---------------------------------------------------------------------------
// AI FLOOD FORECAST (real Random Forest + statistical engine)
// Honest scope: the models are calibrated for the Naraj/Cuttack study region.
// ---------------------------------------------------------------------------

function riskClass(risk) {
  var value = String(risk || "LOW").toUpperCase();
  if (value === "HIGH") return "risk-high";
  if (value === "MEDIUM" || value === "MODERATE") return "risk-medium";
  return "risk-low";
}

function overallRiskClass(risk) {
  var value = String(risk || "LOW").toUpperCase();
  if (value === "HIGH") return "high";
  if (value === "MEDIUM" || value === "MODERATE") return "moderate";
  return "low";
}

var currentForecastStation = "naraj";
// Set when the selected national station has no verified series/model. In that
// state the card shows metadata only and never another station's numbers.
var forecastTier3Station = null;

function floodForecastQuery() {
  if (forecastTier3Station) {
    return (
      "station=" + encodeURIComponent(forecastTier3Station.station) +
      "&state=" + encodeURIComponent(forecastTier3Station.state || "")
    );
  }
  return "station=" + encodeURIComponent(currentForecastStation || "naraj");
}

function setTier3StationOption(st) {
  var picker = document.getElementById("forecast-station");
  if (!picker) return;
  var opt = picker.querySelector('option[data-national-tier3="1"]');
  if (!opt) {
    opt = document.createElement("option");
    opt.setAttribute("data-national-tier3", "1");
    picker.appendChild(opt);
  }
  opt.value = "";
  opt.textContent = st.station + " · " + (st.state || "") + " (no forecast model)";
  picker.value = "";
}

function removeTier3StationOption() {
  var picker = document.getElementById("forecast-station");
  if (!picker) return;
  var opt = picker.querySelector('option[data-national-tier3="1"]');
  if (opt) opt.remove();
}

// Drop every trace of a national-station selection: the tier-3 context, the
// placeholder option, the selection label and the export links.
function clearStationForecastContext() {
  forecastTier3Station = null;
  selectedNationalStation = null;
  removeTier3StationOption();
  var picker = document.getElementById("forecast-station");
  if (picker && currentForecastStation) picker.value = currentForecastStation;
  var label = document.getElementById("national-station-selection");
  if (label) {
    label.textContent =
      "No station selected — pick a marker or a search result. Tiers show " +
      "what this project can actually do for each station.";
  }
  updateForecastExportLinks();
}

function resetTier3View() {
  var panel = document.getElementById("forecast-tier3");
  if (panel) {
    panel.hidden = true;
    panel.innerHTML = "";
  }
  var grid = document.getElementById("forecast-grid");
  if (grid) grid.hidden = false;
  var cone = document.querySelector(".forecast-cone-wrap");
  if (cone) cone.hidden = false;
  var badge = document.querySelector("#flood-forecast .pc-badge-predicted");
  if (badge) badge.style.display = "";
}

function renderTier3Forecast(data) {
  var st = data.station || forecastTier3Station || {};
  var name = st.name || st.station || "this station";
  var state = st.state || "";

  var statusEl = document.getElementById("forecast-status");
  if (statusEl) {
    statusEl.textContent =
      "No forecast model or verified water-level series for " + name +
      (state ? " (" + state + ")" : "") + " — station metadata only.";
  }

  var locationEl = document.getElementById("forecast-location");
  if (locationEl) {
    locationEl.textContent =
      "📍 Selected station: " + name + (state ? ", " + state : "") +
      " — this project has no verified water-level series or trained model here.";
  }

  var mlNote = document.getElementById("forecast-ml-note");
  if (mlNote) {
    mlNote.textContent = "no model for this station";
    mlNote.className = "forecast-ml-note off";
  }

  var overallValue = document.getElementById("overall-risk-value");
  if (overallValue) {
    overallValue.textContent = "N/A";
    overallValue.className = "overall-risk-value unknown";
  }
  var overallDetails = document.getElementById("overall-risk-details");
  if (overallDetails) {
    overallDetails.textContent =
      "No probabilities are produced for stations outside the verified set — " +
      "this project does not reuse another station's forecast.";
  }

  var grid = document.getElementById("forecast-grid");
  if (grid) {
    grid.innerHTML = "";
    grid.hidden = true;
  }
  var cone = document.querySelector(".forecast-cone-wrap");
  if (cone) cone.hidden = true;
  // "PREDICTED" would misdescribe a station with no prediction at all.
  // (display, not [hidden]: the badge has an explicit display rule.)
  var badge = document.querySelector("#flood-forecast .pc-badge-predicted");
  if (badge) badge.style.display = "none";
  if (forecastConeChart) {
    forecastConeChart.destroy();
    forecastConeChart = null;
  }

  ["forecast-replay-note", "forecast-persistence", "forecast-legacy-engine"].forEach(
    function (id) {
      var el = document.getElementById(id);
      if (el) el.hidden = true;
    }
  );

  var obsEl = document.getElementById("forecast-observation");
  if (obsEl) {
    var parts = [];
    parts.push("<strong>" + escapeHtml(name) + " · registered station</strong>");
    var meta = [];
    if (state) meta.push(state);
    if (st.district) meta.push("district " + st.district);
    if (st.river) meta.push("river " + st.river);
    if (st.kind) meta.push(st.kind + " station");
    if (Number.isFinite(st.latitude) && Number.isFinite(st.longitude)) {
      meta.push(st.latitude.toFixed(3) + ", " + st.longitude.toFixed(3));
    }
    if (meta.length) parts.push(escapeHtml(meta.join(" · ")));
    if (st.latest_observation) {
      parts.push(
        "Latest registry observation: <strong>" +
        escapeHtml(String(st.latest_observation.value)) + " " +
        escapeHtml(String(st.latest_observation.unit || "")) +
        "</strong> at " +
        escapeHtml(
          String(st.latest_observation.time).slice(0, 16).replace("T", " ")
        ) + " UTC"
      );
    } else {
      parts.push("No observation is recorded for this station in the registry.");
    }
    if (st.n_obs) parts.push(escapeHtml(String(st.n_obs)) + " observations on record.");
    obsEl.innerHTML = parts.join("<br>");
  }

  var panel = document.getElementById("forecast-tier3");
  if (panel) {
    panel.hidden = false;
    panel.innerHTML =
      "<strong>No forecast for " + escapeHtml(name) + ".</strong> " +
      escapeHtml(data.reason || "This station is outside the verified set.") +
      " <br><span class=\"muted\">" +
      escapeHtml(
        data.scope_note ||
          "Forecasts are served for Naraj (trained model) and Alipingal/Nimapara " +
            "(verified series, legacy engine only)."
      ) + "</span>";
  }
}

async function loadFloodForecast() {
  var card = document.getElementById("flood-forecast");
  var grid = document.getElementById("forecast-grid");

  try {
    var statusEl = document.getElementById("forecast-status");
    if (statusEl) {
      statusEl.textContent = "Loading 6h / 12h / 24h AI forecast...";
    }

    var url = API_BASE_URL + "/api/forecast?" + floodForecastQuery();

    var response = await fetch(url);
    if (!response.ok) {
      throw new Error("Forecast API returned HTTP " + response.status);
    }

    var data = await response.json();

    // Tier 3: registry metadata only. Never fall through to the forecast UI.
    if (
      data.status === "station_not_supported" ||
      data.status === "unknown_station" ||
      data.forecast_tier === 3
    ) {
      renderTier3Forecast(data);
      return;
    }

    if (data.status === "error" || !data.forecast) {
      throw new Error(data.error || "Invalid forecast response from API.");
    }

    resetTier3View();

    var horizons = ["6h", "12h", "24h"];
    var labels = { "6h": "6 Hours", "12h": "12 Hours", "24h": "24 Hours" };

    var overallRisk = data.overall_risk || "LOW";
    var studyRegion = data.study_region || "Naraj / Cuttack, Odisha (model study region)";
    var observed = data.observed || {};
    var cone = data.forecast_cone || [];
    var headlineSource =
      data.headline_source || (data.ml_enabled === true ? "rf_model" : "legacy_engine");
    var isRfHeadline = headlineSource === "rf_model";
    var mlAsOf =
      data.ml_result && data.ml_result.as_of
        ? String(data.ml_result.as_of).slice(0, 16).replace("T", " ")
        : null;
    // The legacy engine's result is reported beside the headline, never inside it.
    var legacyEngine = data.legacy_engine || null;
    var legacyStem =
      legacyEngine && legacyEngine.reference_time
        ? String(legacyEngine.reference_time).slice(0, 16).replace("T", " ")
        : "2022-08-31 00:00";

    function forecastItem(key) {
      var forecast = data.forecast[key] || {};
      var probability = Number(
        forecast.flood_probability_percent !== undefined
          ? forecast.flood_probability_percent
          : 0
      );
      var risk = forecast.risk || "LOW";
      var engineItem = legacyEngine && legacyEngine.forecast
        ? legacyEngine.forecast[key]
        : null;
      var engineP =
        engineItem && engineItem.flood_probability_percent !== undefined
          ? Number(engineItem.flood_probability_percent)
          : null;

      var mlBadge = "";
      if (isRfHeadline && engineP !== null) {
        mlBadge =
          '<span class="forecast-ml-badge" title="Legacy statistical engine, observation basis ' +
          escapeHtml(legacyStem) +
          '" — not included in the headline">engine ' +
          engineP.toFixed(1) + "%</span>";
      }

      return (
        '<div class="forecast-item">' +
          '<div class="forecast-item-top">' +
            "<strong>" + escapeHtml(labels[key]) + "</strong>" +
            mlBadge +
          "</div>" +
          '<div class="forecast-bar" role="img" aria-label="' +
            escapeHtml(labels[key]) + " flood probability " +
            probability.toFixed(1) + '%">' +
            '<div class="forecast-bar-fill ' + riskClass(risk) +
            '" style="width:' + Math.min(probability, 100).toFixed(1) + '%"></div>' +
          "</div>" +
          '<span class="forecast-risk ' + riskClass(risk) + '">' +
            escapeHtml(risk) + " · " + probability.toFixed(1) + "%" +
          "</span>" +
        "</div>"
      );
    }

    var probabilities = horizons.map(function (h) {
      return Number(
        data.forecast[h] && data.forecast[h].flood_probability_percent !== undefined
          ? data.forecast[h].flood_probability_percent
          : 0
      );
    });
    var maxProbability = Math.max.apply(null, probabilities);

    if (statusEl) {
      // The amber replay banner carries the "not a live forecast" warning, so
      // the status line only names the source and generation time.
      statusEl.textContent =
        (isRfHeadline
          ? "Random Forest headline (dataset row " + (mlAsOf || "latest") + " UTC)"
          : "Legacy statistical engine only (no ML model for this station)") +
        " — generated " +
        escapeHtml(String(data.generated_at || "").replace("T", " ").slice(0, 16)) +
        " UTC from real CWC records.";
    }

    var locationEl = document.getElementById("forecast-location");
    if (locationEl && FloodWatchState.selectedLocation) {
      // Model scope relative to the selected location.
      var sel = FloodWatchState.selectedLocation;
      var narajKm = haversineKm(sel.latitude, sel.longitude, 20.4717, 85.7656);
      if (narajKm <= 150) {
        locationEl.textContent =
          "📍 Selected location (" + (sel.name || "pin") + ") lies inside the " +
          "Naraj/Cuttack calibrated study region (" + narajKm.toFixed(0) +
          " km to Naraj) — forecast shown for station: " + studyRegion;
      } else {
        locationEl.textContent =
          "📍 AI forecast model currently calibrated for the Naraj/Cuttack study " +
          "region. Location-specific prediction is not available for this " +
          "location yet (" + narajKm.toFixed(0) + " km away). The forecast below " +
          "is for station " + studyRegion + ", shown as the model's study output — " +
          "not a prediction for your selected location.";
      }
    } else if (locationEl) {
      locationEl.textContent = "📍 Model study region: " + studyRegion;
    }

    var mlNote = document.getElementById("forecast-ml-note");
    if (mlNote) {
      if (isRfHeadline) {
        mlNote.textContent = "RF headline";
        mlNote.className = "forecast-ml-note on";
      } else if (data.ml_capable === false) {
        mlNote.textContent = "legacy engine (no ML for this station)";
        mlNote.className = "forecast-ml-note off";
      } else {
        mlNote.textContent = "RF unavailable — legacy engine";
        mlNote.className = "forecast-ml-note off";
      }
    }

    var overallValue = document.getElementById("overall-risk-value");
    if (overallValue) {
      overallValue.textContent = overallRisk.toUpperCase();
      overallValue.className =
        "overall-risk-value " + overallRiskClass(overallRisk);
    }

    var overallDetails = document.getElementById("overall-risk-details");
    if (overallDetails) {
      overallDetails.textContent =
        (isRfHeadline
          ? "Highest RF probability: "
          : "Highest legacy-engine probability: ") +
        maxProbability.toFixed(1) +
        "% across the 6h, 12h and 24h horizons (study-station output).";
    }

    // Historical-replay banner: everything on this card comes from a record
    // that stops in the past, so say so instead of implying a live forecast.
    var replayEl = document.getElementById("forecast-replay-note");
    if (replayEl) {
      var endStamp =
        data.observation_freshness && data.observation_freshness.latest_observation
          ? String(data.observation_freshness.latest_observation)
              .slice(0, 16)
              .replace("T", " ")
          : null;
      if (endStamp) {
        replayEl.hidden = false;
        replayEl.innerHTML =
          "<strong>Historical replay — not a live forecast.</strong> Every value " +
          "on this card replays the CWC record, which ends at <strong>" +
          escapeHtml(endStamp) + " UTC</strong>. No observation after that date " +
          "exists in this deployment, so this is not a current flood risk.";
      } else {
        replayEl.hidden = true;
      }
    }

    if (grid) {
      grid.innerHTML =
        forecastItem("6h") +
        forecastItem("12h") +
        forecastItem("24h");
    }

    // Persistence indicator: latest dataset row vs the flood threshold.
    var persistEl = document.getElementById("forecast-persistence");
    if (persistEl) {
      var persist = data.persistence || null;
      // The persistence check is Naraj-specific (the served dataset models
      // Naraj); don't show it next to a different station's headline.
      if (persist && persist.available && data.station_key === "naraj") {
        persistEl.hidden = false;
        persistEl.innerHTML =
          "<strong>Persistence check (latest dataset row):</strong> Naraj " +
          Number(persist.level_m).toFixed(2) + " m at " +
          escapeHtml(String(persist.level_as_of).slice(0, 16)) + " UTC vs the " +
          Number(persist.threshold_m).toFixed(2) + " m flood threshold — " +
          (persist.above_threshold
            ? "<strong>at or above threshold</strong>"
            : "<strong>" + Math.abs(Number(persist.margin_m)).toFixed(2) +
              " m below it</strong>") +
          '. <span class="muted">Level from the dataset\'s last row; threshold ' +
          "from hf_forecast_baseline.json.</span>";
      } else {
        persistEl.hidden = true;
      }
    }

    var observationEl = document.getElementById("forecast-observation");
    if (observationEl) {
      var stationLabel =
        data.location && data.location.station
          ? data.location.station
          : "Naraj";
      // Freshness: the series ends in the past, so say so on the card itself.
      var fresh = data.observation_freshness || null;
      var freshHtml = "";
      if (fresh && fresh.latest_observation) {
        var obsStamp = String(fresh.latest_observation).slice(0, 16).replace("T", " ");
        var ageLabel =
          fresh.age_days === null || fresh.age_days === undefined
            ? "age unknown"
            : fresh.age_days + " days old";
        freshHtml = fresh.stale
          ? '<span class="freshness-badge is-stale">⚠ STALE DATA: latest observation ' +
            escapeHtml(obsStamp) + " UTC (" + escapeHtml(ageLabel) +
            "; stale past " + escapeHtml(String(fresh.threshold_hours)) + " h)</span> "
          : '<span class="freshness-badge is-fresh">Latest observation ' +
            escapeHtml(obsStamp) + " UTC (" + escapeHtml(ageLabel) + ")</span> ";
      }
      // Headline basis first; the legacy engine's own basis is named as
      // excluded so nobody reads the 2022 river level as the current one.
      var obsHtml =
        freshHtml + "<strong>" + escapeHtml(stationLabel) + " · Headline:</strong> ";
      if (isRfHeadline) {
        obsHtml += "Random Forest, input row " +
          escapeHtml(mlAsOf || "—") + " UTC";
        obsHtml +=
          ' · <span class="muted">legacy engine basis ' +
          escapeHtml(legacyStem) +
          " UTC, excluded from the headline</span>";
      } else {
        obsHtml +=
          "legacy statistical engine, observation basis " +
          escapeHtml(legacyStem) +
          " UTC — no ML model is served for this station";
      }
      // The engine's observed level is an Aug-2022 value, so it stays in the
      // legacy block rather than sitting next to the current ML headline.
      observationEl.innerHTML = obsHtml;

      // Legacy engine detail, in its own block — never in the headline.
      var legacyEl = document.getElementById("forecast-legacy-engine");
      if (legacyEl) {
        if (isRfHeadline && legacyEngine && legacyEngine.forecast) {
          var legacyParts = horizons
            .map(function (h) {
              var item = legacyEngine.forecast[h] || {};
              var p = Number(item.flood_probability_percent);
              return h + " " + (Number.isFinite(p) ? p.toFixed(1) : "—") + "%";
            })
            .join(" · ");
          var legacyLevel =
            legacyEngine.observed && Number(legacyEngine.observed.water_level_m);
          legacyEl.hidden = false;
          legacyEl.innerHTML =
            "<strong>Legacy engine (observation basis " +
            escapeHtml(legacyStem) +
            " UTC, not part of the headline):</strong> " +
            escapeHtml(legacyParts) +
            (Number.isFinite(legacyLevel)
              ? " · engine observed river level " + legacyLevel.toFixed(2) + " m"
              : "") +
            " · " +
            escapeHtml(
              "rule-based rise/level/seasonal engine, kept for comparison only"
            );
        } else {
          legacyEl.hidden = true;
        }
      }

      renderForecastCone(cone, observed, currentForecastStation);
    }

    if (!grid && card) {
      card.innerHTML =
        "<h3>🤖 AI Flood Forecast</h3>" +
        '<div class="forecast-grid">' +
        forecastItem("6h") +
        forecastItem("12h") +
        forecastItem("24h") +
        "</div>";
    }
  } catch (error) {
    console.error("AI Flood Forecast Error:", error);

    var statusEl2 = document.getElementById("forecast-status");
    if (statusEl2) {
      statusEl2.textContent = "⚠️ Unable to load AI forecast: " + error.message;
    }

    if (card && !grid) {
      card.innerHTML =
        "<h3>🤖 AI Flood Forecast</h3>" +
        '<p class="forecast-error">⚠️ Unable to load AI forecast.</p>' +
        "<small>Make sure the FloodWatch API is running at " +
        escapeHtml(API_BASE_URL || "this origin") +
        ".</small>";
    }
  }
}

// ---------------------------------------------------------------------------
// FORECAST CONE CHART (Chart.js, vendored locally)
// ---------------------------------------------------------------------------

var forecastConeChart = null;

function renderForecastCone(cone, observed, stationKey) {
  var canvas = document.getElementById("forecast-cone-chart");
  if (!canvas || typeof Chart === "undefined") return;

  var ctx = canvas.getContext("2d");

  fetch(
    API_BASE_URL +
      "/api/levels/recent?station=" +
      encodeURIComponent(stationKey || currentForecastStation)
  )
    .then(function (r) {
      return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status));
    })
    .then(function (series) {
      drawForecastCone(ctx, canvas, series, cone, observed);
    })
    .catch(function () {
      drawForecastCone(ctx, canvas, { timestamps: [], levels: [] }, cone, observed);
    });
}

function drawForecastCone(ctx, canvas, series, cone, observed) {
  var timestamps = series.timestamps || [];
  var levels = series.levels || [];

  var step = Math.max(1, Math.ceil(timestamps.length / 72));
  var labels = [];
  var observedData = [];
  for (var i = 0; i < timestamps.length; i += step) {
    labels.push(timestamps[i].slice(5, 16).replace("T", " "));
    observedData.push(levels[i]);
  }

  var coneLabels = cone.map(function (c) {
    return "+" + c.h + "h";
  });

  var allLabels = labels.concat(coneLabels);
  var coneLow = [];
  var coneHigh = [];
  for (var j = 0; j < labels.length - 1; j++) {
    coneLow.push(null);
    coneHigh.push(null);
  }
  coneLow.push(observedData[observedData.length - 1] || null);
  coneHigh.push(observedData[observedData.length - 1] || null);
  for (var k = 0; k < cone.length; k++) {
    coneLow.push(cone[k].low);
    coneHigh.push(cone[k].high);
  }

  var thresholdLine = cone.length ? cone[cone.length - 1].threshold : null;

  if (forecastConeChart) {
    forecastConeChart.destroy();
  }

  forecastConeChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: allLabels,
      datasets: [
        {
          label: "Observed water level (m)",
          data: observedData,
          borderColor: "#1769aa",
          backgroundColor: "rgba(23,105,170,0.08)",
          fill: false,
          tension: 0.25,
          pointRadius: 0,
          borderWidth: 2,
          order: 2,
        },
        {
          label: "Forecast cone (low–high)",
          data: coneLow,
          borderColor: "rgba(194,118,12,0.85)",
          backgroundColor: "rgba(194,118,12,0.15)",
          fill: "+1",
          stepped: false,
          spanGaps: true,
          pointRadius: 0,
          borderWidth: 1,
          order: 1,
        },
        {
          label: "Cone high",
          data: coneHigh,
          borderColor: "rgba(194,118,12,0.85)",
          fill: false,
          pointRadius: 0,
          borderWidth: 1,
          spanGaps: true,
          order: 1,
        },
        {
          label: "Flood-signal level",
          data: allLabels.map(function () {
            return thresholdLine;
          }),
          borderColor: "rgba(164,39,31,0.6)",
          borderDash: [6, 4],
          pointRadius: 0,
          borderWidth: 1.5,
          fill: false,
          order: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: { boxWidth: 14, font: { size: 11 } },
        },
        tooltip: {
          callbacks: {
            label: function (item) {
              return item.dataset.label + ": " +
                (item.parsed.y === null ? "—" : item.parsed.y.toFixed(2) + " m");
            },
          },
        },
        title: { display: false },
      },
      scales: {
        x: {
          ticks: { maxTicksLimit: 8, font: { size: 10 } },
          grid: { display: false },
        },
        y: {
          title: { display: true, text: "Water level (m)", font: { size: 11 } },
          ticks: { font: { size: 10 } },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// MODEL INFO PANEL + EXPORT ACTIONS
// ---------------------------------------------------------------------------

function initializeForecastActions() {
  var refreshBtn = document.getElementById("forecast-refresh-btn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      loadFloodForecast();
    });
  }

  var stationSelect = document.getElementById("forecast-station");
  if (stationSelect) {
    stationSelect.addEventListener("change", function () {
      if (!stationSelect.value) return; // tier-3 placeholder option
      forecastTier3Station = null;
      removeTier3StationOption();
      currentForecastStation = stationSelect.value || "naraj";
      updateForecastExportLinks();
      loadFloodForecast();
    });
  }

  var toggle = document.getElementById("model-info-toggle");
  var panel = document.getElementById("model-info-panel");
  if (toggle && panel) {
    toggle.addEventListener("click", function () {
      var isHidden = panel.classList.toggle("hidden");
      toggle.setAttribute("aria-expanded", isHidden ? "false" : "true");
      if (!isHidden && !panel.dataset.loaded) {
        panel.dataset.loaded = "1";
        loadModelInfo(panel);
      }
    });
  }
}

function updateForecastExportLinks() {
  var csv = document.getElementById("forecast-export-csv");
  var json = document.getElementById("forecast-export-json");
  // No export exists for a station this project cannot forecast.
  var hide = !!forecastTier3Station;
  if (csv) csv.style.display = hide ? "none" : "";
  if (json) json.style.display = hide ? "none" : "";
  if (hide) return;
  var suffix =
    "?station=" + encodeURIComponent(currentForecastStation) + "&format=";
  if (csv) csv.setAttribute("href", API_BASE_URL + "/api/forecast/export" + suffix + "csv");
  if (json) json.setAttribute("href", API_BASE_URL + "/api/forecast/export" + suffix + "json");
}

function loadModelInfo(panel) {
  fetch(API_BASE_URL + "/api/model/info")
    .then(function (r) {
      return r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status));
    })
    .then(function (info) {
      var html = "<h4>Model &amp; validation information</h4>";

      if (info.status === "trained") {
        html +=
          '<div class="model-info-row"><strong>Trained:</strong> ' +
          escapeHtml(String(info.trained_at || "").slice(0, 16).replace("T", " ")) +
          " UTC (v" + escapeHtml(String(info.version || 3)) + ")</div>";
        var ds = info.data_source || {};
        if (ds.huggingface_dataset) {
          html +=
            '<div class="model-info-row"><strong>Data:</strong> <a href="https://huggingface.co/datasets/' +
            escapeHtml(ds.huggingface_dataset) + '" target="_blank" rel="noopener">' +
            escapeHtml(ds.huggingface_dataset) + "</a></div>";
        }
        if (ds.github_repo) {
          html +=
            '<div class="model-info-row"><strong>Pipeline:</strong> <a href="' +
            escapeHtml(ds.github_repo) + '" target="_blank" rel="noopener">' +
            escapeHtml(String(ds.github_repo).replace("https://", "")) + "</a> (ml/src)</div>";
        }
        if (ds.raw_inputs) {
          html +=
            '<div class="model-info-row"><strong>Raw inputs:</strong> ' +
            escapeHtml(ds.raw_inputs) + "</div>";
        }
        if (info.dataset) {
          html +=
            '<div class="model-info-row"><strong>Real-data rows:</strong> ' +
            escapeHtml(String(info.dataset.rows)) +
            " hourly (" + escapeHtml(String(info.dataset.start).slice(0, 10)) + " → " +
            escapeHtml(String(info.dataset.end).slice(0, 10)) +
            "), " + escapeHtml(String(info.dataset.features)) + " features</div>";
        }
        if (info.splits && info.splits.periods) {
          html +=
            '<div class="model-info-row"><strong>Chronological split:</strong> ' +
            "train " + escapeHtml(String(info.splits.periods.train || "").slice(0, 10)) +
            " → " + escapeHtml(String(info.splits.periods.val || "").slice(0, 10)) +
            " · test " + escapeHtml(String(info.splits.periods.test || "").slice(0, 10)) +
            " (holdout never seen in training)</div>";
        }
        if (info.label_rule) {
          html +=
            '<div class="model-info-row"><strong>Flood label:</strong> ' +
            escapeHtml(info.label_rule) + "</div>";
        }
        html += '<div class="model-info-row"><strong>Model scope:</strong> calibrated on the Naraj/Cuttack (Mahanadi) historical study data — NOT an India-wide calibrated model.</div>';
        html += '<div class="model-info-row"><strong>Per-horizon skill (holdout test / validation):</strong></div>';
        html += '<table class="model-skill-table"><thead><tr>' +
          "<th>Horizon</th><th>Test Brier</th><th>Test ROC AUC</th><th>Precision</th><th>Recall</th><th>Val Brier</th>" +
          "</tr></thead><tbody>";
        Object.keys(info.horizons || {}).forEach(function (h) {
          var hz = info.horizons[h] || {};
          var te = hz.test || {};
          var va = hz.validation || {};
          html +=
            "<tr><td>" + escapeHtml(h) + "</td><td>" +
            escapeHtml(te.brier !== undefined ? String(te.brier) : "—") +
            "</td><td>" +
            escapeHtml(te.roc_auc !== undefined ? String(te.roc_auc) : "—") +
            "</td><td>" +
            escapeHtml(te.precision !== undefined ? String(te.precision) : "—") +
            "</td><td>" +
            escapeHtml(te.recall !== undefined ? String(te.recall) : "—") +
            "</td><td>" +
            escapeHtml(va.brier !== undefined ? String(va.brier) : "—") +
            "</td></tr>";
        });
        html += "</tbody></table>";
      } else {
        html +=
          '<p class="muted small">Random Forest models are not trained in this ' +
          "checkout. The statistical engine powers the forecast. Run " +
          "<code>python3 ml_train.py</code> to train them.</p>";
      }

      var bridge = info.ml_bridge || {};
      html +=
        '<div class="model-info-row"><strong>RF serving:</strong> ' +
        (bridge.available
          ? "active (" + (bridge.models_loaded || []).length + " models)"
          : "unavailable" + (bridge.reason ? " — " + escapeHtml(bridge.reason) : "")) +
        "</div>";

      (info.notes || []).forEach(function (n) {
        html += '<p class="muted small model-note">• ' + escapeHtml(n) + "</p>";
      });

      panel.innerHTML = html;
    })
    .catch(function (err) {
      panel.innerHTML =
        '<p class="muted small">Could not load model info: ' +
        escapeHtml(err.message) + "</p>";
    });
}

// ---------------------------------------------------------------------------
// INIT (single implementation, single DOMContentLoaded)
// ---------------------------------------------------------------------------

function initializeLocationSearch() {
  var input = document.getElementById("location-search");
  var button = document.getElementById("location-search-button");
  if (!input || !button) return;

  button.addEventListener("click", function () {
    searchLocation(input.value);
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      searchLocation(input.value);
    }
  });
}

// ---------------------------------------------------------------------------
// NATIONAL STATION EXPLORER
//   All 842 registry stations, clustered by zoom level. Selecting one drives
//   the whole location pipeline; the forecast card then states which tier the
//   station is in and refuses to borrow another station's numbers.
// ---------------------------------------------------------------------------

var nationalStations = [];
var nationalStationLayer = null;
var selectedNationalStation = null;

var TIER_COLORS = { 1: "#b3261e", 2: "#e07b00", 3: "#1769aa" };

function nationalTierColor(tier) {
  return TIER_COLORS[tier] || TIER_COLORS[3];
}

function nationalQueryRaw() {
  var el = document.getElementById("national-station-search");
  return el ? String(el.value || "").trim() : "";
}

function nationalQuery() {
  return nationalQueryRaw().toLowerCase();
}

function nationalStateFilter() {
  var el = document.getElementById("national-station-state");
  return el ? el.value || "all" : "all";
}

function nationalFilterSummaryText() {
  var q = nationalQueryRaw();
  var state = nationalStateFilter();
  var bits = [];
  if (q) bits.push('text “' + q + '”');
  if (state !== "all") bits.push("state: " + state);
  return bits;
}

function updateNationalFilterSummary() {
  var el = document.getElementById("national-filter-summary");
  if (!el) return;
  var bits = nationalFilterSummaryText();
  if (!bits.length) {
    el.textContent = "";
    return;
  }
  var shown = nationalFilteredStations().length;
  el.textContent =
    " · showing " + shown + " of " + nationalStations.length +
    " (" + bits.join(", ") + ")";
}

function nationalFilteredStations() {
  var q = nationalQuery();
  var state = nationalStateFilter();
  return nationalStations.filter(function (s) {
    if (!Number.isFinite(s.latitude) || !Number.isFinite(s.longitude)) return false;
    if (state !== "all" && s.state !== state) return false;
    if (q) {
      var hay = [s.station, s.river, s.district, s.state, s.basin]
        .join(" ")
        .toLowerCase();
      if (hay.indexOf(q) === -1) return false;
    }
    return true;
  });
}

async function initNationalStations() {
  var countEl = document.getElementById("national-station-count");
  try {
    var res = await fetch(API_BASE_URL + "/api/stations/india_cwc?limit=2000");
    if (!res.ok) throw new Error("HTTP " + res.status);
    var data = await res.json();
    nationalStations = Array.isArray(data.stations) ? data.stations : [];
    if (!nationalStations.length) {
      if (countEl) countEl.textContent = "No stations in the registry.";
      return;
    }

    var tiers = { 1: 0, 2: 0, 3: 0 };
    var states = {};
    nationalStations.forEach(function (s) {
      var t = s.forecast_tier || 3;
      tiers[t] = (tiers[t] || 0) + 1;
      if (s.state) states[s.state] = true;
    });
    if (countEl) {
      countEl.textContent =
        nationalStations.length + " stations · " +
        Object.keys(states).length + " states · " +
        (tiers[1] + tiers[2]) + " with verified series";
    }

    var stateSel = document.getElementById("national-station-state");
    if (stateSel) {
      Object.keys(states)
        .sort()
        .forEach(function (name) {
          var opt = document.createElement("option");
          opt.value = name;
          opt.textContent = name;
          stateSel.appendChild(opt);
        });
    }

    var search = document.getElementById("national-station-search");
    if (search) {
      var debounce = null;
      search.addEventListener("input", function () {
        clearTimeout(debounce);
        debounce = setTimeout(function () {
          renderNationalSearchResults();
          renderNationalMarkers();
        }, 150);
      });
      search.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          var first = nationalFilteredStations()[0];
          if (first) selectNationalStation(first);
        }
      });
    }
    if (stateSel) {
      stateSel.addEventListener("change", function () {
        renderNationalSearchResults();
        renderNationalMarkers();
      });
    }
    var reset = document.getElementById("national-station-reset");
    if (reset) {
      reset.addEventListener("click", function () {
        if (search) search.value = "";
        if (stateSel) stateSel.value = "all";
        renderNationalSearchResults();
        renderNationalMarkers();
      });
    }

    whenPublicMapReady(function () {
      renderNationalMarkers();
    });
  } catch (error) {
    console.error("National station registry failed:", error);
    if (countEl) {
      countEl.textContent =
        "Station registry unavailable — " + error.message +
        ". The map still accepts any location.";
    }
  }
}

function whenPublicMapReady(fn) {
  var tries = 0;
  (function attempt() {
    var map = null;
    try {
      if (typeof map1 !== "undefined" && map1) map = map1;
    } catch (e) { /* not ready */ }
    if (map) {
      fn();
      return;
    }
    tries += 1;
    if (tries < 40) setTimeout(attempt, 250);
  })();
}

function renderNationalMarkers() {
  var map = null;
  try {
    if (typeof map1 !== "undefined" && map1) map = map1;
  } catch (e) { /* not ready */ }
  if (!map || !nationalStations.length) return;

  if (!map.__nationalZoomBound) {
    map.__nationalZoomBound = true;
    map.on("zoomend", function () {
      renderNationalMarkers();
    });
  }

  if (nationalStationLayer) {
    map.removeLayer(nationalStationLayer);
    nationalStationLayer = null;
  }

  updateNationalFilterSummary();
  var stations = nationalFilteredStations();
  var layer = L.layerGroup();
  var zoom = map.getZoom();
  // Degrees per cluster cell: coarse at country scale, individual at city scale.
  var cell = zoom >= 9 ? 0 : zoom >= 7 ? 0.5 : zoom >= 5 ? 1.5 : 3;

  if (!cell) {
    stations.forEach(function (st) {
      layer.addLayer(nationalMarker(st));
    });
  } else {
    var buckets = {};
    stations.forEach(function (st) {
      var key =
        Math.floor(st.latitude / cell) + ":" + Math.floor(st.longitude / cell);
      (buckets[key] = buckets[key] || []).push(st);
    });
    Object.keys(buckets).forEach(function (key) {
      var group = buckets[key];
      var count = group.length;
      var lat = 0;
      var lon = 0;
      var topTier = 3;
      group.forEach(function (s) {
        lat += s.latitude;
        lon += s.longitude;
        topTier = Math.min(topTier, s.forecast_tier || 3);
      });
      lat = lat / count;
      lon = lon / count;
      var color = nationalTierColor(topTier);
      var marker = L.circleMarker([lat, lon], {
        radius: Math.min(26, 6 + Math.sqrt(count) * 2.2),
        color: color,
        weight: 1,
        fillColor: color,
        fillOpacity: 0.35,
        bubblingMouseEvents: false,
      });
      marker.bindTooltip(
        count + " station" + (count === 1 ? "" : "s") + " — click to zoom in",
        { direction: "top" }
      );
      marker.on("click", function () {
        map.setView([lat, lon], Math.min(zoom + 2, 11));
      });
      layer.addLayer(marker);
    });
  }

  layer.addTo(map);
  nationalStationLayer = layer;
}

function nationalMarker(st) {
  var tier = st.forecast_tier || 3;
  var color = nationalTierColor(tier);
  var marker = L.circleMarker([st.latitude, st.longitude], {
    radius: tier === 3 ? 4 : 6,
    color: color,
    weight: 1,
    fillColor: color,
    fillOpacity: 0.8,
    bubblingMouseEvents: false,
  });
  var dqNote =
    st.data_quality && st.data_quality.coordinate_state_mismatch
      ? " ⚠ coordinate/state mismatch in source data"
      : "";
  marker.bindTooltip(
    st.station + " · " + (st.state || "") + " — " +
      (st.forecast_tier_label || "") + dqNote,
    { direction: "top" }
  );
  marker.on("click", function () {
    selectNationalStation(st);
  });
  return marker;
}

function renderNationalSearchResults() {
  var list = document.getElementById("national-station-results");
  if (!list) return;
  var q = nationalQuery();
  var state = nationalStateFilter();
  updateNationalFilterSummary();
  if (!q && state === "all") {
    list.hidden = true;
    list.innerHTML = "";
    return;
  }
  var matches = nationalFilteredStations().slice(0, 10);
  list.hidden = false;
  if (!matches.length) {
    // Say WHICH filters produced the empty result, and offer a one-click way
    // to drop either of them.
    var bits = nationalFilterSummaryText();
    var shownQuery = nationalQueryRaw();
    var msg = q && state !== "all"
      ? "No stations match “" + shownQuery + "” in " + state + "."
      : q
        ? "No stations match “" + shownQuery + "”."
        : "No stations in " + state + ".";
    list.innerHTML =
      '<li class="national-empty"><span>' + escapeHtml(msg) +
      ' <span class="muted">Active filters: ' + escapeHtml(bits.join(", ")) +
      "</span></span>" +
      (q ? '<button type="button" data-clear="text">Clear text filter</button>' : "") +
      (state !== "all" ? '<button type="button" data-clear="state">Clear state filter</button>' : "") +
      '<button type="button" data-clear="all">Reset all</button></li>';
    list.querySelectorAll("button[data-clear]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var what = btn.getAttribute("data-clear");
        var search = document.getElementById("national-station-search");
        var stateSel = document.getElementById("national-station-state");
        if ((what === "text" || what === "all") && search) search.value = "";
        if ((what === "state" || what === "all") && stateSel) stateSel.value = "all";
        renderNationalSearchResults();
        renderNationalMarkers();
      });
    });
    return;
  }
  list.innerHTML = "";
  matches.forEach(function (st) {
    var li = document.createElement("li");
    var btn = document.createElement("button");
    btn.type = "button";
    var flagged = st.data_quality && st.data_quality.coordinate_state_mismatch;
    btn.innerHTML =
      escapeHtml(st.station) + " · " + escapeHtml(st.state || "") +
      ' <span class="muted">(' + escapeHtml(st.forecast_tier_label || "") + ")</span>" +
      (flagged ? ' <span class="national-dq-warn">⚠ coordinate/state mismatch</span>' : "");
    btn.addEventListener("click", function () {
      selectNationalStation(st);
    });
    li.appendChild(btn);
    list.appendChild(li);
  });
}

function selectNationalStation(st) {
  if (!st) return;
  selectedNationalStation = st;
  var label = document.getElementById("national-station-selection");
  if (label) {
    var obsNote = st.latest_observation
      ? "latest registry " + (st.kind || "") + " observation " +
        st.latest_observation.value + " " +
        (st.latest_observation.unit || "") + " at " +
        String(st.latest_observation.time).slice(0, 16).replace("T", " ") +
        " UTC"
      : "no observation recorded in the registry";
    var dq = st.data_quality && st.data_quality.coordinate_state_mismatch;
    label.innerHTML =
      "<strong>" + escapeHtml(st.station) + "</strong> · " +
      escapeHtml(st.state || "state unknown") + " · " +
      escapeHtml(st.forecast_tier_label || "") + " · " + escapeHtml(obsNote) +
      (dq
        ? ' · <span class="national-dq-warn">⚠ location in source data looks ' +
          "inconsistent with the recorded state — map not recentred</span>"
        : "");
  }

  if (st.forecast_station_key) {
    forecastTier3Station = null;
    removeTier3StationOption();
    currentForecastStation = st.forecast_station_key;
    var picker = document.getElementById("forecast-station");
    if (picker) picker.value = st.forecast_station_key;
  } else {
    forecastTier3Station = st;
    setTier3StationOption(st);
  }
  updateForecastExportLinks();

  var flaggedCoords = !!(st.data_quality && st.data_quality.coordinate_state_mismatch);
  setSelectedLocation(st.latitude, st.longitude, st.station, {
    state: st.state || "",
    zoom: 8,
    keepStationForecast: true,
    suppressRecenter: flaggedCoords,
  });
  loadFloodForecast();
  renderNationalSearchResults();
}

// Let public.js register its maps with the shared location pipeline.
// Newly-registered maps immediately adopt the current selection (or the
// India-wide default when nothing is selected yet).
function bindPublicMaps() {
  var tries = 0;
  (function attempt() {
    tries += 1;
    var before = FloodWatchState.maps.length;
    try {
      if (typeof map1 !== "undefined" && map1) {
        registerMap(map1);
      }
    } catch (e) { /* not ready yet */ }
    try {
      if (typeof map2 !== "undefined" && map2) {
        registerMap(map2);
      }
    } catch (e) { /* not ready yet */ }
    var added = FloodWatchState.maps.length - before;
    if (added > 0) {
      var sel = FloodWatchState.selectedLocation;
      FloodWatchState.maps.slice(-added).forEach(function (map) {
        if (sel) {
          map.setView(
            [sel.latitude, sel.longitude],
            LOCATION_ZOOM
          );
        } else {
          map.setView(
            [INDIA_DEFAULT.latitude, INDIA_DEFAULT.longitude],
            INDIA_DEFAULT.zoom
          );
        }
      });
      removeLocationLayers();
      var primary = getActiveMap();
      if (primary && sel) {
        ensureUserMarker(primary, sel.latitude, sel.longitude, sel.name);
      }
    }
    if (FloodWatchState.maps.length < 2 && tries < 40) {
      setTimeout(attempt, 250);
    }
  })();
}

function startDashboard() {
  initializeGeolocation();
  initializeLocationSearch();
  initializeForecastActions();
  updateForecastExportLinks();
  initNationalStations();
  bindPublicMaps();

  // Panels start honest and empty until the user selects a location.
  showStatus("Select any location in India to explore flood intelligence.", "info");

  loadFloodForecast();
}

document.addEventListener("DOMContentLoaded", startDashboard);

console.log("FloodWatch dashboard layer loaded successfully.");
