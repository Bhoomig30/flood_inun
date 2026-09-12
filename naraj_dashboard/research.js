// AI-Driven Flood Inundation Analysis & Decision Support System — application logic
// Demonstration case: Mahanadi Basin, Odisha (Naraj gauge currently selected).
// Reads only local, verified data files. No flood classification, calibrated SAR
// value, danger level, accuracy figure, or invented coordinate is computed here.

const STATUS_TAG_CLASS = { OBSERVED: "tag-observed", HISTORICAL: "tag-historical", DERIVED: "tag-derived", PENDING: "tag-pending", REFERENCE: "tag-reference", "NO SAR COVERAGE": "tag-nocoverage" };
function tag(status) { return `<span class="tag ${STATUS_TAG_CLASS[status] || "tag-derived"}">${status}</span>`; }
async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "overview") setTimeout(() => map.invalidateSize(), 50);
  });
});

function goToTab(tabId) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) btn.click();
}

// Situation cards -> click to jump to the relevant tab
document.querySelectorAll(".sit-card").forEach((card) => {
  card.addEventListener("click", () => goToTab(card.dataset.goto));
});

// ---------------------------------------------------------------------------
// Map setup
// ---------------------------------------------------------------------------
const map = L.map("map", { zoomControl: true }).setView([20.4717, 85.7656], 10);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
const leafletLayers = {};
let stationMarkers = {}; // name -> marker

function markerIcon(color, size = 14) {
  return L.divIcon({
    className: "",
    html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 0 1px rgba(0,0,0,0.3);"></div>`,
    iconSize: [size, size], iconAnchor: [size / 2, size / 2],
  });
}

async function buildStationsLayer(cfg) {
  const gj = await loadJSON(cfg.file);
  const group = L.layerGroup();
  gj.features.forEach((f) => {
    const p = f.properties;
    const [lon, lat] = f.geometry.coordinates;
    const isFocus = p.is_focus_station;
    const color = isFocus ? "#a4271f" : (p.is_mainstem ? "#0f6b78" : "#8a97a0");
    const marker = L.marker([lat, lon], { icon: markerIcon(color, isFocus ? 16 : 9) });
    marker.bindPopup(
      `<strong>${p.name}</strong> ${tag("OBSERVED")}<br>
       ${p.local_river} ${p.is_mainstem ? "(mainstem)" : "(tributary)"} · ${p.district}, ${p.state}<br>
       Range: ${p.min_wl_m}–${p.max_wl_m} m (mean ${p.mean_wl_m} m)<br>
       ${p.n_obs.toLocaleString()} observations, ${p.date_range_start} → ${p.date_range_end}`
    );
    marker.on("click", () => { if (isFocus) selectStation(p.name); });
    stationMarkers[p.name] = marker;
    group.addLayer(marker);
  });
  return group;
}

async function buildLayer(cfg) {
  if (cfg.type === "stations") return buildStationsLayer(cfg);
  if (cfg.type === "geojson") {
    if (!cfg.file) return null;
    const gj = await loadJSON(cfg.file);
    return L.geoJSON(gj, {
      style: () => cfg.style || {},
      onEachFeature: (feature, layer) => layer.bindPopup(`<strong>${cfg.label}</strong><br>${tag(cfg.status)}`),
    });
  }
  if (cfg.type === "point") {
    const gj = await loadJSON(cfg.file);
    const feature = gj.features[0];
    const [lon, lat] = feature.geometry.coordinates;
    const marker = L.marker([lat, lon], { icon: markerIcon("#a4271f", 18) });
    const p = feature.properties;
    marker.bindPopup(`<strong>${p.name} Gauge (primary)</strong><br>${tag("OBSERVED")}<br>${lat.toFixed(6)}°N, ${lon.toFixed(6)}°E`);
    return marker;
  }
  if (cfg.type === "image_overlay") {
    const bounds = await loadJSON(cfg.bounds_file);
    const b = bounds.bounds;
    return L.imageOverlay(cfg.file, [[b.south, b.west], [b.north, b.east]], { opacity: 0.65 });
  }
  return null;
}

