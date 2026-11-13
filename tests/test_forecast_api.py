#!/usr/bin/env python3
"""Basic smoke tests for the trained forecast models and the forecast API.

Run with the project interpreter (needs scikit-learn/pandas/joblib) and node on
PATH:

    .venv/bin/python tests/test_forecast_api.py -v

Covers:
  1. model loading      - each bundle opens and predicts a probability in [0, 1]
  2. API response shape - /api/forecast returns the documented structure
  3. probability bounds - every horizon (and the ML layer) stays within range

The API tests start their own server on a free port and shut it down afterwards;
nothing external is contacted.
"""

from __future__ import annotations

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
HORIZONS = ("6h", "12h", "24h")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
