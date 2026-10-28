"""Filesystem locations used by Net Watcher (config, logs, bundled resources)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Net Watcher"
APP_ID = "NetWatcher"
ENV_HOME_OVERRIDE = "NET_WATCHER_HOME"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Directory that contains ``assets/``: the repo root, or PyInstaller's bundle dir."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)


def default_sound_path(kind: str) -> Path:
    """Bundled default sound. ``kind`` is ``"offline"`` or ``"reconnect"``."""
    return resource_path("assets", "sounds", f"{kind}.wav")


def config_dir() -> Path:
    override = os.environ.get(ENV_HOME_OVERRIDE)
    if override:
        base = Path(override)
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_ID
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_ID
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "net-watcher"
    base.mkdir(parents=True, exist_ok=True)
    return base


def logs_dir() -> Path:
    path = config_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return config_dir() / "settings.json"


def history_file() -> Path:
    return config_dir() / "history.json"
