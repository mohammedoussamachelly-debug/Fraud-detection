import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getInbox } from '../../api/workspace'
import { ErrorState } from '../../components/data/ErrorState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { Queue } from '../workspace/Queue'
export function AlertsListPage() {
  const [search, setSearch] = useState(''),
    [status, setStatus] = useState('attention'),
    [severity, setSeverity] = useState(''),
    [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ['workspace-alerts', search, status, severity, offset],
    queryFn: () => getInbox({ search, status, severity, offset, limit: 25 }),
  })
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Review the most important activity first. Amounts are in synthetic units."
      />
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="grid gap-1 text-xs">
          Search activity
          <Input
            value={search}
            placeholder="Account or activity"
            onChange={(e) => {
              setSearch(e.target.value)
              setOffset(0)
            }}
          />
        </label>
        <label className="grid gap-1 text-xs">
          Review status
          <select
            className="rounded-control border border-border bg-surface px-3 py-2"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              setOffset(0)
            }}
          >
            {[
              ['attention', 'Needs attention'],
              ['', 'All statuses'],
              ['open', 'Open'],
              ['triaged', 'Triaged'],
              ['escalated', 'Escalated'],
              ['dismissed', 'Dismissed'],
            ].map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1 text-xs">
          Severity
          <select
            className="rounded-control border border-border bg-surface px-3 py-2"
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value)
              setOffset(0)
            }}
          >
            {['', 'critical', 'high', 'medium', 'low'].map((value) => (
              <option key={value} value={value}>
                {value || 'All severities'}
              </option>
            ))}
          </select>
        </label>
      </div>
      {query.error ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.data ? (
        <div role="status" aria-label="Loading alerts">
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <>
          <Queue items={query.data.items} />
          <Pagination
            total={query.data.total}
            limit={25}
            offset={offset}
            onOffsetChange={setOffset}
            disabled={query.isFetching}
          />
        </>
      )}
    </>
  )
}
