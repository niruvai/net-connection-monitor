import socket
import threading
import time

from core.connectivity import (
    ConnectivityChecker,
    DnsProbe,
    HttpsProbe,
    TcpProbe,
    build_dns_query,
    is_dns_response,
)
from core.models import ProbeResult


class FakeProbe:
    def __init__(self, name, ok, delay=0.0, latency=10.0, crash=False):
        self.name, self.ok, self.delay, self.latency, self.crash = name, ok, delay, latency, crash

    def check(self, timeout):
        time.sleep(self.delay)
        if self.crash:
            raise RuntimeError("boom")
        return ProbeResult(self.name, self.ok, self.latency if self.ok else None, None if self.ok else "down")


def test_reachable_if_any_probe_succeeds():
    checker = ConnectivityChecker([FakeProbe("a", False), FakeProbe("b", True, latency=33.0), FakeProbe("c", False)])
    result = checker.check()
    assert result.reachable
    assert result.latency_ms == 33.0


def test_offline_only_when_all_probes_fail():
    result = ConnectivityChecker([FakeProbe("a", False), FakeProbe("b", False)]).check()
    assert not result.reachable
    assert len(result.probes) == 2
    assert result.latency_ms is None


def test_returns_early_without_waiting_for_slow_probes():
    checker = ConnectivityChecker([FakeProbe("slow", False, delay=2.0), FakeProbe("fast", True)], timeout=3)
    start = time.monotonic()
    assert checker.check().reachable
    assert time.monotonic() - start < 1.0


def test_crashing_probe_is_treated_as_failure_not_exception():
    checker = ConnectivityChecker([FakeProbe("bad", True, crash=True), FakeProbe("ok", True, delay=0.05)])
    assert checker.check().reachable


def test_dns_failure_alone_does_not_cause_offline():
    """A broken resolver must not look like a lost connection when TCP still works."""
    checker = ConnectivityChecker([FakeProbe("dns:1.1.1.1", False), FakeProbe("tcp:1.1.1.1:443", True)])
    assert checker.check().reachable


def test_tcp_probe_against_local_server():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    try:
        ok = TcpProbe("127.0.0.1", port).check(1.0)
        assert ok.ok and ok.latency_ms is not None
    finally:
        server.close()
    assert not TcpProbe("127.0.0.1", port).check(1.0).ok


def test_dns_packet_roundtrip():
    qid, packet = build_dns_query("www.example.com", query_id=0x1234)
    assert qid == 0x1234 and packet[:2] == b"\x12\x34"
    assert packet.endswith(b"\x00\x00\x01\x00\x01")
    reply = b"\x12\x34\x81\x80" + b"\x00" * 8
    assert is_dns_response(reply, 0x1234)
    assert not is_dns_response(reply, 0x9999)
    assert not is_dns_response(b"\x12\x34\x01\x00" + b"\x00" * 8, 0x1234)  # a query, not a reply


def test_dns_probe_with_local_fake_resolver():
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(2)

    def serve():
        data, addr = server.recvfrom(512)
        server.sendto(data[:2] + b"\x81\x80" + data[4:], addr)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    probe = DnsProbe("127.0.0.1")
    # DnsProbe always targets port 53; verify packet handling by pointing a raw client at our server.
    qid, packet = build_dns_query("example.com")
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.settimeout(2)
    client.sendto(packet, server.getsockname())
    data, _ = client.recvfrom(512)
    assert is_dns_response(data, qid)
    assert probe.name == "dns:127.0.0.1"
    client.close()
    server.close()


def test_unreachable_endpoints_fail_fast_and_cleanly():
    assert not DnsProbe("127.0.0.1").check(0.3).ok  # nothing listens on :53 locally
    assert not HttpsProbe("localhost").check(0.5).ok
