import { Link, useLocation } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import * as api from '../../api/auth.ts'
import type { ChangeResult, CodesResult, TotpState } from '../../api/auth.ts'
import { saveBlob } from '../../api/client.ts'
import { useAuth } from '../../auth/AuthContext.tsx'
import { confirmDialog } from '../../components/dialog.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { DeleteAccountSection, LoginSections, NameSection } from './ProfileCards.tsx'
import { LearningCard } from '../../learning/LearningCard.tsx'
import { LanguageCard } from '../../i18n/LanguageControls.tsx'
import { AppearanceCard } from './AppearanceCard.tsx'
import { HomeActionsCard } from './HomeActionsCard.tsx'
import { AppDevicesCard } from './AppDevicesCard.tsx'
import { McpConnectionsCard } from './McpConnectionsCard.tsx'
import { PasskeyCard } from './PasskeyCard.tsx'
import { RemoteLoginCard } from './RemoteLoginCard.tsx'
import { SignatureCard } from './SignatureCard.tsx'
import { t } from '../../i18n/index.ts'
import { Why } from '../../learning/Aids.tsx'
import { TodoPreferences } from '../../components/TodoPreferences.tsx'
import { StatusMessage, Loading } from '../../components/ui.tsx'
import { PersonalTodos } from '../../components/PersonalTodos.tsx'

// Mein Konto: persönliche Einstellungen, unabhängig von der gewählten Organisation.
// Aufgeteilt in Unterpunkte (accountNav.ts), die in der Seitenleiste stehen.

/** Mein Konto › Profil */
export function AccountPage() {
  return (
    <section>
      <h1>{t('Profil')}</h1>
      <div className="stack">
        <NameSection />
        <LanguageCard />
        <AppearanceCard />
        <HomeActionsCard />
        <LearningCard />
        <PersonalTodos />
      </div>
    </section>
  )
}

/** Mein Konto › Anmeldung & Sicherheit */
export function AccountLoginPage() {
  // „Jetzt einrichten“ im Hinweis springt zum Abschnitt, nicht an den Seitenanfang (VW-50)
  const { hash } = useLocation()
  useEffect(() => {
    if (!hash) return
    const target = document.getElementById(hash.slice(1))
    if (!target) return
    target.scrollIntoView({ block: 'start' })
    target.querySelector<HTMLElement>('h2')?.focus()
  }, [hash])
  return (
    <section>
      <h1>{t('Anmeldung & Sicherheit')}</h1>
      <div className="stack">
        <LoginSections />
        <PasskeyCard />
        <TwoFactorCard />
        <DeleteAccountSection />
      </div>
    </section>
  )
}

export function AccountNotificationsPage() {
  return (
    <section>
      <h1>{t('Benachrichtigungen')}</h1>
      <TodoPreferences />
    </section>
  )
}

/** Mein Konto › App & andere Instanzen */
export function AccountAppPage() {
  return (
    <section>
      <h1>{t('App & andere Instanzen')}</h1>
      <div className="stack">
        <AppDevicesCard />
        <RemoteLoginCard />
        <McpConnectionsCard />
      </div>
    </section>
  )
}

/** Mein Konto › Briefvorlage & Unterschrift */
export function AccountTemplatesPage() {
  return (
    <section>
      <h1>{t('Briefvorlage & Unterschrift')}</h1>
      <div className="stack">
        <div className="card">
          <h2>{t('Briefvorlage')}</h2>
          <p className="muted small">
            {t(
              'Als Vorstandsmitglied oder mit einer Rolle in einer Untereinheit erstellst du dir eine Word-Vorlage mit dem Briefbogen deiner Einheit, deiner Funktion und deinem Kontaktweg.',
            )}
          </p>
          <p>
            <Link to="/briefvorlage">{t('Briefvorlage erstellen')}</Link>
          </p>
        </div>
        <SignatureCard />
      </div>
    </section>
  )
}

