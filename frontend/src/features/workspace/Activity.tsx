import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getAccountNeighborhood, getAccountMetrics, getAccountFundFlow } from '../../api/graph'
import { getHistory, investigate, type Activity as ActivityRecord } from '../../api/workspace'
import { Button } from '../../components/ui/button'
import { ErrorState } from '../../components/data/ErrorState'
import { formatCurrency, formatDateTime } from '../../lib/format'
import { NetworkCanvas } from '../network/NetworkCanvas'

import { panel, readable, percentage } from './presentation'

export function InvestigateButton({
  alertId,
  caseId,
}: {
  alertId: string | null
  caseId?: string | null
}) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => investigate(alertId!),
    onSuccess: (result) => {
      for (const key of [
        'workspace-dashboard',
        'workspace-cases',
        'workspace-alerts',
        'workspace-activity',
        'workspace-transactions',
      ]) {
        void client.invalidateQueries({ queryKey: [key] })
      }
      navigate(`/cases/${result.case_id}`)
    },
  })
  if (caseId)
    return (
      <Link className="text-sm font-medium text-accent hover:underline" to={`/cases/${caseId}`}>
        Open investigation →
      </Link>
    )
  if (!alertId) return null
  return (
    <div>
      <Button
        size="sm"
        variant="primary"
        disabled={mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? 'Opening…' : 'Investigate'}
      </Button>
      {mutation.error && <ErrorState error={mutation.error} />}
    </div>
  )
}
export function RiskLabel({ activity }: { activity: ActivityRecord }) {
  return (
    <span
      className={
        activity.risk?.risk_level === 'high' ? 'text-status-negative' : 'text-foreground-muted'
      }
    >
      {activity.risk
        ? `${percentage(activity.risk.risk_score)} · ${activity.risk.risk_level}`
        : 'Not scored'}
    </span>
  )
}
const factors: Record<string, string> = {
  amount: 'Transfer amount',
  log_amount: 'Transfer amount (scaled)',
  hour_of_day: 'Time of day',
  sender_prev_balance: 'Sender balance before transfer',
  recipient_prev_balance: 'Recipient balance before transfer',
  num_prev_txns_by_sender: 'Earlier payments by this sender',
  historical_avg_amount: 'Usual payment amount',
  num_unique_prev_recipients: 'Previous recipients',
  recent_txn_frequency: 'Payments in the previous 24 hours',
  sender_is_new: 'Whether this sender has prior history',
  transaction_type: 'Payment type',
}
export function ActivityDetail({ item }: { item: ActivityRecord }) {
  const tx = item.transaction
  const history = useQuery({
    queryKey: ['activity-history', tx.id],
    queryFn: () => getHistory(tx.id),
  })
  return (
    <div className="min-w-0 space-y-4">
      <section className={panel}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">
              {formatCurrency(tx.amount)}{' '}
              <span className="text-xs font-normal text-foreground-muted">synthetic units</span>
            </h2>
            <p className="mt-1 text-sm">
              <Link className="text-accent" to={`/accounts/${tx.origin_account_id}`}>
                {item.sender}
              </Link>{' '}
              →{' '}
              <Link className="text-accent" to={`/accounts/${tx.dest_account_id}`}>
                {item.recipient}
              </Link>
            </p>
            <p className="mt-1 text-xs text-foreground-muted">
              {readable(tx.type)} · {formatDateTime(tx.occurred_at)}
            </p>
          </div>
          <RiskLabel activity={item} />
        </div>
        <details className="mt-3 text-xs text-foreground-muted">
          <summary className="cursor-pointer">Technical details</summary>
          <p className="mt-2 break-all">
            Transaction {tx.id} · {tx.external_ref} · simulation hour {tx.step}
          </p>
          <p>
            Sender balance: {formatCurrency(tx.origin_balance_before)} →{' '}
            {formatCurrency(tx.origin_balance_after)}
          </p>
          <p>
            Recipient balance: {formatCurrency(tx.dest_balance_before)} →{' '}
            {formatCurrency(tx.dest_balance_after)}
          </p>
        </details>
      </section>
      <section className={panel}>
        <h2 className="mb-2 text-sm font-semibold">What influenced the model score?</h2>
        {item.risk ? (
          <>
            <p className="mb-3 text-sm">
              Score <strong>{percentage(item.risk.risk_score)}</strong> · review threshold{' '}
              {percentage(item.risk.threshold_used)}.{' '}
              {item.risk.risk_score >= item.risk.threshold_used
                ? 'This score crossed the model threshold.'
                : 'This score did not cross the model threshold.'}
            </p>
            <ul className="divide-y divide-border">
              {item.risk.explanation?.contributions.slice(0, 5).map((factor) => (
                <li key={factor.feature} className="flex justify-between gap-4 py-2 text-sm">
                  <span>{factors[factor.feature] ?? readable(factor.feature)}</span>
                  <span className="shrink-0 text-xs text-foreground-muted">
                    {factor.shap_contribution >= 0 ? '+' : ''}
                    {(factor.shap_contribution * 100).toFixed(2)} score points
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-foreground-muted">
              Factors explain the model output, not whether a crime occurred. The PaySim model is
              not calibrated to this demonstration dataset.
            </p>
            <details className="mt-3 text-xs">
              <summary>Technical details</summary>
              <p className="break-all">
                {item.risk.model_version} · SHAP probability contributions
              </p>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all">
                {JSON.stringify(item.risk.explanation, null, 2)}
              </pre>
            </details>
          </>
        ) : (
          <p className="text-sm text-foreground-muted">
            No persisted model assessment is available.
          </p>
        )}
      </section>
      <section className={panel}>
        <h2 className="mb-2 text-sm font-semibold">Sender history before this payment</h2>
        {history.error ? (
          <ErrorState error={history.error} />
        ) : !history.data ? (
          <p role="status">Loading history…</p>
        ) : (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <p>
              <strong>{history.data.num_prev_txns_by_sender ?? 0}</strong> earlier payments
            </p>
            <p>
              <strong>{formatCurrency(String(history.data.historical_avg_amount ?? 0))}</strong>{' '}
              average amount
            </p>
            <p>
              <strong>{history.data.num_unique_prev_recipients ?? 0}</strong> previous recipients
            </p>
            <p>
              <strong>{history.data.recent_txn_frequency ?? 0}</strong> payments in the previous day
            </p>
          </div>
        )}
        <Link
          className="mt-3 inline-block text-xs text-accent"
          to={`/transactions?account=${tx.origin_account_id}`}
        >
          Browse this account’s payments →
        </Link>
      </section>
    </div>
  )
}
export function Connections({ accountId, step }: { accountId: string; step?: number }) {
  const [selected, setSelected] = useState(accountId)
  const graph = useQuery({
    queryKey: ['workspace-graph', accountId, step],
    queryFn: () =>
      getAccountNeighborhood(accountId, {
        hops: 2,
        as_of_step: step === undefined ? undefined : step + 1,
      }),
  })
  const metrics = useQuery({
    queryKey: ['workspace-metrics', selected, step],
    queryFn: () =>
      getAccountMetrics(selected, { as_of_step: step === undefined ? undefined : step + 1 }),
  })
  const flow = useQuery({
    queryKey: ['workspace-flow', selected, step],
    queryFn: () =>
      getAccountFundFlow(selected, {
        as_of_step: step === undefined ? undefined : step + 1,
        max_hops: 3,
        max_branches: 5,
      }),
  })
  return (
    <section className={panel}>
      <h2 className="text-sm font-semibold">Connected accounts</h2>
      <p className="my-2 text-xs text-foreground-muted">
        Recorded transfers through this event’s simulation hour. Select an account to inspect its
        connections.
      </p>
      {graph.error ? (
        <ErrorState error={graph.error} />
      ) : !graph.data ? (
        <p role="status">Loading connected accounts…</p>
      ) : (
        <>
          <NetworkCanvas graph={graph.data} selectedAccount={selected} onSelect={setSelected} />
          <div className="mt-3 flex flex-wrap gap-2">
            {graph.data.nodes.map((node) => (
              <Button
                size="sm"
                key={node.id}
                aria-pressed={selected === node.id}
                onClick={() => setSelected(node.id)}
              >
                {readable(node.external_ref)}
              </Button>
            ))}
          </div>
          <p className="mt-3 text-xs text-foreground-muted">
            {graph.data.nodes.length} accounts · {graph.data.edges.length} recorded transfers ·{' '}
            {graph.data.cycles.length} return paths
            {graph.data.truncated ? ' · Results limited' : ''}
          </p>
        </>
      )}
      {metrics.error && <ErrorState error={metrics.error} />}
      {metrics.data && (
        <p className="mt-3 text-sm">
          Selected account received {metrics.data.incoming_transaction_count} transfers from{' '}
          {metrics.data.unique_senders} senders and sent {metrics.data.outgoing_transaction_count}{' '}
          transfers to {metrics.data.unique_recipients} recipients.{' '}
          {metrics.data.fan_in_pattern && 'Multiple senders converge here. '}
          {metrics.data.fan_out_pattern && 'Funds are distributed to multiple recipients.'}
        </p>
      )}
      {graph.data && (
        <p className="mt-3 text-xs italic text-foreground-muted">{graph.data.disclaimer}</p>
      )}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer">Follow the money · recorded paths</summary>
        {flow.error ? (
          <ErrorState error={flow.error} />
        ) : flow.data ? (
          <>
            <p className="my-2 text-xs text-foreground-muted">
              {flow.data.disclaimer}
              {flow.data.truncated ? ' Results limited.' : ''}
            </p>
            {flow.data.paths.length ? (
              <ol className="space-y-2">
                {flow.data.paths.map((path, i) => (
                  <li key={i} className="border-t border-border py-2">
                    {path.steps.map((s, j) => (
                      <span key={s.transaction_id + j}>
                        {j > 0 && ' → '}
                        <Link className="text-accent" to={`/transactions/${s.transaction_id}`}>
                          {formatCurrency(s.amount)} at hour {s.step}
                        </Link>
                      </span>
                    ))}
                  </li>
                ))}
              </ol>
            ) : (
              <p>No onward paths found.</p>
            )}
          </>
        ) : (
          <p>Loading paths…</p>
        )}
      </details>
    </section>
  )
}
