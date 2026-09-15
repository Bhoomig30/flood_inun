// ============================================================================
// FLOODWATCH — PUBLIC DASHBOARD
// Existing SAR / CWC / NDEM functionality
// + AI Random Forest Flood Inundation
// ============================================================================


// ============================================================================
// JSON LOADER
// ============================================================================

async function loadJSON(path, retries) {

  const attempts = 1 + (retries === undefined ? 2 : retries);

  for (let attempt = 1; attempt <= attempts; attempt++) {

    try {

      const res = await fetch(path);

      if (!res.ok) {
        throw new Error(
          `Failed to load ${path}: ${res.status}`
        );
      }

      return res.json();
    }
    catch (err) {

      if (attempt === attempts) {
        throw err;
      }

      // Backoff before retrying transient failures (server restart, blip).
      await new Promise((r) => setTimeout(r, 600 * attempt));
    }
  }
}


// ============================================================================
// NAVIGATION
// ============================================================================

document
  .querySelectorAll(".pub-nav-btn")
  .forEach((btn) => {

    btn.addEventListener("click", () => {

      document
        .querySelectorAll(".pub-nav-btn")
        .forEach((b) =>
          b.classList.remove("active")
        );

      document
        .querySelectorAll(".pub-pane")
        .forEach((p) =>
          p.classList.remove("active")
        );

      btn.classList.add("active");

      const pane =
        document.getElementById(
          `pub-${btn.dataset.pubtab}`
        );

      if (pane) {
        pane.classList.add("active");
      }

      setTimeout(() => {

        if (map1) {
          map1.invalidateSize();
        }

        if (map2) {
          map2.invalidateSize();
        }

      }, 50);

    });

  });


// ============================================================================
// MAPS
// ============================================================================

let map1 = null;
let map2 = null;

// Study-region context layers (Mahanadi AOI) — clearly-labelled historical
// study data, hidden by default so the India-wide default view is neutral.
let studyAreaGroup = null;
let stationsGroup = null;
let candidateGroup = null;

const layerRegistry = {};

// Active NDEM layer on the flood map — swapped when the selected event changes.
let ndemLayer = null;

// Active satellite images (so event changes can restyle them in place).
const satImageState = {
  polarization: "vv",
};

const SAR_IMAGE_BASE = "data/sar_flood/";


// ============================================================================
// AI FLOOD CONFIGURATION
// ============================================================================

const AI_FLOOD_SCENE = "1017769";

const AI_FLOOD_GEOJSON =
  "data/ai_flood/1017769_flood.geojson";

const AI_FLOOD_RESULTS =
  "data/ai_flood/ai_flood_results_1017769.json";

const AI_FLOOD_THRESHOLD = 0.65;


// Generated GeoTIFF bounds
const AI_FLOOD_BOUNDS = [
  [
    26.58438319211947,
    92.99934742987124
  ],
  [
    26.63037693466639,
    93.04534117241816
  ]
];


// AI results loaded from JSON
let aiFloodResults = null;


// ============================================================================
// MARKER ICON
// ============================================================================

function markerIcon(color, size = 12) {

  return L.divIcon({

    className: "",

    html: `
      <div
        style="
          width:${size}px;
          height:${size}px;
          border-radius:50%;
          background:${color};
          border:2px solid white;
          box-shadow:
            0 0 0 1px rgba(0,0,0,0.3);
        ">
      </div>
    `,

    iconSize: [
      size,
      size
    ],

    iconAnchor: [
      size / 2,
      size / 2
    ]

  });

}


// ============================================================================
// CREATE MAP
// ============================================================================

function makeMap(elId) {

  const m =
    L.map(
      elId,
      {
        zoomControl: true
      }
    ).setView(
      [
        22.5,
        79.0
      ],
      4.5
    );

  L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
      attribution:
        "&copy; OpenStreetMap contributors"
    }
  ).addTo(m);

  // Map-click → drive the shared location pipeline (single source of truth
  // in app.js). Clicking anywhere in India re-centers everything.
  m.on("click", (e) => {
    if (
      typeof setSelectedLocation === "function" &&
      window.FloodWatchState
    ) {
      setSelectedLocation(
        e.latlng.lat,
        e.latlng.lng,
        "Map pin (" +
          e.latlng.lat.toFixed(3) + ", " + e.latlng.lng.toFixed(3) + ")"
      );
    }
  });

  return m;

}


// ============================================================================
// SAR CANDIDATE FLOOD MASK
// ============================================================================

async function addCandidateMask(m) {

  const gj =
    await loadJSON(
      "data/sar_flood/sar_flood_candidate_18aug.geojson"
    );

  candidateGroup = L.geoJSON(
    gj,
    {

      style: {

        color: "#a4271f",

        weight: 1,

        fillColor: "#a4271f",

        fillOpacity: 0.55

      }

    }
  ).addTo(m);

  return candidateGroup;

}


// ============================================================================
// AI FLOOD GEOJSON LAYER
// ============================================================================

async function addAIFloodLayer(m) {

  console.log(
    "Loading AI flood GeoJSON:",
    AI_FLOOD_GEOJSON
  );

  const gj =
    await loadJSON(
      AI_FLOOD_GEOJSON
    );

  console.log(
    "AI flood GeoJSON loaded."
  );

  console.log(
    "AI polygons:",
    gj.features
      ? gj.features.length
      : 0
  );


  const layer =
    L.geoJSON(
      gj,
      {

        style: {

          color: "#0057b8",

          weight: 1,

          fillColor: "#1683d8",

          fillOpacity: 0.55

        },


        onEachFeature:
          function(feature, polygonLayer) {

            const p =
              feature.properties || {};


            const scene =
              p.scene_id ||
              AI_FLOOD_SCENE;


            const floodClass =
              p.flood_class ??
              1;


            const polygonId =
              p.polygon_id ??
              "N/A";


            const area =
              p.area_degrees2 ??
              "N/A";


            polygonLayer.bindPopup(

              `
              <div
                style="
                  min-width:240px;
                  line-height:1.5;
                "
              >

                <strong>
                  AI Flood Inundation
                </strong>

                <hr
                  style="
                    margin:7px 0;
                    border:0;
                    border-top:1px solid #ddd;
                  "
                >

                <b>Scene:</b>
                ${scene}

                <br>

                <b>Model:</b>
                Random Forest

                <br>

                <b>Features:</b>
                12

                <br>

                <b>Threshold:</b>
                ${AI_FLOOD_THRESHOLD}

                <br>

                <b>Flood class:</b>
                ${floodClass}

                <br>

                <b>Polygon ID:</b>
                ${polygonId}

                <br>

                <b>Area:</b>
                ${area} degrees²

              </div>
              `

            );

          }

      }
    );


  return layer;

}


// ============================================================================
// AI RESULTS PANEL
// ============================================================================

async function loadAIFloodResults() {

  try {

    aiFloodResults =
      await loadJSON(
        AI_FLOOD_RESULTS
      );

    console.log(
      "AI flood results loaded:",
      aiFloodResults
    );

  }

  catch (error) {

    console.warn(
      "AI flood results JSON could not be loaded:",
      error.message
    );

    aiFloodResults = null;

  }

}


// ============================================================================
// CREATE AI RESULTS DISPLAY
// ============================================================================

