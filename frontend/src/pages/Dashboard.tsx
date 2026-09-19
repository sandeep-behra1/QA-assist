import { Link } from "react-router-dom";
import { api } from "../api/client";
import { Card, ErrorMessage, Loading, StatCard } from "../components/Common";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, formatScore } from "../utils/format";

export function Dashboard() {
  const { data, loading, error } = useAsync(() => api.dashboard(), []);

  if (loading) return <Loading what="dashboard" />;
  if (error) return <ErrorMessage message={error} />;
  if (!data) return null;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Operations dashboard</h1>
          <p className="page-subtitle">
            Every sale is scored against the checklist version in force on its call date. The gate is
            deterministic; the QA score is reported separately and never decides it.
          </p>
        </div>
      </header>

      <div className="stat-grid">
        <StatCard label="Total sales" value={data.total_sales} hint={`${data.unscored} not scored yet`} />
        <StatCard label="Approved" value={data.approved} tone="approved" />
        <StatCard label="Hold" value={data.hold} tone="hold" />
        <StatCard label="Needs human review" value={data.needs_human_review} tone="review" />
        <StatCard label="Pending reviews" value={data.pending_reviews} />
        <StatCard
          label="First-pass yield"
          value={formatScore(data.first_pass_yield_percent)}
          hint="Approved by the machine, no human needed"
        />
        <StatCard
          label="Critical fail rate"
          value={formatScore(data.critical_fail_rate_percent)}
          tone="hold"
        />
        <StatCard label="Average QA score" value={formatScore(data.average_qa_score)} />
      </div>

      <div className="shortcut-row">
        <Link className="btn-primary" to="/leads/new">
          Add new lead
        </Link>
        <Link className="btn-secondary" to="/review?queue=NEEDS_REVIEW">
          Review pending sales
        </Link>
        <Link className="btn-secondary" to="/configuration">
          Manage checklists
        </Link>
        <Link className="btn-secondary" to="/review?queue=HOLD">
          View critical failures
        </Link>
      </div>

      <div className="two-column">
        <Card title="Top failing checks">
          {data.top_failing_checks.length === 0 ? (
            <p className="muted">Nothing failing right now.</p>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Check</th>
                  <th>Critical</th>
                  <th className="numeric">Fail</th>
                  <th className="numeric">Uncertain</th>
                </tr>
              </thead>
              <tbody>
                {data.top_failing_checks.map((check) => (
                  <tr key={check.check_code}>
                    <td>{check.check_name}</td>
                    <td>{check.critical ? "Yes" : "No"}</td>
                    <td className="numeric">{check.fail_count}</td>
                    <td className="numeric">{check.uncertain_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="Recent activity">
          <ul className="activity-list">
            {data.recent_activity.map((item, index) => (
              <li key={`${item.event_type}-${index}`}>
                <div className="activity-main">
                  {item.lead_id ? (
                    <Link to={`/leads/${item.lead_id}`}>{item.summary}</Link>
                  ) : (
                    <span>{item.summary}</span>
                  )}
                </div>
                <div className="activity-meta">
                  {item.lead_id ? `Lead ${item.lead_id} · ` : ""}
                  {item.actor} · {formatDateTime(item.created_at)}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
