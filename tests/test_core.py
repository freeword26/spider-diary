import datetime
import json
import os
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from spider_diary.core.system_checker import SystemChecker
from spider_diary.core.project_reader import ProjectReader
from spider_diary.report.report_generator import ReportGenerator
from spider_diary.remind.blocker_store import BlockerStore
from spider_diary.engine import DiaryEngine


class TestSystemChecker(unittest.TestCase):
    """Tests for SystemChecker with mocked psutil."""

    def setUp(self):
        self.checker = SystemChecker()

    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_check_disk_ok(self, mock_usage):
        mock_usage.return_value = MagicMock(
            total=100 * (1024 ** 3),
            used=50 * (1024 ** 3),
            free=50 * (1024 ** 3),
        )
        result = self.checker.check_disk("/test")
        assert result["status"] == "ok"
        assert result["percent"] == 50.0
        assert result["total_gb"] == pytest.approx(100.0, rel=1e-2)
        assert result["path"] == "/test"

    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_check_disk_warning(self, mock_usage):
        mock_usage.return_value = MagicMock(
            total=100 * (1024 ** 3),
            used=85 * (1024 ** 3),
            free=15 * (1024 ** 3),
        )
        result = self.checker.check_disk("/test")
        assert result["status"] == "warning"
        assert result["percent"] == 85.0

    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_check_disk_critical(self, mock_usage):
        mock_usage.return_value = MagicMock(
            total=100 * (1024 ** 3),
            used=95 * (1024 ** 3),
            free=5 * (1024 ** 3),
        )
        result = self.checker.check_disk("/test")
        assert result["status"] == "critical"
        assert result["percent"] == 95.0

    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_check_disk_default_path(self, mock_usage):
        mock_usage.return_value = MagicMock(
            total=100 * (1024 ** 3),
            used=30 * (1024 ** 3),
            free=70 * (1024 ** 3),
        )
        result = self.checker.check_disk()
        assert "path" in result

    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    def test_check_memory_ok(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=8 * (1024 ** 3),
            used=8 * (1024 ** 3),
            percent=50.0,
        )
        result = self.checker.check_memory()
        assert result["status"] == "ok"
        assert result["percent"] == 50.0
        assert result["total_gb"] == pytest.approx(16.0, rel=1e-2)

    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    def test_check_memory_warning(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=3 * (1024 ** 3),
            used=13 * (1024 ** 3),
            percent=82.0,
        )
        result = self.checker.check_memory()
        assert result["status"] == "warning"

    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    def test_check_memory_critical(self, mock_mem):
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=1 * (1024 ** 3),
            used=15 * (1024 ** 3),
            percent=95.0,
        )
        result = self.checker.check_memory()
        assert result["status"] == "critical"

    @patch("spider_diary.core.system_checker.psutil.pids")
    def test_check_processes_ok(self, mock_pids):
        mock_pids.return_value = list(range(200))
        result = self.checker.check_processes()
        assert result["status"] == "ok"
        assert result["count"] == 200

    @patch("spider_diary.core.system_checker.psutil.pids")
    def test_check_processes_warning(self, mock_pids):
        mock_pids.return_value = list(range(450))
        result = self.checker.check_processes()
        assert result["status"] == "warning"

    @patch("spider_diary.core.system_checker.psutil.pids")
    def test_check_processes_critical(self, mock_pids):
        mock_pids.return_value = list(range(650))
        result = self.checker.check_processes()
        assert result["status"] == "critical"

    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    def test_check_load_ok(self, mock_loadavg, mock_cpu):
        mock_cpu.return_value = 30.0
        mock_loadavg.return_value = (0.5, 0.6, 0.7)
        result = self.checker.check_load()
        assert result["status"] == "ok"
        assert result["cpu_percent"] == 30.0
        assert result["load_1min"] == 0.5
        assert result["load_5min"] == 0.6
        assert result["load_15min"] == 0.7

    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    def test_check_load_warning(self, mock_loadavg, mock_cpu):
        mock_cpu.return_value = 85.0
        mock_loadavg.return_value = (4.0, 3.5, 3.0)
        result = self.checker.check_load()
        assert result["status"] == "warning"

    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    def test_check_load_critical(self, mock_loadavg, mock_cpu):
        mock_cpu.return_value = 95.0
        mock_loadavg.return_value = (8.0, 7.0, 6.0)
        result = self.checker.check_load()
        assert result["status"] == "critical"

    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    def test_check_load_windows_fallback(self, mock_loadavg, mock_cpu):
        mock_cpu.return_value = 50.0
        mock_loadavg.side_effect = AttributeError("no getloadavg on Windows")
        result = self.checker.check_load()
        assert result["status"] == "ok"
        assert result["load_1min"] is None
        assert result["load_5min"] is None
        assert result["load_15min"] is None

    @patch("spider_diary.core.system_checker.socket.gethostname")
    @patch("spider_diary.core.system_checker.datetime")
    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    @patch("spider_diary.core.system_checker.psutil.pids")
    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_run_all_checks_ok(
        self, mock_disk, mock_pids, mock_mem, mock_loadavg, mock_cpu, mock_dt, mock_host
    ):
        mock_disk.return_value = MagicMock(
            total=100 * (1024 ** 3), used=30 * (1024 ** 3), free=70 * (1024 ** 3)
        )
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=10 * (1024 ** 3),
            used=6 * (1024 ** 3),
            percent=37.5,
        )
        mock_pids.return_value = list(range(150))
        mock_cpu.return_value = 25.0
        mock_loadavg.return_value = (0.5, 0.6, 0.7)
        mock_dt.datetime.now.return_value.isoformat.return_value = "2026-01-01T00:00:00"
        mock_host.return_value = "testhost"

        result = self.checker.run_all_checks()

        assert result["overall_status"] == "ok"
        assert result["hostname"] == "testhost"
        assert "timestamp" in result
        assert result["disk"]["status"] == "ok"
        assert result["memory"]["status"] == "ok"
        assert result["processes"]["status"] == "ok"
        assert result["load"]["status"] == "ok"

    @patch("spider_diary.core.system_checker.socket.gethostname")
    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    @patch("spider_diary.core.system_checker.psutil.pids")
    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    def test_run_all_checks_critical(
        self, mock_disk, mock_pids, mock_mem, mock_loadavg, mock_cpu, mock_host
    ):
        mock_disk.return_value = MagicMock(
            total=100 * (1024 ** 3), used=95 * (1024 ** 3), free=5 * (1024 ** 3)
        )
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=1 * (1024 ** 3),
            used=15 * (1024 ** 3),
            percent=94.0,
        )
        mock_pids.return_value = list(range(150))
        mock_cpu.return_value = 25.0
        mock_loadavg.return_value = (0.3, 0.4, 0.5)
        mock_host.return_value = "testhost"

        result = self.checker.run_all_checks()

        assert result["overall_status"] == "critical"

    def test_custom_config(self):
        checker = SystemChecker(config={"disk_warning": 70})
        assert checker.config["disk_warning"] == 70


