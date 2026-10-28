"""Where this build looks for updates. Edit these two values when you publish releases.

FEED_URL
    HTTPS URL of ``latest.json`` (the release manifest). ``latest.json.sig`` must sit next to it.
    Leave empty to disable the updater entirely (the Settings page then says so).
PUBLIC_KEYS
    Base64 Ed25519 public keys allowed to sign manifests (``python tools/release.py keygen``).
    Several keys are accepted so a key can be rotated without stranding old installs.

Development override (never honored in a packaged build):
    NET_WATCHER_UPDATE_FEED=<url>   NET_WATCHER_UPDATE_PUBKEY=<base64 key>
"""
from __future__ import annotations

import os

from utils.paths import is_frozen

FEED_URL = ""
PUBLIC_KEYS: tuple[str, ...] = ()

CHECK_INTERVAL_HOURS = 6
STARTUP_DELAY_SECONDS = 20


def feed_url() -> str:
    if not is_frozen() and os.environ.get("NET_WATCHER_UPDATE_FEED"):
        return os.environ["NET_WATCHER_UPDATE_FEED"]
    return FEED_URL


def public_keys() -> tuple[str, ...]:
    if not is_frozen() and os.environ.get("NET_WATCHER_UPDATE_PUBKEY"):
        return (os.environ["NET_WATCHER_UPDATE_PUBKEY"],)
    return PUBLIC_KEYS
