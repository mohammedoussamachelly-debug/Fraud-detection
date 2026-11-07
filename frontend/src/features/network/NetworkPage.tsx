import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getAccountFundFlow, getAccountMetrics, getAccountNeighborhood } from '../../api/graph'
import { DetailRow } from '../../components/data/DetailRow'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { FilterBar } from '../../components/data/FilterBar'
import { GraphDisclaimer } from '../../components/data/SyntheticDataBanner'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Skeleton } from '../../components/ui/skeleton'
import { formatCurrency, shortId } from '../../lib/format'
import { UUID_PATTERN } from '../../lib/validation'
import { NetworkCanvas } from './NetworkCanvas'

export function NetworkPage() {
  const [params] = useSearchParams()
  return <NetworkWorkspace key={params.toString()} />
}

function NetworkWorkspace() {
  const [params, setParams] = useSearchParams()
  const account = params.get('account') ?? ''
  const hops = Math.min(4, Math.max(1, Number(params.get('hops')) || 2))
  const cutoffValue = params.get('as_of_step')
  const cutoff = cutoffValue !== null && /^\d+$/.test(cutoffValue) ? Number(cutoffValue) : undefined
  const [input, setInput] = useState(account)
  const [hopInput, setHopInput] = useState(String(hops))
  const [stepInput, setStepInput] = useState(cutoff?.toString() ?? '')
  const [selected, setSelected] = useState(account)
  const graph = useQuery({
    queryKey: ['graph', account, hops, cutoff],
    queryFn: () => getAccountNeighborhood(account, { hops, as_of_step: cutoff }),
    enabled: !!account,
  })
  const metrics = useQuery({
    queryKey: ['graph-metrics', selected, cutoff],
    queryFn: () => getAccountMetrics(selected, { as_of_step: cutoff }),
    enabled: !!account && !!selected,
  })
  const flow = useQuery({
    queryKey: ['fund-flow', selected, cutoff],
    queryFn: () =>
      getAccountFundFlow(selected, { as_of_step: cutoff, max_hops: 3, max_branches: 5 }),
    enabled: !!account && !!selected,
  })
  return (
    <>
      <PageHeader
        title="Network Explorer"
        description="Follow account relationships and bounded fund-flow paths."
      />
      <FilterBar>
        <form
          className="flex w-full flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            const next = new URLSearchParams({ account: input.trim(), hops: hopInput })
            if (stepInput !== '') next.set('as_of_step', stepInput)
            setParams(next)
            setSelected(input.trim())
          }}
        >
          <label className="grid w-full min-w-0 gap-1 text-xs sm:w-auto sm:min-w-64 sm:flex-1 text-foreground-muted">
            Account UUID
            <Input
              required
              pattern={UUID_PATTERN}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Open an account or paste its UUID"
              className="w-full min-w-0"
            />
          </label>
          <label className="grid gap-1 text-xs text-foreground-muted">
            Neighborhood hops
            <Input
              className="w-32"
              type="number"
              required
              min={1}
              max={4}
              value={hopInput}
              onChange={(e) => setHopInput(e.target.value)}
            />
          </label>
          <label className="grid gap-1 text-xs text-foreground-muted">
            As of step (inclusive)
            <Input
              className="w-36"
              type="number"
              min={0}
              step={1}
              value={stepInput}
              onChange={(e) => setStepInput(e.target.value)}
              placeholder="All history"
            />
          </label>
          <Button variant="primary" type="submit">
            Explore
          </Button>
        </form>
      </FilterBar>
      {!account ? (
        <EmptyState
          title="Start with an account"
          description="Find an account in the directory or follow a transaction's origin or recipient."
          action={
            <Link to="/accounts" className="text-sm text-accent">
              Browse accounts →
            </Link>
          }
        />
      ) : graph.isPending ? (
        <Skeleton className="h-96 w-full" />
      ) : graph.error ? (
        <ErrorState error={graph.error} onRetry={() => graph.refetch()} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-foreground-muted">
            <span>
              {graph.data.nodes.length} accounts · {graph.data.edges.length} transfers ·{' '}
              {graph.data.cycles.length} detected cycles
            </span>
            <span>{cutoff === undefined ? 'All available history' : `Through step ${cutoff}`}</span>
            {graph.data.truncated && (
              <strong className="text-status-attention">
                Truncated network — query bounds reached
              </strong>
            )}
          </div>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <Card className="min-w-0">
              <NetworkCanvas graph={graph.data} selectedAccount={selected} onSelect={setSelected} />
              <div className="border-t border-border p-3">
                <h2 className="mb-2 text-xs font-semibold">Select account</h2>
                <div className="flex max-h-36 flex-wrap gap-2 overflow-y-auto">
                  {graph.data.nodes.map((node) => (
                    <Button
                      key={node.id}
                      size="sm"
                      variant={selected === node.id ? 'primary' : 'outline'}
                      onClick={() => setSelected(node.id)}
                      aria-pressed={selected === node.id}
                    >
                      {node.external_ref}
                    </Button>
                  ))}
                </div>
              </div>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Selected account</CardTitle>
                <Link
                  className="break-all font-mono text-xs text-accent"
                  to={`/accounts/${selected}`}
                >
                  {graph.data.nodes.find((n) => n.id === selected)?.external_ref ??
                    shortId(selected)}{' '}
                  →
                </Link>
              </CardHeader>
              <CardContent>
                {metrics.isPending ? (
                  <Skeleton className="h-40 w-full" />
                ) : metrics.error ? (
                  <ErrorState error={metrics.error} onRetry={() => metrics.refetch()} />
                ) : (
                  <>
                    <dl>
                      <DetailRow label="Incoming / outgoing">
                        {metrics.data.incoming_transaction_count} /{' '}
                        {metrics.data.outgoing_transaction_count}
                      </DetailRow>
                      <DetailRow label="Unique senders / recipients">
                        {metrics.data.unique_senders} / {metrics.data.unique_recipients}
                      </DetailRow>
                      <DetailRow label={`Velocity · ${metrics.data.velocity_window_steps} steps`}>
                        {metrics.data.velocity_count} transfers
                      </DetailRow>
                      <DetailRow label="Fan-in / fan-out signal">
                        {metrics.data.fan_in_pattern ? 'Yes' : 'No'} /{' '}
                        {metrics.data.fan_out_pattern ? 'Yes' : 'No'}
                      </DetailRow>
                    </dl>
                    {metrics.data.truncated && (
                      <p className="mt-2 text-xs text-status-attention">
                        Metrics are truncated by query bounds.
                      </p>
                    )}
                    <GraphDisclaimer text={metrics.data.disclaimer} />
                  </>
                )}
              </CardContent>
            </Card>
          </div>
          <div className="my-3">
            <GraphDisclaimer text={graph.data.disclaimer} />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Fund-flow paths from selected account</CardTitle>
              <p className="text-xs text-foreground-muted">
                Up to 3 hops and 5 branches · same temporal cutoff as the network
              </p>
            </CardHeader>
            <CardContent>
              {flow.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : flow.error ? (
                <ErrorState error={flow.error} onRetry={() => flow.refetch()} />
              ) : (
                <>
                  {flow.data.truncated && (
                    <p className="mb-3 text-sm text-status-attention">
                      Truncated paths — additional transfers may exist.
                    </p>
                  )}
                  {flow.data.paths.length === 0 ? (
                    <EmptyState title="No outgoing paths in these bounds" />
                  ) : (
                    <ol className="space-y-3">
                      {flow.data.paths.map((path, index) => (
                        <li key={index} className="rounded-control border border-border p-3">
                          <p className="mb-2 text-xs font-semibold">Path {index + 1}</p>
                          <ol className="space-y-2">
                            {path.steps.map((step, i) => (
                              <li
                                key={`${step.transaction_id}-${i}`}
                                className="flex flex-wrap items-center justify-between gap-2 text-xs"
                              >
                                <span className="font-mono">
                                  {shortId(step.from_account_id)} → {shortId(step.to_account_id)}
                                </span>
                                <Link
                                  to={`/transactions/${step.transaction_id}`}
                                  className="text-accent hover:underline"
                                >
                                  {step.transaction_external_ref}
                                </Link>
                                <span className="tabular-nums">
                                  {formatCurrency(step.amount)} units · step {step.step}
                                </span>
                              </li>
                            ))}
                          </ol>
                        </li>
                      ))}
                    </ol>
                  )}
                  <div className="mt-3">
                    <GraphDisclaimer text={flow.data.disclaimer} />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </>
  )
}
