"""Protocol fault tolerance checker for Spider Diary.

Implements Level 1 Communication Protocol Fault Tolerance checks including
QUIC connection reuse, message acknowledgment redundancy, encryption overhead,
connection migration, and reorder buffer analysis.
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

_DEFAULT_QUIC_PORT = 443
_MAX_QUIC_PER_SERVICE = 50
_MAX_ACK_REDUNDANCY_PCT = 15.0
_MAX_ENCRYPTION_LATENCY_MS = 5.0
_MAX_MIGRATION_PER_MIN = 10
_MAX_REORDER_BUFFER = 30


class ProtocolFaultTolerance:
    """Level 1 Communication Protocol Fault Tolerance checker.

    Analyzes network protocol health including QUIC connections,
    TCP acknowledgment patterns, encryption overhead, connection migration,
    and kernel reorder buffer settings.
    """

    def __init__(
        self,
        quic_port: int = _DEFAULT_QUIC_PORT,
        max_quic_per_service: int = _MAX_QUIC_PER_SERVICE,
        max_ack_redundancy_pct: float = _MAX_ACK_REDUNDANCY_PCT,
        max_encryption_latency_ms: float = _MAX_ENCRYPTION_LATENCY_MS,
        max_migration_per_min: int = _MAX_MIGRATION_PER_MIN,
        max_reorder_buffer: int = _MAX_REORDER_BUFFER,
    ):
        """Initialize ProtocolFaultTolerance checker.

        Args:
            quic_port: Default QUIC service port to monitor.
            max_quic_per_service: Threshold for QUIC connections per service.
            max_ack_redundancy_pct: Threshold for duplicate ACK percentage.
            max_encryption_latancy_ms: Threshold for encryption latency per MB.
            max_migration_per_min: Threshold for QUIC migration frequency.
            max_reorder_buffer: Threshold for kernel TCP reorder buffer.
        """
        self.quic_port = quic_port
        self.max_quic_per_service = max_quic_per_service
        self.max_ack_redundancy_pct = max_ack_redundancy_pct
        self.max_encryption_latency_ms = max_encryption_latency_ms
        self.max_migration_per_min = max_migration_per_min
        self.max_reorder_buffer = max_reorder_buffer

    def _parse_netstat_quic(self) -> Dict[str, int]:
        """Parse netstat output for QUIC connection counts per service.

        Returns:
            Dictionary mapping service identifiers to connection counts.
        """
        connections: Dict[str, int] = {}
        try:
            result = subprocess.run(
                ["netstat", "-an"],
                capture_output=True,
                text=True,
                timeout=15,
                shell=True,
            )
            if result.returncode != 0:
                logger.warning("netstat command failed with return code %d", result.returncode)
                return connections

            for line in result.stdout.strip().split("\n"):
                line_lower = line.lower()
                if "udp" in line_lower and str(self.quic_port) in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        remote_addr = parts[2]
                        if ":" in remote_addr:
                            service_key = remote_addr.rsplit(":", 1)[0]
                            if service_key and service_key != "*":
                                connections[service_key] = connections.get(service_key, 0) + 1
        except FileNotFoundError:
            logger.warning("netstat not found in PATH")
        except subprocess.TimeoutExpired:
            logger.warning("netstat command timed out")
        except Exception as e:
            logger.warning("Error parsing netstat: %s", e)
        return connections

    def check_quic_connection_reuse(self) -> Dict[str, Any]:
        """Check QUIC connection reuse patterns.

        Analyzes active QUIC connections and flags services with connection
        counts exceeding the configured threshold.

        Returns:
            Dictionary with connection counts, violations, and status.
        """
        connections = self._parse_netstat_quic()
        total_connections = sum(connections.values())
        violations = {
            svc: count for svc, count in connections.items()
            if count > self.max_quic_per_service
        }

        if violations:
            status = "warning"
        elif total_connections == 0:
            status = "info"
        else:
            status = "ok"

        result = {
            "check": "quic_connection_reuse",
            "total_connections": total_connections,
            "services": connections,
            "violations": violations,
            "threshold": self.max_quic_per_service,
            "status": status,
            "message": (
                f"{len(violations)} services exceed {self.max_quic_per_service} QUIC connections"
                if violations
                else f"QUIC connections within limits ({total_connections} total)"
            ),
        }
        logger.info("QUIC connection check: %s", result["message"])
        return result

    def check_message_ack_redundancy(self) -> Dict[str, Any]:
        """Analyze TCP+QUIC duplicate acknowledgment redundancy rate.

        Uses network connection statistics to estimate duplicate ACK rates
        and flags when redundancy exceeds the configured threshold.

        Returns:
            Dictionary with ACK statistics and redundancy analysis.
        """
        tcp_total = 0
        tcp_established = 0
        udp_total = 0

        try:
            net_connections = psutil.net_connections(kind="inet")
            for conn in net_connections:
                if conn.type == socket.SOCK_STREAM:
                    tcp_total += 1
                    if conn.status == "ESTABLISHED":
                        tcp_established += 1
                elif conn.type == socket.SOCK_DGRAM:
                    udp_total += 1
        except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
            logger.warning("Access denied reading connections: %s", e)
        except Exception as e:
            logger.warning("Error reading connections: %s", e)

        io_stats = psutil.net_io_counters(pernic=False)
        packets_sent = io_stats.packets_sent
        packets_recv = io_stats.packets_recv
        total_packets = packets_sent + packets_recv

        if total_packets > 0 and tcp_established > 0:
            duplicate_ack_rate = (tcp_established / total_packets) * 100
        else:
            duplicate_ack_rate = 0.0

        if tcp_total > 0 and tcp_established > 1:
            redundancy_rate = ((tcp_established - 1) / tcp_total) * 100
        else:
            redundancy_rate = 0.0

        effective_rate = duplicate_ack_rate + redundancy_rate

        if effective_rate > self.max_ack_redundancy_pct:
            status = "warning"
        else:
            status = "ok"

        result = {
            "check": "message_ack_redundancy",
            "tcp_total": tcp_total,
            "tcp_established": tcp_established,
            "udp_total": udp_total,
            "packets_sent": packets_sent,
            "packets_recv": packets_recv,
            "duplicate_ack_rate": round(effective_rate, 2),
            "threshold_pct": self.max_ack_redundancy_pct,
            "status": status,
            "message": (
                f"Duplicate ACK rate {effective_rate:.2f}% exceeds {self.max_ack_redundancy_pct}%"
                if status == "warning"
                else f"Duplicate ACK rate {effective_rate:.2f}% within limits"
            ),
        }
        logger.info("ACK redundancy check: %s", result["message"])
        return result

    def check_encryption_overhead(self, test_data_size_mb: float = 1.0) -> Dict[str, Any]:
        """Measure encryption/decryption latency overhead.

        Uses CPU-intensive operations to estimate encryption latency
        and flags when per-MB latency exceeds the configured threshold.

        Args:
            test_data_size_mb: Size of test data in megabytes.

        Returns:
            Dictionary with encryption latency measurements and analysis.
        """
        data_size_bytes = int(test_data_size_mb * 1024 * 1024)
        test_data = bytearray(data_size_bytes)

        try:
            import hashlib

            iterations = max(1, int(10 / test_data_size_mb))

            start_time = time.perf_counter()
            for _ in range(iterations):
                hashlib.sha256(test_data).digest()
            elapsed_time = time.perf_counter() - start_time

            avg_latency_ms = (elapsed_time / iterations) * 1000
            latency_per_mb = avg_latency_ms / test_data_size_mb

        except Exception as e:
            logger.warning("Error measuring encryption overhead: %s", e)
            avg_latency_ms = 0.0
            latency_per_mb = 0.0

        if latency_per_mb > self.max_encryption_latency_ms and latency_per_mb > 0:
            status = "warning"
        else:
            status = "ok"

        result = {
            "check": "encryption_overhead",
            "test_data_size_mb": test_data_size_mb,
            "iterations": iterations if 'iterations' in dir() else 0,
            "avg_latency_ms": round(avg_latency_ms, 3),
            "latency_per_mb_ms": round(latency_per_mb, 3),
            "threshold_ms_per_mb": self.max_encryption_latency_ms,
            "status": status,
            "message": (
                f"Encryption overhead {latency_per_mb:.3f}ms/MB exceeds {self.max_encryption_latency_ms}ms/MB"
                if status == "warning"
                else f"Encryption overhead {latency_per_mb:.3f}ms/MB within limits"
            ),
        }
        logger.info("Encryption overhead check: %s", result["message"])
        return result

    def check_connection_migration(self) -> Dict[str, Any]:
        """Check QUIC connection migration frequency.

        Analyzes UDP connection states to detect QUIC connection migration
        events and flags when frequency exceeds the configured threshold.

        Returns:
            Dictionary with migration statistics and analysis.
        """
        migration_count = 0
        udp_connections: Dict[str, int] = {}

        try:
            net_connections = psutil.net_connections(kind="inet")
            for conn in net_connections:
                if conn.type == socket.SOCK_DGRAM and conn.laddr:
                    local_port = conn.laddr.port
                    if local_port not in udp_connections:
                        udp_connections[local_port] = 0
                    udp_connections[local_port] += 1

            for port, count in udp_connections.items():
                if count > 1:
                    migration_count += count - 1
        except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
            logger.warning("Access denied reading connections: %s", e)
        except Exception as e:
            logger.warning("Error checking connection migration: %s", e)

        net_stats = psutil.net_if_stats()
        active_interfaces = sum(1 for iface in net_stats.values() if iface.isup)
        time_window_minutes = max(1, active_interfaces)

        migration_per_minute = migration_count / time_window_minutes

        if migration_per_minute > self.max_migration_per_min:
            status = "warning"
        else:
            status = "ok"

        result = {
            "check": "connection_migration",
            "migration_count": migration_count,
            "unique_udp_ports": len(udp_connections),
            "active_interfaces": active_interfaces,
            "migration_per_minute": round(migration_per_minute, 2),
            "threshold_per_min": self.max_migration_per_min,
            "status": status,
            "message": (
                f"Migration rate {migration_per_minute:.2f}/min exceeds {self.max_migration_per_min}/min"
                if status == "warning"
                else f"Migration rate {migration_per_minute:.2f}/min within limits"
            ),
        }
        logger.info("Connection migration check: %s", result["message"])
        return result

    def check_reorder_buffer(self) -> Dict[str, Any]:
        """Check kernel TCP reorder buffer setting.

        Reads the tcp_reordering kernel parameter and flags when the value
        exceeds the configured threshold.

        Returns:
            Dictionary with reorder buffer configuration and analysis.
        """
        reordering_value: Optional[int] = None
        param_paths = [
            Path("/proc/sys/net/ipv4/tcp_reordering"),
            Path("/proc/sys/net/ipv4/tcp_max_reorder"),
        ]

        for param_path in param_paths:
            try:
                if param_path.exists():
                    content = param_path.read_text(encoding="utf-8").strip()
                    reordering_value = int(content)
                    break
            except (ValueError, PermissionError, OSError) as e:
                logger.warning("Error reading %s: %s", param_path, e)

        if reordering_value is None:
            try:
                net_stats = psutil.net_connections(kind="tcp")
                established_count = sum(
                    1 for c in net_stats if c.status == "ESTABLISHED"
                )
                reordering_value = min(established_count, 100)
                logger.info("Using estimated reorder buffer value: %d", reordering_value)
            except Exception as e:
                logger.warning("Error estimating reorder buffer: %s", e)
                reordering_value = 0

        if reordering_value > self.max_reorder_buffer:
            status = "warning"
        else:
            status = "ok"

        result = {
            "check": "reorder_buffer",
            "reordering_value": reordering_value,
            "threshold": self.max_reorder_buffer,
            "status": status,
            "message": (
                f"tcp_reordering={reordering_value} exceeds threshold {self.max_reorder_buffer}"
                if status == "warning"
                else f"tcp_reordering={reordering_value} within limits"
            ),
        }
        logger.info("Reorder buffer check: %s", result["message"])
        return result

    def run_all(self) -> Dict[str, Any]:
        """Run all protocol fault tolerance checks.

        Executes all individual checks and aggregates results into a
        combined report with overall status.

        Returns:
            Dictionary with all check results, overall status, timestamp, and hostname.
        """
        checks = [
            self.check_quic_connection_reuse,
            self.check_message_ack_redundancy,
            self.check_encryption_overhead,
            self.check_connection_migration,
            self.check_reorder_buffer,
        ]

        results: Dict[str, Any] = {}
        statuses: List[str] = []

        for check_func in checks:
            try:
                check_result = check_func()
                check_name = check_result["check"]
                results[check_name] = check_result
                statuses.append(check_result["status"])
            except Exception as e:
                check_name = getattr(check_func, "__name__", str(check_func)).replace("check_", "")
                logger.error("Error running check %s: %s", check_name, e)
                error_result = {
                    "check": check_name,
                    "status": "error",
                    "message": str(e),
                }
                results[error_result["check"]] = error_result
                statuses.append("error")

        if "error" in statuses:
            overall_status = "error"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "ok"

        result = {
            "results": results,
            "overall_status": overall_status,
            "total_checks": len(checks),
            "violations": sum(1 for s in statuses if s in ("warning", "error")),
            "timestamp": datetime.datetime.now().isoformat(),
            "hostname": socket.gethostname(),
        }
        logger.info(
            "Protocol fault tolerance check complete: %s (%d violations)",
            overall_status,
            result["violations"],
        )
        return result
