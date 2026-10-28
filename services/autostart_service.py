"""Launch Net Watcher at login on Windows (registry), macOS (LaunchAgent) and Linux (.desktop)."""
from __future__ import annotations

import logging
import plistlib
import sys
from pathlib import Path

from utils.paths import APP_ID, APP_NAME, is_frozen

log = logging.getLogger(__name__)

LAUNCH_AGENT_LABEL = "com.netwatcher.app"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> list[str]:
    """Command line that starts the app minimized to the tray."""
    if is_frozen():
        return [sys.executable, "--minimized"]
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(main_py), "--minimized"]


def _quote(arg: str) -> str:
    return f'"{arg}"' if " " in arg else arg


def windows_run_value(command: list[str]) -> str:
    return " ".join(_quote(a) for a in command)


def macos_plist(command: list[str]) -> bytes:
    return plistlib.dumps(
        {"Label": LAUNCH_AGENT_LABEL, "ProgramArguments": command, "RunAtLoad": True, "ProcessType": "Interactive"}
    )


def linux_desktop_entry(command: list[str]) -> str:
    exec_line = " ".join(_quote(a) for a in command)
    return f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec={exec_line}\nX-GNOME-Autostart-enabled=true\n"


def _macos_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _linux_path() -> Path:
    return Path.home() / ".config" / "autostart" / "net-watcher.desktop"


def is_enabled() -> bool:
    try:
        if sys.platform == "win32":
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_ID)
            return True
        return (_macos_path() if sys.platform == "darwin" else _linux_path()).exists()
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Returns True on success. Failures are logged, never raised."""
    try:
        command = launch_command()
        if sys.platform == "win32":
            import winreg

            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                if enabled:
                    winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, windows_run_value(command))
                else:
                    try:
                        winreg.DeleteValue(key, APP_ID)
                    except FileNotFoundError:
                        pass
        else:
            path = _macos_path() if sys.platform == "darwin" else _linux_path()
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                if sys.platform == "darwin":
                    path.write_bytes(macos_plist(command))
                else:
                    path.write_text(linux_desktop_entry(command), encoding="utf-8")
            else:
                path.unlink(missing_ok=True)
        log.info("Launch at login %s", "enabled" if enabled else "disabled")
        return True
    except Exception:
        log.exception("Could not change launch-at-login")
        return False
