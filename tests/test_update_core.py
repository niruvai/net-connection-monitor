import subprocess
import sys
import threading
from pathlib import Path

import pytest

from core.update import installer
from core.update.client import (
    DownloadCancelled,
    UpdateClient,
    UpdateError,
    UpdateInfo,
    cleanup_downloads,
    download_asset,
    download_filename,
    http_get,
)
from core.update.manifest import (
    ManifestError,
    ReleaseAsset,
    is_allowed_url,
    parse_manifest,
    select_asset,
    verify_signature,
)
from core.version import Version, is_newer, parse_version
from tests.update_helpers import Server, asset_entry, make_manifest, new_key, sign

PAYLOAD = b"installer-bytes" * 5000
WIN = ["windows-x64"]


# ---------- versions ----------

@pytest.mark.parametrize(
    "new,old,expected",
    [
        ("1.0.1", "1.0.0", True),
        ("1.10.0", "1.9.9", True),
        ("2.0", "1.99.99", True),
        ("1.0.0", "1.0.0", False),
        ("1.0", "1.0.0", False),
        ("0.9.9", "1.0.0", False),
        ("1.1.0", "1.1.0-beta.2", True),
        ("1.1.0-beta.2", "1.1.0", False),
        ("1.1.0-beta.10", "1.1.0-beta.2", True),
        ("1.1.0-rc.1", "1.1.0-beta.9", True),
        ("v1.2.0", "1.1.0", True),
    ],
)
def test_version_ordering(new, old, expected):
    assert is_newer(new, old) is expected


def test_invalid_versions_rejected():
    for bad in ("", "abc", "1..2", "1.2.3.4.5", None):
        with pytest.raises(ValueError):
            parse_version(bad)
    assert Version.parse("1.2.3") == Version.parse("1.2.3.0")


# ---------- signatures & manifest ----------

def test_signature_roundtrip_and_tamper_detection():
    private, public = new_key()
    data = make_manifest(assets={"windows-x64": asset_entry(PAYLOAD)})
    sig = sign(private, data)
    verify_signature(data, sig, [public])
    with pytest.raises(ManifestError):
        verify_signature(data.replace(b"1.1.0", b"9.9.9"), sig, [public])
    _, other_public = new_key()
    with pytest.raises(ManifestError):
        verify_signature(data, sig, [other_public])
    verify_signature(data, sig, [other_public, public])  # key rotation: any trusted key works
    with pytest.raises(ManifestError):
        verify_signature(data, sig, [])
    with pytest.raises(ManifestError):
        verify_signature(data, b"not base64 !!", [public])


def test_parse_manifest_valid_and_relative_urls():
    data = make_manifest(assets={"windows-x64": asset_entry(PAYLOAD, url="NetWatcher-Setup-1.1.0.exe")})
    info = parse_manifest(data, "https://dl.example.com/nw/latest.json")
    assert info.version == "1.1.0"
    assert info.assets["windows-x64"].url == "https://dl.example.com/nw/NetWatcher-Setup-1.1.0.exe"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(version="banana"),
        lambda d: d.update(schema=2),
        lambda d: d.update(assets={}),
        lambda d: d["assets"]["windows-x64"].update(sha256="xyz"),
        lambda d: d["assets"]["windows-x64"].update(size=0),
        lambda d: d["assets"]["windows-x64"].update(url="http://evil.example.com/a.exe"),
        lambda d: d["assets"]["windows-x64"].update(url="file:///etc/passwd"),
    ],
)
def test_parse_manifest_rejects_bad_input(mutate):
    import json

    d = json.loads(make_manifest(assets={"windows-x64": asset_entry(PAYLOAD)}))
    mutate(d)
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(d).encode(), "https://dl.example.com/latest.json")
    with pytest.raises(ManifestError):
        parse_manifest(b"{not json", "")


def test_url_policy():
    assert is_allowed_url("https://example.com/x")
    assert is_allowed_url("http://127.0.0.1:8000/x")
    assert is_allowed_url("http://localhost/x")
    assert not is_allowed_url("http://example.com/x")
    assert not is_allowed_url("ftp://example.com/x")


