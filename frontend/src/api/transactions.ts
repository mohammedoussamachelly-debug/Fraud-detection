import { apiGet } from './client'
import type { Paginated, RiskExplanation, RiskScoreRecord, Transaction } from './types'

export interface TransactionListParams {
  account_id?: string
  type?: string
  limit?: number
  offset?: number
}

export function listTransactions(
  params: TransactionListParams = {},
): Promise<Paginated<Transaction>> {
  return apiGet<Paginated<Transaction>>('/transactions', { ...params })
}

export function getTransaction(id: string): Promise<Transaction> {
  return apiGet<Transaction>(`/transactions/${id}`)
}

export function getTransactionRiskScore(id: string): Promise<RiskScoreRecord> {
  return apiGet<RiskScoreRecord>(`/transactions/${id}/risk-score`)
}

export function getTransactionExplanation(id: string): Promise<RiskExplanation> {
  return apiGet<RiskExplanation>(`/transactions/${id}/explanation`)
}
