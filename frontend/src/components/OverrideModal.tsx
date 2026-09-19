import { useState } from "react";
import type { CheckResult, CheckStatus, OverrideReasonCode } from "../types";
import { titleCase } from "../utils/format";
import { StatusBadge } from "./Badges";
import { Field } from "./Common";

const STATUSES: CheckStatus[] = ["PASS", "FAIL", "UNCERTAIN", "NOT_APPLICABLE"];

const REASON_CODES: OverrideReasonCode[] = [
  "TRANSCRIPTION_ERROR",
  "EVIDENCE_MISSED",
  "RULE_INTERPRETATION",
  "CRM_DATA_ERROR",
  "AGENT_CORRECTED_LATER",
  "APPROVED_EXCEPTION",
  "OTHER",
];

interface Props {
  result: CheckResult;
  onCancel: () => void;
  onSubmit: (body: {
    override_status: CheckStatus;
    reason_code: OverrideReasonCode;
    notes: string;
    actor: string;
  }) => Promise<void>;
}

export function OverrideModal({ result, onCancel, onSubmit }: Props) {
  const [status, setStatus] = useState<CheckStatus>(result.effective_status);
  const [reasonCode, setReasonCode] = useState<OverrideReasonCode>("EVIDENCE_MISSED");
  const [notes, setNotes] = useState("");
  const [actor, setActor] = useState("qa.reviewer@example.com");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!notes.trim()) {
      setError("Notes are required so the decision can be audited later.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ override_status: status, reason_code: reasonCode, notes: notes.trim(), actor });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The override could not be saved.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <h2 className="modal-title">Override check result</h2>
        <p className="modal-subtitle">{result.check_name}</p>

        <div className="modal-note">
          The automated result <StatusBadge status={result.status} /> is kept on the record. Your
          override is stored alongside it with your name, reason and timestamp.
        </div>

        <Field label="New result" required>
          <select value={status} onChange={(event) => setStatus(event.target.value as CheckStatus)}>
            {STATUSES.map((option) => (
              <option key={option} value={option}>
                {titleCase(option)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Reason code" required>
          <select
            value={reasonCode}
            onChange={(event) => setReasonCode(event.target.value as OverrideReasonCode)}
          >
            {REASON_CODES.map((option) => (
              <option key={option} value={option}>
                {titleCase(option)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Reviewer" required>
          <input value={actor} onChange={(event) => setActor(event.target.value)} />
        </Field>

        <Field label="Notes" hint="Explain what you checked and why the machine result is wrong." required>
          <textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} />
        </Field>

        {error && <div className="form-error">{error}</div>}

        <div className="modal-actions">
          <button className="btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Saving…" : "Save override"}
          </button>
        </div>
      </div>
    </div>
  );
}
