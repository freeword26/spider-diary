"""Unit tests for ProtocolFaultTolerance class."""

import socket
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import psutil
import pytest

from core.protocol_fault_tolerance import ProtocolFaultTolerance


class TestProtocolFaultToleranceInit(unittest.TestCase):
    """Tests for ProtocolFaultTolerance initialization."""

    def test_default_initialization(self):
        checker = ProtocolFaultTolerance()
        assert checker.quic_port == 443
        assert checker.max_quic_per_service == 50
        assert checker.max_ack_redundancy_pct == 15.0
        assert checker.max_encryption_latency_ms == 5.0
        assert checker.max_migration_per_min == 10
        assert checker.max_reorder_buffer == 30

    def test_custom_initialization(self):
        checker = ProtocolFaultTolerance(
            quic_port=8443,
            max_quic_per_service=100,
            max_ack_redundancy_pct=20.0,
            max_encryption_latency_ms=10.0,
            max_migration_per_min=20,
            max_reorder_buffer=50,
        )
        assert checker.quic_port == 8443
        assert checker.max_quic_per_service == 100
        assert checker.max_ack_redundancy_pct == 20.0
        assert checker.max_encryption_latency_ms == 10.0
        assert checker.max_migration_per_min == 20
        assert checker.max_reorder_buffer == 50


class TestCheckQuicConnectionReuse(unittest.TestCase):
    """Tests for check_quic_connection_reuse method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_no_connections(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.checker.check_quic_connection_reuse()
        assert result["check"] == "quic_connection_reuse"
        assert result["total_connections"] == 0
        assert result["status"] == "info"
        assert result["violations"] == {}

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_connections_within_limits(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="UDP    0.0.0.0:1234    10.0.0.1:443    *:*\nUDP    0.0.0.0:1235    10.0.0.2:443    *:*\n",
        )
        result = self.checker.check_quic_connection_reuse()
        assert result["status"] == "ok"
        assert result["total_connections"] == 2
        assert result["violations"] == {}

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_connections_exceed_threshold(self, mock_run):
        lines = []
        for i in range(60):
            lines.append(f"UDP    0.0.0.0:{4000 + i}    10.0.0.1:443    *:*")
        mock_run.return_value = MagicMock(returncode=0, stdout="\n".join(lines))
        result = self.checker.check_quic_connection_reuse()
        assert result["status"] == "warning"
        assert result["violations"]["10.0.0.1"] == 60

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_netstat_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("netstat not found")
        result = self.checker.check_quic_connection_reuse()
        assert result["total_connections"] == 0
        assert result["status"] == "info"

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_netstat_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("netstat", 15)
        result = self.checker.check_quic_connection_reuse()
        assert result["total_connections"] == 0

    @patch("core.protocol_fault_tolerance.subprocess.run")
    def test_result_has_required_fields(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.checker.check_quic_connection_reuse()
        assert "check" in result
        assert "total_connections" in result
        assert "services" in result
        assert "violations" in result
        assert "threshold" in result
        assert "status" in result
        assert "message" in result


class TestCheckMessageAckRedundancy(unittest.TestCase):
    """Tests for check_message_ack_redundancy method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    @patch("core.protocol_fault_tolerance.psutil.net_io_counters")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_normal_ack_rate(self, mock_connections, mock_io):
        mock_connections.return_value = [
            MagicMock(type=socket.SOCK_STREAM, status="ESTABLISHED")
        ]
        mock_io.return_value = MagicMock(packets_sent=100000, packets_recv=100000)
        result = self.checker.check_message_ack_redundancy()
        assert result["check"] == "message_ack_redundancy"
        assert result["status"] == "ok"
        assert result["tcp_established"] == 1

    @patch("core.protocol_fault_tolerance.psutil.net_io_counters")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_high_ack_rate(self, mock_connections, mock_io):
        mock_connections.return_value = [
            MagicMock(type=socket.SOCK_STREAM, status="ESTABLISHED")
            for _ in range(100)
        ]
        mock_io.return_value = MagicMock(packets_sent=500, packets_recv=500)
        result = self.checker.check_message_ack_redundancy()
        assert result["status"] == "warning"
        assert result["duplicate_ack_rate"] > self.checker.max_ack_redundancy_pct

    @patch("core.protocol_fault_tolerance.psutil.net_io_counters")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_no_connections(self, mock_connections, mock_io):
        mock_connections.return_value = []
        mock_io.return_value = MagicMock(packets_sent=0, packets_recv=0)
        result = self.checker.check_message_ack_redundancy()
        assert result["status"] == "ok"
        assert result["duplicate_ack_rate"] == 0

    @patch("core.protocol_fault_tolerance.psutil.net_io_counters")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_access_denied(self, mock_connections, mock_io):
        mock_connections.side_effect = psutil.AccessDenied()
        mock_io.return_value = MagicMock(packets_sent=0, packets_recv=0)
        result = self.checker.check_message_ack_redundancy()
        assert result["status"] == "ok"
        assert result["tcp_total"] == 0

    @patch("core.protocol_fault_tolerance.psutil.net_io_counters")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_result_has_required_fields(self, mock_connections, mock_io):
        mock_connections.return_value = []
        mock_io.return_value = MagicMock(packets_sent=0, packets_recv=0)
        result = self.checker.check_message_ack_redundancy()
        assert "check" in result
        assert "tcp_total" in result
        assert "tcp_established" in result
        assert "udp_total" in result
        assert "packets_sent" in result
        assert "packets_recv" in result
        assert "duplicate_ack_rate" in result
        assert "threshold_pct" in result
        assert "status" in result
        assert "message" in result


