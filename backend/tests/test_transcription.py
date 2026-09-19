"""Transcription: WAV helpers, providers (network stubbed), jobs, attach and the API."""

from __future__ import annotations

import io
import json
import math
import urllib.error
import wave
from array import array

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import DEFAULT_GROQ_STT_MODEL, Settings
from app.services.transcription import service, wav
from app.services.transcription.providers import GroqWhisperProvider, TranscriptionError


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_wav(channels: int = 2, seconds: float = 3.0, rate: int = 8000) -> bytes:
    """A small PCM WAV: a tone on channel 0, silence elsewhere."""
    frames = int(seconds * rate)
    samples = array("h")
    for index in range(frames):
        tone = int(8000 * math.sin(2 * math.pi * 220 * index / rate))
        samples.append(tone)
        samples.extend([0] * (channels - 1))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(samples.tobytes())
    return buffer.getvalue()


SEGMENTS = [
    {"segment_id": 1, "speaker": "AGENT", "start_time": 0.2, "end_time": 2.0,
     "text": "This call may be recorded for quality and compliance purposes.", "asr_confidence": 0.97},
    {"segment_id": 2, "speaker": "CUSTOMER", "start_time": 2.4, "end_time": 3.0,
     "text": "Okay, go ahead.", "asr_confidence": 0.95},
]


def demo_wav(segments=None) -> bytes:
    payload = {"format": "cimet-embedded-transcript/1", "language": "en-AU", "segments": segments or SEGMENTS}
    return wav.embed_transcript(make_wav(), payload)


def upload(client: TestClient, data: bytes, provider: str | None = "embedded", name="call.wav"):
    form = {"provider": provider} if provider else {}
    return client.post(
        "/transcription-jobs", files={"file": (name, data, "audio/wav")}, data=form
    )


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def whisper_body(*segments) -> FakeResponse:
    return FakeResponse(json.dumps({"segments": list(segments)}).encode())


def seg(start, end, text, logprob=-0.1, no_speech=0.01, compression=1.2):
    return {"start": start, "end": end, "text": text, "avg_logprob": logprob,
            "no_speech_prob": no_speech, "compression_ratio": compression}


GROQ = Settings(groq_api_key="gsk_test_key", groq_stt_model=DEFAULT_GROQ_STT_MODEL)


@pytest.fixture
def groq_http(monkeypatch):
    """Stub Groq's transcription endpoint; queue responses per call."""
    state = {"queue": [], "requests": []}

    def fake_urlopen(request, timeout=None):
        state["requests"].append(request)
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("app.services.transcription.providers.time.sleep", lambda s: None)
    return state


# ---------------------------------------------------------------------------
# WAV helpers
# ---------------------------------------------------------------------------


def test_embedded_transcript_round_trips_and_the_file_still_plays():
    embedded = demo_wav()
    assert wav.extract_embedded_transcript(embedded)["segments"][0]["speaker"] == "AGENT"
    info = wav.read_wav_info(embedded)  # a standard reader still understands the file
    assert info is not None and info.channels == 2 and round(info.duration_seconds) == 3


def test_a_plain_wav_has_no_embedded_transcript():
    assert wav.extract_embedded_transcript(make_wav()) is None


def test_stereo_is_split_into_one_mono_wav_per_channel():
    left, right = wav.split_channels(make_wav(channels=2))
    left_info, right_info = wav.read_wav_info(left), wav.read_wav_info(right)
    assert left_info.channels == right_info.channels == 1
    assert left_info.frames == right_info.frames
    with wave.open(io.BytesIO(right), "rb") as reader:
        assert set(array("h", reader.readframes(100)).tolist()) == {0}  # the silent channel stays silent


# ---------------------------------------------------------------------------
# Groq provider (network stubbed)
# ---------------------------------------------------------------------------


def test_dual_channel_audio_attributes_speakers_by_channel(groq_http):
    groq_http["queue"] = [
        whisper_body(seg(0.2, 2.0, " This call may be recorded for quality."), seg(6.0, 8.0, " Thanks for your time.")),
        whisper_body(seg(2.4, 3.0, " Okay, go ahead."), seg(4.0, 5.5, " Yes that's right.")),
    ]
    result = GroqWhisperProvider(GROQ).transcribe(make_wav(channels=2), "call.wav", "audio/wav")

    assert len(groq_http["requests"]) == 2  # one call per channel
    by_speaker = {(s.speaker, s.text) for s in result.segments}
    assert ("AGENT", "This call may be recorded for quality.") in by_speaker
    assert ("CUSTOMER", "Okay, go ahead.") in by_speaker
    assert result.diarization.value == "CHANNEL"
    assert result.model == DEFAULT_GROQ_STT_MODEL
    assert result.channels == 2


