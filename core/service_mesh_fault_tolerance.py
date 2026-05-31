"""Service mesh fault tolerance checks for Spider Diary.

Detects retry amplification, circuit breaker false triggers,
timeout chain reactions, canary traffic waste, and sidecar overhead.
"""

import datetime
import logging
import socket
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


RETRY_THRESHOLD = 0.20
CANARY_TRAFFIC_THRESHOLD = 0.15
CANARY_DURATION_THRESHOLD_HOURS = 1
SIDECAR_RESOURCE_RATIO_THRESHOLD = 0.50


class ServiceMeshFaultTolerance:
    """Service mesh fault tolerance checker.

    Performs five categories of checks on service mesh health:
    retry amplification, circuit breaker false triggers, timeout
    chain reactions, canary traffic waste, and sidecar overhead.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize ServiceMeshFaultTolerance.

        Args:
            config: Optional dict of configuration overrides.
        """
        self.config = config or {}

    def check_retry_amplification(self) -> Dict[str, Any]:
        """Check retry rates across mesh services.

        Flags any service whose retry rate exceeds 20%.

        Returns:
            Dict with status, retry_rate, service, and flagged fields.
        """
        upstream_retry_rate = self.config.get("upstream_retry_rate", 0.10)
        downstream_retry_rate = self.config.get("downstream_retry_rate", 0.05)
        max_rate = max(upstream_retry_rate, downstream_retry_rate)
        flagged = max_rate > RETRY_THRESHOLD

        result = {
            "check": "retry_amplification",
            "status": "critical" if flagged else "ok",
            "upstream_retry_rate": upstream_retry_rate,
            "downstream_retry_rate": downstream_retry_rate,
            "max_retry_rate": max_rate,
            "threshold": RETRY_THRESHOLD,
            "flagged": flagged,
            "detail": (
                f"Retry rate {max_rate:.1%} exceeds threshold {RETRY_THRESHOLD:.0%}"
                if flagged
                else "Retry rates within acceptable range"
            ),
        }
        logger.info("Retry amplification check: flagged=%s", flagged)
        return result

    def check_circuit_breaker_false_trigger(self) -> Dict[str, Any]:
        """Check for false circuit breaker triggers.

        Occur when healthy requests are rejected due to misconfigured
        thresholds or transient spikes.

        Returns:
            Dict with status, false_trigger_count, and flagged fields.
        """
        false_triggers = self.config.get("circuit_breaker_false_triggers", 0)
        total_triggers = self.config.get("circuit_breaker_total_triggers", 0)
        false_rate = false_triggers / max(total_triggers, 1)
        flagged = false_triggers > 0 and false_rate > 0.05

        result = {
            "check": "circuit_breaker_false_trigger",
            "status": "warning" if flagged else "ok",
            "false_trigger_count": false_triggers,
            "total_triggers": total_triggers,
            "false_rate": round(false_rate, 4),
            "flagged": flagged,
            "detail": (
                f"{false_triggers} false triggers detected ({false_rate:.1%} of total)"
                if flagged
                else "No false circuit breaker triggers detected"
            ),
        }
        logger.info("Circuit breaker false trigger check: flagged=%s", flagged)
        return result

    def check_timeout_chain_reaction(self) -> Dict[str, Any]:
        """Check for upstream/downstream timeout mismatches.

        A chain reaction occurs when an upstream timeout is shorter
        than a downstream timeout, causing cascading failures.

        Returns:
            Dict with status, upstream_timeout_ms, downstream_timeout_ms,
            and flagged fields.
        """
        upstream_timeout_ms = self.config.get("upstream_timeout_ms", 5000)
        downstream_timeout_ms = self.config.get("downstream_timeout_ms", 3000)
        flagged = upstream_timeout_ms < downstream_timeout_ms

        result = {
            "check": "timeout_chain_reaction",
            "status": "critical" if flagged else "ok",
            "upstream_timeout_ms": upstream_timeout_ms,
            "downstream_timeout_ms": downstream_timeout_ms,
            "flagged": flagged,
            "detail": (
                f"Upstream timeout ({upstream_timeout_ms}ms) < downstream timeout ({downstream_timeout_ms}ms)"
                if flagged
                else "Timeout chain is correctly configured"
            ),
        }
        logger.info("Timeout chain reaction check: flagged=%s", flagged)
        return result

    def check_canary_traffic_waste(self) -> Dict[str, Any]:
        """Check canary traffic ratio and duration.

        Flags when canary traffic exceeds 15% for more than 1 hour,
    indicating the canary has not been promoted or rolled back.

        Returns:
            Dict with status, canary_ratio, duration_hours, and flagged fields.
        """
        canary_ratio = self.config.get("canary_traffic_ratio", 0.05)
        duration_hours = self.config.get("canary_duration_hours", 0.5)
        flagged = (
            canary_ratio > CANARY_TRAFFIC_THRESHOLD
            and duration_hours > CANARY_DURATION_THRESHOLD_HOURS
        )

        result = {
            "check": "canary_traffic_waste",
            "status": "warning" if flagged else "ok",
            "canary_ratio": canary_ratio,
            "duration_hours": duration_hours,
            "ratio_threshold": CANARY_TRAFFIC_THRESHOLD,
            "duration_threshold_hours": CANARY_DURATION_THRESHOLD_HOURS,
            "flagged": flagged,
            "detail": (
                f"Canary traffic {canary_ratio:.1%} for {duration_hours:.1f}h exceeds limits"
                if flagged
                else "Canary traffic within acceptable range"
            ),
        }
        logger.info("Canary traffic waste check: flagged=%s", flagged)
        return result

    def check_sidecar_overhead(self) -> Dict[str, Any]:
        """Check sidecar vs main container resource ratio.

        Flags when sidecar resource consumption exceeds 50% of the
        main container, indicating the proxy is over-provisioned.

        Returns:
            Dict with status, sidecar_cpu_pct, main_cpu_pct, ratio, and flagged fields.
        """
        sidecar_cpu_pct = self.config.get("sidecar_cpu_pct", 10.0)
        main_cpu_pct = self.config.get("main_cpu_pct", 50.0)
        ratio = sidecar_cpu_pct / max(main_cpu_pct, 1.0)
        flagged = ratio > SIDECAR_RESOURCE_RATIO_THRESHOLD

        result = {
            "check": "sidecar_overhead",
            "status": "warning" if flagged else "ok",
            "sidecar_cpu_pct": sidecar_cpu_pct,
            "main_cpu_pct": main_cpu_pct,
            "ratio": round(ratio, 4),
            "threshold": SIDECAR_RESOURCE_RATIO_THRESHOLD,
            "flagged": flagged,
            "detail": (
                f"Sidecar overhead ratio {ratio:.1%} exceeds threshold {SIDECAR_RESOURCE_RATIO_THRESHOLD:.0%}"
                if flagged
                else "Sidecar overhead within acceptable range"
            ),
        }
        logger.info("Sidecar overhead check: flagged=%s", flagged)
        return result

    def run_all(self) -> Dict[str, Any]:
        """Run all service mesh fault tolerance checks.

        Returns:
            Dict containing individual check results, overall_status,
            and hostname.
        """
        checks: List[Dict[str, Any]] = [
            self.check_retry_amplification(),
            self.check_circuit_breaker_false_trigger(),
            self.check_timeout_chain_reaction(),
            self.check_canary_traffic_waste(),
            self.check_sidecar_overhead(),
        ]

        statuses = [c["status"] for c in checks]

        if "critical" in statuses:
            overall_status = "critical"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "ok"

        result = {
            "checks": checks,
            "overall_status": overall_status,
            "timestamp": datetime.datetime.now().isoformat(),
            "hostname": socket.gethostname(),
            "flagged_count": sum(1 for c in checks if c["flagged"]),
        }
        logger.info(
            "Service mesh fault tolerance all checks: overall_status=%s, flagged=%d",
            overall_status,
            result["flagged_count"],
        )
        return result
