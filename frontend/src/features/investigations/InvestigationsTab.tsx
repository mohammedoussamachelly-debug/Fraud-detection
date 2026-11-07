import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Pagination } from '../../components/ui/pagination'
import { Play } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { listCaseInvestigations, startInvestigation } from '../../api/investigations'
import { describeError, ErrorState } from '../../components/data/ErrorState'
import { EmptyState } from '../../components/data/EmptyState'
import { InvestigationStatusBadge } from '../../components/data/StatusBadge'
import { Button } from '../../components/ui/button'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime, shortId } from '../../lib/format'

export function InvestigationsTab({ caseId }: { caseId: string }) {
  const [offset, setOffset] = useState(0)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const query = useQuery({
    queryKey: ['case-investigations', caseId, offset],
    queryFn: () => listCaseInvestigations(caseId, { limit: 25, offset }),
  })

  const startMutation = useMutation({
    mutationFn: () => startInvestigation(caseId),
    onSuccess: (started) => {
      queryClient.invalidateQueries({ queryKey: ['case-investigations', caseId] })
      navigate(`/investigations/${started.run_id}`)
    },
  })

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-foreground-muted">
          AI-assisted evidence review — every run ends at a human approval gate.
        </p>
        <Button
          variant="primary"
          size="sm"
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
        >
          <Play className="h-3.5 w-3.5" />
          {startMutation.isPending ? 'Starting…' : 'Start investigation'}
        </Button>
      </div>
      {startMutation.error && (
        <p className="mb-3 text-xs text-status-negative">{describeError(startMutation.error)}</p>
      )}

      {query.isLoading && <Skeleton className="h-16 w-full" />}
      {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      {query.data && query.data.items.length === 0 && (
        <EmptyState
          title="No investigations started yet"
          description="An agent run assembles evidence into a draft report for your review."
        />
      )}
      {query.data && query.data.items.length > 0 && (
        <div className="space-y-2">
          {query.data.items.map((run) => (
            <Link
              key={run.run_id}
              className="flex flex-wrap gap-2 items-center justify-between rounded-surface border border-border bg-surface px-3 py-2.5 cursor-pointer hover:bg-neutral-50 dark:hover:bg-neutral-900"
              to={`/investigations/${run.run_id}`}
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-foreground-muted">
                  {shortId(run.run_id)}
                </span>
                <InvestigationStatusBadge status={run.status} />
                {run.revision_count > 0 && (
                  <span className="text-xs text-foreground-subtle">
                    {run.revision_count} revision{run.revision_count === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              <span className="text-xs text-foreground-subtle">
                {formatDateTime(run.started_at)}
              </span>
            </Link>
          ))}
        </div>
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
    </div>
  )
}