def test_request_is_a_multipart_upload_to_the_groq_transcription_endpoint(groq_http):
    groq_http["queue"] = [whisper_body(seg(0, 1, " Hi")), whisper_body()]
    GroqWhisperProvider(GROQ).transcribe(make_wav(channels=2), "call.wav", "audio/wav")

    request = groq_http["requests"][0]
    assert request.full_url == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert request.get_header("Authorization") == "Bearer gsk_test_key"
    assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
    body = request.data.decode("latin-1")
    assert 'name="model"' in body and DEFAULT_GROQ_STT_MODEL in body
    assert "verbose_json" in body and 'name="file"; filename="channel0.wav"' in body


def test_probable_hallucinations_on_a_silent_channel_are_dropped_and_reported(groq_http):
    groq_http["queue"] = [
        whisper_body(seg(0.2, 2.0, " Real words here.")),
        whisper_body(seg(2.4, 3.0, " Thank you.", no_speech=0.93), seg(3.1, 4.0, " la la la la", compression=3.1)),
    ]
    result = GroqWhisperProvider(GROQ).transcribe(make_wav(channels=2), "call.wav", "audio/wav")

    assert [s.text for s in result.segments] == ["Real words here."]
    assert any("2 segment(s) were discarded" in w for w in result.warnings)


def test_whisper_log_probability_becomes_a_bounded_confidence(groq_http):
    groq_http["queue"] = [whisper_body(seg(0, 1, " Clear.", logprob=-0.05), seg(1, 2, " Murky.", logprob=-1.6)), whisper_body()]
    result = GroqWhisperProvider(GROQ).transcribe(make_wav(channels=2), "call.wav", "audio/wav")
    confidences = {s.text: s.confidence for s in result.segments}
    # Anchored to Whisper's own "unreliable below -1.0" threshold, clean above -0.3.
    assert confidences["Clear."] == 1.0
    assert confidences["Murky."] == 0.0


def test_a_mid_range_log_probability_maps_linearly():
    from app.services.transcription.providers import _confidence_from_logprob

    assert _confidence_from_logprob(-0.65) == 0.5
    assert _confidence_from_logprob(-1.0) == 0.0
    assert _confidence_from_logprob(-0.3) == 1.0
    assert 0.0 <= _confidence_from_logprob(-9.0) <= _confidence_from_logprob(0.5) <= 1.0


def test_mono_audio_makes_one_call_and_leaves_speakers_unknown(groq_http):
    groq_http["queue"] = [whisper_body(seg(0, 2, " Hello, is that the account holder?"))]
    result = GroqWhisperProvider(GROQ).transcribe(make_wav(channels=1), "call.wav", "audio/wav")

    assert len(groq_http["requests"]) == 1
    assert [s.speaker for s in result.segments] == ["UNKNOWN"]
    assert result.diarization.value == "NONE"
    assert any("Single-channel audio" in w for w in result.warnings)


def test_a_missing_key_fails_cleanly_without_a_network_call(groq_http):
    with pytest.raises(TranscriptionError, match="GROQ_API_KEY"):
        GroqWhisperProvider(Settings(groq_api_key=None)).transcribe(make_wav(), "call.wav", "audio/wav")
    assert groq_http["requests"] == []


def test_rate_limits_are_retried_after_the_provider_suggested_wait(groq_http):
    body = json.dumps({"error": {"message": "Please try again in 3s."}}).encode()
    limited = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, io.BytesIO(body))
    groq_http["queue"] = [limited, whisper_body(seg(0, 1, " Hello.")), whisper_body()]

    result = GroqWhisperProvider(GROQ).transcribe(make_wav(channels=2), "call.wav", "audio/wav")
    assert [s.text for s in result.segments] == ["Hello."]
    assert len(groq_http["requests"]) == 3


def test_a_provider_http_error_is_reported_as_a_transcription_error(groq_http):
    body = json.dumps({"error": {"message": "The model `x` does not exist. org_01abc"}}).encode()
    groq_http["queue"] = [urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(body))]
    with pytest.raises(TranscriptionError) as excinfo:
        GroqWhisperProvider(GROQ).transcribe(make_wav(channels=1), "call.wav", "audio/wav")
    assert "does not exist" in str(excinfo.value)
    assert "org_01abc" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Timestamp alignment and merged-turn splitting
