# ============================================================
# spider_diary/remind/blocker_store.py
# 阻塞项与提醒数据层 —— 供 run-script.ps1 和 spider_diary 共用
# ============================================================
"""Blocker and reminder data store.

Reads/writes blocker status from a JSON file that both the PowerShell
run-script and the spider_diary engine consume.
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "blockers.json"


class BlockerStore:
    """Lightweight JSON-backed blocker registry."""

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path: Path = store_path or DEFAULT_STORE_PATH
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        if not self.store_path.exists():
            return {"version": 1, "items": [], "last_updated": ""}
        return json.loads(self.store_path.read_text(encoding="utf-8"))

    def _save(self, data: Dict[str, Any]) -> None:
        data["last_updated"] = datetime.now().isoformat()
        self.store_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_all(self) -> List[Dict[str, Any]]:
        return self._load().get("items", [])

    def get_active(self) -> List[Dict[str, Any]]:
        return [i for i in self.get_all() if i.get("status") != "resolved"]

    def get_by_severity(self, severity: str) -> List[Dict[str, Any]]:
        return [i for i in self.get_active() if i.get("severity") == severity]

    def add(self, item: Dict[str, Any]) -> None:
        data = self._load()
        item.setdefault("id", str(len(data["items"]) + 1))
        item.setdefault("status", "active")
        item.setdefault("created_at", datetime.now().isoformat())
        data["items"].append(item)
        self._save(data)

    def resolve(self, item_id: str) -> bool:
        data = self._load()
        for item in data["items"]:
            if str(item.get("id")) == str(item_id):
                item["status"] = "resolved"
                item["resolved_at"] = datetime.now().isoformat()
                self._save(data)
                return True
        return False

    def summary(self) -> str:
        active = self.get_active()
        if not active:
            return "  ✅ No active blockers"
        crit = [i for i in active if i.get("severity") == "critical"]
        warn = [i for i in active if i.get("severity") == "warning"]
        info = [i for i in active if i.get("severity") not in ("critical", "warning")]
        lines = []
        if crit:
            lines.append(f"  🔴 Critical ({len(crit)}):")
            for c in crit:
                lines.append(f"    [{c['id']}] {c.get('title', c.get('message', ''))}")
        if warn:
            lines.append(f"  🟡 Warning ({len(warn)}):")
            for w in warn:
                lines.append(f"    [{w['id']}] {w.get('title', w.get('message', ''))}")
        if info:
            lines.append(f"  🔵 Info ({len(info)}):")
            for i in info:
                lines.append(f"    [{i['id']}] {i.get('title', i.get('message', ''))}")
        return "\n".join(lines)

    def remind_markdown(self) -> str:
        """Generate a Markdown reminder section for daily reports."""
        active = self.get_active()
        if not active:
            return "\n## ✅ System Health\n\nNo active blockers. All systems nominal.\n"

        lines = [
            "",
            "## ⚠️ Active Blockers",
            "",
            f"> Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  Active: {len(active)}",
            "",
            "| # | Sev | Item | Impact | Action |",
            "|---|-----|------|--------|--------|",
        ]
        for item in active:
            sev = item.get("severity", "info")
            icon = {"critical": "🔴", "warning": "🟡"}.get(sev, "🔵")
            title = item.get("title", item.get("message", ""))
            impact = item.get("impact", "")
            action = item.get("suggestion", item.get("action", ""))
            lines.append(f"| {item.get('id', '')} | {icon} {sev} | {title} | {impact} | {action} |")
        lines.append("")
        return "\n".join(lines)
