import { FileText } from 'lucide-react'

import { shortId } from '../../lib/format'
import { cn } from '../../lib/cn'

interface CitationChipProps {
  reference: string
  resolved: boolean
  onClick?: () => void
  label?: string
}

/** Renders an evidence reference like "transaction:<uuid>" as a compact chip. `resolved` marks
 * whether it matches a real collected evidence item in this run — an unresolved citation is a
 * signal worth surfacing, not hiding, since every hypothesis citation should trace to real evidence. */
export function CitationChip({ reference, resolved, onClick, label }: CitationChipProps) {
  const [type, id] = reference.split(':')
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-mono text-xs',
        resolved
          ? 'border-border-strong bg-surface-raised text-foreground-muted hover:text-foreground'
          : 'border-status-negative/40 bg-status-negative/10 text-status-negative',
      )}
      title={resolved ? reference : `${reference} — not found in this run's collected evidence`}
    >
      <FileText className="h-3 w-3" aria-hidden="true" />
      {label ?? `${type}:${id ? shortId(id) : '?'}`}
      {!resolved && ' · unresolved'}
    </button>
  )
}
