from datetime import datetime, timedelta, timezone

from core.history import MAX_ENTRIES, HistoryEntry, OutageHistory
from core.models import ConnectionState as S
from core.session import SessionTracker
from core.settings import Settings, SettingsStore
from utils.formatting import format_clock, format_duration, format_duration_words, format_latency, format_speed


def test_settings_defaults_match_spec():
    s = Settings()
    assert s.check_interval == 2.0 and s.sounds_enabled and s.auto_start_monitoring


def test_settings_are_clamped_and_coerced():
    s = Settings.from_dict({"check_interval": 0, "volume": 900, "dark_mode": 0, "bogus": 1, "offline_sound": None})
    assert s.check_interval == 0.5 and s.volume == 100 and s.dark_mode is False
    assert s.offline_sound == ""
    assert Settings.from_dict({"check_interval": "abc"}).check_interval == 2.0


def test_settings_roundtrip_and_corrupt_file(tmp_path):
    store = SettingsStore(tmp_path / "s.json")
    assert store.load() == Settings()
    store.save(Settings(volume=33, dark_mode=False))
    assert store.load().volume == 33
    (tmp_path / "s.json").write_text("{not json")
    assert store.load() == Settings()
    assert (tmp_path / "s.corrupt").exists()


def test_history_persists_clears_and_caps(tmp_path):
    path = tmp_path / "h.json"
    now = datetime.now(timezone.utc)
    h = OutageHistory(path)
    h.add(HistoryEntry(now, now + timedelta(seconds=30), 30))
    assert len(OutageHistory(path)) == 1
    assert OutageHistory(path).total_downtime == 30
    h.clear()
    assert len(OutageHistory(path)) == 0
    for _ in range(MAX_ENTRIES + 5):
        h.add(HistoryEntry(now, now, 1))
    assert len(h) == MAX_ENTRIES


def test_history_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "h.json"
    path.write_text("[{\"oops\": 1}]")
    assert len(OutageHistory(path)) == 0


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_session_tracks_outage_and_totals():
    clock = Clock()
    history = OutageHistory(None)
    s = SessionTracker(history, clock=clock)
    s.mark_online()
    clock.t += 50
    assert s.uptime() == 50 and s.current_downtime() is None

    s.mark_offline()
    assert s.state is S.OFFLINE and s.uptime() is None
    clock.t += 12
    assert s.current_downtime() == 12
    assert s.disconnect_count() == 1  # the outage in progress counts
    assert s.total_downtime() == 12

    entry = s.mark_online()
    assert entry.duration == 12
    assert s.disconnect_count() == 1 and s.total_downtime() == 12
    assert s.last_outage_duration == 12 and s.last_reconnect is not None

    s.mark_offline()
    clock.t += 8
    s.mark_online()
    assert s.disconnect_count() == 2 and s.total_downtime() == 20


def test_first_online_does_not_create_history():
    s = SessionTracker(OutageHistory(None))
    assert s.mark_online() is None
    assert len(s.history) == 0


def test_formatting():
    assert format_duration(None) == "—"
    assert format_duration(73) == "01:13"
    assert format_duration(3725) == "1:02:05"
    assert format_duration(90_000) == "1d 01:00:00"
    assert format_duration_words(73) == "1 min 13 s"
    assert format_duration_words(0) == "0 s"
    assert format_duration_words(3600) == "1 h"
    assert format_speed(125_000) == "1.0 Mbps"
    assert format_speed(10) == "0 Kbps"
    assert format_speed(None) == "—"
    assert format_latency(4.26) == "4.3 ms" and format_latency(23.4) == "23 ms"
    assert format_clock(None) == "—"
    assert len(format_clock(datetime.now().astimezone())) == 8
