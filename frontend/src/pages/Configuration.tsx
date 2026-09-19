import { useState } from "react";
import { api } from "../api/client";
import { Card, EmptyState, ErrorMessage, Field, Loading } from "../components/Common";
import { CriticalBadge, Tag } from "../components/Badges";
import { useAsync } from "../hooks/useAsync";
import type { Checklist, ChecklistVersion } from "../types";
import { formatDate, titleCase } from "../utils/format";

type TabKey = "checklists" | "catalog";

export function Configuration() {
  const [tab, setTab] = useState<TabKey>("checklists");

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Configuration</h1>
          <p className="page-subtitle">
            Checks, criticality and source-of-truth mappings are data. Adding a retailer or changing a
            rule does not require a code change or a deployment.
          </p>
        </div>
      </header>

      <div className="segmented">
        <button
          className={tab === "checklists" ? "segment segment-active" : "segment"}
          onClick={() => setTab("checklists")}
        >
          Checklists
        </button>
        <button
          className={tab === "catalog" ? "segment segment-active" : "segment"}
          onClick={() => setTab("catalog")}
        >
          Verticals, retailers & pricing
        </button>
      </div>

      {tab === "checklists" ? <ChecklistsTab /> : <CatalogTab />}
    </div>
  );
}

function ChecklistsTab() {
  const { data, loading, error, reload } = useAsync(() => api.checklists(), []);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [effectiveFrom, setEffectiveFrom] = useState("");

  if (loading) return <Loading what="checklists" />;
  if (error) return <ErrorMessage message={error} />;
  if (!data || data.length === 0) return <EmptyState message="No checklists configured." />;

  const selectedVersion: ChecklistVersion | undefined = data
    .flatMap((checklist) => checklist.versions)
    .find((version) => version.id === selectedVersionId);

  const createDraft = async (checklist: Checklist) => {
    setBusy(true);
    setActionError(null);
    try {
      const draft = await api.createDraft(checklist.id, {
        copy_from_version_id: checklist.current_version?.id,
        notes: "New draft",
      });
      await reload();
      setSelectedVersionId(draft.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not create the draft.");
    } finally {
      setBusy(false);
    }
  };

  const publish = async (version: ChecklistVersion) => {
    if (!effectiveFrom) {
      setActionError("Choose the date this version takes effect.");
      return;
    }
    setBusy(true);
    setActionError(null);
    try {
      await api.publishVersion(version.id, effectiveFrom);
      await reload();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Could not publish this version.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {actionError && <ErrorMessage message={actionError} />}
      {data.map((checklist) => (
        <Card
          key={checklist.id}
          title={checklist.name}
          action={
            <button className="btn-secondary btn-sm" disabled={busy} onClick={() => createDraft(checklist)}>
              New draft version
            </button>
          }
        >
          <div className="checklist-summary">
            <div>
              <strong>Current:</strong>{" "}
              {checklist.current_version
                ? `v${checklist.current_version.version_number} · effective ${formatDate(
                    checklist.current_version.effective_from
                  )} · ${checklist.current_version.check_count} checks · ${
                    checklist.current_version.critical_count
                  } critical`
                : "none published"}
            </div>
            <div className="muted">
              {checklist.retailer_name} · {checklist.vertical_code}
            </div>
          </div>

          <h3 className="subsection">Version history</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Status</th>
                <th>Effective from</th>
                <th>Effective to</th>
                <th className="numeric">Checks</th>
                <th className="numeric">Critical</th>
                <th>Published by</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {checklist.versions.map((version) => (
                <tr key={version.id}>
                  <td>v{version.version_number}</td>
                  <td>
                    <span className={`tag version-${version.status.toLowerCase()}`}>
                      {titleCase(version.status)}
                    </span>
                  </td>
                  <td>{formatDate(version.effective_from)}</td>
                  <td>{version.effective_to ? formatDate(version.effective_to) : "open"}</td>
                  <td className="numeric">{version.check_count}</td>
                  <td className="numeric">{version.critical_count}</td>
                  <td>{version.published_by ?? "—"}</td>
                  <td>
                    <button
                      className="btn-link"
                      onClick={() =>
                        setSelectedVersionId(selectedVersionId === version.id ? null : version.id)
                      }
                    >
                      {selectedVersionId === version.id ? "Hide checks" : "View checks"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {selectedVersion && selectedVersion.checklist_id === checklist.id && (
            <div className="version-detail">
              <div className="version-detail-head">
                <h3>
                  v{selectedVersion.version_number} checks ({selectedVersion.checks.length})
                </h3>
                {selectedVersion.status === "DRAFT" ? (
                  <div className="publish-row">
                    <input
                      type="date"
                      value={effectiveFrom}
                      onChange={(event) => setEffectiveFrom(event.target.value)}
                    />
                    <button
                      className="btn-primary btn-sm"
                      disabled={busy}
                      onClick={() => publish(selectedVersion)}
                    >
                      Publish
                    </button>
                  </div>
                ) : (
                  <span className="muted">
                    Published versions are immutable — create a new draft to change a rule.
                  </span>
                )}
              </div>

              <table className="data-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Type</th>
                    <th>Method</th>
                    <th>Source of truth</th>
                    <th>Evidence from</th>
                    <th>Criticality</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedVersion.checks.map((check) => (
                    <tr key={check.id}>
                      <td>
                        <div>{check.name}</div>
                        <div className="mono muted small">{check.code}</div>
                      </td>
                      <td>
                        <Tag>{check.check_type}</Tag>
                      </td>
                      <td>{titleCase(check.evaluation_method)}</td>
                      <td className="mono small">{check.expected_source ?? "—"}</td>
                      <td className="small">{titleCase(check.evidence_source)}</td>
                      <td>
                        <CriticalBadge critical={check.critical} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      ))}
    </>
  );
}

function CatalogTab() {
  const verticals = useAsync(() => api.verticals(), []);
  const retailers = useAsync(() => api.retailers(), []);
  const plans = useAsync(() => api.plans(), []);
  const rateCards = useAsync(() => api.rateCards(), []);

  const [newRetailer, setNewRetailer] = useState({ code: "", name: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const addRetailer = async () => {
    if (!newRetailer.code || !newRetailer.name) {
      setError("A retailer needs both a code and a name.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createRetailer({ ...newRetailer, vertical_ids: [] });
      setNewRetailer({ code: "", name: "" });
      retailers.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the retailer.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {error && <ErrorMessage message={error} />}

      <Card title="Verticals">
        <div className="chip-row">
          {(verticals.data ?? []).map((vertical) => (
            <span key={vertical.id} className="chip">
              {vertical.name}
            </span>
          ))}
        </div>
      </Card>

      <Card title="Retailers">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Code</th>
              <th>Name</th>
            </tr>
          </thead>
          <tbody>
            {(retailers.data ?? []).map((retailer) => (
              <tr key={retailer.id}>
                <td className="mono">{retailer.id}</td>
                <td className="mono">{retailer.code}</td>
                <td>{retailer.name}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3 className="subsection">Add retailer</h3>
        <div className="inline-form">
          <Field label="Code">
            <input
              value={newRetailer.code}
              onChange={(event) => setNewRetailer({ ...newRetailer, code: event.target.value })}
              placeholder="NEWCO"
            />
          </Field>
          <Field label="Name">
            <input
              value={newRetailer.name}
              onChange={(event) => setNewRetailer({ ...newRetailer, name: event.target.value })}
              placeholder="Newco Energy"
            />
          </Field>
          <button className="btn-secondary" disabled={busy} onClick={addRetailer}>
            Add
          </button>
        </div>
      </Card>

      <Card title="Plans">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Code</th>
              <th>Retailer</th>
            </tr>
          </thead>
          <tbody>
            {(plans.data ?? []).map((plan) => (
              <tr key={plan.id}>
                <td className="mono">{plan.id}</td>
                <td>{plan.name}</td>
                <td className="mono">{plan.code}</td>
                <td>
                  {(retailers.data ?? []).find((retailer) => retailer.id === plan.retailer_id)?.name ??
                    plan.retailer_id}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="Rate cards">
        <p className="muted">
          Rate cards are date-effective, so a call is always priced against the card that was in force
          on the day it happened.
        </p>
        <table className="data-table">
          <thead>
            <tr>
              <th>Plan</th>
              <th>Effective from</th>
              <th>Effective to</th>
              <th className="numeric">Peak</th>
              <th className="numeric">Off-peak</th>
              <th className="numeric">Daily supply</th>
              <th>Unit</th>
            </tr>
          </thead>
          <tbody>
            {(rateCards.data ?? []).map((card) => (
              <tr key={card.id}>
                <td>
                  {(plans.data ?? []).find((plan) => plan.id === card.plan_id)?.name ?? card.plan_id}
                </td>
                <td>{formatDate(card.effective_from)}</td>
                <td>{card.effective_to ? formatDate(card.effective_to) : "open"}</td>
                <td className="numeric">{card.peak_rate ?? "—"}</td>
                <td className="numeric">{card.off_peak_rate ?? "—"}</td>
                <td className="numeric">{card.daily_supply_charge ?? "—"}</td>
                <td>{card.unit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
