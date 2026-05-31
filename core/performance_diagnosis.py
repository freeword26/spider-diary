"""Performance diagnosis for Spider Diary.

Detects CPU hotspots, I/O bottlenecks, network issues,
container-level resource usage, and samples resource trends.
"""

import datetime
import logging
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

HOTSPOT_CPU_THRESHOLD = 50.0
HOTSPOT_COUNT_TOP = 10
IO_WAIT_THRESHOLD = 30.0
NETWORK_THRESHOLD_MBPS = 800.0
CONTAINER_CPU_THRESHOLD = 70.0
CONTAINER_MEM_THRESHOLD = 80.0


class PerformanceDiagnosis:
    """Comprehensive performance diagnosis engine.

    Provides CPU hotspot detection, I/O bottleneck analysis,
    network bandwidth analysis, container performance checks,
    and resource trend sampling.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
        self.hostname = socket.gethostname()

    def check_cpu_hotspots(self) -> Dict[str, Any]:
        """Detect CPU-hot processes by sampling per-process CPU usage.

        Returns:
            Dict with hostname, timestamp, hotspot_count, total_processes,
            threshold, and a list of hot processes sorted by cpu_percent.
        """
        timestamp = datetime.datetime.now().isoformat()
        hot_procs: List[Dict[str, Any]] = []

        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                info = proc.info
                cpu = info.get("cpu_percent") or 0.0
                if cpu >= HOTSPOT_CPU_THRESHOLD:
                    hot_procs.append({
                        "pid": info["pid"],
                        "name": info["name"],
                        "cpu_percent": cpu,
                        "mem_percent": round(info.get("memory_percent") or 0.0, 1),
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        hot_procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
        top = hot_procs[:HOTSPOT_COUNT_TOP]

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "hotspot_count": len(hot_procs),
            "total_processes": len(psutil.pids()),
            "threshold": HOTSPOT_CPU_THRESHOLD,
            "hot_processes": top,
            "status": "critical" if len(hot_procs) > 5 else "warning" if hot_procs else "ok",
        }

    def check_io_bottleneck(self) -> Dict[str, Any]:
        """Analyze disk I/O for bottlenecks.

        Reads disk I/O counters and computes read/write throughput
        in MB/s over a short sampling interval.

        Returns:
            Dict with hostname, timestamp, read_mb, write_mb, total_mb,
            iostat data, and status.
        """
        timestamp = datetime.datetime.now().isoformat()
        io_start = psutil.disk_io_counters()
        time.sleep(1)
        io_end = psutil.disk_io_counters()

        read_bytes = io_end.read_bytes - (io_start.read_bytes if io_start else 0)
        write_bytes = io_end.write_bytes - (io_start.write_bytes if io_start else 0)
        read_mb = round(read_bytes / (1024 * 1024), 2)
        write_mb = round(write_bytes / (1024 * 1024), 2)
        total_mb = round(read_mb + write_mb, 2)

        busy_threshold_mb = 100.0
        if total_mb > busy_threshold_mb:
            status = "warning"
        elif total_mb > busy_threshold_mb * 2:
            status = "critical"
        else:
            status = "ok"

        iostat: Dict[str, float] = {}
        if io_start and io_end:
            iostat = {
                "read_count_delta": io_end.read_count - io_start.read_count,
                "write_count_delta": io_end.write_count - io_start.write_count,
                "read_time_ms": io_end.read_time - io_start.read_time,
                "write_time_ms": io_end.write_time - io_start.write_time,
            }

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "read_mb": read_mb,
            "write_mb": write_mb,
            "total_mb": total_mb,
            "iostat": iostat,
            "status": status,
        }

    def check_network_bandwidth(self) -> Dict[str, Any]:
        """Analyze network bandwidth usage.

        Samples network I/O counters over a short interval and
        computes throughput in Mbps.

        Returns:
            Dict with hostname, timestamp, sent_mbps, recv_mbps, total_mbps,
            interface_counts, and status.
        """
        timestamp = datetime.datetime.now().isoformat()
        net_start = psutil.net_io_counters()
        time.sleep(1)
        net_end = psutil.net_io_counters()

        sent_bytes = net_end.bytes_sent - (net_start.bytes_sent if net_start else 0)
        recv_bytes = net_end.bytes_recv - (net_start.bytes_recv if net_start else 0)
        sent_mbps = round(sent_bytes * 8 / (1024 * 1024), 2)
        recv_mbps = round(recv_bytes * 8 / (1024 * 1024), 2)
        total_mbps = round(sent_mbps + recv_mbps, 2)

        sent_pkt = net_end.packets_sent - (net_start.packets_sent if net_start else 0)
        recv_pkt = net_end.packets_recv - (net_start.packets_recv if net_start else 0)
        err_in = net_end.errin - (net_start.errin if net_start else 0)
        err_out = net_end.errout - (net_start.errout if net_start else 0)
        drop_in = net_end.dropin - (net_start.dropin if net_start else 0)
        drop_out = net_end.dropout - (net_start.dropout if net_start else 0)

        if err_in + err_out + drop_in + drop_out > 0:
            status = "warning"
        elif total_mbps > NETWORK_THRESHOLD_MBPS:
            status = "warning"
        else:
            status = "ok"

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "sent_mbps": sent_mbps,
            "recv_mbps": recv_mbps,
            "total_mbps": total_mbps,
            "packets_sent": sent_pkt,
            "packets_recv": recv_pkt,
            "errors_in": err_in,
            "errors_out": err_out,
            "drops_in": drop_in,
            "drops_out": drop_out,
            "status": status,
        }

    def check_container_performance(self) -> Dict[str, Any]:
        """Check container-level resource usage via ``docker stats``.

        Parses docker stats output (if available) and reports
        per-container CPU and memory utilization.

        Returns:
            Dict with hostname, timestamp, container_count, containers list,
            status, and docker_available flag.
        """
        timestamp = datetime.datetime.now().isoformat()
        containers: List[Dict[str, Any]] = []
        docker_available = False

        try:
            result = subprocess.run(
                [
                    "docker", "stats", "--no-stream",
                    "--format",
                    "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}",
                ],
                capture_output=True, text=True, timeout=30, shell=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                docker_available = True
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        cpu_str = parts[1].strip().rstrip("%")
                        try:
                            cpu_pct = float(cpu_str)
                        except ValueError:
                            cpu_pct = 0.0

                        mem_str = parts[2].strip() if len(parts) > 2 else "N/A"
                        net_io = parts[3].strip() if len(parts) > 3 else "N/A"
                        block_io = parts[4].strip() if len(parts) > 4 else "N/A"

                        containers.append({
                            "name": name,
                            "cpu_percent": cpu_pct,
                            "mem_usage": mem_str,
                            "net_io": net_io,
                            "block_io": block_io,
                        })
        except FileNotFoundError:
            logger.debug("docker not in PATH, skipping container performance check")
        except subprocess.TimeoutExpired:
            logger.warning("docker stats timed out")
            docker_available = True
        except Exception as e:
            logger.warning("container_performance check error: %s", e)

        heavy = [
            c for c in containers
            if c["cpu_percent"] > CONTAINER_CPU_THRESHOLD
        ]

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "docker_available": docker_available,
            "container_count": len(containers),
            "containers": containers,
            "heavy_containers": heavy,
            "status": "warning" if heavy else "ok",
        }

    def check_resource_trend(self, duration_sec: int = 60) -> Dict[str, Any]:
        """Sample resource usage over a configurable duration.

        Collects CPU, memory, and disk usage at 5-second intervals
        and computes statistics.

        Args:
            duration_sec: Total sampling duration in seconds.
                          Defaults to 60.

        Returns:
            Dict with hostname, timestamp, duration, sample_count,
            cpu stats, mem stats, disk stats, samples list, and status.
        """
        timestamp = datetime.datetime.now().isoformat()
        interval = 5
        cpu_samples: List[float] = []
        mem_samples: List[float] = []
        disk_samples: List[float] = []
        samples: List[Dict[str, Any]] = []
        end_time = time.monotonic() + duration_sec

        while time.monotonic() < end_time:
            try:
                cpu = psutil.cpu_percent(interval=1)
                mem = psutil.virtual_memory().percent
                disk = psutil.disk_usage(str(self.project_root)).percent
                cpu_samples.append(cpu)
                mem_samples.append(mem)
                disk_samples.append(disk)
                samples.append({
                    "cpu": cpu,
                    "mem": mem,
                    "disk": disk,
                    "ts": datetime.datetime.now().isoformat(),
                })
            except Exception as e:
                logger.warning("Resource trend sample error: %s", e)
            remaining = end_time - time.monotonic()
            if remaining > interval:
                time.sleep(interval)
            elif remaining > 0:
                time.sleep(remaining)
            else:
                break

        if not cpu_samples:
            return {
                "hostname": self.hostname,
                "timestamp": timestamp,
                "duration": duration_sec,
                "sample_count": 0,
                "cpu": {},
                "mem": {},
                "disk": {},
                "samples": [],
                "status": "unknown",
            }

        cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 1)
        cpu_peak = round(max(cpu_samples), 1)
        mem_avg = round(sum(mem_samples) / len(mem_samples), 1)
        mem_peak = round(max(mem_samples), 1)
        disk_avg = round(sum(disk_samples) / len(disk_samples), 1)
        disk_peak = round(max(disk_samples), 1)

        if cpu_peak > 90 or mem_peak > 90:
            status = "critical"
        elif cpu_peak > 80 or mem_peak > 80:
            status = "warning"
        else:
            status = "ok"

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "duration": duration_sec,
            "sample_count": len(cpu_samples),
            "cpu": {"avg": cpu_avg, "peak": cpu_peak},
            "mem": {"avg": mem_avg, "peak": mem_peak},
            "disk": {"avg": disk_avg, "peak": disk_peak},
            "samples": samples,
            "status": status,
        }

    def run_full_diagnosis(self) -> Dict[str, Any]:
        """Run all performance diagnosis checks.

        Returns:
            Dict with hostname, timestamp, overall_status,
            and results from each individual check.
        """
        timestamp = datetime.datetime.now().isoformat()
        cpu = self.check_cpu_hotspots()
        io = self.check_io_bottleneck()
        net = self.check_network_bandwidth()
        containers = self.check_container_performance()
        trend = self.check_resource_trend(duration_sec=15)

        statuses = [cpu["status"], io["status"], net["status"], containers["status"], trend["status"]]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"

        return {
            "hostname": self.hostname,
            "timestamp": timestamp,
            "overall_status": overall,
            "cpu_hotspots": cpu,
            "io_bottleneck": io,
            "network_bandwidth": net,
            "container_performance": containers,
            "resource_trend": trend,
        }
