import type { CheckStatus, ConfidenceLevel, GateDecision } from "../types";
import { GATE_LABELS, STATUS_ICONS, STATUS_LABELS } from "../utils/format";

export function GateBadge({ decision, size }: { decision: GateDecision | null; size?: "lg" }) {
  if (!decision) {
    return <span className="badge badge-muted">Not scored</span>;
  }
  return (
    <span className={`badge gate-${decision.toLowerCase()} ${size === "lg" ? "badge-lg" : ""}`}>
      {GATE_LABELS[decision]}
    </span>
  );
}

export function StatusBadge({ status }: { status: CheckStatus }) {
  return (
    <span className={`badge status-${status.toLowerCase()}`}>
      <span className="badge-icon">{STATUS_ICONS[status]}</span>
      {STATUS_LABELS[status]}
    </span>
  );
}

export function CriticalBadge({ critical }: { critical: boolean }) {
  return (
    <span className={`tag ${critical ? "tag-critical" : "tag-muted"}`}>
      {critical ? "Critical" : "Non-critical"}
    </span>
  );
}

export function ConfidenceBadge({ level }: { level: ConfidenceLevel | null }) {
  if (!level) return null;
  return <span className={`tag confidence-${level.toLowerCase()}`}>{level} confidence</span>;
}

export function Tag({ children }: { children: React.ReactNode }) {
  return <span className="tag tag-muted">{children}</span>;
}
