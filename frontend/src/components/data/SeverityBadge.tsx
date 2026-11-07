import { cn } from '../../lib/cn'

const SEVERITY_COLOR: Record<string, string> = {
  low: 'bg-severity-low',
  medium: 'bg-severity-medium',
  high: 'bg-severity-high',
  critical: 'bg-severity-critical',
}

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium capitalize text-foreground">
      <span
        className={cn('h-1.5 w-1.5 rounded-full', SEVERITY_COLOR[severity] ?? 'bg-neutral-400')}
        aria-hidden="true"
      />
      {severity}
    </span>
  )
}

const RISK_COLOR: Record<string, string> = {
  low: 'text-risk-low',
  medium: 'text-risk-medium',
  high: 'text-risk-high',
}

export function RiskBadge({ level, score }: { level: string; score?: number }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 text-xs font-semibold capitalize',
        RISK_COLOR[level] ?? 'text-foreground-muted',
      )}
    >
      {level}
      {score !== undefined && (
        <span className="tabular-nums text-foreground-subtle">({score.toFixed(3)})</span>
      )}
    </span>
  )
}
