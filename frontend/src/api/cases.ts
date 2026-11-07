import { apiGet, apiPatch, apiPost } from './client'
import type {
  Case,
  CaseDecision,
  CaseDetail,
  CaseEvidence,
  CasePriority,
  CaseStatus,
  DecisionValue,
  EvidenceType,
  Paginated,
} from './types'

export interface CaseListParams {
  status?: CaseStatus
  assigned_to_user_id?: string
  limit?: number
  offset?: number
}

export function listCases(params: CaseListParams = {}): Promise<Paginated<Case>> {
  return apiGet<Paginated<Case>>('/cases', { ...params })
}

export function getCase(id: string): Promise<CaseDetail> {
  return apiGet<CaseDetail>(`/cases/${id}`)
}

export function createCase(
  alertIds: string[],
  priority: CasePriority = 'medium',
): Promise<CaseDetail> {
  return apiPost<CaseDetail>('/cases', { alert_ids: alertIds, priority })
}

export interface CaseUpdateRequest {
  status?: CaseStatus
  priority?: CasePriority
  assigned_analyst_id?: string | null
}

export function updateCase(id: string, body: CaseUpdateRequest): Promise<CaseDetail> {
  return apiPatch<CaseDetail>(`/cases/${id}`, body)
}

export function recordDecision(
  id: string,
  decision: DecisionValue,
  rationale: string,
): Promise<CaseDecision> {
  return apiPost<CaseDecision>(`/cases/${id}/decision`, { decision, rationale })
}

export function getCaseDecision(id: string): Promise<CaseDecision> {
  return apiGet<CaseDecision>(`/cases/${id}/decision`)
}

export interface AttachEvidenceRequest {
  evidence_type: EvidenceType
  source_id?: string
  body?: string
  hops?: number
  as_of_step?: number
  max_hops?: number
  max_branches?: number
}

export function attachEvidence(caseId: string, body: AttachEvidenceRequest): Promise<CaseEvidence> {
  return apiPost<CaseEvidence>(`/cases/${caseId}/evidence`, body)
}

export function listCaseEvidence(
  caseId: string,
  params: { limit?: number; offset?: number } = {},
): Promise<Paginated<CaseEvidence>> {
  return apiGet<Paginated<CaseEvidence>>(`/cases/${caseId}/evidence`, { ...params })
}
