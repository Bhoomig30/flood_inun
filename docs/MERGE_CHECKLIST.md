# Merge checklist — `audit/close-gaps`

Base: `d0c5095`. Branch: `audit/close-gaps` (8 commits). Nothing was pushed or
merged. Commits are listed oldest-first.

Verification date: 2026-11-13. All API/browser checks ran on the branch at
`205e3f4` (the state described here).

---

## What changed, per commit

### `4d5a84c` — Checkpoint of in-progress CWC ingestion work
Carries over uncommitted work from an earlier session so the audit commits stay
clean. **This is the commit to review most carefully: it was not written by the
audit.**

| File | Change |
| --- | --- |
| `.gitignore` | adds `.cache/` and `artifacts/` |
| `scripts/ingest_cwc.py` | **new**, 465 lines: scheduled CWC ingestion (`--once`, `--watch`, `--dry-run`, `--levels-csv`, `--rain-csv`) |
| `naraj_dashboard/data/cwc/ingestion_status.json` | output of one real run — **no longer tracked** (see below) |
| `naraj_dashboard/ml_serve.py` | dataset hot-reload when the feature frame changes |
| `naraj_dashboard/server.js` | `/api/health` gains `data_freshness` read from `ingestion_status.json` |
| `package.json` | `ingest:cwc` and `ingest:cwc:watch` scripts |

Review result:
- **No credentials, API keys, tokens or passwords.** Pattern scan over the whole
  branch diff found none. The only URL is the public Hugging Face dataset.
