import type { ReactNode } from 'react'

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3 rounded-surface border border-border bg-surface p-3">
      {children}
    </div>
  )
}

export function DateRangeFilter({
  from,
  to,
  onChange,
}: {
  from: string
  to: string
  onChange: (from: string, to: string) => void
}) {
  return (
    <>
      <label className="grid gap-1 text-xs text-foreground-muted">
        From (UTC)
        <input
          className="h-8 rounded-control border border-border-strong bg-surface px-2 text-foreground"
          type="date"
          value={from}
          max={to || undefined}
          onChange={(e) => onChange(e.target.value, to)}
        />
      </label>
      <label className="grid gap-1 text-xs text-foreground-muted">
        Through (UTC)
        <input
          className="h-8 rounded-control border border-border-strong bg-surface px-2 text-foreground"
          type="date"
          value={to}
          min={from || undefined}
          onChange={(e) => onChange(from, e.target.value)}
        />
      </label>
    </>
  )
}
