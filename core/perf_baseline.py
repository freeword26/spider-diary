"""Hardware stability baseline and performance calibration for Spider Diary.

Establishes performance baselines, tracks hardware degradation trends,
and provides emergency response recommendations based on system load.

Metrics are persisted to ``data/perf_baseline.json`` for trend analysis.
"""

import datetime
import json
import logging
import pathlib
import socket
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────

CPU_WARNING = 80.0
CPU_CRITICAL = 90.0
MEM_WARNING = 80.0
MEM_CRITICAL = 90.0
DISK_WARNING = 80.0
DISK_CRITICAL = 90.0
LOAD_WARNING = 4.0
LOAD_CRITICAL = 8.0

# Optimization targets
TARGET_RESOURCE_REDUCTION = 0.40
TARGET_RESPONSE_IMPROVEMENT = 0.60


# ── Data classes ────────────────────────────────────────────────

@dataclass
class PerfSample:
    """Single performance measurement."""
    timestamp: str = ""
    cpu_percent: float = 0.0
    mem_percent: float = 0.0
    disk_percent: float = 0.0
    net_bytes_sent: int = 0
    net_bytes_recv: int = 0
    io_read_bytes: int = 0
    io_write_bytes: int = 0


@dataclass
class BaselineRecord:
    """Established performance baseline."""
    hostname: str = ""
    created_at: str = ""
    updated_at: str = ""
    samples: List[Dict] = field(default_factory=list)
    cpu_avg: float = 0.0
    cpu_peak: float = 0.0
    mem_avg: float = 0.0
    mem_peak: float = 0.0
    disk_avg: float = 0.0
    load_avg: float = 0.0
    net_throughput_mbps: float = 0.0
    io_throughput_mbps: float = 0.0
    score: float = 100.0


@dataclass
class EmergencyAction:
    """Recommended emergency action when load exceeds thresholds."""
    trigger: str = ""
    action: str = ""
    command: str = ""
    level: str = "warning"


# ── Main class ──────────────────────────────────────────────────

