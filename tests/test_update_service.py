import json
import time

import pytest

from core.settings import Settings, SettingsStore
from core.update.client import UpdateClient, UpdateError, UpdateInfo
from core.update.manifest import parse_manifest
from services import update_service as us
from services.update_service import UpdateService
from tests.conftest import ScriptedChecker, wait_until
from tests.update_helpers import Server, asset_entry, make_manifest, new_key, sign

PAYLOAD = b"setup" * 4000


def make_info(version="1.1.0", platform="windows-x64", payload=PAYLOAD, host="https://updates.example.com"):
    url = f"{host}/NetWatcher-Setup-{version}.exe"
    entry = asset_entry(payload, url)
    release = parse_manifest(make_manifest(version, {platform: entry}))
    return UpdateInfo(release, release.assets[platform])


class FakeClient:
    configured = True
    supported = True

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, 0

    def check(self):
        self.calls += 1
        if self.error:
            raise UpdateError(self.error)
        return self.result


@pytest.fixture
def make_service(make_controller, qapp, tmp_path):
    services = []

    def factory(client, settings=None, **kw):
        controller = make_controller(ScriptedChecker(True), settings=settings)
        launched = []
        service = UpdateService(
            controller,
            client=client,
            current_version="1.0.0",
            downloads_dir=tmp_path / "updates",
            startup_delay=0.05,
            launcher=launched.append,
            **kw,
        )
        service.launched = launched
        service.controller = controller
        services.append(service)
        return service

    yield factory
    for s in services:
        s.shutdown()


def run(qapp, predicate, timeout=5.0):
    return wait_until(predicate, timeout, app=qapp)


def test_manual_check_finds_update_and_notifies_once(make_service, qapp):
    info = make_info()
    s = make_service(FakeClient(info))
    found = []
    s.update_found.connect(found.append)
    s.check(manual=True)
    assert s.state == us.CHECKING
    assert run(qapp, lambda: s.state == us.AVAILABLE)
    assert s.info.version == "1.1.0" and found
    assert any("Update available" in t for t, _ in s.controller.fake_notifier.sent)
    assert s.controller.settings.last_update_check > 0
    assert s.pending and "1.1.0" in s.status_text()


def test_manual_check_up_to_date(make_service, qapp):
    s = make_service(FakeClient(None))
    finished = []
    s.check_finished.connect(finished.append)
    s.check()
    assert run(qapp, lambda: finished)
    assert finished == [False] and s.state == us.IDLE and not s.pending
    assert "up to date" in s.status_text()


def test_failed_manual_check_reports_but_automatic_is_silent(make_service, qapp):
    s = make_service(FakeClient(error="Could not reach the update server."))
    s.check(manual=True)
    assert run(qapp, lambda: s.state == us.ERROR)
    assert s.status_text() == "Could not reach the update server."
    s.check(manual=False)
    assert run(qapp, lambda: s.state == us.IDLE)
    assert s.controller.fake_notifier.sent == []


def test_skipped_version_not_announced_automatically_but_manual_still_shows(make_service, qapp):
    info = make_info()
    s = make_service(FakeClient(info), settings={"skipped_update_version": "1.1.0"})
    found = []
    s.update_found.connect(found.append)
    s.check(manual=False)
    assert run(qapp, lambda: s.state == us.AVAILABLE)
    assert found == [] and s.controller.fake_notifier.sent == []
    s.info = None
    s._set_state(us.IDLE)
    s.check(manual=True)
    assert run(qapp, lambda: found)


def test_skip_version_persists(make_service, qapp):
    s = make_service(FakeClient(make_info()))
    s.check()
    assert run(qapp, lambda: s.state == us.AVAILABLE)
    s.skip_version()
    assert s.state == us.IDLE and s.info is None
    assert s.controller.store.load().skipped_update_version == "1.1.0"


def test_auto_check_runs_at_startup_only_when_enabled(make_service, qapp):
    client = FakeClient(None)
    s = make_service(client)
    s.start()
    assert run(qapp, lambda: client.calls == 1)

    client2 = FakeClient(None)
    s2 = make_service(client2, settings={"auto_check_updates": False})
    s2.start()
    time.sleep(0.3)
    qapp.processEvents()
    assert client2.calls == 0
    s2.check(manual=True)  # manual checks still work
    assert run(qapp, lambda: client2.calls == 1)


def test_unconfigured_service_is_inert_and_explains_why(make_service, qapp):
    client = UpdateClient("", (), "1.0.0", ["windows-x64"])
    s = make_service(client)
    s.start()
    s.check(manual=True)
    assert not s.available and "not configured" in s.status_text()
    assert s.state == us.ERROR
    s2 = make_service(UpdateClient("", (), "1.0.0", ["windows-x64"]))
    s2.start()
    s2.check(manual=False)
    assert s2.state == us.IDLE


