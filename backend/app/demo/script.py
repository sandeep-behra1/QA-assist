"""Call script model and timeline layout.

A call is a list of turns (someone speaks) and silences (nobody speaks). The
layout function turns that plus a duration per turn into timestamped segments.
The generator feeds it REAL durations measured from synthesised speech, so the
transcript timestamps match the audio exactly; tests feed it estimated
durations, so scenarios can be checked without any text-to-speech.
"""

from __future__ import annotations

from dataclasses import dataclass

AGENT = "AGENT"
CUSTOMER = "CUSTOMER"

DEFAULT_PAUSE = 0.55
SAME_SPEAKER_PAUSE = 0.3
WORDS_PER_SECOND = 2.7  # used only when no real audio duration exists


@dataclass(frozen=True)
class Turn:
    speaker: str
    text: str
    # What the voice actually says, when that differs from the transcript text
    # ("NMI" is read "N M I"; "14" is read "fourteen").
    speak: str | None = None
    pause_before: float | None = None
    # Start this many seconds before the previous turn ends: an interruption.
    overlap: float = 0.0


@dataclass(frozen=True)
class Silence:
    seconds: float


Item = Turn | Silence


@dataclass(frozen=True)
class Placed:
    speaker: str
    text: str
    start: float
    end: float
    turn_index: int


def A(text: str, speak: str | None = None, pause: float | None = None) -> Turn:
    return Turn(AGENT, text, speak, pause)


def C(text: str, speak: str | None = None, pause: float | None = None, overlap: float = 0.0) -> Turn:
    return Turn(CUSTOMER, text, speak, pause, overlap)


def estimate_duration(turn: Turn) -> float:
    words = len((turn.speak or turn.text).split())
    return max(1.0, words / WORDS_PER_SECOND + 0.35)


def layout(items: list[Item], durations: dict[int, float] | None = None, lead_in: float = 0.6) -> list[Placed]:
    """Place turns on a timeline. ``durations`` maps item index -> seconds."""
    placed: list[Placed] = []
    cursor = lead_in
    previous_speaker: str | None = None

    for index, item in enumerate(items):
        if isinstance(item, Silence):
            cursor += item.seconds
            previous_speaker = None
            continue

        duration = (durations or {}).get(index) or estimate_duration(item)
        if item.pause_before is not None:
            gap = item.pause_before
        elif previous_speaker == item.speaker:
            gap = SAME_SPEAKER_PAUSE
        else:
            gap = DEFAULT_PAUSE
        start = cursor + gap - item.overlap if placed else cursor
        start = max(start, 0.0)
        end = start + duration
        placed.append(Placed(item.speaker, item.text, round(start, 2), round(end, 2), index))
        cursor = max(cursor, end)
        previous_speaker = item.speaker

    return placed


def to_segments(placed: list[Placed], confidence: float = 0.97) -> list[dict]:
    """Canonical transcript segments, numbered in time order."""
    ordered = sorted(placed, key=lambda p: (p.start, p.end))
    return [
        {
            "segment_id": number,
            "speaker": item.speaker,
            "start_time": item.start,
            "end_time": item.end,
            "text": item.text,
            "asr_confidence": confidence,
        }
        for number, item in enumerate(ordered, start=1)
    ]


def spell_digits(digits: str) -> str:
    """Speakable digit groups: "6102001234" -> "six one zero two, zero zero one, two three four"."""
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    spoken = [words[int(d)] for d in digits if d.isdigit()]
    groups = [spoken[0:4], spoken[4:7], spoken[7:]]
    return ", ".join(" ".join(group) for group in groups if group)
