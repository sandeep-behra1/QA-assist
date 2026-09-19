"""Transcription providers.

Every provider returns the same thing -- a list of timed segments with an
optional speaker -- and knows nothing about scoring. Swapping in Deepgram,
Azure or a CIMET pipeline means writing one more class with this shape.

Two are included:

  groq      Live speech-to-text via Groq's Whisper. For dual-channel WAVs each
            channel is transcribed separately and attributed to its role, which
            is deterministic diarisation. Mono audio comes back with UNKNOWN
            speakers, which downstream checks treat conservatively.

  embedded  Offline, no ASR. Reads the transcript embedded in the generated demo
            recordings. It is a demo convenience, labelled as such everywhere,
            and it exists so a demo still works with no network or key.
"""

from __future__ import annotations

import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings
from app.core.enums import DiarizationMode, Speaker
from app.services.llm.interpreter import (
    MAX_RETRIES,
    RETRYABLE_STATUS,
    USER_AGENT,
    _describe_failure,
    _read_error_body,
    _suggested_wait,
)
from app.services.transcription import vad, wav

# Audio calls may legitimately be asked to wait longer than a chat call.
MAX_STT_RETRY_WAIT_SECONDS = 20.0

# Channel convention for dual-channel recordings: left = agent, right = customer.
DEFAULT_CHANNEL_ROLES = {0: Speaker.AGENT.value, 1: Speaker.CUSTOMER.value}


class TranscriptionError(RuntimeError):
    pass


@dataclass
class RawSegment:
    start: float
    end: float
    text: str
    confidence: float | None = None
    speaker: str | None = None
    channel: int | None = None


_NUMBER_WORDS = {
    "zero", "oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "double", "triple", "point", "dot",
}
_MAX_OVERLAP_WORDS = 8
_OVERLAP_GAP_SECONDS = 0.6


def _tokens(text: str) -> list[str]:
    return [t.strip(".,!?;:\"'").lower() for t in text.split()]


def dedupe_boundary_overlaps(segments: list[RawSegment]) -> list[RawSegment]:
    """Remove words the model repeated where two of its segments overlap.

    Whisper sometimes ends one segment with the words the next one begins with.
    Only the earlier copy is trimmed, only between neighbours on the same channel
    that touch in time, and never when the repeated words could be figures read
    out (digits or number words), so a genuinely repeated value is left alone.
    """
    ordered = sorted(segments, key=lambda s: (s.channel if s.channel is not None else -1, s.start))
    result: list[RawSegment] = []
    for index, current in enumerate(ordered):
        following = ordered[index + 1] if index + 1 < len(ordered) else None
        if following is not None and following.channel == current.channel and (
            following.start - current.end <= _OVERLAP_GAP_SECONDS
        ):
            a_words, b_words = current.text.split(), _tokens(following.text)
            a_tokens = _tokens(current.text)
            for size in range(min(len(a_tokens), len(b_words), _MAX_OVERLAP_WORDS), 0, -1):
                tail = a_tokens[-size:]
                if tail != b_words[:size]:
                    continue
                if any(any(ch.isdigit() for ch in t) or t in _NUMBER_WORDS for t in tail):
                    break
                current = RawSegment(
                    start=current.start,
                    end=current.end,
                    text=" ".join(a_words[:-size]).strip(),
                    confidence=current.confidence,
                    speaker=current.speaker,
                    channel=current.channel,
                )
                break
        if current.text:
            result.append(current)
    return result


@dataclass
class ProviderResult:
    segments: list[RawSegment]
    provider: str
    model: str | None
    language: str
    diarization: DiarizationMode
    latency_ms: float
    duration_seconds: float | None = None
    channels: int | None = None
    warnings: list[str] = field(default_factory=list)


class TranscriptionProvider(Protocol):
    key: str
    label: str

    def ready(self) -> bool: ...

    def transcribe(self, audio: bytes, filename: str, content_type: str | None) -> ProviderResult: ...


# ---------------------------------------------------------------------------
# Embedded (offline) provider
# ---------------------------------------------------------------------------


