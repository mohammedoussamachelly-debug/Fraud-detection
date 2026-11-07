import type { Alert, CaseDetail, InvestigationDetail, User } from '../api/types'
export const stamp = '2026-11-07T10:30:00Z'
export const user: User = {
  id: '11111111-1111-4111-8111-111111111111',
  email: 'analyst@example.test',
  role: 'analyst',
  is_active: true,
}
export const alert: Alert = {
  id: '22222222-2222-4222-8222-222222222222',
  transaction_id: '33333333-3333-4333-8333-333333333333',
  risk_score_id: null,
  alert_type: 'model_threshold',
  severity: 'critical',
  status: 'open',
  created_at: stamp,
}
export const caseDetail: CaseDetail = {
  id: '44444444-4444-4444-8444-444444444444',
  status: 'investigating',
  priority: 'high',
  assigned_analyst_id: null,
  created_at: stamp,
  updated_at: stamp,
  closed_at: null,
  alerts: [{ alert_id: alert.id, linked_at: stamp }],
}
export const run: InvestigationDetail = {
  run_id: '55555555-5555-4555-8555-555555555555',
  case_id: caseDetail.id,
  started_by_user_id: user.id,
  status: 'awaiting_approval',
  model_provider: 'mock',
  model_name: 'mock-deterministic-v1',
  prompt_version: 'v1',
  revision_count: 0,
  review_feedback: [],
  draft_report: {
    summary: 'Synthetic test report',
    hypotheses: [
      { text: 'Check the source', confidence: 'low', evidence_refs: ['transaction:missing'] },
    ],
    uncertainties: ['Evidence incomplete'],
    recommended_next_step: 'Review original transfer',
    model_provider: 'mock',
    model_name: 'mock-deterministic-v1',
    is_mock: true,
    evidence_refs: [],
  },
  final_report: null,
  error: null,
  started_at: stamp,
  completed_at: stamp,
  steps: [],
  evidence_refs: [],
}
export function page<T>(items: T[], total = items.length) {
  return { items, total, limit: 25, offset: 0 }
}
export function json(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export const inboxEntry = {
  ...alert,
  description: 'Model score crossed the review threshold',
  source: 'Model threshold',
  activity: {
    transaction: {
      id: alert.transaction_id,
      external_ref: 'TEST payment',
      amount: '100',
      occurred_at: stamp,
      type: 'TRANSFER',
      step: 5,
      origin_account_id: user.id,
      dest_account_id: caseDetail.id,
      origin_balance_before: '200',
      origin_balance_after: '100',
      dest_balance_before: '0',
      dest_balance_after: '100',
    },
    sender: 'Test sender',
    recipient: 'Test recipient',
    risk: null,
    alert_id: alert.id,
    case_id: null,
    synthetic: true,
  },
}
