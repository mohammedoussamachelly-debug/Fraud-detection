import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../context/AuthContext'
import { clearToken, setToken } from '../api/tokenStore'
import { AlertsListPage } from '../features/alerts/AlertsListPage'
import { AlertDetailPage } from '../features/alerts/AlertDetailPage'
import { CaseDetailPage } from '../features/cases/CaseDetailPage'
import { DecisionForm } from '../features/cases/DecisionForm'
import { InvestigationDetailPage } from '../features/investigations/InvestigationDetailPage'
import { AuditPage } from '../features/audit/AuditPage'
import { RiskScoreIndicator } from '../features/transactions/RiskScoreIndicator'
import { DataTable, type DataColumn } from '../components/data/DataTable'
import { alert, caseDetail, json, page, run, user } from './fixtures'

function mount(children: ReactNode, path = '/', route = '/') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes>
            <Route path={route} element={children} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}
function mockFetch(handler: (url: URL, init?: RequestInit) => Response | Promise<Response>) {
  return vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init?: RequestInit) => {
      const url = new URL(input)
      if (url.pathname.endsWith('/auth/me')) return Promise.resolve(json(user))
      return Promise.resolve(handler(url, init))
    }),
  )
}
beforeEach(() => {
  setToken('test-session')
})
afterEach(() => {
  clearToken()
  vi.unstubAllGlobals()
})

describe('Alert queue', () => {
  it('shows loading while awaiting the API', () => {
    mockFetch(() => new Promise(() => {}))
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AlertsListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(container.querySelectorAll('tbody tr').length).toBe(6)
    expect(screen.queryByText('No alerts match these filters')).not.toBeInTheDocument()
  })
  it('shows an empty state for a successful empty response', async () => {
    mockFetch(() => json(page([])))
    mount(<AlertsListPage />)
    expect(await screen.findByText('No alerts match these filters')).toBeInTheDocument()
  })
  it('shows API failures and retries without inventing records', async () => {
    let fail = true
    mockFetch(() => (fail ? json({ detail: 'Queue unavailable' }, 503) : json(page([alert]))))
    mount(<AlertsListPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Queue unavailable')
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('critical')).toBeInTheDocument()
  })
  it('uses URL filters and server offsets for next page', async () => {
    const requests: URL[] = []
    mockFetch((url) => {
      requests.push(url)
      return json(page([alert], 30))
    })
    mount(<AlertsListPage />, '/alerts?status=open&severity=critical', '/alerts')
    await screen.findByText('1-25 of 30')
    expect(requests[0].searchParams.get('severity')).toBe('critical')
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() =>
      expect(requests.some((url) => url.searchParams.get('offset') === '25')).toBe(true),
    )
  })
  it('invalidates overview and list totals after a status change', async () => {
    mockFetch((url, init) =>
      url.pathname.includes('/alerts/')
        ? json({ ...alert, status: init?.method === 'PATCH' ? 'triaged' : 'open' })
        : json({ detail: 'Unavailable' }, 404),
    )
    const client = mount(<AlertDetailPage />, `/alerts/${alert.id}`, '/alerts/:alertId')
    client.setQueryData(['alerts', 'overview', 'critical'], page([alert]))
    await screen.findByRole('button', { name: 'Create case' })
    fireEvent.click(screen.getByRole('combobox', { name: 'Change alert status' }))
    fireEvent.click(await screen.findByRole('option', { name: 'triaged' }))
    await waitFor(() =>
      expect(client.getQueryState(['alerts', 'overview', 'critical'])?.isInvalidated).toBe(true),
    )
  })
})

describe('Risk score failures', () => {
  it.each([
    [404, 'Not scored yet'],
    [503, 'Could not load this data'],
    [403, 'Could not load this data'],
  ])('distinguishes HTTP %i', async (status, text) => {
    mockFetch(() => json({ detail: 'Score request failed' }, status as number))
    mount(<RiskScoreIndicator transactionId={alert.transaction_id} />)
    expect(await screen.findByText(text as string)).toBeInTheDocument()
    if (status !== 404) expect(screen.queryByText('Not scored yet')).not.toBeInTheDocument()
  })
})

