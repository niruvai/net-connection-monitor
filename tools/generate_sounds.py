"""Synthesizes the default alert sounds into assets/sounds/ (pure standard library).

    python tools/generate_sounds.py

* offline.wav   - loud two-tone air-horn blast ("TUUUUUT")
* reconnect.wav - a cartoonish "ha-ha-ha-ha-ha" laugh

Replace either file with your own WAV/MP3 (or point to a custom file in
Settings) - this script exists only so the defaults are reproducible.
"""
from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 44_100
OUT = Path(__file__).resolve().parent.parent / "assets" / "sounds"


def write_wav(path: Path, samples: list[float], peak: float = 0.95) -> None:
    top = max(abs(s) for s in samples) or 1.0
    scale = peak / top
    frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s * scale)) * 32767)) for s in samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(frames)
    print(f"wrote {path} ({len(samples) / RATE:.2f}s)")


def horn(duration: float = 1.5) -> list[float]:
    notes = (233.08, 311.13, 392.0)  # Bb3 / Eb4 / G4: a brash, slightly dissonant truck-horn chord
    total = int(duration * RATE)
    out = []
    for n in range(total):
        t = n / RATE
        attack = min(1.0, t / 0.012)
        release = min(1.0, (duration - t) / 0.18)
        env = attack * release
        drop = 1.0 - 0.04 * min(1.0, t / 0.08)  # tiny pitch fall right after the attack
        value = 0.0
        for f in notes:
            for h in range(1, 12, 2):  # odd harmonics: buzzy square-like timbre
                value += math.sin(2 * math.pi * f * drop * h * t) / h
        value *= 1.0 + 0.08 * math.sin(2 * math.pi * 24 * t)  # light reed flutter
        out.append(math.tanh(2.6 * value * env) * env)  # soft clip = loud and punchy
    return out


class Resonator:
    """Two-pole band-pass used to shape a buzzy source into a vowel."""

    def __init__(self, freq: float, bandwidth: float) -> None:
        r = math.exp(-math.pi * bandwidth / RATE)
        self.a1 = 2 * r * math.cos(2 * math.pi * freq / RATE)
        self.a2 = -r * r
        self.gain = 1 - r
        self.y1 = self.y2 = 0.0

    def process(self, x: float) -> float:
        y = self.gain * x + self.a1 * self.y1 + self.a2 * self.y2
        self.y2, self.y1 = self.y1, y
        return y


def laugh(syllables: int = 6) -> list[float]:
    rng = random.Random(7)
    f1, f2, f3 = Resonator(800, 90), Resonator(1250, 110), Resonator(2600, 200)
    out: list[float] = []
    phase = 0.0
    pitch = 330.0
    for i in range(syllables):
        length = 0.115 if i < syllables - 1 else 0.30
        gap = 0.075
        level = 1.0 - 0.07 * i
        n = int(length * RATE)
        for k in range(n):
            t = k / RATE
            frac = k / n
            f0 = pitch * (1.0 - 0.18 * frac) * (1.0 + 0.02 * math.sin(2 * math.pi * 7 * t))
            phase = (phase + f0 / RATE) % 1.0
            source = (1.0 - 2.0 * phase) + 0.15 * math.sin(2 * math.pi * phase * 2)  # sawtooth
            breath = rng.uniform(-1, 1) * (0.9 if t < 0.03 else 0.04)  # the "h" in "ha"
            x = source * (0.25 if t < 0.03 else 1.0) + breath
            env = min(1.0, t / 0.01) * min(1.0, (length - t) / 0.035)
            out.append((f1.process(x) + 0.7 * f2.process(x) + 0.25 * f3.process(x)) * env * level * 6)
        out.extend(f1.process(0) * 0 for _ in range(int(gap * RATE)))
        pitch *= 0.93
    out.extend([0.0] * int(0.1 * RATE))
    return [math.tanh(1.5 * s) for s in out]


if __name__ == "__main__":
    write_wav(OUT / "offline.wav", horn())
    write_wav(OUT / "reconnect.wav", laugh())
