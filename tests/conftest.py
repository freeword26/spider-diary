"""Pytest configuration for Spider Diary."""

import pathlib
import sys

# Add project root to sys.path so ``from core.xxx import ...`` works
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Prevent pytest from trying to import __init__.py as a test module
collect_ignore = [".."]
