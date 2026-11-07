import { cva, type VariantProps } from 'class-variance-authority'
import type { HTMLAttributes } from 'react'

import { cn } from '../../lib/cn'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium leading-none',
  {
    variants: {
      tone: {
        neutral: 'bg-neutral-100 text-foreground-muted dark:bg-neutral-800',
        info: 'bg-blue-500/15 text-status-info',
        positive: 'bg-green-500/15 text-status-positive',
        attention: 'bg-amber-500/15 text-status-attention',
        negative: 'bg-red-500/15 text-status-negative',
        pending: 'bg-violet-500/15 text-status-pending',
      },
    },
    defaultVariants: { tone: 'neutral' },
  },
)

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {
  dot?: boolean
}

export function Badge({ className, tone, dot = false, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ tone }), className)} {...props}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  )
}
