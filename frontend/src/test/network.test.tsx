import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { NetworkPage } from '../features/network/NetworkPage'
import { json } from './fixtures'

vi.mock('../features/network/NetworkCanvas', () => ({
  NetworkCanvas: () => <div>Graph canvas</div>,
}))
afterEach(() => vi.unstubAllGlobals())
it('propagates step zero to every graph request and exposes truncation', async () => {
  const requests: URL[] = []
  const origin = '11111111-1111-4111-8111-111111111111'
  const recipient = '22222222-2222-4222-8222-222222222222'
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string) => {
      const url = new URL(input)
      requests.push(url)
      if (url.pathname.endsWith('/metrics'))
        return Promise.resolve(
          json({
            account_id: origin,
            as_of_step: 0,
            incoming_transaction_count: 0,
            outgoing_transaction_count: 1,
            unique_senders: 0,
            unique_recipients: 1,
            fan_in_pattern: false,
            fan_out_pattern: false,
            velocity_window_steps: 24,
            velocity_count: 1,
            truncated: true,
            disclaimer: 'Structural signals only',
          }),
        )
      if (url.pathname.endsWith('/fund-flow'))
        return Promise.resolve(
          json({
            source_account_id: origin,
            as_of_step: 0,
            max_hops: 3,
            max_branches: 5,
            paths: [],
            truncated: true,
            disclaimer: 'Structural signals only',
          }),
        )
      return Promise.resolve(
        json({
          center_account_id: origin,
          as_of_step: 0,
          hops: 2,
          nodes: [
            { id: origin, external_ref: 'Origin', account_type: 'customer' },
            { id: recipient, external_ref: 'Recipient', account_type: 'customer' },
          ],
          edges: [],
          cycles: [],
          truncated: true,
          disclaimer: 'Structural signals only',
        }),
      )
    }),
  )
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter initialEntries={[`/network?account=${origin}&as_of_step=0`]}>
        <NetworkPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Truncated network — query bounds reached')).toBeInTheDocument()
  expect(screen.getByText('Truncated paths — additional transfers may exist.')).toBeInTheDocument()
  expect(requests.length).toBe(3)
  expect(requests.every((request) => request.searchParams.get('as_of_step') === '0')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Recipient' }))
  await waitFor(() =>
    expect(requests.filter((request) => request.pathname.includes(recipient)).length).toBe(2),
  )
  expect(
    requests.slice(-2).every((request) => request.searchParams.get('as_of_step') === '0'),
  ).toBe(true)
})
it('does not request a graph before an account is chosen', () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <NetworkPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(screen.getByText('Start with an account')).toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
