import type { CaseDecision, CaseDetail } from '../../api/types'
import { formatDateTime, shortId } from '../../lib/format'

export function CaseTimeline({
  detail,
  decision,
}: {
  detail: CaseDetail
  decision?: CaseDecision
}) {
  const events = [
    { at: detail.created_at, text: 'Case created' },
    ...detail.alerts.map((link) => ({
      at: link.linked_at,
      text: `Alert ${shortId(link.alert_id)} linked`,
    })),
    ...(detail.updated_at !== detail.created_at
      ? [{ at: detail.updated_at, text: 'Latest recorded case update' }]
      : []),
    ...(decision
      ? [
          {
            at: decision.decided_at,
            text: `Human decision: ${decision.decision.replace(/_/g, ' ')} · ${shortId(decision.decided_by_user_id)}`,
          },
        ]
      : []),
    ...(detail.closed_at ? [{ at: detail.closed_at, text: 'Case closed' }] : []),
  ].sort((a, b) => a.at.localeCompare(b.at))
  return (
    <section>
      <h2 className="text-sm font-semibold">Recorded milestones</h2>
      <p className="mt-1 text-xs text-foreground-muted">
        Available case timestamps. A full status-change history is not exposed.
      </p>
      <ol className="mt-4 space-y-4 border-l border-border pl-4">
        {events.map((event, i) => (
          <li key={i}>
            <p className="text-sm">{event.text}</p>
            <time className="font-mono text-xs text-foreground-muted" dateTime={event.at}>
              {formatDateTime(event.at)}
            </time>
          </li>
        ))}
      </ol>
    </section>
  )
}
