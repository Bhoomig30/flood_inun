// // AI-Driven Flood Inundation Analysis & Decision Support System — application logic
// // Demonstration case: Mahanadi Basin, Odisha (Naraj gauge currently selected).
// // Reads only local, verified data files. No flood classification, calibrated SAR
// // value, danger level, accuracy figure, or invented coordinate is computed here.

// const STATUS_TAG_CLASS = { OBSERVED: "tag-observed", HISTORICAL: "tag-historical", DERIVED: "tag-derived", PENDING: "tag-pending", REFERENCE: "tag-reference", "NO SAR COVERAGE": "tag-nocoverage" };
// function tag(status) { return `<span class="tag ${STATUS_TAG_CLASS[status] || "tag-derived"}">${status}</span>`; }
// async function loadJSON(path) {
//   const res = await fetch(path);
//   if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
//   return res.json();
// }

// // ---------------------------------------------------------------------------
// // Tab navigation
// // ---------------------------------------------------------------------------
// document.querySelectorAll(".tab-btn").forEach((btn) => {
//   btn.addEventListener("click", () => {
//     document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
//     document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
//     btn.classList.add("active");
//     document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
//     if (btn.dataset.tab === "overview") setTimeout(() => map.invalidateSize(), 50);
//   });
// });

// function goToTab(tabId) {
//   const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
//   if (btn) btn.click();
// }

// // Situation cards -> click to jump to the relevant tab
// document.querySelectorAll(".sit-card").forEach((card) => {
//   card.addEventListener("click", () => goToTab(card.dataset.goto));
// });

// // ---------------------------------------------------------------------------
// // Map setup
// // ---------------------------------------------------------------------------
// const map = L.map("map", { zoomControl: true }).setView([20.4717, 85.7656], 10);
// L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap contributors" }).addTo(map);
// const leafletLayers = {};
// let stationMarkers = {}; // name -> marker

// function markerIcon(color, size = 14) {
//   return L.divIcon({
//     className: "",
//     html: `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${color};border:2px solid white;box-shadow:0 0 0 1px rgba(0,0,0,0.3);"></div>`,
//     iconSize: [size, size], iconAnchor: [size / 2, size / 2],
//   });
// }

// async function buildStationsLayer(cfg) {
//   const gj = await loadJSON(cfg.file);
//   const group = L.layerGroup();
//   gj.features.forEach((f) => {
//     const p = f.properties;
//     const [lon, lat] = f.geometry.coordinates;
//     const isFocus = p.is_focus_station;
//     const color = isFocus ? "#a4271f" : (p.is_mainstem ? "#0f6b78" : "#8a97a0");
//     const marker = L.marker([lat, lon], { icon: markerIcon(color, isFocus ? 16 : 9) });
//     marker.bindPopup(
//       `<strong>${p.name}</strong> ${tag("OBSERVED")}<br>
//        ${p.local_river} ${p.is_mainstem ? "(mainstem)" : "(tributary)"} · ${p.district}, ${p.state}<br>
//        Range: ${p.min_wl_m}–${p.max_wl_m} m (mean ${p.mean_wl_m} m)<br>
//        ${p.n_obs.toLocaleString()} observations, ${p.date_range_start} → ${p.date_range_end}`
//     );
//     marker.on("click", () => { if (isFocus) selectStation(p.name); });
//     stationMarkers[p.name] = marker;
//     group.addLayer(marker);
//   });
//   return group;
// }

// async function buildLayer(cfg) {
//   if (cfg.type === "stations") return buildStationsLayer(cfg);
//   if (cfg.type === "geojson") {
//     if (!cfg.file) return null;
//     const gj = await loadJSON(cfg.file);
//     return L.geoJSON(gj, {
//       style: () => cfg.style || {},
//       onEachFeature: (feature, layer) => layer.bindPopup(`<strong>${cfg.label}</strong><br>${tag(cfg.status)}`),
//     });
//   }
//   if (cfg.type === "point") {
//     const gj = await loadJSON(cfg.file);
//     const feature = gj.features[0];
//     const [lon, lat] = feature.geometry.coordinates;
//     const marker = L.marker([lat, lon], { icon: markerIcon("#a4271f", 18) });
//     const p = feature.properties;
//     marker.bindPopup(`<strong>${p.name} Gauge (primary)</strong><br>${tag("OBSERVED")}<br>${lat.toFixed(6)}°N, ${lon.toFixed(6)}°E`);
//     return marker;
//   }
//   if (cfg.type === "image_overlay") {
//     const bounds = await loadJSON(cfg.bounds_file);
//     const b = bounds.bounds;
//     return L.imageOverlay(cfg.file, [[b.south, b.west], [b.north, b.east]], { opacity: 0.65 });
//   }
//   return null;
// }

// async function initLayers() {
//   const layers = await loadJSON("data/layers.json");
//   const groupsEl = document.getElementById("layer-groups");
//   const groups = {};
//   layers.forEach((cfg) => { groups[cfg.group] = groups[cfg.group] || []; groups[cfg.group].push(cfg); });

//   for (const [groupName, cfgs] of Object.entries(groups)) {
//     const title = document.createElement("div");
//     title.className = "layer-group-title";
//     title.textContent = groupName;
//     groupsEl.appendChild(title);

//     for (const cfg of cfgs) {
//       const isPending = cfg.status === "PENDING" || !cfg.file;
//       const row = document.createElement("div");
//       row.className = "layer-row" + (isPending ? " pending" : "");
//       const checkbox = document.createElement("input");
//       checkbox.type = "checkbox"; checkbox.id = `layer-${cfg.id}`;
//       checkbox.disabled = isPending;
//       checkbox.checked = !!cfg.default_on && !isPending;
//       const label = document.createElement("label");
//       label.htmlFor = checkbox.id;
//       label.innerHTML = `${cfg.label} ${tag(cfg.status)}`;
//       if (cfg.note) label.title = cfg.note;
//       row.appendChild(checkbox); row.appendChild(label);
//       groupsEl.appendChild(row);
//       if (isPending) continue;

//       const layer = await buildLayer(cfg);
//       if (!layer) continue;
//       leafletLayers[cfg.id] = layer;
//       if (checkbox.checked) layer.addTo(map);
//       checkbox.addEventListener("change", () => {
//         if (checkbox.checked) layer.addTo(map); else map.removeLayer(layer);
//       });
//     }
//   }
// }

// // ---------------------------------------------------------------------------
// // Multi-station view (Feature 1)
// // ---------------------------------------------------------------------------
// const FOCUS_STATIONS = ["Naraj", "Alipingal", "Nimapara"];
// const STATION_FILE_KEY = { Naraj: "naraj", Alipingal: "alipingal", Nimapara: "nimapara" };
// let currentStation = "Naraj";
// let wlChart = null;
// let stationSummaries = {};

// async function initStationSelector() {
//   const gj = await loadJSON("data/cwc_stations.geojson");
//   gj.features.forEach((f) => { stationSummaries[f.properties.name] = f.properties; });

//   const el = document.getElementById("station-select");
//   const chipRow = document.createElement("div");
//   chipRow.className = "station-chip-row";
//   FOCUS_STATIONS.forEach((name) => {
//     const chip = document.createElement("div");
//     chip.className = "station-chip" + (name === currentStation ? " active" : "");
//     chip.id = `chip-${name}`;
//     chip.textContent = name;
//     chip.addEventListener("click", () => selectStation(name));
//     chipRow.appendChild(chip);
//   });
//   el.appendChild(chipRow);

//   const info = document.createElement("div");
//   info.className = "station-info";
//   info.id = "station-info";
//   el.appendChild(info);

//   await selectStation(currentStation);
// }

// async function selectStation(name) {
//   currentStation = name;
//   document.querySelectorAll(".station-chip").forEach((c) => c.classList.remove("active"));
//   const chip = document.getElementById(`chip-${name}`);
//   if (chip) chip.classList.add("active");

