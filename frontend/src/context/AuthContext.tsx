import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { useQueryClient } from '@tanstack/react-query'

import { describeError } from '../components/data/ErrorState'
import { fetchCurrentUser, login as loginRequest } from '../api/auth'
import { clearToken, getToken, onUnauthorized, setToken } from '../api/tokenStore'
import type { User, UserRole } from '../api/types'

interface AuthState {
  sessionError: string | null
  user: User | null
  status: 'loading' | 'authenticated' | 'unauthenticated'
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  hasRole: (...roles: UserRole[]) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const generation = useRef(0)
  const [state, setState] = useState<AuthState>({
    user: null,
    status: 'loading',
    sessionError: null,
  })

  const loadCurrentUser = useCallback(async () => {
    const current = ++generation.current
    if (!getToken()) {
      setState({ user: null, status: 'unauthenticated', sessionError: null })
      return
    }
    try {
      const user = await fetchCurrentUser()
      if (current === generation.current)
        setState({ user, status: 'authenticated', sessionError: null })
    } catch (error) {
      if (current !== generation.current) return
      clearToken()
      setState({
        user: null,
        status: 'unauthenticated',
        sessionError: `Could not restore your session: ${describeError(error)}`,
      })
    }
  }, [])

  useEffect(() => {
    void loadCurrentUser()
  }, [loadCurrentUser])

  useEffect(() => {
    return onUnauthorized(() => {
      generation.current++
      clearToken()
      queryClient.clear()
      setState({
        user: null,
        status: 'unauthenticated',
        sessionError: 'Your session has expired. Sign in again.',
      })
    })
  }, [queryClient])

  const login = useCallback(
    async (email: string, password: string) => {
      const current = ++generation.current
      const response = await loginRequest(email, password)
      if (current !== generation.current) return
      setToken(response.access_token)
      try {
        const user = await fetchCurrentUser()
        if (current !== generation.current) return
        queryClient.clear()
        setState({ user, status: 'authenticated', sessionError: null })
      } catch (error) {
        if (current === generation.current) clearToken()
        throw error
      }
    },
    [queryClient],
  )

  const logout = useCallback(() => {
    generation.current++
    clearToken()
    queryClient.clear()
    setState({ user: null, status: 'unauthenticated', sessionError: null })
  }, [queryClient])

  const hasRole = useCallback(
    (...roles: UserRole[]) => state.user !== null && roles.includes(state.user.role),
    [state.user],
  )

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout, hasRole }),
    [state, login, logout, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within an AuthProvider')
  return context
}
