"""Business continuity checks for Spider Diary.

Validates multi-cloud sync, failover timing, failure granularity,
DNS TTL, and cross-region traffic costs.
"""

import datetime
import logging
import socket
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SYNC_DELAY_THRESHOLD_S = 300
FAILOVER_THRESHOLD_S = 60
DNS_TTL_THRESHOLD_S = 60
CROSS_REGION_COST_THRESHOLD_TB = 1.0


class BusinessContinuity:
    """Business continuity checker.

    Performs five categories of checks on continuity readiness:
    multi-cloud sync delay, failover time, failure granularity,
    DNS TTL, and cross-region traffic cost.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize BusinessContinuity.

        Args:
            config: Optional dict of configuration overrides.
        """
        self.config = config or {}

    def check_multi_cloud_sync_delay(self) -> Dict[str, Any]:
        """Check cross-region synchronization latency.

        Flags when cross-region sync exceeds 300 seconds.

        Returns:
            Dict with status, sync_delay_s, regions, and flagged fields.
        """
        sync_delay_s = self.config.get("cross_region_sync_delay_s", 120.0)
        primary_region = self.config.get("primary_region", "us-east-1")
        replica_regions = self.config.get("replica_regions", ["eu-west-1", "ap-south-1"])
        flagged = sync_delay_s > SYNC_DELAY_THRESHOLD_S

        result = {
            "check": "multi_cloud_sync_delay",
            "status": "critical" if flagged else "ok",
            "sync_delay_s": sync_delay_s,
            "threshold_s": SYNC_DELAY_THRESHOLD_S,
            "primary_region": primary_region,
            "replica_regions": replica_regions,
            "flagged": flagged,
            "detail": (
                f"Cross-region sync delay {sync_delay_s:.0f}s exceeds {SYNC_DELAY_THRESHOLD_S}s threshold"
                if flagged
                else "Cross-region sync within acceptable range"
            ),
        }
        logger.info("Multi-cloud sync delay check: flagged=%s", flagged)
        return result

    def check_failover_time(self) -> Dict[str, Any]:
        """Check failover detection-to-switch time.

        Flags when total failover time exceeds 60 seconds.

        Returns:
            Dict with status, failover_time_s, components, and flagged fields.
        """
        detection_time_s = self.config.get("failover_detection_time_s", 10.0)
        decision_time_s = self.config.get("failover_decision_time_s", 5.0)
        switch_time_s = self.config.get("failover_switch_time_s", 15.0)
        total_s = detection_time_s + decision_time_s + switch_time_s
        flagged = total_s > FAILOVER_THRESHOLD_S

        result = {
            "check": "failover_time",
            "status": "critical" if flagged else "ok",
            "failover_time_s": round(total_s, 1),
            "detection_time_s": detection_time_s,
            "decision_time_s": decision_time_s,
            "switch_time_s": switch_time_s,
            "threshold_s": FAILOVER_THRESHOLD_S,
            "flagged": flagged,
            "detail": (
                f"Failover time {total_s:.1f}s exceeds {FAILOVER_THRESHOLD_S}s threshold"
                if flagged
                else "Failover time within acceptable range"
            ),
        }
        logger.info("Failover time check: flagged=%s", flagged)
        return result

    def check_failure_granularity(self) -> Dict[str, Any]:
        """Check if circuit breaker granularity is appropriate.

        A global circuit breaker that blocks all services when one
        fails is a misconfiguration. Flags when granularity is 'global'.

        Returns:
            Dict with status, granularity, scope, and flagged fields.
        """
        granularity = self.config.get("circuit_breaker_granularity", "service")
        affected_services = self.config.get("circuit_breaker_affected_services", ["all"])
        flagged = granularity == "global"

        result = {
            "check": "failure_granularity",
            "status": "warning" if flagged else "ok",
            "granularity": granularity,
            "affected_services": affected_services,
            "flagged": flagged,
            "detail": (
                f"Circuit breaker granularity is '{granularity}' — affects {', '.join(str(s) for s in affected_services)}"
                if flagged
                else f"Circuit breaker granularity is '{granularity}' — properly scoped"
            ),
        }
        logger.info("Failure granularity check: flagged=%s", flagged)
        return result

    def check_dns_ttl(self) -> Dict[str, Any]:
        """Check DNS TTL configuration.

        Flags when DNS TTL exceeds 60 seconds, which prolongs
        failover propagation time.

        Returns:
            Dict with status, dns_ttl_s, record_name, and flagged fields.
        """
        dns_ttl_s = self.config.get("dns_ttl_s", 30)
        record_name = self.config.get("dns_record_name", "app.example.com")
        flagged = dns_ttl_s > DNS_TTL_THRESHOLD_S

        result = {
            "check": "dns_ttl",
            "status": "warning" if flagged else "ok",
            "dns_ttl_s": dns_ttl_s,
            "threshold_s": DNS_TTL_THRESHOLD_S,
            "record_name": record_name,
            "flagged": flagged,
            "detail": (
                f"DNS TTL {dns_ttl_s}s for {record_name} exceeds {DNS_TTL_THRESHOLD_S}s threshold"
                if flagged
                else "DNS TTL within acceptable range"
            ),
        }
        logger.info("DNS TTL check: flagged=%s", flagged)
        return result

    def check_cross_region_traffic_cost(self) -> Dict[str, Any]:
        """Check cross-region data transfer volume.

        Flags when cross-region transfer exceeds 1 TB/month.

        Returns:
            Dict with status, transfer_tb_month, regions, and flagged fields.
        """
        transfer_tb_month = self.config.get("cross_region_transfer_tb_month", 0.3)
        regions = self.config.get("traffic_regions", ["us-east-1", "eu-west-1"])
        flagged = transfer_tb_month > CROSS_REGION_COST_THRESHOLD_TB

        result = {
            "check": "cross_region_traffic_cost",
            "status": "warning" if flagged else "ok",
            "transfer_tb_month": transfer_tb_month,
            "threshold_tb_month": CROSS_REGION_COST_THRESHOLD_TB,
            "regions": regions,
            "flagged": flagged,
            "detail": (
                f"Cross-region transfer {transfer_tb_month:.2f} TB/month exceeds {CROSS_REGION_COST_THRESHOLD_TB} TB threshold"
                if flagged
                else "Cross-region transfer within acceptable range"
            ),
        }
        logger.info("Cross-region traffic cost check: flagged=%s", flagged)
        return result

    def run_all(self) -> Dict[str, Any]:
        """Run all business continuity checks.

        Returns:
            Dict containing individual check results, overall_status,
            timestamp, hostname, and flagged_count.
        """
        checks: List[Dict[str, Any]] = [
            self.check_multi_cloud_sync_delay(),
            self.check_failover_time(),
            self.check_failure_granularity(),
            self.check_dns_ttl(),
            self.check_cross_region_traffic_cost(),
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
            "Business continuity all checks: overall_status=%s, flagged=%d",
            overall_status,
            result["flagged_count"],
        )
        return result
