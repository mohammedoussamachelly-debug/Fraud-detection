import { apiGet, apiPatch } from './client'
import type { Alert, AlertStatus, Paginated } from './types'

export interface AlertListParams {
  status?: AlertStatus
  severity?: string
  created_from?: string
  created_to?: string
  limit?: number
  offset?: number
}

export function listAlerts(params: AlertListParams = {}): Promise<Paginated<Alert>> {
  return apiGet<Paginated<Alert>>('/alerts', { ...params })
}

export function getAlert(id: string): Promise<Alert> {
  return apiGet<Alert>(`/alerts/${id}`)
}

export function updateAlertStatus(id: string, status: AlertStatus): Promise<Alert> {
  return apiPatch<Alert>(`/alerts/${id}`, { status })
}