def test_select_asset_prefers_specific_over_universal():
    data = make_manifest(
        assets={"macos-universal": asset_entry(PAYLOAD, "https://a.example/u.dmg"), "macos-arm64": asset_entry(PAYLOAD, "https://a.example/a.dmg")}
    )
    info = parse_manifest(data)
    assert select_asset(info, ["macos-arm64", "macos-universal"]).platform == "macos-arm64"
    assert select_asset(info, ["macos-x64", "macos-universal"]).platform == "macos-universal"
    assert select_asset(info, ["windows-x64"]) is None


# ---------- client.check ----------

def make_client(manifest, private, public, current="1.0.0", platforms=None, sig=None):
    sig = sign(private, manifest) if sig is None else sig

    def fetch(url):
        return sig if url.endswith(".sig") else manifest

    return UpdateClient("https://dl.example.com/latest.json", (public,), current, WIN if platforms is None else platforms, fetch)


def test_check_finds_newer_release():
    private, public = new_key()
    m = make_manifest("1.1.0", {"windows-x64": asset_entry(PAYLOAD)})
    info = make_client(m, private, public).check()
    assert info.version == "1.1.0" and info.asset.platform == "windows-x64"


@pytest.mark.parametrize("current", ["1.1.0", "2.0.0"])
def test_check_returns_none_when_current_or_newer(current):
    private, public = new_key()
    m = make_manifest("1.1.0", {"windows-x64": asset_entry(PAYLOAD)})
    assert make_client(m, private, public, current).check() is None


def test_check_ignores_release_without_build_for_this_platform():
    private, public = new_key()
    m = make_manifest("1.1.0", {"macos-arm64": asset_entry(PAYLOAD, "https://a.example/a.dmg")})
    assert make_client(m, private, public).check() is None


def test_check_rejects_forged_manifest():
    private, public = new_key()
    attacker, _ = new_key()
    m = make_manifest("9.0.0", {"windows-x64": asset_entry(PAYLOAD)})
    with pytest.raises(UpdateError, match="verified"):
        make_client(m, private, public, sig=sign(attacker, m)).check()


def test_check_requires_configuration_and_supported_platform():
    with pytest.raises(UpdateError, match="not configured"):
        UpdateClient("", (), "1.0.0", WIN).check()
    private, public = new_key()
    with pytest.raises(UpdateError, match="not available"):
        make_client(b"", private, public, platforms=[]).check()


# ---------- download ----------

def info_for(payload=PAYLOAD, url="https://updates.example.com/NetWatcher-Setup-1.1.0.exe", platform="windows-x64", size=None, sha=None):
    entry = asset_entry(payload, url)
    asset = ReleaseAsset(platform, url, sha or entry["sha256"], size or entry["size"])
    return UpdateInfo(parse_manifest(make_manifest(assets={platform: entry})), asset)


class FakeResponse:
    def __init__(self, data, chunk=1000):
        self.data, self.pos, self.chunk = data, 0, chunk

    def read(self, n=-1):
        part = self.data[self.pos : self.pos + min(n, self.chunk)]
        self.pos += len(part)
        return part

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def test_download_verifies_and_reports_progress(tmp_path):
    seen = []
    path = download_asset(info_for(), tmp_path, progress=lambda d, t: seen.append((d, t)), opener=lambda u: FakeResponse(PAYLOAD))
    assert path.read_bytes() == PAYLOAD and path.name == "NetWatcher-1.1.0-windows-x64.exe"
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD)) and len(seen) > 5
    assert list(tmp_path.glob("*.part")) == []


def test_download_reuses_verified_file(tmp_path):
    info = info_for()
    download_asset(info, tmp_path, opener=lambda u: FakeResponse(PAYLOAD))

    def boom(url):
        raise AssertionError("should not hit the network")

    assert download_asset(info, tmp_path, opener=boom).exists()


def test_download_rejects_tampered_payload_and_cleans_up(tmp_path):
    evil = b"X" * len(PAYLOAD)
    with pytest.raises(UpdateError, match="integrity"):
        download_asset(info_for(), tmp_path, opener=lambda u: FakeResponse(evil))
    assert list(tmp_path.iterdir()) == []


