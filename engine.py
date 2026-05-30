import datetime
import logging
import os
import pathlib

from .core.system_checker import SystemChecker
from .core.project_reader import ProjectReader
from .report.report_generator import ReportGenerator
from .report.kanban_sync import KanbanSyncer

logger = logging.getLogger(__name__)


class DiaryEngine:

    def __init__(self, base_path=None, config=None):
        self.base_path = pathlib.Path(base_path or os.getcwd())
        self.config = config or {}

        disk_path = self.config.get("disk_path", str(self.base_path))
        db_path = self.config.get("db_path", str(self.base_path / "project.db"))
        output_dir = self.config.get("output_dir", str(self.base_path / "reports"))

        self.system_checker = SystemChecker(config=self.config.get("system"))
        self.project_reader = ProjectReader(db_path=db_path)
        self.report_generator = ReportGenerator(output_dir=output_dir)
        self.kanban_syncer = KanbanSyncer(output_dir=output_dir)

        logger.info(
            "DiaryEngine initialised: base_path=%s db_path=%s output_dir=%s",
            self.base_path,
            db_path,
            output_dir,
        )

    def run_daily_ops(self):
        system_data = self.system_checker.run_all_checks()
        project_stats = self.project_reader.get_stats()
        projects = self.project_reader.get_all_projects()
        issues = self.project_reader.get_issues()

        project_data = {
            "projects": projects,
            "total": project_stats.get("projects", 0),
            "tasks": project_stats.get("tasks", 0),
            "done": project_stats.get("done", 0),
            "doing": project_stats.get("doing", 0),
            "active": project_stats.get("active", 0),
            "progress_pct": project_stats.get("progress_pct", 0),
        }

        report_data = self.report_generator.generate_and_save(
            system_data, project_data, issues
        )
        report_path = report_data.get("report_path")

        all_tasks = []
        for status in ("Backlog", "Doing", "Review", "Done", "Blocked"):
            all_tasks.extend(self.project_reader.get_tasks_by_status(status))
        kanban_data = {
            "stats": project_stats,
            "tasks": all_tasks,
        }
        kanban_path = self.kanban_syncer.sync(kanban_data)

        timestamp = system_data.get(
            "timestamp", datetime.datetime.now().isoformat()
        )
        overall_status = system_data.get("overall_status", "ok")

        result = {
            "report_path": report_path,
            "kanban_path": kanban_path,
            "system_data": system_data,
            "project_data": project_data,
            "issues": issues,
            "timestamp": timestamp,
            "status": overall_status,
        }
        logger.info("Daily ops complete: status=%s", overall_status)
        return result

    def run_quick_check(self):
        system_data = self.system_checker.run_all_checks()
        project_stats = self.project_reader.get_stats()
        projects = self.project_reader.get_all_projects()

        project_data = {
            "projects": projects,
            "total": project_stats.get("projects", 0),
            "tasks": project_stats.get("tasks", 0),
            "done": project_stats.get("done", 0),
            "doing": project_stats.get("doing", 0),
            "active": project_stats.get("active", 0),
            "progress_pct": project_stats.get("progress_pct", 0),
        }

        timestamp = system_data.get(
            "timestamp", datetime.datetime.now().isoformat()
        )

        return {
            "system_data": system_data,
            "project_data": project_data,
            "timestamp": timestamp,
        }

    def get_summary(self):
        quick = self.run_quick_check()
        sd = quick["system_data"]
        pd = quick["project_data"]
        disk = sd.get("disk", {})
        memory = sd.get("memory", {})
        load = sd.get("load", {})

        lines = [
            f"Spider Diary System Summary",
            f"==========================",
            f"Overall Status : {sd.get('overall_status', 'unknown')}",
            f"Disk           : {disk.get('percent', 'N/A')}% used "
            f"({disk.get('free_gb', 'N/A')} GB free) [{disk.get('status', 'N/A')}]",
            f"Memory         : {memory.get('percent', 'N/A')}% used "
            f"({memory.get('available_gb', 'N/A')} GB avail) [{memory.get('status', 'N/A')}]",
            f"CPU            : {load.get('cpu_percent', 'N/A')}% [{load.get('status', 'N/A')}]",
            f"Projects       : {pd.get('total', 0)} total, {pd.get('active', 0)} active",
            f"Tasks          : {pd.get('tasks', 0)} total, "
            f"{pd.get('done', 0)} done, {pd.get('doing', 0)} doing",
            f"Progress       : {pd.get('progress_pct', 0)}%",
        ]
        return "\n".join(lines)
