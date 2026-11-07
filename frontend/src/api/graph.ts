import { apiGet } from './client'
import type {
  AccountGraphMetrics,
  AccountNeighborhood,
  FundFlow,
  GraphTransaction,
  Paginated,
} from './types'

export interface NeighborhoodParams {
  hops?: number
  as_of_step?: number
}

export function getAccountNeighborhood(
  accountId: string,
  params: NeighborhoodParams = {},
): Promise<AccountNeighborhood> {
  return apiGet<AccountNeighborhood>(`/graph/accounts/${accountId}`, { ...params })
}

export function getAccountMetrics(
  accountId: string,
  params: { as_of_step?: number } = {},
): Promise<AccountGraphMetrics> {
  return apiGet<AccountGraphMetrics>(`/graph/accounts/${accountId}/metrics`, { ...params })
}

export interface AccountTransactionsParams {
  as_of_step?: number
  limit?: number
  offset?: number
}

export function getAccountTransactions(
  accountId: string,
  params: AccountTransactionsParams = {},
): Promise<Paginated<GraphTransaction> & { as_of_step: number | null }> {
  return apiGet(`/graph/accounts/${accountId}/transactions`, { ...params })
}

export interface FundFlowParams {
  as_of_step?: number
  max_hops?: number
  max_branches?: number
}

export function getAccountFundFlow(
  accountId: string,
  params: FundFlowParams = {},
): Promise<FundFlow> {
  return apiGet<FundFlow>(`/graph/accounts/${accountId}/fund-flow`, { ...params })
}
