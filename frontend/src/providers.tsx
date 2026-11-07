import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { AuthProvider } from './context/AuthContext'
import { queryClient } from './lib/queryClient'
import { TooltipProvider } from './components/ui/tooltip'

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider delayDuration={200}>{children}</TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  )
}