def test_full_flow_download_then_install_quits_app(make_service, qapp, tmp_path):
    private, public = new_key()
    manifest = make_manifest("1.1.0", {"windows-x64": asset_entry(PAYLOAD, "NetWatcher-Setup-1.1.0.exe")})
    site = tmp_path / "site"
    site.mkdir()
    (site / "latest.json").write_bytes(manifest)
    (site / "latest.json.sig").write_bytes(sign(private, manifest))
    (site / "NetWatcher-Setup-1.1.0.exe").write_bytes(PAYLOAD)

    with Server(site) as server:
        client = UpdateClient(server.url + "/latest.json", (public,), "1.0.0", ["windows-x64"])
        s = make_service(client)
        quits, progress = [], []
        s.quit_requested.connect(lambda: quits.append(1))
        s.progress.connect(lambda d, t: progress.append((d, t)))

        s.check()
        assert run(qapp, lambda: s.state == us.AVAILABLE)
        s.download()
        assert s.state == us.DOWNLOADING
        assert run(qapp, lambda: s.state == us.READY)
        assert progress and progress[-1][0] == len(PAYLOAD)
        assert s.downloaded.read_bytes() == PAYLOAD

        s.install()
        assert s.state == us.INSTALLING and quits == [1]
        assert len(s.launched) == 1 and s.launched[0].kind == "windows-installer"


def test_download_failure_can_be_retried(make_service, qapp, tmp_path):
    info = make_info(host="http://127.0.0.1:9")  # nothing listens there: connection refused
    s = make_service(FakeClient(info))
    s.check()
    assert run(qapp, lambda: s.state == us.AVAILABLE)
    s.download()
    assert run(qapp, lambda: s.state == us.ERROR, timeout=20)
    assert s.error
    s.download()  # retry allowed from ERROR
    assert s.state == us.DOWNLOADING
    s.cancel_download()
    assert run(qapp, lambda: s.state in (us.AVAILABLE, us.ERROR), timeout=20)


def test_manual_install_plan_does_not_quit(make_service, qapp, tmp_path, monkeypatch):
    s = make_service(FakeClient(make_info()))
    s.info = make_info(platform="macos-arm64")
    f = tmp_path / "updates"
    f.mkdir()
    pkg = f / "NetWatcher-1.1.0-macos-arm64.dmg"
    pkg.write_bytes(b"x")
    s.downloaded = pkg
    s._set_state(us.READY)
    quits = []
    s.quit_requested.connect(lambda: quits.append(1))
    s.install()  # running from source -> macos-manual
    assert quits == [] and s.state == us.READY
    assert s.launched and s.launched[0].kind == "macos-manual"


def test_post_update_housekeeping(make_service, qapp, tmp_path):
    (tmp_path / "updates").mkdir()
    stale = tmp_path / "updates" / "NetWatcher-1.0.0-windows-x64.exe"
    stale.write_bytes(b"old")
    s = make_service(FakeClient(None), settings={"last_run_version": "0.9.0"})
    s.start()
    assert not stale.exists()
    assert s.controller.settings.last_run_version == "1.0.0"
    assert any("updated" in t.lower() for t, _ in s.controller.fake_notifier.sent)


def test_first_run_records_version_without_announcing(make_service, qapp):
    s = make_service(FakeClient(None))
    s.start()
    assert s.controller.settings.last_run_version == "1.0.0"
    assert s.controller.fake_notifier.sent == []


# ---------- settings compatibility: updating must never lose user data ----------

def test_old_settings_file_loads_unchanged_with_new_defaults(tmp_path):
    old = {"check_interval": 5.0, "volume": 42, "dark_mode": False, "offline_sound": "/x/my.wav", "launch_at_login": True}
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(old))
    s = SettingsStore(path).load()
    assert (s.check_interval, s.volume, s.dark_mode, s.offline_sound, s.launch_at_login) == (5.0, 42, False, "/x/my.wav", True)
    assert s.auto_check_updates is True and s.skipped_update_version == "" and s.last_run_version == ""


def test_newer_settings_file_with_unknown_keys_survives_downgrade(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({**Settings().to_dict(), "future_option": 1, "volume": 12}))
    assert SettingsStore(path).load().volume == 12


def test_user_data_lives_outside_the_install_and_download_dirs(tmp_path):
    from utils.paths import config_dir, history_file, settings_file

    assert settings_file().parent == config_dir() == history_file().parent
    assert (config_dir() / "updates").parent == config_dir()  # downloads are disposable; data files are not in it
