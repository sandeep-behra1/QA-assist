/** Mirrors of the backend Pydantic contracts. */

export type CheckStatus = "PASS" | "FAIL" | "UNCERTAIN" | "NOT_APPLICABLE";
export type ExecutionStatus = "COMPLETED" | "INCOMPLETE" | "ERROR";
export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW";
export type GateDecision = "APPROVED" | "HOLD" | "HUMAN_REVIEW";
export type CheckType = "VERBATIM" | "FACTUAL" | "BEHAVIOUR";
export type Speaker = "AGENT" | "CUSTOMER" | "UNKNOWN";

export type EvaluationMethod =
  | "EXACT_TEXT"
  | "NORMALIZED_TEXT"
  | "EMAIL"
  | "NUMERIC"
  | "DATE"
  | "BOOLEAN"
  | "IDENTIFIER"
  | "SEMANTIC"
  | "BEHAVIOUR";

export type OverrideReasonCode =
  | "TRANSCRIPTION_ERROR"
  | "EVIDENCE_MISSED"
  | "RULE_INTERPRETATION"
  | "CRM_DATA_ERROR"
  | "AGENT_CORRECTED_LATER"
  | "APPROVED_EXCEPTION"
  | "OTHER";

export interface Vertical {
  id: number;
  code: string;
  name: string;
  active: boolean;
}

export interface Retailer {
  id: number;
  code: string;
  name: string;
  active: boolean;
}

export interface Plan {
  id: number;
  retailer_id: number;
  vertical_id: number;
  code: string;
  name: string;
  description: string;
  active: boolean;
  attributes: Record<string, unknown>;
}

export interface RateCard {
  id: number;
  plan_id: number;
  effective_from: string;
  effective_to: string | null;
  currency: string;
  unit: string;
  peak_rate: number | null;
  off_peak_rate: number | null;
  shoulder_rate: number | null;
  daily_supply_charge: number | null;
  discount_percent: number | null;
  attributes: Record<string, unknown>;
}

export interface Agent {
  id: number;
  name: string;
  team_leader_id: number | null;
  site: string | null;
  active: boolean;
}

export interface TeamLeader {
  id: number;
  name: string;
  active: boolean;
}

export interface Campaign {
  id: number;
  code: string;
  name: string;
}

export interface Site {
  id: number;
  code: string;
  name: string;
}

export interface LeadSummary {
  id: number;
  vertical_code: string;
  retailer_name: string;
  plan_name: string | null;
  agent_name: string | null;
  team_leader_name: string | null;
  campaign: string | null;
  site: string | null;
  call_datetime: string;
  customer_name: string | null;
  status: string;
  gate_result: GateDecision | null;
  machine_gate_result: GateDecision | null;
  qa_score_weighted: number | null;
  scored_at: string | null;
  has_transcript: boolean;
  has_audio: boolean;
}

export interface CallInfo {
  id: number;
  lead_id: number;
  audio_filename: string | null;
  audio_content_type: string | null;
  audio_size_bytes: number | null;
  duration_seconds: number | null;
  transcription_status: string;
  uploaded_at: string;
  has_audio: boolean;
}

export interface LeadDetail extends LeadSummary {
  vertical_id: number;
  retailer_id: number;
  plan_id: number | null;
  agent_id: number | null;
  team_leader_id: number | null;
  customer_email: string | null;
  customer_phone: string | null;
  customer_dob: string | null;
  address_line1: string | null;
  suburb: string | null;
  state: string | null;
  postcode: string | null;
  attributes: Record<string, unknown>;
  call: CallInfo | null;
  latest_scoring_run_id: number | null;
}

export interface TranscriptSegment {
  segment_id: number;
  speaker: Speaker;
  start_time: number;
  end_time: number;
  text: string;
  asr_confidence: number | null;
}

export interface Transcript {
  transcript_id: number;
  lead_id: number;
  call_id: number | null;
  source: string;
  language: string;
  created_at: string;
  segments: TranscriptSegment[];
}

export interface Evidence {
  id: number;
  transcript_id: number;
  segment_id: number;
  speaker: Speaker;
  text: string;
  start_time: number;
  end_time: number;
  asr_confidence: number | null;
  extraction_method: string;
}

