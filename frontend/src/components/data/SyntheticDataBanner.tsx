import { FlaskConical } from 'lucide-react'

import { cn } from '../../lib/cn'

export function SyntheticDataBanner({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-[var(--radius-control)] border border-border bg-surface-raised px-3 py-1.5 text-xs text-foreground-muted',
        className,
      )}
    >
      <FlaskConical className="h-3.5 w-3.5 text-foreground-subtle" aria-hidden="true" />
      Synthetic demonstration data — no real customers or transactions.
    </div>
  )
}

/** Renders the backend's verbatim structural-signal disclaimer — never paraphrase it (CLAUDE.md). */
export function GraphDisclaimer({ text }: { text: string }) {
  return <p className="text-xs italic text-foreground-subtle">{text}</p>
}
