import React from 'react'
import ReactDOM from 'react-dom/client'

import { AppErrorBoundary } from './components/layout/AppErrorBoundary'
import App from './App'
import { BrowserRouter } from 'react-router-dom'
import { AppProviders } from './providers'
import './index.css'

const rootElement = document.getElementById('root')
if (!rootElement) {
  throw new Error('Root element "#root" not found in index.html')
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <BrowserRouter>
        <AppProviders>
          <App />
        </AppProviders>
      </BrowserRouter>
    </AppErrorBoundary>
  </React.StrictMode>,
)
