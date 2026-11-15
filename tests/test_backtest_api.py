#!/usr/bin/env python3
"""Tests for /api/backtest (Naraj, held-out test period only).

Run with the project interpreter (needs scikit-learn/pandas/joblib and node):

    .venv/bin/python tests/test_backtest_api.py -v

Covers:
  1. a valid in-period hour returns RF probabilities in [0, 1]
  2. the observed level and window outcomes match the CSV exactly
  3. timestamps outside the test period are rejected with a clear message
  4. non-hourly / unparseable timestamps are rejected
  5. stations without a model are refused
  6. the moments list is inside the test period and includes both crossing
     and quiet hours
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
DATASET = ROOT / "naraj_dashboard" / "data" / "hf" / "forecast_dataset.csv"
TEST_START = "2025-04-01 06:00:00"
TEST_END = "2025-12-30 23:00:00"
THRESHOLD = 24.28
HORIZONS = ("6h", "12h", "24h")
VALID_TIME = "2025-09-27 06:00:00"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def http_json(url, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def load_rows():
    with DATASET.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


ROWS = {row["timestamp"]: row for row in load_rows()}


def expected_window(stamp, hours):
    """Max level and threshold outcome in the following `hours` hours."""
    rows = load_rows()
    times = [r["timestamp"] for r in rows]
    i = times.index(stamp)
    levels = [float(r["naraj_water_level_m"]) for r in rows[i + 1 : i + 1 + hours]]
    if not levels:
        return None, None
    maximum = max(levels)
    return round(maximum, 2), maximum >= THRESHOLD


class BacktestApiTests(unittest.TestCase):
    process = None
    port = None

    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        env = dict(os.environ)
        env["PORT"] = str(cls.port)
        env["HOST"] = "127.0.0.1"
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
        ready = False
        while time.time() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError(
                    "server exited during startup: "
                    + cls.process.stderr.read().decode("utf-8", "replace")[-800:]
                )
            try:
                status, body = http_json(
                    f"http://127.0.0.1:{cls.port}/api/health", timeout=3
                )
                if status == 200 and body.get("status") == "online":
                    ready = True
                    break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.5)
        if not ready:
            raise RuntimeError("server did not become ready")

        # /api/health answers before ml_serve.py has loaded its pickles, so wait
        # for one real backtest response before any test asserts on probabilities.
        deadline = time.time() + 90
        last = None
        while time.time() < deadline:
            status, body = http_json(
                f"http://127.0.0.1:{cls.port}/api/backtest?station=naraj"
                f"&time={VALID_TIME.replace(' ', '%20')}",
                timeout=10,
            )
            last = body
            if status == 200 and body.get("status") == "success":
                return
            time.sleep(1.0)
        raise RuntimeError(f"ML bridge never became ready: {str(last)[:300]}")

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

    def url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def backtest(self, time_value, station="naraj"):
        from urllib.parse import quote

        return http_json(
            self.url(
                f"/api/backtest?station={quote(station)}&time={quote(time_value)}"
            )
        )

    def test_valid_time_returns_probabilities_in_range(self):
        status, body = self.backtest(VALID_TIME)
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "success", str(body)[:300])
        self.assertEqual(body.get("station"), "naraj")
        self.assertEqual(body.get("time"), VALID_TIME)
        self.assertAlmostEqual(float(body["threshold_m"]), THRESHOLD, places=2)
        for h in HORIZONS:
            with self.subTest(horizon=h):
                item = body["horizons"][h]
                p = item["probability"]
                self.assertIsInstance(p, (int, float))
                self.assertGreaterEqual(float(p), 0.0)
                self.assertLessEqual(float(p), 1.0)
                self.assertGreaterEqual(float(item["probability_percent"]), 0.0)
                self.assertLessEqual(float(item["probability_percent"]), 100.0)
                self.assertIn(item["risk"], {"LOW", "MODERATE", "HIGH"})

    def test_outcome_matches_csv(self):
        status, body = self.backtest(VALID_TIME)
        self.assertEqual(status, 200)
        row = ROWS[VALID_TIME]
        self.assertAlmostEqual(
            float(body["observed_level_m"]), float(row["naraj_water_level_m"]), places=2
        )
        for h in (6, 12, 24):
            max_level, exceeded = expected_window(VALID_TIME, h)
            item = body["horizons"][f"{h}h"]
            self.assertAlmostEqual(float(item["max_level_m"]), max_level, places=2)
            self.assertEqual(bool(item["threshold_exceeded"]), bool(exceeded))
            self.assertEqual(int(item["dataset_label"]), int(row[f"flood_next_{h}h"]))
            self.assertTrue(item["label_matches_window"])

    def test_persistence_baseline_is_at_or_above_threshold(self):
        status, body = self.backtest(VALID_TIME)
        self.assertEqual(status, 200)
        expected = float(body["observed_level_m"]) >= THRESHOLD
        self.assertEqual(bool(body["baseline"]["predicts_flood"]), expected)
        for h in HORIZONS:
            self.assertEqual(
                bool(body["horizons"][h]["baseline_predicts_flood"]), expected
            )

    def test_time_before_test_period_is_rejected(self):
        status, body = self.backtest("2025-01-01 00:00:00")
        self.assertEqual(status, 400)
        self.assertEqual(body.get("status"), "out_of_range")
        self.assertIn(TEST_START, body.get("message", ""))

    def test_time_after_test_period_is_rejected(self):
        status, body = self.backtest("2026-02-01 00:00:00")
        self.assertEqual(status, 400)
        self.assertEqual(body.get("status"), "out_of_range")
        self.assertIn(TEST_END, body.get("message", ""))

    def test_non_hourly_time_is_rejected(self):
        status, body = self.backtest("2025-09-27 06:30:00")
        self.assertEqual(status, 400)
        self.assertEqual(body.get("status"), "invalid_time")

    def test_unparseable_time_is_rejected(self):
        status, body = self.backtest("not-a-timestamp")
        self.assertEqual(status, 400)
        self.assertEqual(body.get("status"), "invalid_time")

    def test_onset_skill_endpoint_reports_validation_tuned_results(self):
        status, body = http_json(self.url("/api/backtest/onset-skill"))
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "success", str(body)[:200])
        self.assertIn("validation_period", body)
        self.assertIn("test_period", body)
        results = body.get("results") or {}
        for h in HORIZONS:
            with self.subTest(horizon=h):
                item = results[h]
                self.assertGreater(item["onsets"]["test_rows"], 0)
                self.assertGreater(item["onsets"]["test_positives"], 0)
                self.assertLessEqual(
                    item["onsets"]["test_positives"], item["onsets"]["test_rows"]
                )
                cut = item["rf"]["at_tuned_cutoff"]["cutoff"]
                self.assertGreater(cut, 0.0)
                self.assertLess(cut, 0.5)
                for name in ("roc_auc", "pr_auc"):
                    self.assertGreaterEqual(item["rf"]["test_skill"][name], 0.0)
                    self.assertGreaterEqual(item["baseline"]["test_skill"][name], 0.0)
                self.assertIn("summary", item["verdict"])

    def test_station_without_model_is_refused(self):
        status, body = self.backtest(VALID_TIME, station="alipingal")
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "station_not_supported")
        self.assertIn("Naraj only", body.get("reason", ""))

    def test_moments_are_inside_test_period_and_scored(self):
        status, body = http_json(self.url("/api/backtest/moments"))
        self.assertEqual(status, 200)
        self.assertEqual(body.get("status"), "success", str(body)[:300])
        items = body.get("items") or []
        self.assertGreaterEqual(len(items), 5)
        kinds = {i.get("kind") for i in items}
        self.assertIn("pre_crossing", kinds)
        self.assertIn("quiet", kinds)
        for item in items:
            self.assertGreaterEqual(item["time"], TEST_START)
            self.assertLessEqual(item["time"], TEST_END)
            result = item.get("result") or {}
            self.assertEqual(result.get("status"), "success", str(result)[:200])
            for h in HORIZONS:
                p = result["horizons"][h]["probability"]
                self.assertGreaterEqual(float(p), 0.0)
                self.assertLessEqual(float(p), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
