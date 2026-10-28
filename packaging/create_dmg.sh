#!/usr/bin/env bash
# Packs dist/"Net Watcher.app" into dist/NetWatcher-<version>-<arm64|x64>.dmg (drag-to-Applications layout).
# Uses only hdiutil, which ships with macOS.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-.venv/bin/python}"
VERSION="${VERSION:-$("$PYTHON" -c 'from core.version import __version__; print(__version__)')}"
case "$(uname -m)" in arm64) ARCH=arm64 ;; *) ARCH=x64 ;; esac   # matches release.py platform keys
APP="dist/Net Watcher.app"
DMG="dist/NetWatcher-${VERSION}-${ARCH}.dmg"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

[ -d "$APP" ] || { echo "Missing $APP - run packaging/build_macos.sh first" >&2; exit 1; }

cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "Net Watcher" -srcfolder "$STAGE" -ov -format UDZO "$DMG"

if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    codesign --force --timestamp --sign "$CODESIGN_IDENTITY" "$DMG"
    if [ -n "${NOTARY_PROFILE:-}" ]; then
        xcrun notarytool submit "$DMG" --keychain-profile "$NOTARY_PROFILE" --wait
        xcrun stapler staple "$DMG"
    fi
fi
echo "Created $DMG"
