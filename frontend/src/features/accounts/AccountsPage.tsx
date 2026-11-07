import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getAccount, listAccounts } from '../../api/accounts'
import type { Account } from '../../api/types'
import { DataTable, type DataColumn } from '../../components/data/DataTable'
import { DetailRow } from '../../components/data/DetailRow'
import { ErrorState } from '../../components/data/ErrorState'
import { FilterBar } from '../../components/data/FilterBar'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime } from '../../lib/format'

const columns: DataColumn<Account>[] = [
  {
    header: 'Reference',
    accessorKey: 'external_ref',
    cell: ({ getValue }) => <span className="font-mono text-xs">{getValue<string>()}</span>,
  },
  { header: 'Type', accessorKey: 'account_type' },
  {
    header: 'First seen',
    accessorKey: 'first_seen_at',
    cell: ({ getValue }) => formatDateTime(getValue<string>()),
  },
]
export function AccountsPage() {
  const navigate = useNavigate()
  const [input, setInput] = useState('')
  const [reference, setReference] = useState('')
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ['accounts', { reference, offset }],
    queryFn: () => listAccounts({ external_ref: reference || undefined, limit: 25, offset }),
    placeholderData: keepPreviousData,
  })
  return (
    <>
      <PageHeader
        title="Accounts"
        description="Find a synthetic account and follow its transaction network."
      />
      <FilterBar>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            setReference(input.trim())
            setOffset(0)
          }}
        >
          <label className="grid gap-1 text-xs text-foreground-muted">
            Exact account reference
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="All accounts"
            />
          </label>
          <Button type="submit">Search</Button>
        </form>
      </FilterBar>
      <DataTable
        columns={columns}
        data={query.data?.items ?? []}
        isLoading={query.isPending || query.isPlaceholderData}
        error={query.error}
        onRetry={() => query.refetch()}
        emptyTitle="No accounts found"
        emptyDescription="Account reference search requires an exact match."
        onRowClick={(account) => navigate(`/accounts/${account.id}`)}
      />
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
export function AccountDetailPage() {
  const { accountId = '' } = useParams()
  const query = useQuery({ queryKey: ['account', accountId], queryFn: () => getAccount(accountId) })
  if (query.isPending) return <Skeleton className="h-48 w-full" />
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  return (
    <>
      <Link className="mb-4 inline-block text-xs text-accent" to="/accounts">
        ← Accounts
      </Link>
      <PageHeader
        title={query.data.external_ref}
        description="Synthetic account profile"
        actions={
          <Button asChild variant="primary">
            <Link to={`/network?account=${accountId}`}>Explore network</Link>
          </Button>
        }
      />
      <Card className="max-w-2xl p-4">
        <dl>
          <DetailRow label="Account ID">{query.data.id}</DetailRow>
          <DetailRow label="Type">{query.data.account_type}</DetailRow>
          <DetailRow label="First seen">{formatDateTime(query.data.first_seen_at)}</DetailRow>
          <DetailRow label="Registered">{formatDateTime(query.data.created_at)}</DetailRow>
        </dl>
        <Link
          className="mt-4 inline-block text-sm text-accent hover:underline"
          to={`/transactions?account_id=${accountId}`}
        >
          View account transactions →
        </Link>
      </Card>
    </>
  )
}
