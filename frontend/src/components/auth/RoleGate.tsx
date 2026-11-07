import type { ReactNode } from 'react'

import { useAuth } from '../../context/AuthContext'
import type { UserRole } from '../../api/types'

interface RoleGateProps {
  roles: UserRole[]
  children: ReactNode
  fallback?: ReactNode
}

/** Hides UI the signed-in role can't act on. This is a display convenience only —
 * the backend re-checks the role on every request regardless (docs/authentication.md). */
export function RoleGate({ roles, children, fallback = null }: RoleGateProps) {
  const { hasRole } = useAuth()
  return hasRole(...roles) ? <>{children}</> : <>{fallback}</>
}
