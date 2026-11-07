import { PageHeader } from '../components/layout/PageHeader'
import { Button } from '../components/ui/button'

import { useEffect, useState } from 'react'

import { fetchHealth, fetchReadiness, type ReadinessResponse } from '../api/health'

type ConnectionState =
  | { status: 'loading' }
  | { status: 'connected'; readiness: ReadinessResponse }
  | { status: 'error'; message: string }

export function ConnectivityPage() {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<ConnectionState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    async function checkBackend() {
      setState({ status: 'loading' })
      try {
        await fetchHealth()
        const readiness = await fetchReadiness()
        if (!cancelled) {
          setState({ status: 'connected', readiness })
        }
      } catch (error) {
        if (!cancelled) {
          const message =
            error instanceof Error ? error.message : 'Unknown error contacting the backend.'
          setState({ status: 'error', message })
        }
      }
    }

    void checkBackend()

    return () => {
      cancelled = true
    }
  }, [attempt])

  return (
    <div className="space-y-4">
      <PageHeader title="System status" description="Backend and database readiness" />
      <section
        className="rounded-surface border border-border bg-surface p-4 text-sm"
        aria-live="polite"
      >
        <h2 className="mb-3 font-semibold">Backend connectivity</h2>
        {state.status === 'loading' && <p role="status">Checking backend connection…</p>}
        {state.status === 'connected' && (
          <p role="status">
            Connected. Database: <strong>{state.readiness.database}</strong>
          </p>
        )}
        {state.status === 'error' && (
          <p role="alert">Could not reach the backend: {state.message}</p>
        )}
      </section>
      <p>
        <em>
          This page reports live backend/database connectivity only — it does not display any
          financial or analytics data.
        </em>
      </p>
      <Button onClick={() => setAttempt((a) => a + 1)} disabled={state.status === 'loading'}>
        Check again
      </Button>
    </div>
  )
}
