import { readable } from '../workspace/presentation'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getActivities, getActivity } from '../../api/workspace'
import { ErrorState } from '../../components/data/ErrorState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { formatCurrency, formatDateTime } from '../../lib/format'
import { ActivityDetail, Connections, InvestigateButton, RiskLabel } from '../workspace/Activity'
export function TransactionsPage() {
  const { transactionId } = useParams()
  return transactionId ? (
    <TransactionContext key={transactionId} id={transactionId} />
  ) : (
    <TransactionList />
  )
}
function TransactionContext({ id }: { id: string }) {
  const [params] = useSearchParams()
  const query = useQuery({ queryKey: ['workspace-activity', id], queryFn: () => getActivity(id) })
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  if (!query.data) return <Skeleton className="h-64 w-full" />
  const item = query.data
  return (
    <>
      <Link className="mb-4 inline-block text-xs text-accent" to="/transactions">
        ← Transactions
      </Link>
      <PageHeader
        title={readable(item.transaction.external_ref)}
        description="Review the payment, its history, and the accounts involved."
        actions={<InvestigateButton alertId={item.alert_id} caseId={item.case_id} />}
      />
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <ActivityDetail item={item} />
        <Connections
          accountId={params.get('connected') || item.transaction.origin_account_id}
          step={item.transaction.step}
        />
      </div>
    </>
  )
}
function TransactionList() {
  const [params] = useSearchParams()
  const [search, setSearch] = useState(''),
    [type, setType] = useState(''),
    [offset, setOffset] = useState(0)
  const account = params.get('account') ?? ''
  const query = useQuery({
    queryKey: ['workspace-transactions', search, type, account, offset],
    queryFn: () => getActivities({ search, type, account_id: account, offset, limit: 25 }),
  })
  return (
    <>
      <PageHeader
        title="Transactions"
        description="Find a payment and understand its context. Amounts are in synthetic units."
      />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs">
          Search payments
          <Input
            placeholder="Account or payment reference"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setOffset(0)
            }}
          />
        </label>
        <label className="grid gap-1 text-xs">
          Payment type
          <select
            className="rounded-control border border-border bg-surface px-3 py-2"
            value={type}
            onChange={(e) => {
              setType(e.target.value)
              setOffset(0)
            }}
          >
            {['', 'PAYMENT', 'TRANSFER', 'DEBIT', 'CASH_IN', 'CASH_OUT'].map((t) => (
              <option key={t} value={t}>
                {readable(t) || 'All types'}
              </option>
            ))}
          </select>
        </label>
        {account && (
          <Link className="text-xs text-accent" to="/transactions">
            Clear account filter
          </Link>
        )}
      </div>
      {query.error ? (
        <ErrorState error={query.error} onRetry={() => query.refetch()} />
      ) : !query.data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <div className="overflow-x-auto rounded-control border border-border bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Payments and model assessments</caption>
              <thead className="border-b border-border text-xs text-foreground-muted">
                <tr>
                  {['Payment', 'Amount', 'Occurred', 'Model score', 'Investigation'].map((h) => (
                    <th key={h} className="px-4 py-3 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {query.data.items.map((item) => (
                  <tr key={item.transaction.id}>
                    <td className="min-w-64 px-4 py-3">
                      <Link
                        className="font-medium text-accent"
                        to={`/transactions/${item.transaction.id}`}
                      >
                        {item.sender} → {item.recipient}
                      </Link>
                      <p className="mt-1 text-xs text-foreground-muted">
                        {readable(item.transaction.external_ref)} ·{' '}
                        {readable(item.transaction.type)}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 tabular-nums">
                      {formatCurrency(item.transaction.amount)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs">
                      {formatDateTime(item.transaction.occurred_at)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs">
                      <RiskLabel activity={item} />
                    </td>
                    <td className="min-w-40 px-4 py-3">
                      <InvestigateButton alertId={item.alert_id} caseId={item.case_id} />
                      {!item.alert_id && (
                        <span className="text-xs text-foreground-muted">No alert</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!query.data.items.length && (
              <p className="p-6 text-sm">No payments match these filters.</p>
            )}
          </div>
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