//   const s = stationSummaries[name];
//   const infoEl = document.getElementById("station-info");
//   if (infoEl && s) {
//     infoEl.innerHTML = `${s.local_river} ${s.is_mainstem ? "(mainstem)" : "(tributary)"} · ${s.district}, ${s.state}<br>
//       Range ${s.min_wl_m}–${s.max_wl_m} m · ${s.n_obs.toLocaleString()} obs. ${tag("OBSERVED")}`;
//   }

//   if (leafletLayers.cwc_stations) {
//     const marker = stationMarkers[name];
//     if (marker) map.panTo(marker.getLatLng());
//   }

//   const fileKey = STATION_FILE_KEY[name];
//   const data = await loadJSON(`data/cwc/${fileKey}_daily_2021_2025.json`);
//   const labels = data.records.map((r) => r.date);
//   const values = data.records.map((r) => r.water_level_m);
//   if (wlChart) wlChart.destroy();
//   wlChart = new Chart(document.getElementById("wl-chart"), {
//     type: "line",
//     data: { labels, datasets: [{ label: `${name} daily mean (m)`, data: values, borderColor: "#0f6b78", backgroundColor: "rgba(15,107,120,0.08)", borderWidth: 1.2, pointRadius: 0, fill: true, tension: 0 }] },
//     options: { responsive: true, plugins: { legend: { display: false } },
//       scales: { x: { ticks: { maxTicksLimit: 6, font: { size: 9 } }, grid: { display: false } }, y: { title: { display: true, text: "meters", font: { size: 10 } }, ticks: { font: { size: 9 } } } } },
//   });
//   document.getElementById("wl-chart-caption").innerHTML = `Daily mean, manual hourly gauge readings, 2021–2025 (${tag("OBSERVED")})`;

//   if (currentEvent) updateSituation(currentEvent, name);
// }

// // ---------------------------------------------------------------------------
// // Historical event explorer / Flood Evolution timeline (Feature 1)
// // ---------------------------------------------------------------------------
// let eventsData = null;
// let currentEvent = null;

// async function initTimeline() {
//   eventsData = await loadJSON("data/events_august2022.json");
//   const el = document.getElementById("evolution-stepper");
//   eventsData.events.forEach((evt, idx) => {
//     const item = document.createElement("div");
//     item.className = "evo-step";
//     item.id = `evo-${evt.id}`;
//     const hasMask = evt.flood_mask_sar_derived.status === "DERIVED";
//     item.innerHTML = `
//       <div class="evo-dot"></div>
//       <div class="evo-date">${evt.date.slice(5)}</div>
//       <div class="evo-wl">${evt.cwc_observed.water_level_m} m</div>
//       <div class="evo-badges">
//         ${tag(evt.ndem_inundation.status)}
//         ${hasMask ? tag("DERIVED") : ""}
//       </div>
//     `;
//     item.addEventListener("click", () => selectEvent(evt.id));
//     el.appendChild(item);
//     if (idx < eventsData.events.length - 1) {
//       const connector = document.createElement("div");
//       connector.className = "evo-connector";
//       el.appendChild(connector);
//     }
//   });
//   selectEvent("ndem_18aug");
// }

// function selectEvent(eventId) {
//   currentEvent = eventId;
//   document.querySelectorAll(".evo-step").forEach((el) => el.classList.remove("active"));
//   const activeEl = document.getElementById(`evo-${eventId}`);
//   if (activeEl) activeEl.classList.add("active");

//   const evt = eventsData.events.find((e) => e.id === eventId);
//   if (!evt) return;

//   const el = document.getElementById("event-detail");
//   el.innerHTML = `
//     <div class="detail-row"><span class="detail-label">Date</span><span class="detail-value">${evt.date}</span></div>
//     <div class="detail-row"><span class="detail-label">CWC Level (Naraj)</span><span class="detail-value">${evt.cwc_observed.water_level_m} m ${tag(evt.cwc_observed.status)}</span></div>
//     <div class="detail-row"><span class="detail-label">Reading Time</span><span class="detail-value">${evt.cwc_observed.nearest_reading_time.replace("T", " ")}</span></div>
//     <div class="detail-row"><span class="detail-label">Satellite Evidence</span><span class="detail-value text">${tag(evt.satellite_evidence.status)}</span></div>
//     <div class="detail-row"><span class="detail-label">NDEM Inundation</span><span class="detail-value text">${tag(evt.ndem_inundation.status)}</span></div>
//     <div class="detail-row"><span class="detail-label">SAR Flood Mask</span><span class="detail-value text">${tag(evt.flood_mask_sar_derived.status)}</span></div>
//     <p class="muted" style="margin-top:8px; line-height:1.4;">${evt.satellite_evidence.detail}</p>
//   `;

//   Object.entries(leafletLayers).forEach(([id, layer]) => { if (id.startsWith("ndem_")) map.removeLayer(layer); });
//   const matchLayer = leafletLayers[eventId];
//   if (matchLayer) {
//     matchLayer.addTo(map);
//     const cb = document.getElementById(`layer-${eventId}`);
//     if (cb) cb.checked = true;
//     document.querySelectorAll('[id^="layer-ndem_"]').forEach((cb2) => { if (cb2.id !== `layer-${eventId}`) cb2.checked = false; });
//   }

//   updateSituation(eventId, currentStation);
// }

// // ---------------------------------------------------------------------------
// // Situation summary cards (Feature 5)
// // ---------------------------------------------------------------------------
// function updateSituation(eventId, stationName) {
//   const evt = eventsData.events.find((e) => e.id === eventId);
//   if (!evt) return;
//   const hasMask = evt.flood_mask_sar_derived.status === "DERIVED";

//   document.getElementById("sit-event").textContent = evt.date;
//   document.getElementById("sit-cwc").textContent = `${evt.cwc_observed.water_level_m} m`;
//   document.getElementById("sit-sar").textContent = evt.satellite_evidence.status === "OBSERVED" ? "Detected" : "No coverage";
//   document.getElementById("sit-candidate").textContent = hasMask ? `${window.__candidateAreaKm2} km²` : "N/A for this date";
//   document.getElementById("sit-ref").textContent = evt.ndem_inundation.available ? "NDEM available" : "None";
//   document.getElementById("sit-validation").textContent = hasMask ? `IoU ${window.__iouScore}` : "N/A for this date";
// }

// // ---------------------------------------------------------------------------
// // NDEM inundated area (Feature 4)
// // ---------------------------------------------------------------------------
// async function initNdemArea() {
//   const data = await loadJSON("data/ndem_inundated_area.json");
//   const el = document.getElementById("ndem-area-panel");
//   Object.entries(data.events).forEach(([date, info]) => {
//     const row = document.createElement("div");
//     row.className = "ndem-area-row";
//     row.innerHTML = `<span>${date}</span><span class="v">${info.inundated_area_km2_within_aoi} km²</span>`;
//     row.title = info.method;
//     el.appendChild(row);
//   });
//   const note = document.createElement("p");
//   note.className = "muted small";
//   note.style.marginTop = "6px";
//   note.textContent = "Area computed directly from verified NDEM polygon geometry (EPSG:32645), clipped to the Naraj AOI. Not a modeled or predicted value.";
//   el.appendChild(note);
// }

// // ---------------------------------------------------------------------------
// // SAR comparison (Feature 3)
// // ---------------------------------------------------------------------------
// async function initS1Cards() {
//   const data = await loadJSON("data/sentinel1/scenes_metadata.json");
//   const el = document.getElementById("s1-cards");
//   data.scenes.forEach((s) => {
//     const card = document.createElement("div");
//     card.className = "s1-card";
//     card.innerHTML = `
//       <div class="s1-card-title">${s.date} — ${s.role} ${tag("OBSERVED")}</div>
//       <div class="s1-card-row"><span>Orbit</span><span class="v">${s.relative_orbit} (${s.pass_direction})</span></div>
//       <div class="s1-card-row"><span>Product</span><span class="v">${s.product_type}, ${s.mode}, ${s.polarizations.join("+")}</span></div>
//       <div class="s1-card-row"><span>Naraj covered</span><span class="v">${s.naraj_covered ? "Yes" : "No"}</span></div>
//       <div class="s1-card-row"><span>AOI coverage</span><span class="v">${s.aoi_coverage_pct}%</span></div>
//       <p class="muted" style="margin:6px 0 0; line-height:1.35;">${s.calibration_status}</p>
//     `;
//     el.appendChild(card);
//   });
// }

