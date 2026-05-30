import argparse
import json
import logging
import os
import pathlib
import sys

SRC_PARENT = pathlib.Path(__file__).resolve().parents[2]
if str(SRC_PARENT) not in sys.path:
    sys.path.insert(0, str(SRC_PARENT))

from spider_diary.engine import DiaryEngine

logger = logging.getLogger("spider_diary.cli")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import print as rprint

    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="spider-diary",
        description="Spider Diary — Daily ops report generation engine",
    )
    subparsers = parser.add_subparsers(dest="command")

    for cmd in ("run", "check", "report", "kanban", "init", "status", "monitor", "cleanup"):
        sub = subparsers.add_parser(cmd, help=f"{cmd} command")
        if cmd != "status":
            sub.add_argument("--base-path", "-b", default=None, help="Base project path")
            sub.add_argument("--output-dir", "-o", default=None, help="Output directory for reports")
            sub.add_argument("--db-path", "-d", default=None, help="Database path")
        else:
            sub.add_argument("--base-path", "-b", default=None, help="Base project path")
            sub.add_argument("--db-path", "-d", default=None, help="Database path")
        sub.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
        sub.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")

    return parser


def _make_engine(args):
    config = {}
    if getattr(args, "base_path", None):
        config["disk_path"] = args.base_path
    if getattr(args, "output_dir", None):
        config["output_dir"] = args.output_dir
    if getattr(args, "db_path", None):
        config["db_path"] = args.db_path
    base_path = getattr(args, "base_path", None)
    return DiaryEngine(base_path=base_path, config=config or None)


def _print_result(result, as_json=False):
    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        return
    if HAS_RICH:
        _print_rich(result)
    else:
        _print_plain(result)


def _print_plain(result):
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for k2, v2 in value.items():
                print(f"  {k2}: {v2}")
        elif isinstance(value, list):
            print(f"{key}:")
            for item in value:
                print(f"  - {item}")
        else:
            print(f"{key}: {value}")


def _print_rich(result):
    console = Console()
    table = Table(title="Spider Diary Result", show_lines=True)
    table.add_column("Key", style="bold cyan")
    table.add_column("Value", style="white")
    for key, value in result.items():
        if isinstance(value, dict):
            inner = "\n".join(f"{k}: {v}" for k, v in value.items())
            table.add_row(key, inner)
        elif isinstance(value, list):
            inner = "\n".join(str(item) for item in value)
            table.add_row(key, inner if inner else "(empty)")
        else:
            table.add_row(key, str(value))
    console.print(table)


def cmd_run(args):
    engine = _make_engine(args)
    result = engine.run_daily_ops()
    _print_result(result, as_json=args.as_json)


def cmd_check(args):
    engine = _make_engine(args)
    result = engine.run_quick_check()
    _print_result(result, as_json=args.as_json)


def cmd_report(args):
    engine = _make_engine(args)
    quick = engine.run_quick_check()
    issues = engine.project_reader.get_issues()
    project_data = quick["project_data"]
    report_data = engine.report_generator.generate_and_save(
        quick["system_data"], project_data, issues
    )
    result = {
        "report_path": report_data.get("report_path"),
        "content": report_data.get("content", "")[:500] + "...",
        "timestamp": report_data.get("timestamp"),
        "status": "ok",
    }
    _print_result(result, as_json=args.as_json)


def cmd_kanban(args):
    engine = _make_engine(args)
    tasks_by_status = {}
    for status in ("Backlog", "Doing", "Review", "Done", "Blocked"):
        tasks_by_status[status.lower()] = engine.project_reader.get_tasks_by_status(status)
    project_stats = engine.project_reader.get_stats()
    kanban_data = {"stats": project_stats, "tasks": tasks_by_status}
    kanban_path = engine.kanban_syncer.sync(kanban_data)
    md_path = engine.kanban_syncer.sync_markdown(kanban_data)
    result = {"kanban_json_path": kanban_path, "kanban_md_path": md_path, "status": "ok"}
    _print_result(result, as_json=args.as_json)


def cmd_init(args):
    engine = _make_engine(args)
    now = __import__("datetime").datetime.now().isoformat()
    sample_projects = [
        ("PROJ-001", "spidermax_room", "Active", "agent-main", "Main AI agent platform", now),
        ("PROJ-002", "Data Pipeline", "Active", "agent-data", "ETL and data processing", now),
        ("PROJ-003", "Legacy Archive", "Archived", "agent-ops", "Archived projects", now),
    ]
    sample_tasks = [
        ("TASK-001", "PROJ-001", "Implement CLI interface", "agent-ops", "Done", "normal", now),
        ("TASK-002", "PROJ-001", "Write documentation", "agent-ops", "Doing", "high", now),
        ("TASK-003", "PROJ-001", "Add unit tests", "agent-ops", "Backlog", "normal", now),
        ("TASK-004", "PROJ-002", "Setup database", "agent-data", "Done", "high", now),
        ("TASK-005", "PROJ-002", "Build pipeline", "agent-data", "Review", "high", now),
        ("TASK-006", "PROJ-002", "Deploy to staging", "agent-ops", "Backlog", "low", now),
        ("TASK-007", "PROJ-003", "Archive old files", "agent-ops", "Blocked", "low", now),
    ]
    conn = engine.project_reader._connect()
    conn.executemany("INSERT OR IGNORE INTO project_meta VALUES (?,?,?,?,?,?)", sample_projects)
    conn.executemany(
        "INSERT OR IGNORE INTO task_board (task_id, project_id, description, assignee, kanban_status, priority, created_date) VALUES (?,?,?,?,?,?,?)",
        sample_tasks,
    )
    conn.commit()
    conn.close()
    result = {"status": "ok", "message": "Database initialised with sample data"}
    _print_result(result, as_json=args.as_json)


def cmd_status(args):
    engine = _make_engine(args)
    summary = engine.get_summary()
    if args.as_json:
        quick = engine.run_quick_check()
        _print_result(quick, as_json=True)
    else:
        if HAS_RICH:
            Console().print(Panel(summary, title="Spider Diary Status"))
        else:
            print(summary)


def cmd_cleanup(args):
    """Run cleanup scheduler (3-tier storage management)."""
    from spider_diary.core.cleanup_scheduler import CleanupScheduler

    root = pathlib.Path(args.base_path) if args.base_path else pathlib.Path.cwd()
    scheduler = CleanupScheduler(project_root=root)
    summary = scheduler.run_cleanup()
    _print_result(summary, as_json=args.as_json)


def cmd_monitor(args):
    """Run full monitoring suite (models, router, docker)."""
    from spider_diary.core.daily_monitor import DailyMonitor

    project_root = pathlib.Path(args.base_path) if args.base_path else None
    monitor = DailyMonitor(project_root=project_root)
    results = monitor.run_full_check()
    _print_result(results, as_json=args.as_json)


COMMANDS = {
    "run": cmd_run,
    "check": cmd_check,
    "report": cmd_report,
    "kanban": cmd_kanban,
    "init": cmd_init,
    "status": cmd_status,
    "cleanup": cmd_cleanup,
    "monitor": cmd_monitor,
}


def main():
    parser = _build_parser()
    args = parser.parse_args()

    if getattr(args, "verbose", False):
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)


if __name__ == "__main__":
    main()
