import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api/client";
import { AudioPlaceholder, AudioPlayer, type AudioPlayerHandle } from "../components/AudioPlayer";
import { AuditTrail } from "../components/AuditTrail";
import { GateBadge } from "../components/Badges";
import { CheckCard } from "../components/CheckCard";
import { Card, DefinitionList, EmptyState, ErrorMessage, Loading } from "../components/Common";
import { OverrideModal } from "../components/OverrideModal";
import { TranscriptPanel } from "../components/TranscriptPanel";
import type {
  AuditEvent,
  CheckResult,
  LeadDetail as LeadDetailType,
  ScoringRun,
  ScoringRunSummary,
  Transcript,
} from "../types";
import { formatDateTime, formatScore } from "../utils/format";

export function LeadDetail() {
  const { leadId: leadIdParam } = useParams<{ leadId: string }>();
  const leadId = Number(leadIdParam);

  const [lead, setLead] = useState<LeadDetailType | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [run, setRun] = useState<ScoringRun | null>(null);
  const [runs, setRuns] = useState<ScoringRunSummary[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scoring, setScoring] = useState(false);
  const [highlighted, setHighlighted] = useState<number[]>([]);
  const [overrideTarget, setOverrideTarget] = useState<CheckResult | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const playerRef = useRef<AudioPlayerHandle>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [leadData, runList, auditEvents] = await Promise.all([
        api.lead(leadId),
        api.runs(leadId),
        api.leadAuditEvents(leadId),
      ]);
      setLead(leadData);
      setRuns(runList);
      setEvents(auditEvents);

      setTranscript(await api.transcript(leadId).catch(() => null));
      setRun(runList.length > 0 ? await api.run(runList[0].id) : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load this sale.");
    } finally {
      setLoading(false);
    }
  }, [leadId]);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshAfterChange = async (updated: ScoringRun) => {
    setRun(updated);
    setRuns(await api.runs(leadId));
    setEvents(await api.leadAuditEvents(leadId));
    setLead(await api.lead(leadId));
  };

  const handleScore = async () => {
    setScoring(true);
    setError(null);
    try {
      await refreshAfterChange(await api.score(leadId));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Scoring failed."
      );
    } finally {
      setScoring(false);
    }
  };

  const showEvidence = (result: CheckResult) => {
    setHighlighted(result.evidence.map((item) => item.segment_id));
    const first = result.evidence[0];
    if (first) playerRef.current?.seek(first.start_time);
  };

  const hasAudio = Boolean(lead?.call?.has_audio);

  // Plays a moment of the call with a little context either side. Also
  // highlights any transcript lines that fall inside it, so the reviewer sees
  // and hears the same thing.
  const playRange = (start: number, end: number) => {
    setHighlighted(
      (transcript?.segments ?? [])
        .filter((segment) => segment.end_time >= start && segment.start_time <= end)
        .map((segment) => segment.segment_id)
    );
    playerRef.current?.playRange(start, end);
  };

  const uploadAudio = async (file: File) => {
    setUploading(true);
    setUploadError(null);
    try {
      await api.uploadAudio(leadId, file);
      setLead(await api.lead(leadId));
      setEvents(await api.leadAuditEvents(leadId));
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "The recording could not be uploaded.");
    } finally {
      setUploading(false);
    }
  };

  if (loading) return <Loading what="sale" />;
  if (error && !lead) return <ErrorMessage message={error} />;
  if (!lead) return null;

  const summary = run?.summary ?? {};
  const counts = {
    pass: Number(summary.pass_count ?? 0),
    fail: Number(summary.fail_count ?? 0),
    uncertain: Number(summary.uncertain_count ?? 0),
    na: Number(summary.not_applicable_count ?? 0),
    notes: Number(summary.non_critical_fail_count ?? 0),
  };

  return (
    <div className="page">
      <Link to="/leads" className="back-link">
        ← All sales
      </Link>

      <header className="detail-header">
        <div>
          <h1 className="mono">{lead.id}</h1>
          <DefinitionList
            items={[
              ["Vertical", lead.vertical_code],
              ["Retailer", lead.retailer_name],
              ["Plan", lead.plan_name ?? "—"],
              ["Agent", lead.agent_name ?? "—"],
              ["Team leader", lead.team_leader_name ?? "—"],
              ["Call date", formatDateTime(lead.call_datetime)],
            ]}
          />
        </div>
        <div className="detail-gate">
          <GateBadge decision={run?.effective_gate_result ?? null} size="lg" />
          {run && run.override_gate_result && run.override_gate_result !== run.gate_result && (
            <div className="sub-note">Machine decision: {run.gate_result}</div>
          )}
          <div className="detail-score">QA score {formatScore(run?.qa_score_weighted ?? null)}</div>
          <button className="btn-primary" onClick={handleScore} disabled={scoring}>
            {scoring ? "Scoring…" : run ? "Re-score" : "Score sale"}
          </button>
        </div>
      </header>

      {error && <ErrorMessage message={error} />}

      {run && (
        <Card className="gate-explainer">
          <div className="gate-reason">
            <strong>Gate reason:</strong> {String(summary.override_gate_reason ?? run.gate_reason)}
          </div>
          <div className="checklist-meta">
            {run.checklist_name} · {run.checklist_version_label} · effective{" "}
            {run.checklist_effective_from ?? "—"} · {run.check_results.length} checks ·{" "}
            {counts.pass} pass / {counts.fail} fail / {counts.uncertain} uncertain / {counts.na} n/a ·{" "}
            {counts.notes} coaching note(s)
          </div>
          {runs.length > 1 && (
            <div className="run-history">
              <span>Scoring history:</span>
              {runs.map((item) => (
                <button
                  key={item.id}
                  className={`chip ${item.id === run.id ? "chip-active" : ""}`}
                  onClick={async () => setRun(await api.run(item.id))}
                >
                  #{item.id} · {item.effective_gate_result} · {formatDateTime(item.completed_at)}
                </button>
              ))}
            </div>
          )}
        </Card>
      )}

      <div className="review-grid">
        <div className="review-checks">
          {run ? (
            run.check_results.map((result) => (
              <CheckCard
                key={result.id}
                result={result}
                selected={result.evidence.some((item) => highlighted.includes(item.segment_id))}
                onSelectEvidence={showEvidence}
                onOverride={setOverrideTarget}
                onPlayRange={hasAudio ? playRange : undefined}
              />
            ))
          ) : (
            <EmptyState
              message={
                transcript
                  ? "This sale has not been scored yet. Use “Score sale” to run the checklist."
                  : "This sale has no transcript yet, so it cannot be scored."
              }
            />
          )}
        </div>

        <aside className="review-side">
          <Card title="Call audio" className="audio-card">
            {hasAudio && lead.call ? (
              <AudioPlayer
                ref={playerRef}
                src={api.audioUrl(lead.id)}
                filename={lead.call.audio_filename}
                durationSeconds={lead.call.duration_seconds}
              />
            ) : (
              <AudioPlaceholder onUpload={uploadAudio} busy={uploading} error={uploadError} />
            )}
          </Card>

          <Card title="Transcript" className="transcript-card">
            {transcript ? (
              <TranscriptPanel
                transcript={transcript}
                highlightedSegmentIds={highlighted}
                onPlayRange={hasAudio ? playRange : undefined}
              />
            ) : (
              <EmptyState message="No transcript attached." />
            )}
          </Card>
        </aside>
      </div>

      <Card title="CRM record">
        <DefinitionList
          items={[
            ["Customer", lead.customer_name ?? "—"],
            ["Email", lead.customer_email ?? "—"],
            ["Phone", lead.customer_phone ?? "—"],
            ["Date of birth", lead.customer_dob ?? "—"],
            [
              "Address",
              [lead.address_line1, lead.suburb, lead.state, lead.postcode].filter(Boolean).join(", ") ||
                "—",
            ],
            ...Object.entries(lead.attributes ?? {}).map(
              ([key, value]) => [key, String(value)] as [string, string]
            ),
          ]}
        />
      </Card>

      <Card title="Audit trail">
        <AuditTrail events={events} />
      </Card>

      {overrideTarget && (
        <OverrideModal
          result={overrideTarget}
          onCancel={() => setOverrideTarget(null)}
          onSubmit={async (body) => {
            const updated = await api.override(overrideTarget.id, body);
            await refreshAfterChange(updated);
            setOverrideTarget(null);
          }}
        />
      )}
    </div>
  );
}
