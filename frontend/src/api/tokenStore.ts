const STORAGE_KEY = 'sentinelai-token'

let cachedToken: string | null = null
const unauthorizedListeners = new Set<() => void>()

export function getToken(): string | null {
  if (cachedToken !== null) return cachedToken
  try {
    cachedToken = sessionStorage.getItem(STORAGE_KEY)
  } catch {
    cachedToken = null
  }
  return cachedToken
}

export function setToken(token: string): void {
  cachedToken = token
  try {
    sessionStorage.setItem(STORAGE_KEY, token)
  } catch {
    /* sessionStorage unavailable (e.g. private mode); session stays in-memory only */
  }
}

export function clearToken(): void {
  cachedToken = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
}

/** Notified when any request comes back 401 — AuthContext uses this to clear state and redirect. */
export function onUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener)
  return () => unauthorizedListeners.delete(listener)
}

export function notifyUnauthorized(): void {
  for (const listener of unauthorizedListeners) listener()
}
