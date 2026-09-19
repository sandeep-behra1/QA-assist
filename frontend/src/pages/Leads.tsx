import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { GateBadge } from "../components/Badges";
import { Card, ErrorMessage, Loading } from "../components/Common";
import { useAsync } from "../hooks/useAsync";
import { formatDateTime, formatScore } from "../utils/format";

export function Leads() {
  const [retailerId, setRetailerId] = useState<string>("");
  const [verticalId, setVerticalId] = useState<string>("");
  const [agentId, setAgentId] = useState<string>("");

  const filters = useMemo(
    () => ({
      retailer_id: retailerId || undefined,
      vertical_id: verticalId || undefined,
      agent_id: agentId || undefined,
    }),
    [retailerId, verticalId, agentId]
  );

  const leads = useAsync(() => api.leads(filters), [retailerId, verticalId, agentId]);
  const retailers = useAsync(() => api.retailers(), []);
  const verticals = useAsync(() => api.verticals(), []);
  const agents = useAsync(() => api.agents(), []);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Sales</h1>
          <p className="page-subtitle">Completed sales and their QA gate status.</p>
        </div>
        <Link className="btn-primary" to="/leads/new">
          Add new lead
        </Link>
      </header>

      <Card
        title="Filters"
        className="filter-card"
        action={
          <button
            className="btn-link"
            onClick={() => {
              setRetailerId("");
              setVerticalId("");
              setAgentId("");
            }}
          >
            Clear
          </button>
        }
      >
        <div className="filter-row">
          <select value={verticalId} onChange={(event) => setVerticalId(event.target.value)}>
            <option value="">All verticals</option>
            {(verticals.data ?? []).map((vertical) => (
              <option key={vertical.id} value={vertical.id}>
                {vertical.name}
              </option>
            ))}
          </select>
          <select value={retailerId} onChange={(event) => setRetailerId(event.target.value)}>
            <option value="">All retailers</option>
            {(retailers.data ?? []).map((retailer) => (
              <option key={retailer.id} value={retailer.id}>
                {retailer.name}
              </option>
            ))}
          </select>
          <select value={agentId} onChange={(event) => setAgentId(event.target.value)}>
            <option value="">All agents</option>
            {(agents.data ?? []).map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {leads.loading && <Loading what="sales" />}
      {leads.error && <ErrorMessage message={leads.error} />}

      {leads.data && (
        <Card title={`${leads.data.length} sales`}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Lead</th>
                <th>Vertical</th>
                <th>Retailer</th>
                <th>Plan</th>
                <th>Agent</th>
                <th>Call date</th>
                <th>Scored</th>
                <th className="numeric">QA score</th>
                <th>Gate</th>
              </tr>
            </thead>
            <tbody>
              {leads.data.map((lead) => (
                <tr key={lead.id}>
                  <td>
                    <Link to={`/leads/${lead.id}`} className="mono">
                      {lead.id}
                    </Link>
                    {!lead.has_transcript && <span className="tag tag-warning">no transcript</span>}
                  </td>
                  <td>{lead.vertical_code}</td>
                  <td>{lead.retailer_name}</td>
                  <td>{lead.plan_name ?? "—"}</td>
                  <td>{lead.agent_name ?? "—"}</td>
                  <td>{formatDateTime(lead.call_datetime)}</td>
                  <td>{lead.scored_at ? formatDateTime(lead.scored_at) : "Not scored"}</td>
                  <td className="numeric">{formatScore(lead.qa_score_weighted)}</td>
                  <td>
                    <GateBadge decision={lead.gate_result} />
                    {lead.machine_gate_result &&
                      lead.gate_result !== lead.machine_gate_result && (
                        <div className="sub-note">machine: {lead.machine_gate_result}</div>
                      )}
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