# ---------------------------------------------------------------------------


def make_speech_wav(left: list[tuple[float, float]], right: list[tuple[float, float]], seconds=20.0, rate=8000) -> bytes:
    """Stereo WAV where each channel is a tone only inside its listed (start, end) spans."""

    def channel(spans, frequency):
        data = array("h", bytes(2 * int(seconds * rate)))
        for start, end in spans:
            for i in range(int(start * rate), int(end * rate)):
                data[i] = int(9000 * math.sin(2 * math.pi * frequency * i / rate))
        return data

    stereo = array("h", bytes(4 * int(seconds * rate)))
    stereo[0::2] = channel(left, 220)
    stereo[1::2] = channel(right, 330)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(stereo.tobytes())
    return buffer.getvalue()


def test_speech_regions_are_measured_from_the_channel_audio():
    from app.services.transcription import vad

    left, _ = wav.split_channels(make_speech_wav(left=[(1.0, 3.0), (6.0, 8.0)], right=[(3.5, 5.5)]))
    regions = vad.speech_regions(left)
    assert [(round(r.start, 1), round(r.end, 1)) for r in regions] == [(1.0, 3.0), (6.0, 8.0)]


def test_a_silent_channel_has_no_speech_regions():
    from app.services.transcription import vad

    _, right = wav.split_channels(make_speech_wav(left=[(1.0, 3.0)], right=[]))
    assert vad.speech_regions(right) == []


def test_model_timestamps_are_clamped_inward_to_the_measured_speech(groq_http):
    # Whisper says 0.0-9.0 for a line that is really spoken between 1.0s and 3.0s.
    audio = make_speech_wav(left=[(1.0, 3.0)], right=[(4.0, 5.0)])
    groq_http["queue"] = [whisper_body(seg(0.0, 9.0, " Hello there.")), whisper_body(seg(3.5, 6.0, " Hi."))]

    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    agent = next(s for s in result.segments if s.speaker == "AGENT")
    customer = next(s for s in result.segments if s.speaker == "CUSTOMER")
    assert (round(agent.start, 1), round(agent.end, 1)) == (1.0, 3.0)
    assert (round(customer.start, 1), round(customer.end, 1)) == (4.0, 5.0)
    assert any("aligned to the measured speech" in w for w in result.warnings)


def test_a_segment_merged_across_the_other_partys_turn_is_split_using_word_times(groq_http):
    """The model glued two customer replies together across the agent speaking."""
    audio = make_speech_wav(left=[(4.0, 8.0)], right=[(1.0, 2.5), (10.0, 12.0)])
    merged = {
        "start": 1.0, "end": 12.0, "text": " No life support. I'm moving in October.",
        "avg_logprob": -0.1, "no_speech_prob": 0.01, "compression_ratio": 1.2,
    }
    words = [
        {"word": " No", "start": 1.0, "end": 1.4}, {"word": " life", "start": 1.4, "end": 1.9},
        {"word": " support.", "start": 1.9, "end": 2.5},
        {"word": " I'm", "start": 10.0, "end": 10.4}, {"word": " moving", "start": 10.4, "end": 11.0},
        {"word": " in", "start": 11.0, "end": 11.3}, {"word": " October.", "start": 11.3, "end": 12.0},
    ]
    body = FakeResponse(json.dumps({"segments": [merged], "words": words}).encode())
    groq_http["queue"] = [whisper_body(), body]  # channel 0 (agent) empty, channel 1 (customer) merged

    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    customer = sorted((s for s in result.segments if s.speaker == "CUSTOMER"), key=lambda s: s.start)
    assert [s.text for s in customer] == ["No life support.", "I'm moving in October."]
    assert round(customer[1].start, 1) == 10.0  # the evidence now points at the right moment


