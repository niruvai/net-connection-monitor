import plistlib
import wave

import pytest

from services import autostart_service
from services.network_info import ThroughputSampler, interface_signature, local_ip
from utils.paths import default_sound_path


@pytest.mark.parametrize("kind", ["offline", "reconnect"])
def test_default_sounds_are_valid_wavs(kind):
    path = default_sound_path(kind)
    assert path.is_file()
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getnframes() > w.getframerate() * 0.5


def test_throughput_sampler_rates_and_counter_reset():
    t = {"now": 0.0}
    counters = {"v": (0, 0)}
    s = ThroughputSampler(clock=lambda: t["now"], counters=lambda: counters["v"])
    assert s.sample() is None
    t["now"], counters["v"] = 2.0, (1000, 4000)  # sent, recv
    down, up = s.sample()
    assert (down, up) == (2000.0, 500.0)
    t["now"], counters["v"] = 3.0, (10, 20)  # adapter reset -> counters dropped
    assert s.sample() == (0.0, 0.0)


def test_interface_helpers_do_not_raise():
    assert interface_signature() is not None
    local_ip()


def test_autostart_payloads():
    cmd = ["/Apps/Net Watcher.app/Contents/MacOS/NetWatcher", "--minimized"]
    plist = plistlib.loads(autostart_service.macos_plist(cmd))
    assert plist["ProgramArguments"] == cmd and plist["RunAtLoad"] is True
    assert autostart_service.windows_run_value(cmd).startswith('"/Apps/Net Watcher.app')
    assert "Exec=" in autostart_service.linux_desktop_entry(cmd)
    assert "--minimized" in autostart_service.launch_command()


def test_autostart_enable_disable_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert not autostart_service.is_enabled()
    assert autostart_service.set_enabled(True)
    assert autostart_service.is_enabled()
    assert autostart_service.set_enabled(False)
    assert not autostart_service.is_enabled()