def test_download_rejects_oversized_and_truncated(tmp_path):
    with pytest.raises(UpdateError, match="larger"):
        download_asset(info_for(), tmp_path, opener=lambda u: FakeResponse(PAYLOAD + b"extra"))
    with pytest.raises(UpdateError, match="incomplete"):
        download_asset(info_for(), tmp_path, opener=lambda u: FakeResponse(PAYLOAD[:-10]))
    assert list(tmp_path.iterdir()) == []


def test_download_can_be_cancelled(tmp_path):
    cancel = threading.Event()

    def progress(done, total):
        if done > 3000:
            cancel.set()

    with pytest.raises(DownloadCancelled):
        download_asset(info_for(), tmp_path, progress=progress, cancel=cancel, opener=lambda u: FakeResponse(PAYLOAD))
    assert list(tmp_path.iterdir()) == []


def test_download_filename_is_controlled_by_us_not_the_server():
    assert download_filename(info_for()) == "NetWatcher-1.1.0-windows-x64.exe"
    with pytest.raises(UpdateError):
        download_filename(info_for(url="https://x.example/payload.bat"))
    with pytest.raises(UpdateError):  # a .dmg offered for Windows
        download_filename(info_for(url="https://x.example/a.dmg"))
    mac = info_for(url="https://x.example/../../etc/a.dmg", platform="macos-arm64")
    assert download_filename(mac) == "NetWatcher-1.1.0-macos-arm64.dmg"


def test_cleanup_removes_partials_and_old_packages_only(tmp_path):
    (tmp_path / "NetWatcher-1.0.0-windows-x64.exe").write_bytes(b"old")
    (tmp_path / "NetWatcher-0.9.0-macos-arm64.dmg").write_bytes(b"old")
    (tmp_path / "NetWatcher-1.2.0-windows-x64.exe").write_bytes(b"new")
    (tmp_path / "NetWatcher-1.2.0-windows-x64.exe.part").write_bytes(b"half")
    (tmp_path / "notes.txt").write_text("keep me")
    assert cleanup_downloads(tmp_path, "1.0.0") == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["NetWatcher-1.2.0-windows-x64.exe", "notes.txt"]
    assert cleanup_downloads(tmp_path / "missing", "1.0.0") == 0


# ---------- real HTTP: release tool -> server -> client -> download ----------

def test_end_to_end_with_release_tool_and_local_server(tmp_path):
    from tools import release

    key_file = tmp_path / "release.key"
    release.main(["keygen", "--out", str(key_file)])
    private = release.load_private_key(key_file)
    public = release.public_key_b64(private)

    installer_file = tmp_path / "NetWatcher-Setup-1.1.0.exe"
    installer_file.write_bytes(PAYLOAD)
    notes = tmp_path / "notes.md"
    notes.write_text("- shiny")
    out = tmp_path / "site"
    release.main(
        ["publish", "--key", str(key_file), "--version", "1.1.0", "--notes", str(notes), "--asset", f"windows-x64={installer_file}", "--out", str(out)]
    )
    release.main(["verify", "--manifest", str(out / "latest.json"), "--public-key", public])

    with Server(out) as server:
        client = UpdateClient(server.url + "/latest.json", (public,), "1.0.0", WIN)
        info = client.check()
        assert info and info.version == "1.1.0" and "shiny" in info.release.notes
        path = download_asset(info, tmp_path / "dl")
        assert path.read_bytes() == PAYLOAD
        assert UpdateClient(server.url + "/latest.json", (public,), "1.1.0", WIN).check() is None

        (out / "latest.json").write_bytes((out / "latest.json").read_bytes().replace(b"1.1.0", b"7.7.7"))
        with pytest.raises(UpdateError, match="verified"):
            client.check()


def test_release_tool_refuses_overwriting_keys_and_wrong_file_types(tmp_path):
    from tools import release

    key_file = tmp_path / "k"
    release.main(["keygen", "--out", str(key_file)])
    with pytest.raises(SystemExit):
        release.main(["keygen", "--out", str(key_file)])
    wrong = tmp_path / "a.zip"
    wrong.write_bytes(b"x")
    with pytest.raises(SystemExit):
        release.main(["publish", "--key", str(key_file), "--asset", f"windows-x64={wrong}", "--out", str(tmp_path / "o")])