def test_split_words_are_spaced_even_though_the_model_gives_them_without_spaces(groq_http):
    """Groq's word entries carry no leading space; joining them bare glued the call into one word."""
    audio = make_speech_wav(left=[(4.0, 8.0)], right=[(1.0, 2.5), (10.0, 12.0)])
    merged = {
        "start": 1.0, "end": 12.0, "text": " No life support. I'm moving in October.",
        "avg_logprob": -0.1, "no_speech_prob": 0.01, "compression_ratio": 1.2,
    }
    words = [
        {"word": "No", "start": 1.0, "end": 1.4}, {"word": "life", "start": 1.4, "end": 1.9},
        {"word": "support.", "start": 1.9, "end": 2.5},
        {"word": "I'm", "start": 10.0, "end": 10.4}, {"word": "moving", "start": 10.4, "end": 11.0},
        {"word": "in", "start": 11.0, "end": 11.3}, {"word": "October.", "start": 11.3, "end": 12.0},
    ]
    groq_http["queue"] = [whisper_body(), FakeResponse(json.dumps({"segments": [merged], "words": words}).encode())]
    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    customer = sorted((s for s in result.segments if s.speaker == "CUSTOMER"), key=lambda s: s.start)
    assert [s.text for s in customer] == ["No life support.", "I'm moving in October."]


def test_a_split_never_drops_the_last_word_of_a_line(groq_http):
    """The final word's timestamp can fall just past the segment end; it must still be kept."""
    audio = make_speech_wav(left=[(4.0, 8.0)], right=[(1.0, 2.5), (10.0, 12.0)])
    merged = {
        "start": 1.0, "end": 11.4, "text": " No life support. I'm moving in October.",
        "avg_logprob": -0.1, "no_speech_prob": 0.01, "compression_ratio": 1.2,
    }
    words = [
        {"word": "No", "start": 1.0, "end": 1.4}, {"word": "life", "start": 1.4, "end": 1.9},
        {"word": "support.", "start": 1.9, "end": 2.5},
        {"word": "I'm", "start": 10.0, "end": 10.4}, {"word": "moving", "start": 10.4, "end": 11.0},
        {"word": "in", "start": 11.0, "end": 11.3}, {"word": "October.", "start": 11.9, "end": 12.4},
    ]
    groq_http["queue"] = [whisper_body(), FakeResponse(json.dumps({"segments": [merged], "words": words}).encode())]
    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    customer = sorted((s for s in result.segments if s.speaker == "CUSTOMER"), key=lambda s: s.start)
    assert customer[-1].text == "I'm moving in October."


def test_a_line_is_pulled_forward_past_the_previous_sentences_speech():
    """A region ending exactly where a segment begins is the previous sentence, not this one."""
    from app.services.transcription import vad
    from app.services.transcription.providers import RawSegment

    regions = [vad.Region(49.6, 50.12), vad.Region(54.44, 57.94)]
    segment = RawSegment(start=50.12, end=57.88, text="Great.")
    vad.align_segments([segment], regions)
    assert segment.start == 54.44


def test_a_word_on_a_segment_boundary_is_not_repeated_in_the_next_segment(groq_http):
    """A merged turn is split; the boundary word must not also reappear at the start of its neighbour."""
    audio = make_speech_wav(left=[(4.0, 8.0)], right=[(1.0, 2.5), (10.0, 12.0)])
    first = {"start": 1.0, "end": 12.0, "text": " No life support. And", "avg_logprob": -0.1,
             "no_speech_prob": 0.01, "compression_ratio": 1.2}
    second = {"start": 10.0, "end": 12.0, "text": " And I'm moving in October.", "avg_logprob": -0.1,
              "no_speech_prob": 0.01, "compression_ratio": 1.2}
    words = [
        {"word": "No", "start": 1.0, "end": 1.4}, {"word": "life", "start": 1.4, "end": 1.9},
        {"word": "support.", "start": 1.9, "end": 2.5},
        {"word": "And", "start": 10.0, "end": 10.3}, {"word": "I'm", "start": 10.3, "end": 10.6},
        {"word": "moving", "start": 10.6, "end": 11.2}, {"word": "in", "start": 11.2, "end": 11.5},
        {"word": "October.", "start": 11.5, "end": 12.0},
    ]
    groq_http["queue"] = [whisper_body(), FakeResponse(json.dumps({"segments": [first, second], "words": words}).encode())]
    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    texts = [s.text for s in sorted((s for s in result.segments if s.speaker == "CUSTOMER"), key=lambda s: s.start)]
    assert sum(t.count("And") for t in texts) <= 1, texts


