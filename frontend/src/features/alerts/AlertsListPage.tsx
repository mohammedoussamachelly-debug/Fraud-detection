import { keepPreviousData, useQuery } from '@tanstack/react-query'
import type { DataColumn } from '../../components/data/DataTable'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { listAlerts } from '../../api/alerts'
import type { Alert, AlertStatus } from '../../api/types'
import { DateRangeFilter, FilterBar } from '../../components/data/FilterBar'
import { DataTable } from '../../components/data/DataTable'
import { AlertStatusBadge } from '../../components/data/StatusBadge'
import { SeverityBadge } from '../../components/data/SeverityBadge'
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

const STATUS_OPTIONS: Array<AlertStatus | 'all'> = [
  'all',
  'open',
  'triaged',
  'escalated',
  'dismissed',
]
const SEVERITY_OPTIONS = ['all', 'low', 'medium', 'high', 'critical']
const LIMIT = 25

const columns: DataColumn<Alert>[] = [
  {
    header: 'Alert',
    accessorKey: 'id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs text-foreground-muted">{shortId(getValue<string>())}</span>
    ),
  },
  {
    header: 'Type',
    accessorKey: 'alert_type',
    cell: ({ getValue }) => (
      <span className="capitalize">{getValue<string>().replace(/_/g, ' ')}</span>
    ),
  },
  {
    header: 'Severity',
    accessorKey: 'severity',
    cell: ({ getValue }) => <SeverityBadge severity={getValue<string>()} />,
  },
  {
    header: 'Status',
    accessorKey: 'status',
    cell: ({ getValue }) => <AlertStatusBadge status={getValue<string>()} />,
  },
  {
    header: 'Transaction',
    accessorKey: 'transaction_id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs text-foreground-muted">{shortId(getValue<string>())}</span>
    ),
  },
  {
    header: 'Created',
    accessorKey: 'created_at',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
]

export function AlertsListPage() {
  const navigate = useNavigate()
  const [search] = useSearchParams()
  const [status, setStatus] = useState<AlertStatus | 'all'>(() =>
    STATUS_OPTIONS.includes(search.get('status') as AlertStatus)
      ? (search.get('status') as AlertStatus)
      : 'all',
  )
  const [severity, setSeverity] = useState<string>(() =>
    SEVERITY_OPTIONS.includes(search.get('severity') ?? '') ? search.get('severity')! : 'all',
  )
  const [dates, setDates] = useState({ from: '', to: '' })
  const [offset, setOffset] = useState(0)

  const query = useQuery({
    queryKey: ['alerts', { status, severity, offset, dates }],
    queryFn: () =>
      listAlerts({
        status: status === 'all' ? undefined : status,
        severity: severity === 'all' ? undefined : severity,
        created_from: dates.from || undefined,
        created_to: dates.to || undefined,
        limit: LIMIT,
        offset,
      }),
    placeholderData: keepPreviousData,
  })

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Transactions that crossed a model or rule threshold."
      />
      <FilterBar>
        <Select
          value={status}
          onValueChange={(value) => {
            setStatus(value as AlertStatus | 'all')
            setOffset(0)
          }}
        >
          <SelectTrigger aria-label="Alert status">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {option === 'all' ? 'All statuses' : option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={severity}
          onValueChange={(value) => {
            setSeverity(value)
            setOffset(0)
          }}
        >
          <SelectTrigger aria-label="Alert severity">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            {SEVERITY_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {option === 'all' ? 'All severities' : option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DateRangeFilter
          from={dates.from}
          to={dates.to}
          onChange={(from, to) => {
            setDates({ from, to })
            setOffset(0)
          }}
        />
      </FilterBar>
      <p className="mb-2 text-xs text-foreground-muted">
        Newest first · use severity to focus your triage
      </p>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        isLoading={query.isLoading || query.isPlaceholderData}
        error={query.error}
        onRetry={() => query.refetch()}
        onRowClick={(row) => navigate(`/alerts/${row.id}`)}
        emptyTitle="No alerts match these filters"
        emptyDescription="Try widening the status or severity filter."
      />
      {query.data && query.data.total > 0 && (
        <Pagination
          limit={LIMIT}
          offset={offset}
          total={query.data.total}
          onOffsetChange={setOffset}
        />
      )}
    </div>
  )
}
