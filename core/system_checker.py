import datetime
import logging
import os
import shutil
import socket

import psutil

logger = logging.getLogger(__name__)


class SystemChecker:
    """System health checker for Spider Diary.

    Performs disk, memory, process, and CPU load checks with
    configurable thresholds and returns structured status reports.
    """

    def __init__(self, config=None):
        """Initialize SystemChecker.

        Args:
            config: Optional dict of configuration overrides.
        """
        self.config = config or {}

    def check_disk(self, path=None):
        """Check disk usage for a given path.

        Args:
            path: Target path to check. Defaults to current working directory.

        Returns:
            Dict with path, total_gb, used_gb, free_gb, percent, status.
        """
        target = path or os.getcwd()
        usage = shutil.disk_usage(target)
        total_gb = round(usage.total / (1024 ** 3), 2)
        used_gb = round(usage.used / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        percent = round(usage.used / usage.total * 100, 1)

        if percent > 90:
            status = "critical"
        elif percent >= 80:
            status = "warning"
        else:
            status = "ok"

        result = {
            "path": target,
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "percent": percent,
            "status": status,
        }
        logger.info("Disk check for %s: %s%% (%s)", target, percent, status)
        return result

    def check_memory(self):
        """Check system memory usage.

        Returns:
            Dict with total_gb, available_gb, used_gb, percent, status.
        """
        mem = psutil.virtual_memory()
        total_gb = round(mem.total / (1024 ** 3), 2)
        available_gb = round(mem.available / (1024 ** 3), 2)
        used_gb = round(mem.used / (1024 ** 3), 2)
        percent = mem.percent

        if percent > 90:
            status = "critical"
        elif percent >= 80:
            status = "warning"
        else:
            status = "ok"

        result = {
            "total_gb": total_gb,
            "available_gb": available_gb,
            "used_gb": used_gb,
            "percent": percent,
            "status": status,
        }
        logger.info("Memory check: %s%% (%s)", percent, status)
        return result

    def check_processes(self):
        """Count running processes.

        Returns:
            Dict with count and status.
        """
        count = len(psutil.pids())

        if count > 600:
            status = "critical"
        elif count >= 400:
            status = "warning"
        else:
            status = "ok"

        result = {"count": count, "status": status}
        logger.info("Process check: %d processes (%s)", count, status)
        return result

    def check_load(self):
        """Check system load averages and CPU usage.

        On Unix uses psutil.getloadavg(); on Windows uses psutil.cpu_percent().

        Returns:
            Dict with load_1min, load_5min, load_15min, cpu_percent, status.
        """
        cpu_percent = psutil.cpu_percent(interval=1)

        try:
            load_1min, load_5min, load_15min = psutil.getloadavg()
        except AttributeError:
            load_1min = load_5min = load_15min = None

        if cpu_percent > 90:
            status = "critical"
        elif cpu_percent >= 80:
            status = "warning"
        else:
            status = "ok"

        result = {
            "load_1min": load_1min,
            "load_5min": load_5min,
            "load_15min": load_15min,
            "cpu_percent": cpu_percent,
            "status": status,
        }
        logger.info("Load check: CPU %s%% (%s)", cpu_percent, status)
        return result

    def run_all_checks(self):
        """Run all system health checks.

        Returns:
            Dict containing all check results, overall_status,
            timestamp, and hostname.
        """
        disk = self.check_disk()
        memory = self.check_memory()
        processes = self.check_processes()
        load = self.check_load()

        statuses = [disk["status"], memory["status"], processes["status"], load["status"]]

        if "critical" in statuses:
            overall_status = "critical"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "ok"

        result = {
            "disk": disk,
            "memory": memory,
            "processes": processes,
            "load": load,
            "overall_status": overall_status,
            "timestamp": datetime.datetime.now().isoformat(),
            "hostname": socket.gethostname(),
        }
        logger.info("All checks complete: overall_status=%s", overall_status)
        return result
