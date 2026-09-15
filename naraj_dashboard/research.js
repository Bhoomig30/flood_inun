// ============================================================================
// FLOODWATCH — RESEARCH / TECHNICAL VIEW (application logic)
//
// India-wide platform; Mahanadi (Naraj/Cuttack) remains the documented
// demonstration / model-calibration study case. Everything shown here is read
// from the project's verified local datasets — no fabricated values.
// ============================================================================

const STATUS_TAG_CLASS = {
  OBSERVED: "tag-observed",
  HISTORICAL: "tag-historical",
  DERIVED: "tag-derived",
  PENDING: "tag-pending",
  REFERENCE: "tag-reference",
  "NO SAR COVERAGE": "tag-nocoverage",
  VERIFIED: "tag-observed",
};

const STUDY_REGION_NOTE =
  "The India-wide platform architecture serves any selected location. The " +
  "temporal Random Forest forecast is calibrated on the Naraj/Cuttack " +
  "(Mahanadi basin) historical study data — it is not an India-wide " +
  "calibrated model.";

function tag(status) {
  const cls = STATUS_TAG_CLASS[status] || "tag-derived";
  return `<span class="tag ${cls}">${status}</span>`;
}

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    const pane = document.getElementById("tab-" + btn.dataset.tab);
    if (pane) pane.classList.add("active");
    if (typeof researchMap !== "undefined" && researchMap) {
      setTimeout(() => researchMap.invalidateSize(), 60);
    }
  });
});

// Situation cards jump to the linked tab.
document.querySelectorAll(".sit-card[data-goto]").forEach((card) => {
  card.addEventListener("click", () => {
    const btn = document.querySelector(`.tab-btn[data-tab="${card.dataset.goto}"]`);
    if (btn) btn.click();
  });
});

// ---------------------------------------------------------------------------
// Global state
// ---------------------------------------------------------------------------

let researchMap = null;
let researchLayers = {};
let layerRegistry = [];
let eventsData = null;
let allYearsData = null;
let currentEventId = "ndem_18aug";
let wlChart = null;
let sarStage = "preflood";
let sarPol = "vv";
let terrainGrid = null;

// ---------------------------------------------------------------------------
// Leaflet map + layers
// ---------------------------------------------------------------------------

function initMap() {
  researchMap = L.map("map", { zoomControl: true }).setView([20.47, 85.77], 10);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(researchMap);
}

function makeBounds(b) {
  return [
    [b.south, b.west],
    [b.north, b.east],
  ];
}

const IMAGE_BOUNDS = {
  dem: null, // read from data/dem bounds json
  sar_preflood_vv: null,
  sar_duringflood_vv: null,
  sar_change: null,
  sar_ndem_agreement: null,
};

async function loadBounds() {
  try {
    const dem = await loadJSON("data/dem/naraj_aoi_dem_bounds.json");
    IMAGE_BOUNDS.dem = makeBounds(dem.bounds);
  } catch (e) { /* optional */ }
  // All SAR overlays share the AOI bounds (verified in candidate_mask_params).
  const sar = [
    [20.29999999528341, 85.54673544669521],
    [20.65000003015056, 85.9523590970937],
  ];
  IMAGE_BOUNDS.sar_preflood_vv = sar;
  IMAGE_BOUNDS.sar_duringflood_vv = sar;
  IMAGE_BOUNDS.sar_change = sar;
  IMAGE_BOUNDS.sar_ndem_agreement = sar;
}

function styleFor(layerDef) {
  const presets = {
    "Historical Inundation (NDEM)": {
      color: "#c2760c", weight: 1, fillColor: "#c2760c", fillOpacity: 0.4,
    },
    "SAR Flood Detection": {
      color: "#a4271f", weight: 1, fillColor: "#a4271f", fillOpacity: 0.55,
    },
    Sentinel: { color: "#7a1fa2", weight: 1.5, fillOpacity: 0.05 },
    Reference: { color: "#0b3350", weight: 2, fillOpacity: 0 },
    Validation: { color: "#0f6b78", weight: 1, fillColor: "#0f6b78", fillOpacity: 0.3 },
  };
  if (layerDef.style) return layerDef.style;
  if (layerDef.group && presets[layerDef.group]) return presets[layerDef.group];
  if (layerDef.id && layerDef.id.startsWith("s1_")) return presets.Sentinel;
  return presets.Reference;
}

