# PyInstaller spec for Net Watcher (Windows .exe folder build, macOS .app bundle).
#   pyinstaller packaging/net_watcher.spec --noconfirm --distpath dist --workpath build
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
with open(os.path.join(ROOT, "core", "version.py"), encoding="utf-8") as _f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _f.read()).group(1)
ICONS = os.path.join(ROOT, "assets", "icons")

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "assets"), "assets")],
    hiddenimports=["certifi", "cryptography.hazmat.primitives.asymmetric.ed25519"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml", "PySide6.QtQuick"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NetWatcher",
    console=False,
    icon=os.path.join(ICONS, "app.ico") if sys.platform == "win32" else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="NetWatcher", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Net Watcher.app",
        icon=os.path.join(ICONS, "app.icns"),
        bundle_identifier="com.netwatcher.app",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": "Net Watcher",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
