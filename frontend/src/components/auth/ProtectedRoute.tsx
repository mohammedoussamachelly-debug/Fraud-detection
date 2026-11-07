import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'

export function ProtectedRoute() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="flex h-screen items-center justify-center bg-background" role="status">
        <p className="text-sm text-foreground-muted">Loading SentinelAI…</p>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
