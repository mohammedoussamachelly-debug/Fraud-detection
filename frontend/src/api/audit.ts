import { apiGet } from './client'
import type { AuditLogEntry, Paginated } from './types'

export interface AuditLogParams {
  user_id?: string
  action?: string
  occurred_from?: string
  occurred_to?: string
  limit?: number
  offset?: number
}

export function listAuditLog(params: AuditLogParams = {}): Promise<Paginated<AuditLogEntry>> {
  return apiGet<Paginated<AuditLogEntry>>('/audit-log', { ...params })
}
