"""Render a scenario to a stereo WAV using the offline Windows voices.

Each turn is synthesised on its own, its real duration is measured, and the
turns are laid out on a timeline from those durations. The agent goes on the
left channel and the customer on the right, so the result is a dual-channel
recording exactly like a call-centre system produces, and the transcript
timestamps are the measured ones, not estimates.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from app.demo.scenarios import Scenario
from app.demo.script import AGENT, Placed, Turn, layout, to_segments
from app.services.transcription.wav import embed_transcript

SAMPLE_RATE = 16000
VOICES = {"David": "Microsoft David Desktop", "Zira": "Microsoft Zira Desktop"}
_SPEAKING_RATE = {AGENT: 1, "CUSTOMER": 0}
TAIL_SECONDS = 1.2

_POWERSHELL = r"""
param([string]$JobFile)
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $JobFile | ConvertFrom-Json
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($job in $jobs) {
    $synth.SelectVoice($job.voice)
    $synth.Rate = [int]$job.rate
    $synth.SetOutputToWaveFile($job.out, $format)
    $synth.Speak($job.text)
    $synth.SetOutputToNull()
}
$synth.Dispose()
"""


class SynthesisError(RuntimeError):
    pass


@dataclass
class Rendered:
    wav_bytes: bytes
    segments: list[dict]
    duration_seconds: float


def _run_tts(jobs: list[dict], workdir: Path) -> None:
    if sys.platform != "win32":
        raise SynthesisError("The demo voices use Windows speech synthesis, so audio can only be generated on Windows.")
    job_file = workdir / "jobs.json"
    script_file = workdir / "synth.ps1"
    job_file.write_text(json.dumps(jobs, ensure_ascii=True), encoding="utf-8")
    script_file.write_text(_POWERSHELL, encoding="utf-8")
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script_file), "-JobFile", str(job_file)],
        capture_output=True, text=True, timeout=600,
    )
    if completed.returncode != 0:
        raise SynthesisError(f"Speech synthesis failed: {completed.stderr.strip() or completed.stdout.strip()}")


def _read_clip(path: Path) -> array:
    with wave.open(str(path), "rb") as reader:
        if (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise SynthesisError(f"Unexpected audio format from the synthesiser: {path.name}")
        clip = array("h")
        clip.frombytes(reader.readframes(reader.getnframes()))
    return clip


def render_scenario(scenario: Scenario) -> Rendered:
    turns: dict[int, Turn] = {i: item for i, item in enumerate(scenario.items) if isinstance(item, Turn)}

    with tempfile.TemporaryDirectory(prefix="cimet-tts-") as tmp:
        workdir = Path(tmp)
        jobs = []
        for index, turn in turns.items():
            voice = scenario.agent_voice if turn.speaker == AGENT else scenario.customer_voice
            jobs.append({
                "voice": VOICES[voice],
                "rate": _SPEAKING_RATE.get(turn.speaker, 0),
                "text": turn.speak or turn.text,
                "out": str(workdir / f"{index}.wav"),
            })
        _run_tts(jobs, workdir)
        clips = {index: _read_clip(workdir / f"{index}.wav") for index in turns}

    durations = {index: len(clip) / SAMPLE_RATE for index, clip in clips.items()}
    placed = layout(scenario.items, durations)
    return _mix(scenario, placed, clips)


def _mix(scenario: Scenario, placed: list[Placed], clips: dict[int, array]) -> Rendered:
    total_seconds = max(p.end for p in placed) + TAIL_SECONDS
    total = int(round(total_seconds * SAMPLE_RATE))
    left = array("h", bytes(2 * total))
    right = array("h", bytes(2 * total))

    for item in placed:
        clip = clips[item.turn_index]
        start = int(round(item.start * SAMPLE_RATE))
        channel = left if item.speaker == AGENT else right
        channel[start : start + len(clip)] = clip

    stereo = array("h", bytes(4 * total))
    stereo[0::2] = left
    stereo[1::2] = right

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(stereo.tobytes())

    segments = to_segments(placed)
    payload = {
        "format": "cimet-embedded-transcript/1",
        "scenario": scenario.key,
        "language": "en-AU",
        "channel_roles": {"0": "AGENT", "1": "CUSTOMER"},
        "segments": segments,
    }
    return Rendered(embed_transcript(buffer.getvalue(), payload), segments, total_seconds)
