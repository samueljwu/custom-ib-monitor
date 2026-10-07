"""Locations for user data, independent of the application installation."""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_NAME = "CustomIBMonitor"


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_DATA_NAME
    if sys.platform == "win32":
        return Path.home() / "AppData" / "Local" / APP_DATA_NAME
    return Path.home() / ".local" / "share" / APP_DATA_NAME


def legacy_source_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    # Preserve an existing developer installation. Frozen releases never use
    # files beside the executable as user data.
    legacy = legacy_source_dir() / "data"
    if not getattr(sys, "frozen", False) and (legacy / "portfolio.sqlite3").exists():
        return legacy
    return user_data_dir()


def local_config_path() -> Path:
    legacy = legacy_source_dir() / "local_config.json"
    if not getattr(sys, "frozen", False) and legacy.exists():
        return legacy
    return user_data_dir() / "local_config.json"