def test_http_get_blocks_insecure_redirect_and_oversize(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"0" * 5000)
    (tmp_path / "ok.txt").write_text("hello")
    with Server(tmp_path, redirects={"/evil": "http://evil.example.com/x"}) as server:
        assert http_get(server.url + "/ok.txt") == b"hello"
        with pytest.raises(UpdateError):
            http_get(server.url + "/evil")
        with pytest.raises(UpdateError, match="large"):
            http_get(server.url + "/big.bin", max_bytes=100)
        with pytest.raises(UpdateError, match="HTTP 404"):
            http_get(server.url + "/missing")
    with pytest.raises(UpdateError, match="HTTPS"):
        http_get("http://example.com/latest.json")


# ---------- installer plans ----------

def test_windows_install_command_is_silent_and_detached_friendly(tmp_path):
    exe = tmp_path / "NetWatcher-1.1.0-windows-x64.exe"
    exe.write_bytes(b"x")
    plan = installer.plan_install(exe, "1.1.0", "windows-x64")
    assert plan.kind == "windows-installer" and plan.quits_app
    assert plan.command[0] == str(exe) and "/SILENT" in plan.command and "/NWUPDATE=1" in plan.command


@pytest.mark.skipif(sys.platform == "win32", reason="macOS updater script uses POSIX paths and sh")
def test_macos_script_is_valid_shell_and_quotes_paths(tmp_path):
    app = Path("/Applications/My Apps/Net Watcher.app")
    script = installer.macos_script(tmp_path / "it's a dmg.dmg", app, 4242, "1.1.0", tmp_path / "log.txt")
    path = tmp_path / "u.sh"
    path.write_text(script)
    assert subprocess.run(["sh", "-n", str(path)], capture_output=True).returncode == 0
    for needle in ("PID=4242", "codesign --verify --deep --strict", "CFBundleShortVersionString", "trap cleanup EXIT", 'mv "$OLD" "$APP"'):
        assert needle in script
    assert "'/Applications/My Apps/Net Watcher.app'" in script
    assert "it'\"'\"'s a dmg.dmg" in script  # single quote safely escaped


def test_macos_plan_swaps_when_writable_else_manual(tmp_path, monkeypatch):
    dmg = tmp_path / "NetWatcher-1.1.0-macos-arm64.dmg"
    dmg.write_bytes(b"x")
    bundle = tmp_path / "Net Watcher.app"
    bundle.mkdir()
    monkeypatch.setattr(installer, "is_frozen", lambda: True)
    monkeypatch.setattr(installer, "current_app_bundle", lambda: bundle)
    plan = installer.plan_install(dmg, "1.1.0", "macos-arm64", pid=1)
    assert plan.kind == "macos-swap" and plan.quits_app and plan.script

    monkeypatch.setattr(installer.os, "access", lambda *a: False)
    plan = installer.plan_install(dmg, "1.1.0", "macos-arm64", pid=1)
    assert plan.kind == "macos-manual" and not plan.quits_app

    monkeypatch.setattr(installer, "is_frozen", lambda: False)  # running from source
    assert installer.plan_install(dmg, "1.1.0", "macos-arm64").kind == "macos-manual"


def test_install_errors(tmp_path):
    with pytest.raises(installer.InstallError):
        installer.plan_install(tmp_path / "missing.exe", "1.1.0", "windows-x64")
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    with pytest.raises(installer.InstallError):
        installer.plan_install(f, "1.1.0", "linux-x64")


@pytest.mark.skipif(sys.platform == "win32", reason="posix launch")
def test_launch_writes_executable_script_and_starts_detached(tmp_path):
    marker = tmp_path / "ran.txt"
    plan = installer.InstallPlan("macos-swap", ["/bin/sh", str(tmp_path / "u.sh")], script=f"#!/bin/sh\necho ok > '{marker}'\n")
    installer.launch(plan)
    import time

    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.05)
    assert marker.read_text().strip() == "ok"
    assert (tmp_path / "u.sh").stat().st_mode & 0o100
