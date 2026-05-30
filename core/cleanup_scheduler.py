"""Cleanup scheduler for Spider Diary.

Manages file lifecycle with a 3-tier storage model (hot/warm/cold),
cleans temporary artifacts, large logs, and empty directories.
All paths are resolved relative to the project root.
"""

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Default retention configuration
DEFAULT_HOT_DAYS = 7
DEFAULT_WARM_DAYS = 30
DEFAULT_COLD_DAYS = 90
DEFAULT_LOG_RETENTION_DAYS = 30
DEFAULT_TEMP_RETENTION_HOURS = 24
DEFAULT_LARGE_LOG_THRESHOLD_MB = 10

# File patterns targeted for cleanup
TEMP_EXTENSIONS = {".tmp", ".temp", ".bak"}
PYCACHE_DIR = "__pycache__"


@dataclass
class CleanupConfig:
    """Configuration for cleanup thresholds and retention periods."""

    hot_days: int = DEFAULT_HOT_DAYS
    warm_days: int = DEFAULT_WARM_DAYS
    cold_days: int = DEFAULT_COLD_DAYS
    log_retention_days: int = DEFAULT_LOG_RETENTION_DAYS
    temp_retention_hours: int = DEFAULT_TEMP_RETENTION_HOURS
    large_log_threshold_mb: int = DEFAULT_LARGE_LOG_THRESHOLD_MB
    archive_enabled: bool = True
    compression_enabled: bool = True


@dataclass
class CleanupSummary:
    """Aggregated result of a cleanup run."""

    hot_moved: int = 0
    warm_moved: int = 0
    cold_moved: int = 0
    expired_deleted: int = 0
    logs_archived: int = 0
    logs_deleted: int = 0
    temp_deleted: int = 0
    pycache_cleaned: int = 0
    large_logs_deleted: int = 0
    empty_dirs_removed: int = 0
    duration_seconds: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "duration_seconds": self.duration_seconds,
            "hot_moved": self.hot_moved,
            "warm_moved": self.warm_moved,
            "cold_moved": self.cold_moved,
            "expired_deleted": self.expired_deleted,
            "logs_archived": self.logs_archived,
            "logs_deleted": self.logs_deleted,
            "temp_deleted": self.temp_deleted,
            "pycache_cleaned": self.pycache_cleaned,
            "large_logs_deleted": self.large_logs_deleted,
            "empty_dirs_removed": self.empty_dirs_removed,
            "total_files_processed": (
                self.hot_moved
                + self.warm_moved
                + self.cold_moved
                + self.expired_deleted
                + self.logs_deleted
                + self.temp_deleted
                + self.pycache_cleaned
                + self.large_logs_deleted
                + self.empty_dirs_removed
            ),
        }


