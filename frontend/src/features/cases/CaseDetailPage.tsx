import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { attachEvidence, getCaseDecision, listCaseEvidence, updateCase } from '../../api/cases'
import { ApiError } from '../../api/client'
import { getCaseContext, openReport, type Activity } from '../../api/workspace'
import { useAuth } from '../../context/AuthContext'
import { ErrorState } from '../../components/data/ErrorState'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/button'
import { Pagination } from '../../components/ui/pagination'
import { Skeleton } from '../../components/ui/skeleton'
import { formatCurrency, formatDateTime } from '../../lib/format'
import { InvestigationReport } from '../investigations/InvestigationDetailPage'
import { ActivityDetail, Connections } from '../workspace/Activity'
import { panel, readable } from '../workspace/presentation'
import { DecisionForm } from './DecisionForm'

export function CaseDetailPage() {
  const { caseId = '' } = useParams()
  return <Workspace key={caseId} caseId={caseId} />
}
function Workspace({ caseId }: { caseId: string }) {
  const client = useQueryClient()
  const { hasRole } = useAuth()
  const [selected, setSelected] = useState(0)
  const query = useQuery({
    queryKey: ['workspace-case', caseId],
    queryFn: () => getCaseContext(caseId),
  })
  const decision = useQuery({
    queryKey: ['case-decision', caseId],
    queryFn: () => getCaseDecision(caseId),
    retry: false,
  })
  function refreshWorkspace() {
    void query.refetch()
    void client.invalidateQueries({ queryKey: ['workspace-dashboard'] })
    void client.invalidateQueries({ queryKey: ['workspace-cases'] })
  }
  const report = useMutation({ mutationFn: () => openReport(caseId), onSuccess: refreshWorkspace })
  const update = useMutation({
    mutationFn: () => updateCase(caseId, { status: 'investigating' }),
    onSuccess: refreshWorkspace,
  })
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  if (!query.data) return <Skeleton className="h-64 w-full" />
  const data = query.data
  const item = data.activities[selected] ?? data.activities[0]
  const graphStep = item ? Math.max(...data.activities.map((a) => a.transaction.step)) : undefined
  const noDecision = decision.error instanceof ApiError && decision.error.status === 404
  return (
    <>
      <Link className="mb-4 inline-block text-xs text-accent" to="/investigations">
        ← Investigations
      </Link>
      <PageHeader
        title={data.case.title}
        description="Review the evidence, prepare a report, and record a human decision."
        actions={
          <span className="text-xs capitalize">
            {readable(data.case.status)} · {data.case.priority} priority
          </span>
        }
      />
      <nav
        aria-label="Investigation sections"
        className="mb-5 flex flex-wrap gap-5 border-b border-border pb-3 text-sm text-accent"
      >
        <a href="#activity">Activity</a>
        <a href="#supporting">Supporting evidence</a>
        <a href="#report">Investigation report</a>
        <a href="#decision">Case decision</a>
      </nav>
      <section id="activity" className="scroll-mt-4">
        {data.activities.length > 1 && (
          <label className="mb-4 grid w-full min-w-0 max-w-lg gap-1 text-xs">
            Linked payments
            <select
              className="w-full min-w-0 rounded-control border border-border bg-surface px-3 py-2"
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
            >
              {data.activities.map((a, i) => (
                <option key={a.transaction.id} value={i}>
                  {a.sender} → {a.recipient} · {formatCurrency(a.transaction.amount)}
                </option>
              ))}
            </select>
          </label>
        )}
        {item ? (
          <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
            <ActivityDetail item={item} />
            <Connections
              key={item.transaction.id}
              accountId={item.transaction.origin_account_id}
              step={graphStep}
            />
          </div>
        ) : (
          <p className={panel}>No linked payments are available for this case.</p>
        )}
      </section>
      <section id="supporting" className="mt-5 scroll-mt-4">
        <h2 className="mb-3 text-sm font-semibold">Supporting evidence</h2>
        <SupportingEvidence caseId={caseId} activity={item} graphStep={graphStep} />
      </section>
      <section id="report" className="mt-6 scroll-mt-4">
        <h2 className="mb-3 text-sm font-semibold">Investigation report</h2>
        {data.run_id ? (
          <InvestigationReport key={data.run_id} runId={data.run_id} embedded />
        ) : (
          <div className={panel}>
            <p className="mb-3 text-sm text-foreground-muted">
              Prepare a report using the linked transactions, model assessments, and account
              connections. You review the findings before approving them.
            </p>
            <Button variant="primary" disabled={report.isPending} onClick={() => report.mutate()}>
              {report.isPending ? 'Starting investigation…' : 'Start AI investigation'}
            </Button>
            {report.error && <ErrorState error={report.error} />}
          </div>
        )}
      </section>
      <section id="decision" className="mt-6 scroll-mt-4">
        <h2 className="mb-2 text-sm font-semibold">Case decision</h2>
        <p className="mb-3 text-sm text-foreground-muted">
          Approving a report does not resolve this case. A senior analyst or admin records the final
          decision and rationale here.
        </p>
        {data.case.status === 'open' && (
          <Button className="mb-3" disabled={update.isPending} onClick={() => update.mutate()}>
            Begin review
          </Button>
        )}
        {update.error && <ErrorState error={update.error} />}
        {decision.isPending ? (
          <Skeleton className="h-20 w-full" />
        ) : decision.error && !noDecision ? (
          <ErrorState error={decision.error} />
        ) : decision.data || hasRole('senior_analyst', 'admin') ? (
          <DecisionForm
            key={caseId}
            caseId={caseId}
            caseStatus={data.case.status}
            existingDecision={decision.data ?? null}
            onDecided={() => {
              void client.invalidateQueries({ queryKey: ['case-decision', caseId] })
              refreshWorkspace()
            }}
          />
        ) : (
          <p className={panel + ' text-sm text-foreground-muted'}>
            Only a senior analyst or admin can record the final case decision.
          </p>
        )}
      </section>
      <details className="mt-5 text-xs text-foreground-muted">
        <summary>Technical details</summary>
        <p className="break-all">
          Case {caseId} · created {formatDateTime(data.case.created_at)}
        </p>
      </details>
    </>
  )
}
function SupportingEvidence({
  caseId,
  activity,
  graphStep,
}: {
  caseId: string
  activity?: Activity
  graphStep?: number
}) {
  const [note, setNote] = useState('')
  const [offset, setOffset] = useState(0)
  const query = useQuery({
    queryKey: ['case-evidence', caseId, offset],
    queryFn: () => listCaseEvidence(caseId, { offset, limit: 10 }),
  })
  const add = useMutation({
    mutationFn: (kind: 'analyst_note' | 'graph_neighborhood' | 'historical_stats') =>
      attachEvidence(
        caseId,
        kind === 'analyst_note'
          ? { evidence_type: kind, body: note.trim() }
          : {
              evidence_type: kind,
              source_id: activity!.transaction.origin_account_id,
              as_of_step:
                kind === 'graph_neighborhood'
                  ? (graphStep ?? activity!.transaction.step) + 1
                  : activity!.transaction.step,
              hops: 2,
            },
      ),
    onSuccess: () => {
      setNote('')
      void query.refetch()
    },
  })
  return (
    <div className={panel}>
      {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      <ul className="divide-y divide-border">
        {query.data?.items.map((e) => (
          <li key={e.id} className="py-3">
            <p className="text-sm font-medium capitalize">
              {e.evidence_type === 'shap_explanation'
                ? 'Model risk factors'
                : e.evidence_type === 'graph_neighborhood'
                  ? 'Connected accounts'
                  : e.evidence_type === 'historical_stats'
                    ? 'Account history'
                    : readable(e.evidence_type)}
            </p>
            {e.evidence_type === 'transaction' && (
              <p className="mt-1 text-sm text-foreground-muted">
                {formatCurrency(String(e.evidence_payload.amount))} ·{' '}
                {readable(String(e.evidence_payload.external_ref))}
              </p>
            )}
            {e.evidence_type === 'analyst_note' && (
              <p className="mt-1 whitespace-pre-wrap break-words text-sm">
                {String(e.evidence_payload.body)}
              </p>
            )}
            <details className="mt-2 text-xs text-foreground-muted">
              <summary>Technical details · source and snapshot</summary>
              <p className="break-all">{e.source_reference}</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all">
                {JSON.stringify(e.evidence_payload, null, 2)}
              </pre>
            </details>
          </li>
        ))}
      </ul>
      {query.data && (
        <Pagination
          total={query.data.total}
          limit={10}
          offset={offset}
          onOffsetChange={setOffset}
        />
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {activity && (
          <>
            <Button
              size="sm"
              disabled={add.isPending}
              onClick={() => add.mutate('graph_neighborhood')}
            >
              Save connected accounts
            </Button>
            <Button
              size="sm"
              disabled={add.isPending}
              onClick={() => add.mutate('historical_stats')}
            >
              Save account history
            </Button>
          </>
        )}
      </div>
      <label className="mt-4 block text-xs font-medium" htmlFor="analyst-note">
        Analyst note
      </label>
      <textarea
        id="analyst-note"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="mt-2 h-20 w-full rounded-control border border-border bg-surface p-3 text-sm"
      />
      <Button
        className="mt-2"
        size="sm"
        disabled={!note.trim() || add.isPending}
        onClick={() => add.mutate('analyst_note')}
      >
        Save note
      </Button>
      {add.error && <ErrorState error={add.error} />}
    </div>
  )
}
