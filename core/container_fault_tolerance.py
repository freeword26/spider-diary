"""Container-level fault tolerance checks for Spider Diary.

Provides health check frequency, restart storm detection, rolling update
parallelism, resource over-isolation, container startup time, and Docker
disk usage checks with configurable thresholds.
"""

import datetime
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG = {
    "health_check_interval_threshold_sec": 5,
    "restart_storm_threshold_per_min": 3,
    "rolling_update_max_surge_pct": 25,
    "resource_over_iso_cpu_limit_pct": 120,
    "resource_over_iso_usage_threshold_pct": 30,
    "container_startup_threshold_sec": 15,
    "docker_df_timeout_sec": 15,
}


class ContainerFaultTolerance:
    """Container fault tolerance checker for Spider Diary.

    Performs container-level health and configuration checks including
    health check frequency, restart storms, rolling update settings,
    resource over-isolation, startup time, and Docker disk usage.
    """

    def __init__(self, config: Optional[Dict] = None):
        """Initialize ContainerFaultTolerance.

        Args:
            config: Optional dict of configuration overrides.
        """
        self.config = {**_DEFAULT_CONFIG, **(config or {})}

    def check_health_check_frequency(self) -> Dict:
        """Check health check intervals from running containers.

        Inspects Docker containers for HEALTHCHECK configuration flags
        and warns if intervals are below the configured threshold (over-consuming).

        Returns:
            Dict with status, containers checked, flagged list, and message.
        """
        interval_threshold = self.config["health_check_interval_threshold_sec"]
        flagged: List[Dict] = []
        containers: List[Dict] = []

        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=self.config["docker_df_timeout_sec"],
                shell=True,
            )
            if result.returncode != 0:
                return {
                    "status": "unavailable",
                    "containers_checked": 0,
                    "flagged": [],
                    "message": f"docker ps returned {result.returncode}",
                }

            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            for line in lines:
                parts = line.split("\t")
                cid = parts[0]
                name = parts[1] if len(parts) > 1 else "unknown"
                container_info = self._inspect_health_check(cid, name, interval_threshold)
                containers.append(container_info)
                if container_info["flagged"]:
                    flagged.append(container_info)

        except FileNotFoundError:
            return {
                "status": "docker_unavailable",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker not found in PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker command timed out",
            }
        except Exception as exc:
            logger.warning("check_health_check_frequency error: %s", exc)
            return {
                "status": "error",
                "containers_checked": 0,
                "flagged": [],
                "message": str(exc),
            }

        status = "warning" if flagged else "ok"
        return {
            "status": status,
            "containers_checked": len(containers),
            "flagged": flagged,
            "message": (
                f"{len(flagged)} container(s) with health check interval < {interval_threshold}s"
                if flagged
                else f"All containers have adequate health check intervals (>= {interval_threshold}s)"
            ),
        }

    def _inspect_health_check(self, cid: str, name: str, threshold: int) -> Dict:
        """Inspect a single container's health check configuration.

        Args:
            cid: Container ID.
            name: Container name.
            threshold: Interval threshold in seconds.

        Returns:
            Dict with container info and flag status.
        """
        info = {
            "id": cid,
            "name": name,
            "health_check_interval_sec": None,
            "flagged": False,
            "issue": None,
        }
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health}}", cid],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            has_health = result.returncode == 0 and result.stdout.strip() not in (
                "<nil>", "", "map[]"
            )
            if not has_health:
                info["issue"] = "No health check configured"
                return info

            inspect_full = subprocess.run(
                ["docker", "inspect", cid],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if inspect_full.returncode == 0:
                try:
                    data = json.loads(inspect_full.stdout)
                    if data and isinstance(data, list):
                        hc = data[0].get("Config", {}).get("Healthcheck", {})
                        interval = hc.get("Interval", 0)
                        interval_sec = interval / 1_000_000_000
                        info["health_check_interval_sec"] = round(interval_sec, 1)
                        if interval_sec < threshold:
                            info["flagged"] = True
                            info["issue"] = (
                                f"Health check interval {interval_sec:.1f}s "
                                f"< {threshold}s (over-consuming)"
                            )
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    pass
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
        return info

    def check_restart_storm(self) -> Dict:
        """Check container restart frequency across all containers.

        Identifies containers restarting more than the threshold rate
        (>3 restarts/minute by default).

        Returns:
            Dict with status, containers checked, flagged list, and message.
        """
        threshold = self.config["restart_storm_threshold_per_min"]
        flagged: List[Dict] = []
        containers: List[Dict] = []

        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                timeout=self.config["docker_df_timeout_sec"],
                shell=True,
            )
            if result.returncode != 0:
                return {
                    "status": "unavailable",
                    "containers_checked": 0,
                    "flagged": [],
                    "message": f"docker ps -a returned {result.returncode}",
                }

            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            for line in lines:
                parts = line.split("\t")
                cid = parts[0]
                name = parts[1] if len(parts) > 1 else "unknown"
                status_str = parts[2] if len(parts) > 2 else ""

                restart_info = self._check_container_restarts(cid, name, status_str, threshold)
                containers.append(restart_info)
                if restart_info["flagged"]:
                    flagged.append(restart_info)

        except FileNotFoundError:
            return {
                "status": "docker_unavailable",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker not found in PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker command timed out",
            }
        except Exception as exc:
            logger.warning("check_restart_storm error: %s", exc)
            return {
                "status": "error",
                "containers_checked": 0,
                "flagged": [],
                "message": str(exc),
            }

        status = "warning" if flagged else "ok"
        return {
            "status": status,
            "containers_checked": len(containers),
            "flagged": flagged,
            "message": (
                f"{len(flagged)} container(s) exceeding {threshold} restarts/min"
                if flagged
                else f"No restart storms detected (threshold: {threshold}/min)"
            ),
        }

    def _check_container_restarts(
        self, cid: str, name: str, status_str: str, threshold: int
    ) -> Dict:
        """Check restart count for a single container.

        Args:
            cid: Container ID.
            name: Container name.
            status_str: Docker status string.
            threshold: Max restarts per minute threshold.

        Returns:
            Dict with container restart info and flag status.
        """
        info = {
            "id": cid,
            "name": name,
            "restart_count": 0,
            "restart_per_min": 0.0,
            "flagged": False,
            "issue": None,
        }

        restart_count = 0
        uptime_sec = 0.0

        if "Restarting" in status_str:
            match = re.search(r"Restarting\s*\((\d+)\)", status_str)
            if match:
                restart_count = int(match.group(1))

        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.StartedAt}}", cid],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                started_str = result.stdout.strip()
                try:
                    started_dt = datetime.datetime.fromisoformat(
                        started_str.replace("Z", "+00:00")
                    )
                    now = datetime.datetime.now(datetime.timezone.utc)
                    uptime_sec = (now - started_dt).total_seconds()
                except ValueError:
                    pass
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass

        if uptime_sec > 0:
            restart_per_min = (restart_count / uptime_sec) * 60
        else:
            restart_per_min = float(restart_count)

        info["restart_count"] = restart_count
        info["restart_per_min"] = round(restart_per_min, 2)

        if restart_per_min > threshold:
            info["flagged"] = True
            info["issue"] = (
                f"Restart rate {restart_per_min:.1f}/min exceeds threshold {threshold}/min"
            )

        return info

    def check_rolling_update_parallelism(self) -> Dict:
        """Check Kubernetes-style rolling update maxSurge settings.

        Reads Docker Compose or Kubernetes manifests to detect maxSurge
        percentages exceeding the threshold.

        Returns:
            Dict with status, deployments checked, flagged list, and message.
        """
        threshold_pct = self.config["rolling_update_max_surge_pct"]
        flagged: List[Dict] = []
        deployments: List[Dict] = []

        compose_files = [
            Path("docker-compose.yml"),
            Path("docker-compose.yaml"),
            Path("k8s/deployment.yml"),
            Path("k8s/deployment.yaml"),
            Path("kubernetes/deployment.yml"),
            Path("kubernetes/deployment.yaml"),
        ]

        for compose_file in compose_files:
            if compose_file.exists():
                try:
                    content = compose_file.read_text(encoding="utf-8")
                    dep_info = self._parse_deployment_config(
                        str(compose_file), content, threshold_pct
                    )
                    if dep_info:
                        deployments.append(dep_info)
                        if dep_info["flagged"]:
                            flagged.append(dep_info)
                except Exception as exc:
                    logger.warning("Error reading %s: %s", compose_file, exc)

        if not deployments:
            return {
                "status": "ok",
                "deployments_checked": 0,
                "flagged": [],
                "message": "No Docker Compose or K8s deployment files found",
            }

        status = "warning" if flagged else "ok"
        return {
            "status": status,
            "deployments_checked": len(deployments),
            "flagged": flagged,
            "message": (
                f"{len(flagged)} deployment(s) with maxSurge > {threshold_pct}%"
                if flagged
                else f"All deployments within rolling update threshold (<= {threshold_pct}%)"
            ),
        }

    def _parse_deployment_config(
        self, filepath: str, content: str, threshold_pct: int
    ) -> Optional[Dict]:
        """Parse a deployment config to find maxSurge percentage.

        Args:
            filepath: Path to the deployment file.
            content: File content.
            threshold_pct: Max surge percentage threshold.

        Returns:
            Dict with deployment info or None if not applicable.
        """
        info = {
            "file": filepath,
            "max_surge_pct": None,
            "max_surge_raw": None,
            "flagged": False,
            "issue": None,
        }

        match = re.search(r"maxSurge[=:]\s*[\"']?(?:(\d+)%)|(\d+)%", content)
        if match:
            pct_str = match.group(1) or match.group(2)
            pct = int(pct_str)
            info["max_surge_pct"] = pct
            info["max_surge_raw"] = match.group(0)
            if pct > threshold_pct:
                info["flagged"] = True
                info["issue"] = (
                    f"maxSurge {pct}% exceeds threshold {threshold_pct}%"
                )

        return info if info["max_surge_pct"] is not None else None

    def check_resource_over_isolation(self) -> Dict:
        """Check CPU limits vs actual usage for over-isolation.

        Identifies containers where CPU limit is set above threshold
        (e.g., >120% of a single core) while actual usage is below
        the low-usage threshold (e.g., <30%).

        Returns:
            Dict with status, containers checked, flagged list, and message.
        """
        limit_threshold = self.config["resource_over_iso_cpu_limit_pct"]
        usage_threshold = self.config["resource_over_iso_usage_threshold_pct"]
        flagged: List[Dict] = []
        containers: List[Dict] = []

        try:
            result = subprocess.run(
                ["docker", "stats", "--no-stream", "--format",
                 "{{.ID}}\t{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"],
                capture_output=True,
                text=True,
                timeout=self.config["docker_df_timeout_sec"],
                shell=True,
            )
            if result.returncode != 0:
                return {
                    "status": "unavailable",
                    "containers_checked": 0,
                    "flagged": [],
                    "message": f"docker stats returned {result.returncode}",
                }

            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            for line in lines:
                parts = line.split("\t")
                cid = parts[0]
                name = parts[1] if len(parts) > 1 else "unknown"
                cpu_pct_str = parts[2] if len(parts) > 2 else "0%"

                cpu_usage = float(cpu_pct_str.strip().rstrip("%"))

                inspect_result = subprocess.run(
                    ["docker", "inspect", "--format", "{{.HostConfig.NanoCpus}}", cid],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    shell=True,
                )
                cpu_limit_pct = 0.0
                if inspect_result.returncode == 0:
                    nano_str = inspect_result.stdout.strip()
                    try:
                        nano = int(nano_str)
                        if nano > 0:
                            cpu_limit_pct = (nano / 1_000_000_000) * 100
                    except ValueError:
                        pass

                container_info = {
                    "id": cid,
                    "name": name,
                    "cpu_usage_pct": round(cpu_usage, 1),
                    "cpu_limit_pct": round(cpu_limit_pct, 1) if cpu_limit_pct else None,
                    "flagged": False,
                    "issue": None,
                }

                if cpu_limit_pct and cpu_limit_pct > limit_threshold and cpu_usage < usage_threshold:
                    container_info["flagged"] = True
                    container_info["issue"] = (
                        f"CPU limit {cpu_limit_pct:.0f}% > {limit_threshold}% "
                        f"but usage {cpu_usage:.1f}% < {usage_threshold}%"
                    )
                    flagged.append(container_info)

                containers.append(container_info)

        except FileNotFoundError:
            return {
                "status": "docker_unavailable",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker not found in PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker command timed out",
            }
        except Exception as exc:
            logger.warning("check_resource_over_isolation error: %s", exc)
            return {
                "status": "error",
                "containers_checked": 0,
                "flagged": [],
                "message": str(exc),
            }

        status = "warning" if flagged else "ok"
        return {
            "status": status,
            "containers_checked": len(containers),
            "flagged": flagged,
            "message": (
                f"{len(flagged)} container(s) over-isolated"
                if flagged
                else "No over-isolated containers detected"
            ),
        }

    def check_container_startup_time(self) -> Dict:
        """Check container startup time for excessive initialization delay.

        Compares container creation time to start time to detect slow
        startups exceeding the threshold.

        Returns:
            Dict with status, containers checked, flagged list, and message.
        """
        threshold_sec = self.config["container_startup_threshold_sec"]
        flagged: List[Dict] = []
        containers: List[Dict] = []

        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.ID}}\t{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=self.config["docker_df_timeout_sec"],
                shell=True,
            )
            if result.returncode != 0:
                return {
                    "status": "unavailable",
                    "containers_checked": 0,
                    "flagged": [],
                    "message": f"docker ps -a returned {result.returncode}",
                }

            lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
            for line in lines:
                parts = line.split("\t")
                cid = parts[0]
                name = parts[1] if len(parts) > 1 else "unknown"

                startup_info = self._check_startup_time(cid, name, threshold_sec)
                containers.append(startup_info)
                if startup_info["flagged"]:
                    flagged.append(startup_info)

        except FileNotFoundError:
            return {
                "status": "docker_unavailable",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker not found in PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "containers_checked": 0,
                "flagged": [],
                "message": "Docker command timed out",
            }
        except Exception as exc:
            logger.warning("check_container_startup_time error: %s", exc)
            return {
                "status": "error",
                "containers_checked": 0,
                "flagged": [],
                "message": str(exc),
            }

        status = "warning" if flagged else "ok"
        return {
            "status": status,
            "containers_checked": len(containers),
            "flagged": flagged,
            "message": (
                f"{len(flagged)} container(s) with startup > {threshold_sec}s"
                if flagged
                else f"All containers start within {threshold_sec}s"
            ),
        }

    def _check_startup_time(self, cid: str, name: str, threshold: int) -> Dict:
        """Check startup time for a single container.

        Args:
            cid: Container ID.
            name: Container name.
            threshold: Startup time threshold in seconds.

        Returns:
            Dict with startup info and flag status.
        """
        info = {
            "id": cid,
            "name": name,
            "startup_time_sec": None,
            "flagged": False,
            "issue": None,
        }

        try:
            inspect_result = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{.Created}}\t{{.State.StartedAt}}", cid],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True,
            )
            if inspect_result.returncode == 0:
                parts = inspect_result.stdout.strip().split("\t")
                if len(parts) == 2:
                    created_str, started_str = parts
                    created_dt = datetime.datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                    started_dt = datetime.datetime.fromisoformat(
                        started_str.replace("Z", "+00:00")
                    )
                    delta = (started_dt - created_dt).total_seconds()
                    info["startup_time_sec"] = round(delta, 2)
                    if delta > threshold:
                        info["flagged"] = True
                        info["issue"] = (
                            f"Startup time {delta:.1f}s exceeds threshold {threshold}s"
                        )
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
            pass

        return info

    def check_docker_disk_usage(self) -> Dict:
        """Check Docker system disk usage for images, containers, and volumes.

        Runs ``docker system df`` and reports disk consumption details
        with warnings for high usage categories.

        Returns:
            Dict with status, disk details, warnings list, and message.
        """
        warnings: List[Dict] = []

        try:
            result = subprocess.run(
                ["docker", "system", "df"],
                capture_output=True,
                text=True,
                timeout=self.config["docker_df_timeout_sec"],
                shell=True,
            )
            if result.returncode != 0:
                return {
                    "status": "unavailable",
                    "disk_usage": {},
                    "warnings": [],
                    "message": f"docker system df returned {result.returncode}",
                }

            lines = result.stdout.strip().split("\n")
            disk_usage: Dict[str, Dict] = {}

            for line in lines:
                if line.startswith("TYPE") or not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    category = parts[0]
                    total = parts[1] if len(parts) > 1 else "N/A"
                    active = parts[2] if len(parts) > 2 else "N/A"
                    size = parts[3] if len(parts) > 3 else "N/A"
                    reclaimable = "N/A"
                    pct_str = None

                    for p in parts[4:]:
                        p_clean = p.strip().strip("()")
                        if "%" in p_clean:
                            pct_str = p_clean
                        elif reclaimable == "N/A":
                            reclaimable = p

                    disk_usage[category] = {
                        "total": total,
                        "active": active,
                        "size": size,
                        "reclaimable": reclaimable,
                    }

                    if pct_str:
                        pct = float(pct_str.rstrip("%"))
                        disk_usage[category]["percentage"] = pct
                        if pct >= 80:
                            severity = "critical" if pct >= 90 else "warning"
                            warnings.append({
                                "category": category,
                                "severity": severity,
                                "percentage": pct,
                                "message": (
                                    f"Docker {category} usage at {pct}% "
                                    f"(threshold: 80%)"
                                ),
                                "suggestion": (
                                    "docker system prune -a"
                                    if category == "Images"
                                    else "docker volume prune"
                                    if category == "Volumes"
                                    else "docker container prune"
                                ),
                            })

        except FileNotFoundError:
            return {
                "status": "docker_unavailable",
                "disk_usage": {},
                "warnings": [],
                "message": "Docker not found in PATH",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "disk_usage": {},
                "warnings": [],
                "message": "docker system df timed out",
            }
        except Exception as exc:
            logger.warning("check_docker_disk_usage error: %s", exc)
            return {
                "status": "error",
                "disk_usage": {},
                "warnings": [],
                "message": str(exc),
            }

        status = "warning" if warnings else "ok"
        return {
            "status": status,
            "disk_usage": disk_usage,
            "warnings": warnings,
            "message": (
                f"{len(warnings)} Docker disk usage warning(s)"
                if warnings
                else "Docker disk usage within normal limits"
            ),
        }

    def run_all(self) -> Dict:
        """Run all container fault tolerance checks.

        Returns:
            Dict containing all check results, overall_status, and timestamp.
        """
        health_freq = self.check_health_check_frequency()
        restart_storm = self.check_restart_storm()
        rolling_update = self.check_rolling_update_parallelism()
        resource_iso = self.check_resource_over_isolation()
        startup_time = self.check_container_startup_time()
        disk_usage = self.check_docker_disk_usage()

        all_statuses = [
            health_freq["status"],
            restart_storm["status"],
            rolling_update["status"],
            resource_iso["status"],
            startup_time["status"],
            disk_usage["status"],
        ]

        active_statuses = [s for s in all_statuses if s not in ("docker_unavailable", "unavailable", "timeout", "error")]
        if any(s == "critical" for s in active_statuses):
            overall_status = "critical"
        elif any(s == "warning" for s in active_statuses):
            overall_status = "warning"
        else:
            overall_status = "ok"

        any_unavailable = any(
            s in ("docker_unavailable", "unavailable", "timeout", "error")
            for s in all_statuses
        )

        if any_unavailable and overall_status == "ok":
            overall_status = "degraded"

        result = {
            "health_check_frequency": health_freq,
            "restart_storm": restart_storm,
            "rolling_update_parallelism": rolling_update,
            "resource_over_isolation": resource_iso,
            "container_startup_time": startup_time,
            "docker_disk_usage": disk_usage,
            "overall_status": overall_status,
            "timestamp": datetime.datetime.now().isoformat(),
        }

        logger.info("Container fault tolerance run_all complete: overall_status=%s", overall_status)
        return result
