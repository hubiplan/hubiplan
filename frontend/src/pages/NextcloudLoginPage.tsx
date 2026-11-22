// Bei der Nextcloud des Vereins mit dem HUBIplan-Konto anmelden (OpenID Connect).
// Die Nextcloud schickt den Browser hierher; ist man angemeldet und darf hinein, geht es
// ohne Rückfrage mit einem Einmal-Code zurück. Hat man sich vorher von dieser Nextcloud
// abgemeldet (oder verlangt sie es), geht es erst nach einem Klick weiter.
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { oidcApi } from '../api/nextcloud.ts'
import type { NextcloudDenied } from '../api/nextcloud.ts'
import { leaveTo } from '../api/peering.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { Alert } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'

export function NextcloudLoginPage() {
  const { search } = useLocation()
  const { user } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [back, setBack] = useState('')
  const [confirm, setConfirm] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const started = useRef(false)

  const run = useCallback(
    (confirmed: boolean) => {
      const params = Object.fromEntries(new URLSearchParams(search).entries())
      delete params.confirm
      if (confirmed) params.confirm = '1'
      setBusy(true)
      oidcApi
        .authorize(params)
        .then((res) => leaveTo.go(res.redirect))
        .catch((e: unknown) => {
          setBusy(false)
          const body = e instanceof ApiError ? (e.body as NextcloudDenied | null) : null
          if (body?.confirm) {
            setConfirm(body.name ?? '')
            return
          }
          // Fehler im Aufruf selbst meldet die Nextcloud (eingetragene Rückleitung)
          if (body?.redirect) {
            leaveTo.go(body.redirect)
            return
          }
          setConfirm(null)
          setBack(body?.back ?? '')
          setError(errorMessage(e))
        })
    },
    [search],
  )

  useEffect(() => {
    if (started.current) return
    started.current = true
    run(false)
  }, [run])

  return (
    <main className="login-page">
      <div className="card login-card">
        <div className="login-logo">
          <Logo />
        </div>
        <h1>{t('Bei der Nextcloud anmelden')}</h1>
        {error ? (
          <>
            <Alert kind="error">{error}</Alert>
            <p className="muted small">
              {t('Angemeldet bei HUBIplan als')} <strong>{user?.email}</strong>
            </p>
            {back && (
              <p>
                <a className="button" href={back}>
                  {t('Zurück zur Nextcloud')}
                </a>
              </p>
            )}
          </>
        ) : confirm !== null ? (
          <>
            <p>
              {t('Du hast dich von „{name}“ abgemeldet. Möchtest du dich wieder anmelden?', {
                name: confirm || 'Nextcloud',
              })}
            </p>
            <p className="muted small">
              {t('Angemeldet bei HUBIplan als')} <strong>{user?.email}</strong>
            </p>
            <p className="actions">
              <button
                type="button"
                className="button button-primary"
                disabled={busy}
                onClick={() => run(true)}
              >
                {t('Bei der Nextcloud anmelden')}
              </button>
              <Link className="button button-ghost" to="/">
                {t('Zur Startseite')}
              </Link>
            </p>
          </>
        ) : (
          <p aria-live="polite">{t('Einen Moment, du wirst angemeldet …')}</p>
        )}
      </div>
    </main>
  )
}
