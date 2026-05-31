"""Pytest configuration for Spider Diary."""

import pathlib
import sys

# Add project root to sys.path
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Support ``from spider_diary.xxx import ...`` imports in old tests
# by making the project root importable as a package named "spider_diary"
if "spider_diary" not in sys.modules:
    import types
    _pkg = types.ModuleType("spider_diary")
    _pkg.__path__ = [str(_PROJECT_ROOT)]
    _pkg.__package__ = "spider_diary"
    sys.modules["spider_diary"] = _pkg

    # Also register spider_diary.core, spider_diary.report, etc.
    for _subdir in ("core", "report", "storage", "remind", "cli"):
        _subpkg = types.ModuleType(f"spider_diary.{_subdir}")
        _subpkg.__path__ = [str(_PROJECT_ROOT / _subdir)]
        _subpkg.__package__ = f"spider_diary.{_subdir}"
        sys.modules[f"spider_diary.{_subdir}"] = _subpkg

# Prevent pytest from importing __init__.py as a test module
collect_ignore = ["../__init__.py"]
