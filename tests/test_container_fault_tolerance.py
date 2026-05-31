"""Unit tests for ContainerFaultTolerance."""

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

from core.container_fault_tolerance import ContainerFaultTolerance


class TestContainerFaultToleranceInit(unittest.TestCase):
    """Tests for ContainerFaultTolerance initialization."""

    def test_default_config(self):
        cft = ContainerFaultTolerance()
        assert cft.config["health_check_interval_threshold_sec"] == 5
        assert cft.config["restart_storm_threshold_per_min"] == 3
        assert cft.config["rolling_update_max_surge_pct"] == 25
        assert cft.config["resource_over_iso_cpu_limit_pct"] == 120
        assert cft.config["resource_over_iso_usage_threshold_pct"] == 30
        assert cft.config["container_startup_threshold_sec"] == 15

    def test_custom_config(self):
        cft = ContainerFaultTolerance(config={"restart_storm_threshold_per_min": 5})
        assert cft.config["restart_storm_threshold_per_min"] == 5
        assert cft.config["health_check_interval_threshold_sec"] == 5


class TestCheckHealthCheckFrequency(unittest.TestCase):
    """Tests for check_health_check_frequency."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_no_containers(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "ok"
        assert result["containers_checked"] == 0
        assert result["flagged"] == []

    @patch("subprocess.run")
    def test_docker_ps_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "unavailable"

    @patch("subprocess.run")
    def test_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "docker_unavailable"

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=15)
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "timeout"

    @patch("subprocess.run")
    def test_healthy_containers(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="abc123\tweb\n"),
            MagicMock(returncode=0, stdout="map[Interval:10000000000]"),
            MagicMock(returncode=0, stdout=json.dumps([{
                "Config": {"Healthcheck": {"Interval": 10_000_000_000}}
            }])),
        ]
        result = self.cft.check_health_check_frequency()
        assert result["containers_checked"] == 1
        assert result["status"] == "ok"

    @patch("subprocess.run")
    def test_over_consuming_health_check(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="abc123\tweb\n"),
            MagicMock(returncode=0, stdout="map[Interval:2000000000]"),
            MagicMock(returncode=0, stdout=json.dumps([{
                "Config": {"Healthcheck": {"Interval": 2_000_000_000}}
            }])),
        ]
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1
        assert result["flagged"][0]["name"] == "web"
        assert result["flagged"][0]["health_check_interval_sec"] == 2.0
        assert result["flagged"][0]["flagged"] is True

    @patch("subprocess.run")
    def test_no_health_check_configured(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="abc123\tworker\n"),
            MagicMock(returncode=0, stdout="<nil>"),
        ]
        result = self.cft.check_health_check_frequency()
        assert result["status"] == "ok"
        assert result["containers_checked"] == 1
        assert result["flagged"] == []

    @patch("subprocess.run")
    def test_multiple_containers_mixed(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\nc2\tapi\n"),
            MagicMock(returncode=0, stdout="map[Interval:10000000000]"),
            MagicMock(returncode=0, stdout=json.dumps([{
                "Config": {"Healthcheck": {"Interval": 10_000_000_000}}
            }])),
            MagicMock(returncode=0, stdout="map[Interval:3000000000]"),
            MagicMock(returncode=0, stdout=json.dumps([{
                "Config": {"Healthcheck": {"Interval": 3_000_000_000}}
            }])),
        ]
        result = self.cft.check_health_check_frequency()
        assert result["containers_checked"] == 2
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1


class TestCheckRestartStorm(unittest.TestCase):
    """Tests for check_restart_storm."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_no_containers(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.cft.check_restart_storm()
        assert result["status"] == "ok"
        assert result["containers_checked"] == 0

    @patch("subprocess.run")
    def test_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.cft.check_restart_storm()
        assert result["status"] == "docker_unavailable"

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=15)
        result = self.cft.check_restart_storm()
        assert result["status"] == "timeout"

    @patch("subprocess.run")
    def test_stable_container(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\tUp 2 hours\n"),
            MagicMock(returncode=0, stdout="2026-01-01T00:00:00Z"),
        ]
        result = self.cft.check_restart_storm()
        assert result["status"] == "ok"
        assert result["flagged"] == []

    @patch("subprocess.run")
    def test_restart_storm_detected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\tRestarting (15)"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z"),
        ]
        result = self.cft.check_restart_storm()
        assert result["containers_checked"] == 1

    @patch("subprocess.run")
    def test_restart_count_at_threshold(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\tRestarting (60)"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z"),
        ]
        result = self.cft.check_restart_storm()
        assert result["containers_checked"] == 1


