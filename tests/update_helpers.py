import base64
import hashlib
import http.server
import json
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def new_key():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, base64.b64encode(raw).decode()


def make_manifest(version="1.1.0", assets=None, notes="## What's new\n- Faster checks", **extra):
    data = {"schema": 1, "version": version, "released": "2026-10-05T12:00:00Z", "notes": notes, "assets": assets or {}}
    data.update(extra)
    return json.dumps(data).encode()


def asset_entry(payload: bytes, url="https://updates.example.com/NetWatcher-Setup-1.1.0.exe"):
    return {"url": url, "sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}


def sign(private, data: bytes) -> bytes:
    return base64.b64encode(private.sign(data))


class Server:
    """Serves a directory over loopback HTTP on a random port."""

    def __init__(self, directory: Path, redirects: dict | None = None):
        redirects = redirects or {}

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(directory), **kw)

            def do_GET(self):
                if self.path in redirects:
                    self.send_response(302)
                    self.send_header("Location", redirects[self.path])
                    self.end_headers()
                    return
                super().do_GET()

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
