import type { ReactNode } from 'react'

export function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 border-b border-border py-2 last:border-0">
      <dt className="text-xs text-foreground-muted">{label}</dt>
      <dd className="min-w-0 break-all text-right text-sm tabular-nums">{children}</dd>
    </div>
  )
}
