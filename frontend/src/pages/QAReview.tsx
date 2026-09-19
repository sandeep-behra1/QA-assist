import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { GateBadge } from "../components/Badges";
import { Card, EmptyState, ErrorMessage, Loading } from "../components/Common";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, formatScore } from "../utils/format";

const TABS = [
  { key: "NEEDS_REVIEW", label: "Needs review" },
  { key: "HOLD", label: "Hold" },
  { key: "APPROVED", label: "Approved" },
  { key: "ALL", label: "All" },
];

const PRIORITY_LABELS: Record<number, string> = {
  1: "Critical uncertain",
  2: "Critical failure",
  3: "Incomplete scoring",
  4: "Routine",
};

export function QAReview() {
  const [params, setParams] = useSearchParams();
  const queue = params.get("queue") ?? "NEEDS_REVIEW";
  const { data, loading, error } = useAsync(() => api.reviewQueue(queue), [queue]);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>QA review queue</h1>
          <p className="page-subtitle">
            Sales the automated gate would not approve on its own, most urgent first. Uncertain
            critical checks outrank outright failures, because those are the ones waiting on a person.
          </p>
        </div>
      </header>

      <div className="segmented">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={queue === tab.key ? "segment segment-active" : "segment"}
            onClick={() => setParams({ queue: tab.key })}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading && <Loading what="queue" />}
      {error && <ErrorMessage message={error} />}

      {data && data.length === 0 && <EmptyState message="Nothing in this queue." />}

      {data && data.length > 0 && (
        <Card title={`${data.length} sales`}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Lead</th>
                <th>Priority</th>
                <th>Retailer</th>
                <th>Agent</th>
                <th>Call date</th>
                <th>Why</th>
                <th className="numeric">Critical fail</th>
                <th className="numeric">Critical uncertain</th>
                <th className="numeric">QA score</th>
                <th>Gate</th>
              </tr>
            </thead>
            <tbody>
              {data.map((item) => (
                <tr key={item.lead_id}>
                  <td>
                    <Link to={`/leads/${item.lead_id}`} className="mono">
                      {item.lead_id}
                    </Link>
                  </td>
                  <td>
                    <span className={`tag priority-${item.priority}`}>
                      {PRIORITY_LABELS[item.priority] ?? "Routine"}
                    </span>
                  </td>
                  <td>{item.retailer_name}</td>
                  <td>{item.agent_name ?? "—"}</td>
                  <td>{formatDateTime(item.call_datetime)}</td>
                  <td className="reason-cell">{item.reason}</td>
                  <td className="numeric">{item.critical_fail_count}</td>
                  <td className="numeric">{item.critical_uncertain_count}</td>
                  <td className="numeric">{formatScore(item.qa_score_weighted)}</td>
                  <td>
                    <GateBadge decision={item.gate_result} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
