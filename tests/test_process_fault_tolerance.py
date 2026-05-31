"""Unit tests for ProcessFaultTolerance."""

import glob
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.process_fault_tolerance import ProcessFaultTolerance


class TestCheckWatchdogOverhead(unittest.TestCase):
    """Tests for check_watchdog_overhead."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_no_watchdog_processes(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 1, "name": "python", "cmdline": ["python", "main.py"]}
        mock_iter.return_value = [mock_proc]
        result = self.ft.check_watchdog_overhead()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["cpu_percent"] == 0.0
        assert result["processes_found"] == 0

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_watchdog_under_threshold(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 100,
            "name": "watchdog",
            "cmdline": ["python", "watchdog.py"],
            "cpu_percent": 2.0,
        }
        mock_proc.cpu_percent.return_value = 2.0
        mock_iter.return_value = [mock_proc]
        result = self.ft.check_watchdog_overhead()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["cpu_percent"] == 2.0

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_watchdog_over_threshold(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 100,
            "name": "watchdog",
            "cmdline": ["python", "watchdog.py"],
            "cpu_percent": 8.0,
        }
        mock_proc.cpu_percent.return_value = 8.0
        mock_iter.return_value = [mock_proc]
        result = self.ft.check_watchdog_overhead()
        assert result["status"] == "warning"
        assert result["flagged"] is True
        assert result["cpu_percent"] == 8.0

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_watchdog_in_cmdline(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 101,
            "name": "python",
            "cmdline": ["python", "my_watchdog_service.py"],
            "cpu_percent": 1.0,
        }
        mock_proc.cpu_percent.return_value = 1.0
        mock_iter.return_value = [mock_proc]
        result = self.ft.check_watchdog_overhead()
        assert result["status"] == "ok"
        assert result["processes_found"] == 1

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_watchdog_picks_highest_cpu(self, mock_iter):
        mock_low = MagicMock()
        mock_low.info = {
            "pid": 10,
            "name": "watchdog",
            "cmdline": [],
            "cpu_percent": 1.0,
        }
        mock_low.cpu_percent.return_value = 1.0
        mock_high = MagicMock()
        mock_high.info = {
            "pid": 20,
            "name": "watchdog",
            "cmdline": [],
            "cpu_percent": 10.0,
        }
        mock_high.cpu_percent.return_value = 10.0
        mock_iter.return_value = [mock_low, mock_high]
        result = self.ft.check_watchdog_overhead()
        assert result["flagged"] is True
        assert result["cpu_percent"] == 10.0
        assert result["processes_found"] == 2

    @patch("core.process_fault_tolerance.psutil.process_iter")
    def test_handles_nosuch_process(self, mock_iter):
        mock_proc = MagicMock()
        mock_proc.info = {"pid": 1, "name": "python", "cmdline": ["main.py"]}
        mock_proc.cpu_percent.side_effect = __import__("psutil").NoSuchProcess(1)
        mock_iter.return_value = [mock_proc]
        result = self.ft.check_watchdog_overhead()
        assert result["flagged"] is False


class TestCheckMemoryFragmentation(unittest.TestCase):
    """Tests for check_memory_fragmentation."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    @patch("core.process_fault_tolerance.psutil.virtual_memory")
    def test_low_fragmentation(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=12 * (1024 ** 3),
            used=4 * (1024 ** 3),
            percent=25.0,
        )
        result = self.ft.check_memory_fragmentation()
        assert result["fragmentation_percent"] == pytest.approx(25.0, rel=1e-2)
        assert result["status"] == "ok"
        assert result["flagged"] is False

    @patch("core.process_fault_tolerance.psutil.virtual_memory")
    def test_high_fragmentation(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=8 * (1024 ** 3),
            used=8 * (1024 ** 3),
            percent=50.0,
        )
        result = self.ft.check_memory_fragmentation()
        assert result["fragmentation_percent"] == pytest.approx(50.0, rel=1e-2)
        assert result["status"] == "warning"
        assert result["flagged"] is True

    @patch("core.process_fault_tolerance.psutil.virtual_memory")
    def test_total_gb_reported(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=32 * (1024 ** 3),
            available=28 * (1024 ** 3),
            used=4 * (1024 ** 3),
            percent=12.5,
        )
        result = self.ft.check_memory_fragmentation()
        assert result["total_gb"] == pytest.approx(32.0, rel=1e-2)
        assert result["available_gb"] == pytest.approx(28.0, rel=1e-2)

    @patch("core.process_fault_tolerance.psutil.virtual_memory")
    def test_custom_threshold(self, mock_mem):
        ft = ProcessFaultTolerance(config={"memory_fragmentation_threshold": 10.0})
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=14 * (1024 ** 3),
            used=2 * (1024 ** 3),
            percent=12.5,
        )
        result = ft.check_memory_fragmentation()
        assert result["threshold"] == 10.0
        assert result["fragmentation_percent"] == pytest.approx(12.5, rel=1e-2)
        assert result["flagged"] is True


