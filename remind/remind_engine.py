# ============================================================
# spider_diary/remind/remind_engine.py
# 提醒引擎 —— 扫描阻塞项、生成提醒、集成到 spider_diary 报告流
# ============================================================
"""Reminder engine for spider_diary.

Scans project blockers, stale items, health-check failures,
and injects reminder sections into the daily ops report.
"""

import datetime
import json
import logging
import os
import pathlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .blocker_store import BlockerStore

logger = logging.getLogger(__name__)

# ── 默认路径 ──────────────────────────────────────────────────
DEFAULT_BASE = Path(__file__).resolve().parents[2]
DEFAULT_GOV_DB = DEFAULT_BASE / "3_任务执行中枢（TAPD）" / "07_数据库" / "project_governance.db"
DEFAULT_PROJ_DB = DEFAULT_BASE / "data" / "project_management.db"
DEFAULT_REPORT_DIR = DEFAULT_BASE / "3_任务执行中枢（TAPD）" / "07_监控报告"


class RemindEngine:
    """扫描项目阻塞项并生成提醒数据。"""

    def __init__(
        self,
        base_path: Optional[Path] = None,
        gov_db_path: Optional[Path] = None,
        proj_db_path: Optional[Path] = None,
        report_dir: Optional[Path] = None,
    ):
        self.base_path = base_path or DEFAULT_BASE
        self.gov_db_path = gov_db_path or DEFAULT_GOV_DB
        self.proj_db_path = proj_db_path or DEFAULT_PROJ_DB
        self.report_dir = report_dir or DEFAULT_REPORT_DIR
        self.store = BlockerStore(self.report_dir / "blockers.json")
        self._today = datetime.date.today()

    # ── 扫描方法 ──────────────────────────────────────────────

    def scan_stale_projects(self, days: int = 7) -> List[Dict]:
        """扫描超过 N 天未同步的项目。"""
        items = []
        if not self.gov_db_path.exists():
            return items
        try:
            conn = sqlite3.connect(str(self.gov_db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT project_id, name, status, last_synced FROM meta_projects"
            ).fetchall()
            conn.close()
            for r in rows:
                last = r["last_synced"]
                if not last:
                    items.append({
                        "id": f"stale-{r['project_id']}",
                        "severity": "warning",
                        "title": f"项目 {r['name']} 从未同步",
                        "message": f"项目 {r['project_id']} ({r['name']}) 的 last_synced 为空",
                        "impact": "数据可能过时",
                        "suggestion": "运行 daily_sync.py 同步",
                        "source": "scan_stale",
                    })
                    continue
                try:
                    last_dt = datetime.datetime.fromisoformat(last).date()
                    delta = (self._today - last_dt).days
                    if delta >= days:
                        items.append({
                            "id": f"stale-{r['project_id']}",
                            "severity": "warning",
                            "title": f"项目 {r['name']} 已 {delta} 天未同步",
                            "message": f"项目 {r['project_id']} 最后同步: {last}",
                            "impact": "数据可能过时",
                            "suggestion": "运行 daily_sync.py 同步",
                            "source": "scan_stale",
                        })
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.warning("scan_stale_projects error: %s", e)
        return items

    def scan_blocked_tasks(self) -> List[Dict]:
        """扫描阻塞状态的任务。"""
        items = []
        if not self.gov_db_path.exists():
            return items
        try:
            conn = sqlite3.connect(str(self.gov_db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT task_id, project_id, content, status FROM task_pool WHERE status='阻塞'"
            ).fetchall()
            conn.close()
            for r in rows:
                items.append({
                    "id": f"blocked-{r['task_id']}",
                    "severity": "critical",
                    "title": f"阻塞任务: {r['content'][:40]}",
                    "message": f"任务 {r['task_id']} 处于阻塞状态",
                    "impact": f"项目 {r['project_id']} 进度受阻",
                    "suggestion": "检查依赖关系并解除阻塞",
                    "source": "scan_blocked",
                })
        except Exception as e:
            logger.warning("scan_blocked_tasks error: %s", e)
        return items

    def scan_missing_modules(self) -> List[Dict]:
        """扫描关键缺失模块（如 agents_orchestrator）。"""
        items = []
        critical_modules = [
            {
                "module": "agents_orchestrator",
                "path": self.base_path / "agents_orchestrator" / "core" / "__init__.py",
                "impact": "Gateway(6185)、Watchflow、Meta-Observer 均无法启动",
                "suggestion": "创建 agents_orchestrator/core/ 并实现 model_router、dialogue_context 等子模块",
            },
        ]
        for mod in critical_modules:
            if not mod["path"].exists():
                items.append({
                    "id": f"missing-{mod['module']}",
                    "severity": "critical",
                    "title": f"核心模块缺失: {mod['module']}",
                    "message": f"路径不存在: {mod['path']}",
                    "impact": mod["impact"],
                    "suggestion": mod["suggestion"],
                    "source": "scan_missing",
                })
        return items

    def scan_health_failures(self) -> List[Dict]:
        """扫描最近健康检查中的失败项。"""
        items = []
        health_json = self.report_dir / f"code_health_{self._today.strftime('%Y%m%d')}.json"
        if not health_json.exists():
            return items
        try:
            data = json.loads(health_json.read_text(encoding="utf-8"))
            findings = data.get("findings", [])
            for f in findings:
                if f.get("severity") == "S0":
                    items.append({
                        "id": f"health-{f.get('check', 'unknown')}",
                        "severity": "warning",
                        "title": f"健康检查失败: {f.get('check', 'unknown')}",
                        "message": f"{f.get('count', 0)} 个问题",
                        "impact": "代码质量下降",
                        "suggestion": f"运行 {f.get('check')} 修复",
                        "source": "scan_health",
                    })
        except Exception as e:
            logger.warning("scan_health_failures error: %s", e)
        return items

    # ── 全量扫描 ──────────────────────────────────────────────

    def scan_all(self) -> List[Dict]:
        """运行所有扫描器，返回去重后的阻塞项列表。"""
        all_items: List[Dict] = []
        scanners = [
            self.scan_missing_modules,
            self.scan_blocked_tasks,
            self.scan_stale_projects,
            self.scan_health_failures,
        ]
        for scanner in scanners:
            try:
                all_items.extend(scanner())
            except Exception as e:
                logger.warning("Scanner %s error: %s", scanner.__name__, e)

        # 去重（按 id）
        seen = set()
        deduped = []
        for item in all_items:
            if item["id"] not in seen:
                seen.add(item["id"])
                deduped.append(item)
        return deduped

    # ── 同步到 store ──────────────────────────────────────────

    def sync_store(self) -> int:
        """扫描并将新阻塞项写入 store，返回新增数量。"""
        items = self.scan_all()
        existing = self.store.get_active()
        existing_ids = {i["id"] for i in existing}
        new_count = 0
        for item in items:
            if item["id"] not in existing_ids:
                self.store.add(item)
                new_count += 1
                logger.info("New blocker: [%s] %s", item["severity"], item["title"])
        return new_count

    # ── 生成报告片段 ──────────────────────────────────────────

    def build_remind_section(self) -> str:
        """生成 Markdown 格式的提醒段落，追加到每日报告末尾。"""
        return self.store.remind_markdown()

    def build_terminal_panel(self) -> str:
        """生成终端显示的彩色状态面板。"""
        active = self.store.get_active()
        crit = [i for i in active if i.get("severity") == "critical"]
        warn = [i for i in active if i.get("severity") == "warning"]
        info = [i for i in active if i.get("severity") not in ("critical", "warning")]

        lines = [
            "",
            "┌─────────────────────────────────────────────┐",
            "│  🕷️  小蜘蛛日历 — 阻塞项提醒面板              │",
            f"│  {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}                          │",
            "├─────────────────────────────────────────────┤",
        ]
        if not active:
            lines.append("│  ✅ 无活跃阻塞项，系统运行正常                │")
        else:
            lines.append(f"│  🔴 严重: {len(crit)}  |  🟡 警告: {len(warn)}  |  🔵 信息: {len(info)}          │")
            lines.append("├─────────────────────────────────────────────┤")
            for item in active[:8]:
                sev = item.get("severity", "info")
                icon = {"critical": "🔴", "warning": "🟡"}.get(sev, "🔵")
                title = item.get("title", "")[:38]
                lines.append(f"│  {icon} {title,-38} │")
            if len(active) > 8:
                lines.append(f"│  ... 还有 {len(active) - 8} 项                        │")
        lines.append("└─────────────────────────────────────────────┘")
        lines.append("")
        return "\n".join(lines)
