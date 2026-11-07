import { Suspense, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { Sidebar } from './Sidebar'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '../ui/dialog'
import { SyntheticDataBanner } from '../data/SyntheticDataBanner'

export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <div className="flex h-dvh bg-background">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:bg-surface focus:p-3"
      >
        Skip to content
      </a>
      <div className="hidden lg:block">
        <Sidebar />
      </div>
      <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
        <DialogContent className="left-0 top-0 h-dvh max-h-dvh w-64 translate-x-0 translate-y-0 rounded-none p-0">
          <DialogTitle className="sr-only">Navigation</DialogTitle>
          <DialogDescription className="sr-only">Choose a SentinelAI workspace.</DialogDescription>
          <Sidebar onNavigate={() => setMenuOpen(false)} />
        </DialogContent>
      </Dialog>
      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenu={() => setMenuOpen(true)} />
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1440px] p-4 sm:p-6">
            <SyntheticDataBanner className="mb-5" />
            <Suspense
              fallback={
                <p role="status" className="text-sm text-foreground-muted">
                  Loading workspace…
                </p>
              }
            >
              <Outlet />
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  )
}
