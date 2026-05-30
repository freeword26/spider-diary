"""PM Report Generator module.

Generates PMO reports (project progress, resource utilization,
task analysis, milestone status, executive summary) backed by
the PMProjectDB. Outputs JSON with optional Markdown conversion.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VALID_REPORT_TYPES = (
    "project_progress",
    "resource_utilization",
    "task_analysis",
    "milestone_status",
    "executive_summary",
)


class PMReportGenerator:
    """Generator for PMO reports backed by PMProjectDB."""

    def __init__(self, db: "PMProjectDB", output_dir: Optional[Path] = None) -> None:
        """Initialize PMReportGenerator.

        Args:
            db: PMProjectDB instance to query.
            output_dir: Directory for saved report files.
                        Defaults to ./reports in current working directory.
        """
        self.db = db
        if output_dir is None:
            output_dir = Path("reports")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("PMReportGenerator initialized: output_dir=%s", self.output_dir)

    def _report_id(self) -> str:
        return f"RPT_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _now(self) -> str:
        return datetime.now().isoformat()

    def _save_json(self, report: Dict[str, Any], filename: str) -> Path:
        """Save report dict as JSON file.

        Args:
            report: Report data dict.
            filename: Output filename.

        Returns:
            Path to saved file.
        """
        path = self.output_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        logger.info("Report saved: %s", path)
        return path

    # ─── Report: project_progress ────────────────────────────────────

    def generate_project_progress(
        self, project_id: str, include_details: bool = True
    ) -> Dict[str, Any]:
        """Generate a project progress report.

        Args:
            project_id: Project identifier.
            include_details: Whether to include task-level detail.

        Returns:
            Report dict (also saved as JSON).
        """
        project = self.db.get_project(project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        progress = self.db.get_task_progress(project_id)
        overdue = self.db.get_overdue_tasks(project_id)
        upcoming = self.db.get_upcoming_tasks(project_id, days=7)

        report: Dict[str, Any] = {
            "report_id": self._report_id(),
            "report_type": "project_progress",
            "project_id": project_id,
            "project_name": project.get("project_name", ""),
            "generated_at": self._now(),
            "period": {
                "start_date": project.get("start_date", ""),
                "end_date": project.get("end_date", ""),
            },
            "summary": {
                "status": project.get("status", ""),
                "progress_percentage": progress.get("progress_percentage", 0),
                "total_tasks": progress.get("total_tasks", 0),
                "completed_tasks": progress.get("completed_tasks", 0),
                "in_progress_tasks": progress.get("in_progress_tasks", 0),
                "pending_tasks": progress.get("pending_tasks", 0),
                "blocked_tasks": progress.get("blocked_tasks", 0),
            },
            "time_tracking": {
                "total_estimated_hours": progress.get("total_estimated_hours", 0),
                "total_actual_hours": progress.get("total_actual_hours", 0),
                "hours_variance": progress.get("total_actual_hours", 0)
                - progress.get("total_estimated_hours", 0),
            },
            "alerts": {
                "overdue_tasks_count": len(overdue),
                "upcoming_tasks_count": len(upcoming),
            },
        }

        if include_details:
            report["details"] = {
                "overdue_tasks": overdue,
                "upcoming_tasks": upcoming,
                "all_tasks": self.db.list_tasks(project_id=project_id),
            }

        ts = datetime.now().strftime("%Y%m%d")
        report["report_file"] = str(
            self._save_json(report, f"project_progress_{project_id}_{ts}.json")
        )
        report["success"] = True
        return report

    # ─── Report: resource_utilization ────────────────────────────────

    def generate_resource_utilization(
        self,
        project_id: Optional[str] = None,
        include_details: bool = True,
    ) -> Dict[str, Any]:
        """Generate a resource utilization report.

        Args:
            project_id: Optional project scope. If None, reports globally.
            include_details: Whether to include per-resource detail.

        Returns:
            Report dict (also saved as JSON).
        """
        if project_id:
            project = self.db.get_project(project_id)
            if project is None:
                return {"success": False, "error": f"Project {project_id} not found"}

            project_resources = self.db.get_project_resources(project_id)
            resources = project_resources
            total_capacity = sum(
                r.get("capacity", 0) for r in project_resources
            )
            total_used = sum(
                r.get("allocated_capacity", 0) for r in project_resources
            )

            avg_util = 0.0
            if project_resources:
                utils = [
                    (r.get("allocated_capacity", 0) / r.get("capacity", 1)) * 100
                    for r in project_resources
                    if r.get("capacity", 0) > 0
                ]
                if utils:
                    avg_util = round(sum(utils) / len(utils), 2)

            utilization_data = {
                "project_id": project_id,
                "resources": resources,
                "total_resources": len(resources),
                "total_capacity": total_capacity,
                "total_used": total_used,
                "average_utilization": avg_util,
            }
        else:
            utilization_data = self.db.get_resource_utilization()

        report: Dict[str, Any] = {
            "report_id": self._report_id(),
            "report_type": "resource_utilization",
            "project_id": project_id,
            "generated_at": self._now(),
            "summary": {
                "total_resources": utilization_data.get("total_resources", 0),
                "available_resources": utilization_data.get("available_resources", 0),
                "in_use_resources": utilization_data.get("in_use_resources", 0),
                "average_utilization": utilization_data.get("average_utilization", 0),
            },
        }

        if include_details:
            report["details"] = utilization_data

        ts = datetime.now().strftime("%Y%m%d")
        report["report_file"] = str(
            self._save_json(report, f"resource_utilization_{ts}.json")
        )
        report["success"] = True
        return report

    # ─── Report: task_analysis ───────────────────────────────────────

    def generate_task_analysis(
        self, project_id: str, include_details: bool = True
    ) -> Dict[str, Any]:
        """Generate a task analysis report grouped by status, priority, and assignee.

        Args:
            project_id: Project identifier.
            include_details: Whether to include grouped task lists.

        Returns:
            Report dict (also saved as JSON).
        """
        project = self.db.get_project(project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        tasks = self.db.list_tasks(project_id=project_id)

        by_status: Dict[str, List[Dict]] = {}
        by_priority: Dict[str, List[Dict]] = {}
        by_assignee: Dict[str, List[Dict]] = {}

        for task in tasks:
            for grouping, key_field in [
                (by_status, "status"),
                (by_priority, "priority"),
                (by_assignee, "assignee"),
            ]:
                key = task.get(key_field, "")
                grouping.setdefault(key, []).append(task)

        report: Dict[str, Any] = {
            "report_id": self._report_id(),
            "report_type": "task_analysis",
            "project_id": project_id,
            "generated_at": self._now(),
            "summary": {
                "total_tasks": len(tasks),
                "tasks_by_status": {k: len(v) for k, v in by_status.items()},
                "tasks_by_priority": {k: len(v) for k, v in by_priority.items()},
                "tasks_by_assignee": {k: len(v) for k, v in by_assignee.items()},
            },
        }

        if include_details:
            report["details"] = {
                "tasks_by_status": by_status,
                "tasks_by_priority": by_priority,
                "tasks_by_assignee": by_assignee,
            }

        ts = datetime.now().strftime("%Y%m%d")
        report["report_file"] = str(
            self._save_json(report, f"task_analysis_{project_id}_{ts}.json")
        )
        report["success"] = True
        return report

    # ─── Report: milestone_status ────────────────────────────────────

    def generate_milestone_status(
        self, project_id: str, include_details: bool = True
    ) -> Dict[str, Any]:
        """Generate a milestone status report.

        Args:
            project_id: Project identifier.
            include_details: Whether to include milestone detail lists.

        Returns:
            Report dict (also saved as JSON).
        """
        project = self.db.get_project(project_id)
        if project is None:
            return {"success": False, "error": f"Project {project_id} not found"}

        milestones = project.get("milestones", [])
        today = datetime.now().date()

        completed: List[Dict] = []
        upcoming: List[Dict] = []
        overdue: List[Dict] = []

        for ms in milestones:
            status = ms.get("status", "")
            if status == "completed":
                completed.append(ms)
            elif "date" in ms:
                try:
                    target = datetime.strptime(ms["date"], "%Y-%m-%d").date()
                    if target < today:
                        overdue.append(ms)
                    else:
                        upcoming.append(ms)
                except ValueError:
                    upcoming.append(ms)
            else:
                upcoming.append(ms)

        total = len(milestones)
        completion_pct = (len(completed) / total * 100) if total > 0 else 0.0

        report: Dict[str, Any] = {
            "report_id": self._report_id(),
            "report_type": "milestone_status",
            "project_id": project_id,
            "project_name": project.get("project_name", ""),
            "generated_at": self._now(),
            "summary": {
                "total_milestones": total,
                "completed_milestones": len(completed),
                "upcoming_milestones": len(upcoming),
                "overdue_milestones": len(overdue),
                "completion_percentage": round(completion_pct, 2),
            },
        }

        if include_details:
            report["details"] = {
                "completed_milestones": completed,
                "upcoming_milestones": upcoming,
                "overdue_milestones": overdue,
                "all_milestones": milestones,
            }

        ts = datetime.now().strftime("%Y%m%d")
        report["report_file"] = str(
            self._save_json(report, f"milestone_status_{project_id}_{ts}.json")
        )
        report["success"] = True
        return report

    # ─── Report: executive_summary ───────────────────────────────────

    def generate_executive_summary(self) -> Dict[str, Any]:
        """Generate an executive summary across all projects and resources.

        Returns:
            Report dict (also saved as JSON).
        """
        status = self.db.get_overall_status()

        report: Dict[str, Any] = {
            "report_id": self._report_id(),
            "report_type": "executive_summary",
            "generated_at": self._now(),
            "period": {"report_date": datetime.now().strftime("%Y-%m-%d")},
            "summary": {
                "total_projects": status["total_projects"],
                "active_projects": status["active_projects"],
                "total_tasks": status["total_tasks"],
                "total_completed_tasks": status["total_completed_tasks"],
                "overall_progress": status["overall_progress"],
                "average_resource_utilization": status[
                    "resource_utilization"
                ].get("average_utilization", 0),
            },
            "project_summaries": status["project_summaries"],
            "resource_summary": {
                "total_resources": status["resource_utilization"].get(
                    "total_resources", 0
                ),
                "available_resources": status["resource_utilization"].get(
                    "available_resources", 0
                ),
                "in_use_resources": status["resource_utilization"].get(
                    "in_use_resources", 0
                ),
                "average_utilization": status["resource_utilization"].get(
                    "average_utilization", 0
                ),
            },
        }

        ts = datetime.now().strftime("%Y%m%d")
        report["report_file"] = str(
            self._save_json(report, f"executive_summary_{ts}.json")
        )
        report["success"] = True
        return report

    # ─── Markdown conversion ─────────────────────────────────────────

    @staticmethod
    def convert_report_to_markdown(report: Dict[str, Any]) -> str:
        """Convert a report JSON dict to Markdown string.

        Args:
            report: Report data dict.

        Returns:
            Markdown-formatted string.
        """
        lines: List[str] = []

        report_type = report.get("report_type", "unknown")
        report_id = report.get("report_id", "")
        generated_at = report.get("generated_at", "")

        title = report_type.replace("_", " ").title()
        lines.append(f"# {title} Report")
        lines.append(f"")
        lines.append(f"**Report ID**: {report_id}")
        lines.append(f"**Generated At**: {generated_at}")
        lines.append("")

        period = report.get("period", {})
        if period:
            lines.append("## Period")
            for k, v in period.items():
                lines.append(f"- **{k.replace('_', ' ').title()}**: {v}")
            lines.append("")

        summary = report.get("summary", {})
        if summary:
            lines.append("## Summary")
            lines.extend(_dict_to_md_list(summary))
            lines.append("")

        time_tracking = report.get("time_tracking", {})
        if time_tracking:
            lines.append("## Time Tracking")
            lines.extend(_dict_to_md_list(time_tracking))
            lines.append("")

        alerts = report.get("alerts", {})
        if alerts:
            lines.append("## Alerts")
            lines.extend(_dict_to_md_list(alerts))
            lines.append("")

        if "project_summaries" in report:
            lines.append("## Project Summaries")
            lines.append("| Project ID | Name | Status | Progress | Tasks | Completed |")
            lines.append("|------------|------|--------|----------|-------|-----------|")
            for ps in report["project_summaries"]:
                lines.append(
                    f"| {ps.get('project_id', '')} "
                    f"| {ps.get('project_name', '')} "
                    f"| {ps.get('status', '')} "
                    f"| {ps.get('progress', 0)}% "
                    f"| {ps.get('tasks', 0)} "
                    f"| {ps.get('completed', 0)} |"
                )
            lines.append("")

        resource_summary = report.get("resource_summary", {})
        if resource_summary:
            lines.append("## Resource Summary")
            lines.extend(_dict_to_md_list(resource_summary))
            lines.append("")

        if "details" in report:
            lines.append("## Details")
            lines.append("```json")
            lines.append(
                json.dumps(report["details"], ensure_ascii=False, indent=2, default=str)
            )
            lines.append("```")

        return "\n".join(lines)


def _dict_to_md_list(d: Dict[str, Any], indent: int = 0) -> List[str]:
    """Helper to render a dict as Markdown bullet list.

    Args:
        d: Dict to render.
        indent: Indentation level.

    Returns:
        List of markdown lines.
    """
    prefix = "  " * indent + "-"
    lines: List[str] = []
    for k, v in d.items():
        label = k.replace("_", " ").title()
        if isinstance(v, dict):
            lines.append(f"{prefix} **{label}**:")
            lines.extend(_dict_to_md_list(v, indent + 1))
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                lines.append(f"{prefix} **{label}**: ({len(v)} items)")
            else:
                lines.append(f"{prefix} **{label}**: {', '.join(str(i) for i in v)}")
        else:
            lines.append(f"{prefix} **{label}**: {v}")
    return lines