class TestProjectReader(unittest.TestCase):
    """Tests for ProjectReader CRUD operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_project.db")
        self.reader = ProjectReader(db_path=self.db_path)

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def _insert_sample_data(self, conn):
        now = datetime.datetime.now().isoformat()
        projects = [
            ("PROJ-001", "Test Project Alpha", "Active", "agent-a", "Desc A", now),
            ("PROJ-002", "Test Project Beta", "Archived", "agent-b", "Desc B", now),
        ]
        tasks = [
            ("TASK-001", "PROJ-001", "Task one", "agent-a", "Done", "high", now),
            ("TASK-002", "PROJ-001", "Task two", "agent-a", "Doing", "normal", now),
            ("TASK-003", "PROJ-001", "Task three", "agent-a", "Backlog", "low", now),
            ("TASK-004", "PROJ-002", "Task four", "agent-b", "Done", "normal", now),
            ("TASK-005", "PROJ-002", "Task five", "agent-b", "Review", "high", now),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)", projects
        )
        conn.executemany(
            "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
            tasks,
        )
        conn.commit()

    def test_init_creates_tables(self):
        conn = sqlite3.connect(self.db_path)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "project_meta" in table_names
        assert "task_board" in table_names
        assert "okr_master" in table_names
        conn.close()

    def test_get_stats_empty(self):
        stats = self.reader.get_stats()
        assert stats["projects"] == 0
        assert stats["tasks"] == 0
        assert stats["done"] == 0
        assert stats["doing"] == 0
        assert stats["active"] == 0
        assert stats["progress_pct"] == 0.0

    def test_get_stats_with_data(self):
        conn = sqlite3.connect(self.db_path)
        self._insert_sample_data(conn)
        conn.close()
        stats = self.reader.get_stats()
        assert stats["projects"] == 2
        assert stats["tasks"] == 5
        assert stats["done"] == 2
        assert stats["doing"] == 1
        assert stats["active"] == 1
        assert stats["progress_pct"] == 40.0

    def test_get_all_projects_empty(self):
        projects = self.reader.get_all_projects()
        assert projects == []

    def test_get_all_projects_with_data(self):
        conn = sqlite3.connect(self.db_path)
        self._insert_sample_data(conn)
        conn.close()
        projects = self.reader.get_all_projects()
        assert len(projects) == 2
        p1 = projects[0]
        assert p1["project_id"] == "PROJ-001"
        assert p1["project_name"] == "Test Project Alpha"
        assert p1["status"] == "Active"
        assert p1["owner_agent"] == "agent-a"
        assert p1["total_tasks"] == 3
        assert p1["done_tasks"] == 1
        assert p1["progress_pct"] == pytest.approx(33.3, rel=1e-1)

    def test_get_tasks_by_status(self):
        conn = sqlite3.connect(self.db_path)
        self._insert_sample_data(conn)
        conn.close()
        done_tasks = self.reader.get_tasks_by_status("Done")
        assert len(done_tasks) == 2
        doing_tasks = self.reader.get_tasks_by_status("Doing")
        assert len(doing_tasks) == 1
        backlog_tasks = self.reader.get_tasks_by_status("Backlog")
        assert len(backlog_tasks) == 1
        review_tasks = self.reader.get_tasks_by_status("Review")
        assert len(review_tasks) == 1
        blocked_tasks = self.reader.get_tasks_by_status("Blocked")
        assert len(blocked_tasks) == 0

    def test_get_tasks_by_status_fields(self):
        conn = sqlite3.connect(self.db_path)
        self._insert_sample_data(conn)
        conn.close()
        tasks = self.reader.get_tasks_by_status("Done")
        task = tasks[0]
        assert "task_id" in task
        assert "project_id" in task
        assert "description" in task
        assert "assignee" in task
        assert "kanban_status" in task
        assert "priority" in task
        assert "created_date" in task
        assert "completed_date" in task

    def test_get_issues_empty(self):
        issues = self.reader.get_issues()
        assert issues == []

    def test_get_issues_no_tasks(self):
        conn = sqlite3.connect(self.db_path)
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)",
            ("PROJ-EMPTY", "Empty Project", "Active", "agent-x", "No tasks", now),
        )
        conn.commit()
        conn.close()
        issues = self.reader.get_issues()
        no_task_issues = [i for i in issues if i["type"] == "no_tasks"]
        assert len(no_task_issues) == 1
        assert no_task_issues[0]["severity"] == "warning"
        assert "PROJ-EMPTY" in no_task_issues[0]["description"]

    def test_get_issues_stale_doing(self):
        conn = sqlite3.connect(self.db_path)
        old_date = (datetime.datetime.now() - datetime.timedelta(days=10)).isoformat()
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)",
            ("PROJ-STALE", "Stale Project", "Active", "agent-x", "Has stale task", now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
            ("TASK-OLD", "PROJ-STALE", "Old doing task", "agent-x", "Doing", "high", old_date),
        )
        conn.commit()
        conn.close()
        issues = self.reader.get_issues()
        stale_issues = [i for i in issues if i["type"] == "stale_doing"]
        assert len(stale_issues) == 1
        assert stale_issues[0]["severity"] == "critical"
        assert "TASK-OLD" in stale_issues[0]["description"]
        assert "10 days" in stale_issues[0]["description"]

    def test_get_issues_slow_progress(self):
        conn = sqlite3.connect(self.db_path)
        old_date = (datetime.datetime.now() - datetime.timedelta(days=35)).isoformat()
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)",
            ("PROJ-SLOW", "Slow Project", "Active", "agent-x", "Slow progress", old_date),
        )
        conn.execute(
            "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
            ("TASK-SLOW1", "PROJ-SLOW", "Task 1", "agent-x", "Doing", "normal", old_date),
        )
        conn.execute(
            "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
            ("TASK-SLOW2", "PROJ-SLOW", "Task 2", "agent-x", "Backlog", "low", old_date),
        )
        conn.commit()
        conn.close()
        issues = self.reader.get_issues()
        slow_issues = [i for i in issues if i["type"] == "slow_progress"]
        assert len(slow_issues) == 1
        assert slow_issues[0]["severity"] == "warning"
        assert "PROJ-SLOW" in slow_issues[0]["description"]


class TestBlockerStore(unittest.TestCase):
    """Tests for BlockerStore CRUD operations."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store_path = pathlib.Path(self.tmpdir) / "test_blockers.json"
        self.store = BlockerStore(store_path=self.store_path)

    def tearDown(self):
        try:
            self.store_path.unlink()
        except OSError:
            pass
        try:
            self.store_path.parent.rmdir()
        except OSError:
            pass
        try:
            os.rmdir(self.tmpdir)
        except OSError:
            pass

    def test_init_creates_path(self):
        assert self.store_path.parent.exists()

    def test_get_all_empty(self):
        items = self.store.get_all()
        assert items == []

    def test_get_active_empty(self):
        items = self.store.get_active()
        assert items == []

    def test_add_item(self):
        self.store.add({
            "title": "Test blocker",
            "severity": "critical",
            "message": "Something is broken",
            "impact": "Service down",
            "suggestion": "Fix it",
        })
        items = self.store.get_all()
        assert len(items) == 1
        assert items[0]["title"] == "Test blocker"
        assert items[0]["severity"] == "critical"
        assert items[0]["status"] == "active"
        assert "id" in items[0]
        assert "created_at" in items[0]

    def test_add_item_with_custom_id(self):
        self.store.add({
            "id": "custom-1",
            "title": "Custom ID blocker",
            "severity": "warning",
        })
        items = self.store.get_all()
        assert items[0]["id"] == "custom-1"

    def test_add_multiple_items(self):
        for i in range(5):
            self.store.add({
                "title": f"Blocker {i}",
                "severity": "warning",
            })
        items = self.store.get_all()
        assert len(items) == 5

    def test_get_active_filters_resolved(self):
        self.store.add({"title": "Active 1", "severity": "critical"})
        self.store.add({"title": "Active 2", "severity": "warning"})
        self.store.add({"title": "To be resolved", "severity": "info"})
        self.store.resolve("3")
        active = self.store.get_active()
        assert len(active) == 2
        titles = [i["title"] for i in active]
        assert "To be resolved" not in titles

    def test_get_by_severity(self):
        self.store.add({"title": "Critical 1", "severity": "critical"})
        self.store.add({"title": "Critical 2", "severity": "critical"})
        self.store.add({"title": "Warning 1", "severity": "warning"})
        critical = self.store.get_by_severity("critical")
        assert len(critical) == 2
        warning = self.store.get_by_severity("warning")
        assert len(warning) == 1

    def test_get_by_severity_excludes_resolved(self):
        self.store.add({"title": "Critical blocker", "severity": "critical"})
        self.store.resolve("1")
        critical = self.store.get_by_severity("critical")
        assert len(critical) == 0

    def test_resolve_item(self):
        self.store.add({"title": "Will resolve", "severity": "warning"})
        result = self.store.resolve("1")
        assert result is True
        items = self.store.get_all()
        assert items[0]["status"] == "resolved"
        assert "resolved_at" in items[0]

    def test_resolve_nonexistent_item(self):
        result = self.store.resolve("nonexistent")
        assert result is False

    def test_resolve_string_id_match(self):
        self.store.add({"title": "String ID test", "severity": "info", "id": "abc"})
        result = self.store.resolve("abc")
        assert result is True

    def test_summary_all_resolved(self):
        self.store.add({"title": "Done", "severity": "critical"})
        self.store.resolve("1")
        summary = self.store.summary()
        assert "✅" in summary
        assert "No active blockers" in summary

    def test_summary_with_active_items(self):
        self.store.add({"title": "Crit issue", "severity": "critical"})
        self.store.add({"title": "Warn issue", "severity": "warning"})
        self.store.add({"title": "Info issue", "severity": "info"})
        summary = self.store.summary()
        assert "🔴 Critical (1)" in summary
        assert "🟡 Warning (1)" in summary
        assert "🔵 Info (1)" in summary
        assert "Crit issue" in summary
        assert "Warn issue" in summary
        assert "Info issue" in summary

    def test_remind_markdown_no_active(self):
        md = self.store.remind_markdown()
        assert "✅" in md
        assert "No active blockers" in md

    def test_remind_markdown_with_active(self):
        self.store.add({
            "title": "Disk full",
            "severity": "critical",
            "impact": "No writes",
            "suggestion": "Free up space",
        })
        md = self.store.remind_markdown()
        assert "⚠️" in md
        assert "Disk full" in md
        assert "Active: 1" in md
        assert "critical" in md

    def test_persistence(self):
        self.store.add({"title": "Persist test", "severity": "critical"})
        new_store = BlockerStore(store_path=self.store_path)
        items = new_store.get_all()
        assert len(items) == 1
        assert items[0]["title"] == "Persist test"