async function initLayers() {
  const layers = await loadJSON("data/layers.json");
  const groupsEl = document.getElementById("layer-groups");
  const groups = {};
  layers.forEach((cfg) => { groups[cfg.group] = groups[cfg.group] || []; groups[cfg.group].push(cfg); });

  for (const [groupName, cfgs] of Object.entries(groups)) {
    const title = document.createElement("div");
    title.className = "layer-group-title";
    title.textContent = groupName;
    groupsEl.appendChild(title);

    for (const cfg of cfgs) {
      const isPending = cfg.status === "PENDING" || !cfg.file;
      const row = document.createElement("div");
      row.className = "layer-row" + (isPending ? " pending" : "");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox"; checkbox.id = `layer-${cfg.id}`;
      checkbox.disabled = isPending;
      checkbox.checked = !!cfg.default_on && !isPending;
      const label = document.createElement("label");
      label.htmlFor = checkbox.id;
      label.innerHTML = `${cfg.label} ${tag(cfg.status)}`;
      if (cfg.note) label.title = cfg.note;
      row.appendChild(checkbox); row.appendChild(label);
      groupsEl.appendChild(row);
      if (isPending) continue;

      const layer = await buildLayer(cfg);
      if (!layer) continue;
      leafletLayers[cfg.id] = layer;
      if (checkbox.checked) layer.addTo(map);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) layer.addTo(map); else map.removeLayer(layer);
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Multi-station view (Feature 1)
// ---------------------------------------------------------------------------
const FOCUS_STATIONS = ["Naraj", "Alipingal", "Nimapara"];
const STATION_FILE_KEY = { Naraj: "naraj", Alipingal: "alipingal", Nimapara: "nimapara" };
let currentStation = "Naraj";
let wlChart = null;
let stationSummaries = {};

async function initStationSelector() {
  const gj = await loadJSON("data/cwc_stations.geojson");
  gj.features.forEach((f) => { stationSummaries[f.properties.name] = f.properties; });

  const el = document.getElementById("station-select");
  const chipRow = document.createElement("div");
  chipRow.className = "station-chip-row";
  FOCUS_STATIONS.forEach((name) => {
    const chip = document.createElement("div");
    chip.className = "station-chip" + (name === currentStation ? " active" : "");
    chip.id = `chip-${name}`;
    chip.textContent = name;
    chip.addEventListener("click", () => selectStation(name));
    chipRow.appendChild(chip);
  });
  el.appendChild(chipRow);

  const info = document.createElement("div");
  info.className = "station-info";
  info.id = "station-info";
  el.appendChild(info);

  await selectStation(currentStation);
}

async function selectStation(name) {
  currentStation = name;
  document.querySelectorAll(".station-chip").forEach((c) => c.classList.remove("active"));
  const chip = document.getElementById(`chip-${name}`);
  if (chip) chip.classList.add("active");

  const s = stationSummaries[name];
  const infoEl = document.getElementById("station-info");
  if (infoEl && s) {
    infoEl.innerHTML = `${s.local_river} ${s.is_mainstem ? "(mainstem)" : "(tributary)"} · ${s.district}, ${s.state}<br>
      Range ${s.min_wl_m}–${s.max_wl_m} m · ${s.n_obs.toLocaleString()} obs. ${tag("OBSERVED")}`;
  }

  if (leafletLayers.cwc_stations) {
    const marker = stationMarkers[name];
    if (marker) map.panTo(marker.getLatLng());
  }

  const fileKey = STATION_FILE_KEY[name];
  const data = await loadJSON(`data/cwc/${fileKey}_daily_2021_2025.json`);
  const labels = data.records.map((r) => r.date);
  const values = data.records.map((r) => r.water_level_m);
  if (wlChart) wlChart.destroy();
  wlChart = new Chart(document.getElementById("wl-chart"), {
    type: "line",
    data: { labels, datasets: [{ label: `${name} daily mean (m)`, data: values, borderColor: "#0f6b78", backgroundColor: "rgba(15,107,120,0.08)", borderWidth: 1.2, pointRadius: 0, fill: true, tension: 0 }] },
    options: { responsive: true, plugins: { legend: { display: false } },
      scales: { x: { ticks: { maxTicksLimit: 6, font: { size: 9 } }, grid: { display: false } }, y: { title: { display: true, text: "meters", font: { size: 10 } }, ticks: { font: { size: 9 } } } } },
  });
  document.getElementById("wl-chart-caption").innerHTML = `Daily mean, manual hourly gauge readings, 2021–2025 (${tag("OBSERVED")})`;

  if (currentEvent) updateSituation(currentEvent, name);
}

// ---------------------------------------------------------------------------
// Historical event explorer / Flood Evolution timeline (Feature 1)
// ---------------------------------------------------------------------------
let eventsData = null;
let currentEvent = null;

async function initTimeline() {
  eventsData = await loadJSON("data/events_august2022.json");
  const el = document.getElementById("evolution-stepper");
  eventsData.events.forEach((evt, idx) => {
    const item = document.createElement("div");
    item.className = "evo-step";
    item.id = `evo-${evt.id}`;
    const hasMask = evt.flood_mask_sar_derived.status === "DERIVED";
    item.innerHTML = `
      <div class="evo-dot"></div>
      <div class="evo-date">${evt.date.slice(5)}</div>
      <div class="evo-wl">${evt.cwc_observed.water_level_m} m</div>
      <div class="evo-badges">
        ${tag(evt.ndem_inundation.status)}
        ${hasMask ? tag("DERIVED") : ""}
      </div>
    `;
    item.addEventListener("click", () => selectEvent(evt.id));
    el.appendChild(item);
    if (idx < eventsData.events.length - 1) {
      const connector = document.createElement("div");
      connector.className = "evo-connector";
      el.appendChild(connector);
    }
  });
  selectEvent("ndem_18aug");
}

function selectEvent(eventId) {
  currentEvent = eventId;
  document.querySelectorAll(".evo-step").forEach((el) => el.classList.remove("active"));
  const activeEl = document.getElementById(`evo-${eventId}`);
  if (activeEl) activeEl.classList.add("active");

  const evt = eventsData.events.find((e) => e.id === eventId);
  if (!evt) return;

  const el = document.getElementById("event-detail");
  el.innerHTML = `
    <div class="detail-row"><span class="detail-label">Date</span><span class="detail-value">${evt.date}</span></div>
    <div class="detail-row"><span class="detail-label">CWC Level (Naraj)</span><span class="detail-value">${evt.cwc_observed.water_level_m} m ${tag(evt.cwc_observed.status)}</span></div>
    <div class="detail-row"><span class="detail-label">Reading Time</span><span class="detail-value">${evt.cwc_observed.nearest_reading_time.replace("T", " ")}</span></div>
    <div class="detail-row"><span class="detail-label">Satellite Evidence</span><span class="detail-value text">${tag(evt.satellite_evidence.status)}</span></div>
    <div class="detail-row"><span class="detail-label">NDEM Inundation</span><span class="detail-value text">${tag(evt.ndem_inundation.status)}</span></div>
    <div class="detail-row"><span class="detail-label">SAR Flood Mask</span><span class="detail-value text">${tag(evt.flood_mask_sar_derived.status)}</span></div>
    <p class="muted" style="margin-top:8px; line-height:1.4;">${evt.satellite_evidence.detail}</p>
  `;

  Object.entries(leafletLayers).forEach(([id, layer]) => { if (id.startsWith("ndem_")) map.removeLayer(layer); });
  const matchLayer = leafletLayers[eventId];
  if (matchLayer) {
    matchLayer.addTo(map);
    const cb = document.getElementById(`layer-${eventId}`);
    if (cb) cb.checked = true;
    document.querySelectorAll('[id^="layer-ndem_"]').forEach((cb2) => { if (cb2.id !== `layer-${eventId}`) cb2.checked = false; });
  }

  updateSituation(eventId, currentStation);
}

// ---------------------------------------------------------------------------
// Situation summary cards (Feature 5)
// ---------------------------------------------------------------------------
function updateSituation(eventId, stationName) {
  const evt = eventsData.events.find((e) => e.id === eventId);
  if (!evt) return;
  const hasMask = evt.flood_mask_sar_derived.status === "DERIVED";

  document.getElementById("sit-event").textContent = evt.date;
  document.getElementById("sit-cwc").textContent = `${evt.cwc_observed.water_level_m} m`;
  document.getElementById("sit-sar").textContent = evt.satellite_evidence.status === "OBSERVED" ? "Detected" : "No coverage";
  document.getElementById("sit-candidate").textContent = hasMask ? `${window.__candidateAreaKm2} km²` : "N/A for this date";
  document.getElementById("sit-ref").textContent = evt.ndem_inundation.available ? "NDEM available" : "None";
  document.getElementById("sit-validation").textContent = hasMask ? `IoU ${window.__iouScore}` : "N/A for this date";
}

// ---------------------------------------------------------------------------
// NDEM inundated area (Feature 4)
// ---------------------------------------------------------------------------
async function initNdemArea() {
  const data = await loadJSON("data/ndem_inundated_area.json");
  const el = document.getElementById("ndem-area-panel");
  Object.entries(data.events).forEach(([date, info]) => {
    const row = document.createElement("div");
    row.className = "ndem-area-row";
    row.innerHTML = `<span>${date}</span><span class="v">${info.inundated_area_km2_within_aoi} km²</span>`;
    row.title = info.method;
    el.appendChild(row);
  });
  const note = document.createElement("p");
  note.className = "muted small";
  note.style.marginTop = "6px";
  note.textContent = "Area computed directly from verified NDEM polygon geometry (EPSG:32645), clipped to the Naraj AOI. Not a modeled or predicted value.";
  el.appendChild(note);
}

// ---------------------------------------------------------------------------
// SAR comparison (Feature 3)
// ---------------------------------------------------------------------------
async function initS1Cards() {
  const data = await loadJSON("data/sentinel1/scenes_metadata.json");
  const el = document.getElementById("s1-cards");
  data.scenes.forEach((s) => {
    const card = document.createElement("div");
    card.className = "s1-card";
    card.innerHTML = `
      <div class="s1-card-title">${s.date} — ${s.role} ${tag("OBSERVED")}</div>
      <div class="s1-card-row"><span>Orbit</span><span class="v">${s.relative_orbit} (${s.pass_direction})</span></div>
      <div class="s1-card-row"><span>Product</span><span class="v">${s.product_type}, ${s.mode}, ${s.polarizations.join("+")}</span></div>
      <div class="s1-card-row"><span>Naraj covered</span><span class="v">${s.naraj_covered ? "Yes" : "No"}</span></div>
      <div class="s1-card-row"><span>AOI coverage</span><span class="v">${s.aoi_coverage_pct}%</span></div>
      <p class="muted" style="margin:6px 0 0; line-height:1.35;">${s.calibration_status}</p>
    `;
    el.appendChild(card);
  });
}

// ---------------------------------------------------------------------------
// SAR candidate mask summary + NDEM validation summary
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Guided demo flow — pure navigation aid, no fake automation
// ---------------------------------------------------------------------------
function initGuidedFlow() {
  const steps = {
    1: () => { goToTab("overview"); },
    2: () => { goToTab("sar"); },
    3: () => {
      goToTab("sar");
      setTimeout(() => {
        const body = document.getElementById("why-flagged-content");
        if (body.classList.contains("hidden")) document.getElementById("why-flagged-toggle").click();
        document.getElementById("why-flagged-panel")?.scrollIntoView({behavior:"smooth", block:"center"});
        document.querySelector(".why-flagged-panel")?.scrollIntoView({behavior:"smooth", block:"center"});
      }, 150);
    },
    4: () => { goToTab("validation"); },
    5: () => { goToTab("exposure"); },
    6: () => {
      goToTab("confidence");
      setTimeout(() => document.getElementById("aiml-panel")?.scrollIntoView({behavior:"smooth", block:"center"}), 150);
    },
  };
  document.querySelectorAll(".guided-step").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".guided-step").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const fn = steps[btn.dataset.step];
      if (fn) fn();
    });
  });
}

