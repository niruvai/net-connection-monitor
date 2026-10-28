"""Release tooling: signing keys and the signed update manifest.

One-time setup
    python tools/release.py keygen --out ~/secrets/net-watcher-release.key
    -> keep the key file private and backed up; paste the printed public key into
       core/update/config.py (PUBLIC_KEYS) and set FEED_URL, then ship that build.

Every release (after building on each OS, collect the artifacts in one folder)
    python tools/release.py publish \\
        --key ~/secrets/net-watcher-release.key \\
        --notes release-notes.md \\
        --asset windows-x64=dist/installer/NetWatcher-Setup-1.1.0.exe \\
        --asset macos-arm64=dist/NetWatcher-1.1.0-arm64.dmg \\
        --asset macos-x64=dist/NetWatcher-1.1.0-x64.dmg \\
        --out dist/release
    -> writes dist/release/{latest.json, latest.json.sig, <assets>}. Upload the whole folder to the
       location FEED_URL points at (asset URLs are relative to latest.json by default; pass
       --base-url to use absolute URLs, e.g. a CDN).

Sanity check
    python tools/release.py verify --manifest dist/release/latest.json --public-key <base64>

The version comes from core/version.py unless --version is given.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from core.update.manifest import ASSET_SUFFIX, ManifestError, parse_manifest, verify_signature  # noqa: E402
from core.version import Version, __version__  # noqa: E402

KNOWN_PLATFORMS = ("windows-x64", "windows-arm64", "macos-arm64", "macos-x64", "macos-universal")


def public_key_b64(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SystemExit("error: key is not an Ed25519 private key")
    return key


def cmd_keygen(args: argparse.Namespace) -> None:
    out = Path(args.out).expanduser()
    if out.exists():
        raise SystemExit(f"error: {out} already exists; refusing to overwrite a signing key")
    key = Ed25519PrivateKey.generate()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    out.chmod(0o600)
    print(f"Private key written to {out}  (keep it secret and back it up)")
    print(f"Public key (put in core/update/config.py PUBLIC_KEYS):\n  {public_key_b64(key)}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(version: str, notes: str, assets: dict[str, Path], base_url: str, released: str | None = None) -> bytes:
    Version.parse(version)
    entries = {}
    for platform_key, path in sorted(assets.items()):
        if platform_key not in KNOWN_PLATFORMS:
            raise SystemExit(f"error: unknown platform {platform_key!r}; use one of {', '.join(KNOWN_PLATFORMS)}")
        if path.suffix.lower() != ASSET_SUFFIX[platform_key.split("-")[0]]:
            raise SystemExit(f"error: {path.name} has the wrong file type for {platform_key}")
        if not path.is_file():
            raise SystemExit(f"error: {path} not found")
        entries[platform_key] = {
            "url": base_url.rstrip("/") + "/" + path.name if base_url else path.name,
            "sha256": sha256_of(path),
            "size": path.stat().st_size,
        }
    manifest = {
        "schema": 1,
        "version": version,
        "released": released or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": notes,
        "assets": entries,
    }
    return (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def cmd_publish(args: argparse.Namespace) -> None:
    assets: dict[str, Path] = {}
    for item in args.asset:
        key, sep, raw = item.partition("=")
        if not sep:
            raise SystemExit(f"error: --asset expects PLATFORM=PATH, got {item!r}")
        assets[key] = Path(raw).expanduser()
    if not assets:
        raise SystemExit("error: pass at least one --asset")
    notes = Path(args.notes).read_text(encoding="utf-8") if args.notes else ""
    data = build_manifest(args.version or __version__, notes, assets, args.base_url or "")
    key = load_private_key(Path(args.key).expanduser())
    signature = base64.b64encode(key.sign(data))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_bytes(data)
    (out / "latest.json.sig").write_bytes(signature + b"\n")
    for path in assets.values():
        shutil.copy2(path, out / path.name)

    parse_manifest(data, "https://example.invalid/")  # self-check the result
    verify_signature(data, signature, [public_key_b64(key)])
    print(f"Release {args.version or __version__} written to {out}/ :")
    for name in sorted(p.name for p in out.iterdir()):
        print("  ", name)


def cmd_verify(args: argparse.Namespace) -> None:
    manifest = Path(args.manifest)
    data = manifest.read_bytes()
    try:
        verify_signature(data, Path(str(manifest) + ".sig").read_bytes(), [args.public_key])
        info = parse_manifest(data, "https://example.invalid/")
    except ManifestError as exc:
        raise SystemExit(f"INVALID: {exc}")
    print(f"OK: version {info.version}, platforms: {', '.join(sorted(info.assets))}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("keygen", help="create an Ed25519 signing key")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("publish", help="build and sign latest.json for a release")
    p.add_argument("--key", required=True, help="private key file from keygen")
    p.add_argument("--asset", action="append", default=[], metavar="PLATFORM=PATH")
    p.add_argument("--notes", help="markdown file with release notes")
    p.add_argument("--version", help=f"defaults to core/version.py ({__version__})")
    p.add_argument("--base-url", help="absolute URL prefix for assets (default: relative to latest.json)")
    p.add_argument("--out", default="dist/release")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("verify", help="check a manifest and its signature")
    p.add_argument("--manifest", required=True)
    p.add_argument("--public-key", required=True)
    p.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