class EmbeddedTranscriptProvider:
    key = "embedded"
    label = "Demo embedded transcript (offline, no speech recognition)"

    def ready(self) -> bool:
        return True

    def transcribe(self, audio: bytes, filename: str, content_type: str | None) -> ProviderResult:
        started = time.perf_counter()
        payload = wav.extract_embedded_transcript(audio)
        if payload is None:
            raise TranscriptionError(
                "This file has no embedded transcript. It was not generated by the demo tool; "
                "use live transcription (Groq) instead."
            )
        segments: list[RawSegment] = []
        for raw in payload.get("segments", []):
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            segments.append(
                RawSegment(
                    start=float(raw["start_time"]),
                    end=float(raw["end_time"]),
                    text=text,
                    confidence=raw.get("asr_confidence"),
                    speaker=str(raw.get("speaker", Speaker.UNKNOWN.value)),
                )
            )
        info = wav.read_wav_info(audio)
        return ProviderResult(
            segments=segments,
            provider=self.key,
            model="embedded-demo-transcript",
            language=str(payload.get("language", "en-AU")),
            diarization=DiarizationMode.EMBEDDED,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            duration_seconds=info.duration_seconds if info else None,
            channels=info.channels if info else None,
            warnings=["Transcript was read from the demo file, not produced by speech recognition."],
        )


# ---------------------------------------------------------------------------
# Groq Whisper provider
# ---------------------------------------------------------------------------


