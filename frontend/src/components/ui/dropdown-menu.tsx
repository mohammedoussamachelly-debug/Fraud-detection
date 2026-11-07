import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'
import type { ComponentProps } from 'react'

import { cn } from '../../lib/cn'

export const DropdownMenu = DropdownMenuPrimitive.Root
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger

export function DropdownMenuContent({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        className={cn(
          'z-50 min-w-40 rounded-[var(--radius-surface)] border border-border bg-surface p-1 shadow-lg',
          className,
        )}
        sideOffset={4}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  )
}

export function DropdownMenuItem({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item>) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        'cursor-pointer rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm text-foreground outline-none data-[highlighted]:bg-neutral-100 dark:data-[highlighted]:bg-neutral-800',
        className,
      )}
      {...props}
    />
  )
}
