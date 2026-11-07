import type { HTMLAttributes } from 'react'

import { cn } from '../../lib/cn'

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'animate-pulse rounded-[var(--radius-control)] bg-neutral-100 dark:bg-neutral-800',
        className,
      )}
      {...props}
    />
  )
}
