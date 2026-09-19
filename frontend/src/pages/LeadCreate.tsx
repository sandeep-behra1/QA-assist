import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { GateBadge } from "../components/Badges";
import { Card, ErrorMessage, Field } from "../components/Common";
import { useAsync } from "../hooks/useAsync";
import type { DemoPreset, TranscriptionJob } from "../types";
import { formatBytes, formatRange, titleCase } from "../utils/format";

interface FormState {
  lead_id: string;
  vertical_id: string;
  retailer_id: string;
  plan_id: string;
  agent_id: string;
  call_datetime: string;
  customer_name: string;
  customer_email: string;
  customer_phone: string;
  customer_dob: string;
  address_line1: string;
  suburb: string;
  state: string;
  postcode: string;
  campaign: string;
  nmi: string;
  fuel_type: string;
  life_support: string;
  concession: string;
  move_in_date: string;
  payment_collected: string;
  gift_card_value: string;
}

function localNow(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

const EMPTY: FormState = {
  lead_id: "",
  vertical_id: "",
  retailer_id: "",
  plan_id: "",
  agent_id: "",
  call_datetime: localNow(),
  customer_name: "",
  customer_email: "",
  customer_phone: "",
  customer_dob: "",
  address_line1: "",
  suburb: "",
  state: "",
  postcode: "",
  campaign: "",
  nmi: "",
  fuel_type: "ELECTRICITY",
  life_support: "false",
  concession: "false",
  move_in_date: "",
  payment_collected: "false",
  gift_card_value: "",
};

const stem = (filename: string) => filename.replace(/\.[^.]+$/, "");

export function LeadCreate() {
  const navigate = useNavigate();
  const fileInput = useRef<HTMLInputElement>(null);

  const verticals = useAsync(() => api.verticals(), []);
  const retailers = useAsync(() => api.retailers(), []);
  const plans = useAsync(() => api.plans(), []);
  const agents = useAsync(() => api.agents(), []);
  const campaigns = useAsync(() => api.campaigns(), []);
  const providers = useAsync(() => api.transcriptionProviders(), []);
  const existing = useAsync(() => api.leads(), []);
  const [presets, setPresets] = useState<DemoPreset[]>([]);

  const [form, setForm] = useState<FormState>(EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [providerKey, setProviderKey] = useState<string>("");
  const [job, setJob] = useState<TranscriptionJob | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [pasteMode, setPasteMode] = useState(false);
  const [pasted, setPasted] = useState("");
  const [presetNote, setPresetNote] = useState<string | null>(null);

  const [transcribing, setTranscribing] = useState(false);
  const [busy, setBusy] = useState<"save" | "score" | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Demo presets only exist when the backend runs in demo mode; absence is fine.
  useEffect(() => {
    api.demoPresets().then(setPresets).catch(() => setPresets([]));
  }, []);

  // Default to live transcription when it is configured, else the offline demo provider.
  useEffect(() => {
    if (providerKey || !providers.data) return;
    setProviderKey(providers.data.find((p) => p.key === "groq" && p.ready)?.key ?? "embedded");
  }, [providers.data, providerKey]);

  // Reasonable defaults once reference data has loaded.
  useEffect(() => {
    if (!verticals.data || !retailers.data || !plans.data || !agents.data) return;
    setForm((prev) => {
      if (prev.vertical_id) return prev;
      const energy = verticals.data!.find((v) => v.code === "ENERGY") ?? verticals.data![0];
      const retailer = retailers.data!.find((r) => r.code === "AURORA") ?? retailers.data![0];
      const plan = plans.data!.find((p) => p.retailer_id === retailer.id);
      return {
        ...prev,
        vertical_id: String(energy.id),
        retailer_id: String(retailer.id),
        plan_id: plan ? String(plan.id) : "",
        agent_id: agents.data![0] ? String(agents.data![0].id) : "",
      };
    });
  }, [verticals.data, retailers.data, plans.data, agents.data]);

  const set = (key: keyof FormState, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const filteredPlans = useMemo(
    () => (plans.data ?? []).filter((p) => String(p.retailer_id) === form.retailer_id),
    [plans.data, form.retailer_id]
  );

  const applyPreset = (preset: DemoPreset) => {
    const p = preset.preset;
    const vertical = verticals.data?.find((v) => v.code === p.vertical_code);
    const retailer = retailers.data?.find((r) => r.code === p.retailer_code);
    const plan = plans.data?.find((x) => x.code === p.plan_code);
    const agent = agents.data?.find((a) => a.name === p.agent_name);
    const a = p.attributes as Record<string, unknown>;
    const taken = new Set((existing.data ?? []).map((l) => l.id));

    setForm({
      lead_id: taken.has(p.lead_id) ? "" : String(p.lead_id),
      vertical_id: vertical ? String(vertical.id) : "",
      retailer_id: retailer ? String(retailer.id) : "",
      plan_id: plan ? String(plan.id) : "",
      agent_id: agent ? String(agent.id) : "",
      call_datetime: p.call_datetime,
      customer_name: p.customer_name,
      customer_email: p.customer_email,
      customer_phone: p.customer_phone,
      customer_dob: p.customer_dob,
      address_line1: p.address_line1,
      suburb: p.suburb,
      state: p.state,
      postcode: p.postcode,
      campaign: p.campaign ?? "",
      nmi: String(a.nmi ?? ""),
      fuel_type: String(a.fuel_type ?? "ELECTRICITY"),
      life_support: String(Boolean(a.life_support)),
      concession: String(Boolean(a.concession)),
      move_in_date: String(a.move_in_date ?? ""),
      payment_collected: String(Boolean(a.payment_collected)),
      gift_card_value: a.gift_card_value !== undefined ? String(a.gift_card_value) : "",
    });
    setPresetNote(
      taken.has(p.lead_id)
        ? `Sample details loaded from “${preset.title}”. Lead ${p.lead_id} already exists, so a new ID will be allocated.`
        : `Sample details loaded from “${preset.title}”. Edit anything you like.`
    );
  };

  const chooseFile = (chosen: File | null) => {
    setFile(chosen);
    setJob(null);
    setError(null);
    setShowAll(false);
    if (!chosen) return;
    const match = presets.find((p) => p.key === stem(chosen.name));
    if (match) applyPreset(match);
  };

  const transcribe = async (): Promise<TranscriptionJob | null> => {
    if (!file) return null;
    setTranscribing(true);
    setError(null);
    try {
      const result = await api.createTranscriptionJob(file, providerKey);
      setJob(result);
      if (result.status === "FAILED") setError(`Transcription failed: ${result.error ?? "unknown error"}`);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Transcription failed.");
      return null;
    } finally {
      setTranscribing(false);
    }
  };

  const buildPayload = (): Record<string, unknown> => {
    const agent = agents.data?.find((a) => String(a.id) === form.agent_id);
    const attributes: Record<string, unknown> = {
      fuel_type: form.fuel_type,
      nmi: form.nmi || undefined,
      life_support: form.life_support === "true",
      concession: form.concession === "true",
      move_in_date: form.move_in_date || undefined,
      payment_collected: form.payment_collected === "true",
    };
    if (form.gift_card_value) attributes.gift_card_value = Number(form.gift_card_value);
    Object.keys(attributes).forEach((k) => attributes[k] === undefined && delete attributes[k]);

    const payload: Record<string, unknown> = {
      vertical_id: Number(form.vertical_id),
      retailer_id: Number(form.retailer_id),
      plan_id: form.plan_id ? Number(form.plan_id) : null,
      agent_id: form.agent_id ? Number(form.agent_id) : null,
      team_leader_id: agent?.team_leader_id ?? null,
      site: agent?.site ?? null,
      campaign: form.campaign || null,
      call_datetime: form.call_datetime,
      customer_name: form.customer_name || null,
      customer_email: form.customer_email || null,
      customer_phone: form.customer_phone || null,
      customer_dob: form.customer_dob || null,
      address_line1: form.address_line1 || null,
      suburb: form.suburb || null,
      state: form.state || null,
      postcode: form.postcode || null,
      attributes,
      status: "READY",
    };
    if (form.lead_id) payload.lead_id = Number(form.lead_id);
    return payload;
  };

  const save = async (andScore: boolean) => {
    setError(null);
    if (!form.vertical_id || !form.retailer_id || !form.call_datetime) {
      setError("Vertical, retailer and call date & time are required.");
      return;
    }
    setBusy(andScore ? "score" : "save");
    try {
      let activeJob = job;
      if (file && !activeJob) activeJob = await transcribe();
      if (file && (!activeJob || activeJob.status !== "COMPLETED")) {
        setBusy(null);
        return; // the transcription error is already shown
      }

      const lead = await api.createLead(buildPayload());
      if (activeJob && file) {
        await api.attachTranscriptionJob(activeJob.id, lead.id);
      } else if (pasted.trim()) {
        await api.uploadTranscript(lead.id, { pasted_text: pasted });
      }
      if (andScore) await api.score(lead.id);
      navigate(`/leads/${lead.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setBusy(null);
    }
  };

  const preview = job?.segments ?? [];
  const shown = showAll ? preview : preview.slice(0, 8);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Add lead</h1>
          <p className="page-subtitle">
            Upload the call recording, transcribe it, confirm the sale details, then score. Nothing is
            scored until you ask.
          </p>
        </div>
      </header>

      {error && <ErrorMessage message={error} />}

      <Card title="1. Call recording">
        <div className="intake-row">
          <div className="intake-file">
            <input
              ref={fileInput}
              type="file"
              accept=".wav,.mp3,.m4a,.aac,.ogg"
              onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
            />
            {file && (
              <div className="muted small">
                {file.name} · {formatBytes(file.size)}
              </div>
            )}
          </div>

          <Field
            label="Transcription"
            hint={providers.data?.find((p) => p.key === providerKey)?.note ?? undefined}
          >
            <select value={providerKey} onChange={(event) => setProviderKey(event.target.value)}>
              {(providers.data ?? []).map((p) => (
                <option key={p.key} value={p.key} disabled={!p.ready}>
                  {p.label}
                  {p.ready ? "" : " — not configured"}
                </option>
              ))}
            </select>
          </Field>

          <button className="btn-primary" disabled={!file || transcribing || busy !== null} onClick={transcribe}>
            {transcribing ? "Transcribing…" : job ? "Transcribe again" : "Transcribe"}
          </button>
        </div>

        {transcribing && (
          <p className="muted">
            Transcribing the recording — live speech recognition usually takes 20–40 seconds for a call
            this length.
          </p>
        )}

        {job && job.status === "COMPLETED" && (
          <div className="transcription-result">
            <div className="chip-row">
              <span className="tag tag-llm">
                {job.provider === "embedded" ? "Demo embedded transcript" : `${job.provider} · ${job.model}`}
              </span>
              <span className="tag tag-muted">Speakers: {titleCase(job.diarization)}</span>
              <span className="tag tag-muted">{job.segments.length} segments</span>
              {job.duration_seconds !== null && (
                <span className="tag tag-muted">{formatRange(0, job.duration_seconds)} of audio</span>
              )}
              {job.latency_ms !== null && (
                <span className="tag tag-muted">{(job.latency_ms / 1000).toFixed(1)}s</span>
              )}
            </div>
            {job.warnings.map((warning) => (
              <div key={warning} className="transcription-warning">
                {warning}
              </div>
            ))}
            <table className="data-table preview-table">
              <thead>
                <tr>
                  <th>Audio time</th>
                  <th>Speaker</th>
                  <th>Text</th>
                  <th className="numeric">ASR</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((segment) => (
                  <tr key={segment.segment_id}>
                    <td className="mono">{formatRange(segment.start_time, segment.end_time)}</td>
                    <td>
                      <span className={`transcript-speaker speaker-${segment.speaker.toLowerCase()}`}>
                        {segment.speaker}
                      </span>
                    </td>
                    <td>{segment.text}</td>
                    <td className="numeric">
                      {segment.asr_confidence === null ? "—" : `${Math.round(segment.asr_confidence * 100)}%`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {preview.length > 8 && (
              <button className="btn-link" onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show fewer" : `Show all ${preview.length} segments`}
              </button>
            )}
          </div>
        )}

        <div className="paste-toggle">
          <button className="btn-link" onClick={() => setPasteMode((v) => !v)}>
            {pasteMode ? "Hide" : "No recording? Paste a transcript instead"}
          </button>
          {pasteMode && (
            <textarea
              rows={6}
              className="code-area"
              value={pasted}
              onChange={(event) => setPasted(event.target.value)}
              placeholder={"AGENT: This call may be recorded for quality and compliance purposes.\nCUSTOMER: Okay."}
            />
          )}
        </div>
      </Card>

      <Card
        title="2. Sale details"
        action={
          presets.length > 0 ? (
            <select
              value=""
              onChange={(event) => {
                const chosen = presets.find((p) => p.key === event.target.value);
                if (chosen) applyPreset(chosen);
              }}
            >
              <option value="">Fill sample details…</option>
              {presets.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.filename.replace(".wav", "")} → {p.expected_gate.replace("_", " ")}
                </option>
              ))}
            </select>
          ) : undefined
        }
      >
        {presetNote && <p className="preset-note">{presetNote}</p>}
        {presets.length > 0 && presets.find((p) => file && p.key === stem(file.name)) && (
          <p className="muted small">
            Expected outcome for this recording:{" "}
            <GateBadge decision={presets.find((p) => p.key === stem(file!.name))!.expected_gate} />
          </p>
        )}

        <div className="form-grid compact">
          <Field label="Lead ID" hint="Blank = next CRM ID">
            <input value={form.lead_id} onChange={(e) => set("lead_id", e.target.value)} placeholder="auto" />
          </Field>
          <Field label="Retailer" required>
            <select
              value={form.retailer_id}
              onChange={(e) => {
                set("retailer_id", e.target.value);
                const plan = (plans.data ?? []).find((p) => String(p.retailer_id) === e.target.value);
                set("plan_id", plan ? String(plan.id) : "");
              }}
            >
              {(retailers.data ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Plan" hint="Sets the rate card">
            <select value={form.plan_id} onChange={(e) => set("plan_id", e.target.value)}>
              <option value="">None</option>
              {filteredPlans.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Agent">
            <select value={form.agent_id} onChange={(e) => set("agent_id", e.target.value)}>
              {(agents.data ?? []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Call date & time" required hint="Picks the checklist version">
            <input type="datetime-local" value={form.call_datetime} onChange={(e) => set("call_datetime", e.target.value)} />
          </Field>

          <Field label="Customer name">
            <input value={form.customer_name} onChange={(e) => set("customer_name", e.target.value)} />
          </Field>
          <Field label="Email" hint="Checked against the call">
            <input value={form.customer_email} onChange={(e) => set("customer_email", e.target.value)} />
          </Field>
          <Field label="Phone">
            <input value={form.customer_phone} onChange={(e) => set("customer_phone", e.target.value)} />
          </Field>
          <Field label="Date of birth">
            <input type="date" value={form.customer_dob} onChange={(e) => set("customer_dob", e.target.value)} />
          </Field>
          <Field label="Supply address">
            <input value={form.address_line1} onChange={(e) => set("address_line1", e.target.value)} />
          </Field>

          <Field label="NMI">
            <input value={form.nmi} onChange={(e) => set("nmi", e.target.value)} />
          </Field>
          <Field label="Life support" hint="Critical">
            <select value={form.life_support} onChange={(e) => set("life_support", e.target.value)}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </Field>
          <Field label="Concession">
            <select value={form.concession} onChange={(e) => set("concession", e.target.value)}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </Field>
          <Field label="Move-in date">
            <input type="date" value={form.move_in_date} onChange={(e) => set("move_in_date", e.target.value)} />
          </Field>
          <Field label="Payment taken on call" hint="Requires the recording to be muted">
            <select value={form.payment_collected} onChange={(e) => set("payment_collected", e.target.value)}>
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </Field>
        </div>

        <details className="more-fields">
          <summary>More fields (suburb, campaign, gift card…)</summary>
          <div className="form-grid compact">
            <Field label="Vertical">
              <select value={form.vertical_id} onChange={(e) => set("vertical_id", e.target.value)}>
                {(verticals.data ?? []).map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fuel type">
              <select value={form.fuel_type} onChange={(e) => set("fuel_type", e.target.value)}>
                <option>ELECTRICITY</option>
                <option>GAS</option>
                <option>DUAL</option>
              </select>
            </Field>
            <Field label="Suburb">
              <input value={form.suburb} onChange={(e) => set("suburb", e.target.value)} />
            </Field>
            <Field label="State">
              <input value={form.state} onChange={(e) => set("state", e.target.value)} />
            </Field>
            <Field label="Postcode">
              <input value={form.postcode} onChange={(e) => set("postcode", e.target.value)} />
            </Field>
            <Field label="Campaign">
              <select value={form.campaign} onChange={(e) => set("campaign", e.target.value)}>
                <option value="">None</option>
                {(campaigns.data ?? []).map((c) => (
                  <option key={c.id} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Gift card value" hint="Blank if none offered">
              <input value={form.gift_card_value} onChange={(e) => set("gift_card_value", e.target.value)} />
            </Field>
          </div>
        </details>
      </Card>

      <div className="action-row">
        <button className="btn-secondary" disabled={busy !== null || transcribing} onClick={() => save(false)}>
          {busy === "save" ? "Saving…" : "Save"}
        </button>
        <button className="btn-primary" disabled={busy !== null || transcribing} onClick={() => save(true)}>
          {busy === "score" ? "Scoring…" : "Save & Score"}
        </button>
      </div>
    </div>
  );
}
