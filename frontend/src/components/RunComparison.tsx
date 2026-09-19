import { api } from "../api/client";
import { useAsync } from "../hooks/useAsync";
import type { ScoringRun, ScoringRunSummary } from "../types";
import { formatScore } from "../utils/format";
import { GateBadge, StatusBadge } from "./Badges";
import { Card } from "./Common";

interface Props {
  run: ScoringRun;
  runs: ScoringRunSummary[]; // newest first
}

/** What changed between this run and the one before it. Runs are immutable, so both still exist. */
export function RunComparison({ run, runs }: Props) {
  const index = runs.findIndex((item) => item.id === run.id);
  const previous = index >= 0 ? runs[index + 1] : undefined;

  const diff = useAsync(
    () => (previous ? api.runDiff(run.id, previous.id) : Promise.resolve(null)),
    [run.id, previous?.id]
  );

  if (!previous || !diff.data) return null;
  const { data } = diff;
  const scoreMoved = data.base_qa_score !== data.target_qa_score;

  return (
    <Card title={`Changes since run #${previous.id}`} className="run-comparison">
      <div className="comparison-head">
        <div className="comparison-gate">
          <GateBadge decision={data.base_gate} />
          <span className="comparison-arrow">→</span>
          <GateBadge decision={data.target_gate} />
          {!data.gate_changed && <span className="muted small">gate unchanged</span>}
        </div>
        {scoreMoved && (
          <div className="muted small">
            QA score {formatScore(data.base_qa_score)} → {formatScore(data.target_qa_score)}
          </div>
        )}
        <div className="muted small">
          {data.changes.length} check(s) changed · {data.unchanged_count} unchanged. Both runs are kept;
          nothing was overwritten.
        </div>
      </div>

      {data.changes.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Check</th>
              <th>Result</th>
              <th>Observed</th>
              <th>Expected</th>
            </tr>
          </thead>
          <tbody>
            {data.changes.map((change) => (
              <tr key={change.check_code}>
                <td>
                  {change.check_name}
                  {change.critical && <span className="tag tag-critical">critical</span>}
                </td>
                <td className="nowrap">
                  {change.before_status ? <StatusBadge status={change.before_status} /> : "—"}
                  <span className="comparison-arrow">→</span>
                  {change.after_status ? <StatusBadge status={change.after_status} /> : "—"}
                </td>
                <td className="small">
                  {change.before_observed ?? "—"} → <strong>{change.after_observed ?? "—"}</strong>
                </td>
                <td className="small">
                  {change.before_expected ?? "—"} → <strong>{change.after_expected ?? "—"}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
