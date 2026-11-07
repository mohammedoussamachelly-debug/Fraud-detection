import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { getAlert, updateAlertStatus } from '../../api/alerts'
import { getTransaction } from '../../api/transactions'
import type { AlertStatus } from '../../api/types'
import { describeError, ErrorState } from '../../components/data/ErrorState'
import { RiskScoreIndicator } from '../transactions/RiskScoreIndicator'
import { AlertStatusBadge } from '../../components/data/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import { Skeleton } from '../../components/ui/skeleton'
import { formatCurrency, formatDateTime, shortId } from '../../lib/format'
import { CreateCaseDialog } from '../cases/CreateCaseDialog'

const STATUS_OPTIONS: AlertStatus[] = ['open', 'triaged', 'escalated', 'dismissed']

export function AlertDetailPage() {
  const { alertId } = useParams<{ alertId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createCaseOpen, setCreateCaseOpen] = useState(false)

  const alertQuery = useQuery({
    queryKey: ['alert', alertId],
    queryFn: () => getAlert(alertId!),
    enabled: !!alertId,
  })

  const transactionId = alertQuery.data?.transaction_id
  const transactionQuery = useQuery({
    queryKey: ['transaction', transactionId],
    queryFn: () => getTransaction(transactionId!),
    enabled: !!transactionId,
  })
  const statusMutation = useMutation({
    mutationFn: (status: AlertStatus) => updateAlertStatus(alertId!, status),
    onSuccess: (updated) => {
      queryClient.setQueryData(['alert', alertId], updated)
      void queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  if (alertQuery.isLoading) {
    return <Skeleton className="h-40 w-full" />
  }
  if (alertQuery.error || !alertQuery.data) {
    return <ErrorState error={alertQuery.error} onRetry={() => alertQuery.refetch()} />
  }

  const alert = alertQuery.data

  return (
    <div>
      <Link to="/alerts" className="mb-4 inline-block text-xs text-accent hover:underline">
        ← Alert queue
      </Link>
      <PageHeader
        title={<span className="font-mono">Alert {shortId(alert.id)}</span>}
        description={`${alert.alert_type.replace(/_/g, ' ')} · created ${formatDateTime(alert.created_at)}`}
        actions={
          <>
            <Select
              value={alert.status}
              disabled={statusMutation.isPending}
              onValueChange={(value) => statusMutation.mutate(value as AlertStatus)}
            >
              <SelectTrigger aria-label="Change alert status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button variant="primary" size="md" onClick={() => setCreateCaseOpen(true)}>
              Create case
            </Button>
          </>
        }
      />

      {statusMutation.error && (
        <p role="alert" className="mb-3 text-sm">
          {describeError(statusMutation.error)}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Alert</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <Row label="Status">
              <AlertStatusBadge status={alert.status} />
            </Row>
            <Row label="Severity">{alert.severity}</Row>
            <Row label="Type">{alert.alert_type}</Row>
            <Row label="Created">{formatDateTime(alert.created_at)}</Row>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Transaction</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {transactionQuery.error && (
              <ErrorState
                error={transactionQuery.error}
                onRetry={() => transactionQuery.refetch()}
              />
            )}
            {transactionQuery.isLoading && <Skeleton className="h-20 w-full" />}
            {transactionQuery.data && (
              <>
                <Row label="Reference">
                  <button
                    className="font-mono text-xs text-accent hover:underline"
                    onClick={() => navigate(`/transactions/${transactionQuery.data!.id}`)}
                  >
                    {transactionQuery.data.external_ref}
                  </button>
                </Row>
                <Row label="Type">{transactionQuery.data.type}</Row>
                <Row label="Amount (synthetic units)">
                  <span className="tabular-nums">
                    {formatCurrency(transactionQuery.data.amount)}
                  </span>
                </Row>
                <Row label="Step">{transactionQuery.data.step}</Row>
                <Row label="Origin">
                  <Link
                    className="font-mono text-xs text-accent"
                    to={`/accounts/${transactionQuery.data.origin_account_id}`}
                  >
                    {shortId(transactionQuery.data.origin_account_id)} →
                  </Link>
                </Row>
                <Row label="Recipient">
                  <Link
                    className="font-mono text-xs text-accent"
                    to={`/accounts/${transactionQuery.data.dest_account_id}`}
                  >
                    {shortId(transactionQuery.data.dest_account_id)} →
                  </Link>
                </Row>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Risk score</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {transactionId && <RiskScoreIndicator transactionId={transactionId} />}
        </CardContent>
      </Card>

      {transactionId && (
        <CreateCaseDialog
          open={createCaseOpen}
          onOpenChange={setCreateCaseOpen}
          alertIds={[alert.id]}
          onCreated={(caseId) => navigate(`/cases/${caseId}`)}
        />
      )}
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-foreground-muted">{label}</span>
      <span className="text-foreground">{children}</span>
    </div>
  )
}
