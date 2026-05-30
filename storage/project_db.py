"""Project database storage module.

Provides SQLite persistence for projects, tasks, and OKRs.
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ProjectDB:
    """SQLite-backed storage for project, task, and OKR data."""

    _CREATE_TABLES = [
        """
        CREATE TABLE IF NOT EXISTS project_meta (
            project_id TEXT PRIMARY KEY,
            project_name TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            owner_agent TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_date TEXT DEFAULT '',
            linked_okr_id TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS task_board (
            task_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            description TEXT DEFAULT '',
            assignee TEXT DEFAULT '',
            kanban_status TEXT DEFAULT 'todo',
            priority TEXT DEFAULT 'normal',
            created_date TEXT DEFAULT '',
            completed_date TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS okr_master (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            confidence INTEGER DEFAULT 5,
            owner TEXT DEFAULT ''
        )
        """,
    ]

    def __init__(self, db_path=None):
        """Initialize ProjectDB.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ./project.db in the current working directory.
        """
        if db_path is None:
            db_path = Path("project.db")
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_tables()

    def _ensure_tables(self):
        """Create tables if they do not exist."""
        for stmt in self._CREATE_TABLES:
            self.conn.execute(stmt)
        self.conn.commit()

    def _now(self):
        """Return current local time as an ISO-8601 string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_stats(self):
        """Return aggregate statistics.

        Returns:
            dict with counts for projects, tasks, done, doing, active
            and progress percentage as progress_pct.
        """
        cur = self.conn.execute("SELECT COUNT(*) AS cnt FROM project_meta")
        projects = cur.fetchone()["cnt"]

        cur = self.conn.execute("SELECT COUNT(*) AS cnt FROM task_board")
        tasks = cur.fetchone()["cnt"]

        cur = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM task_board WHERE kanban_status='done'"
        )
        done = cur.fetchone()["cnt"]

        cur = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM task_board WHERE kanban_status='doing'"
        )
        doing = cur.fetchone()["cnt"]

        cur = self.conn.execute(
            "SELECT COUNT(*) AS cnt FROM project_meta WHERE status='active'"
        )
        active = cur.fetchone()["cnt"]

        progress_pct = round(done / tasks * 100, 1) if tasks > 0 else 0.0

        return {
            "projects": projects,
            "tasks": tasks,
            "done": done,
            "doing": doing,
            "active": active,
            "progress_pct": progress_pct,
        }

    def get_all_projects(self):
        """Return all projects.

        Returns:
            list of dicts representing each project row.
        """
        cur = self.conn.execute("SELECT * FROM project_meta ORDER BY created_date")
        return [dict(row) for row in cur.fetchall()]

    def get_tasks(self, project_id=None, status=None, assignee=None):
        """Return tasks with optional filters.

        Args:
            project_id: Filter by project_id.
            status: Filter by kanban_status.
            assignee: Filter by assignee.

        Returns:
            list of dicts representing each matching task row.
        """
        conditions = []
        params = []
        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)
        if status is not None:
            conditions.append("kanban_status = ?")
            params.append(status)
        if assignee is not None:
            conditions.append("assignee = ?")
            params.append(assignee)

        query = "SELECT * FROM task_board"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_date"

        cur = self.conn.execute(query, params)
        return [dict(row) for row in cur.fetchall()]

    def get_all_okrs(self):
        """Return all OKRs.

        Returns:
            list of dicts representing each OKR row.
        """
        cur = self.conn.execute("SELECT * FROM okr_master ORDER BY id")
        return [dict(row) for row in cur.fetchall()]

    def create_project(self, project_id, name, **kwargs):
        """Create a new project.

        Args:
            project_id: Unique project identifier.
            name: Project display name.
            **kwargs: Optional fields (status, owner_agent, description,
                      linked_okr_id).

        Returns:
            bool: True if created, False if project_id already exists.
        """
        created_date = datetime.now().strftime("%Y-%m-%d")
        if not self.get_all_projects():  # ensure tables exist on first call
            pass  # tables already ensured in __init__

        # Check existence
        cur = self.conn.execute(
            "SELECT 1 FROM project_meta WHERE project_id = ?", (project_id,)
        )
        if cur.fetchone() is not None:
            logger.warning("Project %s already exists", project_id)
            return False

        self.conn.execute(
            """INSERT INTO project_meta
               (project_id, project_name, status, owner_agent, description,
                created_date, linked_okr_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                project_id,
                name,
                kwargs.get("status", "active"),
                kwargs.get("owner_agent", ""),
                kwargs.get("description", ""),
                created_date,
                kwargs.get("linked_okr_id", ""),
            ),
        )
        self.conn.commit()
        logger.info("Created project %s (%s)", project_id, name)
        return True

    def create_task(self, task_id, project_id, description, **kwargs):
        """Create a new task.

        Args:
            task_id: Unique task identifier.
            project_id: Parent project identifier.
            description: Task description.
            **kwargs: Optional fields (assignee, kanban_status, priority).

        Returns:
            bool: True if created, False if task_id already exists.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM task_board WHERE task_id = ?", (task_id,)
        )
        if cur.fetchone() is not None:
            logger.warning("Task %s already exists", task_id)
            return False

        self.conn.execute(
            """INSERT INTO task_board
               (task_id, project_id, description, assignee, kanban_status,
                priority, created_date, completed_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id,
                project_id,
                description,
                kwargs.get("assignee", ""),
                kwargs.get("kanban_status", "todo"),
                kwargs.get("priority", "normal"),
                self._now(),
                "",
            ),
        )
        self.conn.commit()
        logger.info("Created task %s under project %s", task_id, project_id)
        return True

    def update_task_status(self, task_id, new_status):
        """Update a task's kanban status with cascading side effects.

        Updates the owning project's progress state and linked OKR confidence
        when a task reaches 'done'.

        Args:
            task_id: Task to update.
            new_status: New kanban_status value.

        Returns:
            bool: True if updated, False if task not found.
        """
        cur = self.conn.execute(
            "SELECT * FROM task_board WHERE task_id = ?", (task_id,)
        )
        row = cur.fetchone()
        if row is None:
            logger.warning("Task %s not found", task_id)
            return False

        completed_date = ""
        if new_status == "done":
            completed_date = self._now()

        self.conn.execute(
            "UPDATE task_board SET kanban_status = ?, completed_date = ? "
            "WHERE task_id = ?",
            (new_status, completed_date, task_id),
        )

        # Cascade: update project progress
        project_id = row["project_id"]
        if new_status == "done":
            self.conn.execute(
                "UPDATE project_meta SET status = 'active' "
                "WHERE project_id = ? AND status = 'completed'",
                (project_id,),
            )

        # Cascade: update linked OKR confidence
        cur = self.conn.execute(
            "SELECT linked_okr_id FROM project_meta WHERE project_id = ?",
            (project_id,),
        )
        meta = cur.fetchone()
        if meta and meta["linked_okr_id"]:
            okr_id = meta["linked_okr_id"]
            if new_status == "done":
                self.conn.execute(
                    "UPDATE okr_master SET confidence = MIN(confidence + 1, 10) "
                    "WHERE id = ?",
                    (okr_id,),
                )
            else:
                self.conn.execute(
                    "UPDATE okr_master SET confidence = MAX(confidence - 1, 0) "
                    "WHERE id = ? AND (SELECT kanban_status FROM task_board "
                    "WHERE task_id = ?) = 'done'",
                    (okr_id, task_id),
                )

        self.conn.commit()
        logger.info("Task %s status updated to %s", task_id, new_status)
        return True

    def delete_task(self, task_id):
        """Delete a task by ID.

        Args:
            task_id: Task to delete.

        Returns:
            bool: True if deleted, False if task not found.
        """
        cur = self.conn.execute(
            "SELECT 1 FROM task_board WHERE task_id = ?", (task_id,)
        )
        if cur.fetchone() is None:
            logger.warning("Task %s not found", task_id)
            return False

        self.conn.execute("DELETE FROM task_board WHERE task_id = ?", (task_id,))
        self.conn.commit()
        logger.info("Deleted task %s", task_id)
        return True

    def get_agent_tasks(self, assignee):
        """Return all tasks assigned to a given agent.

        Args:
            assignee: Agent identifier string.

        Returns:
            list of dicts representing matching task rows.
        """
        cur = self.conn.execute(
            "SELECT * FROM task_board WHERE assignee = ? ORDER BY created_date",
            (assignee,),
        )
        return [dict(row) for row in cur.fetchall()]

    def close(self):
        """Close the database connection."""
        self.conn.close()
        logger.info("Database connection closed")
