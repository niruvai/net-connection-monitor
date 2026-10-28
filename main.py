"""Net Watcher entry point."""
from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from core.history import OutageHistory
from core.version import __version__ as VERSION
from core.settings import SettingsStore
from services.controller import AppController
from services.update_service import UpdateService
from ui.icons import app_icon
from ui.main_window import MainWindow
from ui.tray import TrayController
from utils.logging_setup import setup_logging
from utils.paths import APP_NAME, config_dir, history_file, settings_file

log = logging.getLogger("net_watcher")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="net-watcher", description="Internet connection watchdog")
    parser.add_argument("--minimized", action="store_true", help="start hidden in the system tray")
    parser.add_argument("--self-test", action="store_true", help="verify the installation and exit (used by build scripts)")
    parser.add_argument("--allow-multiple", action="store_true", help="skip the single-instance check")
    args, _unknown = parser.parse_known_args(argv)  # Qt may add its own flags
    return args


def build_main_window(
    controller: AppController, with_tray: bool = True, updater: UpdateService | None = None
) -> tuple[MainWindow, TrayController | None]:
    tray = TrayController(controller) if with_tray and TrayController.available() else None
    window = MainWindow(controller, tray, updater)
    if tray:
        tray.show_requested.connect(window.show_and_raise)
        tray.quit_requested.connect(window.request_quit)
        tray.show()
    else:
        log.warning("System tray not available; closing the window will quit the app")
    return window, tray


def self_test() -> int:
    """Checks that a packaged build has everything it needs. Exit code 0 = healthy."""
    from core.update.manifest import verify_signature
    from utils.paths import default_sound_path, resource_path

    problems = []
    for kind in ("offline", "reconnect"):
        if not default_sound_path(kind).is_file():
            problems.append(f"missing sound {kind}.wav")
    if not resource_path("assets", "icons", "app.png").is_file():
        problems.append("missing app icon")
    try:
        import base64

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        public = base64.b64encode(
            key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode()
        verify_signature(b"x", base64.b64encode(key.sign(b"x")), [public])
    except Exception as exc:
        problems.append(f"signature verification unavailable: {exc}")
    try:
        import certifi

        if not certifi.where():
            problems.append("certifi bundle missing")
    except Exception as exc:
        problems.append(f"certifi unavailable: {exc}")
    for problem in problems:
        log.error("self-test: %s", problem)
    log.info("Self-test %s", "FAILED" if problems else "passed")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    args = parse_args(argv[1:])
    setup_logging()
    log.info("Starting %s %s", APP_NAME, VERSION)
    if args.self_test:
        return self_test()

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("NetWatcher")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    lock = QLockFile(str(config_dir() / "net-watcher.lock"))
    lock.setStaleLockTime(0)
    if not args.allow_multiple and not lock.tryLock(100):
        log.warning("Another Net Watcher instance is already running; exiting")
        return 0

    controller = AppController(SettingsStore(settings_file()), OutageHistory(history_file()))
    updater = UpdateService(controller)
    window, tray = build_main_window(controller, updater=updater)
    app.aboutToQuit.connect(updater.shutdown)
    app.aboutToQuit.connect(controller.shutdown)
    if tray and sys.platform == "darwin":
        app.applicationStateChanged.connect(
            lambda state: window.show_and_raise()
            if state == Qt.ApplicationState.ApplicationActive and not window.isVisible()
            else None
        )

    controller.start()
    updater.start()
    if not (args.minimized and tray):
        window.show()

    code = app.exec()
    if tray:
        tray.hide()
    lock.unlock()
    log.info("Exited with code %s", code)
    return code


if __name__ == "__main__":
    sys.exit(main())
