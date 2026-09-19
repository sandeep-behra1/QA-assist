"""Value extraction from candidate segments.

Each extractor turns one segment's text into a typed observed value, or
None when the segment does not actually contain one. Extraction is kept
separate from comparison so that "the agent never said it" and "the agent
said the wrong thing" stay distinguishable all the way to the reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.enums import EvaluationMethod, ExtractionMethod
from app.models import TranscriptSegment
from app.services.normalization import (
    convert_to_unit,
    extract_boolean,
    extract_date,
    extract_email,
    extract_identifier,
    extract_numeric,
    extract_phone,
)


@dataclass(frozen=True)
class ExtractedValue:
    segment: TranscriptSegment
    value: Any
    extraction_method: str
    display: str

    @property
    def comparable(self) -> Any:
        """Canonical form used for equality and conflict detection."""
        if isinstance(self.value, str):
            return self.value.strip().lower()
        if isinstance(self.value, float):
            return round(self.value, 6)
        return self.value


def extract_values(
    method: str,
    segments: list[TranscriptSegment],
    config: dict | None = None,
    expected: Any = None,
    reference_date: date | None = None,
) -> list[ExtractedValue]:
    config = config or {}
    extracted: list[ExtractedValue] = []
    for segment in segments:
        result = _extract_one(method, segment, config, expected, reference_date)
        if result is not None:
            extracted.append(result)
    return extracted


def _extract_one(
    method: str,
    segment: TranscriptSegment,
    config: dict,
    expected: Any,
    reference_date: date | None,
) -> ExtractedValue | None:
    text = segment.text

    if method == EvaluationMethod.EMAIL.value:
        value = extract_email(text)
        if value is None:
            return None
        written = "@" in text
        return ExtractedValue(
            segment=segment,
            value=value,
            extraction_method=(
                ExtractionMethod.WRITTEN_EMAIL.value if written else ExtractionMethod.SPOKEN_EMAIL.value
            ),
            display=value,
        )

    if method == EvaluationMethod.NUMERIC.value:
        reading = extract_numeric(text, keywords=config.get("search_keywords"))
        if reading is None:
            return None
        value = convert_to_unit(reading, config.get("unit"))
        unit = config.get("unit") or ""
        return ExtractedValue(
            segment=segment,
            value=value,
            extraction_method=(
                ExtractionMethod.SPOKEN_NUMBER.value
                if reading.spoken
                else ExtractionMethod.WRITTEN_NUMBER.value
            ),
            display=f"{value:g} {unit}".strip(),
        )

    if method == EvaluationMethod.DATE.value:
        value = extract_date(text, reference_year=reference_date.year if reference_date else None)
        if value is None:
            return None
        return ExtractedValue(
            segment=segment,
            value=value,
            extraction_method=ExtractionMethod.DATE_PARSE.value,
            display=value.isoformat(),
        )

    if method == EvaluationMethod.BOOLEAN.value:
        value = extract_boolean(text)
        if value is None:
            return None
        return ExtractedValue(
            segment=segment,
            value=value,
            extraction_method=ExtractionMethod.BOOLEAN_PARSE.value,
            display="true" if value else "false",
        )

    if method == EvaluationMethod.IDENTIFIER.value:
        if config.get("identifier_type") == "PHONE":
            value = extract_phone(text)
        else:
            value = extract_identifier(
                text,
                min_length=int(config.get("min_length", 6)),
                expected=str(expected) if expected is not None else None,
            )
        if value is None:
            return None
        return ExtractedValue(
            segment=segment,
            value=value,
            extraction_method=ExtractionMethod.IDENTIFIER_PARSE.value,
            display=value,
        )

    return None


def distinct_values(extracted: list[ExtractedValue]) -> list[Any]:
    seen: list[Any] = []
    for item in extracted:
        if item.comparable not in seen:
            seen.append(item.comparable)
    return seen
