"""Network side of updating: fetch + verify the manifest, download + verify the asset.

Pure Python (urllib), no Qt, so it can run on any thread and is easy to test.
"""
from __future__ import annotations

import hashlib
import logging
import re
import ssl
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from core.update.manifest import (
    ASSET_SUFFIX,
    ManifestError,
    ReleaseAsset,
    ReleaseInfo,
    is_allowed_url,
    parse_manifest,
    platform_candidates,
    select_asset,
    verify_signature,
)
from core.version import is_newer

log = logging.getLogger(__name__)

MAX_MANIFEST_BYTES = 256 * 1024
CHUNK = 64 * 1024
TIMEOUT = 15.0
USER_AGENT = "NetWatcher-Updater/1"

ProgressCallback = Callable[[int, int], None]


class UpdateError(Exception):
    """Any failure to check for or fetch an update. The message is safe to show the user."""


class DownloadCancelled(UpdateError):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    release: ReleaseInfo
    asset: ReleaseAsset

    @property
    def version(self) -> str:
        return self.release.version


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not is_allowed_url(newurl):
            raise urllib.error.URLError(f"refusing redirect to insecure URL: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url: str, timeout: float = TIMEOUT):
    if not is_allowed_url(url):
        raise UpdateError("Update URL must use HTTPS.")
    opener = urllib.request.build_opener(_HttpsOnlyRedirects, urllib.request.HTTPSHandler(context=_ssl_context()))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise UpdateError(f"Update server returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise UpdateError("Could not reach the update server.") from exc


def http_get(url: str, max_bytes: int = MAX_MANIFEST_BYTES, timeout: float = TIMEOUT) -> bytes:
    with _open(url, timeout) as response:
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UpdateError("Update response was unexpectedly large.")
    return data


class UpdateClient:
    def __init__(
        self,
        feed_url: str,
        public_keys: tuple[str, ...],
        current_version: str,
        platforms: list[str] | None = None,
        fetch: Callable[[str], bytes] = http_get,
    ) -> None:
        self.feed_url = feed_url
        self.public_keys = tuple(public_keys)
        self.current_version = current_version
        self.platforms = platform_candidates() if platforms is None else platforms
        self._fetch = fetch

    @property
    def configured(self) -> bool:
        return bool(self.feed_url and self.public_keys)

    @property
    def supported(self) -> bool:
        return bool(self.platforms)

    def check(self) -> UpdateInfo | None:
        """Return the newer release for this platform, or None when already up to date."""
        if not self.configured:
            raise UpdateError("Updates are not configured for this build.")
        if not self.supported:
            raise UpdateError("Automatic updates are not available on this operating system.")
        manifest = self._fetch(self.feed_url)
        signature = self._fetch(self.feed_url + ".sig")
        try:
            verify_signature(manifest, signature, self.public_keys)
            release = parse_manifest(manifest, self.feed_url)
        except ManifestError as exc:
            log.error("Rejected update manifest: %s", exc)
            raise UpdateError("The update information could not be verified.") from exc

        if not is_newer(release.version, self.current_version):
            log.info("Up to date (current %s, latest %s)", self.current_version, release.version)
            return None
        asset = select_asset(release, self.platforms)
        if asset is None:
            log.info("Release %s has no build for %s", release.version, self.platforms)
            return None
        log.info("Update available: %s -> %s", self.current_version, release.version)
        return UpdateInfo(release, asset)


def download_filename(info: UpdateInfo) -> str:
    """Safe local name; the extension is forced by platform so the server can't choose what we run."""
    family = info.asset.platform.split("-")[0]
    suffix = ASSET_SUFFIX.get(family, "")
    url_suffix = Path(urlparse(info.asset.url).path).suffix.lower()
    if not suffix or url_suffix != suffix:
        raise UpdateError("Update package has an unexpected file type.")
    return f"NetWatcher-{info.version}-{info.asset.platform}{suffix}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(
    info: UpdateInfo,
    dest_dir: Path,
    progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
    opener: Callable[[str], object] = _open,
) -> Path:
    """Download to ``dest_dir`` and return the verified file. Never leaves a bad file behind."""
    asset = info.asset
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / download_filename(info)
    if final.is_file() and final.stat().st_size == asset.size and sha256_file(final) == asset.sha256:
        log.info("Update %s already downloaded and verified", info.version)
        if progress:
            progress(asset.size, asset.size)
        return final

    partial = final.with_suffix(final.suffix + ".part")
    digest = hashlib.sha256()
    received = 0
    try:
        with opener(asset.url) as response, open(partial, "wb") as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled("Download cancelled.")
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                received += len(chunk)
                if received > asset.size:
                    raise UpdateError("Downloaded file is larger than expected.")
                digest.update(chunk)
                out.write(chunk)
                if progress:
                    progress(received, asset.size)
        if received != asset.size:
            raise UpdateError("Download was incomplete. Please try again.")
        if digest.hexdigest() != asset.sha256:
            log.error("Checksum mismatch for %s", asset.url)
            raise UpdateError("The downloaded file failed its integrity check and was discarded.")
        partial.replace(final)
        log.info("Downloaded and verified %s (%d bytes)", final.name, received)
        return final
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError("The update could not be downloaded or saved.") from exc
    finally:
        partial.unlink(missing_ok=True)


_DOWNLOAD_NAME = re.compile(r"^NetWatcher-(?P<version>[^-]+(?:-[0-9A-Za-z.]+)?)-(?:windows|macos)-[a-z0-9]+\.(?:exe|dmg)(?:\.part)?$")


def cleanup_downloads(dest_dir: Path, current_version: str) -> int:
    """Delete partial files and packages that are not newer than the running version."""
    removed = 0
    if not dest_dir.is_dir():
        return 0
    for path in dest_dir.iterdir():
        match = _DOWNLOAD_NAME.match(path.name)
        try:
            stale = path.suffix == ".part" or (match is not None and not is_newer(match["version"], current_version))
            if stale and path.is_file():
                path.unlink()
                removed += 1
        except (OSError, ValueError):
            continue
    return removed
