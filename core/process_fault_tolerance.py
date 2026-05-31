"""Process-level fault tolerance checks for Spider Diary.

Provides watchdog overhead, memory fragmentation, signal latency,
crash dump size, and IPC bottleneck detection with configurable
thresholds and structured status reports.
"""

import datetime
import glob
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

import psutil

logger = logging.getLogger(__name__)

WATCHDOG_CPU_THRESHOLD = 5.0
MEMORY_FRAGMENTATION_THRESHOLD = 40.0
SIGNAL_LATENCY_THRESHOLD = 1.0
CRASH_DUMP_SIZE_THRESHOLD_MB = 500
IPC_CTX_SWITCH_THRESHOLD = 10000


class ProcessFaultTolerance:
    """Process-level fault tolerance monitor.

    Runs diagnostics on watchdog overhead, memory fragmentation,
    signal latency, crash dump sizes, and IPC bottlenecks.
    """

    def __init__(self, config: Dict = None):
        """Initialize ProcessFaultTolerance.

        Args:
            config: Optional dict of threshold overrides.
        """
        self.config = config or {}
        self._watchdog_cpu_thresh = self.config.get(
            "watchdog_cpu_threshold", WATCHDOG_CPU_THRESHOLD
        )
        self._mem_frag_thresh = self.config.get(
            "memory_fragmentation_threshold", MEMORY_FRAGMENTATION_THRESHOLD
        )
        self._signal_latency_thresh = self.config.get(
            "signal_latency_threshold", SIGNAL_LATENCY_THRESHOLD
        )
        self._crash_dump_thresh_mb = self.config.get(
            "crash_dump_size_threshold_mb", CRASH_DUMP_SIZE_THRESHOLD_MB
        )
        self._ipc_ctx_thresh = self.config.get(
            "ipc_context_switch_threshold", IPC_CTX_SWITCH_THRESHOLD
        )

    def check_watchdog_overhead(self) -> Dict:
        """Check watchdog process CPU usage.

        Scans processes with 'watchdog' in name or cmdline and
        reports the highest CPU usage found.

        Returns:
            Dict with cpu_percent, threshold, flagged, and details.
        """
        max_cpu = 0.0
        watchdog_procs = []
        for proc in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                cmdline = " ".join(info.get("cmdline") or []).lower()
                if "watchdog" in name or "watchdog" in cmdline:
                    cpu = proc.cpu_percent(interval=0.1)
                    max_cpu = max(max_cpu, cpu)
                    watchdog_procs.append({"pid": info["pid"], "name": info["name"], "cpu": cpu})
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        flagged = max_cpu > self._watchdog_cpu_thresh
        result = {
            "cpu_percent": round(max_cpu, 2),
            "threshold": self._watchdog_cpu_thresh,
            "flagged": flagged,
            "processes_found": len(watchdog_procs),
            "details": watchdog_procs,
            "status": "warning" if flagged else "ok",
        }
        if flagged:
            logger.warning(
                "Watchdog overhead flagged: %.1f%% > %.1f%%", max_cpu, self._watchdog_cpu_thresh
            )
        return result

    def check_memory_fragmentation(self) -> Dict:
        """Check system memory fragmentation ratio.

        Uses available/total memory to derive an approximation
        of fragmentation. High fragmentation indicates inefficient
        memory allocation patterns.

        Returns:
            Dict with fragmentation_percent, threshold, flagged, and details.
        """
        mem = psutil.virtual_memory()
        total = mem.total
        available = mem.available
        used = mem.used
        if total == 0:
            fragmentation = 0.0
        else:
            fragmentation = round((1 - available / total) * 100, 2)

        flagged = fragmentation > self._mem_frag_thresh
        result = {
            "fragmentation_percent": fragmentation,
            "threshold": self._mem_frag_thresh,
            "flagged": flagged,
            "total_gb": round(total / (1024 ** 3), 2),
            "available_gb": round(available / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "status": "warning" if flagged else "ok",
        }
        if flagged:
            logger.warning(
                "Memory fragmentation flagged: %.1f%% > %.1f%%",
                fragmentation,
                self._mem_frag_thresh,
            )
        return result

    def check_signal_latency(self) -> Dict:
        """Measure SIGTERM delivery to handler registration latency.

        Starts a subprocess that registers a SIGTERM handler, then
        sends SIGTERM and measures the time the process takes to exit.
        This approximates the signal-to-exit pipeline delay.

        Returns:
            Dict with latency_seconds, threshold, flagged, and status.
        """
        script = (
            "import signal, time\n"
            "start = time.monotonic()\n"
            "def handler(signum, frame):\n"
            "    exit(0)\n"
            "signal.signal(signal.SIGTERM, handler)\n"
            "while True:\n"
            "    time.sleep(0.1)\n"
        )
        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=self._signal_latency_thresh + 2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            elapsed = round(time.monotonic() - start, 4)
        except Exception as e:
            logger.warning("Signal latency check failed: %s", e)
            elapsed = round(time.monotonic() - start, 4)

        flagged = elapsed > self._signal_latency_thresh
        result = {
            "latency_seconds": elapsed,
            "threshold": self._signal_latency_thresh,
            "flagged": flagged,
            "status": "warning" if flagged else "ok",
        }
        if flagged:
            logger.warning(
                "Signal latency flagged: %.4fs > %.1fs", elapsed, self._signal_latency_thresh
            )
        return result

    def check_crash_dump_size(self) -> Dict:
        """Check core dump file sizes on the system.

        Scans common core dump locations (/var/crash, /var/core,
        current working directory, system-configured pattern).

        Returns:
            Dict with largest_mb, threshold_mb, flagged, and dump_files.
        """
        dump_files: list = []
        search_patterns = [
            Path("/var/crash") / "*",
            Path("/var/core") / "*",
            Path.cwd() / "core*",
        ]
        core_pattern_path = Path("/proc/sys/kernel/core_pattern")
        if core_pattern_path.exists():
            pattern = core_pattern_path.read_text().strip()
            if "%" not in pattern:
                p = Path(pattern)
                if p.is_absolute() and p.parent.exists():
                    search_patterns.append(p.parent / "*")

        seen = set()
        for pattern_str in search_patterns:
            base_pattern = str(pattern_str)
            if base_pattern in seen:
                continue
            seen.add(base_pattern)
            for f in glob.glob(base_pattern):
                fp = Path(f)
                if fp.is_file() and ("core" in fp.name or "crash" in fp.name or "dump" in fp.name):
                    try:
                        size_mb = fp.stat().st_size / (1024 * 1024)
                    except OSError:
                        continue
                    dump_files.append({"path": str(fp), "size_mb": round(size_mb, 2)})

        dump_files.sort(key=lambda d: d["size_mb"], reverse=True)
        largest_mb = dump_files[0]["size_mb"] if dump_files else 0.0
        flagged = largest_mb > self._crash_dump_thresh_mb
        result = {
            "largest_mb": largest_mb,
            "threshold_mb": self._crash_dump_thresh_mb,
            "flagged": flagged,
            "dump_count": len(dump_files),
            "dump_files": dump_files[:10],
            "status": "warning" if flagged else "ok",
        }
        if flagged:
            logger.warning(
                "Crash dump size flagged: %.0fMB > %dMB", largest_mb, self._crash_dump_thresh_mb
            )
        return result

    def check_ipc_bottleneck(self) -> Dict:
        """Check IPC bottleneck via system-wide context switches.

        Reads context switches per second from /proc/stat on Linux
        or estimates from psutil on other platforms. High values
        indicate excessive process switching.

        Returns:
            Dict with ctx_switches_per_sec, threshold, flagged, and status.
        """
        ctx_switches = self._measure_ctx_switches()
        flagged = ctx_switches > self._ipc_ctx_thresh
        result = {
            "ctx_switches_per_sec": ctx_switches,
            "threshold": self._ipc_ctx_thresh,
            "flagged": flagged,
            "status": "warning" if flagged else "ok",
        }
        if flagged:
            logger.warning(
                "IPC bottleneck flagged: %d/s > %d/s", ctx_switches, self._ipc_ctx_thresh
            )
        return result

    @staticmethod
    def _read_proc_ctxt(stat_path: Path) -> int:
        """Read the ctxt value from /proc/stat.

        Args:
            stat_path: Path to /proc/stat.

        Returns:
            System-wide context switches since boot.
        """
        for line in stat_path.read_text().split("\n"):
            if line.startswith("ctxt "):
                return int(line.split()[1])
        return 0

    @staticmethod
    def _measure_ctx_switches() -> int:
        """Measure system-wide context switches per second.

        Reads /proc/stat on Linux; falls back to summing
        per-process voluntary context switches via psutil.

        Returns:
            Estimated context switches per second.
        """
        proc_stat_path = Path("/proc/stat")
        if proc_stat_path.exists():
            try:
                ctx1 = ProcessFaultTolerance._read_proc_ctxt(proc_stat_path)
                time.sleep(0.5)
                ctx2 = ProcessFaultTolerance._read_proc_ctxt(proc_stat_path)
                return max(0, int((ctx2 - ctx1) / 0.5))
            except (ValueError, IndexError, OSError):
                pass
        total = 0
        for proc in psutil.process_iter(["pid", "num_ctx_switches"]):
            try:
                switches = proc.num_ctx_switches()
                total += switches.voluntary
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
        return total

    def run_all(self) -> Dict:
        """Run all process fault tolerance checks.

        Returns:
            Dict containing all check results, overall_status,
            and timestamp.
        """
        watchdog = self.check_watchdog_overhead()
        memory_frag = self.check_memory_fragmentation()
        signal_lat = self.check_signal_latency()
        crash_dump = self.check_crash_dump_size()
        ipc = self.check_ipc_bottleneck()

        statuses = [
            watchdog["status"],
            memory_frag["status"],
            signal_lat["status"],
            crash_dump["status"],
            ipc["status"],
        ]
        if "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "ok"

        flagged_checks = [
            name
            for name, result in [
                ("watchdog_overhead", watchdog),
                ("memory_fragmentation", memory_frag),
                ("signal_latency", signal_lat),
                ("crash_dump_size", crash_dump),
                ("ipc_bottleneck", ipc),
            ]
            if result["flagged"]
        ]

        result = {
            "watchdog_overhead": watchdog,
            "memory_fragmentation": memory_frag,
            "signal_latency": signal_lat,
            "crash_dump_size": crash_dump,
            "ipc_bottleneck": ipc,
            "overall_status": overall_status,
            "flagged_checks": flagged_checks,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        logger.info("Process fault tolerance checks complete: overall_status=%s", overall_status)
        return result
