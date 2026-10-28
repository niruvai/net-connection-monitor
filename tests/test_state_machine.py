from core.models import ConnectionState as S
from core.state_machine import ConnectionStateMachine


def feed(machine, values):
    return [machine.update(v) for v in values]


def test_first_success_goes_online_from_unknown():
    m = ConnectionStateMachine()
    t = m.update(True)
    assert (t.previous, t.current) == (S.UNKNOWN, S.ONLINE)
    assert not t.is_reconnect


def test_single_failure_is_not_enough_to_go_offline():
    m = ConnectionStateMachine(failure_threshold=2)
    m.update(True)
    assert m.update(False) is None
    assert m.state is S.ONLINE
    assert m.is_verifying_failure


def test_one_blip_between_successes_never_alerts():
    m = ConnectionStateMachine(failure_threshold=2)
    results = feed(m, [True, False, True, False, True, True])
    assert [r for r in results[1:] if r] == []
    assert m.state is S.ONLINE


def test_offline_fires_once_while_failures_continue():
    m = ConnectionStateMachine(failure_threshold=2)
    m.update(True)
    transitions = [t for t in feed(m, [False] * 10) if t]
    assert len(transitions) == 1 and transitions[0].went_offline


def test_reconnect_fires_once_and_is_flagged_as_reconnect():
    m = ConnectionStateMachine(failure_threshold=2)
    feed(m, [True, False, False])
    transitions = [t for t in feed(m, [True] * 5) if t]
    assert len(transitions) == 1
    assert transitions[0].is_reconnect


def test_unknown_to_offline_after_threshold():
    m = ConnectionStateMachine(failure_threshold=3)
    assert feed(m, [False, False]) == [None, None]
    assert m.update(False).previous is S.UNKNOWN


def test_success_threshold_requires_consecutive_successes():
    m = ConnectionStateMachine(failure_threshold=1, success_threshold=2)
    feed(m, [True, True, False])
    assert m.state is S.OFFLINE
    assert m.update(True) is None
    assert m.update(False) is None  # flapping resets the success streak
    assert m.update(True) is None
    assert m.update(True).is_reconnect


def test_clear_counters_keeps_state():
    m = ConnectionStateMachine(failure_threshold=2)
    feed(m, [True, False])
    m.clear_counters()
    assert m.state is S.ONLINE
    assert m.update(False) is None
