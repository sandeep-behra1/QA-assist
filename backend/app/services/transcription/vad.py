"""Speech-activity alignment for dual-channel recordings.

Whisper's segment timestamps are approximate: they tend to snap to the edges of
its 30-second processing windows and to run across neighbouring silence. That
is not good enough when a reviewer clicks "play evidence" and expects to hear
the quoted words. On a dual-channel call each party is on their own channel,
so the moments they are actually speaking can be measured directly from the
audio, with no model involved.

Alignment only ever CLAMPS a segment inward to the measured speech; it never
extends a segment to include other speech, so it cannot make a line claim
words that belong to a different turn.
"""

from __future__ import annotations

import io
import wave
from array import array
from dataclasses import dataclass

FRAME_SECONDS = 0.02
MIN_GAP_SECONDS = 0.25  # silences shorter than this do not split a region
MIN_REGION_SECONDS = 0.15
MATCH_SLACK_SECONDS = 0.3


@dataclass(frozen=True)
class Region:
    start: float
    end: float


def speech_regions(mono_wav: bytes) -> list[Region]:
    """Contiguous stretches of speech on a mono 16-bit WAV."""
    with wave.open(io.BytesIO(mono_wav), "rb") as reader:
        if reader.getsampwidth() != 2 or reader.getnchannels() != 1:
            return []
        rate = reader.getframerate()
        samples = array("h")
        samples.frombytes(reader.readframes(reader.getnframes()))

    frame_len = max(1, int(rate * FRAME_SECONDS))
    energies: list[float] = []
    for offset in range(0, len(samples) - frame_len + 1, frame_len):
        chunk = samples[offset : offset + frame_len]
        energies.append((sum(x * x for x in chunk) / frame_len) ** 0.5)
    if not energies:
        return []

    peak = max(energies)
    if peak < 150:  # effectively silent channel
        return []
    ordered = sorted(energies)
    noise_floor = ordered[len(ordered) // 5]
    threshold = max(peak * 0.03, noise_floor * 4, 30.0)

    regions: list[Region] = []
    start: int | None = None
    last_active = 0
    max_gap_frames = int(MIN_GAP_SECONDS / FRAME_SECONDS)
    for index, energy in enumerate(energies):
        if energy > threshold:
            if start is None:
                start = index
            last_active = index
        elif start is not None and index - last_active > max_gap_frames:
            regions.append(Region(start * FRAME_SECONDS, (last_active + 1) * FRAME_SECONDS))
            start = None
    if start is not None:
        regions.append(Region(start * FRAME_SECONDS, (last_active + 1) * FRAME_SECONDS))
    return [r for r in regions if r.end - r.start >= MIN_REGION_SECONDS]


SPLIT_GAP_SECONDS = 1.0


def assign_region(start: float, end: float, regions: list[Region]) -> int | None:
    """Index of the speech region a word belongs to (most overlap, else nearest)."""
    if not regions:
        return None
    best, best_overlap = None, 0.0
    for index, region in enumerate(regions):
        overlap = min(end, region.end) - max(start, region.start)
        if overlap > best_overlap:
            best, best_overlap = index, overlap
    if best is not None:
        return best
    middle = (start + end) / 2
    return min(range(len(regions)), key=lambda i: abs((regions[i].start + regions[i].end) / 2 - middle))


def split_word_clusters(words: list[dict], regions: list[Region]) -> list[list[dict]]:
    """Group consecutive words, splitting where the channel was silent >= 1s.

    A speaker's channel is silent while the OTHER party talks, so a long gap
    inside one model segment means the model merged two separate turns.
    """
    if not words or not regions:
        return [words] if words else []
    clusters: list[list[dict]] = [[words[0]]]
    previous = assign_region(words[0]["start"], words[0]["end"], regions)
    for word in words[1:]:
        current = assign_region(word["start"], word["end"], regions)
        if (
            current is not None
            and previous is not None
            and current != previous
            and regions[current].start - regions[previous].end >= SPLIT_GAP_SECONDS
        ):
            clusters.append([word])
        else:
            clusters[-1].append(word)
        previous = current
    return clusters


def align_segments(segments, regions: list[Region]) -> int:
    """Clamp each segment inward to the speech regions it overlaps.

    ``segments`` need ``.start`` and ``.end`` attributes. Returns how many were
    adjusted. A segment matching no region is left exactly as the model gave it.
    """
    adjusted = 0
    for segment in segments:
        # A region belongs to the segment only if the segment really covers most of it. A region
        # that merely ends where the segment begins is the previous sentence, and matching it
        # would stop the start from being pulled forward to where this segment is spoken.
        matched = [
            r
            for r in regions
            if min(segment.end + MATCH_SLACK_SECONDS, r.end) - max(segment.start - MATCH_SLACK_SECONDS, r.start)
            >= 0.5 * (r.end - r.start)
            and (r.start + r.end) / 2 >= segment.start
            and (r.start + r.end) / 2 <= segment.end + MATCH_SLACK_SECONDS
        ]
        if not matched:
            continue
        first, last = min(r.start for r in matched), max(r.end for r in matched)
        new_start = max(segment.start, first) if segment.start <= last else segment.start
        new_end = min(segment.end, last) if segment.end >= first else segment.end
        if new_end > new_start and (round(new_start, 2), round(new_end, 2)) != (
            round(segment.start, 2),
            round(segment.end, 2),
        ):
            segment.start, segment.end = round(new_start, 2), round(new_end, 2)
            adjusted += 1
    return adjusted
