import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getDashboard, getScenarios } from '../../api/workspace'
import { ErrorState } from '../../components/data/ErrorState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Skeleton } from '../../components/ui/skeleton'
import { InvestigateButton } from '../workspace/Activity'
import { panel, percentage } from '../workspace/presentation'
import { Queue } from '../workspace/Queue'
export function OverviewPage() {
  const dashboard = useQuery({ queryKey: ['workspace-dashboard'], queryFn: getDashboard })
  const scenarios = useQuery({ queryKey: ['demo-scenarios'], queryFn: getScenarios })
  return (
    <>
      <PageHeader title="Dashboard" description="What needs your attention right now." />
      {dashboard.error ? (
        <ErrorState error={dashboard.error} onRetry={() => dashboard.refetch()} />
      ) : !dashboard.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 xl:grid-cols-4">
            {[
              ['Transactions monitored', dashboard.data.transactions, '/transactions'],
              ['Alerts requiring attention', dashboard.data.attention, '/alerts'],
              ['Investigations in progress', dashboard.data.investigations, '/investigations'],
              ['Awaiting human review', dashboard.data.review, '/investigations'],
            ].map(([label, value, href]) => (
              <Link key={label} to={String(href)} className={panel + ' hover:border-border-strong'}>
                <p className="text-xs text-foreground-muted">{label}</p>
                <p className="mt-2 text-2xl font-semibold tabular-nums">
                  {Number(value).toLocaleString()}
                </p>
              </Link>
            ))}
          </div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Priority queue</h2>
            <Link to="/alerts" className="text-xs text-accent">
              View all alerts →
            </Link>
          </div>
          <Queue items={dashboard.data.queue} />
        </>
      )}
      <details className="mt-6" id="explore-demo">
        <summary className="cursor-pointer text-sm font-semibold">
          Explore demo · five guided scenarios
        </summary>
        <p className="my-3 max-w-3xl text-xs leading-relaxed text-foreground-muted">
          {scenarios.data?.notice ??
            'Explore synthetic examples using real stored transactions and actual model predictions.'}
        </p>
        {scenarios.error && (
          <ErrorState error={scenarios.error} onRetry={() => scenarios.refetch()} />
        )}
        {scenarios.data?.items.length === 0 && (
          <p className="text-sm text-foreground-muted">
            No demonstration batch is loaded. Follow the demo-data setup guide to populate this
            environment.
          </p>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          {scenarios.data?.items.map((scenario, index) => (
            <article key={`${scenario.batch}-${scenario.key}`} className={panel}>
              <p className="mb-1 text-xs text-foreground-muted">
                Synthetic scenario {String.fromCharCode(65 + (index % 5))}
              </p>
              <h3 className="text-sm font-semibold">{scenario.title}</h3>
              <p className="my-2 text-sm leading-relaxed text-foreground-muted">
                {scenario.description}
              </p>
              <p className="mb-3 text-xs">
                Actual model score: {percentage(scenario.model_score)} · {scenario.model_level}
              </p>
              <div className="flex flex-wrap items-center gap-4">
                <Link
                  className="text-sm text-accent hover:underline"
                  to={`/transactions/${scenario.transaction_id}?connected=${scenario.account_id}`}
                >
                  Explore scenario →
                </Link>
                <InvestigateButton alertId={scenario.alert_id ?? null} caseId={scenario.case_id} />
              </div>
            </article>
          ))}
        </div>
      </details>
    </>
  )
}
