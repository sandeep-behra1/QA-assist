import type { CheckStatus, ConfidenceLevel, GateDecision } from "../types";

export const GATE_LABELS: Record<GateDecision, string> = {
  APPROVED: "Approved",
  HOLD: "Hold",
  HUMAN_REVIEW: "Human Review",
};

export const STATUS_LABELS: Record<CheckStatus, string> = {
  PASS: "Pass",
  FAIL: "Fail",
  UNCERTAIN: "Uncertain",
  NOT_APPLICABLE: "N/A",
};

export const STATUS_ICONS: Record<CheckStatus, string> = {
  PASS: "✓",
  FAIL: "✕",
  UNCERTAIN: "?",
  NOT_APPLICABLE: "–",
};

export function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${(total % 60).toString().padStart(2, "0")}`;
}

/** "0:14" for a point in time, "0:14–0:18" for a span within the call audio. */
export function formatRange(start: number, end?: number): string {
  if (end === undefined || Math.floor(end) === Math.floor(start)) return formatTime(start);
  return `${formatTime(start)}–${formatTime(end)}`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export function formatScore(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${value.toFixed(1)}%`;
}

export function formatBytes(bytes: number | null): string {
  if (!bytes) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function confidenceLabel(level: ConfidenceLevel | null): string {
  return level ? `${level.charAt(0)}${level.slice(1).toLowerCase()} confidence` : "—";
}

export function titleCase(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ");
}
