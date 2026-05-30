import datetime
import glob
import logging
import os
import pathlib
import shutil

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """Manages file lifecycle with tiered storage and temp file cleanup."""

    def __init__(
        self,
        base_path=None,
        hot_dir=None,
        warm_dir=None,
        cold_dir=None,
    ):
        self.base_path = pathlib.Path(base_path or os.getcwd())
        self.hot_dir = pathlib.Path(hot_dir) if hot_dir else self.base_path / "hot"
        self.warm_dir = pathlib.Path(warm_dir) if warm_dir else self.base_path / "warm"
        self.cold_dir = pathlib.Path(cold_dir) if cold_dir else self.base_path / "cold"

    def _is_older_than(self, relative_path, days):
        """Check whether a file under base_path is older than *days*."""
        full = self.base_path / relative_path
        if not full.exists():
            return False
        file_time = datetime.datetime.fromtimestamp(full.stat().st_mtime)
        return (datetime.datetime.now() - file_time).days >= days

    def _get_file_age_days(self, relative_path):
        """Return file age in days, or -1 if not found."""
        full = self.base_path / relative_path
        if not full.exists():
            return -1
        file_time = datetime.datetime.fromtimestamp(full.stat().st_mtime)
        return (datetime.datetime.now() - file_time).days

    def _move_file(self, src, dst_dir):
        """Move a file into dst_dir preserving subdirectory structure relative to hot_dir."""
        rel = src.relative_to(self.hot_dir)
        dst = dst_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        logger.info("Moved %s -> %s", src, dst)

    def move_hot_to_warm(self, threshold_days=30):
        """Move files older than threshold_days from hot to warm storage."""
        self.hot_dir.mkdir(parents=True, exist_ok=True)
        self.warm_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for src in self.hot_dir.rglob("*"):
            if not src.is_file():
                continue
            file_time = datetime.datetime.fromtimestamp(src.stat().st_mtime)
            if (datetime.datetime.now() - file_time).days >= threshold_days:
                self._move_file(src, self.warm_dir)
                count += 1
        logger.info("Hot->Warm: moved %d files", count)
        return count

    def move_warm_to_cold(self, threshold_days=90):
        """Move files older than threshold_days from warm to cold storage."""
        self.warm_dir.mkdir(parents=True, exist_ok=True)
        self.cold_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for src in self.warm_dir.rglob("*"):
            if not src.is_file():
                continue
            file_time = datetime.datetime.fromtimestamp(src.stat().st_mtime)
            if (datetime.datetime.now() - file_time).days >= threshold_days:
                rel = src.relative_to(self.warm_dir)
                dst = self.cold_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                count += 1
                logger.info("Moved %s -> %s", src, dst)
        logger.info("Warm->Cold: moved %d files", count)
        return count

    def cleanup_temp_files(self, patterns=None, older_than_days=None):
        """Remove temporary files matching glob patterns.

        Args:
            patterns: List of glob patterns to match (e.g. ['*.tmp', '*.bak']).
            older_than_days: If set, only remove files older than this many days.

        Returns:
            int: Number of files removed.
        """
        patterns = patterns or ["*.tmp"]
        count = 0
        for pattern in patterns:
            for path in self.base_path.glob(pattern):
                if not path.is_file():
                    continue
                if older_than_days is not None:
                    file_time = datetime.datetime.fromtimestamp(path.stat().st_mtime)
                    if (datetime.datetime.now() - file_time).days < older_than_days:
                        continue
                path.unlink()
                count += 1
                logger.info("Removed temp file: %s", path)
        logger.info("Temp cleanup: removed %d files", count)
        return count

    def run_full_cleanup(self, hot_warm_days=30, warm_cold_days=90, temp_patterns=None):
        """Run the complete cleanup pipeline."""
        self.move_hot_to_warm(threshold_days=hot_warm_days)
        self.move_warm_to_cold(threshold_days=warm_cold_days)
        self.cleanup_temp_files(patterns=temp_patterns or ["*.tmp"])