// // ---------------------------------------------------------------------------
// // SAR candidate mask summary + NDEM validation summary
// // ---------------------------------------------------------------------------
// // ---------------------------------------------------------------------------
// // Guided demo flow — pure navigation aid, no fake automation
// // ---------------------------------------------------------------------------
// function initGuidedFlow() {
//   const steps = {
//     1: () => { goToTab("overview"); },
//     2: () => { goToTab("sar"); },
//     3: () => {
//       goToTab("sar");
//       setTimeout(() => {
//         const body = document.getElementById("why-flagged-content");
//         if (body.classList.contains("hidden")) document.getElementById("why-flagged-toggle").click();
//         document.getElementById("why-flagged-panel")?.scrollIntoView({behavior:"smooth", block:"center"});
//         document.querySelector(".why-flagged-panel")?.scrollIntoView({behavior:"smooth", block:"center"});
//       }, 150);
//     },
//     4: () => { goToTab("validation"); },
//     5: () => { goToTab("exposure"); },
//     6: () => {
//       goToTab("confidence");
//       setTimeout(() => document.getElementById("aiml-panel")?.scrollIntoView({behavior:"smooth", block:"center"}), 150);
//     },
//   };
//   document.querySelectorAll(".guided-step").forEach((btn) => {
//     btn.addEventListener("click", () => {
//       document.querySelectorAll(".guided-step").forEach((b) => b.classList.remove("active"));
//       btn.classList.add("active");
//       const fn = steps[btn.dataset.step];
//       if (fn) fn();
//     });
//   });
// }

// // ---------------------------------------------------------------------------
// // Flood analysis result summary (Overview tab, prioritized)
// // ---------------------------------------------------------------------------
// async function initAnalysisResultSummary() {
//   const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
//   const m = await loadJSON("data/sar_flood/validation_metrics.json");
//   const el = document.getElementById("analysis-result-summary");
//   el.innerHTML = `
//     <div class="detail-row"><span class="detail-label">Candidate inundation area</span><span class="detail-value">${params.final_candidate_area_km2} km²</span></div>
//     <div class="detail-row"><span class="detail-label">% of valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}%</span></div>
//     <div class="detail-row"><span class="detail-label">Validation vs NDEM (F1 / IoU)</span><span class="detail-value">${m.f1} / ${m.iou}</span></div>
//     <p class="muted small" style="margin-top:8px; line-height:1.4;">Independently derived from Sentinel-1 6-Aug → 18-Aug change detection, then compared against NDEM. See SAR Comparison tab for full detail.</p>
//   `;
// }

// async function initSarMaskSummary() {
//   const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
//   const el = document.getElementById("sar-mask-summary");
//   el.innerHTML = `
//     <div class="detail-row"><span class="detail-label">Threshold</span><span class="detail-value">${params.threshold_db_drop} dB drop (both VV and VH, plus combined)</span></div>
//     <div class="detail-row"><span class="detail-label">Spatial filter</span><span class="detail-value text">Remove groups &lt; ${params.min_connected_component_pixels} connected pixels</span></div>
//     <div class="detail-row"><span class="detail-label">Candidate area</span><span class="detail-value">${params.final_candidate_area_km2} km² ${tag("DERIVED")}</span></div>
//     <div class="detail-row"><span class="detail-label">% of valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}%</span></div>
//   `;
// }

// async function initSarValidationSummary() {
//   const m = await loadJSON("data/sar_flood/validation_metrics.json");
//   const el = document.getElementById("sar-validation-summary");
//   el.innerHTML = `
//     <div class="detail-row"><span class="detail-label">IoU</span><span class="detail-value">${m.iou}</span></div>
//     <div class="detail-row"><span class="detail-label">Precision</span><span class="detail-value">${m.precision}</span></div>
//     <div class="detail-row"><span class="detail-label">Recall</span><span class="detail-value">${m.recall}</span></div>
//     <div class="detail-row"><span class="detail-label">F1</span><span class="detail-value">${m.f1}</span></div>
//     <div class="detail-row"><span class="detail-label">NDEM reference area (SAR coverage)</span><span class="detail-value">${m.ndem_flood_km2_within_sar_coverage} km²</span></div>
//     <div class="detail-row"><span class="detail-label">SAR candidate area (SAR coverage)</span><span class="detail-value">${m.sar_flood_km2_within_sar_coverage} km²</span></div>
//     <p class="muted small" style="margin-top:8px; line-height:1.4;">${m.note} Prototype-stage metrics — precision is currently low (the mask over-detects, particularly along river-channel margins where backscatter changed without necessarily reflecting new inundation). This is not a validated operational accuracy figure.</p>
//   `;
// }

// // ---------------------------------------------------------------------------
// // SAR four-stage visual story (Feature 2)
// // ---------------------------------------------------------------------------
// const SAR_STAGES = {
//   preflood: {
//     vv: { src: "data/sar_flood/preflood_vv.png", caption: "6-Aug-2022 — pre-flood reference. Calibrated Sentinel-1A VV sigma0 (dB), geocoded. This establishes the baseline backscatter before the event." },
//     vh: { src: "data/sar_flood/preflood_vh.png", caption: "6-Aug-2022 — pre-flood reference. Calibrated Sentinel-1A VH sigma0 (dB), geocoded." },
//   },
//   duringflood: {
//     vv: { src: "data/sar_flood/duringflood_vv.png", caption: "18-Aug-2022 — during-flood observation. Calibrated VV sigma0 (dB). Compare directly against the pre-flood image above — darker areas indicate lower backscatter, not automatically water." },
//     vh: { src: "data/sar_flood/duringflood_vh.png", caption: "18-Aug-2022 — during-flood observation. Calibrated VH sigma0 (dB)." },
//   },
//   change: {
//     vv: { src: "data/sar_flood/change_combined.png", caption: "SAR change (combined VV+VH, dB) — 18-Aug minus 6-Aug. Blue = darkening (backscatter drop), red = brightening. This is the input to candidate generation, not a flood map itself." },
//     vh: { src: "data/sar_flood/change_combined.png", caption: "SAR change (combined VV+VH, dB) — 18-Aug minus 6-Aug. Blue = darkening (backscatter drop), red = brightening." },
//   },
//   candidate: {
//     vv: { src: "data/sar_flood/preflood_vv.png", caption: "Candidate inundation — see the map (Overview tab) or the mask summary below for the actual polygon layer. Independently derived from the change map, then spatially filtered." },
//     vh: { src: "data/sar_flood/preflood_vv.png", caption: "Candidate inundation — see the map (Overview tab) or the mask summary below for the actual polygon layer." },
//   },
// };

// function initSarStageViewer() {
//   const img = document.getElementById("sar-stage-img");
//   const caption = document.getElementById("sar-stage-caption");
//   const polToggle = document.getElementById("sar-pol-toggle");
//   let stage = "preflood", pol = "vv";

//   function render() {
//     const data = SAR_STAGES[stage][pol];
//     img.src = data.src;
//     caption.textContent = data.caption;
//     polToggle.style.display = stage === "candidate" ? "none" : "flex";
//   }

