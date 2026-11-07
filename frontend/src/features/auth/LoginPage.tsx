import { AudioLines } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'
import { describeError } from '../../components/data/ErrorState'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'

export function LoginPage() {
  const { login, status, sessionError } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (status === 'authenticated') {
    const from = (location.state as { from?: { pathname: string; search?: string } } | null)?.from
    const redirectTo =
      from?.pathname?.startsWith('/') &&
      !from.pathname.startsWith('//') &&
      from.pathname !== '/login'
        ? from.pathname + (from.search ?? '')
        : '/'
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <AudioLines className="h-5 w-5 text-accent" aria-hidden="true" />
          <span className="text-base font-semibold text-foreground">SentinelAI</span>
        </div>
        <Card className="p-6">
          <h1 className="text-sm font-semibold text-foreground">Sign in</h1>
          <p className="mt-1 text-xs text-foreground-muted">
            Fraud investigation platform — synthetic data only.
          </p>
          <form className="mt-5 space-y-3.5" onSubmit={handleSubmit}>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {(error || sessionError) && (
              <p role="alert" className="text-xs text-status-negative">
                {error || sessionError}
              </p>
            )}
            <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  )
}
