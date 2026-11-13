# Request for CWC water-level data access

**Status: draft, not sent.** There is no verified recipient address in this
repository, and this project cannot send e-mail. Replace every bracketed
placeholder before using this text. A plain-text version for the e-mail body is
in [`CWC_ACCESS_REQUEST_EMAIL.txt`](CWC_ACCESS_REQUEST_EMAIL.txt).

Everything below is derived from files in this repository: the CWC station
registry (`naraj_dashboard/data/india_cwc/stations.json`), the stored
water-level series (`naraj_dashboard/data/cwc/`) and the importer
(`scripts/ingest_cwc.py`). No contact details, prices or service levels are
invented here.

---

## 1. What the dashboard is

FloodWatch is a research / decision-support dashboard for Indian riverine flood
risk. It shows observed rainfall and river data for **842 CWC stations across 28
states** and produces a 6/12/24-hour flood forecast where a verified model or
series exists. It is **not** an official flood-warning service and does not
present its output as one.

## 2. What we already hold (measured, not estimated)

| Item | Value in this repository |
| --- | --- |
| Registry stations | 842 in 28 states — 808 telemetry rainfall gauges, 34 river-discharge gauges |
| Verified hourly water-level series | 3 stations (Naraj, Alipingal, Nimapara — Mahanadi basin, Odisha) for August 2022 |
| Verified daily water-level series | The same 3 stations, 2021–2025 |
| Forecast record end | 2025-12-30 23:00 UTC — **318 days stale** on 2026-11-13, and labelled as such in the UI |
| Registry rainfall observations | 694 stations carry a latest observation; Naraj alone has 28,467 hourly values |
| Registry river observations | 34 river stations, 31 with observations in 2025, 1,198–70,319 values each — **discharge in m³/s, not water level** |

The model headline is anchored to the newest row of the stored dataset. A newer
observation extends the forecast without retraining; there is no software
blocker, only a data gap.

## 3. Request A — extend the three existing series (highest priority)

For **Naraj** (Mahanadi, Cuttack, 20.4717 N 85.7656 E), **Alipingal** (Dhaniya,
Jagatsinghpur, 20.1289 N 86.1355 E) and **Nimapara** (Dandia, Puri, 20.0833 N
86.0000 E):

- **hourly water level in metres, 1 January 2021 → present, then ongoing**;
- the **gauge datum / zero** so metres are comparable across sources;
- the **official warning, danger and evacuation levels** for each gauge;
- if available, the same-period hourly rainfall and discharge at these sites.

Hourly resolution matters: the statistical engine needs sub-daily change, and
the daily means we hold cannot substitute for it.

## 4. Request B — prioritised national expansion

The dashboard is national, but only the Mahanadi stations have a verified
water-level series. To extend coverage honestly rather than borrowing one
station's numbers for another, we ask for water level at the stations below.

**Selection rule (registry fields only):** `kind == "river"` (the only stations
with a sub-daily hydrological series), ordered by `n_obs`, with state spread.
No station is included for any reason not measurable in the registry. The
registry records **discharge (m³/s)** for these sites, not level — which is
exactly why level, datum and thresholds are part of the request.

| Priority | Station | State | Registry `n_obs` | First obs | Last obs |
| --- | --- | --- | --- | --- | --- |
| 1 | Karnaprayag (P) | Uttarakhand | 70,319 | 2023-06-07 | 2025-12-26 |
| 2 | Marchula_1 | Uttarakhand | 70,188 | 2022-08-04 | 2025-12-31 |
| 3 | Lambagarh | Uttarakhand | 68,870 | 2023-06-19 | 2025-12-19 |
| 4 | Dhamkund_1 | Jammu & Kashmir | 67,116 | 2023-08-18 | 2025-12-22 |
| 5 | Koteshwar | Uttarakhand | 65,677 | 2023-04-11 | 2025-12-23 |
| 6 | Drass_1 | Ladakh | 64,140 | 2023-07-03 | 2025-09-22 |
| 7 | Ziro | Arunachal Pradesh | 64,097 | 2023-06-19 | 2025-09-22 |
| 8 | Changlang | Arunachal Pradesh | 58,372 | 2023-10-31 | 2025-09-22 |

If a smaller first transfer is easier, the eight stations above cover four
states and four hydrological regimes (Himalayan, trans-Himalayan, north-eastern
and — with Request A — eastern delta). Any additional river gauge with a
comparable record is welcome; the full list of 34 is in the registry.

## 5. Format and delivery

| Item | Requested |
| --- | --- |
| Variable | Water level (m), plus datum and warning/danger/evacuation thresholds |
| Range | 2021-01-01 → present, then ongoing |
| Resolution | Hourly (manual hourly readings are acceptable) |
| Frequency | Daily or every 6 hours |
| Structure | CSV, UTF-8, one row per station-hour, ISO-8601 or `YYYY-MM-DD HH:MM` timestamps |
| Delivery | Portal account, API key, documented URL, SFTP drop, or periodic export |

```csv
station,timestamp,water_level_m,datum_m,danger_level_m
Naraj,2025-12-31 00:00:00,<value>,<gauge zero>,<threshold>
Naraj,2025-12-31 01:00:00,<value>,<gauge zero>,<threshold>
```

The values above are placeholders, not data. Our importer already reads a CSV
from a local path or an HTTPS URL (`scripts/ingest_cwc.py --levels-csv`), so no
software change is needed on our side.

## 6. What we will and will not do

- **Will**: store the data locally, compute forecasts, and display the
  observation timestamp and its age so users can judge currency.
- **Will**: display the attribution and any disclaimer required, and accept a
  licence or terms of use before the first transfer.
- **Will not**: redistribute the raw feed, publish it, or present derived
  products as official CWC warnings.

## 7. Why this matters for accuracy

- Every forecast is currently labelled **stale** because the record ends
  2025-12-30 23:00 UTC. An ongoing feed makes the same models describe current
  conditions.
- Hourly history is required to move the legacy engine past its August-2022
  anchor; the in-repo dataset repeats one value per day and cannot stand in.
- Stations without a verified series are shown as **metadata only** today. Real
  series would let the dashboard add them as genuine tier-2 coverage, without
  inventing probabilities.

## 8. Implementation note (internal)

```bash
python3 scripts/ingest_cwc.py --once --levels-csv <path-or-url> --dry-run   # prove the parse
python3 scripts/ingest_cwc.py --once --levels-csv <path-or-url>             # write + rebuild features
python3 scripts/ingest_cwc.py --watch --interval-minutes 360                # keep it current
```

The importer appends newer observations, never rewrites history, rebuilds the
feature frame, and records `data/cwc/ingestion_status.json` (gitignored), which
`/api/health` and the forecast card read.

## 9. What is not verified

- No recipient address, contact person or data-access process is confirmed in
  this repository; `[RECIPIENT]` must be filled from an authoritative CWC /
  India-WRIS source before sending.
- No e-mail has been sent from this project and no reply has been received.
- The station counts and observation ranges above are copied from the committed
  registry (generated 2026-09-14); re-check them if the registry is rebuilt.