function createAIResultsPanel() {

  if (!aiFloodResults) {
    return;
  }


  // Avoid duplicate panel
  if (
    document.getElementById(
      "ai-flood-results-panel"
    )
  ) {
    return;
  }


  const panel =
    document.createElement(
      "div"
    );


  panel.id =
    "ai-flood-results-panel";


  panel.style.cssText = `
    margin-top:12px;
    padding:14px;
    border:1px solid #d7dee5;
    border-radius:8px;
    background:#ffffff;
    box-shadow:0 2px 8px rgba(0,0,0,0.05);
  `;


  const validation =
    aiFloodResults.validation || {};


  panel.innerHTML = `

    <div
      style="
        display:flex;
        justify-content:space-between;
        align-items:center;
        margin-bottom:10px;
      "
    >

      <strong
        style="
          font-size:15px;
          color:#0b3350;
        "
      >
        AI Flood Inundation
      </strong>

      <span
        style="
          font-size:11px;
          padding:4px 7px;
          border-radius:12px;
          background:#e8f3ff;
          color:#0057b8;
        "
      >
        Random Forest
      </span>

    </div>


    <div
      style="
        font-size:12px;
        color:#56636d;
        margin-bottom:12px;
      "
    >

      Scene ${aiFloodResults.scene_id}
      ·
      ${aiFloodResults.features} features
      ·
      threshold ${aiFloodResults.threshold}

    </div>


    <div
      style="
        display:grid;
        grid-template-columns:
          repeat(2,minmax(0,1fr));
        gap:8px;
      "
    >

      <div>
        <small>Flood area</small>
        <strong>
          ${Number(
            aiFloodResults.flood_percentage
          ).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>Flood polygons</small>
        <strong>
          ${aiFloodResults.polygons}
        </strong>
      </div>


      <div>
        <small>Accuracy</small>
        <strong>
          ${(Number(
            validation.accuracy
          ) * 100).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>Precision</small>
        <strong>
          ${(Number(
            validation.precision
          ) * 100).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>Recall</small>
        <strong>
          ${(Number(
            validation.recall
          ) * 100).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>F1 score</small>
        <strong>
          ${(Number(
            validation.f1
          ) * 100).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>IoU</small>
        <strong>
          ${(Number(
            validation.iou
          ) * 100).toFixed(2)}%
        </strong>
      </div>


      <div>
        <small>False negative rate</small>
        <strong>
          ${(Number(
            validation.false_negative_rate
          ) * 100).toFixed(2)}%
        </strong>
      </div>

    </div>


    <div
      style="
        margin-top:12px;
        padding-top:10px;
        border-top:1px solid #edf0f2;
        font-size:11px;
        color:#687680;
      "
    >

      AI prediction is an analytical estimate.
      It should not be treated as an emergency
      evacuation boundary.

    </div>

  `;


  // Make the values visually consistent
  panel
    .querySelectorAll("small")
    .forEach((el) => {

      el.style.display =
        "block";

      el.style.color =
        "#74818a";

      el.style.marginBottom =
        "2px";

    });


  panel
    .querySelectorAll("strong")
    .forEach((el) => {

      if (
        !el.closest(
          "#ai-flood-results-panel > div:first-child"
        )
      ) {

        el.style.display =
          "block";

        el.style.fontSize =
          "15px";

        el.style.color =
          "#0b3350";

      }

    });


  // Add to layer panel
  const simpleEl =
    document.getElementById(
      "pub-layer-list-simple"
    );


  if (simpleEl) {

    simpleEl.parentElement
      ?.appendChild(panel);

  }

}


// ============================================================================
// CWC MONITORING STATIONS
// ============================================================================

async function addStations(m) {

  const gj =
    await loadJSON(
      "data/cwc_stations.geojson"
    );


  const group =
    (stationsGroup = L.layerGroup()).addTo(m);


  gj.features.forEach(
    (f) => {

      const p =
        f.properties;


      const [
        lon,
        lat
      ] =
        f.geometry.coordinates;


      const isFocus =
        p.is_focus_station;


      const marker =
        L.marker(
          [
            lat,
            lon
          ],
          {

            icon:
              markerIcon(
                isFocus
                  ? "#a4271f"
                  : "#8a97a0",

                isFocus
                  ? 13
                  : 8
              )

          }
        );


      marker.bindPopup(
        `
        <strong>
          ${p.name}
        </strong>
        <br>
        Monitoring station
        `
      );


      group.addLayer(
        marker
      );

    }
  );


  return group;

}


// ============================================================================
// STUDY AREA
// ============================================================================

async function addStudyArea(m) {

  const gj =
    await loadJSON(
      "data/naraj_aoi.geojson"
    );

  studyAreaGroup = L.geoJSON(
    gj,
    {

      style: {

        color:
          "#0b3350",

        weight:
          2,

        fillOpacity:
          0,

        dashArray:
          "6 4"

      }

    }
  ).addTo(m);

  return studyAreaGroup;

}


// ============================================================================
// HISTORICAL NDEM
// ============================================================================

const NDEM_FILE_MAP = {

  ndem_16aug:
    "data/ndem/ndem_16aug.geojson",

  ndem_18aug:
    "data/ndem/ndem_18aug.geojson",

  ndem_19aug:
    "data/ndem/ndem_19aug.geojson",

  ndem_21aug:
    "data/ndem/ndem_21aug.geojson"

};

const NDEM_STYLE = {

  color:
    "#c2760c",

  weight:
    1,

  fillColor:
    "#c2760c",

  fillOpacity:
    0.4

};

async function addNdemLayer(
  m,
  eventId
) {

  const file =
    NDEM_FILE_MAP[eventId] ||
    NDEM_FILE_MAP.ndem_18aug;


  const gj =
    await loadJSON(
      file
    );


  return L.geoJSON(
    gj,
    {

      style:
        NDEM_STYLE

    }
  );

}


// Swap the NDEM layer on the flood map when the selected event changes.
// The layer list checkbox state is preserved: if NDEM was visible it stays
// visible with the new event's extent; if hidden it stays hidden.
async function applyNdemEvent(eventId) {

  if (!map2) {
    return;
  }

  const file =
    NDEM_FILE_MAP[eventId];

  if (!file) {
    // No digitized government extent for this event (2021/2023/2024/2025
    // CWC-dataset events). Remove any stale layer from a previously
    // selected event so the map never shows the wrong date's flood mask.
    if (ndemLayer && map2.hasLayer(ndemLayer)) {
      map2.removeLayer(ndemLayer);
    }
    ndemLayer = null;
    if (layerRegistry) {
      layerRegistry.ndem = null;
    }
    const cbOff =
      document.getElementById("pub-simple-layer-4");
    if (cbOff) {
      cbOff.checked = false;
    }
    return;
  }

  const wasVisible =
    ndemLayer &&
    map2.hasLayer(ndemLayer);

  const next =
    await addNdemLayer(
      map2,
      eventId
    );

  if (ndemLayer) {
    map2.removeLayer(ndemLayer);
  }

  ndemLayer =
    next;

  layerRegistry.ndem =
    next;

  if (wasVisible) {
    next.addTo(map2);
  }

  // Refresh the simple-layer checkbox binding so toggles still target the
  // live layer (registry entry was replaced above).
  const cb =
    document.getElementById(
      "pub-simple-layer-4"
    );

  if (cb) {
    cb.checked =
      wasVisible;
  }

}


// ---------------------------------------------------------------------------
// SATELLITE (SAR) IMAGE STATE
// ---------------------------------------------------------------------------

function sarImagePath(kind, polarization) {
  const pol =
    polarization === "vh" ? "vh" : "vv";
  const fileMap = {
    before: "preflood_" + pol + ".png",
    during: "duringflood_" + pol + ".png",
    change: "change_combined.png",
    candidate: "candidate_overlay_composite.png"
  };
  return SAR_IMAGE_BASE + fileMap[kind];
}

