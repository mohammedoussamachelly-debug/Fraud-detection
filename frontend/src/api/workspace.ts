import { apiGet, apiPost } from './client'
import type { CaseStatus, Paginated, RiskScoreRecord, Transaction } from './types'
export interface Activity {
  transaction: Transaction
  sender: string
  recipient: string
  risk: RiskScoreRecord | null
  alert_id: string | null
  case_id: string | null
  synthetic: boolean
}
export interface InboxEntry {
  id: string
  description: string
  severity: string
  status: string
  created_at: string
  source: string
  activity: Activity
}
export interface CaseSummary {
  id: string
  title: string
  status: CaseStatus
  priority: string
  created_at: string
}
export interface History {
  num_prev_txns_by_sender?: number
  historical_avg_amount?: number
  num_unique_prev_recipients?: number
  recent_txn_frequency?: number
}
export interface CaseContext {
  case: CaseSummary
  activities: Activity[]
  history: History
  run_id: string | null
}
export interface Scenario {
  batch: string
  key: string
  title: string
  description: string
  account_id: string
  transaction_id: string
  model_score: number
  model_level: string
  alert_id?: string
  case_id?: string
}
export const getDashboard = () =>
  apiGet<{
    transactions: number
    attention: number
    investigations: number
    review: number
    queue: InboxEntry[]
  }>('/workspace/dashboard')
export const getScenarios = () => apiGet<{ items: Scenario[]; notice: string }>('/demo/scenarios')
export const getInbox = (query: Record<string, string | number>) =>
  apiGet<Paginated<InboxEntry>>('/workspace/alerts', query)
export const getActivities = (query: Record<string, string | number>) =>
  apiGet<Paginated<Activity>>('/workspace/transactions', query)
export const getActivity = (id: string) => apiGet<Activity>(`/workspace/transactions/${id}`)
export const getHistory = (id: string) => apiGet<History>(`/workspace/transactions/${id}/history`)
export const getWorkspaceCases = (query: Record<string, string | number>) =>
  apiGet<Paginated<CaseSummary>>('/workspace/cases', query)
export const getCaseContext = (id: string) => apiGet<CaseContext>(`/workspace/cases/${id}`)
export const investigate = (id: string) =>
  apiPost<{ case_id: string; created: boolean }>(`/workspace/alerts/${id}/investigate`)
export const openReport = (id: string) =>
  apiPost<{ run_id: string; status: string }>(`/workspace/cases/${id}/report`)
