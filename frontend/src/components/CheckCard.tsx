import type { CheckResult } from "../types";
import { formatDateTime, titleCase } from "../utils/format";
import { ConfidenceBadge, CriticalBadge, StatusBadge, Tag } from "./Badges";
import { AudioTime } from "./Common";

interface Props {
  result: CheckResult;
  selected: boolean;
  onSelectEvidence: (result: CheckResult) => void;
  onOverride: (result: CheckResult) => void;
  /** Present only when the sale has a recording; timestamps become playable. */
  onPlayRange?: (start: number, end: number) => void;
}

export function CheckCard({ result, selected, onSelectEvidence, onOverride, onPlayRange }: Props) {
  const meta = result.llm_metadata as Record<string, unknown>;
  const llm = meta && meta.provider
    ? {
        provider: String(meta.provider),
        model: String(meta.model),
        latency_ms: Number(meta.latency_ms ?? 0),
        succeeded: Boolean(meta.succeeded),
        prompt_version: String(meta.prompt_version ?? ""),
      }
    : null;
  const override = result.overrides.at(-1);
  const displayStatus = result.effective_status;

  const evidence = result.evidence;
  const spanStart = evidence.length ? Math.min(...evidence.map((e) => e.start_time)) : null;
  const spanEnd = evidence.length ? Math.max(...evidence.map((e) => e.end_time)) : null;

  return (
    <article
      className={`check-card status-border-${displayStatus.toLowerCase()} ${
        selected ? "check-card-selected" : ""
      }`}
    >
      <header className="check-card-header">
        <div className="check-card-heading">
          <StatusBadge status={displayStatus} />
          <span className="check-name">{result.check_name}</span>
        </div>
        <div className="check-card-tags">
          <CriticalBadge critical={result.critical} />
          <Tag>{result.check_type}</Tag>
          <Tag>{titleCase(result.evaluation_method)}</Tag>
          {llm ? (
            <span
              className={`tag ${llm.succeeded ? "tag-llm" : "tag-warning"}`}
              title={`Prompt ${llm.prompt_version}. The model only proposes; the gate is deterministic.`}
            >
              {llm.succeeded ? "LLM" : "LLM failed"} · {llm.provider} · {llm.model} ·{" "}
              {Math.round(llm.latency_ms)} ms
            </span>
          ) : (
            <span className="tag tag-muted">Deterministic · no LLM</span>
          )}
          {result.execution_status !== "COMPLETED" && (
            <span className="tag tag-warning">Execution: {titleCase(result.execution_status)}</span>
          )}
        </div>
      </header>

      <p className="check-reason">{result.reason}</p>

      <dl className="check-facts">
        {result.expected_value !== null && (
          <div>
            <dt>Expected</dt>
            <dd>{result.expected_value}</dd>
          </div>
        )}
        {result.observed_value !== null && (
          <div>
            <dt>Observed</dt>
            <dd>{result.observed_value}</dd>
          </div>
        )}
        <div>
          <dt>Audio time</dt>
          <dd>
            {spanStart !== null && spanEnd !== null ? (
              <AudioTime start={spanStart} end={spanEnd} onPlay={onPlayRange} />
            ) : (
              <span className="muted">No evidence</span>
            )}
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>
            <ConfidenceBadge level={result.confidence_level} />
          </dd>
        </div>
        <div>
          <dt>Rule version</dt>
          <dd>{result.rule_version}</dd>
        </div>
        <div>
          <dt>Evaluated</dt>
          <dd>{formatDateTime(result.created_at)}</dd>
        </div>
      </dl>

      {evidence.length > 0 ? (
        <div className="evidence-block">
          <div className="evidence-header">
            <span className="evidence-title">Evidence</span>
            <button className="btn-link" onClick={() => onSelectEvidence(result)}>
              Show in transcript
            </button>
          </div>
          {evidence.map((item) => (
            <div
              key={item.id}
              className="evidence-quote"
              role="button"
              tabIndex={0}
              onClick={() => onSelectEvidence(result)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onSelectEvidence(result);
              }}
              title="Highlight this segment in the transcript"
            >
              <span className="evidence-meta">
                <AudioTime start={item.start_time} end={item.end_time} onPlay={onPlayRange} />
                <span>
                  {item.speaker} · segment {item.segment_id} · {titleCase(item.extraction_method)}
                </span>
              </span>
              <span className="evidence-text">“{item.text}”</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="evidence-none">
          No transcript evidence for this result
          {result.status === "FAIL" ? " — the required statement was absent from the searched scope." : "."}
        </p>
      )}

      {override && (
        <div className="override-banner">
          <div className="override-title">Human override</div>
          <div className="override-line">
            Machine result <StatusBadge status={override.original_status} /> → reviewer set{" "}
            <StatusBadge status={override.override_status} />
          </div>
          <div className="override-reason">{titleCase(override.reason_code)}: “{override.notes}”</div>
          <div className="override-meta">
            {override.actor} · {formatDateTime(override.created_at)}
          </div>
        </div>
      )}

      <footer className="check-card-footer">
        <button className="btn-secondary btn-sm" onClick={() => onOverride(result)}>
          Override result
        </button>
      </footer>
    </article>
  );
}
