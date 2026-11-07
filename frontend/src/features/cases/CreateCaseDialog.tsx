import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { createCase } from '../../api/cases'
import type { CasePriority } from '../../api/types'
import { describeError } from '../../components/data/ErrorState'
import { Button } from '../../components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '../../components/ui/dialog'
import { Label } from '../../components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select'

const PRIORITIES: CasePriority[] = ['low', 'medium', 'high', 'critical']

interface CreateCaseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  alertIds: string[]
  onCreated: (caseId: string) => void
}

export function CreateCaseDialog({
  open,
  onOpenChange,
  alertIds,
  onCreated,
}: CreateCaseDialogProps) {
  const queryClient = useQueryClient()
  const [priority, setPriority] = useState<CasePriority>('medium')

  const mutation = useMutation({
    mutationFn: () => createCase(alertIds, priority),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: ['cases'] })
      onOpenChange(false)
      onCreated(created.id)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Create case</DialogTitle>
        <DialogDescription>
          Groups {alertIds.length} alert{alertIds.length === 1 ? '' : 's'} into one investigation
          case.
        </DialogDescription>
        <div className="mt-4 space-y-1.5">
          <Label>Priority</Label>
          <Select value={priority} onValueChange={(value) => setPriority(value as CasePriority)}>
            <SelectTrigger aria-label="Case priority" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIORITIES.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {mutation.error && (
          <p className="mt-3 text-xs text-status-negative">{describeError(mutation.error)}</p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? 'Creating…' : 'Create case'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
