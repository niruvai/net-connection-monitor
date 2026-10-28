import time

from tests.conftest import ScriptedChecker, wait_until
from core.models import ConnectionState as S


def run(controller, qapp, predicate, timeout=5.0):
    return wait_until(predicate, timeout, app=qapp)


def test_full_outage_cycle_plays_each_sound_exactly_once(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker, settings={"check_interval": 0.5})
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    assert c.fake_audio.played == []  # first ONLINE is not a reconnect
    assert c.fake_notifier.sent == []

    checker.reachable = False
    assert run(c, qapp, lambda: c.state is S.OFFLINE)
    calls = checker.calls
    assert run(c, qapp, lambda: checker.calls > calls + 10)  # lots more failed checks while offline
    assert c.fake_audio.played == ["offline"]
    assert len(c.fake_notifier.sent) == 1 and "DISCONNECTED" in c.fake_notifier.sent[0][0]
    assert c.session.current_downtime() is not None
    assert c.session.disconnect_count() == 1

    time.sleep(0.15)
    checker.reachable = True
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    calls = checker.calls
    assert run(c, qapp, lambda: checker.calls > calls + 10)
    assert c.fake_audio.played == ["offline", "reconnect"]
    assert "BACK" in c.fake_notifier.sent[1][0]
    assert len(c.history) == 1
    entry = c.history.entries[0]
    assert entry.duration >= 0.1 and entry.reconnected_at > entry.disconnected_at
    assert c.session.uptime() is not None and c.session.current_downtime() is None


def test_repeated_outages_alert_every_time(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    for i in range(1, 4):
        checker.reachable = False
        assert run(c, qapp, lambda: c.state is S.OFFLINE)
        checker.reachable = True
        assert run(c, qapp, lambda: c.state is S.ONLINE)
        assert c.fake_audio.played.count("offline") == i
        assert c.fake_audio.played.count("reconnect") == i
    assert len(c.history) == 3
    assert c.session.disconnect_count() == 3


def test_started_offline_alerts_once(make_controller, qapp):
    checker = ScriptedChecker(False)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.OFFLINE)
    calls = checker.calls
    assert run(c, qapp, lambda: checker.calls > calls + 8)
    assert c.fake_audio.played == ["offline"]


def test_sounds_disabled_still_tracks_state(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker, settings={"sounds_enabled": False, "notifications_enabled": False})
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    checker.reachable = False
    assert run(c, qapp, lambda: c.state is S.OFFLINE)
    checker.reachable = True
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    assert c.fake_audio.played == [] and c.fake_notifier.sent == []
    assert len(c.history) == 1


def test_auto_start_monitoring_off_starts_paused(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker, settings={"auto_start_monitoring": False})
    c.start()
    time.sleep(0.3)
    assert c.paused and checker.calls == 0
    c.set_paused(False)
    assert run(c, qapp, lambda: c.state is S.ONLINE)


def test_pause_prevents_alerts(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    c.set_paused(True)
    time.sleep(0.1)
    checker.reachable = False
    time.sleep(0.4)
    qapp.processEvents()
    assert c.state is S.ONLINE and c.fake_audio.played == []
    c.set_paused(False)
    assert run(c, qapp, lambda: c.state is S.OFFLINE)


def test_settings_apply_live_and_persist(make_controller, qapp):
    c = make_controller(ScriptedChecker(True))
    seen = []
    c.settings_changed.connect(seen.append)
    c.update_settings(check_interval=7, volume=35, sounds_enabled=False, launch_at_login=True, dark_mode=False)
    assert c.monitor._monitor.interval == 7
    assert c.fake_audio.volume == 35 and not c.fake_audio.enabled
    assert c._autostart.value is True
    assert seen and seen[-1].dark_mode is False
    assert c.store.load().volume == 35
    c.update_settings(check_interval=9999)
    assert c.settings.check_interval == 120


def test_clear_history_resets_counters(make_controller, qapp):
    checker = ScriptedChecker(True)
    c = make_controller(checker)
    c.monitor.set_interval(0.03)
    c.start()
    assert run(c, qapp, lambda: c.state is S.ONLINE)
    checker.reachable = False
    assert run(c, qapp, lambda: c.state is S.OFFLINE)
    checker.reachable = True
    assert run(c, qapp, lambda: len(c.history) == 1)
    c.clear_history()
    assert len(c.history) == 0 and c.session.disconnect_count() == 0
    assert c.session.last_reconnect is None


def test_gui_thread_never_blocks_on_slow_checks(make_controller, qapp):
    """The checker sleeps 0.6s per cycle; the Qt event loop must keep ticking meanwhile."""
    checker = ScriptedChecker(True, delay=0.6)
    c = make_controller(checker)
    c.start()
    worst = 0.0
    end = time.monotonic() + 1.5
    last = time.monotonic()
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
        now = time.monotonic()
        worst = max(worst, now - last)
        last = now
    assert checker.calls >= 1
    assert worst < 0.1, f"event loop stalled for {worst:.3f}s"


def test_shutdown_stops_monitor_thread(make_controller, qapp):
    c = make_controller(ScriptedChecker(True, delay=0.2))
    c.start()
    time.sleep(0.1)
    start = time.monotonic()
    c.shutdown()
    assert time.monotonic() - start < 2
    assert not c.monitor.running