class TestCheckRollingUpdateParallelism(unittest.TestCase):
    """Tests for check_rolling_update_parallelism."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("pathlib.Path.exists")
    def test_no_deployment_files(self, mock_exists):
        mock_exists.return_value = False
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "ok"
        assert result["deployments_checked"] == 0

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_normal_max_surge(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "maxSurge: 20%"
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "ok"
        assert len(result["flagged"]) == 0

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_excessive_max_surge(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "maxSurge: 50%"
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "warning"
        assert result["deployments_checked"] >= 1
        assert len(result["flagged"]) >= 1
        flagged_files = [f["file"] for f in result["flagged"]]
        assert any("compose.yml" in f or "deployment" in f for f in flagged_files)

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_at_threshold(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "maxSurge: 25%"
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "ok"
        assert len(result["flagged"]) == 0

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_file_read_error(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.side_effect = OSError("permission denied")
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "ok"
        assert result["deployments_checked"] == 0

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_no_maxsurge_in_file(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = "replicas: 3\nimage: nginx:latest"
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "ok"
        assert result["deployments_checked"] == 0

    @patch("pathlib.Path.read_text")
    @patch("pathlib.Path.exists")
    def test_equals_format(self, mock_exists, mock_read):
        mock_exists.return_value = True
        mock_read.return_value = 'maxSurge=30%'
        result = self.cft.check_rolling_update_parallelism()
        assert result["status"] == "warning"


class TestCheckResourceOverIsolation(unittest.TestCase):
    """Tests for check_resource_over_isolation."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_no_containers(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "ok"
        assert result["containers_checked"] == 0

    @patch("subprocess.run")
    def test_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "docker_unavailable"

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=15)
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "timeout"

    @patch("subprocess.run")
    def test_over_limit_high_usage_not_flagged(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\t15.0%\t100MiB / 512MiB\n"),
            MagicMock(returncode=0, stdout="2000000000"),
        ]
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1

    @patch("subprocess.run")
    def test_over_isolated_container(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\t10.0%\t100MiB / 512MiB\n"),
            MagicMock(returncode=0, stdout="1500000000"),
        ]
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1
        assert result["flagged"][0]["cpu_limit_pct"] == 150.0
        assert result["flagged"][0]["cpu_usage_pct"] == 10.0

    @patch("subprocess.run")
    def test_high_usage_not_flagged(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\t80.0%\t400MiB / 512MiB\n"),
            MagicMock(returncode=0, stdout="1500000000"),
        ]
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "ok"
        assert len(result["flagged"]) == 0

    @patch("subprocess.run")
    def test_no_cpu_limit_not_flagged(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\t10.0%\t100MiB / 512MiB\n"),
            MagicMock(returncode=0, stdout="0"),
        ]
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "ok"

    @patch("subprocess.run")
    def test_docker_stats_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = self.cft.check_resource_over_isolation()
        assert result["status"] == "unavailable"


