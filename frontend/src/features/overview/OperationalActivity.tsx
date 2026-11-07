import { useQueries, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { listAlerts } from '../../api/alerts'
import { listCases } from '../../api/cases'
import { listCaseInvestigations } from '../../api/investigations'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { InvestigationStatusBadge } from '../../components/data/StatusBadge'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime, shortId } from '../../lib/format'

export function OperationalActivity() {
  const today = new Date().toISOString().slice(0, 10)
  const days = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(`${today}T00:00:00Z`)
    day.setUTCDate(day.getUTCDate() - (6 - index))
    return day.toISOString().slice(0, 10)
  })
  const counts = useQueries({
    queries: days.map((day) => ({
      queryKey: ['alerts', 'daily-count', day],
      queryFn: () => listAlerts({ created_from: day, created_to: day, limit: 1 }),
    })),
  })
  const recentCases = useQuery({
    queryKey: ['cases', 'recent-activity'],
    queryFn: () => listCases({ limit: 5 }),
  })
  const investigations = useQueries({
    queries: (recentCases.data?.items ?? []).map((item) => ({
      queryKey: ['case-investigations', item.id, 'recent'],
      queryFn: () => listCaseInvestigations(item.id, { limit: 3 }),
    })),
  })
  const countError = counts.find((q) => q.error)?.error
  const activityError = recentCases.error ?? investigations.find((q) => q.error)?.error
  const chart = counts.map((q, i) => ({ day: days[i].slice(5), count: q.data?.total ?? 0 }))
  const runs = investigations
    .flatMap((q) => q.data?.items ?? [])
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 5)
  return (
    <div className="mt-4 grid items-start gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Alert intake · last 7 UTC days</CardTitle>
          <p className="text-xs text-foreground-muted">
            Daily alert creation counts · today is a partial day
          </p>
        </CardHeader>
        <CardContent>
          {countError ? (
            <ErrorState
              error={countError}
              onRetry={() => counts.forEach((q) => void q.refetch())}
            />
          ) : counts.some((q) => q.isPending) ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <>
              <div className="h-40" aria-hidden="true">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chart} margin={{ left: -25 }}>
                    <CartesianGrid vertical={false} stroke="var(--color-border)" />
                    <XAxis
                      dataKey="day"
                      tick={{ fill: 'var(--color-foreground-muted)', fontSize: 11 }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fill: 'var(--color-foreground-muted)', fontSize: 11 }}
                    />
                    <Bar dataKey="count" fill="var(--color-accent)" barSize={20} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <p className="mt-2 text-xs text-foreground-muted">
                {chart.map((day) => `${day.day}: ${day.count}`).join(' · ')}
              </p>
            </>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent investigation activity</CardTitle>
          <p className="text-xs text-foreground-muted">
            Latest runs across the 5 newest cases · not the global run history
          </p>
        </CardHeader>
        <CardContent>
          {activityError ? (
            <ErrorState
              error={activityError}
              onRetry={() => {
                void recentCases.refetch()
                investigations.forEach((q) => void q.refetch())
              }}
            />
          ) : recentCases.isPending || investigations.some((q) => q.isPending) ? (
            <Skeleton className="h-40 w-full" />
          ) : runs.length === 0 ? (
            <EmptyState
              title="No runs in these cases"
              description="Open a case to launch an investigation."
            />
          ) : (
            <ul className="divide-y divide-border">
              {runs.map((run) => (
                <li key={run.run_id}>
                  <Link
                    className="flex flex-wrap items-center justify-between gap-2 py-3"
                    to={`/investigations/${run.run_id}`}
                  >
                    <div>
                      <p className="font-mono text-xs text-accent">
                        Case {shortId(run.case_id)} · run {shortId(run.run_id)}
                      </p>
                      <p className="mt-1 text-xs text-foreground-muted">
                        {formatDateTime(run.started_at)}
                      </p>
                    </div>
                    <InvestigationStatusBadge status={run.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