//   document.querySelectorAll(".stage-btn").forEach((btn) => {
//     btn.addEventListener("click", () => {
//       document.querySelectorAll(".stage-btn").forEach((b) => b.classList.remove("active"));
//       btn.classList.add("active");
//       stage = btn.dataset.stage;
//       render();
//     });
//   });
//   document.querySelectorAll(".pol-btn").forEach((btn) => {
//     btn.addEventListener("click", () => {
//       document.querySelectorAll(".pol-btn").forEach((b) => b.classList.remove("active"));
//       btn.classList.add("active");
//       pol = btn.dataset.pol;
//       render();
//     });
//   });
//   render();
// }

// // ---------------------------------------------------------------------------
// // "Why was this area flagged?" explain panel (Feature 3)
// // ---------------------------------------------------------------------------
// async function initWhyFlagged() {
//   const params = await loadJSON("data/sar_flood/candidate_mask_params.json");
//   const scenes = await loadJSON("data/sentinel1/scenes_metadata.json");
//   const el = document.getElementById("why-flagged-content");
//   const preflood = scenes.scenes.find((s) => s.id === "s1_06aug");
//   const duringflood = scenes.scenes.find((s) => s.id === "s1_18aug");

//   el.innerHTML = `
//     <div class="detail-row"><span class="detail-label">Pre-flood reference</span><span class="detail-value">${preflood.date} (${preflood.product_type}, ${preflood.polarizations.join("+")})</span></div>
//     <div class="detail-row"><span class="detail-label">During-flood observation</span><span class="detail-value">${duringflood.date} (${duringflood.product_type}, ${duringflood.polarizations.join("+")})</span></div>
//     <div class="detail-row"><span class="detail-label">Rule applied</span><span class="detail-value text">${params.condition}</span></div>
//     <div class="detail-row"><span class="detail-label">Threshold (T)</span><span class="detail-value">${params.threshold_db_drop} dB drop</span></div>
//     <div class="detail-row"><span class="detail-label">Spatial filtering</span><span class="detail-value text">Applied — groups &lt; ${params.min_connected_component_pixels} connected pixels removed</span></div>
//     <div class="detail-row"><span class="detail-label">Valid SAR coverage</span><span class="detail-value">${params.final_candidate_pct_of_valid_aoi}% of AOI has SAR data for this pair</span></div>
//     <div class="detail-row"><span class="detail-label">Result</span><span class="detail-value">${params.final_candidate_area_km2} km² flagged as candidate</span></div>
//     <p class="muted" style="margin-top:10px; line-height:1.5;">
//       Candidate inundation areas were identified from <strong>consistent Sentinel-1 backscatter change</strong>
//       between the pre-flood (${preflood.date}) and during-flood (${duringflood.date}) observations — both VV and
//       VH must independently exceed the threshold, and the combined change must too — followed by the project's
//       spatial filtering procedure. <strong>This is a candidate result, not a final operational flood
//       classification.</strong> Full sensitivity analysis across threshold values is documented in
//       <code>SAR_FLOOD_DETECTION_REPORT.md</code>.
//     </p>
//   `;
//   document.getElementById("why-flagged-toggle").addEventListener("click", () => {
//     el.classList.toggle("hidden");
//     document.getElementById("why-flagged-chevron").classList.toggle("open");
//   });
// }

// function initSarSlider() {
//   const slider = document.getElementById("sar-slider");
//   const afterWrap = document.getElementById("sar-img-after-wrap");
//   const afterImg = document.getElementById("sar-img-after");
//   const handle = document.getElementById("sar-slider-handle");
//   const container = document.getElementById("sar-slider-container");
        }
    );
}


// ============================================================
// UPDATE USER LOCATION MARKER
// ============================================================

function updateUserLocationMarker(
    latitude,
    longitude
) {

    if (!map) {
        return;
    }


    if (userLocationMarker) {

        userLocationMarker.setLatLng([
            latitude,
            longitude
        ]);

    } else {

        userLocationMarker =
            L.marker([
                latitude,
                longitude
            ])
            .addTo(map);

    }


    userLocationMarker.bindPopup(
        "<b>Your Location</b><br>" +
        latitude.toFixed(5) +
        ", " +
        longitude.toFixed(5)
    );


    map.setView(
        [
            latitude,
            longitude
        ],
        USER_LOCATION_ZOOM
    );
}


// ============================================================
// FETCH LOCATION DATA
// ============================================================

async function fetchLocationData(
    latitude,
    longitude
) {

    try {

        const url =
            `${API_BASE_URL}/api/location` +
            `?latitude=${encodeURIComponent(latitude)}` +
            `&longitude=${encodeURIComponent(longitude)}`;


        console.log(
            "Requesting location data:",
            url
        );


        const response =
            await fetch(url);


        if (!response.ok) {

            throw new Error(
                `Location API returned HTTP ${response.status}`
            );

        }


        const data =
            await response.json();


        console.log(
            "Location API response:",
            data
        );


        updateRainfallPanel(
            data
        );


        updateRiverPanel(
            data
        );


        addStationMarkers(
            data
        );


        showStatus(
            "Location data loaded successfully.",
            "success"
        );


    } catch (error) {

        console.error(
            "Location data error:",
            error
        );


        showStatus(
            "Unable to load CWC location data.",
            "error"
        );

    }
}


// ============================================================
// RAINFALL PANEL
// ============================================================

function updateRainfallPanel(
    data
) {

    const rainfallCard =
        document.getElementById(
            "rainfall-card"
        );


    if (!rainfallCard) {
        return;
    }


    const rainfall =
        data?.rainfall;


    if (!rainfall) {

        rainfallCard.innerHTML = `
            <h3>🌧️ CWC Rainfall</h3>
            <p>No rainfall station data available.</p>
        `;

        return;
    }


    const station =
        rainfall.station ||
        rainfall.name ||
        "Unknown station";


    const distance =
        Number(
            rainfall.distance_km ??
            rainfall.distance ??
            0
        );


    const value =
        rainfall.value ??
        rainfall.rainfall_mm ??
        rainfall.hourly_rainfall_mm ??
        null;


    const timestamp =
        rainfall.timestamp ||
        rainfall.time ||
        rainfall.observation_time ||
        "Unavailable";


    rainfallCard.innerHTML = `
        <h3>🌧️ CWC Rainfall</h3>

        <div class="data-station">
            <strong>${escapeHtml(station)}</strong>
        </div>

        <div class="data-value">
            ${
                value === null
                    ? "Unavailable"
                    : `${Number(value).toFixed(2)} mm`
            }
        </div>

        <div class="data-distance">
            ${distance.toFixed(2)} km from selected location
        </div>

        <div class="data-time">
            ${escapeHtml(timestamp)}
        </div>
    `;
}


// ============================================================
// RIVER PANEL
// ============================================================

function updateRiverPanel(
    data
) {

    const riverCard =
        document.getElementById(
            "river-card"
        );


    if (!riverCard) {
        return;
    }


    const river =
        data?.river;


    if (!river) {

        riverCard.innerHTML = `
            <h3>🌊 CWC River / Water Level</h3>
            <p>No river station data available.</p>
        `;

        return;
    }


    const station =
        river.station ||
        river.name ||
        "Unknown station";


    const waterLevel =
        river.water_level_m ??
        river.water_level ??
        null;


    const discharge =
        river.discharge_m3s ??
        river.discharge ??
        river.value ??
        null;


    const distance =
        Number(
            river.distance_km ??
            river.distance ??
            0
        );


    const timestamp =
        river.timestamp ||
        river.time ||
        river.observation_time ||
        "Unavailable";


    riverCard.innerHTML = `
        <h3>🌊 CWC River / Water Level</h3>

        <div class="data-station">
            <strong>${escapeHtml(station)}</strong>
        </div>

        ${
            waterLevel !== null
                ? `
                    <div class="data-value">
                        ${Number(waterLevel).toFixed(2)} m
                    </div>
                `
                : ""
        }

        ${
            discharge !== null
                ? `
                    <div class="data-secondary">
                        Discharge:
                        ${Number(discharge).toFixed(2)}
                        m³/s
                    </div>
                `
                : ""
        }

        <div class="data-distance">
            ${distance.toFixed(2)} km from selected location
        </div>

        <div class="data-time">
            ${escapeHtml(timestamp)}
        </div>
    `;
}


