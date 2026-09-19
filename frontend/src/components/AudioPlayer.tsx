import { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { formatTime } from "../utils/format";

export interface AudioPlayerHandle {
  seek: (seconds: number) => void;
  /** Play a window around a piece of evidence, with a little lead-in. */
  playRange: (start: number, end: number, padding?: number) => void;
}

interface Props {
  src: string;
  filename?: string | null;
  durationSeconds?: number | null;
}

/** Shown when a sale has no recording, so the panel never silently vanishes. */
export function AudioPlaceholder({
  onUpload,
  busy,
  error,
}: {
  onUpload: (file: File) => void;
  busy: boolean;
  error: string | null;
}) {
  return (
    <div className="audio-placeholder">
      <div className="audio-placeholder-icon" aria-hidden>
        ♫
      </div>
      <div className="audio-placeholder-body">
        <div className="audio-title">No call recording for this sale</div>
        <p className="muted">
          Timestamps shown against each check and transcript line are positions in the call. Attach
          the recording and they become playable.
        </p>
        <label className="btn-secondary btn-sm audio-upload">
          {busy ? "Uploading…" : "Upload recording"}
          <input
            type="file"
            accept=".wav,.mp3,.m4a,.aac,.ogg"
            disabled={busy}
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
        {error && <div className="audio-error">{error}</div>}
      </div>
    </div>
  );
}

export const AudioPlayer = forwardRef<AudioPlayerHandle, Props>(function AudioPlayer(
  { src, filename, durationSeconds },
  ref
) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const stopAtRef = useRef<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useImperativeHandle(ref, () => ({
    seek(seconds: number) {
      const audio = audioRef.current;
      if (!audio) return;
      stopAtRef.current = null;
      audio.currentTime = Math.max(0, seconds);
    },
    playRange(start: number, end: number, padding = 5) {
      const audio = audioRef.current;
      if (!audio) return;
      stopAtRef.current = end + padding;
      audio.currentTime = Math.max(0, start - padding);
      void audio.play().catch(() => setError("Playback was blocked by the browser."));
    },
  }));

  return (
    <div className="audio-player">
      <div className="audio-player-head">
        <span className="audio-title">Call recording</span>
        <span className="audio-meta">
          {filename ?? "recording"}
          {durationSeconds ? ` · ${formatTime(durationSeconds)}` : ""}
        </span>
      </div>
      <audio
        ref={audioRef}
        src={src}
        controls
        preload="metadata"
        onTimeUpdate={(event) => {
          const stopAt = stopAtRef.current;
          if (stopAt !== null && event.currentTarget.currentTime >= stopAt) {
            event.currentTarget.pause();
            stopAtRef.current = null;
          }
        }}
        onError={() => setError("The recording could not be loaded.")}
      />
      {error && <div className="audio-error">{error}</div>}
    </div>
  );
});
