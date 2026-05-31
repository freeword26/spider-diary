import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import psutil
import pytest

from core.performance_diagnosis import PerformanceDiagnosis
from core.redundancy_metrics import RedundancyMetrics
from core.performance_diagnosis import HOTSPOT_CPU_THRESHOLD


class TestPerformanceDiagnosis(unittest.TestCase):
    """Tests for PerformanceDiagnosis with mocked psutil/subprocess."""

    def setUp(self):
        self.tmpdir = pathlib.Path(tempfile.mkdtemp())
        self.diag = PerformanceDiagnosis(project_root=self.tmpdir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_ok(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(100))
        proc = MagicMock()
        proc.info = {"pid": 1, "name": "test", "cpu_percent": 10.0, "memory_percent": 2.0}
        mock_iter.return_value = [proc]
        result = self.diag.check_cpu_hotspots()
        assert result["status"] == "ok"
        assert result["hotspot_count"] == 0
        assert result["total_processes"] == 100

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_warning(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(200))
        hot_procs = []
        for i in range(3):
            p = MagicMock()
            p.info = {"pid": i, "name": f"hot_{i}", "cpu_percent": 75.0, "memory_percent": 5.0}
            hot_procs.append(p)
        normal = MagicMock()
        normal.info = {"pid": 99, "name": "idle", "cpu_percent": 5.0, "memory_percent": 1.0}
        hot_procs.append(normal)
        mock_iter.return_value = hot_procs
        result = self.diag.check_cpu_hotspots()
        assert result["status"] == "warning"
        assert result["hotspot_count"] == 3

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_critical(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(300))
        procs = []
        for i in range(7):
            p = MagicMock()
            p.info = {"pid": i, "name": f"hot_{i}", "cpu_percent": 80.0, "memory_percent": 3.0}
            procs.append(p)
        mock_iter.return_value = procs
        result = self.diag.check_cpu_hotspots()
        assert result["status"] == "critical"
        assert result["hotspot_count"] == 7

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_sorted_by_cpu(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(50))
        procs = []
        for cpu_val, name in [(55.0, "low"), (90.0, "high"), (70.0, "mid")]:
            p = MagicMock()
            p.info = {"pid": len(procs), "name": name, "cpu_percent": cpu_val, "memory_percent": 1.0}
            procs.append(p)
        mock_iter.return_value = procs
        result = self.diag.check_cpu_hotspots()
        assert result["hot_processes"][0]["name"] == "high"
        assert result["hot_processes"][1]["name"] == "mid"
        assert result["hot_processes"][2]["name"] == "low"

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_skips_nosuchprocess(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(10))
        good = MagicMock()
        good.info = {"pid": 1, "name": "good", "cpu_percent": 60.0, "memory_percent": 1.0}

        class BadProc:
            def __init__(self):
                pass
            @property
            def info(self):
                raise psutil.NoSuchProcess(99)
        mock_iter.return_value = [good, BadProc()]
        result = self.diag.check_cpu_hotspots()
        assert result["hotspot_count"] == 1

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_skips_access_denied(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(10))
        good = MagicMock()
        good.info = {"pid": 1, "name": "good", "cpu_percent": 60.0, "memory_percent": 1.0}

        class BadProc:
            @property
            def info(self):
                raise psutil.AccessDenied(99)
        mock_iter.return_value = [good, BadProc()]
        result = self.diag.check_cpu_hotspots()
        assert result["hotspot_count"] == 1

    @patch("core.performance_diagnosis.psutil.process_iter")
    @patch("core.performance_diagnosis.psutil.pids")
    def test_check_cpu_hotspots_skips_zombie(self, mock_pids, mock_iter):
        mock_pids.return_value = list(range(10))
        good = MagicMock()
        good.info = {"pid": 1, "name": "good", "cpu_percent": 60.0, "memory_percent": 1.0}

        class BadProc:
            @property
            def info(self):
                raise psutil.ZombieProcess(99)
        mock_iter.return_value = [good, BadProc()]
        result = self.diag.check_cpu_hotspots()
        assert result["hotspot_count"] == 1

    @patch("core.performance_diagnosis.psutil.disk_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_io_bottleneck_ok(self, mock_sleep, mock_io):
        mock_io.side_effect = [
            MagicMock(read_bytes=0, write_bytes=0, read_count=0, write_count=0, read_time=0, write_time=0),
            MagicMock(read_bytes=10 * 1024 * 1024, write_bytes=5 * 1024 * 1024, read_count=10, write_count=5, read_time=100, write_time=50),
        ]
        result = self.diag.check_io_bottleneck()
        assert result["read_mb"] == 10.0
        assert result["write_mb"] == 5.0
        assert result["total_mb"] == 15.0
        assert result["status"] == "ok"

    @patch("core.performance_diagnosis.psutil.disk_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_io_bottleneck_warning(self, mock_sleep, mock_io):
        mock_io.side_effect = [
            MagicMock(read_bytes=0, write_bytes=0, read_count=0, write_count=0, read_time=0, write_time=0),
            MagicMock(read_bytes=80 * 1024 * 1024, write_bytes=30 * 1024 * 1024, read_count=100, write_count=50, read_time=500, write_time=300),
        ]
        result = self.diag.check_io_bottleneck()
        assert result["status"] == "warning"

    @patch("core.performance_diagnosis.psutil.disk_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_io_bottleneck_iostat(self, mock_sleep, mock_io):
        mock_io.side_effect = [
            MagicMock(read_bytes=0, write_bytes=0, read_count=0, write_count=0, read_time=0, write_time=0),
            MagicMock(read_bytes=5 * 1024 * 1024, write_bytes=3 * 1024 * 1024, read_count=50, write_count=30, read_time=200, write_time=100),
        ]
        result = self.diag.check_io_bottleneck()
        assert "iostat" in result
        assert result["iostat"]["read_count_delta"] == 50

    @patch("core.performance_diagnosis.psutil.net_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_network_bandwidth_ok(self, mock_sleep, mock_net):
        mock_net.side_effect = [
            MagicMock(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0, errin=0, errout=0, dropin=0, dropout=0),
            MagicMock(bytes_sent=10 * 1024 * 1024, bytes_recv=5 * 1024 * 1024, packets_sent=100, packets_recv=80, errin=0, errout=0, dropin=0, dropout=0),
        ]
        result = self.diag.check_network_bandwidth()
        assert result["status"] == "ok"
        assert result["sent_mbps"] == pytest.approx(80.0, rel=0.1)
        assert result["recv_mbps"] == pytest.approx(40.0, rel=0.1)

    @patch("core.performance_diagnosis.psutil.net_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_network_bandwidth_with_errors(self, mock_sleep, mock_net):
        mock_net.side_effect = [
            MagicMock(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0, errin=0, errout=0, dropin=0, dropout=0),
            MagicMock(bytes_sent=5 * 1024 * 1024, bytes_recv=2 * 1024 * 1024, packets_sent=50, packets_recv=40, errin=2, errout=1, dropin=3, dropout=0),
        ]
        result = self.diag.check_network_bandwidth()
        assert result["status"] == "warning"
        assert result["errors_in"] == 2
        assert result["drops_in"] == 3

    @patch("core.performance_diagnosis.psutil.net_io_counters")
    @patch("core.performance_diagnosis.time.sleep")
    def test_check_network_bandwidth_throughput(self, mock_sleep, mock_net):
        mock_net.side_effect = [
            MagicMock(bytes_sent=0, bytes_recv=0, packets_sent=0, packets_recv=0, errin=0, errout=0, dropin=0, dropout=0),
            MagicMock(bytes_sent=50 * 1024 * 1024, bytes_recv=30 * 1024 * 1024, packets_sent=500, packets_recv=300, errin=0, errout=0, dropin=0, dropout=0),
        ]
        result = self.diag.check_network_bandwidth()
        expected_sent = round(50 * 1024 * 1024 * 8 / (1024 * 1024), 2)
        expected_recv = round(30 * 1024 * 1024 * 8 / (1024 * 1024), 2)
        expected_total = round(expected_sent + expected_recv, 2)
        assert result["sent_mbps"] == expected_sent
        assert result["recv_mbps"] == expected_recv
        assert result["total_mbps"] == expected_total
        assert result["packets_sent"] == 500
        assert result["packets_recv"] == 300

    @patch("core.performance_diagnosis.time.monotonic")
    @patch("core.performance_diagnosis.psutil.disk_usage")
    @patch("core.performance_diagnosis.psutil.virtual_memory")
    @patch("core.performance_diagnosis.psutil.cpu_percent")
    def test_check_resource_trend_short(self, mock_cpu, mock_mem, mock_disk, mock_mono):
        mock_mono.side_effect = [0, 0, 5, 10]
        mock_cpu.return_value = 30.0
        mock_mem.return_value = MagicMock(percent=50.0)
        mock_disk.return_value = MagicMock(percent=40.0)
        result = self.diag.check_resource_trend(duration_sec=5)
        assert result["duration"] == 5
        assert result["status"] == "ok"
        assert result["sample_count"] >= 1
        assert result["cpu"]["avg"] == pytest.approx(30.0, abs=5.0)
        assert result["mem"]["avg"] == pytest.approx(50.0, abs=5.0)

    @patch("core.performance_diagnosis.time.monotonic")
    @patch("core.performance_diagnosis.psutil.disk_usage")
    @patch("core.performance_diagnosis.psutil.virtual_memory")
    @patch("core.performance_diagnosis.psutil.cpu_percent")
    def test_check_resource_trend_critical(self, mock_cpu, mock_mem, mock_disk, mock_mono):
        mock_mono.side_effect = [0, 0, 5, 10]
        mock_cpu.return_value = 95.0
        mock_mem.return_value = MagicMock(percent=93.0)
        mock_disk.return_value = MagicMock(percent=50.0)
        result = self.diag.check_resource_trend(duration_sec=5)
        assert result["status"] == "critical"

    @patch("core.performance_diagnosis.time.monotonic")
    @patch("core.performance_diagnosis.psutil.disk_usage")
    @patch("core.performance_diagnosis.psutil.virtual_memory")
    @patch("core.performance_diagnosis.psutil.cpu_percent")
    def test_check_resource_trend_samples_collected(self, mock_cpu, mock_mem, mock_disk, mock_mono):
        mock_mono.side_effect = [0, 0, 5, 10]
        mock_cpu.return_value = 25.0
        mock_mem.return_value = MagicMock(percent=45.0)
        mock_disk.return_value = MagicMock(percent=60.0)
        result = self.diag.check_resource_trend(duration_sec=5)
        assert len(result["samples"]) >= 1
        sample = result["samples"][0]
        assert "cpu" in sample
        assert "mem" in sample
        assert "disk" in sample
        assert "ts" in sample

    @patch.object(PerformanceDiagnosis, "check_resource_trend", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_container_performance", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_network_bandwidth", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_io_bottleneck", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_cpu_hotspots", return_value={"status": "ok"})
    def test_run_full_diagnosis_ok(self, mock_cpu, mock_io, mock_net, mock_container, mock_trend):
        result = self.diag.run_full_diagnosis()
        assert result["overall_status"] == "ok"
        assert "cpu_hotspots" in result
        assert "io_bottleneck" in result
        assert "network_bandwidth" in result
        assert "container_performance" in result
        assert "resource_trend" in result

    @patch.object(PerformanceDiagnosis, "check_resource_trend", return_value={"status": "critical"})
    @patch.object(PerformanceDiagnosis, "check_container_performance", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_network_bandwidth", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_io_bottleneck", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_cpu_hotspots", return_value={"status": "ok"})
    def test_run_full_diagnosis_critical(self, mock_cpu, mock_io, mock_net, mock_container, mock_trend):
        result = self.diag.run_full_diagnosis()
        assert result["overall_status"] == "critical"

    @patch.object(PerformanceDiagnosis, "check_resource_trend", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_container_performance", return_value={"status": "warning"})
    @patch.object(PerformanceDiagnosis, "check_network_bandwidth", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_io_bottleneck", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_cpu_hotspots", return_value={"status": "ok"})
    def test_run_full_diagnosis_warning(self, mock_cpu, mock_io, mock_net, mock_container, mock_trend):
        result = self.diag.run_full_diagnosis()
        assert result["overall_status"] == "warning"

    @patch.object(PerformanceDiagnosis, "check_resource_trend", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_container_performance", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_network_bandwidth", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_io_bottleneck", return_value={"status": "ok"})
    @patch.object(PerformanceDiagnosis, "check_cpu_hotspots", return_value={
        "hotspot_count": 2, "hostname": "h", "timestamp": "t",
        "threshold": 50, "total_processes": 100, "hot_processes": [], "status": "ok",
    })
    def test_run_full_diagnosis_hostname(self, mock_cpu, mock_io, mock_net, mock_container, mock_trend):
        result = self.diag.run_full_diagnosis()
        assert "hostname" in result
        assert isinstance(result["hostname"], str)

    def test_run_full_diagnosis_has_timestamp(self):
        with patch.object(PerformanceDiagnosis, "check_resource_trend", return_value={"status": "ok"}), \
             patch.object(PerformanceDiagnosis, "check_container_performance", return_value={"status": "ok", "docker_available": False, "container_count": 0, "containers": [], "heavy_containers": []}), \
             patch.object(PerformanceDiagnosis, "check_network_bandwidth", return_value={"status": "ok", "sent_mbps": 0, "recv_mbps": 0, "total_mbps": 0, "packets_sent": 0, "packets_recv": 0, "errors_in": 0, "errors_out": 0, "drops_in": 0, "drops_out": 0}), \
             patch.object(PerformanceDiagnosis, "check_io_bottleneck", return_value={"status": "ok", "read_mb": 0, "write_mb": 0, "total_mb": 0, "iostat": {}}), \
             patch.object(PerformanceDiagnosis, "check_cpu_hotspots", return_value={"status": "ok", "hotspot_count": 0, "hostname": "h", "timestamp": "t", "threshold": 50, "total_processes": 0, "hot_processes": []}):
            result = self.diag.run_full_diagnosis()
            assert "timestamp" in result


class TestPerformanceDiagnosisInit(unittest.TestCase):

    def test_default_project_root(self):
        diag = PerformanceDiagnosis()
        assert diag.project_root == pathlib.Path.cwd()

    def test_custom_project_root(self):
        p = pathlib.Path(tempfile.mkdtemp())
        diag = PerformanceDiagnosis(project_root=p)
        assert diag.project_root == p
        assert isinstance(diag.hostname, str)


class TestPerformanceDiagnosisContainer(unittest.TestCase):
    """Container performance checks."""

    def setUp(self):
        self.tmpdir = pathlib.Path(tempfile.mkdtemp())
        self.diag = PerformanceDiagnosis(project_root=self.tmpdir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_docker_ok(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="web\t15.5%\t128MiB / 512MiB\t1MB / 500KB\t2MB / 1MB\n",
        )
        result = self.diag.check_container_performance()
        assert result["docker_available"] is True
        assert result["container_count"] == 1
        assert result["containers"][0]["name"] == "web"
        assert result["containers"][0]["cpu_percent"] == 15.5
        assert result["status"] == "ok"

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_heavy(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="heavy\t85.0%\t400MiB / 512MiB\t5MB / 2MB\t10MB / 5MB\n",
        )
        result = self.diag.check_container_performance()
        assert result["status"] == "warning"
        assert len(result["heavy_containers"]) == 1
        assert result["heavy_containers"][0]["name"] == "heavy"

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_docker_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.diag.check_container_performance()
        assert result["docker_available"] is False
        assert result["container_count"] == 0
        assert result["status"] == "ok"

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="docker stats", timeout=30)
        result = self.diag.check_container_performance()
        assert result["docker_available"] is True
        assert result["container_count"] == 0

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_nonzero_rc(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = self.diag.check_container_performance()
        assert result["docker_available"] is False
        assert result["container_count"] == 0

    @patch("core.performance_diagnosis.subprocess.run")
    def test_check_container_performance_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.diag.check_container_performance()
        assert result["docker_available"] is False
        assert result["container_count"] == 0


class TestRedundancyMetrics(unittest.TestCase):
    """Tests for RedundancyMetrics with mocked filesystem and subprocess."""

    def setUp(self):
        self.tmpdir = pathlib.Path(tempfile.mkdtemp())
        self.metrics = RedundancyMetrics(project_root=self.tmpdir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def test_check_duplicate_health_checks_no_layers(self):
        result = self.metrics.check_duplicate_health_checks()
        assert result["status"] == "ok"
        assert result["detected_layers"] == []
        assert result["duplicates"] == []

    def test_check_duplicate_health_checks_docker_only(self):
        compose = self.tmpdir / "docker-compose.yml"
        compose.write_text("services:\n  web:\n    healthcheck:\n      test: curl")
        result = self.metrics.check_duplicate_health_checks()
        assert "container" in result["detected_layers"]
        assert result["status"] == "ok"

    def test_check_duplicate_health_checks_container_and_app(self):
        compose = self.tmpdir / "docker-compose.yml"
        compose.write_text("services:\n  web:\n    healthcheck:\n      test: curl")
        healthz = self.tmpdir / "healthz.py"
        healthz.write_text("def check(): pass")
        result = self.metrics.check_duplicate_health_checks()
        assert "container" in result["detected_layers"]
        assert "app" in result["detected_layers"]
        assert result["status"] == "warning"
        assert len(result["duplicates"]) >= 1

    def test_check_duplicate_health_checks_mesh_detected(self):
        vs = self.tmpdir / "VirtualService.yaml"
        vs.write_text("apiVersion: networking.istio.io/v1alpha3")
        result = self.metrics.check_duplicate_health_checks()
        assert "mesh" in result["detected_layers"]

    def test_check_double_encryption_clean(self):
        result = self.metrics.check_double_encryption()
        assert result["status"] == "ok"
        assert result["tls_detected"] is False
        assert result["app_encrypt_detected"] is False

    def test_check_double_encryption_tls_only(self):
        compose = self.tmpdir / "docker-compose.yml"
        compose.write_text("ports:\n  - 443:443\nssl: true")
        result = self.metrics.check_double_encryption()
        assert result["tls_detected"] is True
        assert result["status"] == "ok"

    def test_check_double_encryption_both(self):
        compose = self.tmpdir / "docker-compose.yml"
        compose.write_text("ports:\n  - 443:443")
        crypto = self.tmpdir / "encrypt.py"
        crypto.write_text("from cryptography.fernet import Fernet")
        result = self.metrics.check_double_encryption()
        assert result["tls_detected"] is True
        assert result["app_encrypt_detected"] is True
        assert result["status"] == "warning"
        assert len(result["double_encrypt_paths"]) >= 1

    def test_check_double_encryption_tls_in_nginx_conf(self):
        conf_dir = self.tmpdir / "nginx"
        conf_dir.mkdir()
        conf = conf_dir / "nginx.conf"
        conf.write_text("ssl_certificate /etc/ssl/cert.pem;\nlisten 443;")
        result = self.metrics.check_double_encryption()
        assert result["tls_detected"] is True

    def test_check_double_encryption_app_crypto_in_code(self):
        crypto = self.tmpdir / "crypto.py"
        crypto.write_text("import AES\ncipher = AES.new(key)")
        result = self.metrics.check_double_encryption()
        assert result["app_encrypt_detected"] is True

    def test_check_multi_layer_timeouts_clean(self):
        result = self.metrics.check_multi_layer_timeouts()
        assert result["status"] == "ok"
        assert result["mismatches"] == []

    def test_check_multi_layer_timeouts_mismatch(self):
        cfg = self.tmpdir / "nginx.conf"
        cfg.write_text("proxy_read_timeout 300;\nproxy_connect_timeout 30;")
        app_cfg = self.tmpdir / "application.yml"
        app_cfg.write_text("timeout: 600\n")
        result = self.metrics.check_multi_layer_timeouts()
        assert result["status"] == "warning"
        assert len(result["mismatches"]) >= 1

    def test_check_multi_layer_timeouts_fields(self):
        cfg = self.tmpdir / "nginx.conf"
        cfg.write_text("proxy_read_timeout 30;")
        result = self.metrics.check_multi_layer_timeouts()
        assert result["status"] == "ok"
        for layer in result["layers_detected"]:
            assert "layer" in layer
            assert "timeout_sec" in layer
            assert "file" in layer

    def test_check_multi_layer_timeouts_service_gt_gateway(self):
        app_cfg = self.tmpdir / "application.yml"
        app_cfg.write_text("timeout: 600\nrequestTimeout: 500")
        result = self.metrics.check_multi_layer_timeouts()
        assert result["status"] == "ok"

    @patch("core.redundancy_metrics.subprocess.run")
    def test_check_image_redundancy_no_docker(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.metrics.check_image_redundancy()
        assert result["status"] == "ok"
        assert result["unique_images"] == 0
        assert result["redundant_groups"] == []

    @patch("core.redundancy_metrics.subprocess.run")
    def test_check_image_redundancy_with_redundancy(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="nginx\tlatest\tabc123\t100MB\nnginx\t1.25\tabc123\t100MB\nnginx\tmainline\tabc123\t100MB\n",
        )
        result = self.metrics.check_image_redundancy()
        assert result["status"] == "warning"
        assert len(result["redundant_groups"]) == 1
        assert result["redundant_groups"][0]["count"] == 3

    @patch("core.redundancy_metrics.subprocess.run")
    def test_check_image_redundancy_critical(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "nginx\tlatest\tabc123\t100MB\nnginx\t1.25\tabc123\t100MB\n"
                "nginx\tmainline\tabc123\t100MB\nredis\t7\tdef456\t50MB\n"
                "redis\t6\tdef456\t50MB\nredis\talpine\tdef456\t50MB\n"
            ),
        )
        result = self.metrics.check_image_redundancy()
        assert result["status"] == "critical"

    @patch("core.redundancy_metrics.subprocess.run")
    def test_check_image_redundancy_timeout(self, mock_run):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="docker images", timeout=30)
        result = self.metrics.check_image_redundancy()
        assert result["status"] == "ok"

    def test_check_monitoring_overlap_clean(self):
        result = self.metrics.check_monitoring_overlap()
        assert result["status"] == "ok"
        assert result["tools_detected"] == []

    def test_check_monitoring_overlap_prometheus(self):
        prom = self.tmpdir / "prometheus.yml"
        prom.write_text("scrape_configs:\n  - job_name: test")
        result = self.metrics.check_monitoring_overlap()
        assert "prometheus" in result["tools_detected"]
        assert result["status"] == "ok"

    def test_check_monitoring_overlap_prometheus_datadog(self):
        prom = self.tmpdir / "prometheus.yml"
        prom.write_text("scrape_configs:\n  - job_name: test")
        dd = self.tmpdir / "datadog.yaml"
        dd.write_text("api_key: test123")
        result = self.metrics.check_monitoring_overlap()
        assert "prometheus" in result["tools_detected"]
        assert "datadog" in result["tools_detected"]
        assert result["status"] == "warning"
        assert len(result["overlaps"]) >= 1

    def test_check_monitoring_overlap_custom_overlap(self):
        prom = self.tmpdir / "prometheus.yml"
        prom.write_text("scrape_configs:")
        mon = self.tmpdir / "monitor.py"
        mon.write_text("import time\ndef check(): pass")
        result = self.metrics.check_monitoring_overlap()
        assert "prometheus" in result["tools_detected"]
        assert "custom" in result["tools_detected"]
        has_custom_overlap = any("custom" in o["tools"] for o in result["overlaps"])
        assert has_custom_overlap

    def test_check_monitoring_overlap_elastic(self):
        mb = self.tmpdir / "metricbeat.yml"
        mb.write_text("metricbeat.modules:\n  - module: system")
        result = self.metrics.check_monitoring_overlap()
        assert "elastic" in result["tools_detected"]

    def test_check_monitoring_overlap_grafana_only(self):
        gdash = self.tmpdir / "grafana" / "dashboards"
        gdash.mkdir(parents=True)
        gf = gdash / "overview.json"
        gf.write_text("{}")
        result = self.metrics.check_monitoring_overlap()
        assert "grafana" in result["tools_detected"]
        assert result["status"] == "ok"

    def test_get_redundancy_score_initially_high(self):
        score = self.metrics.get_redundancy_score()
        assert score == 100.0

    def test_get_redundancy_score_returns_float(self):
        score = self.metrics.get_redundancy_score()
        assert isinstance(score, float)
        assert 0.0 <= score <= 100.0

    def test_run_all_returns_all_checks(self):
        result = self.metrics.run_all()
        assert "redundancy_score" in result
        assert "overall_status" in result
        assert "duplicate_health_checks" in result
        assert "double_encryption" in result
        assert "multi_layer_timeouts" in result
        assert "image_redundancy" in result
        assert "monitoring_overlap" in result
        assert "timestamp" in result

    def test_run_all_score_in_valid_range(self):
        result = self.metrics.run_all()
        assert isinstance(result["redundancy_score"], float)
        assert 0.0 <= result["redundancy_score"] <= 100.0

    def test_run_all_overall_status_ok(self):
        result = self.metrics.run_all()
        assert result["overall_status"] == "ok"


class TestRedundancyMetricsInit(unittest.TestCase):

    def test_default_project_root(self):
        metrics = RedundancyMetrics()
        assert metrics.project_root == pathlib.Path.cwd()

    def test_custom_project_root(self):
        p = pathlib.Path(tempfile.mkdtemp())
        metrics = RedundancyMetrics(project_root=p)
        assert metrics.project_root == p


if __name__ == "__main__":
    unittest.main()