function TwoFactorCard() {
  const [totp, setTotp] = useState<TotpState | null>(null)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Aktion, die nach erneuter Passwortbestätigung wiederholt wird, mit ihrem Abschluss
  const [pending, setPending] = useState<{
    action: () => Promise<ChangeResult>
    onSuccess: () => Promise<void>
  } | null>(null)
  const { setUser } = useAuth()
  const { refresh: refreshOrgs } = useOrg()
  const codeRef = useRef<HTMLInputElement>(null)
  const errorRef = useRef<HTMLParagraphElement>(null)
  const [copied, setCopied] = useState<'codes' | 'secret' | null>(null)

  const load = useCallback(async () => {
    setTotp(await api.getTotp())
  }, [])

  // Ladefehler ist kein „nicht eingerichtet“ (Audit 29.10. FE-F01)
  const [loadFailed, setLoadFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    api
      .getTotp()
      .then((state) => {
        if (!active) return
        setLoadFailed(false)
        setTotp(state)
      })
      .catch(() => active && setLoadFailed(true))
    return () => {
      active = false
    }
  }, [attempt])

  const [busy, setBusy] = useState(false)
  const [codesFailed, setCodesFailed] = useState(false)

  // Netzfehler sichtbar machen und danach den tatsächlichen Stand neu laden: Die Änderung
  // kann auf dem Server schon durch sein (Gesamtaudit 30.10., WEB-F01).
  async function run(action: () => Promise<ChangeResult>, onSuccess: () => Promise<void>) {
    setError(null)
    setMessage(null)
    setBusy(true)
    try {
      const result = await action()
      if (result.kind === 'reauthenticate') {
        setPending({ action, onSuccess })
      } else if (result.kind === 'error') {
        setError(result.message)
        // Meldung sichtbar und Fokus im Feld, das zu korrigieren ist (VW-51)
        requestAnimationFrame(() => {
          errorRef.current?.scrollIntoView({ block: 'center' })
          codeRef.current?.focus()
        })
      } else {
        await onSuccess()
      }
    } catch {
      setError(
        t('Keine Verbindung zum Server. Ob die Änderung angekommen ist, zeigt der Stand unten; ') +
          t('bitte prüfen und ggf. wiederholen.'),
      )
      setAttempt((n) => n + 1)
    } finally {
      setBusy(false)
    }
  }

  /** Codes anzeigen oder neu erzeugen; allauth verlangt dafür ggf. erst das Passwort. */
  function codes(fetchCodes: () => Promise<CodesResult>, done: string | null) {
    let found: string[] = []
    return run(
      async () => {
        const result = await fetchCodes()
        if (result.kind !== 'ok') return result
        found = result.codes
        return { kind: 'ok' }
      },
      async () => {
        setRecoveryCodes(found)
        setCodesFailed(false)
        setCopied(null)
        if (done) setMessage(done)
      },
    )
  }

  async function loadRecoveryCodes() {
    try {
      const result = await api.getRecoveryCodes()
      if (result.kind === 'ok') setRecoveryCodes(result.codes)
      setCodesFailed(result.kind === 'error')
    } catch {
      setCodesFailed(true)
    }
  }

  async function regenerate() {
    const yes = await confirmDialog({
      final: true,
      title: t('Neue Wiederherstellungscodes erzeugen?'),
      message: t('Die bisherigen Codes gelten danach nicht mehr.'),
      confirmLabel: t('Neue Codes erzeugen'),
    })
    if (yes)
      await codes(
        api.regenerateRecoveryCodes,
        t('Neue Wiederherstellungscodes erzeugt. Die alten gelten nicht mehr.'),
      )
  }

  async function copy(text: string, what: 'codes' | 'secret') {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(what)
    } catch {
      setError(t('Kopieren hat nicht geklappt. Bitte von Hand abschreiben.'))
    }
  }

  const afterActivate = async () => {
    setCode('')
    setPassword('')
    setMessage(t('Zwei-Faktor-Anmeldung ist aktiv.'))
    await loadRecoveryCodes()
    await load()
    // Der Hinweis „Zwei-Faktor-Anmeldung fehlt“ und die ruhenden Rechte hängen am Konto:
    // gleich neu laden, nicht erst beim nächsten Seitenwechsel (VW-52)
    try {
      const next = await api.getSession()
      if (next) setUser(next)
      await refreshOrgs()
    } catch {
      // der Stand kommt beim nächsten Laden
    }
  }
  const afterDeactivate = async () => {
    setRecoveryCodes([])
    setCodesFailed(false)
    setMessage(t('Zwei-Faktor-Anmeldung wurde ausgeschaltet.'))
    await load()
  }

  // Passwort und Code werden zusammen abgefragt: allauth verlangt für die
  // Aktivierung eine frische Passwortbestätigung, und ein einmal geprüfter
  // TOTP-Code lässt sich nicht noch einmal verwenden.
  function activate(e: FormEvent) {
    e.preventDefault()
    void run(async () => {
      const reauth = await api.reauthenticate(password)
      if (reauth.kind !== 'ok') return reauth
      return api.activateTotp(code.trim())
    }, afterActivate)
  }

  if (pending) {
    return (
      <ReauthCard
        onCancel={() => setPending(null)}
        onConfirmed={async () => {
          const { action, onSuccess } = pending
          setPending(null)
          await run(action, onSuccess)
        }}
      />
    )
  }

  return (
    <div className="card anchor-target" id="zwei-faktor">
      <h2 tabIndex={-1}>{t('Zwei-Faktor-Anmeldung')}</h2>
      <Why k="two_factor" />
      <StatusMessage message={message} />
      {error && totp?.active !== false && (
        <p className="alert alert-error" role="alert" ref={errorRef}>
          {error}
        </p>
      )}

      {totp === null && !loadFailed && <Loading />}
      {totp === null && loadFailed && (
        <div className="alert alert-error" role="alert">
          {t('Der Stand der Zwei-Faktor-Anmeldung konnte nicht geladen werden.')}{' '}
          <button type="button" className="button" onClick={() => setAttempt((n) => n + 1)}>
            {t('Erneut laden')}
          </button>
        </div>
      )}

      {totp?.active && (
        <>
          <p>
            {t(
              'Bei der Anmeldung wird zusätzlich ein Code aus deiner Authenticator-App abgefragt.',
            )}
          </p>
          {codesFailed && (
            <div className="alert alert-error" role="alert">
              {t('Die Wiederherstellungscodes konnten nicht geladen werden.')}{' '}
              <button type="button" className="button" onClick={() => void loadRecoveryCodes()}>
                {t('Codes erneut laden')}
              </button>
            </div>
          )}
          <div className="recovery-codes">
            <p>
              <strong>{t('Wiederherstellungscodes')}</strong>{' '}
              {t(
                '– sicher aufbewahren. Jeder Code funktioniert einmal, falls du dein Handy nicht zur Hand hast.',
              )}
            </p>
            {recoveryCodes.length > 0 && (
              <>
                <ul>
                  {recoveryCodes.map((c) => (
                    <li key={c}>
                      <code>{c}</code>
                    </li>
                  ))}
                </ul>
                <p className="muted small">
                  {t(
                    'Du kannst die Codes hier später wieder anzeigen. Bewahre sie trotzdem getrennt vom Handy auf.',
                  )}
                </p>
              </>
            )}
            <div className="button-row">
              {recoveryCodes.length > 0 ? (
                <>
                  <button
                    type="button"
                    className="button"
                    onClick={() => void copy(recoveryCodes.join('\n'), 'codes')}
                  >
                    {copied === 'codes' ? t('Kopiert') : t('Codes kopieren')}
                  </button>
                  <button
                    type="button"
                    className="button"
                    onClick={() =>
                      saveBlob(
                        new Blob([recoveryCodes.join('\r\n') + '\r\n'], { type: 'text/plain' }),
                        t('wiederherstellungscodes.txt'),
                      )
                    }
                  >
                    {t('Als Textdatei speichern')}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="button"
                  disabled={busy}
                  onClick={() => void codes(api.getRecoveryCodes, null)}
                >
                  {t('Wiederherstellungscodes anzeigen')}
                </button>
              )}
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() => void regenerate()}
              >
                {t('Neue Codes erzeugen')}
              </button>
            </div>
          </div>
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void run(api.deactivateTotp, afterDeactivate)}
          >
            {t('Ausschalten')}
          </button>
        </>
      )}

      {totp && !totp.active && (
        <form onSubmit={activate}>
          <p>
            {t(
              'Schütze dein Konto mit einem zweiten Faktor. Scanne den QR-Code mit einer Authenticator-App (z. B. FreeOTP, Aegis, Google Authenticator) und gib den angezeigten Code ein.',
            )}
          </p>
          <div className="totp-setup">
            <QRCodeSVG
              value={totp.totpUrl}
              size={168}
              marginSize={2}
              role="img"
              aria-label={t('QR-Code für die Authenticator-App')}
            />
            <div className="totp-manual">
              <p className="muted">
                {t('Manuell:')} <code>{totp.secret.replace(/(.{4})(?=.)/g, '$1 ')}</code>
              </p>
              <div className="button-row">
                {/* Am Handy lässt sich der QR-Code nicht scannen: Link öffnet die App (VW-49) */}
                <a className="button totp-open" href={totp.totpUrl}>
                  {t('In Authenticator-App öffnen')}
                </a>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void copy(totp.secret, 'secret')}
                >
                  {copied === 'secret' ? t('Kopiert') : t('Schlüssel kopieren')}
                </button>
              </div>
            </div>
          </div>
          <label className="field">
            <span>{t('Code aus der App')}</span>
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              ref={codeRef}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? 'zwei-faktor-fehler' : undefined}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <label className="field">
            <span>{t('Dein Passwort zur Bestätigung')}</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className="alert alert-error" role="alert" id="zwei-faktor-fehler" ref={errorRef}>
              {error}
            </p>
          )}
          <button type="submit" className="button button-primary" disabled={busy}>
            {t('Aktivieren')}
          </button>
        </form>
      )}
    </div>
  )
}

function ReauthCard({
  onConfirmed,
  onCancel,
}: {
  onConfirmed: () => Promise<void>
  onCancel: () => void
}) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const result = await api.reauthenticate(password)
      if (result.kind === 'ok') await onConfirmed()
      else if (result.kind === 'error') setError(result.message)
    } catch {
      setError(t('Keine Verbindung zum Server. Bitte erneut versuchen.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>{t('Passwort bestätigen')}</h2>
      <p className="muted">{t('Für diese Änderung brauchen wir noch einmal dein Passwort.')}</p>
      <label className="field">
        <span>{t('Passwort')}</span>
        <input
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {t('Bestätigen')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
