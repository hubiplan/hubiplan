// HUBIplan-App auf dem iPhone mit Passkey verbinden (docs/app.md, „Anmelden im Browser“).
// Die iOS-App öffnet diese Seite in einem eingebetteten Browserfenster (ASWebAuthenticationSession):
// Dort meldet sich die Person an, auf Wunsch mit Passkey, der im Browser für jede Adresse gilt.
// Erst ein Tippen auf „Verbinden“ erzeugt den Einmalcode und gibt ihn über hubiplan://… an
// die App zurück; nichts geschieht von selbst.
import { useState } from 'react'
import { devicesApi } from '../api/devices.ts'
import { leaveTo } from '../api/peering.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { appPairLink } from '../components/appLink.ts'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePageTitle } from '../components/pageTitle.ts'
import { Alert } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'

/** Adresse dieser Seite (in Tests ersetzbar). */
export const here = {
  origin: () => window.location.origin,
}

export function AppLoginPage() {
  usePageTitle(t('App verbinden'))
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      const pairing = await devicesApi.pairingCode()
      // Mit der Adresse, die die App geöffnet hat (bei mehreren Adressen je Instanz zählt sie)
      const code = new URL(pairing.url).hash
      const link = appPairLink(`${here.origin()}/app/verbinden${code}`)
      if (!link) throw new Error(t('Der Code zum Verbinden ließ sich nicht erzeugen.'))
      leaveTo.go(link)
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
        <h1>{t('App verbinden')}</h1>
        {error && <Alert kind="error">{error}</Alert>}
        <p>
          {t(
            'Verbinde die HUBIplan-App nur, wenn du sie gerade selbst auf deinem Telefon geöffnet hast.',
          )}
        </p>
        <p className="muted small">
          {t('Angemeldet als')} <strong>{user?.email}</strong>
        </p>
        <button
          type="button"
          className="button button-primary"
          disabled={busy}
          onClick={() => void connect()}
        >
          {t('Verbinden')}
        </button>
      </div>
    </main>
  )
}
