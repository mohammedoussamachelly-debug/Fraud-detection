import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { DataColumn } from '../../components/data/DataTable'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'
import { FilterBar } from '../../components/data/FilterBar'
import { listCases } from '../../api/cases'
import type { Case, CasePriority, CaseStatus } from '../../api/types'
import { DataTable } from '../../components/data/DataTable'
import { CaseStatusBadge } from '../../components/data/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { Pagination } from '../../components/ui/pagination'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import { formatDateTime, shortId } from '../../lib/format'

const STATUS_OPTIONS: Array<CaseStatus | 'all'> = [
  'all',
  'open',
  'investigating',
  'pending_review',
  'resolved',
  'closed',
]
const LIMIT = 25

const PRIORITY_TONE: Record<CasePriority, string> = {
  low: 'text-foreground-muted',
  medium: 'text-status-info',
  high: 'text-status-attention',
  critical: 'text-status-negative',
}

const columns: DataColumn<Case>[] = [
  {
    header: 'Case',
    accessorKey: 'id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs text-foreground-muted">{shortId(getValue<string>())}</span>
    ),
  },
  {
    header: 'Status',
    accessorKey: 'status',
    cell: ({ getValue }) => <CaseStatusBadge status={getValue<string>()} />,
  },
  {
    header: 'Priority',
    accessorKey: 'priority',
    cell: ({ getValue }) => {
      const priority = getValue<CasePriority>()
      return (
        <span className={`text-sm font-medium capitalize ${PRIORITY_TONE[priority]}`}>
          {priority}
        </span>
      )
    },
  },
  {
    header: 'Assignee',
    accessorKey: 'assigned_analyst_id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">
        {getValue<string | null>() ? shortId(getValue<string>()) : 'Unassigned'}
      </span>
    ),
  },
  {
    header: 'Created',
    accessorKey: 'created_at',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
  {
    header: 'Updated',
    accessorKey: 'updated_at',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
]

export function CasesListPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { user } = useAuth()
  const [mine, setMine] = useState(false)
  const [status, setStatus] = useState<CaseStatus | 'all'>(() =>
    STATUS_OPTIONS.includes(params.get('status') as CaseStatus)
      ? (params.get('status') as CaseStatus)
      : 'all',
  )
  const [offset, setOffset] = useState(0)

  const query = useQuery({
    queryKey: ['cases', { status, offset, mine, userId: user?.id }],
    queryFn: () =>
      listCases({
        status: status === 'all' ? undefined : status,
        assigned_to_user_id: mine ? user?.id : undefined,
        limit: LIMIT,
        offset,
      }),
    placeholderData: keepPreviousData,
  })

  return (
    <div>
      <PageHeader title="Cases" description="Investigation cases grouping one or more alerts." />
      <FilterBar>
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value as CaseStatus | 'all')
            setOffset(0)
          }}
        >
          <SelectTrigger aria-label="Case status">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {option === 'all' ? 'All statuses' : option.replace(/_/g, ' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex h-8 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => {
              setMine(e.target.checked)
              setOffset(0)
            }}
          />{' '}
          Assigned to me
        </label>
      </FilterBar>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        isLoading={query.isLoading || query.isPlaceholderData}
        error={query.error}
        onRetry={() => query.refetch()}
        onRowClick={(row) => navigate(`/cases/${row.id}`)}
        emptyTitle="No cases match this filter"
        emptyDescription="Cases are created from one or more alerts."
      />
      {query.data && query.data.total > 0 && (
        <Pagination
          limit={LIMIT}
          offset={offset}
          total={query.data.total}
          disabled={query.isFetching}
          onOffsetChange={setOffset}
        />
      )}
    </div>
  )
}
