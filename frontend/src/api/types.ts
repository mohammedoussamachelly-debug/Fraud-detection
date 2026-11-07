// Mirrors backend/app/schemas/*.py field-for-field. Keep in sync with that
// package, not with docs/database-design.md (which predates several Phase 5
// field-name deviations — see docs/alerts-and-cases.md §1).

export type UserRole = 'analyst' | 'senior_analyst' | 'admin'

export interface User {
  id: string
  email: string
  role: UserRole
  is_active: boolean
}

export interface Paginated<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type AlertStatus = 'open' | 'triaged' | 'escalated' | 'dismissed'

export interface Alert {
  id: string
  transaction_id: string
  risk_score_id: string | null
  alert_type: string
  severity: string
  status: AlertStatus
  created_at: string
}

export type CaseStatus = 'open' | 'investigating' | 'pending_review' | 'resolved' | 'closed'
export type CasePriority = 'low' | 'medium' | 'high' | 'critical'

export interface CaseAlertLink {
  alert_id: string
  linked_at: string
}

export interface Case {
  id: string
  status: CaseStatus
  priority: CasePriority
  assigned_analyst_id: string | null
  created_at: string
  updated_at: string
  closed_at: string | null
}

export interface CaseDetail extends Case {
  alerts: CaseAlertLink[]
}

export type TransactionType = 'CASH_IN' | 'CASH_OUT' | 'DEBIT' | 'PAYMENT' | 'TRANSFER'

export interface Transaction {
  id: string
  external_ref: string
  step: number
  occurred_at: string
  type: TransactionType
  amount: string
  origin_account_id: string
  dest_account_id: string
  origin_balance_before: string
  origin_balance_after: string
  dest_balance_before: string
  dest_balance_after: string
}

export interface Account {
  id: string
  external_ref: string
  account_type: string
  first_seen_at: string
  created_at: string
}

export type RiskLevel = 'low' | 'medium' | 'high'

export interface ShapContribution {
  feature: string
  value: number | string
  shap_contribution: number
  direction: 'increases_risk' | 'decreases_risk'
}

export interface RiskExplanation {
  base_value: number
  contributions: ShapContribution[]
}

export interface RiskScoreRecord {
  id: string
  transaction_id: string
  risk_score: number
  risk_level: RiskLevel
  model_version: string
  threshold_used: number
  explanation: RiskExplanation | null
  scored_at: string
}

export interface GraphNode {
  id: string
  external_ref: string
  account_type: string
}

export interface GraphEdge {
  source: string
  target: string
  transaction_id: string
  external_ref: string
  amount: string
  step: number
  type: TransactionType
}

export interface AccountNeighborhood {
  center_account_id: string
  hops: number
  as_of_step: number | null
  nodes: GraphNode[]
  edges: GraphEdge[]
  cycles: string[][]
  truncated: boolean
  disclaimer: string
}

export interface AccountGraphMetrics {
  account_id: string
  as_of_step: number | null
  incoming_transaction_count: number
  outgoing_transaction_count: number
  unique_senders: number
  unique_recipients: number
  fan_in_pattern: boolean
  fan_out_pattern: boolean
  velocity_window_steps: number
  velocity_count: number
  truncated: boolean
  disclaimer: string
}

export interface GraphTransaction extends Transaction {
  direction: 'incoming' | 'outgoing'
}

export interface FundFlowStep {
  transaction_id: string
  transaction_external_ref: string
  from_account_id: string
  to_account_id: string
  amount: string
  step: number
}

export interface FundFlowPath {
  steps: FundFlowStep[]
}

export interface FundFlow {
  source_account_id: string
  as_of_step: number | null
  max_hops: number
  max_branches: number
  paths: FundFlowPath[]
  truncated: boolean
  disclaimer: string
}

export const EVIDENCE_TYPES = [
  'transaction',
  'risk_score',
  'shap_explanation',
  'graph_neighborhood',
  'graph_metrics',
  'fund_flow',
  'historical_stats',
  'analyst_note',
] as const
export type EvidenceType = (typeof EVIDENCE_TYPES)[number]

export interface CaseEvidence {
  id: string
  case_id: string
  evidence_type: EvidenceType
  source_reference: string
  evidence_payload: Record<string, unknown>
  created_at: string
}

export type DecisionValue = 'confirmed_fraud' | 'not_fraud' | 'dismissed'

export interface CaseDecision {
  id: string
  case_id: string
  decided_by_user_id: string
  decision: DecisionValue
  rationale: string
  decided_at: string
}

export type InvestigationStatus =
  'running' | 'awaiting_approval' | 'approved' | 'rejected' | 'revision_requested' | 'failed'

export interface AgentToolCall {
  tool: string
  args_summary: Record<string, unknown>
  result_ref: string | null
  error?: string
  duration_ms: number
}

export interface AgentStep {
  id: string
  node_name: string
  attempt: number
  status: string
  tool_calls: AgentToolCall[]
  output: Record<string, unknown> | null
  error: string | null
  started_at: string
  completed_at: string | null
}

export interface AgentEvidenceRef {
  id: string
  evidence_type: string
  source_reference: string
  summary: string
  collected_by_node: string
  created_at: string
}

export type ReportConfidence = 'low' | 'medium' | 'high'

export interface ReportHypothesis {
  text: string
  confidence: ReportConfidence
  evidence_refs: string[]
}

export interface AgentReport {
  summary: string
  hypotheses: ReportHypothesis[]
  uncertainties: string[]
  recommended_next_step: string
  model_provider: string
  model_name: string
  is_mock: boolean
  evidence_refs: string[]
}

export interface InvestigationDetail {
  run_id: string
  case_id: string
  started_by_user_id: string
  status: InvestigationStatus
  model_provider: string
  model_name: string
  prompt_version: string
  revision_count: number
  review_feedback: string[]
  draft_report: AgentReport | null
  final_report: AgentReport | null
  error: string | null
  started_at: string
  completed_at: string | null
  steps: AgentStep[]
  evidence_refs: AgentEvidenceRef[]
}

export interface AuditLogEntry {
  id: string
  user_id: string | null
  action: string
  entity_type: string
  entity_id: string | null
  event_metadata: Record<string, unknown>
  occurred_at: string
}
