import { AlertTriangle } from 'lucide-react'

import { ApiError } from '../../api/client'
import { Button } from '../ui/button'

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

interface ErrorStateProps {
  error: unknown
  onRetry?: () => void
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center"
      role="alert"
    >
      <AlertTriangle className="h-5 w-5 text-status-negative" aria-hidden="true" />
      <p className="text-sm font-medium text-foreground">Could not load this data</p>
      <p className="max-w-sm text-sm text-foreground-muted">{describeError(error)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}
