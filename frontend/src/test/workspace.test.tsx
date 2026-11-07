import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { InvestigateButton, Connections } from '../features/workspace/Activity'
import { OverviewPage } from '../features/overview/OverviewPage'
import { clearToken, setToken } from '../api/tokenStore'
import { alert, caseDetail, json } from './fixtures'

vi.mock('../features/network/NetworkCanvas', () => ({
  NetworkCanvas: () => <div>Connected account visualization</div>,
}))
afterEach(() => {
  clearToken()
  vi.unstubAllGlobals()
})
function Location() {
  const location = useLocation()
  return (
    <p>
      Destination: {location.pathname}
      {location.search}
    </p>
  )
}
function mount(element: React.ReactNode) {
  setToken('workspace-test')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <Routes>
          <Route path="/" element={element} />
          <Route path="*" element={<Location />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}
it('opens the returned case with one click and refreshes the action queue', async () => {
  const requests: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      requests.push(url)
      return Promise.resolve(json({ case_id: caseDetail.id, created: false }))
    }),
  )
  const client = mount(<InvestigateButton alertId={alert.id} />)
  client.setQueryData(['workspace-dashboard'], { attention: 1 })
  client.setQueryData(['workspace-alerts'], { items: [] })
  fireEvent.click(screen.getByRole('button', { name: 'Investigate' }))
  expect(await screen.findByText(`Destination: /cases/${caseDetail.id}`)).toBeInTheDocument()
  expect(requests).toHaveLength(1)
  expect(requests[0]).toContain(`/workspace/alerts/${alert.id}/investigate`)
  expect(client.getQueryState(['workspace-dashboard'])?.isInvalidated).toBe(true)
  expect(client.getQueryState(['workspace-alerts'])?.isInvalidated).toBe(true)
})
it('opens an existing investigation without creating another case', async () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  mount(<InvestigateButton alertId={alert.id} caseId={caseDetail.id} />)
  fireEvent.click(screen.getByRole('link', { name: 'Open investigation →' }))
  expect(await screen.findByText(`Destination: /cases/${caseDetail.id}`)).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
it('takes a guided scenario to its actual payment and connected account', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) =>
      Promise.resolve(
        json(
          input.endsWith('/demo/scenarios')
            ? {
                items: [
                  {
                    batch: 'test',
                    key: 'incoming',
                    title: 'Many senders, one recipient',
                    description: 'Synthetic example',
                    account_id: 'collection-account',
                    transaction_id: alert.transaction_id,
                    model_score: 0.000001,
                    model_level: 'low',
                  },
                ],
                notice: 'Synthetic demonstration; genuine model results.',
              }
            : { transactions: 10000, attention: 8, investigations: 1, review: 0, queue: [] },
        ),
      ),
    ),
  )
  mount(<OverviewPage />)
  fireEvent.click(screen.getByText('Explore demo · five guided scenarios'))
  fireEvent.click(await screen.findByRole('link', { name: 'Explore scenario →' }))
  expect(
    await screen.findByText(
      `Destination: /transactions/${alert.transaction_id}?connected=collection-account`,
    ),
  ).toBeInTheDocument()
})
it('includes the inspected hour in every connected-account query', async () => {
  const requests: URL[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) => {
      const url = new URL(input)
      requests.push(url)
      return Promise.resolve(
        json(
          url.pathname.endsWith('/metrics')
            ? {
                incoming_transaction_count: 10,
                outgoing_transaction_count: 6,
                unique_senders: 10,
                unique_recipients: 6,
                fan_in_pattern: true,
                fan_out_pattern: true,
              }
            : url.pathname.endsWith('/fund-flow')
              ? {
                  paths: [],
                  truncated: false,
                  disclaimer: 'Recorded transfers only',
                }
              : { nodes: [], edges: [], cycles: [], truncated: false, disclaimer: 'Synthetic' },
        ),
      )
    }),
  )
  mount(<Connections accountId="collection-account" step={0} />)
  await screen.findByText(/Multiple senders converge here/)
  await waitFor(() => expect(requests).toHaveLength(3))
  expect(requests.every((url) => url.searchParams.get('as_of_step') === '1')).toBe(true)
})
