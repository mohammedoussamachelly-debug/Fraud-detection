import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  approveInvestigation,
  getInvestigation,
  rejectInvestigation,
  requestInvestigationRevision,
} from '../../api/investigations'
import { CitationChip } from '../../components/data/CitationChip'
import { ConfirmationDialog } from '../../components/data/ConfirmationDialog'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { InvestigationStatusBadge } from '../../components/data/StatusBadge'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime, shortId } from '../../lib/format'
import { InvestigationStepViewer } from './InvestigationStepViewer'

type ReviewAction = 'approve' | 'reject' | 'revision'
export function InvestigationDetailPage() {
  const { runId = '' } = useParams()
  const client = useQueryClient()
  const [action, setAction] = useState<ReviewAction | null>(null)
  const [feedback, setFeedback] = useState('')
  const query = useQuery({
    queryKey: ['investigation', runId],
    queryFn: () => getInvestigation(runId),
    refetchInterval: (q) =>
      ['running', 'revision_requested'].includes(q.state.data?.status ?? '') ? 2000 : false,
  })
  const review = useMutation({
    mutationFn: (value: ReviewAction) =>
      value === 'approve'
        ? approveInvestigation(runId)
        : value === 'reject'
          ? rejectInvestigation(runId)
          : requestInvestigationRevision(runId, feedback.trim()),
    onSuccess: (updated) => {
      client.setQueryData(['investigation', runId], updated)
      void client.invalidateQueries({ queryKey: ['case-investigations', updated.case_id] })
      void client.invalidateQueries({ queryKey: ['audit-log'] })
      setAction(null)
      setFeedback('')
    },
  })
  if (query.isPending) return <Skeleton className="h-64 w-full" />
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const run = query.data
  const report = run.final_report ?? run.draft_report
  const canReview = run.status === 'awaiting_approval'
  function citation(reference: string) {
    const item = run.evidence_refs.find((e) => e.source_reference === reference)
    return (
      <CitationChip
        key={reference}
        reference={reference}
        resolved={!!item}
        onClick={() => {
          if (item) {
            const element = document.getElementById(`evidence-${item.id}`)
            element?.scrollIntoView({ block: 'center', behavior: 'instant' })
            element?.focus()
          }
        }}
      />
    )
  }
  return (
    <>
      <Link
        to={`/cases/${run.case_id}?tab=investigations`}
        className="mb-4 inline-block text-xs text-accent"
      >
        ← Case {shortId(run.case_id)}
      </Link>
      <PageHeader
        title={`Investigation ${shortId(run.run_id)}`}
        description={`Started ${formatDateTime(run.started_at)} · ${run.model_provider} / ${run.model_name} · prompt ${run.prompt_version}`}
        actions={<InvestigationStatusBadge status={run.status} />}
      />
      <div className="mb-4 rounded-control border border-border bg-surface p-3 text-sm">
        <strong>Human review required.</strong> Report approval records your review of the AI
        output. A case decision is a separate action for a senior analyst or admin.
      </div>
      {(run.model_provider === 'mock' || report?.is_mock) && (
        <p className="mb-4 rounded-control border border-status-attention/40 bg-status-attention/10 p-3 text-sm text-status-attention">
          <strong>Mock AI report</strong> — deterministic demonstration output, not live model
          inference.
        </p>
      )}
      {run.error && (
        <p role="alert" className="mb-4 break-words text-sm">
          Investigation failed: {run.error}
        </p>
      )}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Execution timeline</CardTitle>
            <p className="text-xs text-foreground-muted">
              {run.steps.length} recorded steps · {run.revision_count} revisions
            </p>
          </CardHeader>
          <CardContent>
            {run.steps.length ? (
              <InvestigationStepViewer steps={run.steps} />
            ) : (
              <EmptyState
                title={
                  run.status === 'running' ? 'Waiting for the first step' : 'No steps recorded'
                }
              />
            )}
          </CardContent>
        </Card>
        <div className="min-w-0 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{run.final_report ? 'Reviewed report' : 'Draft report'}</CardTitle>
            </CardHeader>
            <CardContent>
              {!report ? (
                <EmptyState
                  title={
                    run.status === 'running'
                      ? 'Evidence collection in progress'
                      : 'No report available'
                  }
                  description="A report appears here once the agent has finished collecting and reviewing evidence."
                />
              ) : (
                <div className="space-y-5 break-words text-sm">
                  <p className="whitespace-pre-wrap leading-relaxed">{report.summary}</p>
                  <section>
                    <h2 className="mb-2 font-semibold">Findings</h2>
                    {report.hypotheses.length === 0 ? (
                      <p className="text-foreground-muted">No hypotheses were generated.</p>
                    ) : (
                      <ol className="space-y-3">
                        {report.hypotheses.map((hypothesis, i) => (
                          <li key={i} className="rounded-control border border-border p-3">
                            <p>{hypothesis.text}</p>
                            <p className="my-2 text-xs text-foreground-muted">
                              Confidence: {hypothesis.confidence}
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {hypothesis.evidence_refs.map(citation)}
                            </div>
                          </li>
                        ))}
                      </ol>
                    )}
                  </section>
                  <section>
                    <h2 className="mb-2 font-semibold">Uncertainties</h2>
                    {report.uncertainties.length ? (
                      <ul className="list-disc space-y-1 pl-5 text-foreground-muted">
                        {report.uncertainties.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-foreground-muted">None stated by the report.</p>
                    )}
                  </section>
                  <section>
                    <h2 className="mb-2 font-semibold">Recommended next step</h2>
                    <p>{report.recommended_next_step}</p>
                  </section>
                </div>
              )}
            </CardContent>
          </Card>
          {canReview && (
            <Card>
              <CardHeader>
                <CardTitle>Review report</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="primary"
                    disabled={!report || review.isPending}
                    onClick={() => {
                      review.reset()
                      setAction('approve')
                    }}
                  >
                    Approve report
                  </Button>
                  <Button
                    disabled={review.isPending}
                    onClick={() => {
                      review.reset()
                      setAction('reject')
                    }}
                  >
                    Reject report
                  </Button>
                </div>
                <label className="mt-4 block text-xs font-medium" htmlFor="revision-feedback">
                  Revision feedback
                </label>
                <textarea
                  id="revision-feedback"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  className="mt-2 min-h-24 w-full rounded-control border border-border-strong bg-surface p-3 text-sm"
                  placeholder="Describe missing evidence or findings that need revision."
                />
                <Button
                  className="mt-2"
                  disabled={!feedback.trim() || review.isPending}
                  onClick={() => {
                    review.reset()
                    setAction('revision')
                  }}
                >
                  Request revision
                </Button>
              </CardContent>
            </Card>
          )}
          {run.review_feedback.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Revision feedback history</CardTitle>
              </CardHeader>
              <CardContent>
                <ol className="list-decimal space-y-2 pl-5 text-sm">
                  {run.review_feedback.map((item, i) => (
                    <li key={i} className="whitespace-pre-wrap break-words">
                      {item}
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Collected evidence references</CardTitle>
        </CardHeader>
        <CardContent>
          {run.evidence_refs.length === 0 ? (
            <EmptyState title="No evidence references collected" />
          ) : (
            <ul className="divide-y divide-border">
              {run.evidence_refs.map((e) => (
                <li key={e.id} id={`evidence-${e.id}`} tabIndex={-1} className="py-3">
                  <p className="break-all font-mono text-xs">{e.source_reference}</p>
                  <p className="mt-1 break-words text-sm">{e.summary}</p>
                  <p className="mt-1 text-xs text-foreground-muted">
                    Collected by {e.collected_by_node} · {formatDateTime(e.created_at)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      <ConfirmationDialog
        open={action !== null}
        onOpenChange={(open) => {
          if (!open) setAction(null)
        }}
        title={
          action === 'approve'
            ? 'Approve this report?'
            : action === 'reject'
              ? 'Reject this report?'
              : 'Request a revised report?'
        }
        description="This review is recorded against the investigation. It does not record a fraud case decision."
        pending={review.isPending}
        error={review.error}
        onConfirm={() => {
          if (action) review.mutate(action)
        }}
        confirmLabel={
          action === 'approve'
            ? 'Confirm report approval'
            : action === 'reject'
              ? 'Confirm rejection'
              : 'Send revision request'
        }
      >
        {action === 'revision'
          ? feedback
          : `Investigation ${shortId(runId)} · case ${shortId(run.case_id)}`}
      </ConfirmationDialog>
    </>
  )
}
