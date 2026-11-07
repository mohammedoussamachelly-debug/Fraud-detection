import { apiGet } from './client'

export interface HealthResponse {
  status: string
}

export interface ReadinessResponse {
  status: string
  database: string
}

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health')
}

export function fetchReadiness(): Promise<ReadinessResponse> {
  return apiGet<ReadinessResponse>('/health/ready')
}