async function buildLayer(id) {
  const def = layerRegistry.find((l) => l.id === id);
  if (!def) return null;
  if (def.type === "geojson") {
    const gj = await loadJSON(def.file);
    return L.geoJSON(gj, { style: styleFor(def) });
  }
  if (def.type === "image_overlay") {
    return L.imageOverlay(def.file, IMAGE_BOUNDS[def.id] || IMAGE_BOUNDS.sar_change, {
      opacity: 0.65,
    });
  }
  if (def.type === "stations") {
    const gj = await loadJSON(def.file);
    const group = L.layerGroup();
    gj.features.forEach((f) => {
      const p = f.properties;
      const [lon, lat] = f.geometry.coordinates;
      L.circleMarker([lat, lon], {
        radius: p.is_focus_station ? 6 : 3.5,
        color: p.is_focus_station ? "#a4271f" : "#8a97a0",
        fillOpacity: 0.9,
      })
        .bindPopup(
          `<strong>${esc(p.name)}</strong><br>${esc(p.local_river || p.river || "")}` +
          `<br>${p.is_focus_station ? "Focus station (verified hourly series)" : "CWC monitoring station"}`
        )
        .addTo(group);
    });
    return group;
  }
  if (def.type === "point") {
    const gj = await loadJSON(def.file);
    return L.geoJSON(gj, {
      pointToLayer: (f, latlng) =>
        L.circleMarker(latlng, { radius: 7, color: "#a4271f", fillOpacity: 0.9 }).bindPopup(
          "Naraj gauge — forecast model calibration station"
        ),
    });
  }
  return null;
}