// ---------------------------------------------------------------------------
// Flood analysis result summary (Overview tab, prioritized)
// ---------------------------------------------------------------------------
async function initAnalysisResultSummary() {
  const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
  const m = await loadJSON("data/sar_flood/validation_metrics.json");
  const el = document.getElementById("analysis-result-summary");
  el.innerHTML = `
    <div class="detail-row"><span class="detail-label">Candidate inundation area</span><span class="detail-value">${params.final_candidate_area_km2} km²</span></div>
    <div class="detail-row"><span class="detail-label">% of valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}%</span></div>
    <div class="detail-row"><span class="detail-label">Validation vs NDEM (F1 / IoU)</span><span class="detail-value">${m.f1} / ${m.iou}</span></div>
    <p class="muted small" style="margin-top:8px; line-height:1.4;">Independently derived from Sentinel-1 6-Aug → 18-Aug change detection, then compared against NDEM. See SAR Comparison tab for full detail.</p>
  `;
}

async function initSarMaskSummary() {
  const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
  const el = document.getElementById("sar-mask-summary");
  el.innerHTML = `
    <div class="detail-row"><span class="detail-label">Threshold</span><span class="detail-value">${params.threshold_db_drop} dB drop (both VV and VH, plus combined)</span></div>
    <div class="detail-row"><span class="detail-label">Spatial filter</span><span class="detail-value text">Remove groups &lt; ${params.min_connected_component_pixels} connected pixels</span></div>
    <div class="detail-row"><span class="detail-label">Candidate area</span><span class="detail-value">${params.final_candidate_area_km2} km² ${tag("DERIVED")}</span></div>
    <div class="detail-row"><span class="detail-label">% of valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}%</span></div>
  `;
}