function escapeHtmlText(value) {
  if (typeof escapeHtml === "function") {
    return escapeHtml(value);
  }
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function applySarImages(polarization) {
  satImageState.polarization =
    polarization === "vh" ? "vh" : "vv";

  const ids = [
    "sat-img-before",
    "sat-img-during"
  ];

  ids.forEach((id) => {
    const img =
      document.getElementById(id);
    if (!img) return;
    const kind =
      id === "sat-img-before" ? "before" : "during";
    img.src =
      sarImagePath(kind, satImageState.polarization);
  });

  // Also mark the date labels with the polarization so the state is obvious.
  const lblBefore =
    document.getElementById("sat-date-before");
  const lblDuring =
    document.getElementById("sat-date-during");
  if (lblBefore) {
    lblBefore.textContent =
      (satImageState.dates && satImageState.dates.before
        ? satImageState.dates.before + " · "
        : "") + satImageState.polarization.toUpperCase();
  }
  if (lblDuring) {
    lblDuring.textContent =
      (satImageState.dates && satImageState.dates.during
        ? satImageState.dates.during + " · "
        : "") + satImageState.polarization.toUpperCase();
  }
}

async function setSatelliteEventStatus(eventId) {
  // Read the event and update the "satellite evidence" status banner + dates.
  const banner =
    document.getElementById("sat-event-status");
  const evt =
    eventsData &&
    eventsData.events.find((e) => e.id === eventId);
  if (!evt) return;

  if (banner) {
    const sat = evt.satellite_evidence || {};
    const ok = sat.status === "OBSERVED";
    banner.className =
      "sat-event-banner " +
      (ok ? "sat-event-ok" : "sat-event-warn");
    banner.innerHTML =
      (ok ? "✓ SAR coverage for this event" : "⚠ No SAR coverage for this event") +
      " — " +
      escapeHtmlText(sat.detail || "No Sentinel-1 acquisition for this date.");
  }

  // Keep polarization images in sync when the event changes.
  applySarImages(satImageState.polarization);
}

// ---------------------------------------------------------------------------
// EVENT SELECTOR (used by event picker + past-floods list)
// ---------------------------------------------------------------------------

function selectEvent(eventId) {
  if (
    !eventsData ||
    !eventsData.events.some((e) => e.id === eventId)
  ) {
    return;
  }

  currentEventId =
    eventId;

  const picker =
    document.getElementById("pub-event-picker");
  if (picker) {
    picker.value =
      eventId;
  }

  // Keep the past-floods list highlight in sync.
  document
    .querySelectorAll(".pub-past-flood-item")
    .forEach((el) => {
      el.classList.toggle(
        "active",
        el.dataset.eventId === eventId
      );
    });

  renderSituationCards();
  setSatelliteEventStatus(eventId);

  applyNdemEvent(eventId).catch((err) =>
    console.error("NDEM swap failed:", err)
  );
}



// ============================================================================
// STUDY-REGION LAYER TOGGLES
// ============================================================================

// Sync the Flood Map simple-layer checkboxes when study layers are toggled
// programmatically (e.g. hidden by default on the India-wide view).
function syncStudyLayerToggles(on) {
  ["pub-simple-layer-0", "pub-simple-layer-1", "pub-simple-layer-2", "pub-simple-layer-3"]
    .forEach((id) => {
      const cb = document.getElementById(id);
      if (cb) cb.checked = on;
    });
}

// ============================================================================
// OVERVIEW MAP
// ============================================================================

async function initOverviewMap() {

  map1 =
    makeMap(
      "pub-map"
    );


  await addStudyArea(
    map1
  );


  await addStations(
    map1
  );


  await addCandidateMask(
    map1
  );

  // Study-region layers are clearly-labelled historical study data; they are
  // optional context and start hidden so the India-wide view is neutral.
  [studyAreaGroup, stationsGroup, candidateGroup].forEach((g) => {
    if (g && map1.hasLayer(g)) map1.removeLayer(g);
  });
  syncStudyLayerToggles(false);
}


// ============================================================================
// ADVANCED LAYERS
// ============================================================================

let advancedLayersOnMap2 = {};


// ============================================================================
// FLOOD MAP
// ============================================================================

async function initFloodMap() {

  map2 =
    makeMap(
      "pub-map-2"
    );


  const layers =
    await loadJSON(
      "data/layers.json"
    );


  const studyArea =
    await addStudyArea(
      map2
    );


  const stations =
    await addStations(
      map2
    );


  const candidate =
    await addCandidateMask(
      map2
    );

  // India-wide default: build the study-region layers (so toggles work) but
  // keep them OFF the map until the user enables them.
  [studyAreaGroup, stationsGroup, candidateGroup].forEach((g) => {
    if (g && map2.hasLayer(g)) map2.removeLayer(g);
  });


  // ========================================================================
  // AI FLOOD
  // ========================================================================

  let aiFlood = null;


  try {

    aiFlood =
      await addAIFloodLayer(
        map2
      );

    console.log(
      "AI flood layer ready."
    );

  }

  catch (err) {

    console.error(
      "AI flood layer failed:",
      err
    );

  }


  // ========================================================================
  // NDEM
  // ========================================================================

  const ndem =
    await addNdemLayer(
      map2,
      currentEventId
    );


  // NDEM is built (so event swaps work) but NOT added by default — the
  // default flood-map view is the neutral India-wide base map. The user can
  // toggle the historical study-region layer on from the layer list.
  ndemLayer = ndem;
  layerRegistry.ndem = ndem;


  // ========================================================================
  // SIMPLE LAYERS
  // ========================================================================

  const simpleEl =
    document.getElementById(
      "pub-layer-list-simple"
    );


  if (!simpleEl) {
    return;
  }


  simpleEl.innerHTML = "";


  const simpleDefs = [

    {
      label:
        "Study area: potentially affected area (Aug 2022)",

      layer:
        candidate,

      checked:
        false
    },

    {
      label:
        "Study area: AI flood inundation (scene 1017769)",

      layer:
        aiFlood,

      checked:
        false
    },

    {
      label:
        "Study area: CWC monitoring stations",

      layer:
        stations,

      checked:
        false
    },

    {
      label:
        "Study area: boundary (Mahanadi AOI)",

      layer:
        studyArea,

      checked:
        false
    },

    {
      label:
        "Historical flood extent (reference)",

      // Resolved dynamically so event swaps stay in sync.
      layer:
        () => layerRegistry.ndem,

      checked:
        true
    }

  ];


  simpleDefs.forEach(
    (d, i) => {

      const row =
        document.createElement(
          "div"
        );


      row.className =
        "pub-layer-row";


      const cb =
        document.createElement(
          "input"
        );


      cb.type =
        "checkbox";


      cb.checked =
        d.checked;


      cb.id =
        `pub-simple-layer-${i}`;


      cb.addEventListener(
        "change",
        () => {

          const layer =
            typeof d.layer === "function"
              ? d.layer()
              : d.layer;

          if (!layer) {
            return;
          }


          if (cb.checked) {

            layer.addTo(
              map2
            );

          }

          else {

            map2.removeLayer(
              layer
            );

          }

        }
      );


      const label =
        document.createElement(
          "label"
        );


      label.htmlFor =
        cb.id;


      label.textContent =
        d.label;


      row.appendChild(
        cb
      );


      row.appendChild(
        label
      );


      simpleEl.appendChild(
        row
      );

    }
  );


  // ========================================================================
  // AI SCENE BUTTON
  // ========================================================================

  const aiSceneButton =
    document.createElement(
      "button"
    );


  aiSceneButton.type =
    "button";


  aiSceneButton.textContent =
    "Go to AI scene 1017769";


  aiSceneButton.style.cssText = `
    margin:8px 0;
    padding:7px 10px;
    border:1px solid #0057b8;
    border-radius:5px;
    background:white;
    color:#0057b8;
    cursor:pointer;
  `;


  aiSceneButton.addEventListener(
    "click",
    () => {

      if (aiFlood) {

        aiFlood.addTo(
          map2
        );

      }


      const aiCheckbox =
        document.getElementById(
          "pub-simple-layer-1"
        );


      if (aiCheckbox) {
        aiCheckbox.checked =
          true;
      }


      map2.fitBounds(
        AI_FLOOD_BOUNDS,
        {
          padding:
            [20, 20]
        }
      );

    }
  );


  simpleEl.appendChild(
    aiSceneButton
  );


  // ========================================================================
  // AI RESULTS
  // ========================================================================

  createAIResultsPanel();


  // ========================================================================
  // ADVANCED LAYERS
  // ========================================================================

  const advancedEl =
    document.getElementById(
      "pub-layer-list-advanced"
    );


  if (!advancedEl) {
    return;
  }


  const advancedLabels = {

    dem:
      "Elevation map",

    s1_06aug_footprint:
      "Satellite coverage area (6 Aug)",

    s1_18aug_footprint:
      "Satellite coverage area (18 Aug)",

    sar_preflood_vv:
      "Satellite image — before flood",

    sar_duringflood_vv:
      "Satellite image — during flood",

    sar_change:
      "Surface change map",

    sar_valid_coverage:
      "Area with satellite coverage",

    sar_ndem_agreement:
      "Comparison with historical record"

  };


  const advancedIds =
    Object.keys(
      advancedLabels
    );


  advancedEl.innerHTML =
    "";


  for (
    const id
    of advancedIds
  ) {

    const cfg =
      layers.find(
        (l) =>
          l.id === id
      );


    if (
      !cfg ||
      !cfg.file
    ) {
      continue;
    }


    const row =
      document.createElement(
        "div"
      );


    row.className =
      "pub-layer-row";


    const cb =
      document.createElement(
        "input"
      );


    cb.type =
      "checkbox";


    cb.id =
      `pub-adv-layer-${id}`;


    const label =
      document.createElement(
        "label"
      );


    label.htmlFor =
      cb.id;


    label.textContent =
      advancedLabels[id];


    row.appendChild(
      cb
    );


    row.appendChild(
      label
    );


    advancedEl.appendChild(
      row
    );


    cb.addEventListener(
      "change",
      async () => {

        if (
          !advancedLayersOnMap2[id]
        ) {

          if (
            cfg.type ===
            "geojson"
          ) {

            const gj =
              await loadJSON(
                cfg.file
              );


            advancedLayersOnMap2[id] =
              L.geoJSON(
                gj,
                {

                  style:
                    () =>
                      cfg.style ||
                      {}

                }
              );

          }


          else if (
            cfg.type ===
            "image_overlay"
          ) {

            const b =
              await loadJSON(
                cfg.bounds_file
              );


            advancedLayersOnMap2[id] =
              L.imageOverlay(
                cfg.file,

                [
                  [
                    b.bounds.south,
                    b.bounds.west
                  ],

                  [
                    b.bounds.north,
                    b.bounds.east
                  ]
                ],

                {
                  opacity:
                    0.65
                }
              );

          }

        }


        if (cb.checked) {

          advancedLayersOnMap2[id]
            ?.addTo(map2);

        }

        else if (
          advancedLayersOnMap2[id]
        ) {

          map2.removeLayer(
            advancedLayersOnMap2[id]
          );

        }

      }
    );

  }


  // ========================================================================
  // MORE LAYERS
  // ========================================================================

  const moreLayersButton =
    document.getElementById(
      "pub-more-layers-btn"
    );


  if (moreLayersButton) {

    moreLayersButton.addEventListener(
      "click",
      () => {

        advancedEl.classList.toggle(
          "hidden"
        );

      }
    );

  }


  // ========================================================================
  // WHAT AM I LOOKING AT?
  // ========================================================================

  const whatAmIButton =
    document.getElementById(
      "pub-whatami-btn-2"
    );


  if (whatAmIButton) {

    whatAmIButton.addEventListener(
      "click",
      () => {

        const rows = [];


        const sarCheckbox =
          document.getElementById(
            "pub-simple-layer-0"
          );


        const aiCheckbox =
          document.getElementById(
            "pub-simple-layer-1"
          );


        const stationCheckbox =
          document.getElementById(
            "pub-simple-layer-2"
          );


        const boundaryCheckbox =
          document.getElementById(
            "pub-simple-layer-3"
          );


        const historicalCheckbox =
          document.getElementById(
            "pub-simple-layer-4"
          );


        if (sarCheckbox?.checked) {

          rows.push({

            color:
              "#a4271f",

            title:
              "Potential flood area",

            text:
              "Areas highlighted by the Sentinel-1 SAR flood analysis as potentially affected."

          });

        }


        if (aiCheckbox?.checked) {

          rows.push({

            color:
              "#1683d8",

            title:
              "AI flood inundation",

            text:
              "Spatial flood areas predicted by the Random Forest model using 12 features."

          });

        }


        if (stationCheckbox?.checked) {

          rows.push({

            color:
              "#8a97a0",

            title:
              "Monitoring station",

            text:
              "Locations where river water levels are recorded."

          });

        }


        if (boundaryCheckbox?.checked) {

          rows.push({

            color:
              "white",

            border:
              "#0b3350",

            title:
              "Study area boundary",

            text:
              "The area currently covered by this demonstration."

          });

        }


        if (historicalCheckbox?.checked) {

          rows.push({

            color:
              "#c2760c",

            title:
              "Historical flood extent",

            text:
              "Previously recorded inundated areas from the official reference record."

          });

        }


        if (
          document.getElementById(
            "pub-adv-layer-dem"
          )?.checked
        ) {

          rows.push({

            color:
              "#7fae7f",

            title:
              "Terrain",

            text:
              "Relative land elevation shown on the map."

          });

        }


        if (!rows.length) {

          rows.push({

            color:
              "#d3d1c7",

            title:
              "No layers turned on",

            text:
              "Turn on a layer from the Map layers list."

          });

        }


        showWhatAmI(
          rows
        );

      }
    );

  }

}


// ============================================================================
// WHAT AM I
// ============================================================================

function initWhatAmI() {

  const button =
    document.getElementById(
      "pub-whatami-btn"
    );


  if (!button) {
    return;
  }


  button.addEventListener(
    "click",
    () => {

      showWhatAmI([

        {

          color:
            "#a4271f",

          title:
            "Potential flood area",

          text:
            "Areas highlighted by the flood analysis as potentially affected."

        },

        {

          color:
            "#1683d8",

          title:
            "AI flood inundation",

          text:
            "Flood areas predicted by the Random Forest inundation model."

        },

        {

          color:
            "#8a97a0",

          title:
            "Monitoring station",

          text:
            "Locations where river water levels are recorded."

        },

        {

          color:
            "white",

          border:
            "#0b3350",

          title:
            "Study area boundary",

          text:
            "The area currently covered by this demonstration."

        }

      ]);

    }
  );

}


// ============================================================================
// WHAT AM I MODAL
// ============================================================================

function showWhatAmI(rows) {

  const backdrop =
    document.createElement(
      "div"
    );


  backdrop.className =
    "whatami-modal-backdrop";


  const rowsHtml =
    rows
      .map(
        (r) => `
          <div
            class="whatami-legend-row"
          >

            <span
              class="whatami-swatch"
              style="
                background:${r.color};
                ${
                  r.border
                    ? `border:2px solid ${r.border};`
                    : ""
                }
              "
            ></span>

            <span>

              <strong>
                ${r.title}
              </strong>

              <br>

              ${r.text}

            </span>

          </div>
        `
      )
      .join("");


  backdrop.innerHTML = `

    <div
      class="whatami-modal"
    >

      <h3>
        What am I looking at?
      </h3>

      ${rowsHtml}

      <button
        class="whatami-close-btn"
      >
        Got it
      </button>

    </div>

  `;


  document.body.appendChild(
    backdrop
  );


  backdrop
    .querySelector(
      ".whatami-close-btn"
    )
    .addEventListener(
      "click",
      () =>
        backdrop.remove()
    );


  backdrop.addEventListener(
    "click",
    (e) => {

      if (
        e.target ===
        backdrop
      ) {

        backdrop.remove();

      }

    }
  );

}


// ============================================================================
// INFO ICON
// ============================================================================

function attachInfoIcon(
  container,
  text
) {

  const icon =
    document.createElement(
      "span"
    );


  icon.className =
    "info-icon";


  icon.textContent =
    "i";


  const pop =
    document.createElement(
      "div"
    );


  pop.className =
    "info-popover";


  pop.textContent =
    text;


  icon.addEventListener(
    "click",
    () => {

      pop.classList.toggle(
        "open"
      );

    }
  );


  container.appendChild(
    icon
  );


  return pop;

}


// ============================================================================
// EVENTS
// ============================================================================

let eventsData = null;

let currentEventId =
  "ndem_18aug";

let maskParams = null;


async function loadSharedData() {

  // All-years event register: 21 events derived from the real CWC dataset
  // (Hugging Face bhoomig0630/flood-inundation-upload, 2021-2025) plus the
  // 4 satellite-verified NDEM events of August 2022. Falls back to the
  // original 2022-only file when the all-years file is missing.
  try {
    eventsData =
      await loadJSON(
        "data/events_all_years.json"
      );
  } catch (err) {
    console.warn("All-years events unavailable, falling back to 2022 file:", err.message);
    eventsData =
      await loadJSON(
        "data/events_august2022.json"
      );
  }


  maskParams =
    await loadJSON(
      "data/sar_flood/candidate_mask_params.json"
    );

}


// ============================================================================
// EVENT PICKER
// ============================================================================

function populateEventPicker() {

  const sel =
    document.getElementById(
      "pub-event-picker"
    );


  if (!sel) {
    return;
  }


  sel.innerHTML =
    "";


  eventsData.events.forEach(
    (evt) => {

      const opt =
        document.createElement(
          "option"
        );


      opt.value =
        evt.id;


      const lvl = evt.cwc_observed.water_level_m;
      opt.textContent =
        evt.date + "  —  peak " + lvl.toFixed(2) + " m";


      sel.appendChild(
        opt
      );

    }
  );


  sel.value =
    currentEventId;


  sel.addEventListener(
    "change",
    () => {

      selectEvent(
        sel.value
      );

    }
  );

}


// ============================================================================
// SITUATION CARDS
// ============================================================================

function renderSituationCards() {

  const evt =
    eventsData.events.find(
      (e) =>
        e.id ===
        currentEventId
    );


  if (!evt) {
    return;
  }


  // CWC-dataset events (2021-2025) carry a `source: "cwc_dataset"` marker and
  // a `hydrology` block; the four NDEM events keep their satellite-derived
  // mask. Guard every lookup so a missing block never breaks rendering.
  const isVerified =
    evt.source === "ndem_verified";
  const hasMask =
    !!(
      evt.flood_mask_sar_derived &&
      evt.flood_mask_sar_derived.status === "DERIVED"
    );
  const hydro = evt.hydrology || {};


  const el =
    document.getElementById(
      "pub-situation-cards"
    );


  if (!el) {
    return;
  }


  el.innerHTML =
    "";


  const cards = [

    {

      label:
        "Selected Event",

      value:
        evt.date,

      sub:
        "",

      info:
        "The flood date currently being explored."

    },

    {

      label:
        "River Water Level",

      value:
        `${evt.cwc_observed.water_level_m} m`,

      sub:
        `Recorded ${
          (evt.cwc_observed.nearest_reading_time || evt.date).slice(0, 10)
        }`,

      info:
        "Recorded water level at Naraj. Danger level 24.28 m = 95th percentile " +
        "of the 2021-2025 CWC record."

    },

    {

      label:
        "Rainfall / Rise",

      value:
        isVerified
          ? "—"
          : `${hydro.max_24h_rainfall_mm != null ? hydro.max_24h_rainfall_mm : "—"} mm · +${
              hydro.max_hourly_rise_m != null ? hydro.max_hourly_rise_m : "—"
            } m`,

      sub:
        isVerified
          ? "Not derived for verified events"
          : "Max 24h basin rainfall · max hourly rise",

      info:
        "From the same real CWC dataset the forecast models train on."

    },

    {

      label:
        "Satellite Observation",

      value:
        evt.satellite_evidence.status ===
        "OBSERVED"
          ? "Surface change detected"
          : "Not available for this date",

      sub:
        evt.satellite_evidence.status ===
        "OBSERVED"
          ? "Pre-event vs during-event comparison"
          : "",

      info:
        "Radar satellite images from before and during the event were compared."

    },

    {

      label:
        "Potentially Affected Area",

      value:
        hasMask
          ? `${maskParams.final_candidate_area_km2.toFixed(2)} km²`
          : "N/A for this date",

      sub:
        hasMask
          ? "Based on satellite comparison"
          : "",

      info:
        "Areas identified by the analysis as potentially inundated.",

      highlight:
        true

    },

    {

      label:
        "Historical Flood Data",

      value:
        evt.ndem_inundation.available
          ? "Available"
          : "Not available",

      sub:
        evt.ndem_inundation.available
          ? "Official flood record"
          : "",

      info:
        "An official historical flood record exists for this date."

    }

  ];


  cards.forEach(
    (c) => {

      const card =
        document.createElement(
          "div"
        );


      card.className =
        "pub-sit-card" +
        (
          c.highlight
            ? " highlight"
            : ""
        );


      const labelRow =
        document.createElement(
          "div"
        );


      labelRow.className =
        "pub-sit-label";


      labelRow.textContent =
        c.label;


      card.appendChild(
        labelRow
      );


      const value =
        document.createElement(
          "div"
        );


      value.className =
        "pub-sit-value";


      value.textContent =
        c.value;


      card.appendChild(
        value
      );


      if (c.sub) {

        const sub =
          document.createElement(
            "div"
          );


        sub.className =
          "pub-sit-sub";


        sub.textContent =
          c.sub;


        card.appendChild(
          sub
        );

      }


      const pop =
        attachInfoIcon(
          labelRow,
          c.info
        );


      card.appendChild(
        pop
      );


      el.appendChild(
        card
      );

    }
  );

}


// ============================================================================
// WATER LEVELS
// ============================================================================

const STATION_FILE_KEY = {

  Naraj:
    "naraj",

  Alipingal:
    "alipingal",

  Nimapara:
    "nimapara"

};


let pubWlChart = null;


async function initWaterLevels() {

  const stationsGj =
    await loadJSON(
      "data/cwc_stations.geojson"
    );


  const focusStations =
    stationsGj.features
      .filter(
        (f) =>
          f.properties
            .is_focus_station
      )
      .map(
        (f) =>
          f.properties.name
      );


  const chipsEl =
    document.getElementById(
      "pub-station-chips"
    );


  if (!chipsEl) {
    return;
  }


  chipsEl.innerHTML =
    "";


  focusStations.forEach(
    (
      name,
      i
    ) => {

      const chip =
        document.createElement(
          "div"
        );


      chip.className =
        "pub-station-chip" +
        (
          i === 0
            ? " active"
            : ""
        );


      chip.textContent =
        name;


      chip.addEventListener(
        "click",
        () => {

          document
            .querySelectorAll(
              ".pub-station-chip"
            )
            .forEach(
              (c) =>
                c.classList.remove(
                  "active"
                )
            );


          chip.classList.add(
            "active"
          );


          renderWaterLevelChart(
            name
          );

        }
      );


      chipsEl.appendChild(
        chip
      );

    }
  );


  if (focusStations.length) {

    renderWaterLevelChart(
      focusStations[0]
    );

  }

}


async function renderWaterLevelChart(
  name
) {

  const fileKey =
    STATION_FILE_KEY[name];


  if (!fileKey) {
    return;
  }


  const data =
    await loadJSON(
      `data/cwc/${fileKey}_daily_2021_2025.json`
    );


  const labels =
    data.records.map(
      (r) =>
        r.date
    );


  const values =
    data.records.map(
      (r) =>
        r.water_level_m
    );


  if (pubWlChart) {
    pubWlChart.destroy();
  }


  const canvas =
    document.getElementById(
      "pub-wl-chart"
    );


  if (!canvas) {
    return;
  }


  pubWlChart =
    new Chart(
      canvas,
      {

        type:
          "line",

        data: {

          labels,

          datasets: [

            {

              label:
                `${name} water level (m)`,

              data:
                values,

              borderColor:
                "#0f6b78",

              backgroundColor:
                "rgba(15,107,120,0.08)",

              borderWidth:
                1.3,

              pointRadius:
                0,

              fill:
                true

            }

          ]

        },

        options: {

          responsive:
            true,

          plugins: {

            legend: {

              display:
                false

            }

          },

          scales: {

            x: {

              ticks: {

                maxTicksLimit:
                  6,

                font: {

                  size:
                    10

                }

              },

              grid: {

                display:
                  false

              }

            },

            y: {

              title: {

                display:
                  true,

                text:
                  "meters",

                font: {

                  size:
                    11

                }

              }

            }

          }

        }

      }
    );


  const caption =
    document.getElementById(
      "pub-wl-caption"
    );


  if (caption) {

    caption.textContent =
      `Recorded water levels at ${name}, 2021–2025.`;

  }

}


// ============================================================================
// SAR LIGHTBOX (click-to-zoom)
// ============================================================================

function openSarLightbox(src, alt) {
  let lb = document.getElementById("sar-lightbox");
  if (!lb) {
    lb = document.createElement("div");
    lb.id = "sar-lightbox";
    lb.className = "sar-lightbox hidden";
    lb.setAttribute("role", "dialog");
    lb.setAttribute("aria-modal", "true");
    lb.innerHTML =
      '<button class="sar-lightbox-close" aria-label="Close">&#10005;</button>' +
      '<img class="sar-lightbox-img" alt="" />' +
      '<div class="sar-lightbox-caption"></div>';
    document.body.appendChild(lb);
    lb.addEventListener("click", (e) => {
      if (e.target === lb || e.target.closest(".sar-lightbox-close")) {
        lb.classList.add("hidden");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") lb.classList.add("hidden");
    });
  }
  const img = lb.querySelector(".sar-lightbox-img");
  const cap = lb.querySelector(".sar-lightbox-caption");
  if (img) {
    img.src = src;
    img.alt = alt || "SAR image";
  }
  if (cap) cap.textContent = alt || "";
  lb.classList.remove("hidden");
}


// ============================================================================
// INDIA STATIONS EXPLORER (pan-India CWC gauge registry)
// ============================================================================

let indiaStationsData = null;
let indiaMap = null;
let indiaMarkers = null;
let indiaSelected = null;
let indiaFilters = { q: "", basin: "all", state: "all", availability: "all", maxDistanceKm: "all" };

async function initIndiaStations() {

  const mapEl = document.getElementById("india-map");
  if (!mapEl || indiaMap) return;

  // Real India-wide CWC registry (built from the actual CWC CSVs by
  // scripts/build_india_registry.py). Falls back to the curated registry
  // when the built one is absent.
  try {
    indiaStationsData = await loadJSON("data/india_cwc/stations.json");
  } catch (err) {
    console.warn("India CWC registry unavailable, falling back:", err);
    indiaStationsData = await loadJSON("data/india_stations.json");
  }

  indiaMap = L.map("india-map", { zoomControl: true }).setView([22.5, 80], 4);

  L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { attribution: "&copy; OpenStreetMap contributors" }
  ).addTo(indiaMap);

  indiaMarkers = L.layerGroup().addTo(indiaMap);

  renderIndiaFilters();
  renderIndiaList();

  const search = document.getElementById("india-search");
  if (search) {
    search.addEventListener("input", () => {
      indiaFilters.q = search.value.trim().toLowerCase();
      renderIndiaList();
    });
  }

  const typeSel = document.getElementById("india-type");
  if (typeSel) {
    indiaFilters.type = "all";
    typeSel.addEventListener("change", () => {
      indiaFilters.type = typeSel.value;
      renderIndiaList();
    });
  }

  const stateSel = document.getElementById("india-state");
  if (stateSel) {
    stateSel.addEventListener("change", () => {
      indiaFilters.state = stateSel.value;
      renderIndiaList();
    });
  }

  const availSel = document.getElementById("india-availability");
  if (availSel) {
    availSel.addEventListener("change", () => {
      indiaFilters.availability = availSel.value;
      renderIndiaList();
    });
  }

  const distSel = document.getElementById("india-distance");
  if (distSel) {
    distSel.addEventListener("change", () => {
      indiaFilters.maxDistanceKm = distSel.value;
      renderIndiaList();
    });
  }

  const nearBtn = document.getElementById("india-near-me");
  if (nearBtn) {
    nearBtn.addEventListener("click", () => {
      const sel =
        window.FloodWatchState && window.FloodWatchState.selectedLocation;
      if (!sel) {
        alert("Select a location first (search, Use My Location, or map click).");
        return;
      }
      indiaFilters.near = { lat: sel.latitude, lon: sel.longitude };
      renderIndiaList();
    });
  }

  // Re-sort/re-render when the selected location changes (keeps the
  // distance column honest without a full pane reload).
  if (
    window.FloodWatchState &&
    typeof window.FloodWatchState.onLocationChange === "function"
  ) {
    window.FloodWatchState.onLocationChange(() => {
      if (!indiaStationsData || !indiaMap) return;
      if (indiaFilters.near || indiaFilters.maxDistanceKm !== "all") {
        const sel =
          window.FloodWatchState && window.FloodWatchState.selectedLocation;
        if (sel) {
          indiaFilters.near = { lat: sel.latitude, lon: sel.longitude };
          renderIndiaList();
        }
      }
    });
  }

  // Re-render the map when its pane becomes visible (Leaflet needs layout).
  const btn = document.querySelector('.pub-nav-btn[data-pubtab="india"]');
  if (btn) {
    btn.addEventListener("click", () => {
      setTimeout(() => {
        if (indiaMap) indiaMap.invalidateSize();
      }, 60);
    });
  }
}

function indiaDistanceKm(s) {
  const near = indiaFilters.near;
  if (!near) return null;
  return indiaDistanceKmFrom(near, s);
}

function indiaDistanceKmFrom(from, s) {
  if (!from || s.latitude == null || s.longitude == null) return null;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(s.latitude - from.lat);
  const dLon = toRad(s.longitude - from.lon);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(from.lat)) * Math.cos(toRad(s.latitude)) * Math.sin(dLon / 2) ** 2;
  return Math.round(6371.0 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)) * 10) / 10;
}

