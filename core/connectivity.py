"""Internet reachability probes.

Each probe tests one endpoint over a different mechanism. A check cycle is
"reachable" if *any* probe succeeds, so a single dead endpoint or a broken DNS
resolver can never be mistaken for a lost connection:

* ``TcpProbe``   - TCP handshake with a well-known public IP (no DNS needed)
* ``DnsProbe``   - UDP DNS query sent straight to a public resolver
* ``HttpsProbe`` - HTTPS ``generate_204`` request (also rejects captive portals)
"""
from __future__ import annotations

import http.client
import logging
import queue
import random
import socket
import ssl
import struct
import threading
import time
from typing import Protocol, Sequence

from core.models import CheckResult, ProbeResult

log = logging.getLogger(__name__)


class Probe(Protocol):
    name: str

    def check(self, timeout: float) -> ProbeResult: ...


class TcpProbe:
    def __init__(self, host: str, port: int = 443) -> None:
        self.host, self.port = host, port
        self.name = f"tcp:{host}:{port}"

    def check(self, timeout: float) -> ProbeResult:
        start = time.perf_counter()
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                pass
        except OSError as exc:
            return ProbeResult(self.name, False, error=_short_error(exc))
        return ProbeResult(self.name, True, (time.perf_counter() - start) * 1000)


def build_dns_query(hostname: str, query_id: int | None = None) -> tuple[int, bytes]:
    qid = random.randrange(0, 0x10000) if query_id is None else query_id
    header = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)  # recursion desired, 1 question
    question = b"".join(bytes([len(p)]) + p.encode("ascii") for p in hostname.strip(".").split("."))
    return qid, header + question + b"\x00" + struct.pack("!HH", 1, 1)  # A record, class IN


def is_dns_response(data: bytes, query_id: int) -> bool:
    if len(data) < 12:
        return False
    rid, flags = struct.unpack("!HH", data[:4])
    return rid == query_id and bool(flags & 0x8000)


class DnsProbe:
    """Sends a raw DNS query to a specific resolver; any matching reply proves connectivity."""

    def __init__(self, resolver: str = "1.1.1.1", hostname: str = "www.google.com") -> None:
        self.resolver, self.hostname = resolver, hostname
        self.name = f"dns:{resolver}"

    def check(self, timeout: float) -> ProbeResult:
        qid, packet = build_dns_query(self.hostname)
        start = time.perf_counter()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(packet, (self.resolver, 53))
                while True:
                    data, _ = sock.recvfrom(512)
                    if is_dns_response(data, qid):
                        break
        except OSError as exc:
            return ProbeResult(self.name, False, error=_short_error(exc))
        return ProbeResult(self.name, True, (time.perf_counter() - start) * 1000)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # certifi missing or unreadable: fall back to the OS trust store
        return ssl.create_default_context()


class HttpsProbe:
    """GET a ``generate_204`` URL. Redirects are *not* followed, so captive portals fail."""

    def __init__(self, host: str = "www.gstatic.com", path: str = "/generate_204", expect: int = 204) -> None:
        self.host, self.path, self.expect = host, path, expect
        self.name = f"https:{host}"
        self._context = _ssl_context()

    def check(self, timeout: float) -> ProbeResult:
        start = time.perf_counter()
        conn = http.client.HTTPSConnection(self.host, timeout=timeout, context=self._context)
        try:
            conn.request("GET", self.path, headers={"User-Agent": "NetWatcher/1.0", "Connection": "close"})
            status = conn.getresponse().status
        except (OSError, http.client.HTTPException) as exc:
            return ProbeResult(self.name, False, error=_short_error(exc))
        finally:
            conn.close()
        if status != self.expect:
            return ProbeResult(self.name, False, error=f"HTTP {status}")
        return ProbeResult(self.name, True, (time.perf_counter() - start) * 1000)


def _short_error(exc: BaseException) -> str:
    text = str(exc) or type(exc).__name__
    return text if len(text) <= 60 else text[:57] + "..."


def default_probes() -> list[Probe]:
    return [
        TcpProbe("1.1.1.1", 443),
        TcpProbe("8.8.8.8", 443),
        TcpProbe("9.9.9.9", 443),
        DnsProbe("1.1.1.1", "www.google.com"),
        DnsProbe("8.8.8.8", "www.cloudflare.com"),
        HttpsProbe("www.gstatic.com", "/generate_204"),
        HttpsProbe("cp.cloudflare.com", "/generate_204"),
    ]


class ConnectivityChecker:
    """Runs all probes concurrently and returns as soon as one succeeds."""

    def __init__(self, probes: Sequence[Probe] | None = None, timeout: float = 2.5) -> None:
        self.probes = list(probes) if probes is not None else default_probes()
        self.timeout = timeout

    def check(self) -> CheckResult:
        results: queue.Queue[ProbeResult] = queue.Queue()

        def run(probe: Probe) -> None:
            try:
                results.put(probe.check(self.timeout))
            except Exception as exc:  # a misbehaving probe must never kill the cycle
                log.exception("Probe %s crashed", probe.name)
                results.put(ProbeResult(probe.name, False, error=_short_error(exc)))

        for probe in self.probes:
            threading.Thread(target=run, args=(probe,), name=f"probe-{probe.name}", daemon=True).start()

        collected: list[ProbeResult] = []
        deadline = time.monotonic() + self.timeout + 1.0
        while len(collected) < len(self.probes):
            try:
                result = results.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                break
            collected.append(result)
            if result.ok:
                return CheckResult(True, result.latency_ms, tuple(collected))
        return CheckResult(False, None, tuple(collected))