async function initSarValidationSummary() {
  const m = await loadJSON("data/sar_flood/validation_metrics.json");
  const el = document.getElementById("sar-validation-summary");
  el.innerHTML = `
    <div class="detail-row"><span class="detail-label">IoU</span><span class="detail-value">${m.iou}</span></div>
    <div class="detail-row"><span class="detail-label">Precision</span><span class="detail-value">${m.precision}</span></div>
    <div class="detail-row"><span class="detail-label">Recall</span><span class="detail-value">${m.recall}</span></div>
    <div class="detail-row"><span class="detail-label">F1</span><span class="detail-value">${m.f1}</span></div>
    <div class="detail-row"><span class="detail-label">NDEM reference area (SAR coverage)</span><span class="detail-value">${m.ndem_flood_km2_within_sar_coverage} km²</span></div>
    <div class="detail-row"><span class="detail-label">SAR candidate area (SAR coverage)</span><span class="detail-value">${m.sar_flood_km2_within_sar_coverage} km²</span></div>
    <p class="muted small" style="margin-top:8px; line-height:1.4;">${m.note} Prototype-stage metrics — precision is currently low (the mask over-detects, particularly along river-channel margins where backscatter changed without necessarily reflecting new inundation). This is not a validated operational accuracy figure.</p>
  `;
}