function indiaFilteredStations() {
  if (!indiaStationsData) return [];
  let stations = indiaStationsData.stations.filter((s) => {
    if (indiaFilters.type && indiaFilters.type !== "all" && s.kind !== indiaFilters.type) return false;
    if (indiaFilters.state !== "all" && s.state !== indiaFilters.state) return false;
    if (indiaFilters.q) {
      const hay = (s.station + " " + (s.river || "") + " " + (s.basin || "") + " " + s.state + " " + (s.district || "")).toLowerCase();
      if (!hay.includes(indiaFilters.q)) return false;
    }
    // Data-availability filter (real observation presence / recency).
    if (indiaFilters.availability === "with-obs" && !s.latest_observation) return false;
    if (indiaFilters.availability === "recent") {
      if (!s.last_obs || !indiaStationsData.generated_at) return false;
      // "Recent" is relative to the registry build — the honest reference
      // point we have (the CSVs are a historical export, not a live feed).
      const ageDays =
        (new Date(indiaStationsData.generated_at).getTime() -
          new Date(s.last_obs).getTime()) / 86400000;
      if (!(ageDays >= -1 && ageDays <= 10)) return false;
    }
    return true;
  });

  // Distance filter requires a selected location; applied after computing
  // per-station distances when either filter or sort needs them.
  const needsDistance =
    indiaFilters.near || indiaFilters.maxDistanceKm !== "all";
  if (needsDistance) {
    const sel =
      window.FloodWatchState && window.FloodWatchState.selectedLocation;
    if (sel) {
      indiaFilters.near = indiaFilters.near || {
        lat: sel.latitude,
        lon: sel.longitude,
      };
    }
  }
  if (indiaFilters.maxDistanceKm !== "all") {
    const maxKm = Number(indiaFilters.maxDistanceKm);
    stations = stations.filter((s) => {
      if (s.distance_km == null) {
        const sel =
          window.FloodWatchState && window.FloodWatchState.selectedLocation;
        if (!sel) return false;
        s.distance_km = indiaDistanceKmFrom(sel, s);
      }
      return s.distance_km <= maxKm;
    });
  }
  if (indiaFilters.near) {
    stations = stations
      .map((s) => Object.assign({}, s, { distance_km: indiaDistanceKm(s) }))
      .sort((a, b) => a.distance_km - b.distance_km);
  }
  return stations;
}