class TestCheckEncryptionOverhead(unittest.TestCase):
    """Tests for check_encryption_overhead method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    def test_normal_latency(self):
        result = self.checker.check_encryption_overhead(test_data_size_mb=0.001)
        assert result["check"] == "encryption_overhead"
        assert "avg_latency_ms" in result
        assert "latency_per_mb_ms" in result

    def test_result_has_required_fields(self):
        result = self.checker.check_encryption_overhead(test_data_size_mb=0.001)
        assert "check" in result
        assert "test_data_size_mb" in result
        assert "iterations" in result
        assert "avg_latency_ms" in result
        assert "latency_per_mb_ms" in result
        assert "threshold_ms_per_mb" in result
        assert "status" in result
        assert "message" in result

    def test_high_latency(self):
        call_count = [0]

        def mock_perf_counter():
            call_count[0] += 1
            if call_count[0] <= 1:
                return 0.0
            return 10.0

        self.checker.max_encryption_latency_ms = 0.001
        with patch("core.protocol_fault_tolerance.time.perf_counter", side_effect=mock_perf_counter):
            result = self.checker.check_encryption_overhead(test_data_size_mb=0.1)
        assert result["status"] == "warning"


class TestCheckConnectionMigration(unittest.TestCase):
    """Tests for check_connection_migration method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    @patch("core.protocol_fault_tolerance.psutil.net_if_stats")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_normal_migration(self, mock_connections, mock_if_stats):
        mock_connections.return_value = [
            MagicMock(
                type=socket.SOCK_DGRAM,
                laddr=MagicMock(port=1234),
            )
        ]
        mock_if_stats.return_value = {"eth0": MagicMock(isup=True)}
        result = self.checker.check_connection_migration()
        assert result["check"] == "connection_migration"
        assert result["status"] == "ok"

    @patch("core.protocol_fault_tolerance.psutil.net_if_stats")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_high_migration(self, mock_connections, mock_if_stats):
        mock_connections.return_value = [
            MagicMock(
                type=socket.SOCK_DGRAM,
                laddr=MagicMock(port=1234),
            )
            for _ in range(50)
        ]
        mock_if_stats.return_value = {"eth0": MagicMock(isup=True)}
        result = self.checker.check_connection_migration()
        assert result["status"] == "warning"
        assert result["migration_per_minute"] > self.checker.max_migration_per_min

    @patch("core.protocol_fault_tolerance.psutil.net_if_stats")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_no_udp_connections(self, mock_connections, mock_if_stats):
        mock_connections.return_value = []
        mock_if_stats.return_value = {"eth0": MagicMock(isup=True)}
        result = self.checker.check_connection_migration()
        assert result["migration_count"] == 0
        assert result["status"] == "ok"

    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_access_denied(self, mock_connections):
        mock_connections.side_effect = psutil.AccessDenied()
        with patch("core.protocol_fault_tolerance.psutil.net_if_stats") as mock_if:
            mock_if.return_value = {"eth0": MagicMock(isup=True)}
            result = self.checker.check_connection_migration()
        assert result["status"] == "ok"

    @patch("core.protocol_fault_tolerance.psutil.net_if_stats")
    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    def test_result_has_required_fields(self, mock_connections, mock_if_stats):
        mock_connections.return_value = []
        mock_if_stats.return_value = {"eth0": MagicMock(isup=True)}
        result = self.checker.check_connection_migration()
        assert "check" in result
        assert "migration_count" in result
        assert "unique_udp_ports" in result
        assert "active_interfaces" in result
        assert "migration_per_minute" in result
        assert "threshold_per_min" in result
        assert "status" in result
        assert "message" in result