async function initLayers() {
  layerRegistry = await loadJSON("data/layers.json");
  const container = document.getElementById("layer-groups");
  if (!container) return;

  const groups = [...new Set(layerRegistry.map((l) => l.group || "Other"))];
  for (const groupName of groups) {
    const title = document.createElement("div");
    title.className = "layer-group-title";
    title.textContent = groupName;
    container.appendChild(title);

    for (const def of layerRegistry.filter((l) => (l.group || "Other") === groupName)) {
      const row = document.createElement("div");
      row.className = "layer-row";
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.id = "layer-" + def.id;
      cb.checked = !!def.default_on;
      const label = document.createElement("label");
      label.htmlFor = cb.id;
      label.innerHTML = `${esc(def.label)} ${tag(def.status || "DERIVED")}`;
      row.appendChild(cb);
      row.appendChild(label);
      container.appendChild(row);

      researchLayers[def.id] = null;
      cb.addEventListener("change", async () => {
        try {
          if (cb.checked) {
            if (!researchLayers[def.id]) {
              researchLayers[def.id] = await buildLayer(def.id);
            }
            if (researchLayers[def.id]) researchLayers[def.id].addTo(researchMap);
          } else if (researchLayers[def.id]) {
            researchMap.removeLayer(researchLayers[def.id]);
          }
        } catch (err) {
          console.error("Layer toggle failed:", def.id, err);
          cb.checked = false;
        }
      });
      if (cb.checked) {
        // Load defaults synchronously-ish, but don't block the rest of boot.
        buildLayer(def.id)
          .then((layer) => {
            researchLayers[def.id] = layer;
            if (layer && cb.checked) layer.addTo(researchMap);
          })
          .catch((err) => console.error("Default layer failed:", def.id, err));
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Situation cards
// ---------------------------------------------------------------------------

function setSit(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

async function updateSituationCards() {
  try {
    const results = await loadJSON("data/ai_flood_results_1017769.json");
    setSit("sit-candidate", results.flood_percentage.toFixed(1) + "%");
    setSit(
      "sit-validation",
      "IoU " + (results.validation.iou * 100).toFixed(1) + "%"
    );
  } catch (e) { /* cards stay "—" */ }

  try {
    const areas = await loadJSON("data/ndem_inundated_area.json");
    const ev = areas.events["18-Aug-2022"];
    if (ev) setSit("sit-ref", ev.inundated_area_km2_within_aoi.toFixed(1) + " km²");
  } catch (e) { /* optional */ }

  const evt = currentEvent();
  if (evt && evt.cwc_observed && typeof evt.cwc_observed.water_level_m === "number") {
    setSit("sit-cwc", evt.cwc_observed.water_level_m.toFixed(2) + " m");
  }
  const sat = evt && evt.satellite_evidence ? evt.satellite_evidence.status : "";
  setSit("sit-sar", sat || "—");
  setSit("sit-event", evt ? evt.date : "—");
}

function currentEvent() {
  if (!eventsData) return null;
  return (
    eventsData.events.find((e) => e.id === currentEventId) ||
    eventsData.events[0] ||
    null
  );
}

// ---------------------------------------------------------------------------
// Evolution stepper + event detail
// ---------------------------------------------------------------------------

function renderEvolution() {
  const el = document.getElementById("evolution-stepper");
  if (!el || !eventsData) return;
  el.innerHTML = "";

  const events = eventsData.events
    .filter((e) => e.ndem_inundation && e.ndem_inundation.available)
    .sort((a, b) => (a.date < b.date ? -1 : 1));

  events.forEach((evt, i) => {
    const step = document.createElement("div");
    step.className = "evo-step" + (evt.id === currentEventId ? " active" : "");
    step.setAttribute("role", "button");
    step.setAttribute("tabindex", "0");

    const dot = document.createElement("div");
    dot.className = "evo-dot";
    step.appendChild(dot);

    const date = document.createElement("div");
    date.className = "evo-date";
    date.textContent = new Date(evt.date + "T00:00:00").toLocaleDateString("en-GB", {
      day: "numeric", month: "short",
    });
    step.appendChild(date);

    const wl = document.createElement("div");
    wl.className = "evo-wl";
    wl.textContent =
      evt.cwc_observed && typeof evt.cwc_observed.water_level_m === "number"
        ? evt.cwc_observed.water_level_m.toFixed(2) + " m"
        : "—";
    step.appendChild(wl);

    const badges = document.createElement("div");
    badges.className = "evo-badges";
    badges.innerHTML =
      tag(evt.ndem_inundation.status || "HISTORICAL") +
      tag(evt.satellite_evidence ? evt.satellite_evidence.status : "NO SAR COVERAGE");
    step.appendChild(badges);

    const activate = () => selectEvent(evt.id);
    step.addEventListener("click", activate);
    step.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") activate();
    });
    el.appendChild(step);

    if (i < events.length - 1) {
      const conn = document.createElement("div");
      conn.className = "evo-connector";
      el.appendChild(conn);
    }
  });
}

function selectEvent(eventId) {
  currentEventId = eventId;
  renderEvolution();
  renderEventDetail();

  // Swap the NDEM layer shown on the map.
  const cb = document.getElementById("layer-" + eventId);
  if (cb) {
    cb.checked = true;
    cb.dispatchEvent(new Event("change"));
  }
  updateSituationCards();
}

function renderEventDetail() {
  const el = document.getElementById("event-detail");
  if (!el) return;
  const evt = currentEvent();
  if (!evt) {
    el.innerHTML = '<p class="muted">Select a date on the timeline.</p>';
    return;
  }

  const rows = [];
  if (evt.cwc_observed) {
    rows.push(
      `<div class="detail-row"><span class="detail-label">CWC level ${tag("OBSERVED")}</span>
       <span class="detail-value">${
         typeof evt.cwc_observed.water_level_m === "number"
           ? evt.cwc_observed.water_level_m.toFixed(2) + " m"
           : "—"
       }</span></div>`
    );
  }
  if (evt.ndem_inundation) {
    rows.push(
      `<div class="detail-row"><span class="detail-label">NDEM extent ${tag(evt.ndem_inundation.status)}</span>
       <span class="detail-value text">${esc(evt.ndem_inundation.available ? "Mapped" : "Not mapped")}</span></div>`
    );
  }
  if (evt.satellite_evidence) {
    rows.push(
      `<div class="detail-row"><span class="detail-label">Sentinel-1 ${tag(evt.satellite_evidence.status)}</span>
       <span class="detail-value text">${esc(evt.satellite_evidence.detail || "")}</span></div>`
    );
  }
  if (evt.peak_context) {
    rows.push(
      `<div class="detail-row"><span class="detail-label">Peak context</span>
       <span class="detail-value text">${esc(evt.peak_context)}</span></div>`
    );
  }

  el.innerHTML = `<div><strong>${esc(evt.date)}</strong> — Mahanadi at Naraj</div>${rows.join("")}`;
}

// ---------------------------------------------------------------------------
// Station picker + water level chart
// ---------------------------------------------------------------------------

const STATION_DEFS = [
  { key: "naraj", label: "Naraj · Mahanadi (Cuttack)", file: "data/cwc/naraj_daily_2021_2025.json" },
  { key: "alipingal", label: "Alipingal · Dhaniya", file: "data/cwc/alipingal_daily_2021_2025.json" },
  { key: "nimapara", label: "Nimapara · Dandia", file: "data/cwc/nimapara_daily_2021_2025.json" },
];

async function initStationPicker() {
  const el = document.getElementById("station-select");
  if (!el) return;

  const row = document.createElement("div");
  row.className = "station-chip-row";
  STATION_DEFS.forEach((st) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "station-chip" + (st.key === "naraj" ? " active" : "");
    chip.textContent = st.label.split(" · ")[0];
    chip.setAttribute("aria-label", st.label);
    chip.addEventListener("click", () => {
      row.querySelectorAll(".station-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      drawWlChart(st);
    });
    row.appendChild(chip);
  });
  el.appendChild(row);

  await drawWlChart(STATION_DEFS[0]);
}

async function drawWlChart(station) {
  try {
    const data = await loadJSON(station.file);
    const records = (data.records || []).filter(
      (r) => r && typeof r.water_level_m === "number"
    );
    if (!records.length) return;

    const labels = records.map((r) => r.date);
    const levels = records.map((r) => r.water_level_m);

    if (wlChart) wlChart.destroy();
    wlChart = new Chart(document.getElementById("wl-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: station.label,
            data: levels,
            borderColor: "#0f6b78",
            backgroundColor: "rgba(15,107,120,0.08)",
            pointRadius: 0,
            borderWidth: 1.5,
            tension: 0.2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { ticks: { maxTicksLimit: 8, font: { size: 9 } }, grid: { display: false } },
          y: { ticks: { font: { size: 9 } } },
        },
      },
    });

    const caption = document.getElementById("wl-chart-caption");
    if (caption) {
      caption.innerHTML = `Daily water level, ${esc(station.label)} — verified CWC manual hourly gauge readings aggregated to daily, 2021–2025 (${tag("OBSERVED")}). Naraj is the temporal-forecast calibration station; the other two are study-region context.`;
    }
  } catch (err) {
    console.error("Water level chart failed:", err);
    const caption = document.getElementById("wl-chart-caption");
    if (caption) caption.textContent = "Water-level series unavailable.";
  }
}

// ---------------------------------------------------------------------------
// SAR stage viewer + swipe comparison
// ---------------------------------------------------------------------------

const SAR_STAGE_CAPTIONS = {
  preflood: {
    vv: "Stage 1 — Pre-flood Sentinel-1 VV backscatter (6 Aug 2022, calibrated σ°). Dark regions are typically smooth water/surface; this is intensity, not a flood classification.",
    vh: "Stage 1 — Pre-flood Sentinel-1 VH backscatter (6 Aug 2022, calibrated σ°). Cross-pol is more sensitive to volume scattering.",
  },
  duringflood: {
    vv: "Stage 2 — During-flood Sentinel-1 VV backscatter (18 Aug 2022, calibrated σ°). Areas newly dark vs. Stage 1 are the flooding signal.",
    vh: "Stage 2 — During-flood Sentinel-1 VH backscatter (18 Aug 2022, calibrated σ°).",
  },
  change: {
    vv: "Stage 3 — Combined VV+VH change (pre → during). Blue/violet tones mark strong backscatter drop — the physical flooding signature.",
    vh: "Stage 3 — Combined VV+VH change.",
  },
  candidate: {
    vv: "Stage 4 — Candidate inundation mask: change < −3 dB on both polarizations, ≥5-pixel components. DERIVED — independently generated, then validated against NDEM (see Validation tab).",
    vh: "Stage 4 — Candidate inundation mask.",
  },
};

function sarStageFile(stage, pol) {
  if (stage === "preflood") return "data/sar_flood/preflood_" + pol + ".png";
  if (stage === "duringflood") return "data/sar_flood/duringflood_" + pol + ".png";
  if (stage === "change") return "data/sar_flood/change_combined.png";
  return "data/sar_flood/candidate_overlay_composite.png";
}

function renderSarStage() {
  const img = document.getElementById("sar-stage-img");
  const caption = document.getElementById("sar-stage-caption");
  if (img) img.src = sarStageFile(sarStage, sarPol);
  if (caption) {
    caption.textContent =
      SAR_STAGE_CAPTIONS[sarStage][sarPol] || SAR_STAGE_CAPTIONS[sarStage].vv;
  }
  document.querySelectorAll("#sar-stage-tabs .stage-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.stage === sarStage);
  });
  document.querySelectorAll("#sar-pol-toggle .pol-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.pol === sarPol);
  });
}

