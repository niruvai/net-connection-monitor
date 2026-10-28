"""Renders the app icon (PNG / ICO / ICNS) and tray icons into assets/icons/.

    python tools/make_icons.py

Edit ui/icons.py (or drop in your own app.png and re-run the .ico/.icns steps)
to restyle the icons. ICO and ICNS are written by hand with embedded PNG data,
so no extra tools or libraries are needed on any platform.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QIODevice, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPixmap  # noqa: E402

from ui.icons import paint_app_icon, painted_state_icon  # noqa: E402

OUT = ROOT / "assets" / "icons"


def png_bytes(pixmap: QPixmap, size: int) -> bytes:
    scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    scaled.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, master: QPixmap) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = [png_bytes(master, s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries = b""
    for size, data in zip(sizes, images):
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(images))


def write_icns(path: Path, master: QPixmap) -> None:
    chunks = b""
    for code, size in ((b"icp4", 16), (b"icp5", 32), (b"ic07", 128), (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024)):
        data = png_bytes(master, size)
        chunks += code + struct.pack(">I", len(data) + 8) + data
    path.write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])
    assert app is not None
    OUT.mkdir(parents=True, exist_ok=True)
    master = paint_app_icon(1024)
    (OUT / "app.png").write_bytes(png_bytes(master, 512))
    write_ico(OUT / "app.ico", master)
    write_icns(OUT / "app.icns", master)
    for state in ("online", "offline", "paused", "unknown"):
        (OUT / f"tray_{state}.png").write_bytes(png_bytes(painted_state_icon(state, 128), 64))
    print("wrote", ", ".join(sorted(p.name for p in OUT.iterdir())))


if __name__ == "__main__":
    main()