function renderIndiaFilters() {
  if (!indiaStationsData) return;
  const kinds = [...new Set(indiaStationsData.stations.map((s) => s.kind))].filter(Boolean);
  const states = [...new Set(indiaStationsData.stations.map((s) => s.state))].sort();

  const typeSel = document.getElementById("india-type");
  if (typeSel && !typeSel.options.length) {
    typeSel.innerHTML =
      '<option value="all">All types</option>' +
      kinds.map((k) => '<option value="' + k + '">' + (k === "river" ? "River discharge" : "Rainfall") + "</option>").join("");
  }
  const stateSel = document.getElementById("india-state");
  if (stateSel) {
    stateSel.innerHTML =
      '<option value="all">All states</option>' +
      states.map((s) => '<option value="' + s + '">' + s + "</option>").join("");
  }
}

function renderIndiaList() {
  const list = document.getElementById("india-station-list");
  const countEl = document.getElementById("india-count");
  if (!list) return;

  const all = indiaStationsData ? indiaStationsData.stations : [];
  const stations = indiaFilteredStations().slice(0, 400); // DOM cap; filters narrow further
  if (countEl) {
    countEl.textContent =
      indiaFilteredStations().length + " of " + all.length + " stations" +
      (indiaFilters.near ? " (sorted by distance)" : "");
  }

  indiaMarkers.clearLayers();

  list.innerHTML = stations
    .map((s, i) => {
      const obs = s.latest_observation;
      const obsTxt = obs
        ? obs.value + " " + (obs.unit || "") + " · " + String(obs.time || "").slice(0, 10)
        : "no valid observation in dataset";
      return (
        '<div class="india-station-item' +
        (indiaSelected === s.station + "|" + s.latitude ? " active" : "") +
        '" data-idx="' + i + '">' +
        '<div class="india-station-name">' + s.station + "</div>" +
        '<div class="india-station-meta">' +
          (s.kind === "river" ? "🌊 " : "🌧 ") +
          ((s.river && s.river !== "-") ? s.river + " · " : "") + s.state +
          (s.distance_km != null ? " · " + s.distance_km + " km" : "") +
        "</div>" +
        '<div class="india-station-flag">' + obsTxt + "</div>" +
        "</div>"
      );
    })
    .join("");

  list.querySelectorAll(".india-station-item").forEach((el) => {
    el.addEventListener("click", () => focusIndiaStation(Number(el.dataset.idx)));
  });

  stations.forEach((s) => {
    const isRiver = s.kind === "river";
    const color = isRiver ? "#0f6b78" : "#c2760c";
    const marker = L.circleMarker([s.latitude, s.longitude], {
      radius: s.has_observation === false ? 4 : 5,
      color: "#ffffff",
      weight: 1.2,
      fillColor: color,
      fillOpacity: 0.9,
    });
    const obs = s.latest_observation;
    marker.bindPopup(
      "<strong>" + s.station + "</strong><br>" +
      (s.kind === "river" ? "River discharge" : "Rainfall") +
      ((s.river && s.river !== "-") ? " · " + s.river : "") +
      (s.district ? " · " + s.district : "") + "<br>" + s.state +
      (s.distance_km != null ? "<br>" + s.distance_km + " km from selected location" : "") +
      (obs
        ? "<br>Latest: " + obs.value + " " + (obs.unit || "") +
          " · " + String(obs.time || "").replace("T", " ").slice(0, 16) + " UTC"
        : "<br>No valid observation in the real dataset")
    );
    marker.on("click", () => focusIndiaStation(stations.indexOf(s), false));
    indiaMarkers.addLayer(marker);
  });
}