describe('Case decisions and permissions', () => {
  it('does not offer a decision form to an analyst and does not spin forever', async () => {
    mockFetch((url) =>
      url.pathname.endsWith('/decision') ? json({ detail: 'No decision' }, 404) : json(caseDetail),
    )
    mount(<CaseDetailPage />, `/cases/${caseDetail.id}?tab=decision`, '/cases/:caseId')
    expect(await screen.findByText(/Only a senior analyst or admin/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Review decision' })).not.toBeInTheDocument()
  })
  it('never requests administrator audit data for an analyst', async () => {
    const request = vi.fn(() => json(page([])))
    mockFetch(request)
    mount(<AuditPage />)
    expect(await screen.findByText('Administrator access required')).toBeInTheDocument()
    expect(request).not.toHaveBeenCalled()
  })
  it('requires rationale and an explicit confirmation before posting a decision', async () => {
    const post = vi.fn(() => json({ decision: 'confirmed_fraud' }, 201))
    mockFetch(post)
    const onDecided = vi.fn()
    mount(
      <DecisionForm
        caseId={caseDetail.id}
        caseStatus="investigating"
        existingDecision={null}
        onDecided={onDecided}
      />,
    )
    expect(screen.getByRole('button', { name: 'Review decision' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Rationale/), {
      target: { value: 'Reviewed the source evidence.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Review decision' }))
    expect(post).not.toHaveBeenCalled()
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Record decision' }))
    await waitFor(() => expect(onDecided).toHaveBeenCalledOnce())
    expect(post).toHaveBeenCalledOnce()
  })
  it('keeps a failed mutation visible instead of claiming success', async () => {
    mockFetch(() => json({ detail: 'Decision denied' }, 403))
    const onDecided = vi.fn()
    mount(
      <DecisionForm
        caseId={caseDetail.id}
        caseStatus="investigating"
        existingDecision={null}
        onDecided={onDecided}
      />,
    )
    fireEvent.change(screen.getByLabelText(/Rationale/), {
      target: { value: 'Reviewed the source evidence.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Review decision' }))
    fireEvent.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: 'Record decision' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Decision denied')
    expect(onDecided).not.toHaveBeenCalled()
  })
})

describe('Investigation review', () => {
  it('labels mock output and unresolved citations', async () => {
    mockFetch(() => json(run))
    mount(<InvestigationDetailPage />, `/investigations/${run.run_id}`, '/investigations/:runId')
    expect(await screen.findByText('Mock AI report')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /unresolved/ })).toBeInTheDocument()
  })
  it('approves the report without calling the case decision endpoint', async () => {
    const requests: string[] = []
    mockFetch((url, init) => {
      requests.push(`${init?.method} ${url.pathname}`)
      return json({ ...run, status: url.pathname.endsWith('/approve') ? 'approved' : run.status })
    })
    mount(<InvestigationDetailPage />, `/investigations/${run.run_id}`, '/investigations/:runId')
    fireEvent.click(await screen.findByRole('button', { name: 'Approve report' }))
    expect(requests.some((r) => r.startsWith('POST'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm report approval' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(requests.some((r) => r.includes('/approve'))).toBe(true)
    expect(requests.some((r) => r.includes('/decision'))).toBe(false)
    expect(screen.queryByRole('button', { name: 'Approve report' })).not.toBeInTheDocument()
  })
  it('sends revision feedback to the correct endpoint', async () => {
    const bodies: string[] = []
    mockFetch((url, init) => {
      if (url.pathname.endsWith('/request-revision')) bodies.push(String(init?.body))
      return json(run)
    })
    mount(<InvestigationDetailPage />, `/investigations/${run.run_id}`, '/investigations/:runId')
    expect(await screen.findByRole('button', { name: 'Request revision' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Revision feedback'), {
      target: { value: 'Explain the missing evidence' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Request revision' }))
    fireEvent.click(screen.getByRole('button', { name: 'Send revision request' }))
    await waitFor(() =>
      expect(bodies).toEqual([JSON.stringify({ feedback: 'Explain the missing evidence' })]),
    )
  })
})

describe('Table accessibility', () => {
  it('opens a row with Enter and Space', () => {
    const columns: DataColumn<{ name: string }>[] = [{ header: 'Name', accessorKey: 'name' }]
    const clicked = vi.fn()
    render(
      <DataTable
        columns={columns}
        data={[{ name: 'Record' }]}
        isLoading={false}
        emptyTitle="Empty"
        onRowClick={clicked}
      />,
    )
    const row = screen.getByText('Record').closest('tr')!
    expect(row).toHaveAttribute('tabindex', '0')
    fireEvent.keyDown(row, { key: 'Enter' })
    fireEvent.keyDown(row, { key: ' ' })
    expect(clicked).toHaveBeenCalledTimes(2)
  })
})
