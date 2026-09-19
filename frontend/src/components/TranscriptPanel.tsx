import { useEffect, useRef } from "react";
import type { Transcript } from "../types";
import { AudioTime } from "./Common";

interface Props {
  transcript: Transcript;
  highlightedSegmentIds: number[];
  /** Present only when the sale has a recording; timestamps become playable. */
  onPlayRange?: (start: number, end: number) => void;
  asrFloor?: number;
}

export function TranscriptPanel({
  transcript,
  highlightedSegmentIds,
  onPlayRange,
  asrFloor = 0.6,
}: Props) {
  const refs = useRef<Record<number, HTMLDivElement | null>>({});

  useEffect(() => {
    const first = highlightedSegmentIds[0];
    if (first === undefined) return;
    refs.current[first]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightedSegmentIds]);

  return (
    <div className="transcript-panel">
      <div className="transcript-meta">
        Transcript #{transcript.transcript_id} · {transcript.source} · {transcript.language} ·{" "}
        {transcript.segments.length} segments
      </div>
      <div className="transcript-scroll">
        {transcript.segments.map((segment) => {
          const highlighted = highlightedSegmentIds.includes(segment.segment_id);
          const lowConfidence = segment.asr_confidence !== null && segment.asr_confidence < asrFloor;
          return (
            <div
              key={segment.segment_id}
              ref={(element) => {
                refs.current[segment.segment_id] = element;
              }}
              className={`transcript-segment ${highlighted ? "transcript-highlighted" : ""}`}
            >
              <div className="transcript-line-head">
                <AudioTime start={segment.start_time} end={segment.end_time} onPlay={onPlayRange} />
                <span className={`transcript-speaker speaker-${segment.speaker.toLowerCase()}`}>
                  {segment.speaker}
                </span>
                <span className="transcript-segment-id">#{segment.segment_id}</span>
                {lowConfidence && (
                  <span className="tag tag-warning" title="Low transcription confidence">
                    ASR {(segment.asr_confidence! * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <div className="transcript-text">{segment.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
