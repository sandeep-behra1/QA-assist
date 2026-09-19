"""Synthetic call audio for the demo.

The seed has no real recordings, so this renders a stand-in WAV from a
transcript's own timings: a soft tone while each speaker is "talking"
(a different pitch for AGENT and CUSTOMER) and silence in the gaps. That makes
the timestamps shown against each check audibly meaningful -- seek to an
evidence quote and you hear the right speaker at the right moment, and dead
air is genuinely silent.

It is placeholder audio for demonstration only; there is no speech in it.
"""

from __future__ import annotations

import io
import math
import struct
import wave

SAMPLE_RATE = 8000
_TONES_HZ = {"AGENT": 330.0, "CUSTOMER": 220.0}
_AMPLITUDE = 0.18


def render_call_audio(segments: list[dict], duration_seconds: float) -> bytes:
    total = int(duration_seconds * SAMPLE_RATE)
    samples = [0] * total

    for segment in segments:
        frequency = _TONES_HZ.get(segment["speaker"], 180.0)
        start = max(0, int(segment["start_time"] * SAMPLE_RATE))
        end = min(total, int(segment["end_time"] * SAMPLE_RATE))
        for index in range(start, end):
            # Short fade in/out so segment edges do not click.
            edge = min(index - start, end - index, 400) / 400
            value = math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
            samples[index] = int(value * _AMPLITUDE * edge * 32767)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack(f"<{total}h", *samples))
    return buffer.getvalue()
