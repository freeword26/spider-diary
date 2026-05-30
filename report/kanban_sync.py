"""Kanban board synchronization module.

Generates JSON and Markdown kanban boards from project data.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_KANBAN_COLUMNS = ["todo", "doing", "review", "done", "blocked"]


class KanbanSyncer:
    """Synchronizes project data into kanban board representations."""

    def __init__(self, output_dir=None):
        """Initialize KanbanSyncer.

        Args:
            output_dir: Directory for output files. Defaults to ./reports/
                        resolved relative to the current working directory.
        """
        if output_dir is None:
            output_dir = Path("reports")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _build_kanban(self, project_data):
        """Build kanban column mapping from project data.

        Args:
            project_data: dict from ProjectReader containing tasks/status info.

        Returns:
            dict mapping column names to lists of task dicts.
        """
        columns = {col: [] for col in _KANBAN_COLUMNS}
        tasks = project_data.get("tasks", [])
        for task in tasks:
            status = task.get("kanban_status", "todo")
            if status not in columns:
                status = "todo"
            entry = {
                "id": task.get("task_id", ""),
                "desc": task.get("description", ""),
                "assignee": task.get("assignee", ""),
                "priority": task.get("priority", "normal"),
            }
            columns[status].append(entry)
        return columns

    def _today_str(self):
        """Return today's date as a string in YYYY-MM-DD format."""
        return datetime.now().strftime("%Y-%m-%d")

    def sync(self, project_data):
        """Generate a kanban JSON file from project data.

        Args:
            project_data: dict from ProjectReader.

        Returns:
            str: Path to the dated kanban JSON file.
        """
        columns = self._build_kanban(project_data)
        date_str = self._today_str()

        dated_path = self.output_dir / f"kanban_{date_str}.json"
        latest_path = self.output_dir / "kanban_latest.json"

        for path in (dated_path, latest_path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(columns, f, ensure_ascii=False, indent=2)
            logger.info("Kanban JSON saved to %s", path)

        return str(dated_path)

    def sync_markdown(self, project_data):
        """Generate a markdown kanban board from project data.

        Args:
            project_data: dict from ProjectReader.

        Returns:
            str: Path to the dated kanban markdown file.
        """
        columns = self._build_kanban(project_data)
        date_str = self._today_str()

        lines = [f"# Kanban Board — {date_str}", ""]
        for col in _KANBAN_COLUMNS:
            lines.append(f"## {col.upper()}")
            lines.append("")
            items = columns.get(col, [])
            if not items:
                lines.append("_No items_")
                lines.append("")
                continue
            lines.append("| ID | Description | Assignee | Priority |")
            lines.append("|----|-------------|----------|----------|")
            for item in items:
                lines.append(
                    f"| {item['id']} | {item['desc']} "
                    f"| {item['assignee']} | {item['priority']} |"
                )
            lines.append("")

        content = "\n".join(lines)

        dated_path = self.output_dir / f"kanban_{date_str}.md"
        latest_path = self.output_dir / "kanban_latest.md"

        for path in (dated_path, latest_path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Kanban markdown saved to %s", path)

        return str(dated_path)
