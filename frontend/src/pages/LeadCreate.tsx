import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Card, ErrorMessage, Field } from "../components/Common";
import { useAsync } from "../hooks/useAsync";
import type { ValidationResult } from "../types";

const ENERGY_ATTRIBUTES = [
  { key: "fuel_type", label: "Fuel type", hint: "ELECTRICITY, GAS or DUAL — drives which meter checks apply.", options: ["ELECTRICITY", "GAS", "DUAL"] },
  { key: "nmi", label: "NMI", hint: "National Meter Identifier for electricity supply." },
  { key: "mirn", label: "MIRN", hint: "Gas meter identifier; only needed for gas or dual fuel." },
  { key: "move_in_date", label: "Move-in date", hint: "Connection start date, YYYY-MM-DD.", type: "date" },
  { key: "gift_card_value", label: "Gift card value", hint: "Leave blank when no incentive was offered.", type: "number" },
];

export function LeadCreate() {
  const navigate = useNavigate();
  const verticals = useAsync(() => api.verticals(), []);
  const retailers = useAsync(() => api.retailers(), []);
  const plans = useAsync(() => api.plans(), []);
  const agents = useAsync(() => api.agents(), []);
  const teamLeaders = useAsync(() => api.teamLeaders(), []);
  const campaigns = useAsync(() => api.campaigns(), []);
  const sites = useAsync(() => api.sites(), []);

  const [form, setForm] = useState<Record<string, string>>({
    call_datetime: new Date().toISOString().slice(0, 16),
  });
  const [attributes, setAttributes] = useState<Record<string, string>>({
    fuel_type: "ELECTRICITY",
    concession: "false",
    life_support: "false",
  });
  const [transcriptMode, setTranscriptMode] = useState<"paste" | "json">("paste");
  const [transcriptText, setTranscriptText] = useState("");
  const [audioFile, setAudioFile] = useState<File | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [createdLeadId, setCreatedLeadId] = useState<number | null>(null);

  const set = (key: string, value: string) => setForm((prev) => ({ ...prev, [key]: value }));
  const setAttribute = (key: string, value: string) =>
    setAttributes((prev) => ({ ...prev, [key]: value }));

  const filteredPlans = useMemo(
    () => (plans.data ?? []).filter((plan) => String(plan.retailer_id) === form.retailer_id),
    [plans.data, form.retailer_id]
  );

  const buildAttributes = () => {
    const payload: Record<string, unknown> = {};
    Object.entries(attributes).forEach(([key, value]) => {
      if (value === "" || value === undefined) return;
      if (value === "true" || value === "false") payload[key] = value === "true";
      else if (key === "gift_card_value") payload[key] = Number(value);
      else payload[key] = value;
    });
    return payload;
  };

  const saveLead = async (): Promise<number> => {
    if (createdLeadId) return createdLeadId;
    const payload: Record<string, unknown> = {
      vertical_id: Number(form.vertical_id),
      retailer_id: Number(form.retailer_id),
      plan_id: form.plan_id ? Number(form.plan_id) : null,
      agent_id: form.agent_id ? Number(form.agent_id) : null,
      team_leader_id: form.team_leader_id ? Number(form.team_leader_id) : null,
      campaign: form.campaign || null,
      site: form.site || null,
      call_datetime: form.call_datetime,
      customer_name: form.customer_name || null,
      customer_email: form.customer_email || null,
      customer_phone: form.customer_phone || null,
      customer_dob: form.customer_dob || null,
      address_line1: form.address_line1 || null,
      suburb: form.suburb || null,
      state: form.state || null,
      postcode: form.postcode || null,
      attributes: buildAttributes(),
      status: "DRAFT",
    };
    if (form.lead_id) payload.lead_id = Number(form.lead_id);

    const lead = await api.createLead(payload);
    setCreatedLeadId(lead.id);

    if (transcriptText.trim()) {
      if (transcriptMode === "json") {
        await api.uploadTranscript(lead.id, { payload: JSON.parse(transcriptText) });
      } else {
        await api.uploadTranscript(lead.id, { pasted_text: transcriptText });
      }
    }
    if (audioFile) await api.uploadAudio(lead.id, audioFile);
    return lead.id;
  };

  const run = async (action: "draft" | "validate" | "score") => {
    setBusy(true);
    setError(null);
    setValidation(null);
    try {
      const id = await saveLead();
      if (action === "validate") {
        setValidation(await api.validateLead(id));
      } else if (action === "score") {
        await api.score(id);
        navigate(`/leads/${id}`);
      } else {
        navigate(`/leads/${id}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Add lead</h1>
          <p className="page-subtitle">
            Capture the sale, its CRM details and the call material. Nothing is scored until you ask
            for it.
          </p>
        </div>
      </header>

      {error && <ErrorMessage message={error} />}

      <Card title="A. Sale information">
        <div className="form-grid">
          <Field label="Lead ID" hint="Leave blank to let the system allocate the next CRM id.">
            <input
              value={form.lead_id ?? ""}
              onChange={(event) => set("lead_id", event.target.value)}
              placeholder="3613790"
            />
          </Field>
          <Field label="Vertical" required hint="Determines which checklist family applies.">
            <select value={form.vertical_id ?? ""} onChange={(event) => set("vertical_id", event.target.value)}>
              <option value="">Select…</option>
              {(verticals.data ?? []).map((vertical) => (
                <option key={vertical.id} value={vertical.id}>
                  {vertical.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Retailer" required hint="The retailer whose QA checklist will be used.">
            <select value={form.retailer_id ?? ""} onChange={(event) => set("retailer_id", event.target.value)}>
              <option value="">Select…</option>
              {(retailers.data ?? []).map((retailer) => (
                <option key={retailer.id} value={retailer.id}>
                  {retailer.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Plan / product" hint="Drives which rate card the quoted prices are checked against.">
            <select value={form.plan_id ?? ""} onChange={(event) => set("plan_id", event.target.value)}>
              <option value="">Select…</option>
              {filteredPlans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Agent">
            <select value={form.agent_id ?? ""} onChange={(event) => set("agent_id", event.target.value)}>
              <option value="">Select…</option>
              {(agents.data ?? []).map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Team leader">
            <select
              value={form.team_leader_id ?? ""}
              onChange={(event) => set("team_leader_id", event.target.value)}
            >
              <option value="">Select…</option>
              {(teamLeaders.data ?? []).map((leader) => (
                <option key={leader.id} value={leader.id}>
                  {leader.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Campaign">
            <select value={form.campaign ?? ""} onChange={(event) => set("campaign", event.target.value)}>
              <option value="">Select…</option>
              {(campaigns.data ?? []).map((campaign) => (
                <option key={campaign.id} value={campaign.code}>
                  {campaign.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Site">
            <select value={form.site ?? ""} onChange={(event) => set("site", event.target.value)}>
              <option value="">Select…</option>
              {(sites.data ?? []).map((site) => (
                <option key={site.id} value={site.code}>
                  {site.name}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="Call date & time"
            required
            hint="Decides which checklist version and rate card apply."
          >
            <input
              type="datetime-local"
              value={form.call_datetime ?? ""}
              onChange={(event) => set("call_datetime", event.target.value)}
            />
          </Field>
        </div>
      </Card>

      <Card title="B. Customer / CRM details">
        <div className="form-grid">
          <Field label="Name">
            <input value={form.customer_name ?? ""} onChange={(e) => set("customer_name", e.target.value)} />
          </Field>
          <Field label="Email" hint="Compared against the address the agent reads back on the call.">
            <input value={form.customer_email ?? ""} onChange={(e) => set("customer_email", e.target.value)} />
          </Field>
          <Field label="Phone">
            <input value={form.customer_phone ?? ""} onChange={(e) => set("customer_phone", e.target.value)} />
          </Field>
          <Field label="Date of birth">
            <input type="date" value={form.customer_dob ?? ""} onChange={(e) => set("customer_dob", e.target.value)} />
          </Field>
          <Field label="Address">
            <input value={form.address_line1 ?? ""} onChange={(e) => set("address_line1", e.target.value)} />
          </Field>
          <Field label="Suburb">
            <input value={form.suburb ?? ""} onChange={(e) => set("suburb", e.target.value)} />
          </Field>
          <Field label="State">
            <input value={form.state ?? ""} onChange={(e) => set("state", e.target.value)} />
          </Field>
          <Field label="Postcode">
            <input value={form.postcode ?? ""} onChange={(e) => set("postcode", e.target.value)} />
          </Field>
        </div>

        <h3 className="subsection">Energy-specific fields</h3>
        <p className="muted">
          These are stored as flexible attributes, so another vertical can add its own fields without a
          database migration.
        </p>
        <div className="form-grid">
          {ENERGY_ATTRIBUTES.map((attribute) => (
            <Field key={attribute.key} label={attribute.label} hint={attribute.hint}>
              {attribute.options ? (
                <select
                  value={attributes[attribute.key] ?? ""}
                  onChange={(event) => setAttribute(attribute.key, event.target.value)}
                >
                  {attribute.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type={attribute.type ?? "text"}
                  value={attributes[attribute.key] ?? ""}
                  onChange={(event) => setAttribute(attribute.key, event.target.value)}
                />
              )}
            </Field>
          ))}
          <Field label="Concession" hint="Checked against what the customer confirms on the call.">
            <select
              value={attributes.concession ?? "false"}
              onChange={(event) => setAttribute("concession", event.target.value)}
            >
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </Field>
          <Field label="Life support" hint="Critical compliance field; checked against the call.">
            <select
              value={attributes.life_support ?? "false"}
              onChange={(event) => setAttribute("life_support", event.target.value)}
            >
              <option value="false">No</option>
              <option value="true">Yes</option>
            </select>
          </Field>
        </div>
      </Card>

      <Card title="C. Transcript">
        <div className="segmented">
          <button
            className={transcriptMode === "paste" ? "segment segment-active" : "segment"}
            onClick={() => setTranscriptMode("paste")}
          >
            Paste transcript
          </button>
          <button
            className={transcriptMode === "json" ? "segment segment-active" : "segment"}
            onClick={() => setTranscriptMode("json")}
          >
            Canonical JSON
          </button>
        </div>
        <textarea
          rows={10}
          className="code-area"
          value={transcriptText}
          onChange={(event) => setTranscriptText(event.target.value)}
          placeholder={
            transcriptMode === "paste"
              ? "AGENT: This call may be recorded for quality and compliance purposes.\nCUSTOMER: Okay."
              : '{\n  "transcript_id": 900124,\n  "segments": [\n    {"segment_id": 1, "speaker": "AGENT", "start_time": 12.1, "end_time": 17.85, "text": "...", "asr_confidence": 0.98}\n  ]\n}'
          }
        />
      </Card>

      <Card title="D. Call audio">
        <Field
          label="Recording"
          hint="WAV, MP3 or M4A. Stored for reviewer playback; transcription is not run in this version."
        >
          <input
            type="file"
            accept=".wav,.mp3,.m4a,.aac,.ogg"
            onChange={(event) => setAudioFile(event.target.files?.[0] ?? null)}
          />
        </Field>
      </Card>

      {validation && (
        <Card title="Validation">
          {validation.ready_to_score ? (
            <p className="validation-ok">This sale has everything it needs to be scored.</p>
          ) : (
            <ul className="validation-list">
              {validation.problems.map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <div className="action-row">
        <button className="btn-secondary" disabled={busy} onClick={() => run("draft")}>
          Save draft
        </button>
        <button className="btn-secondary" disabled={busy} onClick={() => run("validate")}>
          Validate data
        </button>
        <button className="btn-primary" disabled={busy} onClick={() => run("score")}>
          {busy ? "Working…" : "Score sale"}
        </button>
      </div>
    </div>
  );
}
