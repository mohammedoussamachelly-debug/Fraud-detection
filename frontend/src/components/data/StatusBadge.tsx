import { Badge, type BadgeProps } from '../ui/badge'

const ALERT_STATUS_TONE: Record<string, BadgeProps['tone']> = {
  open: 'info',
  triaged: 'pending',
  escalated: 'negative',
  dismissed: 'neutral',
}

const CASE_STATUS_TONE: Record<string, BadgeProps['tone']> = {
  open: 'info',
  investigating: 'pending',
  pending_review: 'attention',
  resolved: 'positive',
  closed: 'neutral',
}

const INVESTIGATION_STATUS_TONE: Record<string, BadgeProps['tone']> = {
  running: 'pending',
  awaiting_approval: 'attention',
  approved: 'positive',
  rejected: 'negative',
  revision_requested: 'attention',
  failed: 'negative',
}

function label(value: string): string {
  return value.replace(/_/g, ' ')
}

export function AlertStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={ALERT_STATUS_TONE[status] ?? 'neutral'} dot>
      {label(status)}
    </Badge>
  )
}

export function CaseStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={CASE_STATUS_TONE[status] ?? 'neutral'} dot>
      {label(status)}
    </Badge>
  )
}

export function InvestigationStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={INVESTIGATION_STATUS_TONE[status] ?? 'neutral'} dot>
      {label(status)}
    </Badge>
  )
}
