import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listAuditLog } from '../../api/audit'
import { useAuth } from '../../context/AuthContext'
import { DateRangeFilter, FilterBar } from '../../components/data/FilterBar'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { EvidenceViewer } from '../../components/data/EvidenceViewer'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime } from '../../lib/format'

export function AuditPage() {
  const { hasRole } = useAuth()
  return hasRole('admin') ? (
    <AuditLog />
  ) : (
    <>
      <PageHeader title="Audit log" />
      <EmptyState
        title="Administrator access required"
        description="Your role does not have permission to view the audit log."
      />
    </>
  )
}
function AuditLog() {
  const [actionInput, setActionInput] = useState('')
  const [action, setAction] = useState('')
  const [dates, setDates] = useState({ from: '', to: '' })
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ['audit-log', action, dates, offset],
    queryFn: () =>
      listAuditLog({
        action: action || undefined,
        occurred_from: dates.from || undefined,
        occurred_to: dates.to || undefined,
        limit: 25,
        offset,
      }),
  })
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Recorded authentication, case, and investigation events. Administrator access."
      />
      <FilterBar>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setAction(actionInput.trim())
            setOffset(0)
          }}
        >
          <label className="grid gap-1 text-xs text-foreground-muted">
            Exact action
            <Input
              value={actionInput}
              onChange={(e) => setActionInput(e.target.value)}
              placeholder="All actions"
            />
          </label>
          <Button type="submit">Apply</Button>
        </form>
        <DateRangeFilter
          from={dates.from}
          to={dates.to}
          onChange={(from, to) => {
            setDates({ from, to })
            setOffset(0)
          }}
        />
      </FilterBar>
      {query.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <EmptyState title="No audit events match these filters" />
      ) : (
        <ol className="space-y-3">
          {query.data.items.map((event) => (
            <li key={event.id} className="rounded-surface border border-border bg-surface p-4">
              <div className="flex flex-wrap justify-between gap-2">
                <h2 className="text-sm font-medium">{event.action.replace(/_/g, ' ')}</h2>
                <time dateTime={event.occurred_at} className="text-xs text-foreground-muted">
                  {formatDateTime(event.occurred_at)}
                </time>
              </div>
              <p className="mt-2 break-all font-mono text-xs text-foreground-muted">
                {event.entity_type}: {event.entity_id ?? '—'} · user: {event.user_id ?? 'system'}
              </p>
              <EvidenceViewer payload={event.event_metadata} />
            </li>
          ))}
        </ol>
      )}
      {query.data && (
        <Pagination
          limit={25}
          offset={offset}
          total={query.data.total}
          disabled={query.isFetching}
          onOffsetChange={setOffset}
        />
      )}
    </>
  )
}
