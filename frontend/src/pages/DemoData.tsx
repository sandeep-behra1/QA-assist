import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { Card, EmptyState, ErrorMessage, Loading } from "../components/Common";
import type { DemoTableInfo, DemoTablePage } from "../types";

const PAGE_SIZE = 25;

function show(value: unknown): string {
  if (value === null || value === undefined) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function DemoData() {
  const [tables, setTables] = useState<DemoTableInfo[] | null>(null);
  const [disabled, setDisabled] = useState(false);
  const [selected, setSelected] = useState("leads");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<DemoTablePage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, Record<string, string>>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [resetting, setResetting] = useState(false);

  const loadTables = useCallback(async () => {
    try {
      setTables((await api.demoStatus()).tables);
      setDisabled(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setDisabled(true);
      else setError(err instanceof Error ? err.message : "Could not load the demo tools.");
    }
  }, []);

  const loadPage = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setPage(await api.demoTable(selected, PAGE_SIZE, offset));
      setDrafts({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this table.");
    } finally {
      setLoading(false);
    }
  }, [selected, offset]);

  useEffect(() => {
    void loadTables();
  }, [loadTables]);

  useEffect(() => {
    if (!disabled) void loadPage();
  }, [disabled, loadPage]);

  const setDraft = (rowId: number, column: string, value: string) =>
    setDrafts((prev) => ({ ...prev, [rowId]: { ...prev[rowId], [column]: value } }));

  const saveRow = async (rowId: number) => {
    const changes = drafts[rowId];
    if (!changes || !page) return;
    setSaving(rowId);
    setError(null);
    setMessage(null);
    try {
      const result = await api.demoEdit(selected, rowId, changes);
      if (!result.changed) {
        setMessage("Nothing changed.");
      } else {
        const summary = Object.entries(result.changes)
          .map(([col, diff]) => `${col}: ${show(diff.before)} → ${show(diff.after)}`)
          .join("; ");
        setMessage(`Saved and audited (${summary}). Open the sale and re-score to see the effect.`);
      }
      await loadPage();
      await loadTables();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The edit could not be saved.");
    } finally {
      setSaving(null);
    }
  };

  const reset = async () => {
    if (
      !window.confirm(
        "Reset ALL demo data? This deletes every sale, scoring run, override, audit event and transcription, then reseeds."
      )
    )
      return;
    setResetting(true);
    setError(null);
    try {
      await api.demoReset();
      setMessage("Demo data reset to the seed.");
      setOffset(0);
      await loadTables();
      await loadPage();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setResetting(false);
    }
  };

  if (disabled) {
    return (
      <div className="page">
        <EmptyState message="Demo tools are switched off. Set DEMO_MODE=true in backend/.env and restart the backend." />
      </div>
    );
  }
  if (!tables) return error ? <ErrorMessage message={error} /> : <Loading what="demo tools" />;

  const primary = page?.primary_key ?? "id";

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Demo data</h1>
          <p className="page-subtitle">
            Browse what is stored in the database and change the inputs a sale is scored against. Try:
            edit a rate card or a CRM email, open the sale, press <strong>Re-score</strong>, and compare
            the two runs. Every edit is audited; scoring history is never rewritten.
          </p>
        </div>
        <button className="btn-secondary" onClick={reset} disabled={resetting}>
          {resetting ? "Resetting…" : "Reset demo data"}
        </button>
      </header>

      {message && <div className="state-message state-ok">{message}</div>}
      {error && <ErrorMessage message={error} />}

      <div className="demo-layout">
        <nav className="demo-tables">
          {tables.map((table) => (
            <button
              key={table.name}
              className={`demo-table-button ${table.name === selected ? "demo-table-active" : ""}`}
              onClick={() => {
                setSelected(table.name);
                setOffset(0);
                setMessage(null);
              }}
            >
              <span>{table.name}</span>
              <span className="demo-count">{table.rows}</span>
              {table.editable_columns.length > 0 && <span className="tag tag-warning">editable</span>}
            </button>
          ))}
        </nav>

        <Card
          title={`${selected} ${page ? `(${page.total} rows)` : ""}`}
          action={
            page && page.total > PAGE_SIZE ? (
              <div className="pager">
                <button className="btn-link" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                  ← Newer
                </button>
                <span className="muted small">
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)}
                </span>
                <button
                  className="btn-link"
                  disabled={offset + PAGE_SIZE >= page.total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  Older →
                </button>
              </div>
            ) : undefined
          }
        >
          {loading && <Loading what="rows" />}
          {page && page.rows.length === 0 && <EmptyState message="No rows." />}
          {page && page.rows.length > 0 && (
            <div className="demo-grid-scroll">
              <table className="data-table demo-grid">
                <thead>
                  <tr>
                    <th />
                    {page.columns.map((column) => (
                      <th key={column.name} title={column.type}>
                        {column.name}
                        {column.editable && <span className="edit-dot" title="editable" />}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.rows.map((row) => {
                    const rowId = Number(row[primary]);
                    const dirty = drafts[rowId] && Object.keys(drafts[rowId]).length > 0;
                    return (
                      <tr key={rowId}>
                        <td className="demo-actions">
                          {dirty && (
                            <button className="btn-primary btn-sm" disabled={saving === rowId} onClick={() => saveRow(rowId)}>
                              {saving === rowId ? "…" : "Save"}
                            </button>
                          )}
                          {selected === "leads" && !dirty && (
                            <Link to={`/leads/${rowId}`} className="small">
                              Open
                            </Link>
                          )}
                        </td>
                        {page.columns.map((column) => {
                          const original = show(row[column.name]);
                          if (!column.editable) {
                            return (
                              <td key={column.name} title={original} className="demo-cell">
                                {original.length > 60 ? `${original.slice(0, 60)}…` : original}
                              </td>
                            );
                          }
                          const value = drafts[rowId]?.[column.name] ?? original;
                          return (
                            <td key={column.name}>
                              <input
                                className={`demo-input ${drafts[rowId]?.[column.name] !== undefined ? "demo-input-dirty" : ""}`}
                                value={value}
                                size={Math.max(8, Math.min(value.length + 1, 48))}
                                onChange={(event) => setDraft(rowId, column.name, event.target.value)}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted small demo-footnote">
            Only highlighted columns can be edited, and only in leads, rate cards and transcript lines.
            Check results, evidence, overrides, checklists and the audit trail are read-only.
          </p>
        </Card>
      </div>
    </div>
  );
}
