"""
spider_diary / Spider Diary v1.0.0
每日运维报告生成引擎

独立包：可从 spidermax_room (MAX ROOM / Spider MAX ROOM) 中单独安装使用
pip install spider-diary

使用:
    from spider_diary import DiaryEngine
    engine = DiaryEngine(base_path="/your/project")
    result = engine.run_daily_ops()
    print(result.report_path)
"""

__version__ = "1.0.0"

from .core.system_checker import SystemChecker
from .core.project_reader import ProjectReader
from .report.report_generator import ReportGenerator
from .report.kanban_sync import KanbanSyncer
from .storage.project_db import ProjectDB
from .engine import DiaryEngine

from .remind import BlockerStore
from .remind.remind_engine import RemindEngine

__all__ = [
    "DiaryEngine",
    "SystemChecker",
    "ProjectReader",
    "ReportGenerator",
    "KanbanSyncer",
    "ProjectDB",
    "BlockerStore",
    "RemindEngine",
]
