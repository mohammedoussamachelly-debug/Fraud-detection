import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { getCase, getCaseDecision, updateCase, type CaseUpdateRequest } from '../../api/cases'
import { ApiError } from '../../api/client'
import type { CasePriority, CaseStatus } from '../../api/types'
import { useAuth } from '../../context/AuthContext'
import { describeError, ErrorState } from '../../components/data/ErrorState'
import { CaseStatusBadge } from '../../components/data/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import { Skeleton } from '../../components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs'
import { formatDateTime, shortId } from '../../lib/format'
import { InvestigationsTab } from '../investigations/InvestigationsTab'
import { DecisionForm } from './DecisionForm'
import { EvidencePanel } from './EvidencePanel'
import { CaseTimeline } from './CaseTimeline'

const STATUS_TRANSITIONS: Record<CaseStatus, CaseStatus[]> = {
  open: ['investigating'],
  investigating: ['pending_review', 'open'],
  pending_review: ['investigating'],
  resolved: ['closed'],
  closed: [],
}
const PRIORITIES: CasePriority[] = ['low', 'medium', 'high', 'critical']
export function CaseDetailPage() {
  const { caseId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const client = useQueryClient()
  const { user, hasRole } = useAuth()
  const tab = ['evidence', 'investigations', 'decision', 'history'].includes(
    params.get('tab') ?? '',
  )
    ? params.get('tab')!
    : 'evidence'
  const caseQuery = useQuery({ queryKey: ['case', caseId], queryFn: () => getCase(caseId) })
  const decision = useQuery({
    queryKey: ['case-decision', caseId],
    queryFn: () => getCaseDecision(caseId),
    enabled: !!caseQuery.data,
    retry: false,
  })
  const update = useMutation({
    mutationFn: (body: CaseUpdateRequest) => updateCase(caseId, body),
    onSuccess: (updated) => {
      client.setQueryData(['case', caseId], updated)
      void client.invalidateQueries({ queryKey: ['cases'] })
      void client.invalidateQueries({ queryKey: ['audit-log'] })
    },
  })
  if (caseQuery.isPending) return <Skeleton className="h-40 w-full" />
  if (caseQuery.error)
    return <ErrorState error={caseQuery.error} onRetry={() => caseQuery.refetch()} />
  const detail = caseQuery.data
  const noDecision = decision.error instanceof ApiError && decision.error.status === 404
  return (
    <>
      <Link to="/cases" className="mb-4 inline-block text-xs text-accent">
        ← Cases
      </Link>
      <PageHeader
        title={`Case ${shortId(detail.id)}`}
        description={`Created ${formatDateTime(detail.created_at)} · updated ${formatDateTime(detail.updated_at)}`}
        actions={<CaseStatusBadge status={detail.status} />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-surface border border-border bg-surface p-3">
        <span className="text-xs text-foreground-muted">Priority</span>
        <Select
          value={detail.priority}
          disabled={update.isPending}
          onValueChange={(value) => update.mutate({ priority: value as CasePriority })}
        >
          <SelectTrigger aria-label="Case priority">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRIORITIES.map((value) => (
              <SelectItem key={value} value={value}>
                {value}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {STATUS_TRANSITIONS[detail.status].map((next) => (
          <Button
            key={next}
            variant="outline"
            disabled={update.isPending}
            onClick={() => update.mutate({ status: next })}
          >
            Move to {next.replace(/_/g, ' ')}
          </Button>
        ))}
        {!detail.assigned_analyst_id && user ? (
          <Button
            disabled={update.isPending}
            onClick={() => update.mutate({ assigned_analyst_id: user.id })}
          >
            Assign to me
          </Button>
        ) : (
          <span className="text-xs text-foreground-muted">
            Assignee:{' '}
            {detail.assigned_analyst_id === user?.id
              ? 'You'
              : shortId(detail.assigned_analyst_id ?? '')}
          </span>
        )}
        {detail.assigned_analyst_id === user?.id && (
          <Button
            variant="ghost"
            disabled={update.isPending}
            onClick={() => update.mutate({ assigned_analyst_id: null })}
          >
            Unassign
          </Button>
        )}
      </div>
      {update.error && (
        <p role="alert" className="mb-4 text-sm">
          {describeError(update.error)}
        </p>
      )}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="text-xs text-foreground-muted">Linked alerts</span>
        {detail.alerts.map((link) => (
          <Link
            key={link.alert_id}
            to={`/alerts/${link.alert_id}`}
            className="rounded-control border border-border bg-surface px-2 py-1 font-mono text-xs text-accent hover:underline"
          >
            {shortId(link.alert_id)}
          </Link>
        ))}
      </div>
      <Tabs value={tab} onValueChange={(value) => setParams({ tab: value })}>
        <TabsList aria-label="Case sections">
          <TabsTrigger value="evidence">Evidence & notes</TabsTrigger>
          <TabsTrigger value="investigations">Investigations</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="decision">Decision</TabsTrigger>
        </TabsList>
        <TabsContent value="evidence">
          <EvidencePanel key={caseId} caseId={caseId} />
        </TabsContent>
        <TabsContent value="investigations">
          <InvestigationsTab key={caseId} caseId={caseId} />
        </TabsContent>
        <TabsContent value="history">
          <CaseTimeline detail={detail} decision={decision.data} />
        </TabsContent>
        <TabsContent value="decision">
          {decision.isPending ? (
            <Skeleton className="h-24 w-full" />
          ) : decision.error && !noDecision ? (
            <ErrorState error={decision.error} onRetry={() => decision.refetch()} />
          ) : decision.data || hasRole('senior_analyst', 'admin') ? (
            <DecisionForm
              key={caseId}
              caseId={caseId}
              caseStatus={detail.status}
              existingDecision={decision.data ?? null}
              onDecided={() => {
                void client.invalidateQueries({ queryKey: ['case', caseId] })
                void client.invalidateQueries({ queryKey: ['case-decision', caseId] })
                void client.invalidateQueries({ queryKey: ['cases'] })
                void client.invalidateQueries({ queryKey: ['audit-log'] })
              }}
            />
          ) : (
            <p className="text-sm text-foreground-muted">
              No decision recorded. Only a senior analyst or admin can record a case decision.
            </p>
          )}
        </TabsContent>
      </Tabs>
    </>
  )
}