class TestReportGenerator(unittest.TestCase):
    """Tests for ReportGenerator output format."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.output_dir = os.path.join(self.tmpdir, "reports")
        self.generator = ReportGenerator(output_dir=self.output_dir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def _sample_system_data(self):
        return {
            "disk": {
                "path": "/",
                "total_gb": 100.0,
                "used_gb": 50.0,
                "free_gb": 50.0,
                "percent": 50.0,
                "status": "ok",
            },
            "memory": {
                "total_gb": 16.0,
                "available_gb": 8.0,
                "used_gb": 8.0,
                "percent": 50.0,
                "status": "ok",
            },
            "processes": {"count": 150, "status": "ok"},
            "load": {
                "load_1min": 0.5,
                "load_5min": 0.6,
                "load_15min": 0.7,
                "cpu_percent": 25.0,
                "status": "ok",
            },
            "overall_status": "ok",
            "timestamp": "2026-01-15T12:00:00",
            "hostname": "testhost",
        }

    def _sample_project_data(self):
        return {
            "projects": [
                {"id": "PROJ-001", "name": "Alpha", "status": "Active", "progress": 50},
                {"id": "PROJ-002", "name": "Beta", "status": "Active", "progress": 75},
            ],
            "total": 2,
            "tasks": 10,
            "done": 5,
            "doing": 3,
            "active": 2,
            "progress_pct": 50.0,
        }

    def _sample_issues(self):
        return [
            {
                "type": "stale_doing",
                "severity": "critical",
                "project_id": "PROJ-001",
                "description": "Task TASK-001 has been in Doing for 10 days.",
            }
        ]

    def test_generate_returns_content(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        assert "content" in data
        assert "timestamp" in data
        assert data["report_path"] is None

    def test_generate_has_all_sections(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), self._sample_issues()
        )
        content = data["content"]
        assert "# 每日运维报告 / Daily Ops Report" in content
        assert "## 1. 系统状态检查" in content
        assert "## 2. 项目状态总览" in content
        assert "## 3. 发现的问题" in content
        assert "## 4. 运维建议" in content
        assert "## 5. 总结" in content
        assert "Generated by Spider Diary" in content

    def test_generate_system_details(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        content = data["content"]
        assert "testhost" in content
        assert "50.0%" in content
        assert "100.0 GB" in content

    def test_generate_project_table(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        content = data["content"]
        assert "PROJ-001" in content
        assert "Alpha" in content
        assert "Active" in content

    def test_generate_issues_section(self):
        issues = self._sample_issues()
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), issues
        )
        content = data["content"]
        assert "TASK-001" in content
        assert "10 days" in content

    def test_generate_issues_empty(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        content = data["content"]
        assert "无未解决的问题" in content

    def test_generate_advice_normal(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        content = data["content"]
        assert "系统运行正常" in content

    def test_generate_advice_disk_warning(self):
        sys_data = self._sample_system_data()
        sys_data["disk"] = {
            "path": "/",
            "total_gb": 100.0,
            "used_gb": 85.0,
            "free_gb": 15.0,
            "percent": 85.0,
            "status": "warning",
        }
        data = self.generator.generate(sys_data, self._sample_project_data(), [])
        content = data["content"]
        assert "磁盘空间紧张" in content

    def test_generate_advice_memory_critical(self):
        sys_data = self._sample_system_data()
        sys_data["memory"] = {
            "total_gb": 16.0,
            "available_gb": 1.0,
            "used_gb": 15.0,
            "percent": 95.0,
            "status": "critical",
        }
        data = self.generator.generate(sys_data, self._sample_project_data(), [])
        content = data["content"]
        assert "内存使用率较高" in content

    def test_generate_advice_cpu_high(self):
        sys_data = self._sample_system_data()
        sys_data["load"] = {
            "load_1min": 8.0,
            "load_5min": 7.0,
            "load_15min": 6.0,
            "cpu_percent": 90.0,
            "status": "critical",
        }
        data = self.generator.generate(sys_data, self._sample_project_data(), [])
        content = data["content"]
        assert "CPU 负载较高" in content

    def test_generate_risk_level(self):
        sys_data = self._sample_system_data()
        data = self.generator.generate(sys_data, self._sample_project_data(), [])
        assert data["content"].count("风险等级") >= 1

    def test_save_creates_files(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        result = self.generator.save(data)
        assert result is not None
        assert os.path.exists(result)
        latest = os.path.join(self.output_dir, "latest.md")
        assert os.path.exists(latest)

    def test_save_content_persists(self):
        data = self.generator.generate(
            self._sample_system_data(), self._sample_project_data(), []
        )
        report_path = self.generator.save(data)
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "# 每日运维报告 / Daily Ops Report" in content

    def test_generate_and_save(self):
        result = self.generator.generate_and_save(
            self._sample_system_data(), self._sample_project_data(), self._sample_issues()
        )
        assert result["report_path"] is not None
        assert os.path.exists(result["report_path"])
        assert "content" in result

    def test_determine_risk_level(self):
        assert self.generator._determine_risk_level({"overall_status": "ok"}) == "低 / Low"
        assert self.generator._determine_risk_level({"overall_status": "warning"}) == "中 / Medium"
        assert self.generator._determine_risk_level({"overall_status": "critical"}) == "高 / High"
        assert self.generator._determine_risk_level({"overall_status": "unknown"}) == "低 / Low"

    def test_generate_summary(self):
        summary = self.generator._generate_summary(
            self._sample_system_data(), self._sample_project_data(), self._sample_issues()
        )
        assert "项目总数" in summary or "2 个项目" in summary
        assert "待处理问题" in summary

    def test_render_issues(self):
        issues = self._sample_issues()
        rendered = self.generator._render_issues(issues)
        assert "TASK-001" in rendered

    def test_render_issues_empty(self):
        rendered = self.generator._render_issues([])
        assert "无未解决的问题" in rendered

    def test_render_project_table(self):
        table = self.generator._render_project_table(
            self._sample_project_data()["projects"]
        )
        assert "PROJ-001" in table
        assert "Alpha" in table
        assert "项目ID" in table or "项目ID" not in table

    def test_render_project_table_empty(self):
        table = self.generator._render_project_table([])
        assert "无项目记录" in table


class TestDiaryEngineIntegration(unittest.TestCase):
    """Integration tests for DiaryEngine."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "project.db")
        self.report_dir = os.path.join(self.tmpdir, "reports")
        self.engine = DiaryEngine(
            base_path=self.tmpdir,
            config={
                "db_path": self.db_path,
                "output_dir": self.report_dir,
            },
        )

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def _init_sample_data(self):
        conn = sqlite3.connect(self.db_path)
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)",
            ("PROJ-001", "Integration Test", "Active", "agent-test", "Test project", now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
            ("TASK-001", "PROJ-001", "Test task", "agent-test", "Done", "normal", now),
        )
        conn.commit()
        conn.close()

    @patch("spider_diary.core.system_checker.psutil.cpu_percent")
    @patch("spider_diary.core.system_checker.psutil.getloadavg")
    @patch("spider_diary.core.system_checker.psutil.virtual_memory")
    @patch("spider_diary.core.system_checker.psutil.pids")
    @patch("spider_diary.core.system_checker.shutil.disk_usage")
    @patch("spider_diary.core.system_checker.socket.gethostname")
    def test_run_quick_check(
        self, mock_host, mock_disk, mock_pids, mock_mem, mock_loadavg, mock_cpu
    ):
        mock_host.return_value = "integration-host"
        mock_disk.return_value = MagicMock(
            total=100 * (1024 ** 3), used=30 * (1024 ** 3), free=70 * (1024 ** 3)
        )
        mock_mem.return_value = MagicMock(
            total=16 * (1024 ** 3),
            available=10 * (1024 ** 3),
            used=6 * (1024 ** 3),
            percent=37.5,
        )
        mock_pids.return_value = list(range(100))
        mock_cpu.return_value = 20.0
        mock_loadavg.return_value = (0.2, 0.3, 0.4)

        self._init_sample_data()
        result = self.engine.run_quick_check()

        assert "system_data" in result
        assert "project_data" in result
        assert "timestamp" in result
        assert result["system_data"]["hostname"] == "integration-host"
        assert result["project_data"]["projects"][0]["project_id"] == "PROJ-001"
        assert result["project_data"]["tasks"] == 1

    def test_get_summary(self):
        self._init_sample_data()
        with patch("spider_diary.core.system_checker.psutil.cpu_percent", return_value=20.0), \
             patch("spider_diary.core.system_checker.psutil.getloadavg", return_value=(0.2, 0.3, 0.4)), \
             patch("spider_diary.core.system_checker.psutil.virtual_memory", return_value=MagicMock(
                 total=16 * (1024 ** 3), available=10 * (1024 ** 3), used=6 * (1024 ** 3), percent=37.5
             )), \
             patch("spider_diary.core.system_checker.psutil.pids", return_value=list(range(100))), \
             patch("spider_diary.core.system_checker.shutil.disk_usage", return_value=MagicMock(
                 total=100 * (1024 ** 3), used=30 * (1024 ** 3), free=70 * (1024 ** 3)
             )), \
             patch("spider_diary.core.system_checker.socket.gethostname", return_value="test"):
            summary = self.engine.get_summary()

        assert "Spider Diary System Summary" in summary
        assert "Overall Status" in summary
        assert "Projects" in summary
        assert "Tasks" in summary

    def test_engine_initialization(self):
        assert self.engine.base_path == pathlib.Path(self.tmpdir)
        assert str(self.engine.project_reader.db_path) == self.db_path
        assert str(self.engine.report_generator.output_dir) == self.report_dir


if __name__ == "__main__":
    unittest.main()
