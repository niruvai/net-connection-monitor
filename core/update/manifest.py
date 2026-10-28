"""Release manifest: parsing, validation and Ed25519 signature verification.

``latest.json`` (schema 1)::

    {
      "schema": 1,
      "version": "1.1.0",
      "released": "2026-10-05T12:00:00Z",
      "notes": "Markdown release notes",
      "assets": {
        "windows-x64": {"url": "NetWatcher-Setup-1.1.0.exe", "sha256": "<hex>", "size": 123456},
        "macos-arm64": {"url": "NetWatcher-1.1.0-arm64.dmg", "sha256": "<hex>", "size": 123456},
        "macos-x64":   {"url": "NetWatcher-1.1.0-x64.dmg",   "sha256": "<hex>", "size": 123456}
      }
    }

Relative asset URLs are resolved against the manifest URL. The manifest is
authenticated by a detached signature (``latest.json.sig``); the assets are
authenticated by the SHA-256 recorded in the signed manifest.
"""
from __future__ import annotations

import base64
import binascii
import json
import platform
import re
import sys
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from core.version import Version

SCHEMA = 1
MAX_NOTES = 20_000
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ASSET_SUFFIX = {"windows": ".exe", "macos": ".dmg"}


class ManifestError(Exception):
    """The manifest is malformed, unsigned, or signed by an unknown key."""


@dataclass(frozen=True)
class ReleaseAsset:
    platform: str
    url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    notes: str
    released: str
    assets: dict[str, ReleaseAsset]

    @property
    def parsed_version(self) -> Version:
        return Version.parse(self.version)


def is_allowed_url(url: str) -> bool:
    """HTTPS everywhere; plain HTTP only for loopback (local testing)."""
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and (parsed.hostname or "") in LOCAL_HOSTS


def platform_candidates() -> list[str]:
    """Manifest asset keys that suit this machine, best first. Empty = unsupported platform."""
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return ["windows-arm64", "windows-x64"] if machine == "arm64" else ["windows-x64"]
    if sys.platform == "darwin":
        arch = "arm64" if machine == "arm64" else "x64"
        return [f"macos-{arch}", "macos-universal"]
    return []


def decode_public_key(b64: str):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(b64.strip(), validate=True))
    except (ValueError, binascii.Error) as exc:
        raise ManifestError(f"invalid public key: {exc}") from exc


def verify_signature(data: bytes, signature_b64: bytes | str, public_keys: tuple[str, ...] | list[str]) -> None:
    """Raise ManifestError unless ``data`` was signed by one of ``public_keys``."""
    from cryptography.exceptions import InvalidSignature

    if not public_keys:
        raise ManifestError("no update signing key is configured in this build")
    try:
        raw = signature_b64.decode("ascii") if isinstance(signature_b64, bytes) else signature_b64
        signature = base64.b64decode(raw.strip(), validate=True)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise ManifestError("signature file is not valid base64") from exc
    for key_b64 in public_keys:
        try:
            decode_public_key(key_b64).verify(signature, data)
            return
        except InvalidSignature:
            continue
    raise ManifestError("manifest signature does not match any trusted key")


def parse_manifest(data: bytes, base_url: str = "") -> ReleaseInfo:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ManifestError("manifest is not valid JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise ManifestError(f"unsupported manifest schema (expected {SCHEMA})")

    version = raw.get("version")
    try:
        Version.parse(version)
    except (ValueError, TypeError) as exc:
        raise ManifestError(f"manifest has an invalid version: {version!r}") from exc

    assets_raw = raw.get("assets")
    if not isinstance(assets_raw, dict) or not assets_raw:
        raise ManifestError("manifest lists no assets")
    assets: dict[str, ReleaseAsset] = {}
    for key, item in assets_raw.items():
        if not isinstance(item, dict):
            raise ManifestError(f"asset {key!r} is malformed")
        url = urljoin(base_url, str(item.get("url", "")))
        sha = str(item.get("sha256", ""))
        size = item.get("size")
        if not is_allowed_url(url):
            raise ManifestError(f"asset {key!r} must be served over HTTPS")
        if not _SHA256_RE.match(sha):
            raise ManifestError(f"asset {key!r} has no valid sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ManifestError(f"asset {key!r} has no valid size")
        assets[key] = ReleaseAsset(key, url, sha.lower(), size)

    notes = raw.get("notes", "")
    return ReleaseInfo(
        version=str(version).lstrip("v"),
        notes=str(notes)[:MAX_NOTES] if isinstance(notes, str) else "",
        released=str(raw.get("released", "")),
        assets=assets,
    )


def select_asset(release: ReleaseInfo, candidates: list[str] | None = None) -> ReleaseAsset | None:
    for key in platform_candidates() if candidates is None else candidates:
        if key in release.assets:
            return release.assets[key]
    return None
