import { useQuery } from '@tanstack/react-query'
import { ApiError } from '../../api/client'
import { getTransactionRiskScore } from '../../api/transactions'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { RiskBadge } from '../../components/data/SeverityBadge'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime } from '../../lib/format'

export function RiskScoreIndicator({ transactionId }: { transactionId: string }) {
  const query = useQuery({
    queryKey: ['transaction-risk-score', transactionId],
    queryFn: () => getTransactionRiskScore(transactionId),
    retry: false,
  })
  if (query.isPending) return <Skeleton className="h-24 w-full" />
  if (query.error)
    return query.error instanceof ApiError && query.error.status === 404 ? (
      <EmptyState
        title="Not scored yet"
        description="No persisted model score is available for this transaction."
      />
    ) : (
      <ErrorState error={query.error} onRetry={() => query.refetch()} />
    )
  const score = query.data
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <RiskBadge level={score.risk_level} score={score.risk_score} />
        <span className="text-xs text-foreground-muted">
          Threshold {score.threshold_used.toFixed(3)}
        </span>
      </div>
      <dl className="space-y-1 text-xs text-foreground-muted">
        <div>
          Model <span className="font-mono text-foreground">{score.model_version}</span>
        </div>
        <div>Scored {formatDateTime(score.scored_at)}</div>
        <div className="break-all">
          Score ID <span className="font-mono">{score.id}</span>
        </div>
      </dl>
      <div className="border-t border-border pt-3">
        <h3 className="text-sm font-semibold">Why this score?</h3>
        <p className="mt-1 text-xs text-foreground-muted">
          SHAP contributions explain the model output; they do not establish fraud.
        </p>
        {!score.explanation ? (
          <p className="mt-3 text-sm text-foreground-muted">
            No SHAP explanation was stored with this score.
          </p>
        ) : (
          <>
            <p className="my-3 text-xs text-foreground-muted">
              Base value: {score.explanation.base_value.toFixed(4)} · contributions in model output
              units
            </p>
            <ul className="divide-y divide-border">
              {score.explanation.contributions.map((item, index) => (
                <li key={`${item.feature}-${index}`} className="py-2 text-sm">
                  <div className="flex flex-wrap justify-between gap-2">
                    <span className="break-all font-mono text-xs">{item.feature}</span>
                    <span
                      className={`font-mono text-xs tabular-nums ${item.direction === 'increases_risk' ? 'text-risk-high' : 'text-risk-low'}`}
                    >
                      {item.shap_contribution > 0 ? '+' : ''}
                      {item.shap_contribution.toFixed(4)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-foreground-muted">
                    Value {String(item.value)} · {item.direction.replace(/_/g, ' ')}
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
