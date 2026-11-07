import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Button } from '../ui/button'

type Theme = 'light' | 'dark'

function systemPrefersDark(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem('sentinelai-theme')
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* localStorage unavailable */
  }
  return systemPrefersDark() ? 'dark' : 'light'
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readStoredTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('sentinelai-theme', theme)
    } catch {
      /* per-viewer convenience only; safe to drop if storage is unavailable */
    }
  }, [theme])

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  )
}