// ---------------------------------------------------------------------------
// SAR four-stage visual story (Feature 2)
// ---------------------------------------------------------------------------
const SAR_STAGES = {
  preflood: {
    vv: { src: "data/sar_flood/preflood_vv.png", caption: "6-Aug-2022 — pre-flood reference. Calibrated Sentinel-1A VV sigma0 (dB), geocoded. This establishes the baseline backscatter before the event." },
    vh: { src: "data/sar_flood/preflood_vh.png", caption: "6-Aug-2022 — pre-flood reference. Calibrated Sentinel-1A VH sigma0 (dB), geocoded." },
  },
  duringflood: {
    vv: { src: "data/sar_flood/duringflood_vv.png", caption: "18-Aug-2022 — during-flood observation. Calibrated VV sigma0 (dB). Compare directly against the pre-flood image above — darker areas indicate lower backscatter, not automatically water." },
    vh: { src: "data/sar_flood/duringflood_vh.png", caption: "18-Aug-2022 — during-flood observation. Calibrated VH sigma0 (dB)." },
  },
  change: {
    vv: { src: "data/sar_flood/change_combined.png", caption: "SAR change (combined VV+VH, dB) — 18-Aug minus 6-Aug. Blue = darkening (backscatter drop), red = brightening. This is the input to candidate generation, not a flood map itself." },
    vh: { src: "data/sar_flood/change_combined.png", caption: "SAR change (combined VV+VH, dB) — 18-Aug minus 6-Aug. Blue = darkening (backscatter drop), red = brightening." },
  },
  candidate: {
    vv: { src: "data/sar_flood/preflood_vv.png", caption: "Candidate inundation — see the map (Overview tab) or the mask summary below for the actual polygon layer. Independently derived from the change map, then spatially filtered." },
    vh: { src: "data/sar_flood/preflood_vv.png", caption: "Candidate inundation — see the map (Overview tab) or the mask summary below for the actual polygon layer." },
  },
};

