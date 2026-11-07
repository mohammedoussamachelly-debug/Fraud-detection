import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from '../context/AuthContext'
import { clearToken, getToken, setToken } from '../api/tokenStore'
import { apiGet } from '../api/client'
import { LoginPage } from '../features/auth/LoginPage'
import { ProtectedRoute } from '../components/auth/ProtectedRoute'
import { json, user } from './fixtures'

function Session() {
  const { status, logout } = useAuth()
  return (
    <>
      <p>{status}</p>
      <button onClick={logout}>Sign out</button>
    </>
  )
}
afterEach(() => {
  clearToken()
  vi.unstubAllGlobals()
})
beforeEach(() => clearToken())
it('clears private cached data and the token on logout', async () => {
  setToken('first-session')
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(json(user))),
  )
  const client = new QueryClient()
  client.setQueryData(['case', 'private'], { confidential: true })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Session />
      </AuthProvider>
    </QueryClientProvider>,
  )
  await screen.findByText('authenticated')
  fireEvent.click(screen.getByText('Sign out'))
  expect(getToken()).toBeNull()
  expect(client.getQueryData(['case', 'private'])).toBeUndefined()
})
it('expires the session and cache on HTTP 401', async () => {
  setToken('expired-session')
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(url.endsWith('/auth/me') ? json(user) : json({ detail: 'Expired' }, 401)),
    ),
  )
  const client = new QueryClient()
  client.setQueryData(['private'], { confidential: true })
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Session />
      </AuthProvider>
    </QueryClientProvider>,
  )
  await screen.findByText('authenticated')
  await act(async () => {
    await expect(apiGet('/alerts')).rejects.toMatchObject({ status: 401 })
  })
  await screen.findByText('unauthenticated')
  expect(client.getQueryData(['private'])).toBeUndefined()
  expect(getToken()).toBeNull()
})
it('does not let a stale response for the previous token expire the new session', async () => {
  setToken('old-token')
  let finish!: (response: Response) => void
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        }),
    ),
  )
  const request = apiGet('/alerts')
  setToken('new-token')
  finish(json({ detail: 'Expired' }, 401))
  await expect(request).rejects.toMatchObject({ status: 401 })
  expect(getToken()).toBe('new-token')
})
it('returns to a protected deep link after signing in', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/auth/login')
          ? json({ access_token: 'signed-in', token_type: 'bearer', expires_in: 100 })
          : json(user),
      ),
    ),
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/cases/case-123?tab=decision']}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route path="/cases/:id" element={<p>Requested case</p>} />
            </Route>
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await screen.findByRole('heading', { name: 'Sign in' })
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: user.email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByText('Requested case')).toBeInTheDocument()
})
it('cleans up a token if fetching the signed-in profile fails', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        url.endsWith('/auth/login')
          ? json({ access_token: 'new-session', token_type: 'bearer', expires_in: 100 })
          : json({ detail: 'Profile unavailable' }, 503),
      ),
    ),
  )
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: user.email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'test-password' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Profile unavailable'))
  expect(getToken()).toBeNull()
})

it('rejects a successful old-session mutation before it can repopulate private cache', async () => {
  setToken('old-token')
  let finish!: (response: Response) => void
  vi.stubGlobal(
    'fetch',
    vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        }),
    ),
  )
  const request = apiGet('/cases/private')
  clearToken()
  finish(json({ private: true }))
  await expect(request).rejects.toMatchObject({ status: 401 })
})
