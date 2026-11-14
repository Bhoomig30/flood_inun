// ============================================================================
// FLOODWATCH — NARAJ BACKTEST (historical, held-out test period only)
//
// Answers "what did the model say at this hour, and what actually happened?"
// using the SAME feature rows and labels the Random Forests were evaluated on.
// Nothing is invented: every outcome comes from the dataset's own future rows.
//
// Test period: the chronological split's test window (2025-04-01 06:00 to
// 2025-12-30 23:00 UTC), read from hf_forecast_baseline.json. Requests outside
// it are refused because the model has seen those rows during training.
// ============================================================================

const fs = require("fs");
const path = require("path");

const DATASET = path.join(__dirname, "data", "hf", "forecast_dataset.csv");
const BASELINE = path.join(__dirname, "data", "ml_models", "hf_forecast_baseline.json");

const FALLBACK_TEST_START = "2025-04-01 06:00:00";
const FALLBACK_TEST_END = "2025-12-30 23:00:00";
const FALLBACK_THRESHOLD_M = 24.28;
const HORIZONS = [6, 12, 24];

let CACHE = null;

function loadBaseline() {
  try {
    const b = JSON.parse(fs.readFileSync(BASELINE, "utf-8"));
    return {
      threshold_m: Number((b.label && b.label.threshold_m) || FALLBACK_THRESHOLD_M),
      test_start:
        (b.split && b.split.test_start) || FALLBACK_TEST_START,
      test_end: (b.split && b.split.test_end) || FALLBACK_TEST_END,
    };
  } catch (err) {
    return {
      threshold_m: FALLBACK_THRESHOLD_M,
      test_start: FALLBACK_TEST_START,
      test_end: FALLBACK_TEST_END,
    };
  }
}

function load() {
  if (CACHE) return CACHE;
  const meta = loadBaseline();
  const text = fs.readFileSync(DATASET, "utf-8");
  const lines = text.split(/\r?\n/);
  const header = lines[0].split(",");
  const idx = {
    timestamp: header.indexOf("timestamp"),
    level: header.indexOf("naraj_water_level_m"),
    l6: header.indexOf("flood_next_6h"),
    l12: header.indexOf("flood_next_12h"),
    l24: header.indexOf("flood_next_24h"),
  };
  if (Object.values(idx).some((v) => v < 0)) {
    throw new Error("forecast_dataset.csv is missing a backtest column");
  }

  const rows = [];
  const index = new Map();
  for (let i = 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line) continue;
    const parts = line.split(",");
    const time = parts[idx.timestamp];
    const level = Number(parts[idx.level]);
    if (!time || !Number.isFinite(level)) continue;
    const row = {
      time,
      level,
      labels: {
        6: Number(parts[idx.l6]),
        12: Number(parts[idx.l12]),
        24: Number(parts[idx.l24]),
      },
    };
    index.set(time, rows.length);
    rows.push(row);
  }
  CACHE = { rows, index, ...meta };
  return CACHE;
}

// Accepts "YYYY-MM-DD HH:MM[:SS]", "YYYY-MM-DDTHH:MM[:SS][Z]" and returns the
// dataset's canonical "YYYY-MM-DD HH:MM:SS" (treated as UTC), or null.
function normalizeTimestamp(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const m = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?Z?$/
  );
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  const stamp = Date.UTC(
    Number(y),
    Number(mo) - 1,
    Number(d),
    Number(h),
    Number(mi),
    Number(s || 0)
  );
  const dt = new Date(stamp);
  if (
    dt.getUTCFullYear() !== Number(y) ||
    dt.getUTCMonth() !== Number(mo) - 1 ||
    dt.getUTCDate() !== Number(d) ||
    dt.getUTCHours() !== Number(h) ||
    dt.getUTCMinutes() !== Number(mi)
  ) {
    return null;
  }
  const pad = (n) => String(n).padStart(2, "0");
  return (
    `${y}-${mo}-${d} ${pad(h)}:${pad(mi)}:${pad(Number(s || 0))}`
  );
}

function testPeriod() {
  const c = load();
  return { start: c.test_start, end: c.test_end };
}

function inTestPeriod(time) {
  const p = testPeriod();
  return time >= p.start && time <= p.end;
}

function windowStats(index, hours) {
  const c = load();
  const values = [];
  for (let k = 1; k <= hours; k += 1) {
    const row = c.rows[index + k];
    if (!row) break;
    values.push(row.level);
  }
  const complete = values.length === hours;
  if (!values.length) {
    return { max_level_m: null, threshold_exceeded: null, window_complete: false };
  }
  const max = Math.max(...values);
  return {
    max_level_m: Number(max.toFixed(2)),
    threshold_exceeded: max >= c.threshold_m,
    window_complete: complete,
  };
}

