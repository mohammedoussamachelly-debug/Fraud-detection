import { apiGet, apiPost } from './client'
import type { User } from './types'

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export function login(email: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>('/auth/login', { email, password })
}

export function fetchCurrentUser(): Promise<User> {
  return apiGet<User>('/auth/me')
}
