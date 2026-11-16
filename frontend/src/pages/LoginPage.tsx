import { LanguageSwitch } from '../i18n/LanguageControls.tsx'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import * as api from '../api/auth.ts'
import type { LoginResult } from '../api/auth.ts'
import { ApiError } from '../api/client.ts'
import { useAuth } from '../auth/AuthContext.tsx'
import { loginTarget, rememberedTarget } from '../auth/loginTarget.ts'
import { autofillSupported, cancelled, getPasskey, passkeysSupported } from '../auth/webauthn.ts'
import { Logo } from '../components/Logo.tsx'
import { PoweredBy } from '../components/PoweredBy.tsx'
import { RemoteLoginChoices } from './VerbundLoginPages.tsx'
import { t } from '../i18n/index.ts'

type Step = 'password' | 'mfa'

/** Die Instanz kennt die Anmeldung mit Passkey nicht (abgeschaltet). */
function passkeysDisabled(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

export function LoginPage() {
  const { user, setUser } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Nach der Anmeldung zur ursprünglich aufgerufenen Seite (sonst Startseite)
  const target = loginTarget(location.state)

  const [step, setStep] = useState<Step>('password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Zweiter Faktor auch mit Passkey möglich (allauth nennt dann „webauthn“)
  const [mfaPasskey, setMfaPasskey] = useState(false)
  // Das Konto hat Passkeys, aber keinen für diese Adresse: sagen, wofür sie gelten
  const [elsewhere, setElsewhere] = useState<string[] | null>(null)
  // Passkeys auf dieser Instanz abgeschaltet (HUBIPLAN_PASSKEYS=0): Knopf und Vorschlag weg
  const [passkeyOff, setPasskeyOff] = useState(false)
  const passkeys = passkeysSupported() && !passkeyOff
  // Zählt hoch, wenn der Vorschlag im E-Mail-Feld neu angeboten werden soll
  const [autofillRound, setAutofillRound] = useState(0)
  // Vorschlag gespeicherter Passkeys im E-Mail-Feld; wird abgebrochen, sobald die Person
  // selbst „Mit Passkey anmelden“ wählt oder die Seite verlässt
  const autofill = useRef<AbortController | null>(null)
  // Nach einem Fehler steht der Fokus im Feld, das zu korrigieren ist (UX-Audit 05.11. W-03)
  const emailRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)
  const codeRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (step !== 'password' || user || passkeyOff) return
    let active = true
    const controller = new AbortController()
    autofill.current = controller
    void (async () => {
      if (!(await autofillSupported()) || !active) return
      let credential: Record<string, unknown>
      try {
        credential = await getPasskey(await api.passkeyLoginOptions(), {
          conditional: true,
          signal: controller.signal,
        })
      } catch (e) {
        // Der Vorschlag ist nur ein Angebot: Abbruch, keine Verbindung, zu viele Anfragen
        // oder abgeschaltete Passkeys melden nichts, es geht still weiter mit Passwort
        if (active && passkeysDisabled(e)) setPasskeyOff(true)
        return
      }
      if (!active) return
      setBusy(true)
      try {
        const result = await api.passkeyLogin(credential)
        if (!active) return
        handle(result)
        // Abgelehnt (etwa weil die Seite lange offen stand): Vorschlag mit neuer Aufgabe
        // wieder anbieten, die alte gilt nur einmal
        if (result.kind === 'error') setAutofillRound((n) => n + 1)
      } catch {
        if (active) setError(t('Die Anmeldung mit Passkey hat nicht geklappt.'))
      } finally {
        setBusy(false)
      }
    })()
    return () => {
      active = false
      controller.abort()
      if (autofill.current === controller) autofill.current = null
    }
    // handle hängt nur von stabilen Werten ab; neu starten nur beim Wechsel des Schritts
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [step, user, passkeyOff, autofillRound])

  if (user) return <Navigate to={target} replace />

  function handle(result: LoginResult) {
    if (result.kind === 'ok') {
      setUser(result.user)
      rememberedTarget(true)
      navigate(target, { replace: true })
    } else if (result.kind === 'mfa') {
      setMfaPasskey(result.passkey && passkeys)
      setElsewhere(null)
      setStep('mfa')
      setError(null)
      // Nur ein Hinweis: Kommt keine Antwort, bleibt es beim Code
      if (!result.passkey)
        void api
          .passkeyElsewhere()
          .then((info) => setElsewhere(info.elsewhere ? info.hosts : null))
          .catch(() => undefined)
    } else {
      setError(result.message)
      focusAfterError()
    }
  }

  function focusAfterError(target?: HTMLInputElement | null) {
    // Erst nach dem Rendern der Meldung, damit aria-describedby schon stimmt
    setTimeout(() => {
      const field = target ?? (step === 'mfa' ? codeRef.current : passwordRef.current)
      field?.focus()
      field?.select()
    }, 0)
  }

  /** Eigene Meldung statt Browser-Hinweis in Browsersprache (W-18); leer = alles ausgefüllt. */
  function missing(): [string, HTMLInputElement | null] | null {
    if (step === 'mfa') return code.trim() ? null : [t('Bitte den Code eingeben.'), codeRef.current]
    if (!email.trim()) return [t('Bitte E-Mail-Adresse eingeben.'), emailRef.current]
    if (!password) return [t('Bitte Passwort eingeben.'), passwordRef.current]
    return null
  }

  async function submit(e: FormEvent, action: () => Promise<LoginResult>) {
    e.preventDefault()
    // Gesperrt wird über aria-disabled: ein echtes disabled nähme dem Knopf den Fokus
    if (busy) return
    const empty = missing()
    if (empty) {
      setError(empty[0])
      focusAfterError(empty[1])
      return
    }
    setBusy(true)
    setError(null)
    try {
      handle(await action())
    } catch {
      setError(t('Der Server ist nicht erreichbar.'))
      focusAfterError()
    } finally {
      setBusy(false)
    }
  }

  /** Browserabfrage für den Passkey; Abbrechen ist kein Fehler. */
  async function withPasskey(
    loadOptions: () => Promise<Record<string, unknown>>,
    finish: (credential: Record<string, unknown>) => Promise<LoginResult>,
  ) {
    if (busy) return
    autofill.current?.abort()
    setBusy(true)
    setError(null)
    try {
      const credential = await getPasskey(await loadOptions())
      handle(await finish(credential))
    } catch (e) {
      if (passkeysDisabled(e)) setPasskeyOff(true)
      if (e instanceof ApiError && e.status === 429)
        setError(t('Zu viele Versuche. Bitte später erneut.'))
      else if (!cancelled(e)) setError(t('Die Anmeldung mit Passkey hat nicht geklappt.'))
    } finally {
      setBusy(false)
      // Der Knopf hat den Vorschlag im E-Mail-Feld abgebrochen: wieder anbieten
      setAutofillRound((n) => n + 1)
    }
  }

  return (
    <main className="login-page">
      <div className="card login-card">
        <div className="login-logo">
          <Logo />
        </div>

        {step === 'password' ? (
          <form noValidate onSubmit={(e) => submit(e, () => api.login(email.trim(), password))}>
            <h1>{t('Anmelden')}</h1>
            <label className="field">
              <span>{t('E-Mail-Adresse')}</span>
              <input
                ref={emailRef}
                type="email"
                autoComplete={passkeys ? 'username webauthn' : 'username'}
                required
                aria-invalid={error && !email.trim() ? true : undefined}
                aria-describedby={error ? 'anmelden-fehler' : undefined}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('Passwort')}</span>
              <input
                ref={passwordRef}
                type="password"
                autoComplete="current-password"
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'anmelden-fehler' : undefined}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <p className="alert alert-error" role="alert" id="anmelden-fehler">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="button button-primary button-block"
              aria-disabled={busy || undefined}
            >
              {busy ? t('Anmelden …') : t('Anmelden')}
            </button>
            {passkeys && (
              <button
                type="button"
                className="button button-ghost button-block"
                aria-disabled={busy || undefined}
                onClick={() => void withPasskey(api.passkeyLoginOptions, api.passkeyLogin)}
              >
                {t('Mit Passkey anmelden')}
              </button>
            )}
            <p className="small">
              <Link to="/passwort-vergessen" state={location.state}>
                {t('Passwort vergessen?')}
              </Link>{' '}
              ·{' '}
              <Link to="/anmelden/link" state={location.state}>
                {t('Ohne Passwort per Link anmelden')}
              </Link>
            </p>
            <RemoteLoginChoices target={target} />
          </form>
        ) : (
          <form noValidate onSubmit={(e) => submit(e, () => api.authenticateMfa(code.trim()))}>
            <h1>{t('Bestätigungscode')}</h1>
            <p className="muted">
              {mfaPasskey
                ? t(
                    'Bestätige mit deinem Passkey – oder gib einen Code aus deiner Authenticator-App bzw. einen Wiederherstellungscode ein.',
                  )
                : t(
                    'Gib den 6-stelligen Code aus deiner Authenticator-App ein – oder einen deiner Wiederherstellungscodes.',
                  )}
            </p>
            {elsewhere && (
              <p className="muted small">
                {elsewhere.length === 1
                  ? t(
                      'Dein Passkey gilt für {host}, nicht für diese Adresse. Hier geht es mit dem Code weiter.',
                      { host: elsewhere[0] },
                    )
                  : t(
                      'Dein Passkey gilt für eine andere Adresse, nicht für diese. Hier geht es mit dem Code weiter.',
                    )}
              </p>
            )}
            {mfaPasskey && (
              <button
                type="button"
                className="button button-primary button-block"
                aria-disabled={busy || undefined}
                onClick={() => void withPasskey(api.passkeyMfaOptions, api.passkeyMfa)}
              >
                {t('Mit Passkey bestätigen')}
              </button>
            )}
            <label className="field">
              <span>{t('Code')}</span>
              <input
                ref={codeRef}
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus={!mfaPasskey}
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? 'anmelden-fehler' : undefined}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </label>
            {error && (
              <p className="alert alert-error" role="alert" id="anmelden-fehler">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="button button-primary button-block"
              aria-disabled={busy || undefined}
            >
              {busy ? t('Prüfe …') : t('Bestätigen')}
            </button>
            <button
              type="button"
              className="button button-ghost button-block"
              onClick={() => {
                setStep('password')
                setCode('')
                setError(null)
              }}
            >
              {t('Zurück')}
            </button>
          </form>
        )}
      </div>
      <LanguageSwitch />
      <PoweredBy />
    </main>
  )
}
