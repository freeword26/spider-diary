"""Reads project and task status from a SQLite database."""

import datetime
import logging
import os
import pathlib
import sqlite3

logger = logging.getLogger(__name__)


class ProjectReader:
    """Reads project/task status from a SQLite database.

    If no db_path is provided, looks for ``project.db`` in the current
    working directory.  The database and its tables are created
    automatically when the reader is instantiated.
    """

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = pathlib.Path(os.getcwd()) / "project.db"
        self.db_path = pathlib.Path(db_path)
        self._init_db()

    # -- public interface -------------------------------------------------

    def get_stats(self):
        """Return high-level statistics across all projects and tasks.

        Returns:
            dict with keys: projects, tasks, done, doing, active,
            progress_pct
        """
        try:
            with self._connect() as conn:
                projects = conn.execute(
                    "SELECT COUNT(*) FROM project_meta"
                ).fetchone()[0]
                tasks = conn.execute(
                    "SELECT COUNT(*) FROM task_board"
                ).fetchone()[0]
                done = conn.execute(
                    "SELECT COUNT(*) FROM task_board WHERE kanban_status='Done'"
                ).fetchone()[0]
                doing = conn.execute(
                    "SELECT COUNT(*) FROM task_board WHERE kanban_status='Doing'"
                ).fetchone()[0]
                active = conn.execute(
                    "SELECT COUNT(*) FROM project_meta WHERE status='Active'"
                ).fetchone()[0]
        except sqlite3.OperationalError:
            logger.warning("Tables missing – returning zeroed stats.")
            return {
                "projects": 0,
                "tasks": 0,
                "done": 0,
                "doing": 0,
                "active": 0,
                "progress_pct": 0.0,
            }

        progress_pct = (done / tasks * 100) if tasks else 0.0
        return {
            "projects": projects,
            "tasks": tasks,
            "done": done,
            "doing": doing,
            "active": active,
            "progress_pct": round(progress_pct, 1),
        }

    def get_all_projects(self):
        """Return a list of dicts with per-project information.

        Each dict contains: project_id, project_name, status,
        owner_agent, total_tasks, done_tasks, progress_pct.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT project_id, project_name, status, owner_agent, "
                    "description, created_date FROM project_meta"
                ).fetchall()
        except sqlite3.OperationalError:
            logger.warning("project_meta table missing – returning empty list.")
            return []

        projects = []
        for row in rows:
            pid = row[0]
            total = conn.execute(
                "SELECT COUNT(*) FROM task_board WHERE project_id=?",
                (pid,),
            ).fetchone()[0] if self._table_exists(conn, "task_board") else 0
            done = conn.execute(
                "SELECT COUNT(*) FROM task_board "
                "WHERE project_id=? AND kanban_status='Done'",
                (pid,),
            ).fetchone()[0] if self._table_exists(conn, "task_board") else 0
            pct = (done / total * 100) if total else 0.0
            projects.append(
                {
                    "project_id": row[0],
                    "project_name": row[1],
                    "status": row[2],
                    "owner_agent": row[3],
                    "total_tasks": total,
                    "done_tasks": done,
                    "progress_pct": round(pct, 1),
                }
            )
        return projects

    def get_tasks_by_status(self, status):
        """Return tasks filtered by kanban status.

        Args:
            status: one of "Backlog", "Doing", "Review", "Done", "Blocked".

        Returns:
            list of task dicts.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT task_id, project_id, description, assignee, "
                    "kanban_status, priority, created_date, completed_date "
                    "FROM task_board WHERE kanban_status=?",
                    (status,),
                ).fetchall()
        except sqlite3.OperationalError:
            logger.warning("task_board table missing – returning empty list.")
            return []

        return [
            {
                "task_id": r[0],
                "project_id": r[1],
                "description": r[2],
                "assignee": r[3],
                "kanban_status": r[4],
                "priority": r[5],
                "created_date": r[6],
                "completed_date": r[7],
            }
            for r in rows
        ]

    def get_issues(self):
        """Return a list of potential issues detected in the data.

        Detects:
            - Projects with 0 tasks.
            - Tasks in "Doing" for more than 7 days.
            - Projects with progress < 10 % and older than 30 days.

        Each issue dict contains: type, severity, project_id, description.
        """
        issues = []
        now = datetime.datetime.now()

        try:
            with self._connect() as conn:
                # Projects with 0 tasks
                if self._table_exists(conn, "task_board"):
                    proj_rows = conn.execute(
                        "SELECT project_id, project_name FROM project_meta"
                    ).fetchall()
                    for pid, pname in proj_rows:
                        count = conn.execute(
                            "SELECT COUNT(*) FROM task_board WHERE project_id=?",
                            (pid,),
                        ).fetchone()[0]
                        if count == 0:
                            issues.append(
                                {
                                    "type": "no_tasks",
                                    "severity": "warning",
                                    "project_id": pid,
                                    "description": (
                                        f"Project '{pname}' ({pid}) has 0 tasks."
                                    ),
                                }
                            )

                    # Tasks in Doing > 7 days
                    doing_rows = conn.execute(
                        "SELECT task_id, project_id, description, created_date "
                        "FROM task_board WHERE kanban_status='Doing'"
                    ).fetchall()
                    for tid, pid, desc, created in doing_rows:
                        try:
                            created_dt = datetime.datetime.fromisoformat(created)
                        except (ValueError, TypeError):
                            continue
                        if (now - created_dt).days > 7:
                            issues.append(
                                {
                                    "type": "stale_doing",
                                    "severity": "critical",
                                    "project_id": pid,
                                    "description": (
                                        f"Task '{desc}' ({tid}) has been in "
                                        f"Doing for {(now - created_dt).days} days."
                                    ),
                                }
                            )

                    # Projects with progress < 10 % and > 30 days old
                    for pid, pname in proj_rows:
                        total = conn.execute(
                            "SELECT COUNT(*) FROM task_board WHERE project_id=?",
                            (pid,),
                        ).fetchone()[0]
                        if total == 0:
                            continue
                        done = conn.execute(
                            "SELECT COUNT(*) FROM task_board "
                            "WHERE project_id=? AND kanban_status='Done'",
                            (pid,),
                        ).fetchone()[0]
                        pct = done / total * 100
                        if pct >= 10:
                            continue
                        proj_info = conn.execute(
                            "SELECT created_date FROM project_meta "
                            "WHERE project_id=?",
                            (pid,),
                        ).fetchone()
                        if proj_info and proj_info[0]:
                            try:
                                proj_dt = datetime.datetime.fromisoformat(
                                    proj_info[0]
                                )
                            except (ValueError, TypeError):
                                continue
                            if (now - proj_dt).days > 30:
                                issues.append(
                                    {
                                        "type": "slow_progress",
                                        "severity": "warning",
                                        "project_id": pid,
                                        "description": (
                                            f"Project '{pname}' ({pid}) has "
                                            f"{pct:.1f}% progress after "
                                            f"{(now - proj_dt).days} days."
                                        ),
                                    }
                                )
        except sqlite3.OperationalError:
            logger.warning("Tables missing – returning empty issues list.")

        return issues

    # -- internal helpers -------------------------------------------------

    def _connect(self):
        """Return a sqlite3 connection to the database."""
        return sqlite3.connect(str(self.db_path))

    @staticmethod
    def _table_exists(conn, name):
        """Check whether *name* is a table in the given connection."""
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        return row is not None

    def _init_db(self):
        """Create the database schema if it does not already exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_meta (
                    project_id   TEXT PRIMARY KEY,
                    project_name TEXT,
                    status       TEXT,
                    owner_agent  TEXT,
                    description  TEXT,
                    created_date TEXT
                );

                CREATE TABLE IF NOT EXISTS task_board (
                    task_id        TEXT PRIMARY KEY,
                    project_id     TEXT,
                    description    TEXT,
                    assignee       TEXT,
                    kanban_status  TEXT,
                    priority       TEXT,
                    created_date   TEXT,
                    completed_date TEXT
                );

                CREATE TABLE IF NOT EXISTS okr_master (
                    id         TEXT PRIMARY KEY,
                    title      TEXT,
                    status     TEXT,
                    confidence INTEGER,
                    owner      TEXT
                );
                """
            )
            conn.commit()
        logger.info("Database initialised at %s", self.db_path)