function initSarStageTabs() {
  const tabs = document.getElementById("sar-stage-tabs");
  if (tabs) {
    tabs.addEventListener("click", (e) => {
      const btn = e.target.closest(".stage-btn");
      if (!btn) return;
      sarStage = btn.dataset.stage;
      renderSarStage();
    });
  }
  const pol = document.getElementById("sar-pol-toggle");
  if (pol) {
    pol.addEventListener("click", (e) => {
      const btn = e.target.closest(".pol-btn");
      if (!btn) return;
      sarPol = btn.dataset.pol;
      renderSarStage();
    });
  }
  renderSarStage();
}

function initSarSwipe() {
  const slider = document.getElementById("sar-slider");
  const afterWrap = document.getElementById("sar-img-after-wrap");
  const handle = document.getElementById("sar-slider-handle");
  if (!slider || !afterWrap || !handle) return;

  const apply = () => {
    const v = Number(slider.value);
    afterWrap.style.clipPath = `inset(0 0 0 ${v}%)`;
    handle.style.left = v + "%";
  };
  slider.addEventListener("input", apply);
  apply();

  const swipeBtn = document.getElementById("sar-mode-swipe");
  const opacityBtn = document.getElementById("sar-mode-opacity");
  if (swipeBtn && opacityBtn) {
    const setMode = (mode) => {
      swipeBtn.classList.toggle("active", mode === "swipe");
      opacityBtn.classList.toggle("active", mode === "opacity");
      if (mode === "opacity") {
        afterWrap.style.clipPath = "none";
        handle.style.display = "none";
        afterWrap.style.opacity = "0.5";
      } else {
        handle.style.display = "";
        afterWrap.style.opacity = "1";
        apply();
      }
    };
    swipeBtn.addEventListener("click", () => setMode("swipe"));
    opacityBtn.addEventListener("click", () => setMode("opacity"));
  }
}

