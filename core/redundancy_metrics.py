"""Redundancy metrics for Spider Diary.

Detects duplicate health checks, double encryption, multi-layer
timeout mismatches, image redundancy, and monitoring overlap.
Computes an overall redundancy score.
"""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

WEIGHT_DUP_HEALTH = 25.0
WEIGHT_DOUBLE_ENCRYPT = 20.0
WEIGHT_TIMEOUT_MISMATCH = 20.0
WEIGHT_IMAGE_REDUN = 20.0
WEIGHT_MONITOR_OVERLAP = 15.0
WEIGHT_TOTAL = (
    WEIGHT_DUP_HEALTH + WEIGHT_DOUBLE_ENCRYPT + WEIGHT_TIMEOUT_MISMATCH
    + WEIGHT_IMAGE_REDUN + WEIGHT_MONITOR_OVERLAP
)


class RedundancyMetrics:
    """Detects redundancy patterns across infrastructure layers.

    Identifies wasteful duplication in health checks, encryption,
    timeouts, container images, and monitoring tools, and computes
    an overall redundancy score from 0 (severe redundancy) to 100 (clean).
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()

    def check_duplicate_health_checks(self) -> Dict[str, Any]:
        """Detect overlapping health checks (container + mesh + app layer).

        Scans docker-compose for health checks and checks for service-
        mesh (istio/linkerd) or application-level health endpoints that
        duplicate the container-level checks.

        Returns:
            Dict with check name, detected_layers list, duplicates list,
            status, and detail message.
        """
        detected_layers: List[str] = []
        duplicates: List[Dict[str, str]] = []
        compose_files = list(self.project_root.rglob("docker-compose*.yml")) + \
                        list(self.project_root.rglob("docker-compose*.yaml"))

        has_docker_health = False
        for cf in compose_files:
            try:
                content = cf.read_text(encoding="utf-8", errors="ignore")
                if "healthcheck" in content:
                    has_docker_health = True
                    detected_layers.append("container")
                    break
            except OSError:
                continue

        has_mesh = False
        mesh_files = list(self.project_root.rglob("**/VirtualService*.yaml")) + \
                     list(self.project_root.rglob("**/DestinationRule*.yaml")) + \
                     list(self.project_root.rglob("**/linkerd-proxy*.yaml"))
        if mesh_files:
            has_mesh = True
            detected_layers.append("mesh")

        has_app_health = False
        app_patterns = [
            "**/healthz*", "**/health_check*", "**/actuator/health*",
            "**/readiness*", "**/liveness*",
        ]
        for pattern in app_patterns:
            matches = list(self.project_root.rglob(pattern))
            if matches:
                has_app_health = True
                detected_layers.append("app")
                break

        if has_docker_health and has_app_health:
            duplicates.append({
                "type": "container + app",
                "detail": "healthcheck in docker-compose overlaps with app-level /healthz",
            })
        if has_docker_health and has_mesh:
            duplicates.append({
                "type": "container + mesh",
                "detail": "healthcheck in docker-compose overlaps with service-mesh probes",
            })
        if has_mesh and has_app_health:
            duplicates.append({
                "type": "mesh + app",
                "detail": "service-mesh health checking overlaps with app-level probes",
            })

        if duplicates:
            status = "warning"
        else:
            status = "ok"

        return {
            "check": "duplicate_health_checks",
            "detected_layers": detected_layers,
            "duplicates": duplicates,
            "status": status,
            "detail": f"Layers detected: {', '.join(detected_layers)}" if detected_layers else "No health check layers found",
        }

    def check_double_encryption(self) -> Dict[str, Any]:
        """Detect TLS + application-layer double encryption.

        Checks docker-compose, nginx/conf files, and application configs
        for both TLS termination at the proxy level AND application-layer
        encryption (e.g., Fernet, AES in the codebase) on the same data path.

        Returns:
            Dict with check name, tls_detected, app_encrypt_detected,
            double_encrypt_paths list, status, and detail.
        """
        tls_detected = False
        app_encrypt_detected = False
        double_encrypt_paths: List[Dict[str, str]] = []

        compose_files = list(self.project_root.rglob("docker-compose*.yml")) + \
                        list(self.project_root.rglob("docker-compose*.yaml"))
        for cf in compose_files:
            try:
                content = cf.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"443|tls|ssl|https", content, re.IGNORECASE):
                    tls_detected = True
                    break
            except OSError:
                continue

        conf_files = list(self.project_path("nginx*.conf")) if False else \
            list(self.project_root.rglob("**/nginx*.conf")) + \
            list(self.project_root.rglob("**/nginx/conf.d/*.conf"))
        for cf in conf_files:
            try:
                content = cf.read_text(encoding="utf-8", errors="ignore")
                if re.search(r"ssl_certificate|listen\s+443|proxy_ssl", content):
                    tls_detected = True
                    break
            except OSError:
                continue

        encrypt_patterns = [
            "**/crypto*.py", "**/encrypt*.py", "**/cipher*.py",
            "**/fernet*", "**/aes_*", "**/kms*",
        ]
        for pattern in encrypt_patterns:
            for match in self.project_root.rglob(pattern):
                try:
                    content = match.read_text(encoding="utf-8", errors="ignore")
                    if re.search(r"Fernet|AES|encrypt|cipher", content, re.IGNORECASE):
                        app_encrypt_detected = True
                        double_encrypt_paths.append({
                            "file": str(match.relative_to(self.project_root)),
                            "pattern": pattern,
                        })
                        break
                except OSError:
                    continue
            if app_encrypt_detected:
                break

        if tls_detected and app_encrypt_detected:
            status = "warning"
        else:
            status = "ok"

        return {
            "check": "double_encryption",
            "tls_detected": tls_detected,
            "app_encrypt_detected": app_encrypt_detected,
            "double_encrypt_paths": double_encrypt_paths,
            "status": status,
            "detail": "TLS + app-layer encryption overlap detected" if double_encrypt_paths else "No double encryption found",
        }

    def _project_path(self, pattern: str) -> List[Path]:
        return list(self.project_root.rglob(pattern))

    def check_multi_layer_timeouts(self) -> Dict[str, Any]:
        """Detect client + gateway + service timeout mismatch.

        Scans configuration files for timeout settings across
        client-side, gateway (nginx/envoy), and service-level configs
        and detects if inner layers have higher timeouts than outer ones.

        Returns:
            Dict with check name, layers_detected list, mismatches list,
            status, and detail.
        """
        layers_detected: List[Dict[str, Any]] = []
        mismatches: List[Dict[str, str]] = []

        timeout_patterns = [
            ("client", r"(read|connect|request)[_\-]?timeout['\"]?\s*[:=]\s*(\d+)"),
            ("gateway", r"(proxy_read_timeout|proxy_connect_timeout|upstream_connect_timeout)\s+(\d+)"),
            ("service", r"(timeout|requestTimeout|idleTimeout)['\"]?\s*[:=]\s*(\d+)"),
        ]

        config_globs = [
            "**/nginx*.conf", "**/envoy*.yaml", "**/application*.yml",
            "**/application*.yaml", "**/application*.properties",
            "**/config*.yaml", "**/config*.yml", "**/config*.json",
            "**/kubeconfig*", "**/deployment*.yaml", "**/values*.yaml",
        ]

        for layer_name, pattern in timeout_patterns:
            found = False
            for glob_pattern in config_globs:
                for fp in self.project_root.rglob(glob_pattern):
                    try:
                        content = fp.read_text(encoding="utf-8", errors="ignore")
                        match = re.search(pattern, content, re.IGNORECASE)
                        if match:
                            val = int(match.group(2))
                            layers_detected.append({
                                "layer": layer_name,
                                "timeout_sec": val,
                                "file": str(fp.relative_to(self.project_root)),
                            })
                            found = True
                            break
                    except (OSError, ValueError):
                        continue
                if found:
                    break

        by_layer: Dict[str, int] = {}
        for ld in layers_detected:
            layer = ld["layer"]
            if layer not in by_layer:
                by_layer[layer] = ld["timeout_sec"]

        client_t = by_layer.get("client", 0)
        gateway_t = by_layer.get("gateway", 0)
        service_t = by_layer.get("service", 0)

        if client_t and gateway_t and gateway_t > client_t:
            mismatches.append({
                "type": "gateway > client",
                "detail": f"Gateway timeout ({gateway_t}s) exceeds client timeout ({client_t}s)",
            })
        if gateway_t and service_t and service_t > gateway_t:
            mismatches.append({
                "type": "service > gateway",
                "detail": f"Service timeout ({service_t}s) exceeds gateway timeout ({gateway_t}s)",
            })

        if mismatches:
            status = "warning"
        else:
            status = "ok"

        return {
            "check": "multi_layer_timeouts",
            "layers_detected": layers_detected,
            "mismatches": mismatches,
            "status": status,
            "detail": f"Timeout mismatches: {len(mismatches)}" if mismatches else "No timeout mismatches detected",
        }

    def check_image_redundancy(self) -> Dict[str, Any]:
        """Detect same base image used with different tags.

        Runs ``docker images`` locally and groups images by
        repository to detect multiple tags referencing the same image ID,
        or similar images from different registries.

        Returns:
            Dict with check name, unique_images, redundant_groups list,
            status, and detail.
        """
        unique_images: List[Dict[str, str]] = []
        redundant_groups: List[Dict[str, Any]] = []

        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"],
                capture_output=True, text=True, timeout=30, shell=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                by_id: Dict[str, List[Dict[str, str]]] = {}
                for line in result.stdout.strip().split("\n"):
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        entry = {
                            "repository": parts[0].strip(),
                            "tag": parts[1].strip(),
                            "image_id": parts[2].strip(),
                            "size": parts[3].strip() if len(parts) > 3 else "?",
                        }
                        unique_images.append(entry)
                        img_id = entry["image_id"]
                        if img_id not in by_id:
                            by_id[img_id] = []
                        by_id[img_id].append(entry)

                for img_id, entries in by_id.items():
                    if len(entries) > 1:
                        tags = [f"{e['repository']}:{e['tag']}" for e in entries]
                        redundant_groups.append({
                            "image_id": img_id,
                            "tags": tags,
                            "count": len(entries),
                        })
        except FileNotFoundError:
            logger.debug("docker not in PATH, skipping image redundancy check")
        except subprocess.TimeoutExpired:
            logger.warning("docker images timed out")
        except Exception as e:
            logger.warning("image_redundancy check error: %s", e)

        if redundant_groups:
            total_dupes = sum(g["count"] - 1 for g in redundant_groups)
            status = "warning" if total_dupes <= 3 else "critical"
        else:
            status = "ok"

        return {
            "check": "image_redundancy",
            "unique_images": len(unique_images),
            "redundant_groups": redundant_groups,
            "status": status,
            "detail": f"{len(redundant_groups)} redundant image groups found" if redundant_groups else "No redundant images found",
        }

    def check_monitoring_overlap(self) -> Dict[str, Any]:
        """Detect Prometheus + Datadog + custom monitoring overlap.

        Scans config files for multiple monitoring tool configurations
        that could result in redundant metric collection.

        Returns:
            Dict with check name, tools_detected list, overlaps list,
            status, and detail.
        """
        tools_detected: List[str] = []
        overlaps: List[Dict[str, str]] = []

        monitor_checks = [
            (
                "prometheus",
                [
                    "**/prometheus*.yml", "**/prometheus*.yaml",
                    "**/prometheus*.json",
                ],
            ),
            (
                "datadog",
                [
                    "**/datadog*.yml", "**/datadog*.yaml",
                    "**/datadog.conf", "**/datadog*.json",
                ],
            ),
            (
                "grafana",
                [
                    "**/grafana*.yml", "**/grafana*.yaml",
                    "**/grafana/dashboards/*.json",
                ],
            ),
            (
                "custom",
                [
                    "**/monitor*.py", "**/healthcheck*.py",
                    "**/watchdog*.py", "**/observer*.py",
                ],
            ),
            (
                "elastic",
                [
                    "**/metricbeat*.yml", "**/filebeat*.yml",
                    "**/elastic*agent*.yml",
                ],
            ),
        ]

        for tool_name, patterns in monitor_checks:
            for pattern in patterns:
                for fp in self.project_root.rglob(pattern):
                    try:
                        content = fn_read = fp.read_text(encoding="utf-8", errors="ignore")
                        if content.strip():
                            tools_detected.append(tool_name)
                            break
                    except OSError:
                        continue
                if tool_name in tools_detected:
                    break

        scoring_tools = {"prometheus", "datadog", "elastic"}
        detected_scoring = [t for t in tools_detected if t in scoring_tools]
        if len(detected_scoring) > 1:
            for i in range(len(detected_scoring)):
                for j in range(i + 1, len(detected_scoring)):
                    overlaps.append({
                        "tools": f"{detected_scoring[i]} + {detected_scoring[j]}",
                        "detail": f"Both {detected_scoring[i]} and {detected_scoring[j]} collect similar metrics",
                    })

        if "custom" in tools_detected:
            for scoring in detected_scoring:
                overlaps.append({
                    "tools": f"custom + {scoring}",
                    "detail": f"Custom monitoring overlaps with {scoring}",
                })

        if overlaps:
            status = "warning"
        else:
            status = "ok"

        return {
            "check": "monitoring_overlap",
            "tools_detected": tools_detected,
            "overlaps": overlaps,
            "status": status,
            "detail": f"Monitoring tools: {', '.join(tools_detected)}" if tools_detected else "No monitoring tools detected",
        }

    def get_redundancy_score(self) -> float:
        """Compute overall redundancy score from 0 to 100.

        Higher score means less redundancy. Each check contributes
        a weighted portion based on detected issues.

        Returns:
            Float score between 0 (severe redundancy) and 100 (clean).
        """
        dup = self.check_duplicate_health_checks()
        enc = self.check_double_encryption()
        timeouts = self.check_multi_layer_timeouts()
        images = self.check_image_redundancy()
        monitors = self.check_monitoring_overlap()

        penalty = 0.0

        if dup["status"] != "ok":
            penalty += WEIGHT_DUP_HEALTH * min(len(dup["duplicates"]) * 0.3, 1.0)

        if enc["status"] != "ok":
            penalty += WEIGHT_DOUBLE_ENCRYPT * min(len(enc["double_encrypt_paths"]) * 0.3, 1.0)

        if timeouts["status"] != "ok":
            penalty += WEIGHT_TIMEOUT_MISMATCH * min(len(timeouts["mismatches"]) * 0.3, 1.0)

        if images["status"] == "critical":
            penalty += WEIGHT_IMAGE_REDUN
        elif images["status"] == "warning":
            penalty += WEIGHT_IMAGE_REDUN * 0.5

        if monitors["status"] != "ok":
            penalty += WEIGHT_MONITOR_OVERLAP * min(len(monitors["overlaps"]) * 0.3, 1.0)

        score = max(0, 100.0 - (penalty / WEIGHT_TOTAL * 100.0))
        return round(score, 1)

    def run_all(self) -> Dict[str, Any]:
        """Run all redundancy checks and compute overall score.

        Returns:
            Dict with timestamp, redundancy_score, overall_status,
            and results from each individual check.
        """
        dup = self.check_duplicate_health_checks()
        enc = self.check_double_encryption()
        timeouts = self.check_multi_layer_timeouts()
        images = self.check_image_redundancy()
        monitors = self.check_monitoring_overlap()
        score = self.get_redundancy_score()

        statuses = [dup["status"], enc["status"], timeouts["status"], images["status"], monitors["status"]]
        if "critical" in statuses:
            overall = "critical"
        elif "warning" in statuses:
            overall = "warning"
        else:
            overall = "ok"

        return {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "redundancy_score": score,
            "overall_status": overall,
            "duplicate_health_checks": dup,
            "double_encryption": enc,
            "multi_layer_timeouts": timeouts,
            "image_redundancy": images,
            "monitoring_overlap": monitors,
        }
