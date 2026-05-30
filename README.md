# 🕷️ Spider Diary

**Daily operations report generation engine with project tracking, kanban, and reminder system.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://github.com/freeword26/spider-diary/blob/main/Dockerfile)

## Features

- **System Health Monitoring** — Disk, memory, CPU, and process checks with configurable thresholds
- **Project & Task Management** — SQLite-backed CRUD with milestones, OKR tracking, and auto-progress
- **Kanban Board** — JSON and Markdown export with 5-column workflow (Backlog → Doing → Review → Done/Blocked)
- **Daily Operations Report** — Auto-generated Markdown reports with system status, project overview, and actionable advice
- **Blocker Tracking** — JSON-persisted blocker store with severity levels, resolution tracking, and Markdown reminders
- **Automatic Cleanup** — 3-tier storage management (Hot 7d → Warm 30d → Cold 90d → Delete)
- **Docker Ready** — Single-command deployment with Docker Compose

## Quick Start

### Install

```bash
pip install -e .
```

### CLI Usage

```bash
# Run full daily operations
spider-diary run

# Quick system check
spider-diary check

# Generate report only
spider-diary report

# Initialize database with sample data
spider-diary init

# View system status
spider-diary status
```

### Docker Deployment

```bash
# Build and run
docker-compose up -d

# Execute commands
docker exec spider-diary spider-diary status
docker exec spider-diary spider-diary run
```

### Python API

```python
from spider_diary import DiaryEngine

engine = DiaryEngine(base_path="/your/project")
result = engine.run_daily_ops()

print(result["status"])        # ok / warning / critical
print(result["report_path"])   # Path to generated report
print(result["kanban_path"])   # Path to generated kanban
```

## Project Structure

```
spider_diary/
├── cli/main.py                  # CLI entry point (6 commands)
├── engine.py                    # DiaryEngine — main orchestrator
├── cleanup.py                   # CleanupScheduler — 3-tier storage cleanup
├── core/
│   ├── system_checker.py        # SystemChecker — health monitoring
│   ├── project_reader.py        # ProjectReader — project/task/OKR queries
│   ├── daily_monitor.py         # DailyMonitor — model/router monitoring
│   └── cleanup_scheduler.py     # File cleanup with age-based tiers
├── report/
│   ├── report_generator.py      # ReportGenerator — daily ops report
│   ├── kanban_sync.py           # KanbanSyncer — JSON + Markdown export
│   └── pm_report_generator.py   # PMReportGenerator — 5 report types
├── storage/
│   ├── project_db.py            # ProjectDB — lightweight SQLite storage
│   └── pm_project_db.py         # PMProjectDB — full PM with resources
├── remind/
│   ├── blocker_store.py         # BlockerStore — JSON-persisted blockers
│   └── remind_engine.py         # RemindEngine — 5 automated scanners
└── tests/
    ├── test_core.py             # 63 unit tests
    └── test_cleanup.py          # 25 cleanup tests
```

## CLI Commands (12 total)

| Command | Description |
|---------|-------------|
| `spider-diary run` | Full daily ops: check + report + kanban |
| `spider-diary check` | Quick system + project check |
| `spider-diary report` | Generate daily ops report |
| `spider-diary kanban` | Generate kanban board files |
| `spider-diary init` | Initialize database + sample data |
| `spider-diary status` | Terminal status panel |
| `spider-diary cleanup` | Run cleanup scheduler |
| `spider-diary monitor` | Run monitoring suite |
| `spider-diary pm-init <id> <name>` | Initialize a new project |
| `spider-diary pm-task <id> <desc>` | Create a task |
| `spider-diary pm-status` | PMO status panel |
| `spider-diary pm-report [type]` | Generate PM reports |

## Dependencies

- Python 3.10+
- psutil >= 5.9.0
- rich >= 13.0.0

## Testing

```bash
python -m pytest tests/ -v
# 88 tests, all passing
```

## License

MIT License — see [LICENSE](LICENSE) for details.