class TestCheckReorderBuffer(unittest.TestCase):
    """Tests for check_reorder_buffer method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    @patch("core.protocol_fault_tolerance.Path.read_text")
    @patch("core.protocol_fault_tolerance.Path.exists")
    def test_normal_reorder_value(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "5"
        result = self.checker.check_reorder_buffer()
        assert result["check"] == "reorder_buffer"
        assert result["reordering_value"] == 5
        assert result["status"] == "ok"

    @patch("core.protocol_fault_tolerance.Path.read_text")
    @patch("core.protocol_fault_tolerance.Path.exists")
    def test_high_reorder_value(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "50"
        result = self.checker.check_reorder_buffer()
        assert result["reordering_value"] == 50
        assert result["status"] == "warning"

    @patch("core.protocol_fault_tolerance.psutil.net_connections")
    @patch("core.protocol_fault_tolerance.Path.read_text")
    @patch("core.protocol_fault_tolerance.Path.exists")
    def test_proc_not_available(self, mock_exists, mock_read, mock_connections):
        mock_exists.return_value = False
        mock_read.side_effect = PermissionError()
        from unittest.mock import MagicMock
        mock_connections.return_value = [
            MagicMock(status="ESTABLISHED"),
            MagicMock(status="LISTEN"),
        ]
        result = self.checker.check_reorder_buffer()
        assert result["check"] == "reorder_buffer"
        assert "reordering_value" in result

    @patch("core.protocol_fault_tolerance.Path.exists")
    def test_boundary_value(self, mock_exists):
        mock_exists.return_value = True
        self.checker.max_reorder_buffer = 30
        with patch("core.protocol_fault_tolerance.Path.read_text") as mock_read:
            mock_read.return_value = "30"
            result = self.checker.check_reorder_buffer()
            assert result["status"] == "ok"

    def test_result_has_required_fields(self):
        from unittest.mock import MagicMock
        with patch("core.protocol_fault_tolerance.Path.exists", return_value=False), \
             patch("core.protocol_fault_tolerance.psutil.net_connections") as mock_conn:
            mock_conn.return_value = []
            result = self.checker.check_reorder_buffer()
        assert "check" in result
        assert "reordering_value" in result
        assert "threshold" in result
        assert "status" in result
        assert "message" in result


class TestRunAll(unittest.TestCase):
    """Tests for run_all method."""

    def setUp(self):
        self.checker = ProtocolFaultTolerance()

    @patch("core.protocol_fault_tolerance.socket.gethostname")
    @patch("core.protocol_fault_tolerance.datetime")
    @patch.object(ProtocolFaultTolerance, "check_reorder_buffer")
    @patch.object(ProtocolFaultTolerance, "check_connection_migration")
    @patch.object(ProtocolFaultTolerance, "check_encryption_overhead")
    @patch.object(ProtocolFaultTolerance, "check_message_ack_redundancy")
    @patch.object(ProtocolFaultTolerance, "check_quic_connection_reuse")
    def test_all_ok(
        self,
        mock_quic,
        mock_ack,
        mock_enc,
        mock_mig,
        mock_reorder,
        mock_dt,
        mock_host,
    ):
        mock_quic.return_value = {"check": "quic", "status": "ok"}
        mock_ack.return_value = {"check": "ack", "status": "ok"}
        mock_enc.return_value = {"check": "enc", "status": "ok"}
        mock_mig.return_value = {"check": "mig", "status": "ok"}
        mock_reorder.return_value = {"check": "reorder", "status": "ok"}
        mock_dt.datetime.now.return_value.isoformat.return_value = "2026-01-01T00:00:00"
        mock_host.return_value = "testhost"

        result = self.checker.run_all()

        assert result["overall_status"] == "ok"
        assert result["total_checks"] == 5
        assert result["violations"] == 0
        assert result["hostname"] == "testhost"
        assert "timestamp" in result
        assert "results" in result

    @patch("core.protocol_fault_tolerance.socket.gethostname")
    @patch.object(ProtocolFaultTolerance, "check_reorder_buffer")
    @patch.object(ProtocolFaultTolerance, "check_connection_migration")
    @patch.object(ProtocolFaultTolerance, "check_encryption_overhead")
    @patch.object(ProtocolFaultTolerance, "check_message_ack_redundancy")
    @patch.object(ProtocolFaultTolerance, "check_quic_connection_reuse")
    def test_one_warning(
        self,
        mock_quic,
        mock_ack,
        mock_enc,
        mock_mig,
        mock_reorder,
        mock_host,
    ):
        mock_quic.return_value = {"check": "quic", "status": "ok"}
        mock_ack.return_value = {"check": "ack", "status": "warning"}
        mock_enc.return_value = {"check": "enc", "status": "ok"}
        mock_mig.return_value = {"check": "mig", "status": "ok"}
        mock_reorder.return_value = {"check": "reorder", "status": "ok"}
        mock_host.return_value = "testhost"

        result = self.checker.run_all()

        assert result["overall_status"] == "warning"
        assert result["violations"] == 1

    @patch("core.protocol_fault_tolerance.socket.gethostname")
    @patch.object(ProtocolFaultTolerance, "check_reorder_buffer")
    @patch.object(ProtocolFaultTolerance, "check_connection_migration")
    @patch.object(ProtocolFaultTolerance, "check_encryption_overhead")
    @patch.object(ProtocolFaultTolerance, "check_message_ack_redundancy")
    @patch.object(ProtocolFaultTolerance, "check_quic_connection_reuse")
    def test_one_error(
        self,
        mock_quic,
        mock_ack,
        mock_enc,
        mock_mig,
        mock_reorder,
        mock_host,
    ):
        mock_quic.return_value = {"check": "quic", "status": "error"}
        mock_ack.return_value = {"check": "ack", "status": "ok"}
        mock_enc.return_value = {"check": "enc", "status": "ok"}
        mock_mig.return_value = {"check": "mig", "status": "ok"}
        mock_reorder.return_value = {"check": "reorder", "status": "ok"}
        mock_host.return_value = "testhost"

        result = self.checker.run_all()

        assert result["overall_status"] == "error"
        assert result["violations"] == 1

    @patch("core.protocol_fault_tolerance.socket.gethostname")
    @patch.object(ProtocolFaultTolerance, "check_reorder_buffer")
    @patch.object(ProtocolFaultTolerance, "check_connection_migration")
    @patch.object(ProtocolFaultTolerance, "check_encryption_overhead")
    @patch.object(ProtocolFaultTolerance, "check_message_ack_redundancy")
    @patch.object(ProtocolFaultTolerance, "check_quic_connection_reuse")
    def test_check_exception_handling(
        self,
        mock_quic,
        mock_ack,
        mock_enc,
        mock_mig,
        mock_reorder,
        mock_host,
    ):
        mock_quic.side_effect = Exception("Test error")
        mock_ack.return_value = {"check": "ack", "status": "ok"}
        mock_enc.return_value = {"check": "enc", "status": "ok"}
        mock_mig.return_value = {"check": "mig", "status": "ok"}
        mock_reorder.return_value = {"check": "reorder", "status": "ok"}
        mock_host.return_value = "testhost"

        result = self.checker.run_all()

        assert result["overall_status"] == "error"


if __name__ == "__main__":
    unittest.main()