def test_a_segment_is_not_split_when_the_speaker_never_paused(groq_http):
    audio = make_speech_wav(left=[(1.0, 6.0)], right=[])
    line = {"start": 1.0, "end": 6.0, "text": " One long turn.", "avg_logprob": -0.1,
            "no_speech_prob": 0.01, "compression_ratio": 1.2}
    words = [{"word": " One", "start": 1.0, "end": 2.0}, {"word": " long", "start": 3.0, "end": 4.0},
             {"word": " turn.", "start": 4.5, "end": 6.0}]
    groq_http["queue"] = [FakeResponse(json.dumps({"segments": [line], "words": words}).encode()), whisper_body()]
    result = GroqWhisperProvider(GROQ).transcribe(audio, "call.wav", "audio/wav")
    assert [s.text for s in result.segments] == ["One long turn."]


# ---------------------------------------------------------------------------
# Jobs via the API
# ---------------------------------------------------------------------------


def test_providers_endpoint_reports_which_are_usable(client: TestClient):
    providers = {p["key"]: p for p in client.get("/transcription/providers").json()}
    assert providers["embedded"]["ready"] is True
    assert providers["groq"]["ready"] is False  # no key in the test environment


def test_embedded_job_returns_a_canonical_timestamped_transcript(client: TestClient):
    response = upload(client, demo_wav())
    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "COMPLETED"
    assert job["provider"] == "embedded" and job["diarization"] == "EMBEDDED"
    assert job["duration_seconds"] == pytest.approx(3.0, abs=0.1)
    assert [s["speaker"] for s in job["segments"]] == ["AGENT", "CUSTOMER"]
    assert job["segments"][0]["start_time"] == 0.2 and job["segments"][0]["end_time"] == 2.0
    assert any("not produced by speech recognition" in w for w in job["warnings"])


def test_a_recording_without_an_embedded_transcript_fails_with_a_reason(client: TestClient):
    job = upload(client, make_wav()).json()
    assert job["status"] == "FAILED"
    assert "no embedded transcript" in job["error"]
    assert job["segments"] == []
    assert client.get(f"/transcription-jobs/{job['id']}").json()["status"] == "FAILED"


def test_sensitive_values_are_redacted_before_the_job_is_stored(client: TestClient):
    payload = [
        {"segment_id": 1, "speaker": "CUSTOMER", "start_time": 0.0, "end_time": 2.0,
         "text": "My card is 4111 1111 1111 1111 and the code is 482913.", "asr_confidence": 0.9}
    ]
    job = upload(client, demo_wav(payload)).json()
    text = job["segments"][0]["text"]
    assert "4111" not in text and "482913" not in text and "[REDACTED]" in text


def test_default_provider_falls_back_to_embedded_when_no_groq_key(client: TestClient):
    assert upload(client, demo_wav(), provider=None).json()["provider"] == "embedded"


def test_unsupported_and_oversized_uploads_are_rejected(client: TestClient, monkeypatch):
    assert upload(client, b"hello", name="notes.txt").status_code == 415

    monkeypatch.setattr("app.api.transcription.get_settings", lambda: Settings(max_upload_bytes=1000))
    monkeypatch.setattr("app.services.transcription.service.get_settings", lambda: Settings(max_upload_bytes=1000))
    assert upload(client, demo_wav()).status_code == 413


def test_unknown_provider_is_a_client_error(client: TestClient):
    assert upload(client, demo_wav(), provider="deepgram").status_code == 422


# ---------------------------------------------------------------------------
# Attach + pipeline
# ---------------------------------------------------------------------------


