import { Activity, AudioLines, Bell, FolderKanban, ReceiptText } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { cn } from '../../lib/cn'
const PRIMARY = [
  { to: '/', label: 'Dashboard', icon: Activity },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/investigations', label: 'Investigations', icon: FolderKanban },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText },
]
const linkStyle = ({ isActive }: { isActive: boolean }) =>
  cn(
    'flex items-center gap-2.5 rounded-control px-2.5 py-2 text-sm font-medium text-foreground-muted hover:bg-neutral-100 dark:hover:bg-neutral-800',
    isActive && 'bg-neutral-100 text-foreground dark:bg-neutral-800',
  )
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { hasRole } = useAuth()
  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex h-12 items-center gap-2 border-b border-border px-4">
        <AudioLines className="h-4 w-4 text-accent" aria-hidden="true" />
        <span className="text-sm font-semibold">SentinelAI</span>
      </div>
      <nav aria-label="Primary navigation" onClick={onNavigate} className="space-y-0.5 px-2 py-3">
        {PRIMARY.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === '/'} className={linkStyle}>
            <item.icon className="h-4 w-4" aria-hidden="true" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <details className="mx-2 mt-4 text-xs text-foreground-muted">
        <summary className="cursor-pointer px-2.5 py-2">Advanced / Admin</summary>
        <nav aria-label="Advanced navigation" onClick={onNavigate}>
          <NavLink to="/accounts" className={linkStyle}>
            Accounts
          </NavLink>
          <NavLink to="/network" className={linkStyle}>
            Network explorer
          </NavLink>
          <NavLink to="/cases" className={linkStyle}>
            Case administration
          </NavLink>
          {hasRole('admin') && (
            <NavLink to="/audit-log" className={linkStyle}>
              Audit log
            </NavLink>
          )}
          <NavLink to="/status" className={linkStyle}>
            System status
          </NavLink>
        </nav>
      </details>
      <p className="mt-auto border-t border-border p-4 text-xs text-foreground-muted">
        Synthetic financial activity.
        <br />
        Human decisions, traceable evidence.
      </p>
    </aside>
  )
}
