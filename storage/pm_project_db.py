"""PM Project Database module.

Unified SQLite-backed storage for PMO projects, tasks, and resources.
Merges project initialization, task management, and resource management
into a single PMProjectDB class.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PMProjectDB:
    """Unified SQLite-backed storage for PMO projects, tasks, and resources."""

    _CREATE_TABLES = [
        """
        CREATE TABLE IF NOT EXISTS pm_projects (
            project_id TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            project_type TEXT DEFAULT 'new',
            description TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            owner TEXT DEFAULT '',
            team_members TEXT DEFAULT '[]',
            dependencies TEXT DEFAULT '[]',
            milestones TEXT DEFAULT '[]',
            budget REAL DEFAULT 0.0,
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'initialized',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pm_tasks (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            priority TEXT DEFAULT 'medium',
            start_date TEXT DEFAULT '',
            end_date TEXT DEFAULT '',
            estimated_hours REAL DEFAULT 0.0,
            actual_hours REAL DEFAULT 0.0,
            dependencies TEXT DEFAULT '[]',
            tags TEXT DEFAULT '[]',
            okr_id TEXT DEFAULT '',
            progress_pct REAL DEFAULT 0.0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            completed_at TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pm_resources (
            resource_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            resource_type TEXT DEFAULT 'human',
            status TEXT DEFAULT 'available',
            capacity REAL DEFAULT 0.0,
            used_capacity REAL DEFAULT 0.0,
            skills TEXT DEFAULT '[]',
            cost_per_hour REAL DEFAULT 0.0,
            metadata TEXT DEFAULT '{}',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS pm_allocations (
            allocation_id TEXT PRIMARY KEY,
            resource_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            task_id TEXT DEFAULT '',
            allocated_capacity REAL DEFAULT 0.0,
            start_time TEXT DEFAULT '',
            end_time TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT ''
        )
        """,
    ]

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize PMProjectDB.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ./pm_project.db in the current working directory.
        """
        if db_path is None:
            db_path = Path("pm_project.db")
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create tables if they do not exist."""
        for stmt in self._CREATE_TABLES:
            self.conn.execute(stmt)
        self.conn.commit()

    def _now(self) -> str:
        """Return current local time as an ISO-8601 string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ─── Project CRUD ────────────────────────────────────────────────

    def create_project(
        self,
        project_id: str,
        name: str,
        project_type: str = "new",
        description: str = "",
        start_date: str = "",
        end_date: str = "",
        priority: str = "medium",
        owner: str = "",
        team_members: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        milestones: Optional[List[Dict[str, Any]]] = None,
        budget: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Create a new project with full metadata.

        Args:
            project_id: Unique project identifier.
            name: Project display name.
            project_type: Type classification (main/sub/new/non-it).
            description: Project description.
            start_date: Planned start date (ISO format).
            end_date: Planned end date (ISO format).
            priority: Priority level (high/medium/low).
            owner: Project owner identifier.
            team_members: List of team member identifiers.
            dependencies: List of dependent project IDs.
            milestones: List of milestone dicts with name/date/description.
            budget: Budget allocation.
            tags: List of tag strings.

        Returns:
            True if created, False if project_id already exists.
        """
        import json

        cur = self.conn.execute(
            "SELECT 1 FROM pm_projects WHERE project_id = ?", (project_id,)
        )
        if cur.fetchone() is not None:
            logger.warning("Project %s already exists", project_id)
            return False

        now = self._now()
        self.conn.execute(
            """INSERT INTO pm_projects
               (project_id, project_name, project_type, description,
                start_date, end_date, priority, owner, team_members,
                dependencies, milestones, budget, tags, status,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                name,
                project_type,
                description,
                start_date,
                end_date,
                priority,
                owner,
                json.dumps(team_members or []),
                json.dumps(dependencies or []),
                json.dumps(milestones or []),
                budget,
                json.dumps(tags or []),
                "initialized",
                now,
                now,
            ),
        )
        self.conn.commit()
        logger.info("Created project %s (%s)", project_id, name)
        return True

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a project by ID.

        Args:
            project_id: Project identifier.

        Returns:
            Project dict or None if not found.
        """
        import json

        cur = self.conn.execute(
            "SELECT * FROM pm_projects WHERE project_id = ?", (project_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        for field in ("team_members", "dependencies", "milestones", "tags"):
            try:
                d[field] = json.loads(d.get(field, "[]"))
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        return d

    def list_projects(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all projects, optionally filtered by status.

        Args:
            status: Filter by status field.

        Returns:
            List of project dicts.
        """
        import json

        query = "SELECT * FROM pm_projects"
        params: list = []
        if status is not None:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at"

        cur = self.conn.execute(query, params)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            for field in ("team_members", "dependencies", "milestones", "tags"):
                try:
                    d[field] = json.loads(d.get(field, "[]"))
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
            results.append(d)
        return results

    def update_project(self, project_id: str, **kwargs: Any) -> bool:
        """Update project fields.

        Args:
            project_id: Project identifier.
            **kwargs: Fields to update.

        Returns:
            True if updated, False if not found.
        """
        import json

        cur = self.conn.execute(
            "SELECT 1 FROM pm_projects WHERE project_id = ?", (project_id,)
        )
        if cur.fetchone() is None:
            logger.warning("Project %s not found", project_id)
            return False

        json_fields = {"team_members", "dependencies", "milestones", "tags"}
        set_parts = []
        params: list = []
        for key, value in kwargs.items():
            if key in json_fields and not isinstance(value, str):
                value = json.dumps(value)
            set_parts.append(f"{key} = ?")
            params.append(value)

        set_parts.append("updated_at = ?")
        params.append(self._now())
        params.append(project_id)

        self.conn.execute(
            f"UPDATE pm_projects SET {', '.join(set_parts)} WHERE project_id = ?",
            params,
        )
        self.conn.commit()
        logger.info("Updated project %s", project_id)
        return True

    def delete_project(self, project_id: str) -> bool:
        """Delete a project and its associated tasks/allocations.

        Args:
            project_id: Project identifier.

        Returns:
            True if deleted, False if not found.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM pm_projects WHERE project_id = ?", (project_id,)
        )
        if cur.fetchone() is None:
            logger.warning("Project %s not found", project_id)
            return False

        self.conn.execute("DELETE FROM pm_allocations WHERE project_id = ?", (project_id,))
        self.conn.execute("DELETE FROM pm_tasks WHERE project_id = ?", (project_id,))
        self.conn.execute("DELETE FROM pm_projects WHERE project_id = ?", (project_id,))
        self.conn.commit()
        logger.info("Deleted project %s", project_id)
        return True

    # ─── Task CRUD ───────────────────────────────────────────────────

    def create_task(
        self,
        task_id: str,
        project_id: str,
        title: str,
        description: str = "",
        assignee: str = "",
        status: str = "pending",
        priority: str = "medium",
        start_date: str = "",
        end_date: str = "",
        estimated_hours: float = 0.0,
        dependencies: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        okr_id: str = "",
    ) -> bool:
        """Create a new task within a project.

        Args:
            task_id: Unique task identifier.
            project_id: Parent project identifier.
            title: Task title.
            description: Task description.
            assignee: Assigned agent/person.
            status: Task status (pending/in_progress/completed/blocked/cancelled).
            priority: Priority (low/medium/high/critical).
            start_date: Planned start date.
            end_date: Planned end date.
            estimated_hours: Estimated effort in hours.
            dependencies: List of dependent task IDs.
            tags: List of tag strings.
            okr_id: Linked OKR identifier.

        Returns:
            True if created, False if task_id already exists or project not found.
        """
        import json

        proj = self.conn.execute(
            "SELECT 1 FROM pm_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if proj is None:
            logger.warning("Project %s not found, cannot create task", project_id)
            return False

        cur = self.conn.execute(
            "SELECT 1 FROM pm_tasks WHERE task_id = ?", (task_id,)
        )
        if cur.fetchone() is not None:
            logger.warning("Task %s already exists", task_id)
            return False

        now = self._now()
        self.conn.execute(
            """INSERT INTO pm_tasks
               (task_id, project_id, title, description, assignee, status,
                priority, start_date, end_date, estimated_hours, actual_hours,
                dependencies, tags, okr_id, progress_pct, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                project_id,
                title,
                description,
                assignee,
                status,
                priority,
                start_date,
                end_date,
                estimated_hours,
                0.0,
                json.dumps(dependencies or []),
                json.dumps(tags or []),
                okr_id,
                0.0,
                now,
                now,
            ),
        )
        self.conn.commit()
        logger.info("Created task %s under project %s", task_id, project_id)
        return True

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a task by ID.

        Args:
            task_id: Task identifier.

        Returns:
            Task dict or None if not found.
        """
        import json

        cur = self.conn.execute(
            "SELECT * FROM pm_tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        for field in ("dependencies", "tags"):
            try:
                d[field] = json.loads(d.get(field, "[]"))
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        return d

    def list_tasks(
        self,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filters.

        Args:
            project_id: Filter by project.
            status: Filter by status.
            assignee: Filter by assignee.

        Returns:
            List of task dicts.
        """
        import json

        conditions: list = []
        params: list = []
        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        if assignee is not None:
            conditions.append("assignee = ?")
            params.append(assignee)

        query = "SELECT * FROM pm_tasks"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at"

        cur = self.conn.execute(query, params)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            for field in ("dependencies", "tags"):
                try:
                    d[field] = json.loads(d.get(field, "[]"))
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
            results.append(d)
        return results

    def update_task_status(
        self,
        task_id: str,
        new_status: str,
        actual_hours: Optional[float] = None,
    ) -> bool:
        """Update a task's status with auto-progress tracking and OKR cascading.

        Args:
            task_id: Task to update.
            new_status: New status value.
            actual_hours: Optional actual hours logged.

        Returns:
            True if updated, False if task not found.
        """
        cur = self.conn.execute(
            "SELECT * FROM pm_tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("Task %s not found", task_id)
            return False

        progress_map = {
            "pending": 0.0,
            "in_progress": 50.0,
            "completed": 100.0,
            "blocked": 0.0,
            "cancelled": 0.0,
        }
        progress = progress_map.get(new_status, 0.0)

        completed_at = ""
        if new_status == "completed":
            completed_at = self._now()

        if actual_hours is not None:
            self.conn.execute(
                "UPDATE pm_tasks SET status = ?, progress_pct = ?, "
                "actual_hours = ?, completed_at = ?, updated_at = ? "
                "WHERE task_id = ?",
                (new_status, progress, actual_hours, completed_at, self._now(), task_id),
            )
        else:
            self.conn.execute(
                "UPDATE pm_tasks SET status = ?, progress_pct = ?, "
                "completed_at = ?, updated_at = ? WHERE task_id = ?",
                (new_status, progress, completed_at, self._now(), task_id),
            )

        # Cascade: update project status when all tasks are done
        project_id = row["project_id"]
        if new_status == "completed":
            self._recalculate_project_progress(project_id)

        self.conn.commit()
        logger.info("Task %s status updated to %s", task_id, new_status)
        return True

    def _recalculate_project_progress(self, project_id: str) -> None:
        """Recalculate and update project status based on task completion."""
        cur = self.conn.execute(
            "SELECT status FROM pm_tasks WHERE project_id = ?", (project_id,)
        )
        task_statuses = [r["status"] for r in cur.fetchall()]

        if not task_statuses:
            return

        all_done = all(s == "completed" for s in task_statuses)
        any_active = any(s == "in_progress" for s in task_statuses)

        if all_done:
            new_status = "completed"
        elif any_active:
            new_status = "active"
        else:
            new_status = "initialized"

        self.conn.execute(
            "UPDATE pm_projects SET status = ?, updated_at = ? WHERE project_id = ?",
            (new_status, self._now(), project_id),
        )

    def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID.

        Args:
            task_id: Task to delete.

        Returns:
            True if deleted, False if not found.
        """
        cur = self.conn.execute(
            "SELECT project_id FROM pm_tasks WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("Task %s not found", task_id)
            return False

        self.conn.execute("DELETE FROM pm_tasks WHERE task_id = ?", (task_id,))
        self.conn.commit()
        self._recalculate_project_progress(row["project_id"])
        logger.info("Deleted task %s", task_id)
        return True

    def get_task_progress(self, project_id: str) -> Dict[str, Any]:
        """Get aggregated task progress for a project.

        Args:
            project_id: Project identifier.

        Returns:
            Dict with task counts, progress percentage, and hour tracking.
        """
        tasks = self.list_tasks(project_id=project_id)
        total = len(tasks)
        if total == 0:
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "in_progress_tasks": 0,
                "pending_tasks": 0,
                "blocked_tasks": 0,
                "progress_percentage": 0.0,
                "total_estimated_hours": 0.0,
                "total_actual_hours": 0.0,
            }

        completed = sum(1 for t in tasks if t["status"] == "completed")
        in_progress = sum(1 for t in tasks if t["status"] == "in_progress")
        pending = sum(1 for t in tasks if t["status"] == "pending")
        blocked = sum(1 for t in tasks if t["status"] == "blocked")
        total_est = sum(t["estimated_hours"] for t in tasks)
        total_act = sum(t["actual_hours"] for t in tasks)

        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "pending_tasks": pending,
            "blocked_tasks": blocked,
            "progress_percentage": round((completed / total) * 100, 2),
            "total_estimated_hours": total_est,
            "total_actual_hours": total_act,
        }

    def get_overdue_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        """Get tasks past their end date that are not completed or cancelled.

        Args:
            project_id: Project identifier.

        Returns:
            List of overdue task dicts.
        """
        today = datetime.now().date()
        tasks = self.list_tasks(project_id=project_id)
        overdue = []
        for task in tasks:
            if task["status"] in ("completed", "cancelled"):
                continue
            if task["end_date"]:
                try:
                    end = datetime.strptime(task["end_date"], "%Y-%m-%d").date()
                    if end < today:
                        overdue.append(task)
                except ValueError:
                    continue
        return overdue

    def get_upcoming_tasks(
        self, project_id: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get tasks due within the next N days.

        Args:
            project_id: Project identifier.
            days: Number of days to look ahead.

        Returns:
            Sorted list of upcoming task dicts.
        """
        today = datetime.now().date()
        future = today + timedelta(days=days)
        tasks = self.list_tasks(project_id=project_id)
        upcoming = []
        for task in tasks:
            if task["status"] in ("completed", "cancelled"):
                continue
            if task["end_date"]:
                try:
                    end = datetime.strptime(task["end_date"], "%Y-%m-%d").date()
                    if today <= end <= future:
                        upcoming.append(task)
                except ValueError:
                    continue
        return sorted(upcoming, key=lambda t: t["end_date"])

    # ─── Resource CRUD ───────────────────────────────────────────────

    def add_resource(
        self,
        resource_id: str,
        name: str,
        resource_type: str = "human",
        capacity: float = 0.0,
        skills: Optional[List[str]] = None,
        cost_per_hour: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a new resource to the pool.

        Args:
            resource_id: Unique resource identifier.
            name: Resource display name.
            resource_type: Type (human/compute/storage/network/license/other).
            capacity: Total capacity units.
            skills: List of skill strings.
            cost_per_hour: Cost per hour of usage.
            metadata: Additional metadata dict.

        Returns:
            True if added, False if resource_id already exists.
        """
        import json

        cur = self.conn.execute(
            "SELECT 1 FROM pm_resources WHERE resource_id = ?", (resource_id,)
        )
        if cur.fetchone() is not None:
            logger.warning("Resource %s already exists", resource_id)
            return False

        now = self._now()
        self.conn.execute(
            """INSERT INTO pm_resources
               (resource_id, name, resource_type, status, capacity,
                used_capacity, skills, cost_per_hour, metadata,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                resource_id,
                name,
                resource_type,
                "available",
                capacity,
                0.0,
                json.dumps(skills or []),
                cost_per_hour,
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        self.conn.commit()
        logger.info("Added resource %s (%s)", resource_id, name)
        return True

    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a resource by ID.

        Args:
            resource_id: Resource identifier.

        Returns:
            Resource dict or None if not found.
        """
        import json

        cur = self.conn.execute(
            "SELECT * FROM pm_resources WHERE resource_id = ?", (resource_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        for field in ("skills",):
            try:
                d[field] = json.loads(d.get(field, "[]"))
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        try:
            d["metadata"] = json.loads(d.get("metadata", "{}"))
        except (json.JSONDecodeError, TypeError):
            d["metadata"] = {}
        return d

    def list_resources(
        self,
        resource_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List resources with optional filters.

        Args:
            resource_type: Filter by resource type.
            status: Filter by status.

        Returns:
            List of resource dicts.
        """
        import json

        conditions: list = []
        params: list = []
        if resource_type is not None:
            conditions.append("resource_type = ?")
            params.append(resource_type)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)

        query = "SELECT * FROM pm_resources"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at"

        cur = self.conn.execute(query, params)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            for field in ("skills",):
                try:
                    d[field] = json.loads(d.get(field, "[]"))
                except (json.JSONDecodeError, TypeError):
                    d[field] = []
            try:
                d["metadata"] = json.loads(d.get("metadata", "{}"))
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = {}
            results.append(d)
        return results

    def update_resource_status(self, resource_id: str, new_status: str) -> bool:
        """Update a resource's status.

        Args:
            resource_id: Resource identifier.
            new_status: New status value.

        Returns:
            True if updated, False if not found.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM pm_resources WHERE resource_id = ?", (resource_id,)
        )
        if cur.fetchone() is None:
            logger.warning("Resource %s not found", resource_id)
            return False

        self.conn.execute(
            "UPDATE pm_resources SET status = ?, updated_at = ? WHERE resource_id = ?",
            (new_status, self._now(), resource_id),
        )
        self.conn.commit()
        logger.info("Resource %s status updated to %s", resource_id, new_status)
        return True

    def delete_resource(self, resource_id: str) -> bool:
        """Delete a resource by ID.

        Args:
            resource_id: Resource identifier.

        Returns:
            True if deleted, False if not found.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM pm_resources WHERE resource_id = ?", (resource_id,)
        )
        if cur.fetchone() is None:
            logger.warning("Resource %s not found", resource_id)
            return False

        self.conn.execute(
            "DELETE FROM pm_allocations WHERE resource_id = ?", (resource_id,)
        )
        self.conn.execute(
            "DELETE FROM pm_resources WHERE resource_id = ?", (resource_id,)
        )
        self.conn.commit()
        logger.info("Deleted resource %s", resource_id)
        return True

    # ─── Allocation / Release ────────────────────────────────────────

    def allocate_resource(
        self,
        resource_id: str,
        project_id: str,
        task_id: str = "",
        capacity: float = 1.0,
        start_time: str = "",
        end_time: str = "",
    ) -> Optional[str]:
        """Allocate a resource to a project/task.

        Args:
            resource_id: Resource to allocate.
            project_id: Target project.
            task_id: Optional target task.
            capacity: Capacity units to allocate.
            start_time: Allocation start (ISO format).
            end_time: Allocation end (ISO format).

        Returns:
            Allocation ID if successful, None otherwise.
        """
        import json

        resource = self.get_resource(resource_id)
        if resource is None:
            logger.warning("Resource %s not found", resource_id)
            return None

        if resource["status"] not in ("available", "in_use"):
            logger.warning("Resource %s is not available (status: %s)", resource_id, resource["status"])
            return None

        if resource["used_capacity"] + capacity > resource["capacity"]:
            logger.warning("Resource %s has insufficient capacity", resource_id)
            return None

        if not start_time:
            start_time = datetime.now().isoformat()
        if not end_time:
            end_time = (datetime.now() + timedelta(days=7)).isoformat()

        allocation_id = f"ALLOC_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        now = self._now()

        self.conn.execute(
            """INSERT INTO pm_allocations
               (allocation_id, resource_id, project_id, task_id,
                allocated_capacity, start_time, end_time, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                allocation_id,
                resource_id,
                project_id,
                task_id,
                capacity,
                start_time,
                end_time,
                "active",
                now,
            ),
        )

        new_used = resource["used_capacity"] + capacity
        new_status = "in_use" if new_used >= resource["capacity"] else "available"
        self.conn.execute(
            "UPDATE pm_resources SET used_capacity = ?, status = ?, updated_at = ? "
            "WHERE resource_id = ?",
            (new_used, new_status, now, resource_id),
        )

        self.conn.commit()
        logger.info(
            "Allocated resource %s to project %s (allocation: %s)",
            resource_id, project_id, allocation_id,
        )
        return allocation_id

    def release_resource(self, allocation_id: str) -> bool:
        """Release a resource allocation.

        Args:
            allocation_id: Allocation to release.

        Returns:
            True if released, False if not found.
        """
        cur = self.conn.execute(
            "SELECT * FROM pm_allocations WHERE allocation_id = ?", (allocation_id,)
        )
        alloc = cur.fetchone()
        if alloc is None:
            logger.warning("Allocation %s not found", allocation_id)
            return False

        resource_id = alloc["resource_id"]
        allocated_capacity = alloc["allocated_capacity"]

        self.conn.execute(
            "UPDATE pm_allocations SET status = 'released' WHERE allocation_id = ?",
            (allocation_id,),
        )

        resource = self.get_resource(resource_id)
        if resource is not None:
            new_used = max(0.0, resource["used_capacity"] - allocated_capacity)
            new_status = "available" if new_used < resource["capacity"] else "in_use"
            self.conn.execute(
                "UPDATE pm_resources SET used_capacity = ?, status = ?, updated_at = ? "
                "WHERE resource_id = ?",
                (new_used, new_status, self._now(), resource_id),
            )

        self.conn.commit()
        logger.info("Released allocation %s", allocation_id)
        return True

    def get_project_resources(self, project_id: str) -> List[Dict[str, Any]]:
        """Get all active resource allocations for a project.

        Args:
            project_id: Project identifier.

        Returns:
            List of dicts with resource and allocation data.
        """
        cur = self.conn.execute(
            """SELECT a.*, r.name, r.resource_type, r.skills, r.capacity
               FROM pm_allocations a
               JOIN pm_resources r ON a.resource_id = r.resource_id
               WHERE a.project_id = ? AND a.status = 'active'
               ORDER BY a.created_at""",
            (project_id,),
        )
        import json

        results = []
        for row in cur.fetchall():
            d = dict(row)
            try:
                d["skills"] = json.loads(d.get("skills", "[]"))
            except (json.JSONDecodeError, TypeError):
                d["skills"] = []
            results.append(d)
        return results

    def get_resource_utilization(self) -> Dict[str, Any]:
        """Get aggregate resource utilization statistics.

        Returns:
            Dict with counts by status and average utilization.
        """
        resources = self.list_resources()
        total = len(resources)
        if total == 0:
            return {
                "total_resources": 0,
                "available_resources": 0,
                "in_use_resources": 0,
                "maintenance_resources": 0,
                "reserved_resources": 0,
                "unavailable_resources": 0,
                "average_utilization": 0.0,
                "resources_detail": [],
            }

        counts: Dict[str, int] = {
            "available": 0,
            "in_use": 0,
            "maintenance": 0,
            "reserved": 0,
            "unavailable": 0,
        }
        total_util = 0.0
        details = []

        for r in resources:
            util = (r["used_capacity"] / r["capacity"] * 100) if r["capacity"] > 0 else 0.0
            total_util += util
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            details.append(
                {
                    "resource_id": r["resource_id"],
                    "name": r["name"],
                    "type": r["resource_type"],
                    "status": r["status"],
                    "utilization": round(util, 2),
                    "used_capacity": r["used_capacity"],
                    "total_capacity": r["capacity"],
                }
            )

        return {
            "total_resources": total,
            "available_resources": counts.get("available", 0),
            "in_use_resources": counts.get("in_use", 0),
            "maintenance_resources": counts.get("maintenance", 0),
            "reserved_resources": counts.get("reserved", 0),
            "unavailable_resources": counts.get("unavailable", 0),
            "average_utilization": round(total_util / total, 2),
            "resources_detail": details,
        }

    # ─── Overall Status ─────────────────────────────────────────────

    def get_overall_status(self) -> Dict[str, Any]:
        """Get overall PMO status across all projects and resources.

        Returns:
            Dict with project counts, resource utilization, and summaries.
        """
        projects = self.list_projects()
        total = len(projects)
        active = sum(1 for p in projects if p["status"] == "active")
        completed = sum(1 for p in projects if p["status"] == "completed")

        resource_util = self.get_resource_utilization()

        total_tasks = 0
        total_completed = 0
        project_summaries = []

        for proj in projects:
            progress = self.get_task_progress(proj["project_id"])
            total_tasks += progress["total_tasks"]
            total_completed += progress["completed_tasks"]
            project_summaries.append(
                {
                    "project_id": proj["project_id"],
                    "project_name": proj["project_name"],
                    "status": proj["status"],
                    "progress": progress["progress_percentage"],
                    "tasks": progress["total_tasks"],
                    "completed": progress["completed_tasks"],
                }
            )

        return {
            "total_projects": total,
            "active_projects": active,
            "completed_projects": completed,
            "total_tasks": total_tasks,
            "total_completed_tasks": total_completed,
            "overall_progress": (
                round((total_completed / total_tasks) * 100, 2) if total_tasks > 0 else 0.0
            ),
            "resource_utilization": resource_util,
            "project_summaries": project_summaries,
        }

    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
        logger.info("PMProjectDB connection closed")
