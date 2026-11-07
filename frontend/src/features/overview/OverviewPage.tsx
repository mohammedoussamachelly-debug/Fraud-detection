import { OperationalActivity } from './OperationalActivity'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { listAlerts } from '../../api/alerts'
import { listCases } from '../../api/cases'
import { listTransactions } from '../../api/transactions'
import { PageHeader } from '../../components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { ErrorState } from '../../components/data/ErrorState'
import { EmptyState } from '../../components/data/EmptyState'
import { Skeleton } from '../../components/ui/skeleton'
import { SeverityBadge } from '../../components/data/SeverityBadge'
import { CaseStatusBadge } from '../../components/data/StatusBadge'
import { formatDateTime, formatNumber, shortId } from '../../lib/format'

const severities = ['critical', 'high', 'medium', 'low']

export function OverviewPage() {
  const alerts = useQueries({
    queries: severities.map((severity) => ({
      queryKey: ['alerts', 'overview', severity],
      queryFn: () => listAlerts({ status: 'open', severity, limit: 8 }),
    })),
  })
  const cases = useQuery({
    queryKey: ['cases', 'overview'],
    queryFn: () => listCases({ status: 'pending_review', limit: 5 }),
  })
  const transactions = useQuery({
    queryKey: ['transactions', 'count'],
    queryFn: () => listTransactions({ limit: 1 }),
  })
  const alertsError = alerts.find((q) => q.error)?.error
  const loadingAlerts = alerts.some((q) => q.isPending)
  const distribution = alerts.map((q, i) => ({
    severity: severities[i],
    count: q.data?.total ?? 0,
  }))
  const queue = alerts.flatMap((q) => q.data?.items ?? []).slice(0, 8)
  return (
    <>
      <PageHeader
        title="Overview"
        description="Prioritize the queue. Follow the evidence."
        actions={
          <Link
            to="/alerts?status=open&severity=critical"
            className="text-sm font-medium text-accent hover:underline"
          >
            Review critical alerts →
          </Link>
        }
      />
      <div className="mb-5 grid gap-px overflow-hidden rounded-surface border border-border bg-border sm:grid-cols-3">
        <div className="bg-surface p-4">
          <p className="text-xs text-foreground-muted">Open alerts</p>
          {alertsError ? (
            <ErrorState
              error={alertsError}
              onRetry={() => alerts.forEach((q) => void q.refetch())}
            />
          ) : loadingAlerts ? (
            <Skeleton className="mt-2 h-8 w-20" />
          ) : (
            <>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {formatNumber(distribution.reduce((sum, d) => sum + d.count, 0))}
              </p>
              <p className="mt-1 text-xs text-foreground-muted">
                {formatNumber(distribution[0].count)} critical ·{' '}
                {formatNumber(distribution[1].count)} high priority
              </p>
            </>
          )}
        </div>
        <div className="bg-surface p-4">
          <p className="text-xs text-foreground-muted">Cases awaiting human review</p>
          {cases.error ? (
            <ErrorState error={cases.error} onRetry={() => cases.refetch()} />
          ) : cases.isPending ? (
            <Skeleton className="mt-2 h-8 w-20" />
          ) : (
            <>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {formatNumber(cases.data.total)}
              </p>
              <Link
                to="/cases?status=pending_review"
                className="mt-1 text-xs text-accent hover:underline"
              >
                Open review queue →
              </Link>
            </>
          )}
        </div>
        <div className="bg-surface p-4">
          <p className="text-xs text-foreground-muted">Transactions in monitoring dataset</p>
          {transactions.error ? (
            <ErrorState error={transactions.error} onRetry={() => transactions.refetch()} />
          ) : transactions.isPending ? (
            <Skeleton className="mt-2 h-8 w-20" />
          ) : (
            <>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {formatNumber(transactions.data.total)}
              </p>
              <p className="mt-1 text-xs text-foreground-muted">
                All ingested synthetic transactions
              </p>
            </>
          )}
        </div>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Priority queue</CardTitle>
            <p className="text-xs text-foreground-muted">
              Open alerts · severity first, then newest within each severity
            </p>
          </CardHeader>
          <CardContent>
            {alertsError ? (
              <ErrorState
                error={alertsError}
                onRetry={() => alerts.forEach((q) => void q.refetch())}
              />
            ) : loadingAlerts ? (
              <Skeleton className="h-52 w-full" />
            ) : queue.length === 0 ? (
              <EmptyState
                title="No open alerts"
                description="New alerts will appear when a scoring threshold is crossed."
              />
            ) : (
              <ul className="divide-y divide-border">
                {queue.map((alert) => (
                  <li key={alert.id}>
                    <Link
                      className="flex flex-wrap items-center justify-between gap-2 py-3 hover:text-accent"
                      to={`/alerts/${alert.id}`}
                    >
                      <div>
                        <p className="text-sm font-medium capitalize">
                          {alert.alert_type.replace(/_/g, ' ')}
                        </p>
                        <p className="mt-1 font-mono text-xs text-foreground-muted">
                          {shortId(alert.id)} · {formatDateTime(alert.created_at)}
                        </p>
                      </div>
                      <SeverityBadge severity={alert.severity} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <Link
              className="mt-3 inline-block text-xs text-accent hover:underline"
              to="/alerts?status=open"
            >
              View all open alerts →
            </Link>
          </CardContent>
        </Card>
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Open alerts by severity</CardTitle>
              <p className="text-xs text-foreground-muted">
                Alert severity, not a distribution of all transaction risk scores.
              </p>
            </CardHeader>
            <CardContent>
              {alertsError ? (
                <p className="text-sm text-foreground-muted">
                  Distribution unavailable until the alert counts load.
                </p>
              ) : loadingAlerts ? (
                <Skeleton className="h-40 w-full" />
              ) : (
                <>
                  <div className="h-40" aria-hidden="true">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={distribution}
                        layout="vertical"
                        margin={{ left: 8, right: 20 }}
                      >
                        <CartesianGrid horizontal={false} stroke="var(--color-border)" />
                        <XAxis
                          type="number"
                          allowDecimals={false}
                          tick={{ fill: 'var(--color-foreground-muted)', fontSize: 11 }}
                        />
                        <YAxis
                          type="category"
                          dataKey="severity"
                          width={55}
                          tick={{ fill: 'var(--color-foreground-muted)', fontSize: 12 }}
                        />
                        <Bar dataKey="count" fill="var(--color-accent)" barSize={16} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-xs text-foreground-muted">
                    {distribution.map((d) => `${d.severity}: ${d.count}`).join(' · ')}
                  </p>
                </>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Cases requiring attention</CardTitle>
            </CardHeader>
            <CardContent>
              {cases.error ? (
                <ErrorState error={cases.error} onRetry={() => cases.refetch()} />
              ) : cases.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : cases.data.items.length === 0 ? (
                <EmptyState title="No cases awaiting review" />
              ) : (
                <ul className="divide-y divide-border">
                  {cases.data.items.map((item) => (
                    <li key={item.id}>
                      <Link
                        className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm hover:text-accent"
                        to={`/cases/${item.id}`}
                      >
                        <span className="font-mono">{shortId(item.id)}</span>
                        <CaseStatusBadge status={item.status} />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <OperationalActivity />
    </>
  )
}
