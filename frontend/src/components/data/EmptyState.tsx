import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center"
      role="status"
    >
      {Icon && <Icon className="h-6 w-6 text-foreground-subtle" aria-hidden="true" />}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="max-w-sm text-sm text-foreground-muted">{description}</p>}
      {action}
    </div>
  )
}
