import type {
  Agent,
  AuditEvent,
  Campaign,
  Checklist,
  ChecklistVersion,
  DashboardSummary,
  LeadDetail,
  LeadSummary,
  Plan,
  QueueItem,
  RateCard,
  Retailer,
  ScoringRun,
  ScoringRunSummary,
  Site,
  TeamLeader,
  Transcript,
  ValidationResult,
  Vertical,
} from "../types";

const BASE_URL = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: options?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      // Response had no JSON body; the status text is the best we have.
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const qs = (params: Record<string, string | number | undefined | null>) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const api = {
  health: () => request<{ status: string; database: string; llm_provider: string }>("/health"),
  dashboard: () => request<DashboardSummary>("/dashboard/summary"),

  verticals: () => request<Vertical[]>("/verticals"),
  createVertical: (body: { code: string; name: string }) =>
    request<Vertical>("/verticals", { method: "POST", body: JSON.stringify(body) }),

  retailers: (verticalId?: number) => request<Retailer[]>(`/retailers${qs({ vertical_id: verticalId })}`),
  createRetailer: (body: { code: string; name: string; vertical_ids: number[] }) =>
    request<Retailer>("/retailers", { method: "POST", body: JSON.stringify(body) }),

  retailerVerticals: () =>
    request<{ id: number; retailer_id: number; vertical_id: number }[]>("/retailer-verticals"),
  linkRetailerVertical: (body: { retailer_id: number; vertical_id: number }) =>
    request("/retailer-verticals", { method: "POST", body: JSON.stringify(body) }),

  plans: (params: { retailer_id?: number; vertical_id?: number } = {}) =>
    request<Plan[]>(`/plans${qs(params)}`),
  createPlan: (body: Record<string, unknown>) =>
    request<Plan>("/plans", { method: "POST", body: JSON.stringify(body) }),

  rateCards: (planId?: number) => request<RateCard[]>(`/rate-cards${qs({ plan_id: planId })}`),
  createRateCard: (body: Record<string, unknown>) =>
    request<RateCard>("/rate-cards", { method: "POST", body: JSON.stringify(body) }),

  agents: () => request<Agent[]>("/agents"),
  teamLeaders: () => request<TeamLeader[]>("/team-leaders"),
  campaigns: () => request<Campaign[]>("/campaigns"),
  sites: () => request<Site[]>("/sites"),

  checklists: () => request<Checklist[]>("/checklists"),
  checklist: (id: number) => request<Checklist>(`/checklists/${id}`),
  checklistVersion: (id: number) => request<ChecklistVersion>(`/checklist-versions/${id}`),
  createDraft: (checklistId: number, body: { copy_from_version_id?: number; notes?: string }) =>
    request<ChecklistVersion>(`/checklists/${checklistId}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  addCheck: (versionId: number, body: Record<string, unknown>) =>
    request(`/checklist-versions/${versionId}/checks`, { method: "POST", body: JSON.stringify(body) }),
  updateCheck: (checkId: number, body: Record<string, unknown>) =>
    request(`/checks/${checkId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCheck: (checkId: number) => request(`/checks/${checkId}`, { method: "DELETE" }),
  publishVersion: (versionId: number, effectiveFrom: string) =>
    request<ChecklistVersion>(`/checklist-versions/${versionId}/publish`, {
      method: "POST",
      body: JSON.stringify({ effective_from: effectiveFrom }),
    }),

  leads: (params: Record<string, string | number | undefined> = {}) =>
    request<LeadSummary[]>(`/leads${qs(params)}`),
  lead: (leadId: number) => request<LeadDetail>(`/leads/${leadId}`),
  createLead: (body: Record<string, unknown>) =>
    request<LeadDetail>("/leads", { method: "POST", body: JSON.stringify(body) }),
  updateLead: (leadId: number, body: Record<string, unknown>) =>
    request<LeadDetail>(`/leads/${leadId}`, { method: "PATCH", body: JSON.stringify(body) }),
  validateLead: (leadId: number) => request<ValidationResult>(`/leads/${leadId}/validate`),

  transcript: (leadId: number) => request<Transcript>(`/leads/${leadId}/transcript`),
  uploadTranscript: (leadId: number, body: { payload?: unknown; pasted_text?: string }) =>
    request<Transcript>(`/leads/${leadId}/transcript`, { method: "POST", body: JSON.stringify(body) }),

  uploadAudio: (leadId: number, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ call_id: number; size_bytes: number; filename: string }>(
      `/leads/${leadId}/audio`,
      { method: "POST", body: form }
    );
  },
  audioUrl: (leadId: number) => `${BASE_URL}/leads/${leadId}/audio`,

  score: (leadId: number) => request<ScoringRun>(`/leads/${leadId}/score`, { method: "POST" }),
  latestRun: (leadId: number) => request<ScoringRun>(`/leads/${leadId}/scoring-runs/latest`),
  runs: (leadId: number) => request<ScoringRunSummary[]>(`/leads/${leadId}/scoring-runs`),
  run: (runId: number) => request<ScoringRun>(`/scoring-runs/${runId}`),

  reviewQueue: (queue: string) => request<QueueItem[]>(`/reviews${qs({ queue })}`),
  override: (
    checkResultId: number,
    body: { override_status: string; reason_code: string; notes: string; actor: string }
  ) =>
    request<ScoringRun>(`/check-results/${checkResultId}/override`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  leadAuditEvents: (leadId: number) => request<AuditEvent[]>(`/leads/${leadId}/audit-events`),
  auditEvents: (limit = 100) => request<AuditEvent[]>(`/audit-events${qs({ limit })}`),
};
