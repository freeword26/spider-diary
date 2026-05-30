import datetime
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from spider_diary.cleanup import CleanupScheduler


class TestFileAgeDetection(unittest.TestCase):
    """Tests for file age detection logic."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.scheduler = CleanupScheduler(base_path=self.tmpdir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def _create_file(self, name, days_old=0, size=1024):
        path = pathlib.Path(self.tmpdir) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        if days_old > 0:
            old_time = (
                datetime.datetime.now() - datetime.timedelta(days=days_old)
            ).timestamp()
            os.utime(path, (old_time, old_time))
        return path

    def test_recent_file_not_old(self):
        self._create_file("recent.txt", days_old=1)
        assert not self.scheduler._is_older_than("recent.txt", days=7)

    def test_old_file_detected(self):
        self._create_file("old.txt", days_old=30)
        assert self.scheduler._is_older_than("old.txt", days=7)

    def test_file_exactly_at_boundary(self):
        self._create_file("boundary.txt", days_old=7)
        assert self.scheduler._is_older_than("boundary.txt", days=7)

    def test_nonexistent_file(self):
        result = self.scheduler._is_older_than("nonexistent.txt", days=7)
        assert result is False

    def test_get_file_age_days(self):
        self._create_file("aged.txt", days_old=15)
        age = self.scheduler._get_file_age_days("aged.txt")
        assert abs(age - 15) <= 1

    def test_get_file_age_nonexistent(self):
        age = self.scheduler._get_file_age_days("nonexistent.txt")
        assert age == -1


class TestThreeTierStorageMovement(unittest.TestCase):
    """Tests for 3-tier storage movement (hot → warm → cold)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.hot_dir = os.path.join(self.tmpdir, "hot")
        self.warm_dir = os.path.join(self.tmpdir, "warm")
        self.cold_dir = os.path.join(self.tmpdir, "cold")
        os.makedirs(self.hot_dir)
        os.makedirs(self.warm_dir)
        os.makedirs(self.cold_dir)
        self.scheduler = CleanupScheduler(
            base_path=self.tmpdir,
            hot_dir=self.hot_dir,
            warm_dir=self.warm_dir,
            cold_dir=self.cold_dir,
        )

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def _create_file(self, directory, name, days_old=0):
        path = pathlib.Path(directory) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test content")
        if days_old > 0:
            old_time = (
                datetime.datetime.now() - datetime.timedelta(days=days_old)
            ).timestamp()
            os.utime(path, (old_time, old_time))
        return path

    def test_hot_to_warm_movement(self):
        self._create_file(self.hot_dir, "report_old.md", days_old=35)
        moved = self.scheduler.move_hot_to_warm(threshold_days=30)
        assert moved == 1
        assert not os.path.exists(os.path.join(self.hot_dir, "report_old.md"))
        assert os.path.exists(os.path.join(self.warm_dir, "report_old.md"))

    def test_recent_hot_file_stays(self):
        self._create_file(self.hot_dir, "report_new.md", days_old=5)
        moved = self.scheduler.move_hot_to_warm(threshold_days=30)
        assert moved == 0
        assert os.path.exists(os.path.join(self.hot_dir, "report_new.md"))

    def test_warm_to_cold_movement(self):
        self._create_file(self.warm_dir, "report_archive.md", days_old=95)
        moved = self.scheduler.move_warm_to_cold(threshold_days=90)
        assert moved == 1
        assert not os.path.exists(os.path.join(self.warm_dir, "report_archive.md"))
        assert os.path.exists(os.path.join(self.cold_dir, "report_archive.md"))

    def test_recent_warm_file_stays(self):
        self._create_file(self.warm_dir, "report_recent.md", days_old=10)
        moved = self.scheduler.move_warm_to_cold(threshold_days=90)
        assert moved == 0
        assert os.path.exists(os.path.join(self.warm_dir, "report_recent.md"))

    def test_empty_tier_no_movement(self):
        moved = self.scheduler.move_hot_to_warm(threshold_days=30)
        assert moved == 0

    def test_multiple_files_partial_movement(self):
        self._create_file(self.hot_dir, "a_old.md", days_old=40)
        self._create_file(self.hot_dir, "b_old.md", days_old=60)
        self._create_file(self.hot_dir, "c_new.md", days_old=5)
        moved = self.scheduler.move_hot_to_warm(threshold_days=30)
        assert moved == 2
        assert os.path.exists(os.path.join(self.hot_dir, "c_new.md"))

    def test_move_preserves_subdirectory_structure(self):
        self._create_file(os.path.join(self.hot_dir, "sub"), "nested.md", days_old=40)
        moved = self.scheduler.move_hot_to_warm(threshold_days=30)
        assert moved == 1
        assert os.path.exists(os.path.join(self.warm_dir, "sub", "nested.md"))


class TestTempFileCleanup(unittest.TestCase):
    """Tests for temporary file cleanup."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.scheduler = CleanupScheduler(base_path=self.tmpdir)

    def tearDown(self):
        import shutil
        try:
            shutil.rmtree(self.tmpdir)
        except OSError:
            pass

    def _create_file(self, name, days_old=0):
        path = pathlib.Path(self.tmpdir) / name
        path.write_bytes(b"temp data")
        if days_old > 0:
            old_time = (
                datetime.datetime.now() - datetime.timedelta(days=days_old)
            ).timestamp()
            os.utime(path, (old_time, old_time))
        return path

    def test_cleanup_temp_files(self):
        self._create_file("temp_001.tmp", days_old=0)
        self._create_file("temp_002.tmp", days_old=1)
        self._create_file("normal.txt", days_old=0)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp"])
        assert cleaned == 2
        assert not os.path.exists(os.path.join(self.tmpdir, "temp_001.tmp"))
        assert not os.path.exists(os.path.join(self.tmpdir, "temp_002.tmp"))

    def test_cleanup_does_not_remove_non_temp(self):
        self._create_file("important.md", days_old=0)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp"])
        assert cleaned == 0
        assert os.path.exists(os.path.join(self.tmpdir, "important.md"))

    def test_cleanup_old_temp_files(self):
        self._create_file("old_temp.tmp", days_old=8)
        self._create_file("new_temp.tmp", days_old=1)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp"], older_than_days=7)
        assert cleaned == 1
        assert not os.path.exists(os.path.join(self.tmpdir, "old_temp.tmp"))
        assert os.path.exists(os.path.join(self.tmpdir, "new_temp.tmp"))

    def test_cleanup_multiple_patterns(self):
        self._create_file("a.tmp", days_old=0)
        self._create_file("b.bak", days_old=0)
        self._create_file("c.log", days_old=0)
        self._create_file("d.txt", days_old=0)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp", "*.bak"])
        assert cleaned == 2
        assert not os.path.exists(os.path.join(self.tmpdir, "a.tmp"))
        assert not os.path.exists(os.path.join(self.tmpdir, "b.bak"))
        assert os.path.exists(os.path.join(self.tmpdir, "c.log"))

    def test_cleanup_empty_directory(self):
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp"])
        assert cleaned == 0

    def test_cleanup_multiple_extension_patterns(self):
        self._create_file("report.csv", days_old=0)
        self._create_file("data.json", days_old=0)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["*.tmp"])
        assert cleaned == 0

    def test_cleanup_swagger_temp_files(self):
        self._create_file("swagger-codegen.tmp", days_old=0)
        self._create_file("regular.txt", days_old=0)
        cleaned = self.scheduler.cleanup_temp_files(patterns=["swagger*"])
        assert cleaned == 1
        assert not os.path.exists(os.path.join(self.tmpdir, "swagger-codegen.tmp"))
