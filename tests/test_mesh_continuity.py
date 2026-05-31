"""Unit tests for ServiceMeshFaultTolerance and BusinessContinuity."""

import unittest
from unittest.mock import patch

import pytest

from core.service_mesh_fault_tolerance import ServiceMeshFaultTolerance
from core.business_continuity import BusinessContinuity


class TestServiceMeshFaultToleranceRetryAmplification(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.check_retry_amplification."""

    def setUp(self):
        self.mesh = ServiceMeshFaultTolerance()

    def test_ok_below_threshold(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_retry_rate": 0.10, "downstream_retry_rate": 0.05}
        )
        result = mesh.check_retry_amplification()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["max_retry_rate"] == 0.10

    def test_flagged_above_threshold(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_retry_rate": 0.10, "downstream_retry_rate": 0.25}
        )
        result = mesh.check_retry_amplification()
        assert result["status"] == "critical"
        assert result["flagged"] is True

    def test_exactly_at_threshold_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_retry_rate": 0.20, "downstream_retry_rate": 0.05}
        )
        result = mesh.check_retry_amplification()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.mesh.check_retry_amplification()
        for key in (
            "check", "status", "upstream_retry_rate",
            "downstream_retry_rate", "max_retry_rate",
            "threshold", "flagged", "detail",
        ):
            assert key in result

    def test_custom_config(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_retry_rate": 0.50, "downstream_retry_rate": 0.60}
        )
        result = mesh.check_retry_amplification()
        assert result["upstream_retry_rate"] == 0.50
        assert result["downstream_retry_rate"] == 0.60
        assert result["flagged"] is True


class TestServiceMeshFaultToleranceCircuitBreaker(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.check_circuit_breaker_false_trigger."""

    def setUp(self):
        self.mesh = ServiceMeshFaultTolerance()

    def test_ok_no_false_triggers(self):
        result = self.mesh.check_circuit_breaker_false_trigger()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["false_trigger_count"] == 0

    def test_flagged_with_false_triggers(self):
        mesh = ServiceMeshFaultTolerance(
            {"circuit_breaker_false_triggers": 3, "circuit_breaker_total_triggers": 10}
        )
        result = mesh.check_circuit_breaker_false_trigger()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_low_false_rate_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"circuit_breaker_false_triggers": 1, "circuit_breaker_total_triggers": 100}
        )
        result = mesh.check_circuit_breaker_false_trigger()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.mesh.check_circuit_breaker_false_trigger()
        for key in (
            "check", "status", "false_trigger_count",
            "total_triggers", "false_rate", "flagged", "detail",
        ):
            assert key in result


class TestServiceMeshFaultToleranceTimeoutChain(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.check_timeout_chain_reaction."""

    def setUp(self):
        self.mesh = ServiceMeshFaultTolerance()

    def test_ok_correct_order(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_timeout_ms": 5000, "downstream_timeout_ms": 3000}
        )
        result = mesh.check_timeout_chain_reaction()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_inverted_order(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_timeout_ms": 2000, "downstream_timeout_ms": 5000}
        )
        result = mesh.check_timeout_chain_reaction()
        assert result["status"] == "critical"
        assert result["flagged"] is True

    def test_same_timeout_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"upstream_timeout_ms": 3000, "downstream_timeout_ms": 3000}
        )
        result = mesh.check_timeout_chain_reaction()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.mesh.check_timeout_chain_reaction()
        for key in (
            "check", "status", "upstream_timeout_ms",
            "downstream_timeout_ms", "flagged", "detail",
        ):
            assert key in result


class TestServiceMeshFaultToleranceCanaryWaste(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.check_canary_traffic_waste."""

    def setUp(self):
        self.mesh = ServiceMeshFaultTolerance()

    def test_ok_low_ratio_and_short_duration(self):
        result = self.mesh.check_canary_traffic_waste()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_high_ratio_long_duration(self):
        mesh = ServiceMeshFaultTolerance(
            {"canary_traffic_ratio": 0.25, "canary_duration_hours": 3.0}
        )
        result = mesh.check_canary_traffic_waste()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_high_ratio_short_duration_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"canary_traffic_ratio": 0.25, "canary_duration_hours": 0.5}
        )
        result = mesh.check_canary_traffic_waste()
        assert result["flagged"] is False

    def test_low_ratio_long_duration_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"canary_traffic_ratio": 0.10, "canary_duration_hours": 3.0}
        )
        result = mesh.check_canary_traffic_waste()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.mesh.check_canary_traffic_waste()
        for key in (
            "check", "status", "canary_ratio", "duration_hours",
            "ratio_threshold", "duration_threshold_hours",
            "flagged", "detail",
        ):
            assert key in result


