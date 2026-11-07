import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { useState } from 'react'

import { attachEvidence, listCaseEvidence } from '../../api/cases'
import type { EvidenceType } from '../../api/types'
import { EvidenceViewer } from '../../components/data/EvidenceViewer'
import { Pagination } from '../../components/ui/pagination'
import { UUID_PATTERN } from '../../lib/validation'
import { EVIDENCE_TYPES } from '../../api/types'
import { describeError } from '../../components/data/ErrorState'
import { EmptyState } from '../../components/data/EmptyState'
import { ErrorState } from '../../components/data/ErrorState'
import { Button } from '../../components/ui/button'
import { Card } from '../../components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../components/ui/dialog'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import { Skeleton } from '../../components/ui/skeleton'
import { formatDateTime } from '../../lib/format'

const SOURCE_ID_TYPES: EvidenceType[] = [
  'transaction',
  'risk_score',
  'shap_explanation',
  'graph_neighborhood',
  'graph_metrics',
  'fund_flow',
  'historical_stats',
]

export function EvidencePanel({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient()
  const [offset, setOffset] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)

  const query = useQuery({
    queryKey: ['case-evidence', caseId, offset],
    queryFn: () => listCaseEvidence(caseId, { limit: 25, offset }),
  })

  function onAttached() {
    setDialogOpen(false)
    queryClient.invalidateQueries({ queryKey: ['case-evidence', caseId] })
  }

  return (
    <div>
      <div className="mb-3 flex justify-end">
        <Button variant="outline" size="sm" onClick={() => setDialogOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> Attach evidence
        </Button>
      </div>

      {query.isLoading && <Skeleton className="h-24 w-full" />}
      {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      {query.data && query.data.items.length === 0 && (
        <EmptyState
          title="No evidence attached yet"
          description="Attach a transaction, score, graph snapshot, or note."
        />
      )}
      {query.data && query.data.items.length > 0 && (
        <div className="space-y-2">
          {query.data.items.map((item) => (
            <Card key={item.id} className="p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium capitalize text-foreground">
                  {item.evidence_type.replace(/_/g, ' ')}
                </span>
                <span className="text-xs text-foreground-subtle">
                  {formatDateTime(item.created_at)}
                </span>
              </div>
              <p className="mt-1 break-all font-mono text-xs text-foreground-muted">
                {item.source_reference}
              </p>
              <EvidenceViewer payload={item.evidence_payload} />
              {item.evidence_type === 'analyst_note' &&
                typeof item.evidence_payload.body === 'string' && (
                  <p className="mt-2 whitespace-pre-wrap break-words text-sm text-foreground">
                    {item.evidence_payload.body}
                  </p>
                )}
            </Card>
          ))}
        </div>
      )}

      {query.data && (
        <Pagination
          limit={25}
          offset={offset}
          total={query.data.total}
          disabled={query.isFetching}
          onOffsetChange={setOffset}
        />
      )}
      <AttachEvidenceDialog
        caseId={caseId}
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        onAttached={onAttached}
      />
    </div>
  )
}

function AttachEvidenceDialog({
  caseId,
  open,
  onOpenChange,
  onAttached,
}: {
  caseId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onAttached: () => void
}) {
  const [evidenceType, setEvidenceType] = useState<EvidenceType>('analyst_note')
  const [sourceId, setSourceId] = useState('')
  const [body, setBody] = useState('')
  const [snapshotStep, setSnapshotStep] = useState('')
  const [hops, setHops] = useState('2')
  const [maxHops, setMaxHops] = useState('3')
  const [branches, setBranches] = useState('5')
  const graphEvidence = ['graph_neighborhood', 'graph_metrics', 'fund_flow'].includes(evidenceType)

  const mutation = useMutation({
    mutationFn: () =>
      attachEvidence(caseId, {
        evidence_type: evidenceType,
        source_id: evidenceType === 'analyst_note' ? undefined : sourceId.trim(),
        body: evidenceType === 'analyst_note' ? body.trim() : undefined,
        as_of_step: graphEvidence && snapshotStep !== '' ? Number(snapshotStep) : undefined,
        hops: evidenceType === 'graph_neighborhood' ? Number(hops) : undefined,
        max_hops: evidenceType === 'fund_flow' ? Number(maxHops) : undefined,
        max_branches: evidenceType === 'fund_flow' ? Number(branches) : undefined,
      }),
    onSuccess: () => {
      setSourceId('')
      setBody('')
      onAttached()
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Attach evidence</DialogTitle>
        <DialogDescription>
          Resolve a source record from the backend, or record an analyst note.
        </DialogDescription>
        <form
          className="mt-4 space-y-3"
          onSubmit={(e) => {
            e.preventDefault()
            mutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label>Evidence type</Label>
            <Select
              value={evidenceType}
              onValueChange={(value) => setEvidenceType(value as EvidenceType)}
            >
              <SelectTrigger aria-label="Evidence type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EVIDENCE_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type.replace(/_/g, ' ')}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {evidenceType === 'analyst_note' ? (
            <div className="space-y-1.5">
              <Label htmlFor="note-body">Note</Label>
              <textarea
                id="note-body"
                className="h-24 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-2.5 py-2 text-sm text-foreground"
                value={body}
                onChange={(e) => setBody(e.target.value)}
              />
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor="source-id">
                {SOURCE_ID_TYPES.includes(evidenceType) &&
                (evidenceType === 'transaction' ||
                  evidenceType === 'risk_score' ||
                  evidenceType === 'shap_explanation')
                  ? evidenceType === 'transaction'
                    ? 'Transaction ID'
                    : 'Risk score ID'
                  : 'Account id'}
              </Label>
              <Input
                required
                pattern={UUID_PATTERN}
                id="source-id"
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                placeholder="uuid"
              />
            </div>
          )}
          {graphEvidence && (
            <div className="grid grid-cols-2 gap-3">
              <label className="grid gap-1 text-xs text-foreground-muted">
                Snapshot through step
                <Input
                  type="number"
                  min={0}
                  step={1}
                  value={snapshotStep}
                  onChange={(e) => setSnapshotStep(e.target.value)}
                  placeholder="All history"
                />
              </label>
              {evidenceType === 'graph_neighborhood' && (
                <label className="grid gap-1 text-xs text-foreground-muted">
                  Neighborhood hops
                  <Input
                    required
                    type="number"
                    min={1}
                    max={4}
                    value={hops}
                    onChange={(e) => setHops(e.target.value)}
                  />
                </label>
              )}
              {evidenceType === 'fund_flow' && (
                <>
                  <label className="grid gap-1 text-xs text-foreground-muted">
                    Maximum hops
                    <Input
                      required
                      type="number"
                      min={1}
                      max={5}
                      value={maxHops}
                      onChange={(e) => setMaxHops(e.target.value)}
                    />
                  </label>
                  <label className="grid gap-1 text-xs text-foreground-muted">
                    Maximum branches
                    <Input
                      required
                      type="number"
                      min={1}
                      max={10}
                      value={branches}
                      onChange={(e) => setBranches(e.target.value)}
                    />
                  </label>
                </>
              )}
            </div>
          )}
          {mutation.error && (
            <p role="alert" className="text-xs text-status-negative">
              {describeError(mutation.error)}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={
                mutation.isPending ||
                (evidenceType === 'analyst_note'
                  ? !body.trim()
                  : !new RegExp(`^${UUID_PATTERN}$`).test(sourceId.trim()))
              }
            >
              {mutation.isPending ? 'Attaching…' : 'Attach'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
