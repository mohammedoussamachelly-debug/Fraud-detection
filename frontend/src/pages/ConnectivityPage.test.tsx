import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ConnectivityPage } from './ConnectivityPage'

describe('ConnectivityPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a loading state before the backend responds', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise(() => {})),
    )

    render(<ConnectivityPage />)

    expect(screen.getByRole('status')).toHaveTextContent(/checking backend/i)
  })

  it('shows the connected state with database status once health and readiness succeed', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/health/ready')) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: 'ready', database: 'connected' }), { status: 200 }),
        )
      }
      return Promise.resolve(new Response(JSON.stringify({ status: 'ok' }), { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ConnectivityPage />)

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/connected/i))
    expect(screen.getByText('connected')).toBeInTheDocument()
  })

  it('shows an error state when the backend is unreachable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new Error('network error'))),
    )

    render(<ConnectivityPage />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/could not reach the SentinelAI backend/i)
  })

  it('shows an error state when the backend responds with a failure status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('', { status: 503 }))),
    )

    render(<ConnectivityPage />)

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('alert')).toHaveTextContent(/503/)
  })
})
