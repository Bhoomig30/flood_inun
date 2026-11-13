#!/usr/bin/env python3
"""Basic smoke tests for the trained forecast models and the forecast API.

Run with the project interpreter (needs scikit-learn/pandas/joblib) and node on
PATH:

    .venv/bin/python tests/test_forecast_api.py -v

Covers:
  1. model loading      - each bundle opens and predicts a probability in [0, 1]
  2. API response shape - /api/forecast returns the documented structure
  3. probability bounds - every horizon (and the ML layer) stays within range
  4. forecast anchor    - the ML layer is anchored to the dataset's LAST row
                          (read from the CSV, not hard-coded), freshness agrees,
                          and the anchor cannot silently regress to 2022-08-31
  5. headline           - the reported probability IS the RF probability; the
                          legacy engine is reported separately, never blended
  6. persistence        - latest dataset level vs the baseline threshold, both
                          read from the files

The API tests start their own server on a free port and shut it down afterwards;
nothing external is contacted.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "naraj_dashboard" / "data" / "ml_models"
DATASET = ROOT / "naraj_dashboard" / "data" / "hf" / "forecast_dataset.csv"
INGEST_STATUS = ROOT / "naraj_dashboard" / "data" / "cwc" / "ingestion_status.json"
HORIZONS = ("6h", "12h", "24h")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def hour_key(value):
    """Normalise an ISO or pandas-style timestamp to 'YYYY-MM-DD HH:MM'."""
    if not value:
        return None
    return str(value).strip().replace("T", " ")[:16]


def dataset_latest_timestamp():
    """Newest timestamp in the served dataset (fixed-width, so max() is safe)."""
    with DATASET.open(newline="", encoding="utf-8") as fh:
        stamps = [row["timestamp"] for row in csv.DictReader(fh) if row.get("timestamp")]
    if not stamps:
        raise AssertionError(f"no timestamps in {DATASET}")
    return max(stamps)


def dataset_last_row():
    """Final row of the dataset, parsed without loading the whole 24 MB file."""
    with DATASET.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - 65536))
        chunk = fh.read().decode("utf-8", "replace")
    lines = [line for line in chunk.split("\n") if line.strip()]
    with DATASET.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    values = next(csv.reader([lines[-1].rstrip("\r")]))
    return dict(zip(header, values))


def baseline_threshold():
    payload = json.loads((MODEL_DIR / "hf_forecast_baseline.json").read_text(encoding="utf-8"))
    return float(payload["label"]["threshold_m"])


class ModelLoadingTests(unittest.TestCase):
    def test_bundles_load_and_predict_in_range(self):
        try:
            import joblib
            import pandas as pd
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"training deps unavailable: {exc}")

        self.assertTrue(DATASET.exists(), f"dataset missing: {DATASET}")
        frame = pd.read_csv(DATASET).sort_values("timestamp")
        row = frame.iloc[-1]

        for h in HORIZONS:
            with self.subTest(horizon=h):
                path = MODEL_DIR / f"hf_forecast_{h}.pkl"
                self.assertTrue(path.exists(), f"bundle missing: {path}")
                bundle = joblib.load(path)
                for key in ("model", "imputer", "features"):
                    self.assertIn(key, bundle, f"{path.name} missing {key!r}")

                features = bundle["features"]
                self.assertGreater(len(features), 10)
                missing = [c for c in features if c not in frame.columns]
                self.assertEqual(missing, [], f"{path.name} expects unknown features: {missing[:5]}")

                x = row[features].to_frame().T
                p = float(bundle["model"].predict_proba(bundle["imputer"].transform(x))[0, 1])
                self.assertGreaterEqual(p, 0.0)
                self.assertLessEqual(p, 1.0)


class ForecastApiTests(unittest.TestCase):
    process = None
    port = None

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ)
        env["PORT"] = str(cls.port)
        env["HOST"] = "127.0.0.1"
        # the server spawns `python3 ml_serve.py`, which must find scikit-learn
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

        cls.process = subprocess.Popen(
            ["node", "naraj_dashboard/server.js"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

        deadline = time.time() + 40
        last_error = None
        while time.time() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError("server exited during startup: " + cls.process.stderr.read().decode("utf-8", "replace")[-800:])
            try:
                status, body = http_json(f"http://127.0.0.1:{cls.port}/api/health", timeout=3)
                if status == 200 and body.get("status") == "online":
                    return
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
            time.sleep(0.5)
        raise RuntimeError(f"server did not become ready on port {cls.port}: {last_error}")

    @classmethod
    def tearDownClass(cls):
        if cls.process and cls.process.poll() is None:
            try:
                os.killpg(os.getpgid(cls.process.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                cls.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(cls.process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_forecast_response_shape(self):
        status, body = http_json(f"http://127.0.0.1:{self.port}/api/forecast?station=naraj")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "success", f"unexpected body: {str(body)[:300]}")

        forecast = body.get("forecast")
        self.assertIsInstance(forecast, dict)
        for h in HORIZONS:
            with self.subTest(horizon=h):
                item = forecast.get(h)
                self.assertIsInstance(item, dict, f"missing horizon {h}")
                self.assertIn("flood_probability_percent", item)
                self.assertIn("risk", item)
                self.assertIsInstance(item["flood_probability_percent"], (int, float))
                self.assertIn(str(item["risk"]).upper(), {"LOW", "MEDIUM", "MODERATE", "HIGH"})

        self.assertIn(body.get("overall_risk"), {"LOW", "MEDIUM", "MODERATE", "HIGH"})
        self.assertIsInstance(body.get("forecast_cone"), list)

    def test_probabilities_in_range(self):
        _, body = http_json(f"http://127.0.0.1:{self.port}/api/forecast?station=naraj")
        for h in HORIZONS:
            with self.subTest(horizon=h):
                pct = body["forecast"][h]["flood_probability_percent"]
                self.assertGreaterEqual(pct, 0.0)
                self.assertLessEqual(pct, 100.0)
                ml = body["forecast"][h].get("ml_probability_percent")
                if ml is not None:
                    self.assertGreaterEqual(ml, 0.0)
                    self.assertLessEqual(ml, 100.0)

    def test_observation_freshness_reported(self):
        _, body = http_json(f"http://127.0.0.1:{self.port}/api/forecast?station=naraj")
        fresh = body.get("observation_freshness")
        self.assertIsInstance(fresh, dict, "observation_freshness missing")
        self.assertIn("latest_observation", fresh)
        self.assertIn("stale", fresh)
        self.assertIsInstance(fresh["stale"], bool)
        self.assertEqual(fresh.get("threshold_hours"), 48)
        if fresh.get("age_hours") is not None:
            self.assertEqual(fresh["stale"], fresh["age_hours"] > 48)

    def test_health_reports_ingestion_state_without_inventing_freshness(self):
        """The status file is a gitignored run snapshot: absent in a fresh clone."""
        status, body = http_json(f"http://127.0.0.1:{self.port}/api/health")
        self.assertEqual(status, 200)
        fresh = body.get("data_freshness")
        self.assertIsInstance(fresh, dict, "data_freshness missing from /api/health")
        if INGEST_STATUS.exists():
            self.assertIn(fresh.get("status"), {"reported", "example"})
            self.assertIn("latest_observation", fresh)
            self.assertIn(fresh.get("stale"), {True, False, None})
        else:
            self.assertEqual(fresh.get("status"), "not_run")
            self.assertEqual(fresh.get("message"), "no ingestion run yet")
            self.assertIsNone(fresh.get("latest_observation"))
            self.assertIsNone(fresh.get("stale"), "must not invent a stale verdict")

    # -- forecast anchor regression guards ---------------------------------

    def forecast_with_ml(self, timeout=90):
        """Forecast response, waiting for the ml_serve.py warm-up to finish.

        The server answers /api/health before the ML subprocess has loaded its
        pickles, so a single early request would legitimately have no ML layer.
        """
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            _, body = http_json(f"http://127.0.0.1:{self.port}/api/forecast?station=naraj")
            last = body
            if (body.get("ml_result") or {}).get("as_of"):
                return body
            time.sleep(1.0)
        self.fail(f"ML bridge never became ready: {str((last or {}).get('ml'))[:300]}")

    def test_ml_as_of_equals_dataset_latest_row(self):
        """The ML layer must predict from the newest row the dataset contains."""
        body = self.forecast_with_ml()
        ml = body.get("ml_result") or {}
        self.assertTrue(ml, f"ML layer missing from response: {body.get('ml')}")
        self.assertEqual(
            hour_key(ml.get("as_of")),
            hour_key(dataset_latest_timestamp()),
            "ml_result.as_of does not match the dataset's latest timestamp",
        )

    def test_freshness_latest_observation_matches_ml_as_of(self):
        body = self.forecast_with_ml()
        fresh = body["observation_freshness"]
        ml_as_of = (body.get("ml_result") or {}).get("as_of")
        self.assertTrue(ml_as_of, "ML layer missing")
        self.assertEqual(hour_key(fresh.get("latest_observation")), hour_key(ml_as_of))
        self.assertEqual(hour_key(fresh.get("latest_observation")), hour_key(dataset_latest_timestamp()))
        # The dataset ends in 2025, so the true age is ~10 months: still stale.
        self.assertGreater(fresh.get("age_days") or 0, 30)
        self.assertIn(fresh.get("latest_observation_source"), {"ml_dataset", "statistical_engine"})

    def test_anchor_does_not_regress_to_august_2022(self):
        """Guard the bug itself: the engine's Aug-2022 hourly end must not
        become the ML anchor again."""
        body = self.forecast_with_ml()
        anchors = body.get("forecast_anchors") or {}
        ml_as_of = hour_key((body.get("ml_result") or {}).get("as_of"))
        self.assertNotEqual(ml_as_of, "2022-08-31 00:00", "ML anchor regressed to 2022-08-31")
        self.assertGreaterEqual(int((ml_as_of or "0")[:4]), 2025)
        self.assertEqual(hour_key(anchors.get("statistical_engine_reference_time")), "2022-08-31 00:00")
        self.assertFalse(anchors.get("anchors_aligned"))
        # The headline no longer mixes the two moments, so this stays false.
        self.assertFalse(anchors.get("ensemble_mixes_anchors"))
        self.assertEqual(anchors.get("headline_source"), "rf_model")

    # -- headline = RF only; legacy engine stays separate -------------------

    def test_headline_probability_is_the_ml_probability(self):
        body = self.forecast_with_ml()
        self.assertEqual(body.get("headline_source"), "rf_model")
        for h in HORIZONS:
            with self.subTest(horizon=h):
                item = body["forecast"][h]
                self.assertIn("ml_probability_percent", item)
                self.assertAlmostEqual(
                    float(item["flood_probability_percent"]),
                    float(item["ml_probability_percent"]),
                    places=6,
                    msg="headline is not the RF probability",
                )
                # risk band comes from the headline value, not the old blend
                expected = "HIGH" if item["flood_probability_percent"] >= 75 else (
                    "MODERATE" if item["flood_probability_percent"] >= 25 else "LOW"
                )
                self.assertEqual(item["risk"], expected)
                self.assertNotIn("ml_weight", item)

    def test_legacy_engine_present_and_separate(self):
        body = self.forecast_with_ml()
        legacy = body.get("legacy_engine")
        self.assertIsInstance(legacy, dict, "legacy_engine block missing")
        self.assertIn("2022-08-31", legacy.get("label", ""))
        self.assertIn("not part of the headline", legacy.get("note", ""))
        self.assertEqual(hour_key(legacy.get("reference_time")), "2022-08-31 00:00")
        for h in HORIZONS:
            with self.subTest(horizon=h):
                item = legacy["forecast"][h]
                self.assertIn("flood_probability_percent", item)
                self.assertGreaterEqual(float(item["flood_probability_percent"]), 0.0)
                self.assertLessEqual(float(item["flood_probability_percent"]), 100.0)
        # the engine result is NOT what the headline reports
        self.assertGreaterEqual(len(legacy["forecast"]), 3)

    def test_legacy_headline_for_station_without_ml(self):
        """Stations the RF does not serve keep the engine headline, labelled."""
        _, body = http_json(
            f"http://127.0.0.1:{self.port}/api/forecast?station=nimapara"
        )
        self.assertEqual(body.get("status"), "success", str(body)[:300])
        self.assertEqual(body.get("headline_source"), "legacy_engine")
        self.assertFalse(body.get("ml_enabled"))
        self.assertIn("legacy_engine", body)
        self.assertEqual(
            body["forecast_anchors"].get("headline_source"), "legacy_engine"
        )

    # -- persistence indicator ----------------------------------------------

    def test_persistence_indicator_uses_dataset_and_baseline_files(self):
        body = self.forecast_with_ml()
        persist = body.get("persistence") or {}
        self.assertTrue(persist.get("available"), f"persistence unavailable: {persist}")
        row = dataset_last_row()
        self.assertAlmostEqual(
            float(persist["level_m"]), float(row["naraj_water_level_m"]), places=6
        )
        self.assertEqual(hour_key(persist["level_as_of"]), hour_key(row["timestamp"]))
        self.assertAlmostEqual(
            float(persist["threshold_m"]), baseline_threshold(), places=6
        )
        self.assertEqual(
            bool(persist["above_threshold"]),
            float(row["naraj_water_level_m"]) >= baseline_threshold(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
