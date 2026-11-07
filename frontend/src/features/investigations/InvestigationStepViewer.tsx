import type { AgentStep } from '../../api/types'
import { Badge } from '../../components/ui/badge'
import { EvidenceViewer } from '../../components/data/EvidenceViewer'
import { formatDateTime } from '../../lib/format'

export function InvestigationStepViewer({ steps }: { steps: AgentStep[] }) {
  return (
    <ol className="space-y-3">
      {steps.map((step) => (
        <li key={step.id} className="rounded-surface border border-border p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-medium">{step.node_name.replace(/_/g, ' ')}</h3>
            <Badge tone={step.status === 'failed' ? 'negative' : 'neutral'}>{step.status}</Badge>
          </div>
          <p className="mt-1 text-xs text-foreground-muted">
            Attempt {step.attempt} · {formatDateTime(step.started_at)}
          </p>
          {step.error && (
            <p role="alert" className="mt-2 break-words text-xs">
              {step.error}
            </p>
          )}
          {step.tool_calls.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs text-accent">
                {step.tool_calls.length} tool call{step.tool_calls.length === 1 ? '' : 's'}
              </summary>
              <ul className="mt-2 space-y-2">
                {step.tool_calls.map((call, i) => (
                  <li key={i} className="rounded-control bg-background p-2 text-xs">
                    <p className="break-all font-mono">
                      {call.tool} · {call.duration_ms}ms
                    </p>
                    <p className="mt-1 break-all text-foreground-muted">
                      Result: {call.result_ref ?? 'No result'}
                      {call.error ? ` · ${call.error}` : ''}
                    </p>
                    <EvidenceViewer payload={call.args_summary} />
                  </li>
                ))}
              </ul>
            </details>
          )}
          {step.output && <EvidenceViewer payload={step.output} />}
        </li>
      ))}
    </ol>
  )
}
