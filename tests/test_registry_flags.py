#!/usr/bin/env python3
"""Tests for the registry coordinate sanity check.

Run with any Python 3 (no third-party packages needed):

    python3 tests/test_registry_flags.py -v

Covers:
  1. the coarse bounding-box check flags a known-bad coordinate pair
  2. a plausible station inside its state is not flagged
  3. the committed registry carries the flags and the summary block
  4. flagging never changes coordinates or removes a station
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_india_registry.py"
REGISTRY = ROOT / "naraj_dashboard" / "data" / "india_cwc" / "stations.json"

spec = importlib.util.spec_from_file_location("build_india_registry", SCRIPT)
registry_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry_builder)


class CoordinateFlagTests(unittest.TestCase):
    def test_out_of_state_coordinates_are_flagged(self):
        # Changlang is recorded as Arunachal Pradesh but its coordinates are in
        # the western Himalaya; the check must catch that without knowing the
        # correct location.
        flag = registry_builder.coordinate_flag("Arunachal Pradesh", 33.27139, 76.16667)
        self.assertIsNotNone(flag)
        self.assertTrue(flag["coordinate_state_mismatch"])
        self.assertIn("outside", flag["detail"])
        self.assertIn("note", flag)

    def test_plausible_coordinates_are_not_flagged(self):
        self.assertIsNone(registry_builder.coordinate_flag("Odisha", 20.47167, 85.76556))
        self.assertIsNone(registry_builder.coordinate_flag("Kerala", 11.80806, 76.08417))

    def test_unknown_state_is_not_guessed(self):
        self.assertIsNone(registry_builder.coordinate_flag("Atlantis", 10.0, 76.0))

    def test_committed_registry_has_flags_and_summary(self):
        payload = json.loads(REGISTRY.read_text("utf-8"))
        stations = payload["stations"]
        flagged = [s for s in stations if s.get("data_quality")]
        self.assertEqual(len(stations), 842)
        self.assertGreaterEqual(len(flagged), 2)
        self.assertEqual(
            payload["data_quality"]["coordinate_check"]["flagged"], len(flagged)
        )
        names = {s["station"] for s in flagged}
        self.assertIn("Changlang", names)
        self.assertIn("Ziro", names)

    def test_flagging_does_not_move_or_drop_stations(self):
        before = json.loads(REGISTRY.read_text("utf-8"))["stations"]
        # Positional, not keyed by name: the registry can hold two gauges with
        # the same name and state at different coordinates.
        snapshot = [
            (s["station"], s["state"], s["latitude"], s["longitude"])
            for s in before
        ]
        rows = [dict(s) for s in before]
        flagged = registry_builder.apply_coordinate_flags(rows)
        self.assertEqual(len(rows), len(before))
        self.assertEqual(
            [
                (s["station"], s["state"], s["latitude"], s["longitude"])
                for s in rows
            ],
            snapshot,
        )
        self.assertEqual(
            {s["station"] for s in flagged},
            {s["station"] for s in before if s.get("data_quality")},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
