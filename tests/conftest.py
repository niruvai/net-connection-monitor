import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.models import CheckResult


class ScriptedChecker:
    """Checker whose outcome is set by the test; optionally slow."""

    def __init__(self, reachable=True, delay=0.0):
        self.reachable = reachable
        self.delay = delay
        self.calls = 0

    def check(self):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return CheckResult(self.reachable, 12.5 if self.reachable else None)


class FakeAudio:
    """Stand-in for AudioService that records what would have been played."""

    def __init__(self):
        self.enabled = True
        self.played = []

    def configure(self, enabled, volume_percent, offline, reconnect):
        self.enabled = enabled
        self.volume = volume_percent

    def play(self, kind, force=False):
        if self.enabled or force:
            self.played.append(kind)
            return True
        return False

    def stop(self):
        pass

    def resolve(self, kind):
        return Path(kind)


class FakeNotifier:
    def __init__(self):
        self.enabled = True
        self.sent = []

    def attach(self, tray):
        pass

    def notify(self, title, message, force=False):
        if self.enabled or force:
            self.sent.append((title, message))
            return True
        return False


class FakeAutostart:
    def __init__(self):
        self.value = False

    def set_enabled(self, enabled):
        self.value = enabled
        return True


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("NET_WATCHER_HOME", str(tmp_path / "home"))


def wait_until(predicate, timeout=5.0, app=None):
    """Spin the Qt event loop (if any) until predicate() is true."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    if app is not None:
        app.processEvents()
    return bool(predicate())


@pytest.fixture
def scripted():
    return ScriptedChecker


@pytest.fixture
def make_controller(qapp, tmp_path):
    from core.history import OutageHistory
    from core.settings import SettingsStore
    from services.controller import AppController

    created = []

    def factory(checker, settings=None, history=None, **overrides):
        store = SettingsStore(tmp_path / f"settings{len(created)}.json")
        if settings:
            from core.settings import Settings

            store.save(Settings.from_dict(settings))
        audio, notifier = FakeAudio(), FakeNotifier()
        controller = AppController(
            store,
            history or OutageHistory(tmp_path / f"history{len(created)}.json"),
            checker=checker,
            audio=audio,
            notifier=notifier,
            autostart=FakeAutostart(),
            signature_provider=lambda: None,
            ip_fetcher=lambda: "198.51.100.7",
            recheck_delay=0.02,
            **overrides,
        )
        controller.fake_audio, controller.fake_notifier = audio, notifier
        created.append(controller)
        return controller

    yield factory
    for c in created:
        c.shutdown()
