import type { ReactNode } from 'react'

export function PageHeader({
  title,
  description,
  actions,
  headingLevel = 1,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  headingLevel?: 1 | 2
}) {
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  return (
    <div className="mb-5 flex flex-col sm:flex-row items-start justify-between gap-4">
      <div className="min-w-0">
        <Heading className="break-words text-lg font-semibold text-foreground">{title}</Heading>
        {description && <p className="mt-0.5 text-sm text-foreground-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
