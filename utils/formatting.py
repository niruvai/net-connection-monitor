"""Small display helpers shared by the UI and notifications."""
from __future__ import annotations

from datetime import datetime


def format_duration(seconds: float | None) -> str:
    """``73`` -> ``01:13``; ``3725`` -> ``1:02:05``; ``2 days`` -> ``2d 00:00:00``."""
    if seconds is None:
        return "—"
    total = max(0, int(seconds))
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours:02d}:{minutes:02d}:{secs:02d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration_words(seconds: float | None) -> str:
    """Human wording used in alerts: ``1 min 13 s``."""
    if seconds is None:
        return "—"
    total = max(0, int(round(seconds)))
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if secs or not parts:
        parts.append(f"{secs} s")
    return " ".join(parts)


def format_speed(bytes_per_second: float | None) -> str:
    if bytes_per_second is None:
        return "—"
    bits = max(0.0, bytes_per_second) * 8
    if bits >= 1_000_000_000:
        return f"{bits / 1_000_000_000:.2f} Gbps"
    if bits >= 1_000_000:
        return f"{bits / 1_000_000:.1f} Mbps"
    return f"{bits / 1_000:.0f} Kbps"


def format_latency(milliseconds: float | None) -> str:
    if milliseconds is None:
        return "—"
    if milliseconds < 10:
        return f"{milliseconds:.1f} ms"
    return f"{milliseconds:.0f} ms"


def format_clock(moment: datetime | None) -> str:
    """Time of day, with the date only when it is not today."""
    if moment is None:
        return "—"
    moment = moment.astimezone()
    if moment.date() == datetime.now().astimezone().date():
        return moment.strftime("%H:%M:%S")
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def format_datetime(moment: datetime | None) -> str:
    if moment is None:
        return "—"
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_size(num_bytes: float | None) -> str:
    if num_bytes is None:
        return "—"
    size = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