// ---------------------------------------------------------------------------
// Analysis result / validation / SAR mask / confidence panels
// ---------------------------------------------------------------------------

function fmtPct(x) {
  return (x * 100).toFixed(2) + "%";
}

async function renderAnalysisPanels() {
  // Flood analysis result (AI scene)
  try {
    const r = await loadJSON("data/ai_flood_results_1017769.json");
    const el = document.getElementById("analysis-result-summary");
    if (el) {
      el.innerHTML = `
        <div class="detail-row"><span class="detail-label">Scene</span><span class="detail-value">${esc(r.scene_id)}</span></div>
        <div class="detail-row"><span class="detail-label">Classifier</span><span class="detail-value text">${esc(r.model)}, ${esc(String(r.features))} features</span></div>
        <div class="detail-row"><span class="detail-label">Flood fraction</span><span class="detail-value">${esc(r.flood_percentage.toFixed(2))}%</span></div>
        <div class="detail-row"><span class="detail-label">Polygons</span><span class="detail-value">${esc(String(r.polygons))}</span></div>
        <p class="chart-caption">Scene-level RF flood classification of Sentinel-1 imagery. This scene is in Assam (Brahmaputra floods, 2020) — it demonstrates the inundation-mapping pipeline's portability beyond Odisha; the temporal forecast model is the Naraj-calibrated part.</p>`;
    }
  } catch (e) {
    console.error("AI results panel failed:", e);
  }

  // SAR mask summary
  try {
    const p = await loadJSON("data/sar_flood/candidate_mask_params.json");
    const el = document.getElementById("sar-mask-summary");
    if (el) {
      el.innerHTML = `
        <div class="detail-row"><span class="detail-label">Rule</span><span class="detail-value text">${esc(p.condition)}</span></div>
        <div class="detail-row"><span class="detail-label">Threshold</span><span class="detail-value">−${esc(p.threshold_db_drop)} dB</span></div>
        <div class="detail-row"><span class="detail-label">Min component</span><span class="detail-value">${esc(String(p.min_connected_component_pixels))} px (8-conn.)</span></div>
        <div class="detail-row"><span class="detail-label">Candidate area</span><span class="detail-value">${esc(p.final_candidate_area_km2.toFixed(2))} km² (${esc(p.final_candidate_pct_of_valid_aoi.toFixed(2))}% of valid AOI)</span></div>`;
    }
  } catch (e) {
    console.error("SAR mask panel failed:", e);
  }

  // Why flagged
  const why = document.getElementById("why-flagged-content");
  if (why) {
    why.innerHTML = `
      <p class="muted">A pixel is flagged as candidate inundation when <strong>both</strong>
      VV and VH backscatter drop by more than 3 dB between the 6-Aug and 18-Aug
      calibrated scenes, the drop is spatially connected (≥5 pixels), and the
      pixel is inside the valid Sentinel-1 coverage. Flooding converts rough,
      vegetated land into smooth specular water surfaces, which strongly reduce
      radar backscatter — that physical signature is the entire detection rule.</p>
      <p class="muted">False positives are expected where soil is inundated-but-vegetated,
      where radar shadows occur, or where the pre-flood scene was already water.
      The Validation tab quantifies exactly these errors against the NDEM
      reference instead of hiding them.</p>`;
  }
  const whyToggle = document.getElementById("why-flagged-toggle");
  if (whyToggle) {
    whyToggle.addEventListener("click", () => {
      const body = document.getElementById("why-flagged-content");
      const chev = document.getElementById("why-flagged-chevron");
      const hidden = body.classList.toggle("hidden");
      chev.textContent = hidden ? "▸" : "▾";
    });
  }

  // Validation metrics
  try {
    const r = await loadJSON("data/ai_flood_results_1017769.json");
    const v = r.validation;
    const el = document.getElementById("sar-validation-summary");
    if (el) {
      el.innerHTML = `
        <div class="detail-row"><span class="detail-label">Precision</span><span class="detail-value">${fmtPct(v.precision)}</span></div>
        <div class="detail-row"><span class="detail-label">Recall</span><span class="detail-value">${fmtPct(v.recall)}</span></div>
        <div class="detail-row"><span class="detail-label">F1</span><span class="detail-value">${fmtPct(v.f1)}</span></div>
        <div class="detail-row"><span class="detail-label">IoU</span><span class="detail-value">${fmtPct(v.iou)}</span></div>
        <div class="detail-row"><span class="detail-label">False-positive rate</span><span class="detail-value">${fmtPct(v.false_positive_rate)}</span></div>
        <div class="detail-row"><span class="detail-label">False-negative rate</span><span class="detail-value">${fmtPct(v.false_negative_rate)}</span></div>
        <p class="chart-caption">Scene-level evaluation of the RF classifier (12 features) on held-out labels. The SAR-vs-NDEM spatial agreement above evaluates the rule-based candidate mask — a different, honest, prototype-stage measurement.</p>`;
    }
  } catch (e) {
    console.error("Validation panel failed:", e);
  }

  // NDEM area panel
  try {
    const areas = await loadJSON("data/ndem_inundated_area.json");
    const el = document.getElementById("ndem-area-panel");
    if (el) {
      let html = "";
      for (const [date, ev] of Object.entries(areas.events)) {
        html += `<div class="ndem-area-row"><span>${esc(date)}</span><span class="v">${esc(
          ev.inundated_area_km2_within_aoi.toFixed(2)
        )} km²</span></div>`;
      }
      html += `<p class="chart-caption">${esc(areas.aoi ? "Within AOI " + areas.aoi + ". " : "")}Derived from verified NDEM geometries (UTM 45N) — not a forecast.</p>`;
      el.innerHTML = html;
    }
  } catch (e) {
    console.error("NDEM area panel failed:", e);
  }

  // Confidence grid
  try {
    const items = await loadJSON("data/confidence_panel.json");
    const el = document.getElementById("confidence-grid");
    if (el) {
      el.innerHTML = items
        .map(
          (i) => `
          <div class="detail-row"><span class="detail-label">${esc(i.item)}</span>
          <span class="detail-value text">${tag(i.status)} ${esc(i.detail)}</span></div>`
        )
        .join("");
    }
  } catch (e) {
    console.error("Confidence grid failed:", e);
  }

  // Data sources (collapsible provenance)
  try {
    const sources = await loadJSON("data/data_sources.json");
    const el = document.getElementById("data-sources");
    if (el) {
      el.innerHTML = sources
        .map(
          (s) => `
          <div class="detail-row"><span class="detail-label">${esc(s.category)} ${tag(s.status)}</span>
          <span class="detail-value text">${esc(s.detail)}<br><small>Source: ${esc(s.source)} · verified in ${esc(s.verified_in)}</small></span></div>`
        )
        .join("");
    }
    const toggle = document.getElementById("sources-toggle");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const body = document.getElementById("data-sources");
        const chev = document.getElementById("sources-chevron");
        const hidden = body.classList.toggle("hidden");
        chev.textContent = hidden ? "▸" : "▾";
      });
    }
  } catch (e) {
    console.error("Data sources panel failed:", e);
  }

  // Exposure panel
  try {
    const exp = await loadJSON("data/exposure_layers.json");
    const el = document.getElementById("exposure-content");
    if (el) {
      const planned = (exp.planned_layers_if_data_becomes_available || [])
        .map((p) => `<li>${esc(p)}</li>`)
        .join("");
      el.innerHTML = `<p class="muted">${esc(exp.message)}</p>${
        planned ? `<ul class="muted small">${planned}</ul>` : ""
      }`;
    }
  } catch (e) {
    console.error("Exposure panel failed:", e);
  }

  // Terrain disclaimer
  const dis = document.getElementById("terrain-disclaimer");
  if (dis) {
    dis.textContent =
      "Relative elevation scenario over the Naraj AOI (SRTM 1 arc-second). " +
      "It illustrates the DEM-threshold mechanism only — it is not a water-level " +
      "to flood-depth conversion and not a location-specific forecast.";
  }
}

