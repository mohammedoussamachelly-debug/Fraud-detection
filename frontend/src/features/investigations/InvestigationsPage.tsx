import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { listCases } from '../../api/cases'
import { ErrorState } from '../../components/data/ErrorState'
import { EmptyState } from '../../components/data/EmptyState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { CaseStatusBadge } from '../../components/data/StatusBadge'
import { UUID_PATTERN } from '../../lib/validation'
import { InvestigationsTab } from './InvestigationsTab'
import { shortId } from '../../lib/format'

export function InvestigationsPage() {
  const [params, setParams] = useSearchParams()
  const caseId = params.get('case') ?? ''
  const [input, setInput] = useState(caseId)
  const [offset, setOffset] = useState(0)
  const cases = useQuery({
    queryKey: ['cases', 'investigation-picker', offset],
    queryFn: () => listCases({ limit: 10, offset }),
    enabled: !caseId,
  })
  return (
    <>
      <PageHeader
        title="AI Investigations"
        description="Review evidence collection, findings, and reports within a case."
      />
      <form
        className="mb-5 flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          setParams({ case: input.trim() })
        }}
      >
        <label className="grid gap-1 text-xs text-foreground-muted">
          Case UUID
          <Input
            required
            pattern={UUID_PATTERN}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            className="w-72 max-w-full"
          />
        </label>
        <Button type="submit">Open case runs</Button>
        {caseId && (
          <Button
            onClick={() => {
              setParams({})
              setInput('')
            }}
            type="button"
          >
            Choose another case
          </Button>
        )}
      </form>
      {caseId ? (
        <>
          <Link className="mb-4 inline-block font-mono text-xs text-accent" to={`/cases/${caseId}`}>
            Case {shortId(caseId)} →
          </Link>
          <InvestigationsTab key={caseId} caseId={caseId} />
        </>
      ) : cases.isPending ? (
        <Skeleton className="h-48 w-full" />
      ) : cases.error ? (
        <ErrorState error={cases.error} onRetry={() => cases.refetch()} />
      ) : cases.data.items.length === 0 ? (
        <EmptyState
          title="Create a case to start investigating"
          action={
            <Link className="text-sm text-accent" to="/alerts">
              Open alert queue →
            </Link>
          }
        />
      ) : (
        <>
          <h2 className="mb-3 text-sm font-semibold">Choose a case</h2>
          <ul className="divide-y divide-border rounded-surface border border-border bg-surface">
            {cases.data.items.map((c) => (
              <li key={c.id}>
                <button
                  className="flex w-full flex-wrap items-center justify-between gap-2 p-3 text-left hover:bg-background"
                  onClick={() => {
                    setInput(c.id)
                    setParams({ case: c.id })
                  }}
                >
                  <span className="font-mono text-sm">{shortId(c.id)}</span>
                  <CaseStatusBadge status={c.status} />
                </button>
              </li>
            ))}
          </ul>
          <Pagination
            limit={10}
            offset={offset}
            total={cases.data.total}
            disabled={cases.isFetching}
            onOffsetChange={setOffset}
          />
        </>
      )}
    </>
  )
}