// ============================================================
// STATION MARKERS
// ============================================================

function addStationMarkers(
    data
) {

    if (!map) {
        return;
    }


    if (
        data?.rainfall &&
        data.rainfall.latitude !== undefined &&
        data.rainfall.longitude !== undefined
    ) {

        const lat =
            Number(data.rainfall.latitude);

        const lon =
            Number(data.rainfall.longitude);


        if (rainfallMarker) {
            map.removeLayer(
                rainfallMarker
            );
        }


        rainfallMarker =
            L.marker([
                lat,
                lon
            ])
            .addTo(map)
            .bindPopup(
                `<b>CWC Rainfall Station</b><br>` +
                `${escapeHtml(
                    data.rainfall.station ||
                    data.rainfall.name ||
                    "Rainfall station"
                )}`
            );
    }


    if (
        data?.river &&
        data.river.latitude !== undefined &&
        data.river.longitude !== undefined
    ) {

        const lat =
            Number(data.river.latitude);

        const lon =
            Number(data.river.longitude);


        if (riverMarker) {
            map.removeLayer(
                riverMarker
            );
        }


        riverMarker =
            L.marker([
                lat,
                lon
            ])
            .addTo(map)
            .bindPopup(
                `<b>CWC River Station</b><br>` +
                `${escapeHtml(
                    data.river.station ||
                    data.river.name ||
                    "River station"
                )}`
            );
    }
}


// ============================================================
// STATUS MESSAGE
// ============================================================

function showStatus(
    message,
    type = "info"
) {

    let status =
        document.getElementById(
            "floodwatch-status"
        );


    if (!status) {

        status =
            document.createElement(
                "div"
            );

        status.id =
            "floodwatch-status";


        status.style.position =
            "fixed";

        status.style.bottom =
            "20px";

        status.style.left =
            "20px";

        status.style.zIndex =
            "10000";

        status.style.padding =
            "10px 14px";

        status.style.borderRadius =
            "8px";

        status.style.fontSize =
            "13px";

        status.style.background =
            "#ffffff";

        status.style.boxShadow =
            "0 2px 10px rgba(0,0,0,0.15)";


        document.body.appendChild(
            status
        );
    }


    status.textContent =
        message;


    if (type === "error") {

        status.style.border =
            "1px solid #c0392b";

    } else if (type === "success") {

        status.style.border =
            "1px solid #2e7d32";

    } else {

        status.style.border =
            "1px solid #8aa0a8";

    }


    clearTimeout(
        status.__hideTimer
    );


    status.__hideTimer =
        setTimeout(
            () => {
                status.remove();
            },
            5000
        );
}


// ============================================================
// HTML ESCAPE HELPER
// ============================================================

function escapeHtml(
    value
) {

    return String(
        value ?? ""
    )
    .replace(
        /&/g,
        "&amp;"
    )
    .replace(
        /</g,
        "&lt;"
    )
    .replace(
        />/g,
        "&gt;"
    )
    .replace(
        /"/g,
        "&quot;"
    )
    .replace(
        /'/g,
        "&#039;"
    );
}


// ============================================================
// LOCATION SEARCH
// ============================================================

async function searchLocation(
    query
) {

    const trimmed =
        String(query || "").trim();


    if (!trimmed) {
        return;
    }


    try {

        showStatus(
            "Searching for location...",
            "loading"
        );


        const url =
            "https://nominatim.openstreetmap.org/search" +
            "?format=json" +
            "&limit=1" +
            "&q=" +
            encodeURIComponent(
                trimmed
            );


        const response =
            await fetch(
                url,
                {
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );


        if (!response.ok) {

            throw new Error(
                `Location search returned HTTP ${response.status}`
            );

        }


        const results =
            await response.json();


        if (
            !Array.isArray(results) ||
            results.length === 0
        ) {

            showStatus(
                "Location not found.",
                "error"
            );

            return;
        }


        const result =
            results[0];


        const latitude =
            Number(result.lat);


        const longitude =
            Number(result.lon);


        if (
            !Number.isFinite(latitude) ||
            !Number.isFinite(longitude)
        ) {

            throw new Error(
                "Invalid coordinates returned by location search."
            );
        }


        userLatitude =
            latitude;

        userLongitude =
            longitude;


        updateUserLocationMarker(
            latitude,
            longitude
        );


        await fetchLocationData(
            latitude,
            longitude
        );


    } catch (error) {

        console.error(
            "Location search error:",
            error
        );


        showStatus(
            "Unable to search for this location.",
            "error"
        );

    }
}


// ============================================================
// LOCATION SEARCH UI
// ============================================================

function createLocationSearch() {

    let container =
        document.getElementById(
            "location-search"
        );


    if (!container) {

        container =
            document.createElement(
                "div"
            );

        container.id =
            "location-search";


        container.style.position =
            "fixed";

        container.style.top =
            "20px";

        container.style.left =
            "20px";

        container.style.zIndex =
            "9999";

        container.style.display =
            "flex";

        container.style.gap =
            "6px";

        container.style.background =
            "#ffffff";

        container.style.padding =
            "8px";

        container.style.borderRadius =
            "8px";

        container.style.boxShadow =
            "0 2px 10px rgba(0,0,0,0.15)";


        document.body.appendChild(
            container
        );
    }


    let input =
        document.getElementById(
            "location-input"
        );


    if (!input) {

        input =
            document.createElement(
                "input"
            );

        input.id =
            "location-input";

        input.type =
            "text";

        input.placeholder =
            "Search city, district or place";

        input.style.width =
            "230px";

        input.style.padding =
            "9px";

        input.style.border =
            "1px solid #ccd6da";

        input.style.borderRadius =
            "6px";


        container.appendChild(
            input
        );
    }


    let button =
        document.getElementById(
            "search-location"
        );


    if (!button) {

        button =
            document.createElement(
                "button"
            );

        button.id =
            "search-location";

        button.type =
            "button";

        button.textContent =
            "Search";

        button.style.padding =
            "9px 13px";

        button.style.border =
            "none";

        button.style.borderRadius =
            "6px";

        button.style.cursor =
            "pointer";


        container.appendChild(
            button
        );
    }


    button.addEventListener(
        "click",
        () => {
            searchLocation(
                input.value
            );
        }
    );


    input.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key ===
                "Enter"
            ) {

                event.preventDefault();

                searchLocation(
                    input.value
                );
            }
        }
    );
}


// ============================================================
// INITIAL LOAD LOCATION
// ============================================================

async function loadDefaultLocation() {

    try {

        updateUserLocationMarker(
            DEFAULT_LOCATION[0],
            DEFAULT_LOCATION[1]
        );


        await fetchLocationData(
            DEFAULT_LOCATION[0],
            DEFAULT_LOCATION[1]
        );


    } catch (error) {

        console.error(
            "Default location load failed:",
            error
        );

    }
}


// ============================================================
// AI FLOOD FORECAST
// ============================================================

