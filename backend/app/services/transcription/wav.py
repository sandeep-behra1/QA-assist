"""WAV helpers: inspection, channel splitting, and an embedded-transcript chunk.

Call-centre recordings are normally dual-channel (agent on one channel,
customer on the other). Splitting the channels is what makes speaker
attribution deterministic: no model has to guess who said what.

The generated demo recordings additionally carry their own ground-truth
transcript in a private RIFF chunk ("cimt"). Every standard player and reader
ignores unknown chunks, so the file still plays normally, while the offline
"embedded" provider can read the exact timestamps back out.
"""

from __future__ import annotations

import io
import json
import struct
import sys
import wave
from array import array
from dataclasses import dataclass

EMBED_CHUNK_ID = b"cimt"


class WavError(ValueError):
    pass


@dataclass(frozen=True)
class WavInfo:
    channels: int
    sample_rate: int
    sample_width: int
    frames: int

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0


def read_wav_info(data: bytes) -> WavInfo | None:
    """Basic PCM WAV facts, or None if this is not a WAV the stdlib can read."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(data), "rb") as reader:
            return WavInfo(
                channels=reader.getnchannels(),
                sample_rate=reader.getframerate(),
                sample_width=reader.getsampwidth(),
                frames=reader.getnframes(),
            )
    except (wave.Error, EOFError):
        return None


def split_channels(data: bytes) -> list[bytes]:
    """Return one mono 16-bit WAV per channel of a multi-channel 16-bit WAV."""
    with wave.open(io.BytesIO(data), "rb") as reader:
        channels = reader.getnchannels()
        width = reader.getsampwidth()
        rate = reader.getframerate()
        frames = reader.readframes(reader.getnframes())

    if width != 2:
        raise WavError("Only 16-bit PCM WAV files can be split into channels.")
    if channels < 2:
        return [data]

    samples = array("h")
    samples.frombytes(frames)
    if sys.byteorder == "big":  # WAV is little-endian
        samples.byteswap()

    outputs: list[bytes] = []
    for index in range(channels):
        mono = array("h", samples[index::channels])
        if sys.byteorder == "big":
            mono.byteswap()
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(1)
            writer.setsampwidth(2)
            writer.setframerate(rate)
            writer.writeframes(mono.tobytes())
        outputs.append(buffer.getvalue())
    return outputs


def embed_transcript(wav_bytes: bytes, payload: dict) -> bytes:
    """Append the transcript as a private "cimt" chunk and fix the RIFF size."""
    if wav_bytes[:4] != b"RIFF":
        raise WavError("Not a RIFF/WAV file.")
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    chunk = EMBED_CHUNK_ID + struct.pack("<I", len(body)) + body
    if len(body) % 2:
        chunk += b"\x00"  # RIFF chunks are word-aligned
    combined = bytearray(wav_bytes) + chunk
    struct.pack_into("<I", combined, 4, len(combined) - 8)
    return bytes(combined)


def extract_embedded_transcript(wav_bytes: bytes) -> dict | None:
    """Read the private transcript chunk back out, or None if there isn't one."""
    if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
        return None
    position = 12
    while position + 8 <= len(wav_bytes):
        chunk_id = wav_bytes[position : position + 4]
        (size,) = struct.unpack_from("<I", wav_bytes, position + 4)
        start = position + 8
        if chunk_id == EMBED_CHUNK_ID:
            try:
                return json.loads(wav_bytes[start : start + size].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return None
        position = start + size + (size % 2)
    return None