- **No personal data.** No e-mail addresses in the diff.
- **RESOLVED (branch `audit/india-wide`, commit "Untrack the ingestion run
  snapshot")**: the committed file carried a machine-specific
  `/workspace/.../rainfall_staged_to` path. It is now gitignored, removed from
  the index with `git rm --cached`, and replaced by
  `data/cwc/ingestion_status.example.json` with the same structure and
  placeholder values. `/api/health` reports `status: "not_run"`,
  `message: "no ingestion run yet"` and `stale: null` when the file is absent,
  instead of inventing a freshness verdict; `scripts/ingest_cwc.py` still runs.
- The ingestion script is **functional, not a stub** (stdlib only: `argparse`,
  `csv`, `json`, `shutil`, `subprocess`, `urllib`; no third-party imports). It
  fails honestly when no water-level source is supplied and records
  `stale: true` with blockers instead of inventing an anchor.
- The dashboard **does depend on the committed status file**: `/api/health`
  reports it, and it is a snapshot (`last_run_utc 2026-11-12`). If it is not
  regenerated it silently ages; the file's own `stale` flag is what the UI
  surfaces, so this is visible, not silent.

### `56dabab` — Phase 1: docs and setup match the trained models
`requirements.txt` (pin `scikit-learn>=1.3,<1.8`), `README_FORECASTING.md`,
`research.html`, `research.js`, `style.css`. Removes the false "No trained model
exists" claim, documents both trained models and the open stages.

### `1adf9f6` — Phase 2: portable calibration, baseline, freshness, tests
`ml_train.py` (`FrozenEstimator` with `cv="prefit"` fallback), new
`ml/src/baseline_skill.py`, new `hf_forecast_baseline.json`, `server.js`
(freshness + baseline), `app.js`, `research.js`, `style.css`, new
`tests/test_forecast_api.py`.

### `b953a5a` — Phase 3: `docs/NEXT_STEPS.md`
Plan only; no code.

### `033a377` — Anchor the ML forecast to the dataset's latest row
`server.js`, `app.js`, tests, README. The RF stopped being pinned to the
engine's 2022-08-31 timestamp.

### `2660a2a` — RF is the headline; engine moved to a legacy block
`server.js`, `app.js`, `index.html`, tests, README, `docs/NEXT_STEPS.md`.
Removes the 60/40 blend, adds `legacy_engine`, `persistence`, replay banner.

### `205e3f4` — NDEM layer checkbox honesty
`public.js` only. The checkbox no longer claims a layer is visible when it is
not (and untick itself when no extent exists for the selected event).

---

## How it was verified

| Check | Result |
| --- | --- |
| Clean venv, `pip install -r requirements.txt` | scikit-learn **1.7.2**, pandas 3.1.1, numpy 2.5.4 |
| Training on 1.7.2 (`ml_train.py`, temporary copy) | **0 metric differences** vs committed metadata (6h 0.9921 / 12h 0.9900 / 24h 0.9825) |
| Training on 1.9.1 (diagnostic only) | runs, 53 metric diffs, warns when unpickling 1.7.2 bundles — reason the pin stays |
| Committed `.pkl` files | unmodified (`git status` on `data/ml_models` empty after every run) |
| `tests/test_forecast_api.py` in the working tree | **11 tests OK** |
| Same suite in a **clean clone** (git bundle) with a **fresh venv** | **11 tests OK** (7.0 s) |
| `/api/forecast?station=naraj` | `headline_source: rf_model`, headline 0.15 / 0.23 / 0.23 %, `ml_result.as_of 2025-12-30 23:00`, legacy engine 7.21 / 7.63 / 8.10 % |
| `/api/forecast?station=alipingal,nimapara` | `headline_source: legacy_engine`, no `ml_result`, clearly labelled |
| `/api/health`, `/api/model/info` | online; model trained; `baseline_skill` present |
| Browser: forecast card | replay banner, RF headline, `engine x%` badges, persistence check (21.61 m vs 24.28 m), STALE badge, legacy block |
| Browser: Water Levels tab | Alipingal and Nimapara charts render from the 2021–2025 daily series |
| Browser: Past Floods | 30 entries; selecting events switches to Flood Map and swaps the NDEM layer (235 features for 18 Aug 2022 vs 153 for 16 Aug 2022), list/picker highlight and situation cards update; a 2025 event clears the layer and unticks the box |
| Browser: NDEM checkbox | starts unchecked with no layer on the map; toggling on draws the extent |
| Browser console | no errors during the checks; all requests 200 |
| Branch review | no secrets/tokens/personal data; largest tracked file is the 23 MB `forecast_dataset.csv`, **already tracked before this branch** |

---

## Known limitations

1. **The data is a historical replay** ending 2025-12-30 23:00 UTC. Every
   forecast is stale by design until live CWC levels are ingested; the UI says
   so and the badge stays amber.
2. **The legacy engine is anchored to 2022-08-31** because its hourly input is
   `data/cwc/*_august2022_hourly.json`. It is reported separately and is not in
   the headline. Extending its hourly history is the follow-up that would allow
   re-blending (`docs/NEXT_STEPS.md`).
3. **Only Naraj has an ML headline.** Alipingal and Nimapara remain
   engine-only, labelled `headline_source: legacy_engine`.
4. **The forecast cone plots the engine's Aug-2022 series** (last 72 hours) and
   the engine's projection, not the RF row. The card header says this.
5. **The RF measures poorly against a naive persistence rule on Brier/F1**
   (see the research page table); it wins only on AUC. Do not quote the model as
   uniformly better.
6. **No automated UI tests.** The DOM-level fixes in `205e3f4` and the card
   layout were verified by hand in a headless browser, not by CI.
7. **`ingestion_status.json` is a committed run artifact** with a machine path
   and a fixed run date; regenerate or ignore it (owner decision).
8. **Exposure, SAR/DEM fusion, threshold tuning and live ingestion are not
   done** — see `docs/NEXT_STEPS.md`.

---

## Owner checks before merging

- [x] ~~Decide whether `ingestion_status.json` stays tracked.~~ Done: gitignored
      with an example committed; `/api/health` reports `not_run` when absent.
- [ ] Decide the model-artifact question: regenerate the `.pkl` bundles on the
      `FrozenEstimator` path (metrics identical on 1.7.2, pickled objects differ),
      or keep the current bundles and the `<1.8` pin.
- [ ] Run `npm start` (or `node naraj_dashboard/server.js`) with the venv first
      on `PATH`, then open the dashboard yourself. The screenshots in this work
      are not committed.
- [ ] Confirm the Hugging Face dataset's licence/attribution requirements before
      publishing anything derived from it.
- [ ] Confirm the CWC access route (portal / API key / export / vendor) — see
      `docs/CWC_ACCESS_REQUEST.md`.
- [ ] Decide whether the statistical engine should be retired or kept as the
      legacy comparison once hourly history exists.
- [ ] Be aware that the Past Floods selection does **not** zoom the Flood Map to
      the study region (pre-existing behaviour, unchanged here). Selecting an
      event swaps layers and updates the strip, but the map stays at the
      India-wide view until the user zooms.