function initSarStageViewer() {
  const img = document.getElementById("sar-stage-img");
  const caption = document.getElementById("sar-stage-caption");
  const polToggle = document.getElementById("sar-pol-toggle");
  let stage = "preflood", pol = "vv";

  function render() {
    const data = SAR_STAGES[stage][pol];
    img.src = data.src;
    caption.textContent = data.caption;
    polToggle.style.display = stage === "candidate" ? "none" : "flex";
  }

  document.querySelectorAll(".stage-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".stage-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      stage = btn.dataset.stage;
      render();
    });
  });
  document.querySelectorAll(".pol-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pol-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      pol = btn.dataset.pol;
      render();
    });
  });
  render();
}

// ---------------------------------------------------------------------------
// "Why was this area flagged?" explain panel (Feature 3)
// ---------------------------------------------------------------------------
async function initWhyFlagged() {
  const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
  const scenes = await loadJSON("data/sentinel1/scenes_metadata.json");
  const el = document.getElementById("why-flagged-content");
  const preflood = scenes.scenes.find((s) => s.id === "s1_06aug");
  const duringflood = scenes.scenes.find((s) => s.id === "s1_18aug");

  el.innerHTML = `
    <div class="detail-row"><span class="detail-label">Pre-flood reference</span><span class="detail-value">${preflood.date} (${preflood.product_type}, ${preflood.polarizations.join("+")})</span></div>
    <div class="detail-row"><span class="detail-label">During-flood observation</span><span class="detail-value">${duringflood.date} (${duringflood.product_type}, ${duringflood.polarizations.join("+")})</span></div>
    <div class="detail-row"><span class="detail-label">Rule applied</span><span class="detail-value text">${params.condition}</span></div>
    <div class="detail-row"><span class="detail-label">Threshold (T)</span><span class="detail-value">${params.threshold_db_drop} dB drop</span></div>
    <div class="detail-row"><span class="detail-label">Spatial filtering</span><span class="detail-value text">Applied — groups &lt; ${params.min_connected_component_pixels} connected pixels removed</span></div>
    <div class="detail-row"><span class="detail-label">Valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}% of AOI has SAR data for this pair</span></div>
    <div class="detail-row"><span class="detail-label">Result</span><span class="detail-value">${params.final_candidate_area_km2} km² flagged as candidate</span></div>
    <p class="muted" style="margin-top:10px; line-height:1.5;">
      Candidate inundation areas were identified from <strong>consistent Sentinel-1 backscatter change</strong>
      between the pre-flood (${preflood.date}) and during-flood (${duringflood.date}) observations — both VV and
      VH must independently exceed the threshold, and the combined change must too — followed by the project's
      spatial filtering procedure. <strong>This is a candidate result, not a final operational flood
      classification.</strong> Full sensitivity analysis across threshold values is documented in
      <code>SAR_FLOOD_DETECTION_REPORT.md</code>.
    </p>
  `;
  document.getElementById("why-flagged-toggle").addEventListener("click", () => {
    el.classList.toggle("hidden");
    document.getElementById("why-flagged-chevron").classList.toggle("open");
  });
}