class TestCheckContainerStartupTime(unittest.TestCase):
    """Tests for check_container_startup_time."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_no_containers(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = self.cft.check_container_startup_time()
        assert result["status"] == "ok"
        assert result["containers_checked"] == 0

    @patch("subprocess.run")
    def test_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.cft.check_container_startup_time()
        assert result["status"] == "docker_unavailable"

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=15)
        result = self.cft.check_container_startup_time()
        assert result["status"] == "timeout"

    @patch("subprocess.run")
    def test_fast_startup(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\n"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z\t2026-01-01T12:00:03Z"),
        ]
        result = self.cft.check_container_startup_time()
        assert result["status"] == "ok"
        assert len(result["flagged"]) == 0

    @patch("subprocess.run")
    def test_slow_startup(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\n"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z\t2026-01-01T12:00:30Z"),
        ]
        result = self.cft.check_container_startup_time()
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1
        assert result["flagged"][0]["startup_time_sec"] == 30.0

    @patch("subprocess.run")
    def test_startup_exactly_at_threshold(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\n"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z\t2026-01-01T12:00:14Z"),
        ]
        result = self.cft.check_container_startup_time()
        assert result["status"] == "ok"

    @patch("subprocess.run")
    def test_multiple_containers_mixed(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="c1\tweb\nc2\tapi\n"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z\t2026-01-01T12:00:03Z"),
            MagicMock(returncode=0, stdout="2026-01-01T12:00:00Z\t2026-01-01T12:01:00Z"),
        ]
        result = self.cft.check_container_startup_time()
        assert result["containers_checked"] == 2
        assert result["status"] == "warning"
        assert len(result["flagged"]) == 1


class TestCheckDockerDiskUsage(unittest.TestCase):
    """Tests for check_docker_disk_usage."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_normal_usage(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TYPE            TOTAL    ACTIVE     SIZE   RECLAIMABLE\n"
                "Images          5        3          2.5GB   1.0GB (40%)\n"
                "Containers      20       10         500MB   200MB (50%)\n"
                "Local Volumes   10       5          1.0GB   300MB (30%)\n"
            ),
        )
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "ok"
        assert result["warnings"] == []

    @patch("subprocess.run")
    def test_high_image_usage_warning(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TYPE            TOTAL    ACTIVE     SIZE   RECLAIMABLE\n"
                "Images          5        3          2.5GB   1.0GB (85%)\n"
                "Containers      20       10         500MB   200MB (50%)\n"
            ),
        )
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "warning"
        assert len(result["warnings"]) == 1
        assert result["warnings"][0]["severity"] == "warning"
        assert result["warnings"][0]["category"] == "Images"

    @patch("subprocess.run")
    def test_critical_image_usage(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TYPE            TOTAL    ACTIVE     SIZE   RECLAIMABLE\n"
                "Images          5        3          2.5GB   1.0GB (95%)\n"
            ),
        )
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "warning"
        assert result["warnings"][0]["severity"] == "critical"

    @patch("subprocess.run")
    def test_multiple_warnings(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TYPE            TOTAL    ACTIVE     SIZE   RECLAIMABLE\n"
                "Images          5        3          2.5GB   1.0GB (85%)\n"
                "Containers      20       10         500MB   200MB (90%)\n"
                "Local Volumes   10       5          1.0GB   300MB (30%)\n"
            ),
        )
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "warning"
        assert len(result["warnings"]) == 2

    @patch("subprocess.run")
    def test_docker_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "docker_unavailable"

    @patch("subprocess.run")
    def test_docker_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=15)
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "timeout"

    @patch("subprocess.run")
    def test_docker_system_df_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = self.cft.check_docker_disk_usage()
        assert result["status"] == "unavailable"

    @patch("subprocess.run")
    def test_disk_usage_parsed(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TYPE            TOTAL    ACTIVE     SIZE   RECLAIMABLE\n"
                "Images          5        3          2.5GB   1.0GB (40%)\n"
            ),
        )
        result = self.cft.check_docker_disk_usage()
        assert "Images" in result["disk_usage"]
        assert result["disk_usage"]["Images"]["total"] == "5"