class TestCheckSignalLatency(unittest.TestCase):
    """Tests for check_signal_latency."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    @patch("core.process_fault_tolerance.subprocess.Popen")
    @patch("core.process_fault_tolerance.time.monotonic")
    def test_latency_under_threshold(self, mock_time, mock_popen):
        mock_time.side_effect = [0.0, 0.02]
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        result = self.ft.check_signal_latency()
        assert result["latency_seconds"] == pytest.approx(0.02, rel=1e-2)
        assert result["flagged"] is False
        assert result["status"] == "ok"

    @patch("core.process_fault_tolerance.subprocess.Popen")
    @patch("core.process_fault_tolerance.time.monotonic")
    def test_latency_over_threshold(self, mock_time, mock_popen):
        mock_time.side_effect = [0.0, 2.5]
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        result = self.ft.check_signal_latency()
        assert result["latency_seconds"] == pytest.approx(2.5, rel=1e-2)
        assert result["flagged"] is True
        assert result["status"] == "warning"

    @patch("core.process_fault_tolerance.subprocess.Popen")
    @patch("core.process_fault_tolerance.time.monotonic")
    def test_subprocess_timeout_kills_process(self, mock_time, mock_popen):
        mock_time.side_effect = [0.0, 5.0]
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=3)
        mock_popen.return_value = mock_proc
        result = self.ft.check_signal_latency()
        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_called()

    @patch("core.process_fault_tolerance.subprocess.Popen")
    @patch("core.process_fault_tolerance.time.monotonic")
    def test_custom_threshold_flagged(self, mock_time, mock_popen):
        ft = ProcessFaultTolerance(config={"signal_latency_threshold": 0.01})
        mock_time.side_effect = [1.0, 1.5]
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        result = ft.check_signal_latency()
        assert result["threshold"] == 0.01
        assert result["flagged"] is True

    @patch("core.process_fault_tolerance.subprocess.Popen")
    @patch("core.process_fault_tolerance.time.monotonic")
    def test_custom_threshold_not_flagged(self, mock_time, mock_popen):
        ft = ProcessFaultTolerance(config={"signal_latency_threshold": 5.0})
        mock_time.side_effect = [0.0, 0.3]
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc
        result = ft.check_signal_latency()
        assert result["threshold"] == 5.0
        assert result["flagged"] is False
        assert result["status"] == "ok"


class TestCheckCrashDumpSize(unittest.TestCase):
    """Tests for check_crash_dump_size."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    def _make_ctx_pattern_mock(self):
        """Create a mock for /proc/sys/kernel/core_pattern that returns a string."""
        ctx_mock = MagicMock()
        ctx_mock.exists.return_value = True
        ctx_mock.read_text.return_value = "|/usr/lib/systemd/systemd-coredump %P %u %g"
        return ctx_mock

    @patch("core.process_fault_tolerance.glob.glob")
    @patch("core.process_fault_tolerance.Path")
    def test_no_dumps(self, mock_path_cls, mock_glob):
        mock_glob.return_value = []
        mock_path_cls.return_value = self._make_ctx_pattern_mock()
        result = self.ft.check_crash_dump_size()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["largest_mb"] == 0.0
        assert result["dump_count"] == 0

    @patch("core.process_fault_tolerance.glob.glob")
    @patch("core.process_fault_tolerance.Path")
    def test_small_dumps_not_flagged(self, mock_path_cls, mock_glob):
        mock_glob.return_value = ["/tmp/core.123"]
        mock_path_cls.return_value = self._make_ctx_pattern_mock()

        real_file = MagicMock()
        real_file.is_file.return_value = True
        real_file.stat.return_value.st_size = 100 * 1024 * 1024

        with patch("pathlib.Path.is_file", return_value=True), patch(
            "pathlib.Path.stat", return_value=real_file.stat.return_value
        ):
            result = self.ft.check_crash_dump_size()
            assert result["flagged"] is False

    def test_large_dump_flagged(self):
        stat_mock = MagicMock()
        stat_mock.st_size = 600 * 1024 * 1024

        real_path_instance = MagicMock()
        real_path_instance.is_file.return_value = True
        real_path_instance.stat.return_value = stat_mock
        real_path_instance.name = "core.456"

        ctx_mock = self._make_ctx_pattern_mock()

        def path_side_effect(p):
            if str(p) == "/proc/sys/kernel/core_pattern":
                return ctx_mock
            return real_path_instance

        with patch("core.process_fault_tolerance.Path", side_effect=path_side_effect), patch(
            "core.process_fault_tolerance.glob.glob",
            return_value=["/tmp/core.456"],
        ):
            result = self.ft.check_crash_dump_size()
            assert result["flagged"] is True
            assert result["largest_mb"] == pytest.approx(600.0, rel=1e-2)

    @patch("core.process_fault_tolerance.glob.glob")
    @patch("core.process_fault_tolerance.Path")
    def test_custom_threshold(self, mock_path_cls, mock_glob):
        ft = ProcessFaultTolerance(config={"crash_dump_size_threshold_mb": 100})
        mock_glob.return_value = []
        mock_path_cls.return_value = self._make_ctx_pattern_mock()
        result = ft.check_crash_dump_size()
        assert result["threshold_mb"] == 100


