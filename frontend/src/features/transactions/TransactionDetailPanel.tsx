import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { getTransaction } from '../../api/transactions'
import { DetailRow } from '../../components/data/DetailRow'
import { ErrorState } from '../../components/data/ErrorState'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../components/ui/dialog'
import { Skeleton } from '../../components/ui/skeleton'
import { formatCurrency, formatDateTime, shortId } from '../../lib/format'
import { RiskScoreIndicator } from './RiskScoreIndicator'

export function TransactionDetailPanel({
  transactionId,
  onClose,
}: {
  transactionId: string
  onClose: () => void
}) {
  const query = useQuery({
    queryKey: ['transaction', transactionId],
    queryFn: () => getTransaction(transactionId),
  })
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <DialogContent className="inset-y-0 left-auto right-0 h-dvh max-h-dvh w-full max-w-xl translate-x-0 translate-y-0 rounded-none p-5 sm:p-6">
        <DialogTitle>Transaction details</DialogTitle>
        <DialogDescription className="break-all font-mono text-xs">
          {transactionId}
        </DialogDescription>
        {query.isPending ? (
          <Skeleton className="mt-5 h-48 w-full" />
        ) : query.error ? (
          <ErrorState error={query.error} onRetry={() => query.refetch()} />
        ) : (
          <div className="mt-5 space-y-5">
            <section>
              <h2 className="mb-2 text-sm font-semibold">Transfer context</h2>
              <dl>
                <DetailRow label="Reference">{query.data.external_ref}</DetailRow>
                <DetailRow label="Amount (synthetic units)">
                  {formatCurrency(query.data.amount)}
                </DetailRow>
                <DetailRow label="Type">{query.data.type}</DetailRow>
                <DetailRow label="Occurred">{formatDateTime(query.data.occurred_at)}</DetailRow>
                <DetailRow label="Simulation step">{query.data.step}</DetailRow>
                <DetailRow label="Origin account">
                  <Link
                    className="font-mono text-accent hover:underline"
                    to={`/accounts/${query.data.origin_account_id}`}
                  >
                    {shortId(query.data.origin_account_id)} →
                  </Link>
                </DetailRow>
                <DetailRow label="Recipient account">
                  <Link
                    className="font-mono text-accent hover:underline"
                    to={`/accounts/${query.data.dest_account_id}`}
                  >
                    {shortId(query.data.dest_account_id)} →
                  </Link>
                </DetailRow>
                <DetailRow label="Origin balance, before → after">
                  {formatCurrency(query.data.origin_balance_before)} →{' '}
                  {formatCurrency(query.data.origin_balance_after)}
                </DetailRow>
                <DetailRow label="Recipient balance, before → after">
                  {formatCurrency(query.data.dest_balance_before)} →{' '}
                  {formatCurrency(query.data.dest_balance_after)}
                </DetailRow>
              </dl>
            </section>
            <section className="border-t border-border pt-4">
              <h2 className="mb-3 text-sm font-semibold">Persisted risk assessment</h2>
              <RiskScoreIndicator transactionId={transactionId} />
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