export interface HumanOverride {
  id: number;
  check_result_id: number;
  original_status: CheckStatus;
  override_status: CheckStatus;
  reason_code: OverrideReasonCode;
  notes: string;
  actor: string;
  created_at: string;
}

export interface CheckResult {
  id: number;
  scoring_run_id: number;
  check_definition_id: number | null;
  check_code: string;
  check_name: string;
  check_type: CheckType;
  evaluation_method: EvaluationMethod;
  critical: boolean;
  blocking_behavior: string;
  weight: number;
  display_order: number;
  rule_version: string;
  status: CheckStatus;
  effective_status: CheckStatus;
  execution_status: ExecutionStatus;
  confidence_level: ConfidenceLevel | null;
  reason: string;
  observed_value: string | null;
  expected_value: string | null;
  llm_metadata: Record<string, unknown>;
  created_at: string;
  evidence: Evidence[];
  overrides: HumanOverride[];
}

export interface ScoringRun {
  id: number;
  lead_id: number;
  checklist_version_id: number | null;
  transcript_id: number | null;
  status: string;
  started_at: string;
  completed_at: string | null;
  gate_result: GateDecision | null;
  override_gate_result: GateDecision | null;
  effective_gate_result: GateDecision | null;
  gate_reason: string;
  qa_score_raw: number | null;
  qa_score_weighted: number | null;
  summary: Record<string, number | string | string[]>;
  evaluator_metadata: Record<string, unknown>;
  error_message: string | null;
  checklist_name: string | null;
  checklist_version_label: string | null;
  checklist_effective_from: string | null;
  check_results: CheckResult[];
}

export interface ScoringRunSummary {
  id: number;
  lead_id: number;
  status: string;
  started_at: string;
  completed_at: string | null;
  gate_result: GateDecision | null;
  override_gate_result: GateDecision | null;
  effective_gate_result: GateDecision | null;
  qa_score_weighted: number | null;
  checklist_version_id: number | null;
}

export interface CheckDefinition {
  id: number;
  checklist_version_id: number;
  code: string;
  name: string;
  description: string;
  check_type: CheckType;
  evaluation_method: EvaluationMethod;
  evidence_source: string;
  expected_source: string | null;
  critical: boolean;
  active: boolean;
  display_order: number;
  blocking_behavior: string;
  weight: number;
  evaluation_config: Record<string, unknown>;
  applicable_conditions: Record<string, unknown>;
}

export interface ChecklistVersion {
  id: number;
  checklist_id: number;
  version_number: number;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  effective_from: string | null;
  effective_to: string | null;
  notes: string;
  published_at: string | null;
  published_by: string | null;
  checks: CheckDefinition[];
  check_count: number;
  critical_count: number;
}

export interface Checklist {
  id: number;
  retailer_id: number;
  vertical_id: number;
  retailer_name: string | null;
  vertical_code: string | null;
  code: string;
  name: string;
  active: boolean;
  versions: ChecklistVersion[];
  current_version: ChecklistVersion | null;
}

export interface QueueItem {
  lead_id: number;
  scoring_run_id: number;
  retailer_name: string;
  vertical_code: string;
  agent_name: string | null;
  call_datetime: string;
  gate_result: GateDecision;
  machine_gate_result: GateDecision | null;
  reason: string;
  critical_fail_count: number;
  critical_uncertain_count: number;
  incomplete_count: number;
  priority: number;
  qa_score_weighted: number | null;
}

export interface AuditEvent {
  id: number;
  event_type: string;
  entity_type: string;
  entity_id: string;
  lead_id: number | null;
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DashboardSummary {
  total_sales: number;
  scored_sales: number;
  approved: number;
  hold: number;
  needs_human_review: number;
  pending_reviews: number;
  unscored: number;
  first_pass_yield_percent: number | null;
  critical_fail_rate_percent: number | null;
  average_qa_score: number | null;
  top_failing_checks: {
    check_code: string;
    check_name: string;
    fail_count: number;
    uncertain_count: number;
    critical: boolean;
  }[];
  recent_activity: {
    lead_id: number | null;
    event_type: string;
    actor: string;
    created_at: string;
    summary: string;
  }[];
}

export interface ValidationResult {
  lead_id: number;
  ready_to_score: boolean;
  problems: string[];
}
