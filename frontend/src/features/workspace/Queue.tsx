import { Link } from 'react-router-dom'
import type { InboxEntry } from '../../api/workspace'
import { formatCurrency, formatDateTime } from '../../lib/format'
import { InvestigateButton } from './Activity'
import { readable } from './presentation'
export function Queue({ items }: { items: InboxEntry[] }) {
  if (!items.length)
    return (
      <p className="rounded-control border border-border bg-surface p-6 text-sm text-foreground-muted">
        No alerts match this view.
      </p>
    )
  return (
    <div className="overflow-x-auto rounded-control border border-border bg-surface">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Prioritized activity requiring review</caption>
        <thead className="border-b border-border bg-surface-muted text-xs text-foreground-muted">
          <tr>
            {['Activity', 'Severity / status', 'Amount', 'Occurred', 'Next action'].map((h) => (
              <th key={h} className="px-4 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((item) => (
            <tr key={item.id}>
              <td className="min-w-64 px-4 py-3">
                <Link
                  className="font-medium text-foreground hover:text-accent"
                  to={`/transactions/${item.activity.transaction.id}`}
                >
                  {item.description}
                </Link>
                <p className="mt-1 text-xs text-foreground-muted">
                  {item.activity.sender} → {item.activity.recipient}
                </p>
                <p className="mt-1 text-xs text-foreground-muted">{item.source}</p>
              </td>
              <td className="whitespace-nowrap px-4 py-3">
                <span className="font-medium capitalize">{item.severity}</span>
                <p className="text-xs text-foreground-muted">{readable(item.status)}</p>
              </td>
              <td className="whitespace-nowrap px-4 py-3 tabular-nums">
                {formatCurrency(item.activity.transaction.amount)}
              </td>
              <td className="whitespace-nowrap px-4 py-3 text-xs text-foreground-muted">
                {formatDateTime(item.activity.transaction.occurred_at)}
              </td>
              <td className="min-w-40 px-4 py-3">
                <InvestigateButton alertId={item.id} caseId={item.activity.case_id} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