async function loadFloodForecast() {

    const card =
        document.getElementById(
            "flood-forecast"
        );


    if (!card) {

        console.warn(
            "Flood forecast card not found."
        );

        return;
    }


    try {

        card.innerHTML = `
            <h3>🤖 AI Flood Forecast</h3>
            <p>Loading AI forecast...</p>
        `;


        const response =
            await fetch(
                `${API_BASE_URL}/api/forecast`,
                {
                    method: "GET",
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );


        if (!response.ok) {

            throw new Error(
                `Forecast API returned HTTP ${response.status}`
            );

        }


        const data =
            await response.json();


        console.log(
            "AI Forecast API response:",
            data
        );


        if (
            !data ||
            !data.forecast ||
            typeof data.forecast !== "object"
        ) {

            throw new Error(
                "Invalid forecast response from API."
            );

        }


        const forecast6 =
            data.forecast["6h"] || {};


        const forecast12 =
            data.forecast["12h"] || {};


        const forecast24 =
            data.forecast["24h"] || {};


        const probability6 =
            Number(
                forecast6.flood_probability_percent ?? 0
            );


        const probability12 =
            Number(
                forecast12.flood_probability_percent ?? 0
            );


        const probability24 =
            Number(
                forecast24.flood_probability_percent ?? 0
            );


        const overallRisk =
            data.overall_risk ||
            data.risk ||
            "LOW";


        const modelName =
            data.model_name ||
            "FloodWatch Future Flood Forecast";


        const algorithm =
            data.algorithm ||
            "Random Forest";


        const studyRegion =
            data.study_region ||
            "Naraj / Cuttack, Odisha";


        const featureCount =
            data.feature_count ??
            data.model_features ??
            71;


        const latitude =
            Number(
                data.location?.latitude ??
                DEFAULT_LOCATION[0]
            );


        const longitude =
            Number(
                data.location?.longitude ??
                DEFAULT_LOCATION[1]
            );


        const observationTime =
            data.observation_time ||
            data.observed_at ||
            "Latest available historical observation";


        const warning =
            data.warning ||
            "Historical-data AI forecast. Not a live government warning.";


        const scope =
            data.model_scope ||
            "Temporal model trained for the Naraj/Cuttack study region in Odisha; it is not fully India-wide calibrated.";


        function riskClass(
            risk
        ) {

            const value =
                String(
                    risk ||
                    "LOW"
                ).toUpperCase();


            if (
                value === "HIGH"
            ) {

                return "risk-high";

            }


            if (
                value === "MEDIUM" ||
                value === "MODERATE"
            ) {

                return "risk-medium";

            }


            return "risk-low";
        }


        function forecastItem(
            title,
            forecast,
            probability
        ) {

            const risk =
                forecast?.risk ||
                "LOW";


            return `
                <div class="forecast-item">

                    <strong>
                        ${escapeHtml(title)}
                    </strong>

                    <span
                        class="forecast-risk ${riskClass(risk)}"
                    >
                        ${escapeHtml(risk)}
                    </span>

                    <small>
                        ${probability.toFixed(2)}%
                        flood probability
                    </small>

                </div>
            `;
        }


        const maxProbability =
            Math.max(
                probability6,
                probability12,
                probability24
            );


        card.innerHTML = `
            <h3>🤖 AI Flood Forecast</h3>

            <div
                class="forecast-summary"
                style="
                    margin:10px 0 14px;
                    padding:12px;
                    border:1px solid #d9e2e8;
                    border-radius:10px;
                    background:#f7fafb;
                "
            >

                <div
                    style="
                        font-size:12px;
                        color:#5f6f78;
                    "
                >
                    Overall predicted risk
                </div>

                <div
                    class="forecast-risk ${riskClass(overallRisk)}"
                    style="
                        font-size:22px;
                        margin-top:3px;
                    "
                >
                    ${escapeHtml(overallRisk)}
                </div>

                <div
                    style="
                        font-size:12px;
                        margin-top:5px;
                    "
                >
                    Maximum forecast probability:
                    <strong>
                        ${maxProbability.toFixed(2)}%
                    </strong>
                </div>

            </div>

            <div class="forecast-location">
                📍
                ${latitude.toFixed(4)},
                ${longitude.toFixed(4)}
            </div>

            <div
                class="forecast-model-info"
                style="
                    margin:10px 0;
                    padding:10px;
                    border-left:3px solid #0f6b78;
                    background:#f7fafb;
                    font-size:12px;
                    line-height:1.55;
                "
            >

                <div>
                    <strong>Model:</strong>
                    ${escapeHtml(modelName)}
                </div>

                <div>
                    <strong>Algorithm:</strong>
                    ${escapeHtml(algorithm)}
                </div>

                <div>
                    <strong>Study region:</strong>
                    ${escapeHtml(studyRegion)}
                </div>

                <div>
                    <strong>Input features:</strong>
                    ${escapeHtml(
                        String(featureCount)
                    )}
                </div>

            </div>

            <div class="forecast-grid">

                ${forecastItem(
                    "6 Hours",
                    forecast6,
                    probability6
                )}

                ${forecastItem(
                    "12 Hours",
                    forecast12,
                    probability12
                )}

                ${forecastItem(
                    "24 Hours",
                    forecast24,
                    probability24
                )}

            </div>

            <div class="forecast-time">
                <strong>
                    Observation:
                </strong>

                ${escapeHtml(
                    observationTime
                )}
            </div>

            <div
                class="forecast-warning"
                style="
                    margin-top:10px;
                    padding:9px;
                    border-radius:8px;
                    background:#fff8e6;
                    color:#6b5312;
                    font-size:12px;
                    line-height:1.45;
                "
            >
                ⚠️
                ${escapeHtml(warning)}
            </div>

            <div
                class="forecast-scope"
                style="
                    margin-top:8px;
                    font-size:11px;
                    color:#66757d;
                    line-height:1.45;
                "
            >

                <strong>
                    Model scope:
                </strong>

                ${escapeHtml(scope)}

            </div>
        `;


    } catch (error) {

        console.error(
            "AI Flood Forecast Error:",
            error
        );


        card.innerHTML = `
            <h3>🤖 AI Flood Forecast</h3>

            <p class="forecast-error">
                ⚠️ Unable to load AI forecast.
            </p>

            <small>
                Make sure the FloodWatch Python API
                is running at
                ${escapeHtml(API_BASE_URL)}.
            </small>

            <div
                style="
                    margin-top:8px;
                    font-size:11px;
                    color:#66757d;
                    line-height:1.4;
                "
            >
                Error:
                ${escapeHtml(error.message)}
            </div>
        `;
    }
}


// ============================================================
// START DASHBOARD
// ============================================================

function startDashboard() {

    initializeMap();

    createLocationButton();

    createLocationSearch();

    loadDefaultLocation();

}


document.addEventListener(
    "DOMContentLoaded",
    function () {

        startDashboard();

        loadFloodForecast();

    }
);


console.log(
    "FloodWatch dashboard loaded successfully."
);
    rainfallMarker.bindPopup(
        "<b>🌧 CWC Rainfall Station</b><br>" +
        "<strong>" +
        escapeHtml(station.station) +
        "</strong><br>" +
        "Distance: " +
        station.distance_km +
        " km"
    );
}


// ============================================================
// RIVER MAP MARKER
// ============================================================

function updateRiverMarker(
    station,
    observation
) {

    if (
        !map ||
        !station
    ) {

        return;
    }


    const location = [
        station.latitude,
        station.longitude
    ];


    if (riverMarker) {

        riverMarker.setLatLng(
            location
        );

    } else {

        riverMarker =
            L.marker(
                location
            )
            .addTo(
                map
            );
    }


    riverMarker.bindPopup(
        "<b>🌊 CWC River Station</b><br>" +
        "<strong>" +
        escapeHtml(station.station) +
        "</strong><br>" +
        "Distance: " +
        station.distance_km +
        " km"
    );
}


// ============================================================
// FIND ELEMENT
// ============================================================

function findElement(
    ids
) {

    for (
        const id of ids
    ) {

        const element =
            document.getElementById(
                id
            );


        if (element) {

            return element;

        }
    }


    return null;
}


// ============================================================
// LOCATION SEARCH
// ============================================================

function initializeLocationSearch() {

    const searchInput =
        findElement(
            [
                "location-search",
                "location-input",
                "search-location"
            ]
        );


    const searchButton =
        findElement(
            [
                "location-search-btn",
                "search-location-btn",
                "location-search-button"
            ]
        );


    if (
        searchInput &&
        searchButton
    ) {

        searchButton.addEventListener(
            "click",
            function () {

                searchLocation(
                    searchInput.value
                );

            }
        );


        searchInput.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key ===
                    "Enter"
                ) {

                    searchLocation(
                        searchInput.value
                    );

                }
            }
        );
    }
}


