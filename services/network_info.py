"""Local network facts: interface fingerprint, throughput, and IP addresses.

Everything here is cheap and non-blocking except ``fetch_public_ip`` (an HTTPS
request), which callers must run off the GUI thread.
"""
from __future__ import annotations

import http.client
import logging
import re
import socket
import time
from typing import Callable, Hashable

import psutil

from core.connectivity import _ssl_context

log = logging.getLogger(__name__)

_LOOPBACK_PREFIXES = ("lo",)


def interface_signature() -> Hashable:
    """Fingerprint of usable interfaces + their IPv4 addresses; changes when adapters change."""
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except Exception:
        return None
    parts = []
    for name, st in sorted(stats.items()):
        if not st.isup or name.lower().startswith(_LOOPBACK_PREFIXES):
            continue
        ips = sorted(a.address for a in addrs.get(name, []) if a.family == socket.AF_INET)
        if ips:
            parts.append((name, tuple(ips)))
    return tuple(parts)


def local_ip() -> str | None:
    """Address of the interface used for the default route. Sends no packets."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            ip = sock.getsockname()[0]
        return None if ip.startswith("0.") else ip
    except OSError:
        return None


_IP_SOURCES = (("api.ipify.org", "/"), ("icanhazip.com", "/"), ("checkip.amazonaws.com", "/"))
_IP_RE = re.compile(r"^[0-9a-fA-F:.]{3,45}$")


def fetch_public_ip(timeout: float = 4.0) -> str | None:
    for host, path in _IP_SOURCES:
        conn = http.client.HTTPSConnection(host, timeout=timeout, context=_ssl_context())
        try:
            conn.request("GET", path, headers={"User-Agent": "NetWatcher/1.0"})
            resp = conn.getresponse()
            body = resp.read(128).decode("ascii", "ignore").strip()
            if resp.status == 200 and _IP_RE.match(body):
                return body
        except (OSError, http.client.HTTPException):
            continue
        finally:
            conn.close()
    return None


class ThroughputSampler:
    """Live download/upload rate from OS interface counters (no test traffic is generated)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, counters: Callable | None = None) -> None:
        self._clock = clock
        self._counters = counters or self._read_counters
        self._last: tuple[float, int, int] | None = None

    @staticmethod
    def _read_counters() -> tuple[int, int]:
        sent = recv = 0
        for name, io in psutil.net_io_counters(pernic=True).items():
            if name.lower().startswith(_LOOPBACK_PREFIXES):
                continue
            sent += io.bytes_sent
            recv += io.bytes_recv
        return sent, recv

    def sample(self) -> tuple[float, float] | None:
        """Return ``(download_Bps, upload_Bps)`` since the previous call, or None on the first call."""
        try:
            sent, recv = self._counters()
        except Exception:
            log.debug("Could not read interface counters", exc_info=True)
            return None
        now = self._clock()
        previous, self._last = self._last, (now, sent, recv)
        if previous is None:
            return None
        elapsed = now - previous[0]
        if elapsed <= 0:
            return None
        # Counters can reset when an adapter disappears/reappears; clamp to zero instead of going negative.
        return max(0, recv - previous[2]) / elapsed, max(0, sent - previous[1]) / elapsed

    def reset(self) -> None:
        self._last = None