function focusIndiaStation(idx, fly) {
  if (!indiaStationsData) return;
  const stations = indiaFilteredStations();
  const s = stations[idx];
  if (!s) return;

  indiaSelected = s.station + "|" + s.latitude;

  const panel = document.getElementById("india-station-detail");
  if (panel) {
    const obs = s.latest_observation;
    panel.innerHTML =
      '<h4>' + s.station + "</h4>" +
      '<div class="india-detail-row"><strong>Type:</strong> ' +
      (s.kind === "river" ? "River water discharge" : "Rainfall (telemetry)") + "</div>" +
      ((s.river && s.river !== "-")
        ? '<div class="india-detail-row"><strong>River:</strong> ' + s.river + "</div>"
        : "") +
      ((s.basin && s.basin !== "-")
        ? '<div class="india-detail-row"><strong>Basin:</strong> ' + s.basin + "</div>"
        : "") +
      '<div class="india-detail-row"><strong>State:</strong> ' + s.state +
      (s.district ? " · " + s.district : "") + "</div>" +
      '<div class="india-detail-row"><strong>Coordinates:</strong> ' +
      s.latitude.toFixed(3) + ", " + s.longitude.toFixed(3) + "</div>" +
      (s.distance_km != null
        ? '<div class="india-detail-row"><strong>Distance from selected location:</strong> ' +
          s.distance_km + " km</div>"
        : "") +
      '<div class="india-detail-row"><strong>Observations:</strong> ' +
      (s.n_obs || 0) + " rows" +
      (s.first_obs ? " (" + s.first_obs.slice(0, 10) + " → " + s.last_obs.slice(0, 10) + ")" : "") +
      "</div>" +
      (obs
        ? '<div class="india-detail-row"><strong>Latest observation:</strong> ' +
          obs.value + " " + (obs.unit || "") + " at " +
          String(obs.time || "").replace("T", " ").slice(0, 16) + " UTC</div>"
        : '<div class="india-detail-row"><strong>Latest observation:</strong> none in the real dataset</div>') +
      '<div class="india-detail-row"><strong>Source:</strong> CWC NWDP telemetry CSVs ' +
      '(real data — see Data & Methodology)</div>';
  }

  renderIndiaList();

  if (indiaMap && fly !== false) {
    indiaMap.flyTo([s.latitude, s.longitude], 6, { duration: 0.6 });
  }
}

