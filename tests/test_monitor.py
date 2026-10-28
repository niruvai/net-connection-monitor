import time

from tests.conftest import ScriptedChecker, wait_until
from core.models import ConnectionState as S
from core.monitor import NetworkMonitor


class Recorder:
    def __init__(self):
        self.checks = []
        self.transitions = []
        self.adapter_changes = 0

    def on_check(self, r):
        self.checks.append(r)

    def on_transition(self, t, r):
        self.transitions.append(t)

    def on_adapter(self):
        self.adapter_changes += 1


def make(checker, rec=None, **kw):
    rec = rec or Recorder()
    kw.setdefault("interval", 0.05)
    kw.setdefault("recheck_delay", 0.02)
    m = NetworkMonitor(checker, on_check=rec.on_check, on_transition=rec.on_transition, on_adapter_change=rec.on_adapter, **kw)
    return m, rec


def test_offline_and_reconnect_each_reported_exactly_once():
    checker = ScriptedChecker(True)
    m, rec = make(checker)
    m.start()
    try:
        assert wait_until(lambda: m.state is S.ONLINE)
        checker.reachable = False
        assert wait_until(lambda: m.state is S.OFFLINE)
        n = len(rec.checks)
        assert wait_until(lambda: len(rec.checks) > n + 8)  # many more failed checks...
        checker.reachable = True
        assert wait_until(lambda: m.state is S.ONLINE)
        assert wait_until(lambda: len(rec.checks) > n + 12)
    finally:
        m.stop()
    kinds = [(t.previous, t.current) for t in rec.transitions]
    assert kinds == [(S.UNKNOWN, S.ONLINE), (S.ONLINE, S.OFFLINE), (S.OFFLINE, S.ONLINE)]


def test_single_failed_cycle_does_not_declare_offline():
    results = iter([True, False, True])
    checker = ScriptedChecker(True)

    class Flaky:
        def check(self_inner):
            try:
                value = next(results)
            except StopIteration:
                value = True
            checker.reachable = value
            return checker.check()

    m, rec = make(Flaky())
    m.start()
    try:
        assert wait_until(lambda: len(rec.checks) >= 8)
    finally:
        m.stop()
    assert all(not t.went_offline for t in rec.transitions)


def test_pause_stops_checks_and_resume_continues():
    checker = ScriptedChecker(True)
    m, rec = make(checker)
    m.start()
    try:
        assert wait_until(lambda: len(rec.checks) >= 2)
        m.pause()
        time.sleep(0.2)
        frozen = checker.calls
        time.sleep(0.3)
        assert checker.calls == frozen
        assert m.paused
        m.resume()
        assert wait_until(lambda: checker.calls > frozen + 2)
    finally:
        m.stop()


def test_start_paused_does_not_check_until_resumed():
    checker = ScriptedChecker(True)
    m, rec = make(checker)
    m.start(paused=True)
    try:
        time.sleep(0.3)
        assert checker.calls == 0
        m.resume()
        assert wait_until(lambda: checker.calls > 0)
    finally:
        m.stop()


def test_stop_is_prompt_even_with_long_interval():
    m, _ = make(ScriptedChecker(True), interval=60)
    m.start()
    time.sleep(0.1)
    start = time.monotonic()
    m.stop()
    assert time.monotonic() - start < 1.0
    assert not m.running


def test_set_interval_wakes_sleeping_loop():
    checker = ScriptedChecker(True)
    m, _ = make(checker, interval=60)
    m.start()
    try:
        assert wait_until(lambda: checker.calls == 1)
        m.set_interval(0.05)
        assert wait_until(lambda: checker.calls >= 3)
    finally:
        m.stop()


def test_adapter_change_triggers_immediate_recheck():
    checker = ScriptedChecker(True)
    signature = {"v": 1}
    m, rec = make(checker, interval=60, signature_provider=lambda: signature["v"])
    m.start()
    try:
        assert wait_until(lambda: checker.calls == 1)
        signature["v"] = 2
        assert wait_until(lambda: checker.calls == 2, timeout=3)
        assert rec.adapter_changes == 1
    finally:
        m.stop()


def test_checker_exception_does_not_kill_thread():
    class Crashy:
        calls = 0

        def check(self):
            Crashy.calls += 1
            if Crashy.calls < 3:
                raise RuntimeError("socket exploded")
            return ScriptedChecker(True).check()

    m, rec = make(Crashy())
    m.start()
    try:
        assert wait_until(lambda: m.state is S.ONLINE, timeout=3)
    finally:
        m.stop()


def test_callback_exception_does_not_kill_thread():
    checker = ScriptedChecker(True)

    def bad(*_):
        raise ValueError("ui bug")

    m = NetworkMonitor(checker, interval=0.03, on_check=bad, on_transition=bad)
    m.start()
    try:
        assert wait_until(lambda: checker.calls >= 4)
        assert m.running
    finally:
        m.stop()


def test_slow_check_runs_off_the_calling_thread():
    checker = ScriptedChecker(True, delay=0.5)
    m, _ = make(checker)
    start = time.monotonic()
    m.start()
    m.pause()
    m.resume()
    m.set_interval(1)
    assert time.monotonic() - start < 0.1  # control calls never wait for a check
    m.stop()
