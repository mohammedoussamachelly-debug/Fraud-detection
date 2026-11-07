import {
  Activity,
  AudioLines,
  Bell,
  FolderKanban,
  LandmarkIcon,
  Network,
  SearchCheck,
  ReceiptText,
  Shield,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'
import { cn } from '../../lib/cn'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: Activity, roles: null },
  { to: '/alerts', label: 'Alerts', icon: Bell, roles: null },
  { to: '/cases', label: 'Cases', icon: FolderKanban, roles: null },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText, roles: null },
  { to: '/network', label: 'Network Explorer', icon: Network, roles: null },
  { to: '/investigations', label: 'AI Investigations', icon: SearchCheck, roles: null },
  { to: '/accounts', label: 'Accounts', icon: LandmarkIcon, Network, SearchCheck, roles: null },
  { to: '/audit-log', label: 'Audit log', icon: Shield, roles: ['admin'] as const },
] as const

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { hasRole } = useAuth()

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-12 items-center gap-2 border-b border-border px-4">
        <AudioLines className="h-4 w-4 text-accent" aria-hidden="true" />
        <span className="text-sm font-semibold text-foreground">SentinelAI</span>
      </div>
      <nav
        aria-label="Primary navigation"
        onClick={onNavigate}
        className="flex-1 space-y-0.5 px-2 py-3"
      >
        {NAV_ITEMS.filter((item) => item.roles === null || hasRole(...item.roles)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-sm font-medium text-foreground-muted hover:bg-neutral-100 hover:text-foreground dark:hover:bg-neutral-800',
                isActive && 'bg-neutral-100 text-foreground dark:bg-neutral-800',
              )
            }
          >
            <item.icon className="h-4 w-4" aria-hidden="true" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-border px-2 py-2">
        <NavLink
          to="/status"
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 rounded-[var(--radius-control)] px-2.5 py-1.5 text-xs text-foreground-subtle hover:text-foreground',
              isActive && 'text-foreground',
            )
          }
        >
          System status
        </NavLink>
      </div>
    </aside>
  )
}
