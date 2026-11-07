import { Component, type ReactNode } from 'react'
import { Button } from '../ui/button'

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    if (this.state.failed)
      return (
        <main className="mx-auto max-w-lg p-6" role="alert">
          <h1 className="text-lg font-semibold">The workspace could not be displayed</h1>
          <p className="my-3 text-sm text-foreground-muted">
            Reload to recover your session. If this continues, contact your administrator.
          </p>
          <Button onClick={() => window.location.reload()}>Reload workspace</Button>
        </main>
      )
    return this.props.children
  }
}
