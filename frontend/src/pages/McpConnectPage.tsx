// KI-Assistent mit dem HUBIplan-Konto verbinden (OAuth, docs/mcp.md Stufe 1a).
// Der Assistent schickt den Browser hierher; die Person sieht, wer anfragt und was er
// darf, wählt die Einheit und stimmt zu oder lehnt ab.
import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import { mcpApi } from '../api/mcp.ts'
import type { McpDenied, McpRequest } from '../api/mcp.ts'
import { leaveTo } from '../api/peering.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { Alert } from '../components/ui.tsx'
import { t } from '../i18n/index.ts'

export function McpConnectPage() {
  const { search } = useLocation()
  const { user } = useAuth()
  const params = useMemo(() => Object.fromEntries(new URLSearchParams(search).entries()), [search])
  const [info, setInfo] = useState<McpRequest | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [back, setBack] = useState('')
  const [unit, setUnit] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    mcpApi
      .describe(new URLSearchParams(params).toString())
      .then((data) => {
        if (!active) return
        setInfo(data)
        setUnit(data.units.length === 1 ? data.units[0].id : null)
      })
      .catch((e: unknown) => {
        if (!active) return
        const body = e instanceof ApiError ? (e.body as McpDenied | null) : null
        setBack(body?.redirect ?? '')
        setError(errorMessage(e))
      })
    return () => {
      active = false
    }
  }, [params])

  async function answer(allow: boolean) {
    setBusy(true)
    setError(null)
    try {
      const res =
        allow && unit !== null ? await mcpApi.allow(params, unit) : await mcpApi.deny(params)
      leaveTo.go(res.redirect)
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as McpDenied | null) : null
      setBack(body?.redirect ?? '')
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
        <h1>{t('KI-Assistent verbinden')}</h1>
        {error && <Alert kind="error">{error}</Alert>}
        {error && back && (
          <p>
            <a className="button" href={back}>
              {t('Zurück zum Assistenten')}
            </a>
          </p>
        )}
        {!info && !error && <p aria-live="polite">{t('Einen Moment …')}</p>}
        {info && (
          <>
            {/* Die Adresse entscheidet, wohin die Freigabe geht; den Namen wählt der Assistent
                selbst (Gesamtaudit 11.11., S-06). */}
            <p>
              {info.redirect_kind === 'rechner'
                ? t('Die Freigabe geht an ein Programm auf deinem Rechner:')
                : t('Die Freigabe geht an:')}{' '}
              <strong>{info.redirect_host}</strong>
            </p>
            <p className="muted small">
              {t('Der Assistent nennt sich „{name}“.', { name: info.client })}
            </p>
            {info.redirect_kind !== 'bekannt' && !info.connected_before && (
              <Alert kind={info.redirect_kind === 'rechner' ? 'info' : 'error'}>
                {info.redirect_kind === 'rechner'
                  ? t(
                      'Erlaube nur, wenn du die Verbindung gerade selbst in einem Programm auf diesem Rechner eingerichtet hast.',
                    )
                  : t(
                      'Diese Adresse gehört zu keinem bekannten KI-Assistenten. Erlaube nur, wenn du die Verbindung gerade selbst eingerichtet hast und die Adresse kennst. Kam der Link per Mail oder Nachricht, lehne ab.',
                    )}
              </Alert>
            )}
            <p className="muted small">
              {t('Angemeldet als')} <strong>{user?.email}</strong>
            </p>
            <h2>{t('Der Assistent darf')}</h2>
            <ul>
              {info.scopes.map((s) => (
                <li key={s.scope}>{s.label}</li>
              ))}
              <li>{t('die Hilfe von HUBIplan lesen')}</li>
            </ul>
            <p className="muted small">
              {t(
                'Nie mehr als du selbst. Veröffentlichen, Mitgliederdaten, Mails und Zahlungen gibt es über den Assistenten nicht. Was er schreibt, geht an den Anbieter des Assistenten; schreibe dort keine vertraulichen Daten hinein. Trennen kannst du die Verbindung jederzeit unter Mein Konto › App & andere Instanzen.',
              )}
            </p>
            {info.problem ? (
              <Alert kind="error">{info.problem}</Alert>
            ) : info.units.length === 0 ? (
              <Alert kind="info">
                {t(
                  'Für keine deiner Einheiten ist das möglich. Nötig sind das Modul „KI-Assistenten“ und in deiner Rolle das Zusatzrecht „KI-Assistenten verbinden“.',
                )}
              </Alert>
            ) : (
              <label className="field">
                <span>{t('Für welche Einheit?')}</span>
                <select
                  value={unit ?? ''}
                  onChange={(e) => setUnit(e.target.value ? Number(e.target.value) : null)}
                >
                  <option value="">{t('Bitte wählen')}</option>
                  {info.units.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <div className="button-row">
              {!info.problem && info.units.length > 0 && (
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy || unit === null}
                  onClick={() => void answer(true)}
                >
                  {t('Erlauben')}
                </button>
              )}
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() => void answer(false)}
              >
                {t('Ablehnen')}
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  )
}
