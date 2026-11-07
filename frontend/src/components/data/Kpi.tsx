import type { ReactNode } from 'react'

import { Card } from '../ui/card'
import { Skeleton } from '../ui/skeleton'
import { cn } from '../../lib/cn'

interface KpiProps {
  label: string
  value: ReactNode
  loading?: boolean
  tone?: 'default' | 'negative' | 'attention' | 'positive'
  hint?: string
}

const TONE_CLASS: Record<NonNullable<KpiProps['tone']>, string> = {
  default: 'text-foreground',
  negative: 'text-status-negative',
  attention: 'text-status-attention',
  positive: 'text-status-positive',
}

export function Kpi({ label, value, loading = false, tone = 'default', hint }: KpiProps) {
  return (
    <Card className="px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-foreground-subtle">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-16" />
      ) : (
        <p className={cn('mt-1 text-2xl font-semibold tabular-nums', TONE_CLASS[tone])}>{value}</p>
      )}
      {hint && <p className="mt-1 text-xs text-foreground-muted">{hint}</p>}
    </Card>
  )
}
