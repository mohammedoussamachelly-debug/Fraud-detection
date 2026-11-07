import { getToken, notifyUnauthorized } from './tokenStore'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8001/api/v1'

/** RFC 7807 problem+json shape — every non-2xx response from the backend uses this (docs/api-contracts.md §0). */
export interface ProblemDetail {
  type: string
  title: string
  status: number
  detail: string | Record<string, unknown> | unknown[]
  instance: string
}

export class ApiError extends Error {
  status: number
  problem: ProblemDetail | null

  constructor(message: string, status: number, problem: ProblemDetail | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problem = problem
  }
}

function describeProblem(problem: ProblemDetail): string {
  if (typeof problem.detail === 'string' && problem.detail.length > 0) return problem.detail
  if (problem.title) return problem.title
  return 'Request failed.'
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Record<string, string | number | boolean | undefined | null>
  /** Set for the `service` principal (ingestion/scoring only) — human routes never use this. */
  serviceApiKey?: string
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.toString()
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (options.serviceApiKey) {
    headers.Authorization = `Bearer ${options.serviceApiKey}`
  } else if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  let body: string | undefined
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body,
    })
  } catch {
    throw new ApiError('Could not reach the SentinelAI backend.', 0)
  }

  // Prevent an old session's in-flight mutation from repopulating a cleared cache.
  if (token && token !== getToken()) {
    throw new ApiError('The session changed while this request was in progress.', 401)
  }

  if (response.status === 401 && token === getToken() && path !== '/auth/login') {
    notifyUnauthorized()
  }

  if (!response.ok) {
    let problem: ProblemDetail | null = null
    try {
      problem = (await response.json()) as ProblemDetail
    } catch {
      problem = null
    }
    const message = problem
      ? describeProblem(problem)
      : `Request failed with status ${response.status}`
    throw new ApiError(message, response.status, problem)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function apiGet<T>(path: string, query?: RequestOptions['query']): Promise<T> {
  return apiRequest<T>(path, { method: 'GET', query })
}

export function apiPost<T>(path: string, body?: unknown, options: RequestOptions = {}): Promise<T> {
  return apiRequest<T>(path, { ...options, method: 'POST', body })
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'PATCH', body })
}

export { API_BASE_URL }
