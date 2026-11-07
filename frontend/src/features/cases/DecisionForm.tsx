import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { recordDecision } from '../../api/cases'
import type { CaseDecision, DecisionValue, CaseStatus } from '../../api/types'
import { ConfirmationDialog } from '../../components/data/ConfirmationDialog'
import { describeError } from '../../components/data/ErrorState'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Label } from '../../components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'
import { formatDateTime } from '../../lib/format'

const DECISIONS: DecisionValue[] = ['confirmed_fraud', 'not_fraud', 'dismissed']
const DECISION_LABEL: Record<DecisionValue, string> = {
  confirmed_fraud: 'Confirmed fraud',
  not_fraud: 'Not fraud',
  dismissed: 'Dismissed',
}

interface DecisionFormProps {
  caseId: string
  caseStatus: CaseStatus
  existingDecision: CaseDecision | null
  onDecided: () => void
}

export function DecisionForm({
  caseId,
  caseStatus,
  existingDecision,
  onDecided,
}: DecisionFormProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [decision, setDecision] = useState<DecisionValue>('confirmed_fraud')
  const [rationale, setRationale] = useState('')

  const mutation = useMutation({
    mutationFn: () => recordDecision(caseId, decision, rationale.trim()),
    onSuccess: () => {
      setConfirmOpen(false)
      onDecided()
    },
  })

  if (existingDecision) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Decision</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="font-medium text-foreground">{DECISION_LABEL[existingDecision.decision]}</p>
          <p className="whitespace-pre-wrap break-words text-foreground-muted">
            {existingDecision.rationale}
          </p>
          <p className="text-xs text-foreground-subtle">
            Recorded {formatDateTime(existingDecision.decided_at)}
          </p>
        </CardContent>
      </Card>
    )
  }

  const canDecide = caseStatus === 'investigating' || caseStatus === 'pending_review'

  return (
    <Card>
      <CardHeader>
        <CardTitle>Record decision</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {!canDecide && (
          <p className="text-sm text-foreground-muted">
            A decision can only be recorded while the case is <strong>investigating</strong> or{' '}
            <strong>pending review</strong> — move it there first.
          </p>
        )}
        <div className="space-y-1.5">
          <Label>Decision</Label>
          <Select
            value={decision}
            onValueChange={(value) => setDecision(value as DecisionValue)}
            disabled={!canDecide}
          >
            <SelectTrigger aria-label="Case decision" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DECISIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {DECISION_LABEL[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="rationale">Rationale (minimum 10 characters)</Label>
          <textarea
            id="rationale"
            className="h-24 w-full rounded-[var(--radius-control)] border border-border-strong bg-surface px-2.5 py-2 text-sm text-foreground disabled:opacity-50"
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            disabled={!canDecide}
          />
        </div>
        {mutation.error && (
          <p className="text-xs text-status-negative">{describeError(mutation.error)}</p>
        )}
        <Button
          variant="primary"
          disabled={!canDecide || rationale.trim().length < 10 || mutation.isPending}
          onClick={() => {
            mutation.reset()
            setConfirmOpen(true)
          }}
        >
          Review decision
        </Button>
        <ConfirmationDialog
          open={confirmOpen}
          onOpenChange={setConfirmOpen}
          title="Record final case decision?"
          description="This records your identity and rationale and resolves the case. Review the evidence before confirming."
          pending={mutation.isPending}
          error={mutation.error}
          onConfirm={() => mutation.mutate()}
          confirmLabel="Record decision"
        >
          <p className="font-semibold">{DECISION_LABEL[decision]}</p>
          <p className="mt-2">{rationale}</p>
        </ConfirmationDialog>
      </CardContent>
    </Card>
  )
}