class TestRunAll(unittest.TestCase):
    """Tests for run_all method."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch.object(ContainerFaultTolerance, "check_docker_disk_usage")
    @patch.object(ContainerFaultTolerance, "check_container_startup_time")
    @patch.object(ContainerFaultTolerance, "check_resource_over_isolation")
    @patch.object(ContainerFaultTolerance, "check_rolling_update_parallelism")
    @patch.object(ContainerFaultTolerance, "check_restart_storm")
    @patch.object(ContainerFaultTolerance, "check_health_check_frequency")
    def test_all_ok(
        self,
        mock_health,
        mock_restart,
        mock_rolling,
        mock_resource,
        mock_startup,
        mock_disk,
    ):
        mock_health.return_value = {"status": "ok"}
        mock_restart.return_value = {"status": "ok"}
        mock_rolling.return_value = {"status": "ok"}
        mock_resource.return_value = {"status": "ok"}
        mock_startup.return_value = {"status": "ok"}
        mock_disk.return_value = {"status": "ok"}

        result = self.cft.run_all()

        assert result["overall_status"] == "ok"
        assert result["health_check_frequency"]["status"] == "ok"
        assert result["restart_storm"]["status"] == "ok"
        assert result["rolling_update_parallelism"]["status"] == "ok"
        assert result["resource_over_isolation"]["status"] == "ok"
        assert result["container_startup_time"]["status"] == "ok"
        assert result["docker_disk_usage"]["status"] == "ok"
        assert "timestamp" in result

    @patch.object(ContainerFaultTolerance, "check_docker_disk_usage")
    @patch.object(ContainerFaultTolerance, "check_container_startup_time")
    @patch.object(ContainerFaultTolerance, "check_resource_over_isolation")
    @patch.object(ContainerFaultTolerance, "check_rolling_update_parallelism")
    @patch.object(ContainerFaultTolerance, "check_restart_storm")
    @patch.object(ContainerFaultTolerance, "check_health_check_frequency")
    def test_one_warning(
        self,
        mock_health,
        mock_restart,
        mock_rolling,
        mock_resource,
        mock_startup,
        mock_disk,
    ):
        mock_health.return_value = {"status": "ok"}
        mock_restart.return_value = {"status": "warning"}
        mock_rolling.return_value = {"status": "ok"}
        mock_resource.return_value = {"status": "ok"}
        mock_startup.return_value = {"status": "ok"}
        mock_disk.return_value = {"status": "ok"}

        result = self.cft.run_all()
        assert result["overall_status"] == "warning"

    @patch.object(ContainerFaultTolerance, "check_docker_disk_usage")
    @patch.object(ContainerFaultTolerance, "check_container_startup_time")
    @patch.object(ContainerFaultTolerance, "check_resource_over_isolation")
    @patch.object(ContainerFaultTolerance, "check_rolling_update_parallelism")
    @patch.object(ContainerFaultTolerance, "check_restart_storm")
    @patch.object(ContainerFaultTolerance, "check_health_check_frequency")
    def test_all_unavailable(
        self,
        mock_health,
        mock_restart,
        mock_rolling,
        mock_resource,
        mock_startup,
        mock_disk,
    ):
        mock_health.return_value = {"status": "docker_unavailable"}
        mock_restart.return_value = {"status": "docker_unavailable"}
        mock_rolling.return_value = {"status": "ok"}
        mock_resource.return_value = {"status": "docker_unavailable"}
        mock_startup.return_value = {"status": "docker_unavailable"}
        mock_disk.return_value = {"status": "docker_unavailable"}

        result = self.cft.run_all()
        assert result["overall_status"] == "degraded"

    @patch.object(ContainerFaultTolerance, "check_docker_disk_usage")
    @patch.object(ContainerFaultTolerance, "check_container_startup_time")
    @patch.object(ContainerFaultTolerance, "check_resource_over_isolation")
    @patch.object(ContainerFaultTolerance, "check_rolling_update_parallelism")
    @patch.object(ContainerFaultTolerance, "check_restart_storm")
    @patch.object(ContainerFaultTolerance, "check_health_check_frequency")
    def test_run_all_includes_all_checks(
        self,
        mock_health,
        mock_restart,
        mock_rolling,
        mock_resource,
        mock_startup,
        mock_disk,
    ):
        mock_health.return_value = {"status": "ok"}
        mock_restart.return_value = {"status": "ok"}
        mock_rolling.return_value = {"status": "ok"}
        mock_resource.return_value = {"status": "ok"}
        mock_startup.return_value = {"status": "ok"}
        mock_disk.return_value = {"status": "ok"}

        result = self.cft.run_all()

        assert "health_check_frequency" in result
        assert "restart_storm" in result
        assert "rolling_update_parallelism" in result
        assert "resource_over_isolation" in result
        assert "container_startup_time" in result
        assert "docker_disk_usage" in result


class TestInspectHealthCheck(unittest.TestCase):
    """Tests for _inspect_health_check helper."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    @patch("subprocess.run")
    def test_container_no_health(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="<nil>")
        result = self.cft._inspect_health_check("abc123", "web", 5)
        assert result["health_check_interval_sec"] is None
        assert result["flagged"] is False
        assert result["issue"] == "No health check configured"

    @patch("subprocess.run")
    def test_exception_handling(self, mock_run):
        mock_run.side_effect = Exception("unexpected error")
        result = self.cft._inspect_health_check("abc123", "web", 5)
        assert result["name"] == "web"
        assert result["flagged"] is False


class TestParseDeploymentConfig(unittest.TestCase):
    """Tests for _parse_deployment_config helper."""

    def setUp(self):
        self.cft = ContainerFaultTolerance()

    def test_maxsurge_with_colon(self):
        result = self.cft._parse_deployment_config("compose.yml", "maxSurge: 30%", 25)
        assert result is not None
        assert result["max_surge_pct"] == 30
        assert result["flagged"] is True

    def test_maxsurge_without_percent(self):
        result = self.cft._parse_deployment_config("compose.yml", "maxSurge: 10", 25)
        assert result is None

    def test_normal_maxsurge(self):
        result = self.cft._parse_deployment_config("compose.yml", "maxSurge: 20%", 25)
        assert result is not None
        assert result["flagged"] is False


if __name__ == "__main__":
    unittest.main()