// ---------------------------------------------------------------------------
// Terrain scenario canvas
// ---------------------------------------------------------------------------

async function initTerrain() {
  try {
    terrainGrid = await loadJSON("data/terrain_scenario_grid.json");
  } catch (e) {
    console.error("Terrain grid unavailable:", e);
    return;
  }
  const canvas = document.getElementById("terrain-canvas");
  const slider = document.getElementById("terrain-slider");
  const readout = document.getElementById("terrain-readout");
  if (!canvas || !slider || !terrainGrid) return;

  const [rows, cols] = terrainGrid.shape;
  const b = terrainGrid.bounds;

  function draw() {
    const ctx = canvas.getContext("2d");
    const cw = canvas.width / cols;
    const ch = canvas.height / rows;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const threshold = Number(slider.value);

    let min = Infinity;
    for (const r of terrainGrid.relative_elevation_m)
      for (const v of r) if (v < min) min = v;

    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        const v = terrainGrid.relative_elevation_m[y][x];
        const rel = v - min;
        if (rel < threshold) {
          ctx.fillStyle = "rgba(10,90,140,0.75)"; // below threshold → scenario water
        } else {
          const t = Math.min((v - 17) / (214 - 17), 1);
          const g = Math.round(40 + 180 * (1 - t));
          ctx.fillStyle = `rgb(${Math.round(60 + 90 * (1 - t))},${g},${Math.round(50 + 60 * (1 - t))})`;
        }
        ctx.fillRect(x * cw, canvas.height - (y + 1) * ch, cw + 0.6, ch + 0.6);
      }
    }

    readout.textContent = threshold.toFixed(1) + " m above AOI minimum";
  }

  slider.addEventListener("input", draw);
  draw();
}

