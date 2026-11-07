import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import type { ComponentProps } from 'react'

import { cn } from '../../lib/cn'

export const TooltipProvider = TooltipPrimitive.Provider
export const Tooltip = TooltipPrimitive.Root
export const TooltipTrigger = TooltipPrimitive.Trigger

export function TooltipContent({
  className,
  ...props
}: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        className={cn(
          'z-50 rounded-[var(--radius-control)] bg-neutral-900 px-2 py-1 text-xs text-neutral-50 shadow-md dark:bg-neutral-100 dark:text-neutral-900',
          className,
        )}
        sideOffset={4}
        {...props}
      />
    </TooltipPrimitive.Portal>
  )
}
