"""Tests for the performance baseline module."""

import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.perf_baseline import (
    PerfBaseline,
    PerfSample,
    CPU_WARNING,
    CPU_CRITICAL,
    TARGET_RESOURCE_REDUCTION,
)


class TestPerfBaseline(unittest.TestCase):
    def setUp(self):
        self.tmpdir = pathlib.Path(tempfile.mkdtemp())
        self.pb = PerfBaseline(data_dir=self.tmpdir)

    def test_take_sample(self):
        sample = self.pb.take_sample()
        self.assertIsInstance(sample, PerfSample)
        self.assertTrue(len(sample.timestamp) > 0)
        self.assertGreaterEqual(sample.cpu_percent, 0.0)
        self.assertGreaterEqual(sample.mem_percent, 0.0)

    def test_compute_score(self):
        score = self.pb._compute_score([10, 20, 30], [40, 50], [60])
        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_compute_score_all_zero(self):
        score = self.pb._compute_score([0, 0], [0, 0], [0])
        self.assertGreater(score, 80)

    def test_baseline_persistence(self):
        baseline = self.pb.establish_baseline(duration_sec=2, interval_sec=1)
        self.assertIsNotNone(self.pb.baseline_file)
        self.assertTrue(self.pb.baseline_file.exists())
        data = json.loads(self.pb.baseline_file.read_text(encoding="utf-8"))
        self.assertIn("cpu_avg", data)
        self.assertIn("score", data)

    def test_track_trend_no_baseline(self):
        trend = self.pb.track_trend()
        self.assertFalse(trend["baseline"])

    def test_track_trend_with_baseline(self):
        self.pb.establish_baseline(duration_sec=2, interval_sec=1)
        trend = self.pb.track_trend()
        self.assertTrue(trend["baseline"])
        self.assertIn("trend", trend)
        self.assertIn("cpu_delta", trend)

    def test_get_emergency_actions_normal(self):
        with patch("psutil.cpu_percent", return_value=30.0), \
             patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value.percent = 40.0
            actions = self.pb.get_emergency_actions()
            self.assertEqual(len(actions), 1)
            self.assertEqual(actions[0]["level"], "ok")

    def test_get_emergency_actions_warning(self):
        with patch("psutil.cpu_percent", return_value=85.0), \
             patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value.percent = 70.0
            actions = self.pb.get_emergency_actions()
            self.assertGreater(len(actions), 0)
            levels = [a["level"] for a in actions]
            self.assertIn("warning", levels)

    def test_get_emergency_actions_critical(self):
        with patch("psutil.cpu_percent", return_value=95.0), \
             patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value.percent = 80.0
            actions = self.pb.get_emergency_actions()
            levels = [a["level"] for a in actions]
            self.assertIn("critical", levels)
            cmds = [a["command"] for a in actions]
            self.assertTrue(any("kubectl scale" in c for c in cmds))

    def test_optimization_progress_no_baseline(self):
        result = self.pb.get_optimization_progress()
        self.assertFalse(result["baseline"])

    def test_optimization_progress_with_baseline(self):
        self.pb.establish_baseline(duration_sec=2, interval_sec=1)
        result = self.pb.get_optimization_progress()
        self.assertTrue(result["baseline"])
        self.assertIn("targets", result)
        self.assertIn("current", result)
        self.assertIn("targets_met", result)

    def test_run_full_check(self):
        result = self.pb.run_full_check()
        self.assertIn("timestamp", result)
        self.assertIn("sample", result)
        self.assertIn("trend", result)
        self.assertIn("emergency_actions", result)
        self.assertIn("optimization_progress", result)

    def test_target_constants(self):
        self.assertEqual(CPU_WARNING, 80.0)
        self.assertEqual(CPU_CRITICAL, 90.0)
        self.assertEqual(TARGET_RESOURCE_REDUCTION, 0.40)


if __name__ == "__main__":
    unittest.main()
