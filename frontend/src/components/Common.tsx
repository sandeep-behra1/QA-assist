import type { ReactNode } from "react";
import { formatRange } from "../utils/format";

export function Card({
  title,
  action,
  children,
  className,
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className ?? ""}`}>
      {(title || action) && (
        <header className="card-header">
          {typeof title === "string" ? <h2 className="card-title">{title}</h2> : title}
          {action}
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: "approved" | "hold" | "review" | "neutral";
}) {
  return (
    <div className={`stat-card stat-${tone ?? "neutral"}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

export function Field({
  label,
  hint,
  children,
  required,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        {required && <span className="field-required"> *</span>}
      </span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

/**
 * A position in the call recording. Clickable (and labelled with a play
 * glyph) when audio exists for the sale; plain text otherwise, so the same
 * timestamp is still useful for locating the moment in the transcript.
 */
export function AudioTime({
  start,
  end,
  onPlay,
}: {
  start: number;
  end?: number;
  onPlay?: (start: number, end: number) => void;
}) {
  const label = formatRange(start, end);
  if (!onPlay) {
    return (
      <span className="audio-time" title="Position in the call">
        {label}
      </span>
    );
  }
  return (
    <button
      className="audio-time audio-time-link"
      title="Play this moment in the recording"
      onClick={(event) => {
        event.stopPropagation();
        onPlay(start, end ?? start);
      }}
    >
      ▶ {label}
    </button>
  );
}

export function Loading({ what = "data" }: { what?: string }) {
  return <div className="state-message">Loading {what}…</div>;
}

export function ErrorMessage({ message }: { message: string }) {
  return <div className="state-message state-error">{message}</div>;
}

export function EmptyState({ message }: { message: string }) {
  return <div className="state-message state-empty">{message}</div>;
}

export function DefinitionList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="definition-list">
      {items.map(([term, value]) => (
        <div key={term}>
          <dt>{term}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
