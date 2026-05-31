"""
Spider Diary v1.0.0 — Daily operations report generation engine.

Usage:
    from spider_diary import DiaryEngine
    engine = DiaryEngine(base_path="/your/project")
    result = engine.run_daily_ops()
"""

__version__ = "1.0.0"

import sys
import os

# Support both package import and flat (dev) import
_pkg_root = os.path.dirname(os.path.abspath(__file__))
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from core.system_checker import SystemChecker
from core.project_reader import ProjectReader
from report.report_generator import ReportGenerator
from report.kanban_sync import KanbanSyncer
from storage.project_db import ProjectDB
from engine import DiaryEngine

from remind import BlockerStore
from remind.remind_engine import RemindEngine

# Fault tolerance modules
from core.protocol_fault_tolerance import ProtocolFaultTolerance
from core.process_fault_tolerance import ProcessFaultTolerance
from core.container_fault_tolerance import ContainerFaultTolerance
from core.service_mesh_fault_tolerance import ServiceMeshFaultTolerance
from core.business_continuity import BusinessContinuity

# Performance modules
from core.perf_baseline import PerfBaseline
from core.performance_diagnosis import PerformanceDiagnosis
from core.redundancy_metrics import RedundancyMetrics

__all__ = [
    # Core
    "DiaryEngine",
    "SystemChecker",
    "ProjectReader",
    "ReportGenerator",
    "KanbanSyncer",
    "ProjectDB",
    "BlockerStore",
    "RemindEngine",
    # Fault tolerance
    "ProtocolFaultTolerance",
    "ProcessFaultTolerance",
    "ContainerFaultTolerance",
    "ServiceMeshFaultTolerance",
    "BusinessContinuity",
    # Performance
    "PerfBaseline",
    "PerformanceDiagnosis",
    "RedundancyMetrics",
]
