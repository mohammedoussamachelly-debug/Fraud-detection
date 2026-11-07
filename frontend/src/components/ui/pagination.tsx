import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from './button'

interface PaginationProps {
  disabled?: boolean
  limit: number
  offset: number
  total: number
  onOffsetChange: (offset: number) => void
}

export function Pagination({
  limit,
  offset,
  total,
  onOffsetChange,
  disabled = false,
}: PaginationProps) {
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)

  return (
    <div className="flex items-center justify-between px-1 py-2 text-xs text-foreground-muted">
      <span className="tabular-nums">
        {from}-{to} of {total}
      </span>
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="icon"
          disabled={disabled || offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          disabled={disabled || offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