// ============================================================================
// SATELLITE STORY
// ============================================================================

async function initSatelliteStory() {

  const before =
    document.getElementById(
      "sat-img-before"
    );


  const during =
    document.getElementById(
      "sat-img-during"
    );


  const change =
    document.getElementById(
      "sat-img-change"
    );


  const candidate =
    document.getElementById(
      "sat-img-candidate"
    );


  if (before) {

    before.src =
      sarImagePath("before", "vv");

  }


  if (during) {

    during.src =
      sarImagePath("during", "vv");

  }


  if (change) {

    change.src =
      sarImagePath("change", "vv");

  }


  if (candidate) {

    candidate.src =
      sarImagePath("candidate", "vv");

  }

  // Click-to-zoom lightbox on every SAR image.
  [before, during, change, candidate].forEach((img) => {
    if (!img) return;
    img.classList.add("sat-zoomable");
    img.setAttribute("role", "button");
    img.setAttribute("tabindex", "0");
    img.setAttribute(
      "aria-label",
      "View satellite image enlarged"
    );
    const zoom = () => openSarLightbox(img.src, img.alt);
    img.addEventListener("click", zoom);
    img.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        zoom();
      }
    });
  });

  // Polarization toggle (VV = co-polar, VH = cross-polar).
  const polWrap = document.getElementById("sat-pol-toggle");
  if (polWrap) {
    polWrap.classList.remove("hidden");
    polWrap.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        polWrap
          .querySelectorAll("button")
          .forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        applySarImages(btn.dataset.pol);
      });
    });
  }

  // Event-aware status banner + dates.
  const scenes =
    await loadJSON(
      "data/sentinel1/scenes_metadata.json"
    );

  const pre =
    scenes.scenes.find(
      (s) =>
        s.id ===
        "s1_06aug"
    );

  const duringScene =
    scenes.scenes.find(
      (s) =>
        s.id ===
        "s1_18aug"
    );

  const fmtDay = (iso) => {
    const m = String(iso || "").match(/^\d{4}-(\d{2})-(\d{2})$/);
    if (!m) return iso || "";
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return Number(m[2]) + " " + months[Number(m[1]) - 1];
  };

  satImageState.dates = {
    before: pre ? fmtDay(pre.date) : "06 Aug",
    during: duringScene ? fmtDay(duringScene.date) : "18 Aug"
  };

  const lblBefore =
    document.getElementById("sat-date-before");
  const lblDuring =
    document.getElementById("sat-date-during");
  if (lblBefore) {
    lblBefore.textContent =
      satImageState.dates.before + " · VV";
  }
  if (lblDuring) {
    lblDuring.textContent =
      satImageState.dates.during + " · VV";
  }

  await setSatelliteEventStatus(currentEventId);


  const tech =
    document.getElementById(
      "sat-tech-content"
    );

  const params =
    await loadJSON(
      "data/sar_flood/candidate_mask_params.json"
    );


  if (
    tech &&
    pre &&
    duringScene
  ) {

    tech.innerHTML = `

      <p>
        <strong>Satellite:</strong>
        Sentinel-1A (radar / SAR)
      </p>

      <p>
        <strong>Pre-flood image:</strong>
        ${pre.date},
        ${pre.product_type},
        polarizations
        ${pre.polarizations.join("+")}
      </p>

      <p>
        <strong>During-flood image:</strong>
        ${duringScene.date},
        ${duringScene.product_type},
        polarizations
        ${duringScene.polarizations.join("+")}
      </p>

      <p>
        <strong>Detection rule:</strong>
        ${params.condition}
      </p>

      <p>
        <strong>Threshold:</strong>
        ${params.threshold_db_drop}
        dB backscatter drop
      </p>

      <p>
        Full methodology and validation metrics are in the
        <a
          href="research.html"
          style="color:var(--teal)"
        >
          Research / Technical View
        </a>.
      </p>

    `;

  }


  const toggle =
    document.getElementById(
      "sat-tech-toggle"
    );


  if (
    toggle &&
    tech
  ) {

    toggle.addEventListener(
      "click",
      () => {

        tech.classList.toggle(
          "hidden"
        );

      }
    );

  }

}


// ============================================================================
// PAST FLOODS
// ============================================================================
function initPastFloods() {

  const el =
    document.getElementById(
      "pub-past-floods-list"
    );


  if (!el || !eventsData) {
    return;
  }


  el.innerHTML =
    "";

  // Group events by year (newest first) for a scannable timeline.
  const byYear = new Map();
  eventsData.events
    .slice()
    .sort((a, b) => (a.date < b.date ? 1 : -1))
    .forEach((evt) => {
      const y = String(evt.date).slice(0, 4);
      if (!byYear.has(y)) byYear.set(y, []);
      byYear.get(y).push(evt);
    });

  const fmtDate = (iso) => {
    const d = new Date(iso + "T00:00:00");
    return isNaN(d) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  };

  byYear.forEach((evts, year) => {

    const yearHead =
      document.createElement("div");
    yearHead.className = "pub-pf-year";
    yearHead.textContent =
      year + "  ·  " + evts.length + (evts.length === 1 ? " event" : " events");
    el.appendChild(yearHead);

    evts.forEach((evt) => {

      const item =
        document.createElement("div");
      item.className = "pub-past-flood-item";
      item.dataset.eventId = evt.id;
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");

      const verified = evt.source === "ndem_verified";
      const lvl = evt.cwc_observed.water_level_m;
      const dur = evt.duration_hours;
      const badges = [];
      if (verified) badges.push('<span class="pub-pf-badge ok">NDEM verified</span>');
      if (evt.satellite_evidence && evt.satellite_evidence.status === "OBSERVED")
        badges.push('<span class="pub-pf-badge ok">SAR</span>');
      if (!verified)
        badges.push('<span class="pub-pf-badge">CWC record</span>');

      item.innerHTML = `
        <div class="pub-pf-top">
          <span class="pub-pf-date">${fmtDate(evt.date)}</span>
          <span class="pub-pf-level ${lvl >= 25 ? "severe" : ""}">${lvl.toFixed(2)} m</span>
        </div>
        <div class="pub-pf-meta">
          ${dur ? `<span>${dur} h above danger level</span>` : ""}
          ${badges.join(" ")}
        </div>
      `;

      const activate = () => {
        selectEvent(evt.id);
        const floodBtn =
          document.querySelector('.pub-nav-btn[data-pubtab="floodmap"]');
        if (floodBtn) floodBtn.click();
      };

      item.addEventListener("click", activate);
      item.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activate();
        }
      });

      if (evt.id === currentEventId) {
        item.classList.add("active");
      }

      el.appendChild(item);

    });

  });

}