class PerfBaseline:
    """Hardware stability baseline and performance calibration.

    Provides:
    - Baseline establishment via ``establish_baseline()``
    - Trend tracking via ``track_trend()``
    - Emergency response recommendations via ``get_emergency_actions()``
    - Optimization target progress via ``get_optimization_progress()``
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self.hostname = socket.gethostname()
        self.data_dir = data_dir or (Path.cwd() / "data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_file = self.data_dir / "perf_baseline.json"
        self._baseline: Optional[BaselineRecord] = None
        self._load_baseline()

    # ── Baseline persistence ─────────────────────────────────────

    def _load_baseline(self) -> None:
        if self.baseline_file.exists():
            try:
                data = json.loads(self.baseline_file.read_text(encoding="utf-8"))
                self._baseline = BaselineRecord(**data)
            except (json.JSONDecodeError, TypeError):
                self._baseline = None

    def _save_baseline(self) -> None:
        if self._baseline:
            self._baseline.updated_at = datetime.datetime.now().isoformat()
            self.baseline_file.write_text(
                json.dumps(asdict(self._baseline), indent=2, default=str),
                encoding="utf-8",
            )

    # ── Sampling ─────────────────────────────────────────────────

    def take_sample(self) -> PerfSample:
        """Capture a single performance snapshot."""
        net = psutil.net_io_counters()
        io = psutil.disk_io_counters()
        return PerfSample(
            timestamp=datetime.datetime.now().isoformat(),
            cpu_percent=psutil.cpu_percent(interval=0.5),
            mem_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage(str(Path.cwd())).percent,
            net_bytes_sent=net.bytes_sent,
            net_bytes_recv=net.bytes_recv,
            io_read_bytes=io.read_bytes if io else 0,
            io_write_bytes=io.write_bytes if io else 0,
        )

    def establish_baseline(self, duration_sec: int = 60, interval_sec: int = 5) -> BaselineRecord:
        """Run a baseline measurement over ``duration_sec`` seconds.

        Samples every ``interval_sec`` seconds and computes averages
        and peaks.  Stores the result to ``data/perf_baseline.json``.
        """
        logger.info("Establishing baseline: %ds at %ds intervals", duration_sec, interval_sec)
        samples: List[PerfSample] = []
        end_time = time.monotonic() + duration_sec

        while time.monotonic() < end_time:
            samples.append(self.take_sample())
            time.sleep(interval_sec)

        cpu_vals = [s.cpu_percent for s in samples]
        mem_vals = [s.mem_percent for s in samples]
        disk_vals = [s.disk_percent for s in samples]

        first_net = samples[0].net_bytes_sent + samples[0].net_bytes_recv
        last_net = samples[-1].net_bytes_sent + samples[-1].net_bytes_recv
        net_delta_mb = (last_net - first_net) / (1024 * 1024)
        duration_min = duration_sec / 60.0
        net_mbps = round(net_delta_mb / max(duration_min, 0.01), 2)

        first_io = samples[0].io_read_bytes + samples[0].io_write_bytes
        last_io = samples[-1].io_read_bytes + samples[-1].io_write_bytes
        io_delta_mb = (last_io - first_io) / (1024 * 1024)
        io_mbps = round(io_delta_mb / max(duration_min, 0.01), 2)

        try:
            load_avg = psutil.getloadavg()[0]
        except AttributeError:
            load_avg = psutil.cpu_percent(interval=0.1) / 100.0 * psutil.cpu_count()

        self._baseline = BaselineRecord(
            hostname=self.hostname,
            created_at=datetime.datetime.now().isoformat(),
            updated_at=datetime.datetime.now().isoformat(),
            samples=[asdict(s) for s in samples],
            cpu_avg=round(sum(cpu_vals) / len(cpu_vals), 1),
            cpu_peak=round(max(cpu_vals), 1),
            mem_avg=round(sum(mem_vals) / len(mem_vals), 1),
            mem_peak=round(max(mem_vals), 1),
            disk_avg=round(sum(disk_vals) / len(disk_vals), 1),
            load_avg=round(load_avg, 2),
            net_throughput_mbps=net_mbps,
            io_throughput_mbps=io_mbps,
            score=self._compute_score(cpu_vals, mem_vals, disk_vals),
        )
        self._save_baseline()
        logger.info("Baseline established: score=%.1f", self._baseline.score)
        return self._baseline

    def _compute_score(self, cpu: List[float], mem: List[float], disk: List[float]) -> float:
        """Compute a 0-100 health score from sampled metrics."""
        cpu_score = max(0, 100 - sum(cpu) / len(cpu))
        mem_score = max(0, 100 - sum(mem) / len(mem))
        disk_score = max(0, 100 - sum(disk) / len(disk))
        return round((cpu_score * 0.4 + mem_score * 0.35 + disk_score * 0.25), 1)

    # ── Trend tracking ───────────────────────────────────────────

    def track_trend(self) -> Dict:
        """Compare current metrics against the established baseline.

        Returns a dict with delta values and trend indicators.
        """
        sample = self.take_sample()
        if not self._baseline:
            return {"baseline": False, "current": asdict(sample)}

        cpu_delta = round(sample.cpu_percent - self._baseline.cpu_avg, 1)
        mem_delta = round(sample.mem_percent - self._baseline.mem_avg, 1)

        trend = "stable"
        if cpu_delta > 20 or mem_delta > 20:
            trend = "degrading"
        elif cpu_delta < -10 and mem_delta < -10:
            trend = "improving"

        return {
            "baseline": True,
            "baseline_date": self._baseline.created_at,
            "current": asdict(sample),
            "cpu_delta": cpu_delta,
            "mem_delta": mem_delta,
            "trend": trend,
            "baseline_score": self._baseline.score,
        }

    # ── Emergency response ────────────────────────────────────────

    def get_emergency_actions(self) -> List[Dict]:
        """Return recommended actions based on current system load."""
        actions: List[Dict] = []
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory().percent

        if cpu > CPU_CRITICAL or mem > MEM_CRITICAL:
            actions.append({
                "trigger": f"CPU {cpu}% or Memory {mem}% > critical threshold",
                "action": "Downgrade non-core services",
                "command": "kubectl scale deployment non-critical-service --replicas=1",
                "level": "critical",
            })
            actions.append({
                "trigger": "Resource-heavy containers detected",
                "action": "Limit resource-intensive containers",
                "command": "docker update --cpus 1.5 --memory 1g <container>",
                "level": "critical",
            })
            actions.append({
                "trigger": "Debug logging overhead",
                "action": "Downgrade log level from DEBUG to WARN",
                "command": "sed -i 's/log_level: debug/log_level: warn/' /app/config.yaml",
                "level": "warning",
            })
        elif cpu > CPU_WARNING or mem > MEM_WARNING:
            actions.append({
                "trigger": f"CPU {cpu}% or Memory {mem}% > warning threshold",
                "action": "Monitor closely, prepare for scaling",
                "command": "spider-diary monitor --json",
                "level": "warning",
            })

        if not actions:
            actions.append({
                "trigger": "System load normal",
                "action": "No emergency action required",
                "command": "",
                "level": "ok",
            })

        return actions

    # ── Optimization progress ─────────────────────────────────────

    def get_optimization_progress(self) -> Dict:
        """Check progress toward optimization targets.

        Targets: 40% resource reduction, 60% response time improvement.
        """
        if not self._baseline:
            return {"baseline": False, "message": "Run establish_baseline() first"}

        sample = self.take_sample()
        cpu_reduction = round(
            max(0, (self._baseline.cpu_avg - sample.cpu_percent) / max(self._baseline.cpu_avg, 1) * 100), 1
        )
        mem_reduction = round(
            max(0, (self._baseline.mem_avg - sample.mem_percent) / max(self._baseline.mem_avg, 1) * 100), 1
        )

        resource_target_met = cpu_reduction >= TARGET_RESOURCE_REDUCTION * 100
        response_target_met = False

        return {
            "baseline": True,
            "baseline_date": self._baseline.created_at,
            "targets": {
                "resource_reduction_pct": TARGET_RESOURCE_REDUCTION * 100,
                "response_improvement_pct": TARGET_RESPONSE_IMPROVEMENT * 100,
            },
            "current": {
                "cpu_reduction_pct": cpu_reduction,
                "mem_reduction_pct": mem_reduction,
                "cpu_current": sample.cpu_percent,
                "cpu_baseline": self._baseline.cpu_avg,
                "mem_current": sample.mem_percent,
                "mem_baseline": self._baseline.mem_avg,
            },
            "targets_met": {
                "resource_reduction": resource_target_met,
                "response_improvement": response_target_met,
            },
            "system_load_ok": sample.cpu_percent < CPU_WARNING and sample.mem_percent < MEM_WARNING,
            "p99_latency_met": False,
        }

    # ── Full report ──────────────────────────────────────────────

    def run_full_check(self) -> Dict:
        """Run complete performance baseline check."""
        sample = self.take_sample()
        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "hostname": self.hostname,
            "sample": asdict(sample),
            "trend": self.track_trend(),
            "emergency_actions": self.get_emergency_actions(),
            "optimization_progress": self.get_optimization_progress(),
        }
