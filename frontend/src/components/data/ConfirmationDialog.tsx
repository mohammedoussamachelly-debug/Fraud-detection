import type { ReactNode } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../ui/dialog'
import { Button } from '../ui/button'
import { describeError } from './ErrorState'

export function ConfirmationDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  onConfirm,
  pending,
  error,
  confirmLabel = 'Confirm',
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  children?: ReactNode
  onConfirm: () => void
  pending: boolean
  error?: unknown
  confirmLabel?: string
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!pending) onOpenChange(value)
      }}
    >
      <DialogContent>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        {children && <div className="mt-4 whitespace-pre-wrap break-words text-sm">{children}</div>}
        {error ? (
          <p role="alert" className="mt-3 text-sm">
            {describeError(error)}
          </p>
        ) : null}
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={() => onOpenChange(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onConfirm} disabled={pending}>
            {pending ? 'Saving…' : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
