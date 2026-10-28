"""Qt-facing update orchestration: schedule checks, download, install.

Network work happens on short-lived worker threads; results come back as signals
so the GUI thread never blocks. All security-relevant logic (signature, hash,
URL rules) lives in ``core.update``.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from core.update import config
from core.update.client import (
    DownloadCancelled,
    UpdateClient,
    UpdateError,
    UpdateInfo,
    cleanup_downloads,
    download_asset,
)
from core.update.installer import InstallError, launch, plan_install
from core.version import __version__
from services.controller import AppController
from utils.paths import config_dir

log = logging.getLogger(__name__)

IDLE, CHECKING, AVAILABLE, DOWNLOADING, READY, INSTALLING, ERROR = (
    "idle", "checking", "available", "downloading", "ready", "installing", "error",
)


class UpdateService(QObject):
    state_changed = Signal(str)
    update_found = Signal(object)  # UpdateInfo, emitted when a new (not skipped) version appears
    progress = Signal(int, int)  # downloaded bytes, total bytes
    check_finished = Signal(bool)  # True when an update is available
    quit_requested = Signal()  # the installer has been launched: the app must exit now

    _check_done = Signal(object, object, bool)  # info, error message, manual
    _download_done = Signal(object, object)  # path, error message
    _progress = Signal(int, int)

    def __init__(
        self,
        controller: AppController,
        client: UpdateClient | None = None,
        current_version: str = __version__,
        downloads_dir: Path | None = None,
        startup_delay: float = config.STARTUP_DELAY_SECONDS,
        interval_hours: float = config.CHECK_INTERVAL_HOURS,
        platform_key: str | None = None,
        launcher=launch,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_version = current_version
        self.client = client or UpdateClient(config.feed_url(), config.public_keys(), current_version)
        self.downloads_dir = downloads_dir or (config_dir() / "updates")
        self._platform_key = platform_key
        self._launcher = launcher
        self._startup_delay = startup_delay

        self.state = IDLE
        self.info: UpdateInfo | None = None
        self.error = ""
        self.message = ""
        self.downloaded: Path | None = None
        self._cancel = threading.Event()
        self._notified_version = ""

        self._check_done.connect(self._on_check_done)
        self._download_done.connect(self._on_download_done)
        self._progress.connect(self.progress)

        self._timer = QTimer(self)
        self._timer.setInterval(int(interval_hours * 3600 * 1000))
        self._timer.timeout.connect(self._scheduled_check)

    # ----- properties used by the UI -----

    @property
    def available(self) -> bool:
        """Can this build check for updates at all?"""
        return self.client.configured and self.client.supported

    def unavailable_reason(self) -> str:
        if not self.client.configured:
            return "Updates are not configured for this build."
        if not self.client.supported:
            return "Automatic updates are not available on this operating system."
        return ""

    @property
    def pending(self) -> bool:
        return self.state in (AVAILABLE, DOWNLOADING, READY, INSTALLING) and self.info is not None

    def status_text(self) -> str:
        if not self.available:
            return self.unavailable_reason()
        if self.state == CHECKING:
            return "Checking for updates…"
        if self.pending:
            return f"Version {self.info.version} is available."
        if self.state == ERROR:
            return self.error
        last = self.controller.settings.last_update_check
        if last:
            return f"Net Watcher is up to date. Last checked {time.strftime('%H:%M', time.localtime(last))}."
        return "Not checked yet."

    # ----- lifecycle -----

    def start(self) -> None:
        """Call once after the window exists: post-update bookkeeping and the check schedule."""
        self._after_update_housekeeping()
        if self.available and self.controller.settings.auto_check_updates:
            QTimer.singleShot(int(self._startup_delay * 1000), self._scheduled_check)
        if self.available:
            self._timer.start()

    def shutdown(self) -> None:
        self._timer.stop()
        self._cancel.set()

    def _after_update_housekeeping(self) -> None:
        previous = self.controller.settings.last_run_version
        if previous and previous != self.current_version:
            log.info("Net Watcher updated from %s to %s", previous, self.current_version)
            self.controller.notifier.notify("Net Watcher updated", f"Now running version {self.current_version}.")
        if previous != self.current_version:
            self.controller.update_settings(last_run_version=self.current_version)
        try:
            removed = cleanup_downloads(self.downloads_dir, self.current_version)
            if removed:
                log.info("Removed %d stale update file(s)", removed)
        except Exception:
            log.debug("Update cleanup failed", exc_info=True)

    # ----- checking -----

    def _scheduled_check(self) -> None:
        if self.controller.settings.auto_check_updates and self.state in (IDLE, ERROR):
            self.check(manual=False)

    def check(self, manual: bool = True) -> None:
        if self.state in (CHECKING, DOWNLOADING, INSTALLING):
            return
        if not self.available:
            self._fail(self.unavailable_reason(), quiet=not manual)
            return
        if self.pending:
            return
        self._set_state(CHECKING)
        threading.Thread(target=self._check_worker, args=(manual,), name="update-check", daemon=True).start()

    def _check_worker(self, manual: bool) -> None:
        try:
            self._check_done.emit(self.client.check(), None, manual)
        except UpdateError as exc:
            self._check_done.emit(None, str(exc), manual)
        except Exception:
            log.exception("Unexpected error while checking for updates")
            self._check_done.emit(None, "Something went wrong while checking for updates.", manual)

    def _on_check_done(self, info: UpdateInfo | None, error: str | None, manual: bool) -> None:
        if error:
            self._fail(error, quiet=not manual)
            return
        self.controller.update_settings(last_update_check=time.time())
        self.error = ""
        if info is None:
            self.info = None
            self._set_state(IDLE)
            self.check_finished.emit(False)
            return
        self.info = info
        skipped = self.controller.settings.skipped_update_version == info.version
        self._set_state(AVAILABLE)
        self.check_finished.emit(True)
        if manual or not skipped:
            if self._notified_version != info.version:
                self._notified_version = info.version
                self.controller.notifier.notify(
                    "Update available", f"Net Watcher {info.version} is ready to download."
                )
            self.update_found.emit(info)

    def _fail(self, message: str, quiet: bool) -> None:
        # Automatic checks fail silently (e.g. you are offline - which is this app's whole job).
        log.log(logging.INFO if quiet else logging.WARNING, "Update check failed: %s", message)
        self.error = message
        self._set_state(IDLE if quiet else ERROR)
        self.check_finished.emit(False)

    # ----- download / install -----

    def skip_version(self) -> None:
        if self.info:
            self.controller.update_settings(skipped_update_version=self.info.version)
            log.info("Skipping update %s", self.info.version)
        self.info = None
        self._set_state(IDLE)

    def download(self) -> None:
        if self.state not in (AVAILABLE, ERROR) or self.info is None:
            return
        self._cancel = threading.Event()
        self.error = ""
        self._set_state(DOWNLOADING)
        threading.Thread(target=self._download_worker, args=(self.info, self._cancel), name="update-download", daemon=True).start()

    def cancel_download(self) -> None:
        self._cancel.set()

    def _download_worker(self, info: UpdateInfo, cancel: threading.Event) -> None:
        try:
            path = download_asset(info, self.downloads_dir, progress=self._progress.emit, cancel=cancel)
            self._download_done.emit(path, None)
        except DownloadCancelled:
            self._download_done.emit(None, "")
        except UpdateError as exc:
            self._download_done.emit(None, str(exc))
        except Exception:
            log.exception("Unexpected error while downloading the update")
            self._download_done.emit(None, "The update could not be downloaded.")

    def _on_download_done(self, path: Path | None, error: str | None) -> None:
        if error is None and path is not None:
            self.downloaded = path
            self._set_state(READY)
            return
        if error:
            self.error = error
            self._set_state(ERROR)
        else:  # cancelled
            self._set_state(AVAILABLE if self.info else IDLE)

    def install(self) -> None:
        if self.state != READY or self.info is None or self.downloaded is None:
            return
        try:
            plan = plan_install(self.downloaded, self.info.version, self.info.asset.platform)
            self._set_state(INSTALLING)
            self.message = plan.message
            self._launcher(plan)
        except InstallError as exc:
            log.error("Install failed: %s", exc)
            self.error = str(exc)
            self._set_state(ERROR)
            return
        log.info("Installer launched for %s (%s)", self.info.version, plan.kind)
        if plan.quits_app:
            self.quit_requested.emit()
        else:
            self._set_state(READY)

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.state_changed.emit(state)
        elif state == ERROR:
            self.state_changed.emit(state)