class TestServiceMeshFaultToleranceSidecarOverhead(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.check_sidecar_overhead."""

    def setUp(self):
        self.mesh = ServiceMeshFaultTolerance()

    def test_ok_low_overhead(self):
        result = self.mesh.check_sidecar_overhead()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_high_overhead(self):
        mesh = ServiceMeshFaultTolerance(
            {"sidecar_cpu_pct": 60.0, "main_cpu_pct": 80.0}
        )
        result = mesh.check_sidecar_overhead()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_exactly_at_threshold_not_flagged(self):
        mesh = ServiceMeshFaultTolerance(
            {"sidecar_cpu_pct": 25.0, "main_cpu_pct": 50.0}
        )
        result = mesh.check_sidecar_overhead()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.mesh.check_sidecar_overhead()
        for key in (
            "check", "status", "sidecar_cpu_pct", "main_cpu_pct",
            "ratio", "threshold", "flagged", "detail",
        ):
            assert key in result


class TestServiceMeshFaultToleranceRunAll(unittest.TestCase):
    """Tests for ServiceMeshFaultTolerance.run_all."""

    @patch("core.service_mesh_fault_tolerance.socket.gethostname")
    @patch("core.service_mesh_fault_tolerance.datetime")
    def test_run_all_ok(self, mock_dt, mock_host):
        mock_dt.datetime.now.return_value.isoformat.return_value = "2026-01-01T00:00:00"
        mock_host.return_value = "testhost"
        mesh = ServiceMeshFaultTolerance(
            {
                "upstream_retry_rate": 0.05,
                "downstream_retry_rate": 0.05,
                "circuit_breaker_false_triggers": 0,
                "upstream_timeout_ms": 5000,
                "downstream_timeout_ms": 3000,
                "canary_traffic_ratio": 0.05,
                "canary_duration_hours": 0.5,
                "sidecar_cpu_pct": 10.0,
                "main_cpu_pct": 50.0,
            }
        )
        result = mesh.run_all()
        assert result["overall_status"] == "ok"
        assert result["hostname"] == "testhost"
        assert result["flagged_count"] == 0
        assert len(result["checks"]) == 5

    @patch("core.service_mesh_fault_tolerance.socket.gethostname")
    def test_run_all_critical(self, mock_host):
        mock_host.return_value = "testhost"
        mesh = ServiceMeshFaultTolerance(
            {
                "upstream_retry_rate": 0.30,
                "downstream_retry_rate": 0.25,
                "circuit_breaker_false_triggers": 0,
                "upstream_timeout_ms": 1000,
                "downstream_timeout_ms": 5000,
                "canary_traffic_ratio": 0.05,
                "canary_duration_hours": 0.5,
                "sidecar_cpu_pct": 10.0,
                "main_cpu_pct": 50.0,
            }
        )
        result = mesh.run_all()
        assert result["overall_status"] == "critical"

    @patch("core.service_mesh_fault_tolerance.socket.gethostname")
    def test_run_all_warning(self, mock_host):
        mock_host.return_value = "testhost"
        mesh = ServiceMeshFaultTolerance(
            {
                "upstream_retry_rate": 0.05,
                "downstream_retry_rate": 0.05,
                "circuit_breaker_false_triggers": 2,
                "circuit_breaker_total_triggers": 10,
                "upstream_timeout_ms": 5000,
                "downstream_timeout_ms": 3000,
                "canary_traffic_ratio": 0.05,
                "canary_duration_hours": 0.5,
                "sidecar_cpu_pct": 10.0,
                "main_cpu_pct": 50.0,
            }
        )
        result = mesh.run_all()
        assert result["overall_status"] == "warning"

    def test_all_checks_have_check_field(self):
        mesh = ServiceMeshFaultTolerance()
        result = mesh.run_all()
        for check in result["checks"]:
            assert "check" in check
            assert "status" in check
            assert "flagged" in check
            assert "detail" in check


class TestBusinessContinuityMultiCloudSync(unittest.TestCase):
    """Tests for BusinessContinuity.check_multi_cloud_sync_delay."""

    def setUp(self):
        self.bc = BusinessContinuity()

    def test_ok_below_threshold(self):
        result = self.bc.check_multi_cloud_sync_delay()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_above_threshold(self):
        bc = BusinessContinuity({"cross_region_sync_delay_s": 500.0})
        result = bc.check_multi_cloud_sync_delay()
        assert result["status"] == "critical"
        assert result["flagged"] is True

    def test_exact_threshold_not_flagged(self):
        bc = BusinessContinuity({"cross_region_sync_delay_s": 300.0})
        result = bc.check_multi_cloud_sync_delay()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.bc.check_multi_cloud_sync_delay()
        for key in (
            "check", "status", "sync_delay_s", "threshold_s",
            "primary_region", "replica_regions", "flagged", "detail",
        ):
            assert key in result


class TestBusinessContinuityFailoverTime(unittest.TestCase):
    """Tests for BusinessContinuity.check_failover_time."""

    def setUp(self):
        self.bc = BusinessContinuity()

    def test_ok_below_threshold(self):
        bc = BusinessContinuity(
            {
                "failover_detection_time_s": 5.0,
                "failover_decision_time_s": 3.0,
                "failover_switch_time_s": 10.0,
            }
        )
        result = bc.check_failover_time()
        assert result["status"] == "ok"
        assert result["flagged"] is False
        assert result["failover_time_s"] == 18.0

    def test_flagged_above_threshold(self):
        bc = BusinessContinuity(
            {
                "failover_detection_time_s": 30.0,
                "failover_decision_time_s": 20.0,
                "failover_switch_time_s": 15.0,
            }
        )
        result = bc.check_failover_time()
        assert result["status"] == "critical"
        assert result["flagged"] is True

    def test_exact_threshold_not_flagged(self):
        bc = BusinessContinuity(
            {
                "failover_detection_time_s": 20.0,
                "failover_decision_time_s": 20.0,
                "failover_switch_time_s": 20.0,
            }
        )
        result = bc.check_failover_time()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.bc.check_failover_time()
        for key in (
            "check", "status", "failover_time_s", "detection_time_s",
            "decision_time_s", "switch_time_s", "threshold_s",
            "flagged", "detail",
        ):
            assert key in result


class TestBusinessContinuityFailureGranularity(unittest.TestCase):
    """Tests for BusinessContinuity.check_failure_granularity."""

    def setUp(self):
        self.bc = BusinessContinuity()

    def test_ok_service_level(self):
        bc = BusinessContinuity(
            {
                "circuit_breaker_granularity": "service",
                "circuit_breaker_affected_services": ["payment-service"],
            }
        )
        result = bc.check_failure_granularity()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_global(self):
        bc = BusinessContinuity(
            {
                "circuit_breaker_granularity": "global",
                "circuit_breaker_affected_services": ["all"],
            }
        )
        result = bc.check_failure_granularity()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_return_fields(self):
        result = self.bc.check_failure_granularity()
        for key in (
            "check", "status", "granularity",
            "affected_services", "flagged", "detail",
        ):
            assert key in result


class TestBusinessContinuityDnsTtl(unittest.TestCase):
    """Tests for BusinessContinuity.check_dns_ttl."""

    def setUp(self):
        self.bc = BusinessContinuity()

    def test_ok_below_threshold(self):
        result = self.bc.check_dns_ttl()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_above_threshold(self):
        bc = BusinessContinuity({"dns_ttl_s": 120})
        result = bc.check_dns_ttl()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_exact_threshold_not_flagged(self):
        bc = BusinessContinuity({"dns_ttl_s": 60})
        result = bc.check_dns_ttl()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.bc.check_dns_ttl()
        for key in (
            "check", "status", "dns_ttl_s", "threshold_s",
            "record_name", "flagged", "detail",
        ):
            assert key in result


class TestBusinessContinuityCrossRegionCost(unittest.TestCase):
    """Tests for BusinessContinuity.check_cross_region_traffic_cost."""

    def setUp(self):
        self.bc = BusinessContinuity()

    def test_ok_below_threshold(self):
        result = self.bc.check_cross_region_traffic_cost()
        assert result["status"] == "ok"
        assert result["flagged"] is False

    def test_flagged_above_threshold(self):
        bc = BusinessContinuity({"cross_region_transfer_tb_month": 2.5})
        result = bc.check_cross_region_traffic_cost()
        assert result["status"] == "warning"
        assert result["flagged"] is True

    def test_exact_threshold_not_flagged(self):
        bc = BusinessContinuity({"cross_region_transfer_tb_month": 1.0})
        result = bc.check_cross_region_traffic_cost()
        assert result["flagged"] is False

    def test_return_fields(self):
        result = self.bc.check_cross_region_traffic_cost()
        for key in (
            "check", "status", "transfer_tb_month",
            "threshold_tb_month", "regions", "flagged", "detail",
        ):
            assert key in result


class TestBusinessContinuityRunAll(unittest.TestCase):
    """Tests for BusinessContinuity.run_all."""

    @patch("core.business_continuity.socket.gethostname")
    @patch("core.business_continuity.datetime")
    def test_run_all_ok(self, mock_dt, mock_host):
        mock_dt.datetime.now.return_value.isoformat.return_value = "2026-01-01T00:00:00"
        mock_host.return_value = "testhost"
        bc = BusinessContinuity(
            {
                "cross_region_sync_delay_s": 120.0,
                "failover_detection_time_s": 5.0,
                "failover_decision_time_s": 3.0,
                "failover_switch_time_s": 10.0,
                "circuit_breaker_granularity": "service",
                "dns_ttl_s": 30,
                "cross_region_transfer_tb_month": 0.3,
            }
        )
        result = bc.run_all()
        assert result["overall_status"] == "ok"
        assert result["hostname"] == "testhost"
        assert result["flagged_count"] == 0
        assert len(result["checks"]) == 5

    @patch("core.business_continuity.socket.gethostname")
    def test_run_all_critical(self, mock_host):
        mock_host.return_value = "testhost"
        bc = BusinessContinuity(
            {
                "cross_region_sync_delay_s": 500.0,
                "failover_detection_time_s": 30.0,
                "failover_decision_time_s": 20.0,
                "failover_switch_time_s": 15.0,
                "circuit_breaker_granularity": "service",
                "dns_ttl_s": 30,
                "cross_region_transfer_tb_month": 0.3,
            }
        )
        result = bc.run_all()
        assert result["overall_status"] == "critical"

    @patch("core.business_continuity.socket.gethostname")
    def test_run_all_warning(self, mock_host):
        mock_host.return_value = "testhost"
        bc = BusinessContinuity(
            {
                "cross_region_sync_delay_s": 120.0,
                "failover_detection_time_s": 5.0,
                "failover_decision_time_s": 3.0,
                "failover_switch_time_s": 10.0,
                "circuit_breaker_granularity": "global",
                "circuit_breaker_affected_services": ["all"],
                "dns_ttl_s": 120,
                "cross_region_transfer_tb_month": 2.5,
            }
        )
        result = bc.run_all()
        assert result["overall_status"] == "warning"

    def test_all_checks_have_check_field(self):
        bc = BusinessContinuity()
        result = bc.run_all()
        for check in result["checks"]:
            assert "check" in check
            assert "status" in check
            assert "flagged" in check
            assert "detail" in check


if __name__ == "__main__":
    unittest.main()
