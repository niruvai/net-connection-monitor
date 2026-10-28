#!/usr/bin/env bash
# Builds "Net Watcher.app" and (unless --no-dmg) the DMG installer.
#
#   ./packaging/build_macos.sh [--no-dmg]
#
# Optional environment variables:
#   CODESIGN_IDENTITY   e.g. "Developer ID Application: Your Name (TEAMID)" - signs the .app and DMG
#   NOTARY_PROFILE      keychain profile from `xcrun notarytool store-credentials` - notarizes the DMG
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

.venv/bin/python -m pytest -q
.venv/bin/python -m PyInstaller packaging/net_watcher.spec --noconfirm --distpath dist --workpath build

APP="dist/Net Watcher.app"
if [ -n "${CODESIGN_IDENTITY:-}" ]; then
    codesign --deep --force --options runtime --timestamp --sign "$CODESIGN_IDENTITY" "$APP"
else
    # Ad-hoc signature so the bundle launches on Apple Silicon; users still need right-click > Open.
    codesign --deep --force --sign - "$APP"
fi
echo "Built $APP"

"$APP/Contents/MacOS/NetWatcher" --self-test || { echo "Packaged app failed its self-test" >&2; exit 1; }
echo "Self-test passed"
.venv/bin/python -c "from core.update import config; import sys; sys.exit(0 if config.FEED_URL and config.PUBLIC_KEYS else 1)" \
    || echo "WARNING: core/update/config.py has no FEED_URL / PUBLIC_KEYS: this build will not check for updates." >&2

if [ "${1:-}" != "--no-dmg" ]; then
    ./packaging/create_dmg.sh
fi