// ============================================================================
// GUIDE
// ============================================================================

function initGuide() {

  const backdrop =
    document.getElementById(
      "guide-backdrop"
    );


  const openBtn =
    document.getElementById(
      "pub-guide-open-btn"
    );


  const closeBtn =
    document.getElementById(
      "guide-close-btn"
    );


  if (
    !backdrop ||
    !openBtn ||
    !closeBtn
  ) {

    return;

  }


  const openGuide =
    () => {

      backdrop.classList.remove(
        "hidden"
      );

      openBtn.classList.add(
        "active"
      );

    };


  const closeGuide =
    () => {

      backdrop.classList.add(
        "hidden"
      );

      openBtn.classList.remove(
        "active"
      );

    };


  openBtn.addEventListener(
    "click",
    openGuide
  );


  closeBtn.addEventListener(
    "click",
    closeGuide
  );


  backdrop.addEventListener(
    "click",
    (e) => {

      if (
        e.target ===
        backdrop
      ) {

        closeGuide();

      }

    }
  );


  const tourAgain =
    document.getElementById(
      "guide-tour-again-btn"
    );


  if (tourAgain) {

    tourAgain.addEventListener(
      "click",
      () => {

        closeGuide();

        startTour();

      }
    );

  }

}


// ============================================================================
// TOUR
// ============================================================================

const TOUR_STEPS = [

  {

    title:
      "Choose an event",

    text:
      "Select the flood date you want to explore using the event selector."

  },

  {

    title:
      "Understand the situation",

    text:
      "These cards summarize river water level, satellite evidence and affected area."

  },

  {

    title:
      "Explore the map",

    text:
      "Zoom, move around and turn flood information layers on or off."

  },

  {

    title:
      "Explore the AI flood map",

    text:
      "Turn on AI flood inundation to view the Random Forest spatial prediction for scene 1017769."

  },

  {

    title:
      "Need help?",

    text:
      "Click Guide at any time to understand unfamiliar terms."

  }

];


const TOUR_STORAGE_KEY =
  "floodwatch_tour_seen";


function startTour() {

  let step = 0;


  const backdrop =
    document.getElementById(
      "tour-backdrop"
    );


  const stepCount =
    document.getElementById(
      "tour-step-count"
    );


  const title =
    document.getElementById(
      "tour-title"
    );


  const text =
    document.getElementById(
      "tour-text"
    );


  const nextBtn =
    document.getElementById(
      "tour-next-btn"
    );


  const skipBtn =
    document.getElementById(
      "tour-skip-btn"
    );


  if (
    !backdrop ||
    !stepCount ||
    !title ||
    !text ||
    !nextBtn ||
    !skipBtn
  ) {

    return;

  }


  function render() {

    stepCount.textContent =
      `Step ${step + 1} of ${TOUR_STEPS.length}`;


    title.textContent =
      TOUR_STEPS[step].title;


    text.textContent =
      TOUR_STEPS[step].text;


    nextBtn.textContent =
      step ===
      TOUR_STEPS.length - 1
        ? "Done"
        : "Next";

  }


  function end() {

    backdrop.classList.add(
      "hidden"
    );


    try {

      localStorage.setItem(
        TOUR_STORAGE_KEY,
        "1"
      );

    }

    catch (e) {}


    const banner =
      document.getElementById(
        "pub-tour-banner"
      );


    if (banner) {

      banner.classList.add(
        "hidden"
      );

    }

  }


  nextBtn.onclick =
    () => {

      if (
        step <
        TOUR_STEPS.length - 1
      ) {

        step++;

        render();

      }

      else {

        end();

      }

    };


  skipBtn.onclick =
    end;


  render();


  backdrop.classList.remove(
    "hidden"
  );

}


// ============================================================================
// TOUR BANNER
// ============================================================================

function initTourBanner() {

  const banner =
    document.getElementById(
      "pub-tour-banner"
    );


  const startBtn =
    document.getElementById(
      "pub-tour-start-btn"
    );


  const skipBtn =
    document.getElementById(
      "pub-tour-skip-btn"
    );


  if (
    !banner ||
    !startBtn ||
    !skipBtn
  ) {

    return;

  }


  let alreadySeen = false;


  try {

    alreadySeen =
      localStorage.getItem(
        TOUR_STORAGE_KEY
      ) === "1";

  }

  catch (e) {}


  if (!alreadySeen) {

    banner.classList.remove(
      "hidden"
    );

  }


  startBtn.addEventListener(
    "click",
    () => {

      banner.classList.add(
        "hidden"
      );

      startTour();

    }
  );


  skipBtn.addEventListener(
    "click",
    () => {

      banner.classList.add(
        "hidden"
      );


      try {

        localStorage.setItem(
          TOUR_STORAGE_KEY,
          "1"
        );

      }

      catch (e) {}

    }
  );

}


// ============================================================================
// BOOT
// ============================================================================// Resilient boot: each step runs independently so one failed dataset,
// script or slow network cannot blank the whole dashboard.
(function boot() {

  console.log(
    "Starting FloodWatch..."
  );


  const bootFailures = [];

  function safeStep(name, fn) {
    return Promise.resolve()
      .then(fn)
      .catch((err) => {
        bootFailures.push(name + ": " + (err && err.message ? err.message : err));
        console.error("FloodWatch boot step failed (continuing):", name, err);
      });
  }

  safeStep("shared data", loadSharedData)
    .then(() => safeStep("AI flood results", loadAIFloodResults))
    .then(() => safeStep("event picker", populateEventPicker))
    .then(() => safeStep("situation cards", renderSituationCards))

    // ------------------------------------------------------------------------
    // Overview
    // ------------------------------------------------------------------------

    .then(() => safeStep("overview map", initOverviewMap))
    .then(() => safeStep("what-am-i", initWhatAmI))

    // ------------------------------------------------------------------------
    // Flood map
    // ------------------------------------------------------------------------

    .then(() => safeStep("flood map", initFloodMap))

    // ------------------------------------------------------------------------
    // Water levels
    // ------------------------------------------------------------------------

    .then(() => safeStep("water levels", initWaterLevels))

    // ------------------------------------------------------------------------
    // Satellite story
    // ------------------------------------------------------------------------

    .then(() => safeStep("satellite story", initSatelliteStory))

    // ------------------------------------------------------------------------
    // Past floods
    // ------------------------------------------------------------------------

    .then(() => safeStep("past floods", initPastFloods))

    // ------------------------------------------------------------------------
    // Guide / Tour
    // ------------------------------------------------------------------------

    .then(() => safeStep("guide", initGuide))
    .then(() => safeStep("india stations", initIndiaStations))
    .then(() => safeStep("tour banner", initTourBanner))
    .then(() => {

      if (bootFailures.length === 0) {

        console.log(
          "=========================================="
        );

        console.log(
          "FloodWatch loaded successfully."
        );


        console.log(
          "AI Scene:",
          AI_FLOOD_SCENE
        );


        console.log(
          "AI GeoJSON:",
          AI_FLOOD_GEOJSON
        );


        console.log(
          "AI Results:",
          AI_FLOOD_RESULTS
        );


        console.log(
          "AI Threshold:",
          AI_FLOOD_THRESHOLD
        );


        console.log(
          "=========================================="
        );

        return;
      }

      // Partial failure: warn without blocking the working UI.
      console.warn(
        "FloodWatch loaded with " + bootFailures.length + " degraded section(s):",
        bootFailures.join(" | ")
      );

      document.body.insertAdjacentHTML(
        "beforeend",
        `<div
          id="pub-boot-warning"
          role="status"
          style="
            position:fixed;
            bottom:10px;
            left:10px;
            right:10px;
            background:#8a5a00;
          color:white;
          padding:10px 14px;
          border-radius:6px;
          font-size:12px;
          z-index:9999;
        "
      >

        ⚠ Some FloodWatch sections could not load: ${bootFailures.map(esc).join(" · ")}. The rest of the dashboard still works.

        <br>

        Check the browser console for details. <button type="button" onclick="this.parentElement.remove()" style="margin-left:8px;background:none;border:1px solid #fff;color:#fff;cursor:pointer;border-radius:4px;padding:2px 8px">Dismiss</button>

      </div>
      `
      );
    });

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
})();