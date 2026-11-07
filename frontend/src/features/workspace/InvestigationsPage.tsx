import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getWorkspaceCases } from '../../api/workspace'
import { ErrorState } from '../../components/data/ErrorState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime } from '../../lib/format'
import { readable } from './presentation'
export function InvestigationsPage() {
  const [status, setStatus] = useState(''),
    [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ['workspace-cases', status, offset],
    queryFn: () => getWorkspaceCases({ status, offset, limit: 25 }),
  })
  return (
    <>
      <PageHeader
        title="Investigations"
        description="Evidence, reports, and decisions in one place."
      />
      <label className="mb-4 grid w-fit gap-1 text-xs">
        Case status
        <select
          className="rounded-control border border-border bg-surface px-3 py-2"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value)
            setOffset(0)
          }}
        >
          {['', 'open', 'investigating', 'pending_review', 'resolved', 'closed'].map((value) => (
            <option key={value} value={value}>
              {readable(value) || 'All statuses'}
            </option>
          ))}
        </select>
      </label>
      {query.error ? (
        <ErrorState error={query.error} />
      ) : !query.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <ul className="divide-y divide-border rounded-control border border-border bg-surface">
            {query.data.items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div>
                  <Link className="text-sm font-medium text-accent" to={`/cases/${item.id}`}>
                    {item.title}
                  </Link>
                  <p className="mt-1 text-xs text-foreground-muted">
                    {formatDateTime(item.created_at)} · {item.priority} priority
                  </p>
                </div>
                <span className="text-xs capitalize">{readable(item.status)}</span>
              </li>
            ))}
          </ul>
          {!query.data.items.length && (
            <p className="py-6 text-sm text-foreground-muted">
              No investigations match. Choose an alert to begin a review.
            </p>
          )}
          <Pagination
            total={query.data.total}
            limit={25}
            offset={offset}
            onOffsetChange={setOffset}
          />
        </>
      )}
    </>
  )
}
