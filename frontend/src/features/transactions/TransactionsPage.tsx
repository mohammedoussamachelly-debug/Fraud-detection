import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { listTransactions } from '../../api/transactions'
import type { Transaction } from '../../api/types'
import { DataTable, type DataColumn } from '../../components/data/DataTable'
import { FilterBar } from '../../components/data/FilterBar'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { formatCurrency, formatDateTime, shortId } from '../../lib/format'
import { TransactionDetailPanel } from './TransactionDetailPanel'

const columns: DataColumn<Transaction>[] = [
  {
    header: 'Reference',
    accessorKey: 'external_ref',
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue<string>()}</span>,
  },
  { header: 'Type', accessorKey: 'type' },
  {
    header: 'Amount · units',
    accessorKey: 'amount',
    cell: ({ getValue }) => (
      <span className="block text-right tabular-nums">{formatCurrency(getValue<string>())}</span>
    ),
  },
  {
    header: 'Origin',
    accessorKey: 'origin_account_id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{shortId(getValue<string>())}</span>
    ),
  },
  {
    header: 'Recipient',
    accessorKey: 'dest_account_id',
    cell: ({ getValue }) => (
      <span className="font-mono text-xs">{shortId(getValue<string>())}</span>
    ),
  },
  { header: 'Step ↑', accessorKey: 'step' },
  {
    header: 'Occurred',
    accessorKey: 'occurred_at',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
]
import { UUID_PATTERN } from '../../lib/validation'

export function TransactionsPage() {
  const { transactionId } = useParams()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [accountInput, setAccountInput] = useState(params.get('account_id') ?? '')
  const [lookup, setLookup] = useState('')
  const account = params.get('account_id') ?? ''
  const type = params.get('type') ?? ''
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  const query = useQuery({
    queryKey: ['transactions', { account, type, offset }],
    queryFn: () =>
      listTransactions({
        account_id: account || undefined,
        type: type || undefined,
        offset,
        limit: 25,
      }),
    placeholderData: keepPreviousData,
  })
  function filter(event: FormEvent) {
    event.preventDefault()
    const next = new URLSearchParams(params)
    if (accountInput.trim()) next.set('account_id', accountInput.trim())
    else next.delete('account_id')
    next.delete('offset')
    setParams(next)
  }
  function openTransaction(id: string) {
    navigate(`/transactions/${encodeURIComponent(id)}${params.size ? `?${params}` : ''}`)
  }
  return (
    <>
      <PageHeader
        title="Transactions"
        description="Inspect ingested activity, persisted model scores, and account relationships."
      />
      <FilterBar>
        <form className="flex flex-wrap items-end gap-2" onSubmit={filter}>
          <label className="grid gap-1 text-xs text-foreground-muted">
            Account UUID
            <Input
              value={accountInput}
              onChange={(e) => setAccountInput(e.target.value)}
              pattern={UUID_PATTERN}
              placeholder="All accounts"
              className="w-64 max-w-full"
            />
          </label>
          <Button type="submit">Apply</Button>
        </form>
        <label className="grid gap-1 text-xs text-foreground-muted">
          Transaction type
          <select
            className="h-8 rounded-control border border-border-strong bg-surface px-2 text-sm text-foreground"
            value={type}
            onChange={(e) => {
              const next = new URLSearchParams(params)
              if (e.target.value) next.set('type', e.target.value)
              else next.delete('type')
              next.delete('offset')
              setParams(next)
            }}
          >
            <option value="">All types</option>
            {['TRANSFER', 'PAYMENT', 'CASH_IN', 'CASH_OUT', 'DEBIT'].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            openTransaction(lookup.trim())
          }}
        >
          <label className="grid gap-1 text-xs text-foreground-muted">
            Open transaction UUID
            <Input
              required
              pattern={UUID_PATTERN}
              value={lookup}
              onChange={(e) => setLookup(e.target.value)}
              className="w-64 max-w-full"
            />
          </label>
          <Button type="submit">Open</Button>
        </form>
      </FilterBar>
      <p className="mb-2 text-xs text-foreground-muted">
        Simulation step ascending · amounts are synthetic units, with no currency assigned
      </p>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        isLoading={query.isPending || query.isPlaceholderData}
        error={query.error}
        onRetry={() => query.refetch()}
        emptyTitle="No matching transactions"
        emptyDescription="Try another account or transaction type."
        onRowClick={(t) => openTransaction(t.id)}
      />
      {query.data && (
        <Pagination
          limit={25}
          offset={offset}
          total={query.data.total}
          disabled={query.isFetching}
          onOffsetChange={(value) => {
            const next = new URLSearchParams(params)
            next.set('offset', String(value))
            setParams(next)
          }}
        />
      )}
      {transactionId && (
        <TransactionDetailPanel
          key={transactionId}
          transactionId={transactionId}
          onClose={() => navigate(`/transactions${params.size ? `?${params}` : ''}`)}
        />
      )}
    </>
  )
}
