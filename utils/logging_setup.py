"""Application-wide logging: rotating file plus console."""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from utils.paths import logs_dir

LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO, to_file: bool = True) -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if to_file:
        try:
            handler = RotatingFileHandler(
                logs_dir() / "net-watcher.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
            )
            handler.setFormatter(formatter)
            root.addHandler(handler)
        except OSError:
            root.warning("Could not open log file; logging to console only", exc_info=True)

    _install_exception_hooks()
    _configured = True


def _install_exception_hooks() -> None:
    log = logging.getLogger("net_watcher.uncaught")

    def _excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("Uncaught exception", exc_info=(exc_type, exc, tb))

    def _thread_hook(args):
        log.critical(
            "Uncaught exception in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