function initSarSlider() {
  const slider = document.getElementById("sar-slider");
  const afterWrap = document.getElementById("sar-img-after-wrap");
  const afterImg = document.getElementById("sar-img-after");
  const handle = document.getElementById("sar-slider-handle");
  const container = document.getElementById("sar-slider-container");
  const beforeImg = document.getElementById("sar-img-before");

  let mode = "swipe";

  function applySwipe(pct) {
    afterWrap.style.width = pct + "%";
    afterImg.style.width = (10000 / pct) + "%"; // keep underlying image full-size, only wrapper clips
    handle.style.left = pct + "%";
  }

  slider.addEventListener("input", () => {
    const pct = Number(slider.value);
    if (mode === "swipe") applySwipe(pct);
    else afterWrap.style.opacity = pct / 100;
  });
  applySwipe(50);

  document.getElementById("sar-mode-swipe").addEventListener("click", () => {
    mode = "swipe";
    document.getElementById("sar-mode-swipe").classList.add("active");
    document.getElementById("sar-mode-opacity").classList.remove("active");
    afterWrap.style.width = "";
    afterWrap.style.opacity = "1";
    handle.style.display = "block";
    afterWrap.style.width = "100%";
    afterImg.style.width = "100%";
    container.classList.remove("opacity-mode");
    applySwipe(Number(slider.value));
  });
  document.getElementById("sar-mode-opacity").addEventListener("click", () => {
    mode = "opacity";
    document.getElementById("sar-mode-opacity").classList.add("active");
    document.getElementById("sar-mode-swipe").classList.remove("active");
    afterWrap.style.width = "100%";
    afterImg.style.width = "100%";
    handle.style.display = "none";
    afterWrap.style.opacity = Number(slider.value) / 100;
  });
}

// ---------------------------------------------------------------------------
// Terrain-based scenario (Feature 5) — RELATIVE elevation only, no datum conversion
// ---------------------------------------------------------------------------
async function initTerrainScenario() {
  const grid = await loadJSON("data/terrain_scenario_grid.json");
  document.getElementById("terrain-disclaimer").textContent = grid.disclaimer;

  const canvas = document.getElementById("terrain-canvas");
  const ctx = canvas.getContext("2d");
  const rows = grid.shape[0], cols = grid.shape[1];
  const cellW = canvas.width / cols, cellH = canvas.height / rows;
  const maxRel = grid.max_relative_m;

  const slider = document.getElementById("terrain-slider");
  slider.max = String(Math.ceil(maxRel));
  const readout = document.getElementById("terrain-readout");

  function render(thresholdM) {
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const relElev = grid.relative_elevation_m[r][c];
        let color;
        if (relElev <= thresholdM) {
          color = "#0f6b78"; // "inundated" relative to this illustrative threshold
        } else {
          const t = Math.min(1, relElev / maxRel);
          const g = Math.round(200 - t * 90);
          color = `rgb(${170 - t * 60},${g},${140 - t * 60})`;
        }
        ctx.fillStyle = color;
        ctx.fillRect(c * cellW, r * cellH, cellW + 1, cellH + 1);
      }
    }
  }

  slider.addEventListener("input", () => {
    const v = Number(slider.value);
    readout.textContent = `${v.toFixed(1)} m above AOI minimum`;
    render(v);
  });
  render(Number(slider.value));
  readout.textContent = `${Number(slider.value).toFixed(1)} m above AOI minimum`;
}

