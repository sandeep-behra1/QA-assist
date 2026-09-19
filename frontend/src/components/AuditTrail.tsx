import type { AuditEvent } from "../types";
import { formatDateTime, titleCase } from "../utils/format";
import { EmptyState } from "./Common";

const TONE: Record<string, string> = {
  SALE_APPROVED: "audit-approved",
  SALE_HOLD: "audit-hold",
  SALE_ROUTED_TO_REVIEW: "audit-review",
  CHECK_OVERRIDDEN: "audit-override",
};

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return <EmptyState message="No audit events yet." />;
  }
  return (
    <ol className="audit-trail">
      {events.map((event) => (
        <li key={event.id} className={`audit-entry ${TONE[event.event_type] ?? ""}`}>
          <div className="audit-entry-head">
            <span className="audit-type">{titleCase(event.event_type)}</span>
            <span className="audit-time">{formatDateTime(event.created_at)}</span>
          </div>
          <div className="audit-actor">{event.actor}</div>
          {Object.keys(event.details ?? {}).length > 0 && (
            <dl className="audit-details">
              {Object.entries(event.details).map(([key, value]) => (
                <div key={key}>
                  <dt>{titleCase(key)}</dt>
                  <dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ol>
  );
}
