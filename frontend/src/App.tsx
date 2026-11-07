import { lazy, Suspense } from 'react'
import { Route, Routes, Link } from 'react-router-dom'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { AppShell } from './components/layout/AppShell'
import { LoginPage } from './features/auth/LoginPage'
import { Skeleton } from './components/ui/skeleton'

const OverviewPage = lazy(() =>
  import('./features/overview/OverviewPage').then((m) => ({ default: m.OverviewPage })),
)
const AlertsListPage = lazy(() =>
  import('./features/alerts/AlertsListPage').then((m) => ({ default: m.AlertsListPage })),
)
const AlertDetailPage = lazy(() =>
  import('./features/alerts/AlertDetailPage').then((m) => ({ default: m.AlertDetailPage })),
)
const TransactionsPage = lazy(() =>
  import('./features/transactions/TransactionsPage').then((m) => ({ default: m.TransactionsPage })),
)
const CasesListPage = lazy(() =>
  import('./features/cases/CasesListPage').then((m) => ({ default: m.CasesListPage })),
)
const CaseDetailPage = lazy(() =>
  import('./features/cases/CaseDetailPage').then((m) => ({ default: m.CaseDetailPage })),
)
const AccountsPage = lazy(() =>
  import('./features/accounts/AccountsPage').then((m) => ({ default: m.AccountsPage })),
)
const AccountDetailPage = lazy(() =>
  import('./features/accounts/AccountsPage').then((m) => ({ default: m.AccountDetailPage })),
)
const NetworkPage = lazy(() =>
  import('./features/network/NetworkPage').then((m) => ({ default: m.NetworkPage })),
)
const InvestigationsPage = lazy(() =>
  import('./features/workspace/InvestigationsPage').then((m) => ({
    default: m.InvestigationsPage,
  })),
)
const InvestigationDetailPage = lazy(() =>
  import('./features/investigations/InvestigationDetailPage').then((m) => ({
    default: m.InvestigationDetailPage,
  })),
)
const AuditPage = lazy(() =>
  import('./features/audit/AuditPage').then((m) => ({ default: m.AuditPage })),
)
const ConnectivityPage = lazy(() =>
  import('./pages/ConnectivityPage').then((m) => ({ default: m.ConnectivityPage })),
)

export default function App() {
  return (
    <Suspense
      fallback={
        <div role="status" className="p-6">
          <p className="mb-3 text-sm text-foreground-muted">Loading workspace…</p>
          <Skeleton className="h-48 w-full" />
        </div>
      }
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="alerts" element={<AlertsListPage />} />
            <Route path="alerts/:alertId" element={<AlertDetailPage />} />
            <Route path="transactions" element={<TransactionsPage />} />
            <Route path="transactions/:transactionId" element={<TransactionsPage />} />
            <Route path="cases" element={<CasesListPage />} />
            <Route path="cases/:caseId" element={<CaseDetailPage />} />
            <Route path="accounts" element={<AccountsPage />} />
            <Route path="accounts/:accountId" element={<AccountDetailPage />} />
            <Route path="network" element={<NetworkPage />} />
            <Route path="investigations" element={<InvestigationsPage />} />
            <Route path="investigations/:runId" element={<InvestigationDetailPage />} />
            <Route path="audit-log" element={<AuditPage />} />
            <Route path="status" element={<ConnectivityPage />} />
            <Route
              path="*"
              element={
                <div>
                  <h1 className="text-lg font-semibold">Page not found</h1>
                  <Link to="/" className="text-accent">
                    Return to overview
                  </Link>
                </div>
              }
            />
          </Route>
        </Route>
      </Routes>
    </Suspense>
  )
}