def _multipart(fields: list[tuple[str, str]], filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = f"----cimet{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class GroqWhisperProvider:
    key = "groq"

    # A silent channel is exactly where Whisper hallucinates ("Thank you.").
    # Segments the model itself flags as probably-not-speech are dropped, and
    # the count is reported rather than hidden.
    NO_SPEECH_THRESHOLD = 0.6
    COMPRESSION_THRESHOLD = 2.4

    def __init__(self, settings: Settings, channel_roles: dict[int, str] | None = None):
        self._settings = settings
        self._roles = channel_roles or DEFAULT_CHANNEL_ROLES

    @property
    def label(self) -> str:
        return f"Groq Whisper live speech recognition ({self._settings.groq_stt_model})"

    def ready(self) -> bool:
        return self._settings.stt_ready

    def transcribe(self, audio: bytes, filename: str, content_type: str | None) -> ProviderResult:
        if not self.ready():
            raise TranscriptionError("GROQ_API_KEY is not set, so live transcription is unavailable.")

        started = time.perf_counter()
        info = wav.read_wav_info(audio)
        warnings: list[str] = []
        segments: list[RawSegment] = []
        dropped = 0

        if info and info.channels >= 2 and info.sample_width == 2:
            channel_audio = wav.split_channels(audio)
            realigned = 0
            for channel, mono in enumerate(channel_audio[: len(self._roles)]):
                body = self._call(mono, f"channel{channel}.wav", "audio/wav")
                kept, skipped = self._segments(body, channel=channel, speaker=self._roles.get(channel))
                regions = vad.speech_regions(mono)
                kept = self._split_merged_turns(kept, body.get("words") or [], regions)
                kept = dedupe_boundary_overlaps(kept)
                realigned += vad.align_segments(kept, regions)
                segments.extend(kept)
                dropped += skipped
            diarization = DiarizationMode.CHANNEL
            if realigned:
                warnings.append(
                    f"{realigned} timestamp(s) were aligned to the measured speech on each channel "
                    "(the model's own timestamps are approximate)."
                )
        else:
            body = self._call(audio, filename, content_type or _guess_type(filename))
            kept, dropped = self._segments(body, channel=None, speaker=Speaker.UNKNOWN.value)
            segments.extend(kept)
            diarization = DiarizationMode.NONE
            warnings.append(
                "Single-channel audio: speakers could not be separated, so every line is UNKNOWN. "
                "Checks that depend on who spoke will resolve to UNCERTAIN. Use a dual-channel "
                "recording (agent and customer on separate channels) for full checking."
            )

        if dropped:
            warnings.append(f"{dropped} segment(s) were discarded as probable non-speech or repetition.")

        return ProviderResult(
            segments=segments,
            provider=self.key,
            model=self._settings.groq_stt_model,
            language="en-AU",
            diarization=diarization,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            duration_seconds=info.duration_seconds if info else None,
            channels=info.channels if info else None,
            warnings=warnings,
        )

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _split_merged_turns(segments: list[RawSegment], words: list[dict], regions) -> list[RawSegment]:
        """Undo the model merging a speaker's lines across the other party's turns."""
        if not words or not regions:
            return segments
        result: list[RawSegment] = []
        claimed: set[int] = set()  # a word on a segment boundary belongs to one segment only
        for segment in segments:
            inside = []
            for index, w in enumerate(words):
                middle = (float(w["start"]) + float(w["end"])) / 2
                if index not in claimed and segment.start - 0.05 <= middle <= segment.end + 0.05:
                    claimed.add(index)
                    inside.append(w)
            clusters = vad.split_word_clusters(
                [{"word": w["word"], "start": float(w["start"]), "end": float(w["end"])} for w in inside],
                regions,
            )
            if len(clusters) < 2:
                result.append(segment)
                continue
            # Word entries carry no leading space of their own, so they are joined explicitly.
            texts = [" ".join(str(w["word"]).strip() for w in cluster if str(w["word"]).strip()) for cluster in clusters]
            original, rebuilt = _tokens(segment.text), _tokens(" ".join(texts))
            if rebuilt != original[: len(rebuilt)]:
                result.append(segment)  # the words do not reproduce the segment: do not guess
                continue
            if len(rebuilt) < len(original):
                # Words just past the segment's end time were not claimed; they belong on the last line.
                texts[-1] = f"{texts[-1]} {' '.join(segment.text.split()[len(rebuilt):])}".strip()
            for cluster, text in zip(clusters, texts):
                if text:
                    result.append(
                        RawSegment(
                            start=cluster[0]["start"],
                            end=cluster[-1]["end"],
                            text=text,
                            confidence=segment.confidence,
                            speaker=segment.speaker,
                            channel=segment.channel,
                        )
                    )
        return result

    def _segments(self, body: dict, channel: int | None, speaker: str | None) -> tuple[list[RawSegment], int]:
        kept: list[RawSegment] = []
        dropped = 0
        for item in body.get("segments") or []:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            if (
                float(item.get("no_speech_prob", 0.0)) > self.NO_SPEECH_THRESHOLD
                or float(item.get("compression_ratio", 0.0)) > self.COMPRESSION_THRESHOLD
            ):
                dropped += 1
                continue
            logprob = item.get("avg_logprob")
            confidence = _confidence_from_logprob(float(logprob)) if logprob is not None else None
            kept.append(
                RawSegment(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    text=text,
                    confidence=confidence,
                    speaker=speaker,
                    channel=channel,
                )
            )
        return kept, dropped

    def _call(self, audio: bytes, filename: str, content_type: str) -> dict:
        settings = self._settings
        fields = [
            ("model", settings.groq_stt_model),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "segment"),
            # Word times let a merged segment be split back into separate turns.
            ("timestamp_granularities[]", "word"),
            ("temperature", "0"),
            ("language", "en"),
            # No "prompt" hint: a style prompt leaked its own words into the transcript
            # ("Prices are you moving in" for "When are you moving in"). A transcript that
            # a check reads must contain only what was said.
        ]
        body, header = _multipart(fields, filename, content_type, audio)
        request = urllib.request.Request(
            f"{settings.groq_base_url.rstrip('/')}/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": header,
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
            method="POST",
        )
        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=settings.transcription_timeout_seconds) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as exc:
                exc.cached_body = _read_error_body(exc)  # type: ignore[attr-defined]
                if exc.code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                    wait = _suggested_wait(exc, attempt)
                    if wait <= MAX_STT_RETRY_WAIT_SECONDS:
                        time.sleep(wait)
                        continue
                raise TranscriptionError(f"Groq transcription failed: {_describe_failure(exc)}") from exc
            except (OSError, ValueError) as exc:
                raise TranscriptionError(f"Groq transcription failed: {_describe_failure(exc)}") from exc
        raise TranscriptionError("Groq transcription failed after retries.")  # pragma: no cover


# Whisper itself treats a segment with avg_logprob below -1.0 as unreliable, and
# clean speech typically sits above about -0.3. exp(avg_logprob) is not a good
# confidence (clean short answers score ~0.6), so map that documented range
# linearly onto 0..1. This is a calibration choice, not a probability.
_LOGPROB_UNRELIABLE = -1.0
_LOGPROB_CLEAN = -0.3


def _confidence_from_logprob(avg_logprob: float) -> float:
    scaled = (avg_logprob - _LOGPROB_UNRELIABLE) / (_LOGPROB_CLEAN - _LOGPROB_UNRELIABLE)
    return round(max(0.0, min(1.0, scaled)), 2)


def _guess_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