// Data half of a backtest: observed level, future maxima, actual outcomes,
// dataset label and the persistence baseline. The model probabilities are
// attached by the server, which owns the ML bridge.
function describe(time) {
  const c = load();
  const canonical = normalizeTimestamp(time);
  if (!canonical) {
    return {
      ok: false,
      status: "invalid_time",
      message:
        "Could not read that timestamp. Use an hourly UTC timestamp such as 2025-09-27T06:00:00.",
    };
  }
  const period = testPeriod();
  if (!inTestPeriod(canonical)) {
    return {
      ok: false,
      status: "out_of_range",
      message:
        `Backtest is limited to the held-out test period ` +
        `${period.start} to ${period.end} UTC. ${canonical} is outside it, ` +
        `so the model may have seen that row during training.`,
      test_period: period,
      requested_time: canonical,
    };
  }
  const index = c.index.get(canonical);
  if (index === undefined) {
    return {
      ok: false,
      status: "invalid_time",
      message:
        `No dataset row at ${canonical} UTC. The dataset is hourly; pick an ` +
        `exact hour between ${period.start} and ${period.end}.`,
      test_period: period,
    };
  }

  const row = c.rows[index];
  const baselinePredicts = row.level >= c.threshold_m;
  const horizons = {};
  for (const h of HORIZONS) {
    const stats = windowStats(index, h);
    const label = row.labels[h];
    horizons[`${h}h`] = {
      max_level_m: stats.max_level_m,
      threshold_exceeded: stats.threshold_exceeded,
      window_complete: stats.window_complete,
      dataset_label: Number.isFinite(label) ? label : null,
      label_matches_window:
        stats.threshold_exceeded === null
          ? null
          : Number(label) === (stats.threshold_exceeded ? 1 : 0),
      baseline_predicts_flood: baselinePredicts,
    };
  }

  return {
    ok: true,
    data: {
      station: "naraj",
      time: canonical,
      observed_level_m: Number(row.level.toFixed(2)),
      threshold_m: c.threshold_m,
      test_period: period,
      baseline: {
        rule: "predict flood if the observed level is at or above the threshold",
        predicts_flood: baselinePredicts,
      },
      horizons,
      warning:
        "Historical backtest on held-out data, not a live forecast. Outcomes " +
        "come from the dataset's future rows, which the model never trained on.",
    },
  };
}

// A small set of representative hours: hours before real threshold crossings,
// plus quiet hours with no crossing in the next 24 hours. Deduplicated by
// crossing event and spread across the test period.
function moments() {
  const c = load();
  const period = testPeriod();
  const rows = c.rows;
  const startIndex = rows.findIndex((r) => r.time >= period.start);
  const endIndex = rows.length - 1;

  const crossEvents = [];
  let lastCross = null;
  for (let i = startIndex; i <= endIndex - 24; i += 1) {
    if (rows[i].level >= c.threshold_m) continue;
    let crossAt = null;
    for (let k = i + 1; k <= i + 24; k += 1) {
      if (rows[k].level >= c.threshold_m) {
        crossAt = k;
        break;
      }
    }
    if (crossAt === null) continue;
    if (lastCross !== null && crossAt === lastCross) continue;
    lastCross = crossAt;
    crossEvents.push({ crossAt, rowIndex: i });
  }

  const picked = [];
  const used = new Set();
  for (const ev of crossEvents) {
    const lead = Math.max(ev.crossAt - 6, startIndex);
    const t = rows[lead].time;
    if (used.has(t)) continue;
    used.add(t);
    picked.push({
      time: t,
      kind: "pre_crossing",
      label:
        "6 h before the level first reached " + c.threshold_m + " m (" +
        rows[ev.crossAt].time + ")",
    });
  }

  const quiet = [];
  for (let i = startIndex; i <= endIndex - 24; i += 1) {
    if (rows[i].level > c.threshold_m - 0.75) continue;
    let crosses = false;
    for (let k = i + 1; k <= i + 24; k += 1) {
      if (rows[k].level >= c.threshold_m) {
        crosses = true;
        break;
      }
    }
    if (!crosses) quiet.push(i);
  }
  const wantedQuiet = 3;
  for (let n = 0; n < wantedQuiet && quiet.length; n += 1) {
    const pick = quiet[Math.floor((n + 0.5) * quiet.length / wantedQuiet)];
    const t = rows[pick].time;
    if (used.has(t)) continue;
    used.add(t);
    picked.push({
      time: t,
      kind: "quiet",
      label: "Quiet hour: no threshold crossing in the next 24 h",
    });
  }

  return { period, threshold_m: c.threshold_m, moments: picked };
}

module.exports = {
  normalizeTimestamp,
  testPeriod,
  describe,
  moments,
  load,
};
