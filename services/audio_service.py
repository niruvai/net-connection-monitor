"""Sound playback built on Qt Multimedia (bundled with PySide6, same API on Windows/macOS).

WAV files use ``QSoundEffect`` (low latency, loud and reliable); other formats
such as MP3/OGG fall back to ``QMediaPlayer``. A custom file that is missing or
unplayable silently falls back to the bundled default.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QSoundEffect

from utils.paths import default_sound_path

log = logging.getLogger(__name__)

SOUND_KINDS = ("offline", "reconnect")
SOUND_FILTER = "Audio files (*.wav *.mp3 *.ogg *.flac *.m4a *.aac);;All files (*)"


class AudioService(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.enabled = True
        self.volume = 0.8
        self._custom: dict[str, str] = {k: "" for k in SOUND_KINDS}
        self._effects: dict[str, QSoundEffect] = {}
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self.on_play: Callable[[str, Path], None] | None = None  # test/diagnostic hook

    def configure(self, enabled: bool, volume_percent: int, offline: str, reconnect: str) -> None:
        self.enabled = enabled
        self.volume = max(0.0, min(1.0, volume_percent / 100))
        self._custom = {"offline": offline, "reconnect": reconnect}
        for effect in self._effects.values():
            effect.setVolume(self.volume)
        if self._output:
            self._output.setVolume(self.volume)

    def resolve(self, kind: str) -> Path:
        custom = self._custom.get(kind, "")
        if custom:
            path = Path(custom).expanduser()
            if path.is_file():
                return path
            log.warning("Custom %s sound not found (%s); using default", kind, custom)
        return default_sound_path(kind)

    def play(self, kind: str, force: bool = False) -> bool:
        """Play a sound. ``force`` bypasses the enabled flag (used by the Test buttons)."""
        if not (self.enabled or force):
            return False
        path = self.resolve(kind)
        if self.on_play:
            self.on_play(kind, path)
        if not path.is_file():
            log.error("Sound file missing: %s", path)
            return False
        try:
            self.stop()
            if path.suffix.lower() == ".wav":
                self._play_effect(path)
            else:
                self._play_media(path)
            return True
        except Exception:
            log.exception("Could not play %s", path)
            return False

    def stop(self) -> None:
        for effect in self._effects.values():
            effect.stop()
        if self._player:
            self._player.stop()

    def _play_effect(self, path: Path) -> None:
        key = str(path)
        effect = self._effects.get(key)
        if effect is not None and effect.status() == QSoundEffect.Status.Error:
            effect.deleteLater()  # e.g. no output device earlier; retry with a fresh backend
            effect = None
        if effect is None:
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(key))
            effect.statusChanged.connect(lambda e=effect, p=path: self._on_status(e, p))
            self._effects[key] = effect
        effect.setVolume(self.volume)
        effect.play()

    def _on_status(self, effect: QSoundEffect, path: Path) -> None:
        if effect.status() == QSoundEffect.Status.Error:
            log.error("Audio backend rejected %s; falling back to media player", path)
            self._play_media(path)

    def _play_media(self, path: Path) -> None:
        if self._player is None:
            self._output = QAudioOutput(self)
            self._player = QMediaPlayer(self)
            self._player.setAudioOutput(self._output)
        self._output.setVolume(self.volume)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
