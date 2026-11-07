import { Menu, LogOut, User as UserIcon } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { Button } from '../ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
import { ThemeToggle } from './ThemeToggle'

const ROLE_LABEL: Record<string, string> = {
  analyst: 'Analyst',
  senior_analyst: 'Senior Analyst',
  admin: 'Admin',
}

export function Header({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuth()

  return (
    <header className="flex h-12 items-center justify-between border-b border-border bg-surface px-4">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onMenu}
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" />
        </Button>
        <span className="text-xs text-foreground-muted">Investigation workspace</span>
      </div>
      <div className="flex items-center gap-3">
        <ThemeToggle />
        {user && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <UserIcon className="h-4 w-4" />
                <span className="flex flex-col items-start leading-tight">
                  <span className="max-w-32 truncate text-xs font-medium text-foreground">
                    {user.email}
                  </span>
                  <span className="text-[11px] text-foreground-subtle">
                    {ROLE_LABEL[user.role] ?? user.role}
                  </span>
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                onSelect={() => logout()}
                className="flex items-center gap-2 text-status-negative"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
    </header>
  )
}
