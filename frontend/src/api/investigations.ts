import { apiGet, apiPost } from './client'
import type { InvestigationDetail, Paginated } from './types'

export interface InvestigationSummary {
  run_id: string
  case_id: string
  started_by_user_id: string
  status: InvestigationDetail['status']
  revision_count: number
  started_at: string
  completed_at: string | null
}

export function startInvestigation(caseId: string): Promise<{ run_id: string; status: string }> {
  return apiPost(`/cases/${caseId}/investigations`)
}

export function listCaseInvestigations(
  caseId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Paginated<InvestigationSummary>> {
  return apiGet<Paginated<InvestigationSummary>>(`/cases/${caseId}/investigations`, { ...params })
}

export function getInvestigation(runId: string): Promise<InvestigationDetail> {
  return apiGet<InvestigationDetail>(`/investigations/${runId}`)
}

export function approveInvestigation(runId: string): Promise<InvestigationDetail> {
  return apiPost<InvestigationDetail>(`/investigations/${runId}/approve`)
}

export function rejectInvestigation(runId: string): Promise<InvestigationDetail> {
  return apiPost<InvestigationDetail>(`/investigations/${runId}/reject`)
}

export function requestInvestigationRevision(
  runId: string,
  feedback: string,
): Promise<InvestigationDetail> {
  return apiPost<InvestigationDetail>(`/investigations/${runId}/request-revision`, { feedback })
}