class TestCheckIPCBottleneck(unittest.TestCase):
    """Tests for check_ipc_bottleneck."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    @patch("core.process_fault_tolerance.psutil.process_iter")
    @patch("core.process_fault_tolerance.Path")
    @patch("core.process_fault_tolerance.time")
    def test_low_ctx_switches(self, mock_time_cls, mock_path_cls, mock_iter):
        stat_file = MagicMock()
        stat_file.exists.return_value = True
        stat_file.read_text.return_value = "ctxt 5000\n"
        mock_path_cls.return_value = stat_file
        mock_time_cls.sleep.return_value = None
        result = self.ft.check_ipc_bottleneck()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    @patch("core.process_fault_tolerance.psutil.process_iter")
    @patch("core.process_fault_tolerance.Path")
    @patch("core.process_fault_tolerance.time")
    def test_high_ctx_switches(self, mock_time_cls, mock_path_cls, mock_iter):
        stat_file = MagicMock()
        stat_file.exists.return_value = True
        stat_file.read_text.side_effect = [
            "ctxt 5000\n",
            "ctxt 35000\n",
        ]
        mock_path_cls.return_value = stat_file
        mock_time_cls.sleep.return_value = None
        result = self.ft.check_ipc_bottleneck()
        assert result["flagged"] is True
        assert result["status"] == "warning"

    @patch("core.process_fault_tolerance.psutil.process_iter")
    @patch("core.process_fault_tolerance.Path")
    @patch("core.process_fault_tolerance.time")
    def test_proc_stat_unavailable_fallback(self, mock_time_cls, mock_path_cls, mock_iter):
        stat_file = MagicMock()
        stat_file.exists.return_value = False
        mock_path_cls.return_value = stat_file

        mock_proc = MagicMock()
        mock_switches = MagicMock()
        mock_switches.voluntary = 3000
        mock_proc.num_ctx_switches.return_value = mock_switches
        mock_iter.return_value = [mock_proc]

        result = self.ft.check_ipc_bottleneck()
        assert result["status"] == "ok"
        assert result["ctx_switches_per_sec"] == 3000

    @patch(
        "core.process_fault_tolerance.ProcessFaultTolerance._measure_ctx_switches",
        return_value=7500,
    )
    def test_custom_threshold(self, mock_measure):
        ft = ProcessFaultTolerance(config={"ipc_context_switch_threshold": 5000})
        result = ft.check_ipc_bottleneck()
        assert result["threshold"] == 5000
        assert result["flagged"] is True

    @patch(
        "core.process_fault_tolerance.ProcessFaultTolerance._measure_ctx_switches",
        return_value=3000,
    )
    def test_custom_threshold_not_flagged(self, mock_measure):
        ft = ProcessFaultTolerance(config={"ipc_context_switch_threshold": 5000})
        result = ft.check_ipc_bottleneck()
        assert result["flagged"] is False
        assert result["status"] == "ok"


class TestRunAll(unittest.TestCase):
    """Tests for run_all."""

    def setUp(self):
        self.ft = ProcessFaultTolerance()

    @patch.object(ProcessFaultTolerance, "check_watchdog_overhead")
    @patch.object(ProcessFaultTolerance, "check_memory_fragmentation")
    @patch.object(ProcessFaultTolerance, "check_signal_latency")
    @patch.object(ProcessFaultTolerance, "check_crash_dump_size")
    @patch.object(ProcessFaultTolerance, "check_ipc_bottleneck")
    def test_all_ok(
        self, mock_ipc, mock_dump, mock_signal, mock_mem, mock_watch
    ):
        mock_watch.return_value = {"status": "ok", "flagged": False}
        mock_mem.return_value = {"status": "ok", "flagged": False}
        mock_signal.return_value = {"status": "ok", "flagged": False}
        mock_dump.return_value = {"status": "ok", "flagged": False}
        mock_ipc.return_value = {"status": "ok", "flagged": False}
        result = self.ft.run_all()
        assert result["overall_status"] == "ok"
        assert result["flagged_checks"] == []
        assert "watchdog_overhead" in result
        assert "memory_fragmentation" in result
        assert "signal_latency" in result
        assert "crash_dump_size" in result
        assert "ipc_bottleneck" in result
        assert "timestamp" in result

    @patch.object(ProcessFaultTolerance, "check_watchdog_overhead")
    @patch.object(ProcessFaultTolerance, "check_memory_fragmentation")
    @patch.object(ProcessFaultTolerance, "check_signal_latency")
    @patch.object(ProcessFaultTolerance, "check_crash_dump_size")
    @patch.object(ProcessFaultTolerance, "check_ipc_bottleneck")
    def test_some_flagged(
        self, mock_ipc, mock_dump, mock_signal, mock_mem, mock_watch
    ):
        mock_watch.return_value = {"status": "warning", "flagged": True}
        mock_mem.return_value = {"status": "ok", "flagged": False}
        mock_signal.return_value = {"status": "ok", "flagged": False}
        mock_dump.return_value = {"status": "ok", "flagged": False}
        mock_ipc.return_value = {"status": "ok", "flagged": False}
        result = self.ft.run_all()
        assert result["overall_status"] == "warning"
        assert "watchdog_overhead" in result["flagged_checks"]

    @patch.object(ProcessFaultTolerance, "check_watchdog_overhead")
    @patch.object(ProcessFaultTolerance, "check_memory_fragmentation")
    @patch.object(ProcessFaultTolerance, "check_signal_latency")
    @patch.object(ProcessFaultTolerance, "check_crash_dump_size")
    @patch.object(ProcessFaultTolerance, "check_ipc_bottleneck")
    def test_multiple_flagged(
        self, mock_ipc, mock_dump, mock_signal, mock_mem, mock_watch
    ):
        mock_watch.return_value = {"status": "warning", "flagged": True}
        mock_mem.return_value = {"status": "warning", "flagged": True}
        mock_signal.return_value = {"status": "ok", "flagged": False}
        mock_dump.return_value = {"status": "ok", "flagged": False}
        mock_ipc.return_value = {"status": "warning", "flagged": True}
        result = self.ft.run_all()
        assert result["overall_status"] == "warning"
        assert len(result["flagged_checks"]) == 3


class TestCustomConfig(unittest.TestCase):
    """Tests for custom threshold configuration."""

    def test_watchdog_threshold_override(self):
        ft = ProcessFaultTolerance(config={"watchdog_cpu_threshold": 10.0})
        assert ft._watchdog_cpu_thresh == 10.0

    def test_all_thresholds_override(self):
        ft = ProcessFaultTolerance(
            config={
                "watchdog_cpu_threshold": 15.0,
                "memory_fragmentation_threshold": 50.0,
                "signal_latency_threshold": 2.0,
                "crash_dump_size_threshold_mb": 1000,
                "ipc_context_switch_threshold": 50000,
            }
        )
        assert ft._watchdog_cpu_thresh == 15.0
        assert ft._mem_frag_thresh == 50.0
        assert ft._signal_latency_thresh == 2.0
        assert ft._crash_dump_thresh_mb == 1000
        assert ft._ipc_ctx_thresh == 50000

    def test_default_thresholds(self):
        ft = ProcessFaultTolerance()
        assert ft._watchdog_cpu_thresh == 5.0
        assert ft._mem_frag_thresh == 40.0
        assert ft._signal_latency_thresh == 1.0
        assert ft._crash_dump_thresh_mb == 500
        assert ft._ipc_ctx_thresh == 10000


if __name__ == "__main__":
    unittest.main()
