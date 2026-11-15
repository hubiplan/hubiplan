// Verwaltung in der iPhone-App über den Browser freischalten (docs/app.md, devices/browser_unlock.py).
// Die App öffnet /app/freischalten#t=<Ticket> im eingebetteten Browser. Nach dem Anmelden
// zeigt die Seite das Gerät; erst „Freischalten“ bestätigt (mit frischem Passkey oder Code)
// und gibt die App über hubiplan://freischalten… zurück.
import { useEffect, useState } from 'react'
import { devicesApi } from '../api/devices.ts'
import { leaveTo } from '../api/peering.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePageTitle } from '../components/pageTitle.ts'
import { Alert } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'

function ticketFromHash(hash: string): string {
  return (
    hash
      .replace(/^#/, '')
      .split('&')
      .find((part) => part.startsWith('t='))
      ?.slice(2) ?? ''
  )
}

export function AppUnlockPage() {
  usePageTitle(t('Verwaltung in der App freischalten'))
  const { user } = useAuth()
  // Im Fragment, damit das Ticket in keinem Server-Protokoll landet
  const [ticket] = useState(() => ticketFromHash(window.location.hash))
  const [device, setDevice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    if (!ticket) {
      setError(t('Die Freischaltung ist abgelaufen. Bitte in der App noch einmal beginnen.'))
      return
    }
    devicesApi
      .browserUnlock(ticket, false)
      .then((res) => active && setDevice(res.device))
      .catch((e: unknown) => active && setError(errorMessage(e)))
    return () => {
      active = false
    }
  }, [ticket])

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      const res = await devicesApi.browserUnlock(ticket, true)
      if (res.redirect) leaveTo.go(res.redirect)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  return (
    <main className="login-page">
      <div className="card login-card">
        <div className="login-logo">
          <Logo />
        </div>
        <h1>{t('Verwaltung in der App freischalten')}</h1>
        {error && <Alert kind="error">{error}</Alert>}
        {device && (
          <>
            <p>
              {t('Gerät:')} <strong>{device}</strong>
            </p>
            <p>
              {t(
                'Schalte die Verwaltung nur frei, wenn du das gerade selbst in der HUBIplan-App auf diesem Gerät angestoßen hast. Die Freischaltung gilt 30 Tage.',
              )}
            </p>
            <p className="muted small">
              {t('Angemeldet als')} <strong>{user?.email}</strong>
            </p>
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() => void confirm()}
            >
              {t('Freischalten')}
            </button>
          </>
        )}
      </div>
    </main>
  )
}
