"""Single source of truth for the app version, plus version comparison.

Build scripts read ``__version__`` from this file (see packaging/), so bump it
here and nowhere else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

__version__ = "1.0.0"

_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){0,3})(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")


@dataclass(frozen=True)
class Version:
    """``1.2.3`` or ``1.2.3-beta.1``. A pre-release sorts before its final release."""

    release: tuple[int, ...]
    pre: tuple = ()  # empty = final release
    text: str = ""

    @classmethod
    def parse(cls, text: str) -> "Version":
        match = _VERSION_RE.match(str(text).strip())
        if not match:
            raise ValueError(f"invalid version: {text!r}")
        release = tuple(int(p) for p in match.group(1).split("."))
        pre = tuple(
            (0, int(part), "") if part.isdigit() else (1, 0, part) for part in (match.group(2) or "").split(".") if part
        )
        return cls(release, pre, str(text).strip().lstrip("v"))

    def _key(self):
        padded = self.release + (0,) * (4 - len(self.release))
        # final releases (no pre) must sort after any pre-release of the same number
        return padded, (1, ()) if not self.pre else (0, self.pre)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Version) and self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def __str__(self) -> str:
        return self.text


def parse_version(text: str) -> Version:
    return Version.parse(text)


def is_newer(candidate: str, current: str) -> bool:
    """True if ``candidate`` is a strictly newer version than ``current``."""
    return Version.parse(current) < Version.parse(candidate)