// ============================================================
// SEARCH LOCATION WITH OPENSTREETMAP NOMINATIM
// ============================================================

async function searchLocation(
    query
) {

    if (
        !query ||
        !String(query).trim()
    ) {

        showStatus(
            "Enter a location to search.",
            "error"
        );

        return;
    }


    const cleanQuery =
        String(query).trim();


    showStatus(
        "Searching location...",
        "loading"
    );


    try {

        const url =
            "https://nominatim.openstreetmap.org/search" +
            "?format=json" +
            "&limit=1" +
            "&q=" +
            encodeURIComponent(
                cleanQuery
            );


        const response =
            await fetch(
                url,
                {
                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );


        if (!response.ok) {

            throw new Error(
                "Location search failed with HTTP " +
                response.status
            );

        }


        const results =
            await response.json();


        if (
            !Array.isArray(results) ||
            results.length === 0
        ) {

            showStatus(
                "Location not found.",
                "error"
            );

            return;
        }


        const result =
            results[0];


        const latitude =
            Number(
                result.lat
            );


        const longitude =
            Number(
                result.lon
            );


        if (
            !Number.isFinite(latitude) ||
            !Number.isFinite(longitude)
        ) {

            throw new Error(
                "Invalid coordinates returned."
            );

        }


        userLatitude =
            latitude;


        userLongitude =
            longitude;


        updateUserLocationMarker(
            latitude,
            longitude
        );


        await fetchLocationData(
            latitude,
            longitude
        );


        showStatus(
            "Location selected successfully.",
            "success"
        );


    } catch (error) {

        console.error(
            "Location search error:",
            error
        );


        showStatus(
            "Unable to search for location.",
            "error"
        );
    }
}


// ============================================================
// BROWSER GEOLOCATION
// ============================================================

function initializeGeolocation() {

    const button =
        findElement(
            [
                "use-my-location",
                "location-btn",
                "get-location"
            ]
        );


    if (!button) {

        console.warn(
            "Location button not found."
        );

        return;
    }


    button.addEventListener(
        "click",
        function () {

            if (
                !navigator.geolocation
            ) {

                showStatus(
                    "Geolocation is not supported by this browser.",
                    "error"
                );

                return;
            }


            showStatus(
                "Getting your location...",
                "loading"
            );


            button.disabled =
                true;


            navigator.geolocation.getCurrentPosition(

                async function(position) {

                    const latitude =
                        position.coords.latitude;


                    const longitude =
                        position.coords.longitude;


                    userLatitude =
                        latitude;


                    userLongitude =
                        longitude;


                    updateUserLocationMarker(
                        latitude,
                        longitude
                    );


                    await fetchLocationData(
                        latitude,
                        longitude
                    );


                    button.disabled =
                        false;


                    showStatus(
                        "Your location has been selected.",
                        "success"
                    );

                },


                function(error) {

                    console.error(
                        "Geolocation error:",
                        error
                    );


                    button.disabled =
                        false;


                    let message =
                        "Unable to determine your location.";


                    if (
                        error.code ===
                        error.PERMISSION_DENIED
                    ) {

                        message =
                            "Location permission was denied.";

                    } else if (
                        error.code ===
                        error.POSITION_UNAVAILABLE
                    ) {

                        message =
                            "Your location is unavailable.";

                    } else if (
                        error.code ===
                        error.TIMEOUT
                    ) {

                        message =
                            "Location request timed out.";

                    }


                    showStatus(
                        message,
                        "error"
                    );
                },

                {
                    enableHighAccuracy: true,
                    timeout: 15000,
                    maximumAge: 300000
                }
            );
        }
    );
}


// ============================================================
// AI FORECAST REFRESH
// ============================================================

function initializeForecastRefresh() {

    const button =
        findElement(
            [
                "refresh-forecast",
                "forecast-refresh",
                "refresh-ai-forecast"
            ]
        );


    if (!button) {

        return;
    }


    button.addEventListener(
        "click",
        function () {

            loadFloodForecast();

        }
    );
}


// ============================================================
// INITIALIZE DASHBOARD
// ============================================================

function initializeDashboard() {

    initializeMap();

    initializeLocationSearch();

    initializeGeolocation();

    initializeForecastRefresh();


    if (
        !userLatitude ||
        !userLongitude
    ) {

        userLatitude =
            DEFAULT_LOCATION[0];

        userLongitude =
            DEFAULT_LOCATION[1];

    }


    updateUserLocationMarker(
        userLatitude,
        userLongitude
    );


    fetchLocationData(
        userLatitude,
        userLongitude
    );


    loadFloodForecast();


    console.log(
        "FloodWatch dashboard initialized."
    );
}


// ============================================================
// START
// ============================================================

if (
    document.readyState ===
    "loading"
) {

    document.addEventListener(
        "DOMContentLoaded",
        initializeDashboard
    );

} else {

    initializeDashboard();

}
    let value =
        "No valid rainfall observation";


    if (
        observation
        &&
        typeof observation.rainfall_mm
        === "number"
    ) {

        value =
            observation.rainfall_mm
            .toFixed(2)
            +
            " mm";
    }


    rainfallMarker.bindPopup(
        `
        <b>🌧 CWC Rainfall Station</b>
        <br>
        <strong>${escapeHtml(station.station)}</strong>
        <br>
        Distance: ${station.distance_km} km
        <br>
        Rainfall: ${escapeHtml(value)}
        <br>
        <small>
        Historical CWC data
        </small>
        `
    );
}


// ============================================================
// RIVER MAP MARKER
// ============================================================

function updateRiverMarker(
    station,
    observation
) {

    if (
        !map
        ||
        !station
    ) {

        return;
    }


    const location =
        [
            station.latitude,
            station.longitude
        ];


    if (
        riverMarker
    ) {

        riverMarker.setLatLng(
            location
        );

    } else {

        riverMarker =
            L.marker(
                location
            )
            .addTo(
                map
            );
    }


    let value =
        "No valid discharge observation";


    if (
        observation
        &&
        typeof observation.discharge_m3s
        === "number"
    ) {

        value =
            observation.discharge_m3s
            .toFixed(2)
            +
            " m³/s";
    }


    riverMarker.bindPopup(
        `
        <b>🌊 CWC River Station</b>
        <br>
        <strong>${escapeHtml(station.station)}</strong>
        <br>
        Distance: ${station.distance_km} km
        <br>
        Discharge: ${escapeHtml(value)}
        <br>
        <small>
        Historical CWC data
        </small>
        `
    );
}


// ============================================================
// STATUS MESSAGE
// ============================================================

function showStatus(
    message,
    type = "info"
) {

    let status =
        document.getElementById(
            "location-status"
        );


    if (!status) {

        status =
            document.createElement(
                "div"
            );

        status.id =
            "location-status";

        status.style.position =
            "fixed";

        status.style.bottom =
            "20px";

        status.style.left =
            "20px";

        status.style.zIndex =
            "9999";

        status.style.padding =
            "10px 15px";

        status.style.borderRadius =
            "8px";

        status.style.background =
            "white";

        status.style.boxShadow =
            "0 2px 10px rgba(0,0,0,0.2)";


        document.body.appendChild(
            status
        );
    }


    status.textContent =
        message;


    if (type === "error") {

        status.style.border =
            "2px solid #dc2626";

    } else if (
        type === "success"
    ) {

        status.style.border =
            "2px solid #16a34a";

    } else {

        status.style.border =
            "2px solid #2563eb";
    }
}


// ============================================================
// FIND FIRST EXISTING ELEMENT
// ============================================================

function findElement(
    ids
) {

    for (
        const id of ids
    ) {

        const element =
            document.getElementById(
                id
            );


        if (element) {

            return element;
        }
    }


    return null;
}


// ============================================================
// HTML ESCAPING
// ============================================================