// ---------------------------------------------------------------------------
// Model panel (temporal forecast scope — honest labeling)
// ---------------------------------------------------------------------------

async function renderModelScopePanel() {
  const el = document.getElementById("analysis-result-summary");
  // The temporal-model scope is added to the Data & Methodology tab via the
  // architecture panel area — appended as an honest note block.
  const host = document.getElementById("architecture-panel");
  if (!host) return;
  try {
    const info = await loadJSON("/api/model/info").catch(() => null);
    const note = document.createElement("div");
    note.className = "panel";
    note.style.marginTop = "10px";
    const trained =
      info && info.status === "trained"
        ? `Random Forest temporal forecast models (6h/12h/24h) are trained on the
           project's real 43,800-row CWC dataset (2021–2025, Hugging Face:
           bhoomig0630/flood-inundation-upload) with a strict chronological
           holdout.`
        : `The statistical temporal engine runs on the verified Naraj/Alipingal/
           Nimapara series; the Random Forest bundles are not present in this
           checkout (run ml_train.py with the real dataset to train them).`;
    note.innerHTML = `
      <div class="panel-header"><h2>Temporal Forecast Model — Scope ${tag("DERIVED")}</h2></div>
      <p class="muted">${trained}</p>
      <p class="muted"><strong>${esc(STUDY_REGION_NOTE)}</strong></p>
      <p class="muted small">Flood-extent mapping (SAR/RF scene classification) and
      temporal forecasting are different tasks: the first generalizes to any
      scene with imagery, the second needs calibrated gauge records — currently
      only the Mahanadi study region has them.</p>`;
    host.appendChild(note);
  } catch (e) {
    /* scope note is best-effort */
  }
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

async function bootResearch() {
  const failures = [];
  const step = async (name, fn) => {
    try {
      await fn();
    } catch (err) {
      failures.push(name + ": " + (err && err.message ? err.message : err));
      console.error("Research boot step failed:", name, err);
    }
  };

  await step("map", initMap);
  await step("bounds", loadBounds);
  await step("layers", initLayers);
  await step("events", async () => {
    try {
      allYearsData = await loadJSON("data/events_all_years.json");
    } catch (e) { /* optional */ }
    eventsData = await loadJSON("data/events_august2022.json");
    renderEvolution();
    renderEventDetail();
    updateSituationCards();
  });
  await step("stations", initStationPicker);
  await step("sar", initSarStageTabs);
  await step("swipe", initSarSwipe);
  await step("panels", renderAnalysisPanels);
  await step("terrain", initTerrain);
  await step("model-scope", renderModelScopePanel);

  if (failures.length) {
    console.warn("Research view loaded with degraded sections:", failures.join(" | "));
  } else {
    console.log("Research view loaded successfully.");
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootResearch);
} else {
  bootResearch();
}
