"""User settings: a typed dataclass persisted as JSON. No Qt imports."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

INTERVAL_RANGE = (0.5, 120.0)


@dataclass
class Settings:
    check_interval: float = 2.0
    sounds_enabled: bool = True
    volume: int = 80  # 0-100 master volume
    offline_sound: str = ""  # empty = bundled assets/sounds/offline.wav
    reconnect_sound: str = ""  # empty = bundled assets/sounds/reconnect.wav
    notifications_enabled: bool = True
    auto_start_monitoring: bool = True
    launch_at_login: bool = False
    dark_mode: bool = True
    minimize_to_tray_on_close: bool = True
    auto_check_updates: bool = True
    skipped_update_version: str = ""
    last_update_check: float = 0.0  # unix time of the last completed check
    last_run_version: str = ""  # lets the app notice it was just updated

    def sanitized(self) -> "Settings":
        """Return a copy with every value coerced into its valid range/type."""
        defaults = Settings()
        clean = Settings()
        for f in fields(self):
            value = getattr(self, f.name)
            default = getattr(defaults, f.name)
            try:
                if isinstance(default, bool):
                    value = value if isinstance(value, bool) else bool(value)
                elif isinstance(default, int):
                    value = int(value)
                elif isinstance(default, float):
                    value = float(value)
                else:
                    value = str(value) if value is not None else default
            except (TypeError, ValueError):
                value = default
            setattr(clean, f.name, value)
        clean.check_interval = min(max(clean.check_interval, INTERVAL_RANGE[0]), INTERVAL_RANGE[1])
        clean.volume = min(max(clean.volume, 0), 100)
        return clean

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known}).sanitized()


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("settings file is not a JSON object")
            return Settings.from_dict(raw)
        except FileNotFoundError:
            return Settings()
        except (OSError, ValueError) as exc:
            log.warning("Could not read settings (%s); using defaults", exc)
            self._backup_corrupt()
            return Settings()

    def save(self, settings: Settings) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            log.exception("Could not save settings to %s", self.path)

    def _backup_corrupt(self) -> None:
        try:
            self.path.replace(self.path.with_suffix(".corrupt"))
        except OSError:
            pass
