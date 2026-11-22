// Von der Nextcloud abgemeldet (OpenID Connect RP-Initiated Logout).
// Die Nextcloud schickt den Browser nach dem Abmelden hierher. HUBIplan merkt sich die
// Abmeldung (die nächste Anmeldung bei dieser Nextcloud geht dann erst nach einem Klick)
// und fragt, ob man sich auch bei HUBIplan abmelden möchte.
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { oidcApi } from '../api/nextcloud.ts'
import type { NextcloudLoggedOut } from '../api/nextcloud.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { Alert } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'

export function NextcloudLogoutPage() {
  const { search } = useLocation()
  const { user, loading, logout } = useAuth()
  const [answer, setAnswer] = useState<NextcloudLoggedOut | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const started = useRef(false)

  useEffect(() => {
    // Erst wenn klar ist, ob man bei HUBIplan angemeldet ist (Sitzung, CSRF)
    if (loading || started.current) return
    started.current = true
    const params = Object.fromEntries(new URLSearchParams(search).entries())
    oidcApi
      .endSession(params)
      .then(setAnswer)
      .catch((e: unknown) => setError(errorMessage(e)))
  }, [search, loading])

  async function logoutHere() {
    setBusy(true)
    setError(null)
    try {
      if (await logout()) setDone(true)
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  const name = answer?.name || 'Nextcloud'
  const stillIn = Boolean(user) && !done

  return (
    <main className="login-page">
      <div className="card login-card">
        <div className="login-logo">
          <Logo />
        </div>
        <h1>{t('Von der Nextcloud abgemeldet')}</h1>
        {error && <Alert kind="error">{error}</Alert>}
        {!answer && !error ? (
          <p aria-live="polite">{t('Einen Moment …')}</p>
        ) : (
          <>
            <p>{t('Du hast dich von „{name}“ abgemeldet.', { name })}</p>
            {stillIn ? (
              <>
                <p>
                  {t('Bei HUBIplan bist du weiter angemeldet als')} <strong>{user?.email}</strong>.{' '}
                  {t(
                    'Die Nextcloud meldet dich erst wieder an, wenn du es dort ausdrücklich bestätigst.',
                  )}
                </p>
                <p className="actions">
                  <button
                    type="button"
                    className="button button-primary"
                    disabled={busy}
                    onClick={() => void logoutHere()}
                  >
                    {t('Auch bei HUBIplan abmelden')}
                  </button>
                  <a className="button button-ghost" href="/">
                    {t('Bei HUBIplan angemeldet bleiben')}
                  </a>
                </p>
              </>
            ) : (
              <p aria-live="polite">
                {done ? t('Du bist jetzt auch bei HUBIplan abgemeldet.') : null}
              </p>
            )}
            {answer?.back && (
              <p>
                <a className={stillIn ? 'small' : 'button'} href={answer.back}>
                  {t('Zurück zur Nextcloud')}
                </a>
              </p>
            )}
          </>
        )}
      </div>
    </main>
  )
}