function escapeHtml(
    value
) {

    if (
        value === null
        ||
        value === undefined
    ) {

        return "";
    }


    return String(value)
        .replace(
            /&/g,
            "&amp;"
        )
        .replace(
            /</g,
            "&lt;"
        )
        .replace(
            />/g,
            "&gt;"
        )
        .replace(
            /"/g,
            "&quot;"
        )
        .replace(
            /'/g,
            "&#039;"
        );
}


// ============================================================
// INITIALIZATION
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function() {

        console.log(
            "Naraj dashboard starting..."
        );


        initializeMap();


        createLocationButton();


        console.log(
            "Naraj dashboard ready."
        );
    }
);

// ------------------------------------------------------------------------
// AI FLOOD FORECAST
// ------------------------------------------------------------------------

async function loadFloodForecast() {

    const card =
        document.getElementById(
            "flood-forecast"
        );


    if (!card) {

        console.warn(
            "Flood forecast card not found."
        );

        return;
    }


    try {

        card.innerHTML = `
            <h3>🤖 AI Flood Forecast</h3>
            <p>Loading AI forecast...</p>
        `;


        const response =
            await fetch(
                `${API_BASE_URL}/api/forecast`,
                {
                    method: "GET",

                    headers: {
                        "Accept":
                            "application/json"
                    }
                }
            );


        if (!response.ok) {

            throw new Error(
                `Forecast API returned HTTP ${response.status}`
            );
        }


        const data =
            await response.json();


        console.log(
            "AI Forecast API response:",
            data
        );


        if (
            !data
            ||
            !data.forecast
            ||
            typeof data.forecast
            !== "object"
        ) {

            throw new Error(
                "Invalid forecast response from API."
            );
        }


        const forecast6 =
            data.forecast["6h"]
            ||
            {};

        const forecast12 =
            data.forecast["12h"]
            ||
            {};

        const forecast24 =
            data.forecast["24h"]
            ||
            {};


        const probability6 =
            Number(
                forecast6
                    .flood_probability_percent
                ??
                0
            );


        const probability12 =
            Number(
                forecast12
                    .flood_probability_percent
                ??
                0
            );


        const probability24 =
            Number(
                forecast24
                    .flood_probability_percent
                ??
                0
            );


        const overallRisk =
            data.overall_risk
            ||
            data.risk
            ||
            "LOW";


        const modelName =
            data.model_name
            ||
            "FloodWatch Future Flood Forecast";


        const algorithm =
            data.algorithm
            ||
            "Random Forest";


        const studyRegion =
            data.study_region
            ||
            "Naraj / Cuttack, Odisha";


        const featureCount =
            data.feature_count
            ??
            data.model_features
            ??
            71;


        const latitude =
            Number(
                data.location?.latitude
                ??
                DEFAULT_LOCATION[0]
            );


        const longitude =
            Number(
                data.location?.longitude
                ??
                DEFAULT_LOCATION[1]
            );


        const observationTime =
            data.observation_time
            ||
            data.observed_at
            ||
            "Latest available historical observation";


        const warning =
            data.warning
            ||
            "Historical-data AI forecast. Not a live government warning.";


        const scope =
            data.model_scope
            ||
            "Temporal model trained for the Naraj/Cuttack study region in Odisha; it is not fully India-wide calibrated.";


        function riskClass(
            risk
        ) {

            const value =
                String(
                    risk
                    ||
                    "LOW"
                )
                .toUpperCase();


            if (
                value === "HIGH"
            ) {

                return "risk-high";
            }


            if (
                value === "MEDIUM"
                ||
                value === "MODERATE"
            ) {

                return "risk-medium";
            }


            return "risk-low";
        }


        function forecastItem(
            title,
            forecast,
            probability
        ) {

            const risk =
                forecast?.risk
                ||
                "LOW";


            return `
                <div class="forecast-item">

                    <strong>
                        ${escapeHtml(title)}
                    </strong>

                    <span
                        class="forecast-risk ${riskClass(risk)}"
                    >
                        ${escapeHtml(risk)}
                    </span>

                    <small>
                        ${probability.toFixed(2)}% flood probability
                    </small>

                </div>
            `;
        }


        const maxProbability =
            Math.max(
                probability6,
                probability12,
                probability24
            );


        card.innerHTML = `

            <h3>🤖 AI Flood Forecast</h3>


            <div
                class="forecast-summary"
                style="
                    margin:10px 0 14px;
                    padding:12px;
                    border:1px solid #d9e2e8;
                    border-radius:10px;
                    background:#f7fafb;
                "
            >

                <div
                    style="
                        font-size:12px;
                        color:#5f6f78;
                    "
                >
                    Overall predicted risk
                </div>


                <div
                    class="forecast-risk ${riskClass(overallRisk)}"
                    style="
                        font-size:22px;
                        margin-top:3px;
                    "
                >
                    ${escapeHtml(overallRisk)}
                </div>


                <div
                    style="
                        font-size:12px;
                        margin-top:5px;
                    "
                >

                    Maximum forecast probability:

                    <strong>
                        ${maxProbability.toFixed(2)}%
                    </strong>

                </div>

            </div>


            <div class="forecast-location">

                📍
                ${latitude.toFixed(4)},
                ${longitude.toFixed(4)}

            </div>


            <div
                class="forecast-model-info"
                style="
                    margin:10px 0;
                    padding:10px;
                    border-left:3px solid #0f6b78;
                    background:#f7fafb;
                    font-size:12px;
                    line-height:1.55;
                "
            >

                <div>
                    <strong>Model:</strong>
                    ${escapeHtml(modelName)}
                </div>

                <div>
                    <strong>Algorithm:</strong>
                    ${escapeHtml(algorithm)}
                </div>

                <div>
                    <strong>Study region:</strong>
                    ${escapeHtml(studyRegion)}
                </div>

                <div>
                    <strong>Input features:</strong>
                    ${escapeHtml(String(featureCount))}
                </div>

            </div>


            <div class="forecast-grid">

                ${forecastItem(
                    "6 Hours",
                    forecast6,
                    probability6
                )}

                ${forecastItem(
                    "12 Hours",
                    forecast12,
                    probability12
                )}

                ${forecastItem(
                    "24 Hours",
                    forecast24,
                    probability24
                )}

            </div>


            <div class="forecast-time">

                <strong>
                    Observation:
                </strong>

                ${escapeHtml(
                    observationTime
                )}

            </div>


            <div
                class="forecast-warning"
                style="
                    margin-top:10px;
                    padding:9px;
                    border-radius:8px;
                    background:#fff8e6;
                    color:#6b5312;
                    font-size:12px;
                    line-height:1.45;
                "
            >

                ⚠️
                ${escapeHtml(warning)}

            </div>


            <div
                class="forecast-scope"
                style="
                    margin-top:8px;
                    font-size:11px;
                    color:#66757d;
                    line-height:1.45;
                "
            >

                <strong>
                    Model scope:
                </strong>

                ${escapeHtml(scope)}

            </div>

        `;

    } catch (
        error
    ) {

        console.error(
            "AI Flood Forecast Error:",
            error
        );


        card.innerHTML = `

            <h3>
                🤖 AI Flood Forecast
            </h3>

            <p class="forecast-error">
                ⚠️ Unable to load AI forecast.
            </p>

            <small>

                Make sure the FloodWatch Python API
                is running at
                ${escapeHtml(API_BASE_URL)}.

            </small>

            <div
                style="
                    margin-top:8px;
                    font-size:11px;
                    color:#66757d;
                    line-height:1.4;
                "
            >

                Error:
                ${escapeHtml(
                    error.message
                )}

            </div>

        `;
    }
}


// ------------------------------------------------------------------------
// START DASHBOARD
// ------------------------------------------------------------------------

initTourBanner();


document.addEventListener(
    "DOMContentLoaded",
    function () {

        loadFloodForecast();

    }
);


console.log(
    "FloodWatch dashboard loaded successfully."
);