def new_lead(client: TestClient) -> int:
    verticals = {v["code"]: v["id"] for v in client.get("/verticals").json()}
    aurora = next(r for r in client.get("/retailers").json() if r["code"] == "AURORA")
    response = client.post(
        "/leads",
        json={"vertical_id": verticals["ENERGY"], "retailer_id": aurora["id"],
              "call_datetime": "2026-09-18T10:00:00", "customer_name": "Attach Test"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_attaching_a_job_gives_the_lead_its_audio_and_transcript(seeded_client: TestClient):
    job = upload(seeded_client, demo_wav()).json()
    lead_id = new_lead(seeded_client)

    attached = seeded_client.post(f"/transcription-jobs/{job['id']}/attach", json={"lead_id": lead_id})
    assert attached.status_code == 200
    body = attached.json()
    assert body["source"] == "EMBEDDED_DEMO"
    assert [s["speaker"] for s in body["segments"]] == ["AGENT", "CUSTOMER"]

    lead = seeded_client.get(f"/leads/{lead_id}").json()
    assert lead["has_transcript"] and lead["has_audio"]
    assert lead["call"]["transcription_status"] == "AVAILABLE"
    assert lead["call"]["duration_seconds"] == pytest.approx(3.0, abs=0.1)

    audio = seeded_client.get(f"/leads/{lead_id}/audio")
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"

    events = {e["event_type"] for e in seeded_client.get(f"/leads/{lead_id}/audit-events").json()}
    assert {"AUDIO_UPLOADED", "TRANSCRIPT_UPLOADED"} <= events


def test_an_attached_transcript_flows_into_scoring(seeded_client: TestClient):
    job = upload(seeded_client, demo_wav()).json()
    lead_id = new_lead(seeded_client)
    seeded_client.post(f"/transcription-jobs/{job['id']}/attach", json={"lead_id": lead_id})

    run = seeded_client.post(f"/leads/{lead_id}/score").json()
    disclaimer = next(r for r in run["check_results"] if r["check_code"] == "RECORDING_DISCLAIMER")
    assert disclaimer["status"] == "PASS"
    assert disclaimer["evidence"][0]["start_time"] == 0.2  # the audio timestamp travels with the evidence
    assert run["gate_result"] in {"HOLD", "HUMAN_REVIEW"}  # nothing else was said, so it cannot approve


def test_a_job_cannot_be_attached_twice_or_when_failed(seeded_client: TestClient):
    job = upload(seeded_client, demo_wav()).json()
    first, second = new_lead(seeded_client), new_lead(seeded_client)
    assert seeded_client.post(f"/transcription-jobs/{job['id']}/attach", json={"lead_id": first}).status_code == 200
    assert seeded_client.post(f"/transcription-jobs/{job['id']}/attach", json={"lead_id": second}).status_code == 409

    failed = upload(seeded_client, make_wav()).json()
    assert seeded_client.post(f"/transcription-jobs/{failed['id']}/attach", json={"lead_id": first}).status_code == 409


def test_attach_to_an_unknown_lead_or_job_is_rejected(seeded_client: TestClient):
    job = upload(seeded_client, demo_wav()).json()
    assert seeded_client.post(f"/transcription-jobs/{job['id']}/attach", json={"lead_id": 1}).status_code == 409
    assert seeded_client.post("/transcription-jobs/nope/attach", json={"lead_id": 1}).status_code == 404


def test_transcribe_audio_button_works_on_a_sale_that_already_has_a_recording(seeded_client: TestClient):
    lead_id = new_lead(seeded_client)
    seeded_client.post(f"/leads/{lead_id}/audio", files={"file": ("call.wav", demo_wav(), "audio/wav")})
    assert seeded_client.get(f"/leads/{lead_id}").json()["call"]["transcription_status"] == "NOT_STARTED"

    job = seeded_client.post(f"/leads/{lead_id}/transcribe", json={"provider": "embedded"}).json()
    assert job["status"] == "COMPLETED"
    assert seeded_client.get(f"/leads/{lead_id}/transcript").json()["segments"][0]["speaker"] == "AGENT"
    assert seeded_client.get(f"/leads/{lead_id}").json()["call"]["transcription_status"] == "AVAILABLE"


def test_transcribe_audio_marks_the_call_failed_when_the_provider_fails(seeded_client: TestClient):
    lead_id = new_lead(seeded_client)
    seeded_client.post(f"/leads/{lead_id}/audio", files={"file": ("call.wav", make_wav(), "audio/wav")})

    job = seeded_client.post(f"/leads/{lead_id}/transcribe", json={"provider": "embedded"}).json()
    assert job["status"] == "FAILED"
    assert seeded_client.get(f"/leads/{lead_id}").json()["call"]["transcription_status"] == "FAILED"


def test_transcribing_a_sale_with_no_audio_is_refused(seeded_client: TestClient):
    assert seeded_client.post("/leads/3613827/transcribe", json={}).status_code == 409


def test_failed_transcription_is_audited(seeded_client: TestClient, seeded_db: Session):
    upload(seeded_client, make_wav())
    events = seeded_client.get("/audit-events?event_type=TRANSCRIPTION_FAILED").json()
    assert events and events[0]["details"]["provider"] == "embedded"


def test_service_lists_groq_as_unready_until_a_key_is_set():
    assert {p["key"]: p["ready"] for p in service.list_providers(Settings())} == {"groq": False, "embedded": True}
    assert service.list_providers(GROQ)[0]["ready"] is True
    assert service.default_provider_key(GROQ) == "groq"
    assert service.default_provider_key(Settings()) == "embedded"