// ---------------------------------------------------------------------------
// Exposure analysis placeholder (Feature 7)
// ---------------------------------------------------------------------------
async function initExposure() {
  const data = await loadJSON("data/exposure_layers.json");
  const el = document.getElementById("exposure-content");
  if (data.available_layers.length === 0) {
    el.innerHTML = `
      <div class="exposure-placeholder">
        <div style="font-size:15px; font-weight:600; color:var(--navy);">${tag("PENDING")} Next integration layer — no verified exposure/infrastructure data yet</div>
        <p style="max-width:480px;margin:10px auto 0;">${data.message}</p>
        <div class="exposure-planned">
          <strong>This interface is ready to accept, once verified data exists:</strong>
          <ul>${data.planned_layers_if_data_becomes_available.map((l) => `<li>${l}</li>`).join("")}</ul>
        </div>
      </div>`;
  }
}

// ---------------------------------------------------------------------------
// Data confidence panel (Feature 6)
// ---------------------------------------------------------------------------
async function initConfidence() {
  const data = await loadJSON("data/confidence_panel.json");
  const el = document.getElementById("confidence-grid");
  const grid = document.createElement("div");
  grid.className = "confidence-grid-inner";
  data.forEach((item) => {
    const div = document.createElement("div");
    div.className = "confidence-item";
    const pillClass = item.status === "VERIFIED" ? "verified" : "pending";
    div.innerHTML = `
      <div class="confidence-item-title"><span>${item.item}</span><span class="status-pill ${pillClass}">${item.status}</span></div>
      <div class="confidence-item-detail">${item.detail}</div>`;
    grid.appendChild(div);
  });
  el.appendChild(grid);
}

async function initDataSources() {
  const data = await loadJSON("data/data_sources.json");
  const el = document.getElementById("data-sources");
  data.forEach((s) => {
    const item = document.createElement("div");
    item.className = "source-item";
    item.innerHTML = `<div class="source-title"><span>${s.category}</span>${tag(s.status)}</div>
      <div class="source-detail">${s.detail}</div><div class="source-ref">Source: ${s.source}</div>`;
    el.appendChild(item);
  });
  document.getElementById("sources-toggle").addEventListener("click", () => {
    el.classList.toggle("hidden");
    document.getElementById("sources-chevron").classList.toggle("open");
  });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
(async function boot() {
  try {
    const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
    const m = await loadJSON("data/sar_flood/validation_metrics.json");
    window.__candidateAreaKm2 = params.final_candidate_area_km2;
    window.__f1Score = m.f1;
    window.__iouScore = m.iou;

    await initLayers();
    await initStationSelector();
    await initTimeline();
    await initNdemArea();
    await initAnalysisResultSummary();
    await initS1Cards();
    initSarSlider();
    initSarStageViewer();
    await initSarMaskSummary();
    await initWhyFlagged();
    await initSarValidationSummary();
    await initTerrainScenario();
    await initExposure();
    await initConfidence();
    await initDataSources();
    initGuidedFlow();
  } catch (err) {
    console.error(err);
    document.body.insertAdjacentHTML("beforeend",
      `<div style="position:fixed;bottom:10px;left:10px;background:#a4271f;color:white;padding:8px 12px;border-radius:4px;font-size:12px;z-index:9999;">
        Failed to load a data file: ${err.message}. Check the browser console.
      </div>`);
  }
})();
