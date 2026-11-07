import { apiGet } from './client'
import type { Account, Paginated } from './types'

export interface AccountListParams {
  external_ref?: string
  account_type?: string
  limit?: number
  offset?: number
}

export function listAccounts(params: AccountListParams = {}): Promise<Paginated<Account>> {
  return apiGet<Paginated<Account>>('/accounts', { ...params })
}

export function getAccount(id: string): Promise<Account> {
  return apiGet<Account>(`/accounts/${id}`)
}
