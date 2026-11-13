# Request for CWC water-level data access

A message you can send to whoever controls the CWC data you need (portal
administrator, India-WRIS / data.gov.in contact, regional office, or a data
vendor). Replace the bracketed placeholders before sending; nothing here is a
real contact address.

Everything below is based on what the repository already holds and what
`scripts/ingest_cwc.py` already accepts.

---

## Short version (paste into an e-mail)

> **Subject: Request for hourly water-level observations — Naraj, Alipingal and Nimapara (Mahanadi basin, Odisha), 2021 to present**
>
> Dear [name / team],
>
> We maintain FloodWatch, a research dashboard that models flood risk at three
> Central Water Commission gauges in the Mahanadi delta: **Naraj** (Mahanadi,
> Cuttack), **Alipingal** (Dhaniya, Jagatsinghpur) and **Nimapara** (Dandia,
> Puri). We already hold verified hourly readings for August 2022 and daily
> means from 2021 to 2025, and we would like to extend the hourly record to the
> present.
>
> Could you tell us the supported way to obtain, on an ongoing basis, **hourly
> water level (metres) for these three stations from 1 January 2021 to the
> current day**, ideally with the gauge datum, danger level and any warning
> thresholds? A CSV export, a documented download URL, an API key for the
> portal, or a scheduled export would all work — our importer reads a CSV from a
> path or an HTTPS URL, so no software change is needed on our side.
>
> We would also welcome a price or process note if this requires a paid
> subscription, and guidance on how you would like the data credited.
>
> Thank you,
> [name, role, organisation, contact]

---

## What is needed, precisely

| Item | Requested | Why this exact thing |
| --- | --- | --- |
| Stations | **Naraj** (Mahanadi, Cuttack, 20.4717 N 85.7656 E), **Alipingal** (Dhaniya, Jagatsinghpur, 20.1289 N 86.1355 E), **Nimapara** (Dandia, Puri, 20.0833 N 86.0000 E) | These are the three stations with verified series in our data; the model is calibrated on them |
| Variable | Hourly **water level in metres** | The model's features (`rise_6h/12h/24h`, `trend_3h`) need sub-daily change |
| Also useful | Gauge zero / datum reference, danger level, warning and evacuation thresholds | Without the datum the metres cannot be compared across sources; the flood label needs the official threshold |
| Optional | Hourly rainfall (mm) at the same stations, discharge (m³/s) | Rainfall is currently taken from a separate public dataset; native station rainfall would remove a join |
| Time range | **1 January 2021 → present**, then ongoing | Our stored record starts 2021-01-01; we need everything after 2025-12-31 to move the anchor |
| Resolution | **Hourly** (manual hourly readings are fine) | Daily-only data cannot replace the hourly series (see below) |
| Frequency | Daily, or every 6 hours | Matches the ingestion scheduler; a once-a-day export is enough for a working freshness indicator |
| Format | CSV, UTF-8, one row per station-hour, ISO-8601 or `YYYY-MM-DD HH:MM` timestamps | `scripts/ingest_cwc.py --levels-csv` already parses this |
| Access | Any of: portal account, API key, documented URL, SFTP drop, periodic e-mail export | All are supported by the existing importer except e-mail, which would need a manual save to disk |
| Volume | ≈26,000 rows per station for five years at hourly resolution | Small; a single file per station or per year is fine |

### Format example (structure only — the values are placeholders, not data)

```csv
station,timestamp,water_level_m,datum_m,danger_level_m
Naraj,2025-12-31 00:00:00,<value>,<gauge zero>,<threshold>
Naraj,2025-12-31 01:00:00,<value>,<gauge zero>,<threshold>
```

Our importer also accepts the column layout of the export that produced our
existing files (`rwl_manual_hr_cwc_005_2021_2025.csv`); matching that layout
means a zero-configuration import.

---

## Why we are asking

- The dashboard's forecasts currently **replay a record that ends
  2025-12-30 23:00 UTC**. As of 2026-11-13 that is about **318 days old**, and
  the interface labels every forecast as stale. With an ongoing hourly feed the
  same models would describe current conditions.
- The machine-learning headline is anchored to the newest row in our dataset. A
  newer row means a current forecast; no retraining is required to consume it.
- The statistical engine additionally needs **hourly** history. It currently
  stops at August 2022 because that is the only hourly file we hold. Our
  in-repo `forecast_dataset.csv` indexes hours but repeats a single value per
  day, so it cannot stand in for hourly observations.
- The project is a research / decision-support dashboard. It is **not** an
  official flood warning service and will not be presented as one.

---

## What we will and will not do with it

- **Will**: store it locally, compute forecasts, and show the observation time
  and age in the interface so users always know how current the data is.
- **Will not**: redistribute the raw feed, publish it, or present derived
  products as official CWC warnings.
- We are happy to display the attribution and any disclaimer you require, and to
  accept a licence or terms of use before the first transfer.

---

## Implementation note (for us, not for the recipient)

Once a source exists, no code change is required for a CSV:

```bash
python3 scripts/ingest_cwc.py --once --levels-csv <path-or-url> --dry-run   # prove the parse
python3 scripts/ingest_cwc.py --once --levels-csv <path-or-url>             # write + rebuild features
python3 scripts/ingest_cwc.py --watch --interval-minutes 360                # keep it current
```

The importer appends only newer observations, never rewrites history, rebuilds
the feature frame, and records `data/cwc/ingestion_status.json`, which
`/api/health` and the forecast card read.