class CleanupScheduler:
    """Manages automated file cleanup with tiered retention.

    Hot tier: Recent files (default 7 days) — kept in active /reports.
    Warm tier: Aging files (default 30 days) — moved to /reports/warm.
    Cold tier: Old files (default 90 days) — moved to /reports/cold.
    Expired: Files beyond cold tier are deleted.

    Additional cleanup targets:
    - __pycache__ directories
    - Temporary files (.tmp, .temp, .bak) older than temp_retention_hours
    - Large log files exceeding the size threshold
    - Empty directories left behind after cleanup
    """

    def __init__(self, project_root: Optional[Path] = None, config: Optional[CleanupConfig] = None):
        """Initialize the cleanup scheduler.

        Args:
            project_root: Root directory of the project. Defaults to the
                git repository root or the current working directory.
            config: Cleanup threshold configuration. Uses defaults when None.
        """
        self.project_root = project_root or self._detect_project_root()
        self.config = config or CleanupConfig()

        # Tier directories relative to project root
        self.reports_dir = self.project_root / "reports"
        self.hot_dir = self.reports_dir / "hot"
        self.warm_dir = self.reports_dir / "warm"
        self.cold_dir = self.reports_dir / "cold"
        self.logs_dir = self.project_root / "logs"
        self.current_logs_dir = self.logs_dir / "current"
        self.archive_dir = self.logs_dir / "archive"
        self.temp_dir = self.project_root / "temp"

    @staticmethod
    def _detect_project_root() -> Path:
        """Detect the project root by walking up from the current directory."""
        cwd = Path.cwd()
        for path in [cwd] + list(cwd.parents):
            if (path / ".git").exists():
                return path
        return cwd

    def ensure_directories(self) -> None:
        """Create all tier and log directories if they do not exist."""
        for d in (
            self.hot_dir,
            self.warm_dir,
            self.cold_dir,
            self.current_logs_dir,
            self.archive_dir,
            self.temp_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _file_age_days(file_path: Path) -> float:
        """Return the age of a file in days."""
        if not file_path.exists():
            return float("inf")
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        return (datetime.now() - mtime).total_seconds() / 86400

    def _move_file(self, src: Path, dst_dir: Path) -> None:
        """Move a file into dst_dir, creating the directory if needed."""
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst_dir / src.name))

    # ── Tier management ─────────────────────────────────────────

    def _promote_tiers(self) -> Dict[str, int]:
        """Promote files between tiers based on their age.

        Returns:
            Counts of files that expired from each tier.
        """
        result: Dict[str, int] = {"expired": 0}

        # Promote from warm -> cold, delete from cold
        for f in list(self.warm_dir.glob("*.json")):
            if self._file_age_days(f) > self.config.warm_days:
                self._move_file(f, self.cold_dir)

        for f in list(self.cold_dir.glob("*.json")):
            if self._file_age_days(f) > self.config.cold_days:
                f.unlink()
                result["expired"] += 1

        return result

    def cleanup_reports(self) -> Dict[str, int]:
        """Distribute report files into the correct tier based on age.

        Files in the root /reports directory named ``daily_report_*.json``
        are moved to / kept in the appropriate tier.  Existing tier
        directories are also re-evaluated so that aged files are promoted.

        Returns:
            Dict with counts for each tier movement and expired deletions.
        """
        result = {"hot_moved": 0, "warm_moved": 0, "cold_moved": 0, "expired_deleted": 0}

        report_pattern = "daily_report_*.json"

        # Promote files already inside tier directories
        tier_result = self._promote_tiers()
        result["expired_deleted"] = tier_result["expired"]

        if not self.reports_dir.exists():
            return result

        for file_path in self.reports_dir.glob(report_pattern):
            age = self._file_age_days(file_path)
            if age <= self.config.hot_days:
                self._move_file(file_path, self.hot_dir)
                result["hot_moved"] += 1
            elif age <= self.config.warm_days:
                self._move_file(file_path, self.warm_dir)
                result["warm_moved"] += 1
            elif age <= self.config.cold_days:
                self._move_file(file_path, self.cold_dir)
                result["cold_moved"] += 1
            else:
                file_path.unlink()
                result["expired_deleted"] += 1

        return result

    # ── Log cleanup ─────────────────────────────────────────────

    def cleanup_logs(self) -> Dict[str, int]:
        """Archive or delete old log files.

        - Files in logs/current older than ``log_retention_days`` are
          moved to logs/archive.
        - Top-level log files matching ``*.log`` that are older than the
          retention period and larger than the size threshold are deleted.

        Returns:
            Dict with counts of archived and deleted log files.
        """
        archived = 0
        deleted = 0

        if self.current_logs_dir.exists():
            for f in self.current_logs_dir.glob("*.log"):
                if self._file_age_days(f) > self.config.log_retention_days:
                    self._move_file(f, self.archive_dir)
                    archived += 1

        if self.logs_dir.exists():
            for f in self.logs_dir.glob("*.log"):
                if self._file_age_days(f) > self.config.log_retention_days:
                    size_mb = f.stat().st_size / (1024 * 1024)
                    if size_mb > self.config.large_log_threshold_mb:
                        f.unlink()
                        deleted += 1

        return {"archived": archived, "deleted": deleted}

    def cleanup_large_logs(self) -> int:
        """Remove log files anywhere under the project that exceed the size threshold.

        Returns:
            Number of large log files deleted.
        """
        count = 0
        large_bytes = self.config.large_log_threshold_mb * 1024 * 1024
        for log_file in self.project_root.rglob("*.log"):
            if log_file.stat().st_size > large_bytes:
                log_file.unlink()
                count += 1
                logger.info("Removed large log: %s", log_file)
        return count

    # ── Temp & artifact cleanup ─────────────────────────────────

    def cleanup_temp(self) -> int:
        """Delete temporary files older than ``temp_retention_hours``.

        Targets .tmp, .temp, and .bak extensions.

        Returns:
            Number of temporary files deleted.
        """
        count = 0
        if not self.temp_dir.exists():
            return count
        for item in self.temp_dir.rglob("*"):
            if item.is_file() and item.suffix.lower() in TEMP_EXTENSIONS:
                age_hours = self._file_age_days(item) * 24
                if age_hours > self.config.temp_retention_hours:
                    item.unlink()
                    count += 1
        return count

    def cleanup_pycache(self) -> int:
        """Remove all __pycache__ directories under the project root.

        Returns:
            Number of __pycache__ directories removed.
        """
        count = 0
        for pycache in self.project_root.rglob(PYCACHE_DIR):
            if pycache.is_dir():
                shutil.rmtree(pycache)
                count += 1
                logger.info("Removed __pycache__: %s", pycache)
        return count

    def cleanup_empty_dirs(self) -> int:
        """Remove empty directories (bottom-up) under the project root.

        The project root itself is never removed.

        Returns:
            Number of empty directories removed.
        """
        count = 0
        for dirpath, dirnames, filenames in os.walk(str(self.project_root), topdown=False):
            p = Path(dirpath)
            if p == self.project_root:
                continue
            try:
                if p.exists() and not any(p.iterdir()):
                    p.rmdir()
                    count += 1
            except OSError:
                pass
        return count

    # ── Top-level entry point ───────────────────────────────────

    def run_cleanup(self) -> Dict:
        """Execute the full cleanup pipeline.

        Runs report tiering, log cleanup, temp/artifact removal, and
        empty-directory cleanup, then returns a summary dict.

        Returns:
            Summary dict with per-category counts and totals.
        """
        self.ensure_directories()
        start = datetime.now()

        reports = self.cleanup_reports()
        logs = self.cleanup_logs()
        large_logs = self.cleanup_large_logs()
        temp = self.cleanup_temp()
        pycache = self.cleanup_pycache()
        empty_dirs = self.cleanup_empty_dirs()

        duration = (datetime.now() - start).total_seconds()

        summary = CleanupSummary(
            hot_moved=reports["hot_moved"],
            warm_moved=reports["warm_moved"],
            cold_moved=reports["cold_moved"],
            expired_deleted=reports["expired_deleted"],
            logs_archived=logs["archived"],
            logs_deleted=logs["deleted"],
            temp_deleted=temp,
            pycache_cleaned=pycache,
            large_logs_deleted=large_logs,
            empty_dirs_removed=empty_dirs,
            duration_seconds=round(duration, 3),
            timestamp=start.isoformat(),
        )

        result = summary.to_dict()
        self._log_summary(result)
        logger.info("Cleanup complete: %s", json.dumps(result))
        return result

    def _log_summary(self, summary: Dict) -> None:
        """Append a JSON summary line to the cleanup log file."""
        log_file = self.current_logs_dir / f"cleanup_{datetime.now().strftime('%Y%m%d')}.log"
        self.current_logs_dir.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write(f"{json.dumps(summary)}\n")
