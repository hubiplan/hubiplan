// Mein Konto › Anmeldung & Sicherheit: Passkeys einrichten, umbenennen, entfernen
// (konzepte/passkey-anmeldung.md, Stufe P1). Ein Passkey gilt für genau eine Adresse.
import { useCallback, useEffect, useState } from 'react'
import * as api from '../../api/auth.ts'
import type { ChangeResult, PasskeyList } from '../../api/auth.ts'
import { cancelled, createPasskey, getPasskey, passkeysSupported } from '../../auth/webauthn.ts'
import { choiceDialog, confirmDialog, promptDialog } from '../../components/dialog.ts'
import { Loading, StatusMessage } from '../../components/ui.tsx'
import { formatDay } from '../../i18n/format.ts'
import { t } from '../../i18n/index.ts'

export function PasskeyCard() {
  const [list, setList] = useState<PasskeyList | null>(null)
  const [loadFailed, setLoadFailed] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])

  const load = useCallback(async () => {
    try {
      setList(await api.listPasskeys())
      setLoadFailed(false)
    } catch {
      setLoadFailed(true)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  /** allauth will vor Sicherheitsänderungen eine frische Bestätigung. */
  async function reauthenticate(): Promise<boolean> {
    const here = list?.passkeys.some((p) => p.here) && passkeysSupported()
    if (here) {
      const choice = await choiceDialog({
        title: t('Bestätigen'),
        message: t('Für diese Änderung bestätige bitte noch einmal, dass du es bist.'),
        choices: [
          { value: 'passkey', label: t('Mit Passkey bestätigen'), primary: true },
          { value: 'password', label: t('Mit Passwort') },
          { value: 'cancel', label: t('Abbrechen') },
        ],
        cancelValue: 'cancel',
      })
      if (choice === 'cancel') return false
      if (choice === 'passkey') {
        try {
          const result = await api.passkeyReauth(await getPasskey(await api.passkeyReauthOptions()))
          if (result.kind === 'ok') return true
          setError(result.kind === 'error' ? result.message : null)
        } catch (e) {
          if (!cancelled(e)) setError(t('Die Bestätigung mit Passkey hat nicht geklappt.'))
        }
        return false
      }
    }
    let hint = ''
    for (;;) {
      const intro = t('Für diese Änderung brauchen wir noch einmal dein Passwort.')
      const password = await promptDialog({
        title: t('Passwort bestätigen'),
        message: hint ? `${hint} ${intro}` : intro,
        label: t('Passwort'),
        confirmLabel: t('Bestätigen'),
        danger: false,
        inputType: 'password',
        autoComplete: 'current-password',
      })
      if (password === null) return false
      if (!password) continue
      const result = await api.reauthenticate(password)
      if (result.kind === 'ok') return true
      hint = result.kind === 'error' ? result.message : ''
    }
  }

  /** Änderung ausführen; verlangt allauth eine Bestätigung, danach einmal wiederholen. */
  async function change(action: () => Promise<ChangeResult>): Promise<boolean> {
    let result = await action()
    if (result.kind === 'reauthenticate') {
      if (!(await reauthenticate())) return false
      result = await action()
    }
    if (result.kind === 'error') setError(result.message)
    return result.kind === 'ok'
  }

  async function run(work: () => Promise<void>) {
    if (busy) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await work()
    } catch (e) {
      if (!cancelled(e))
        setError(t('Keine Verbindung zum Server. Bitte prüfen und ggf. wiederholen.'))
    } finally {
      setBusy(false)
      await load()
    }
  }

  function add() {
    void run(async () => {
      let start = await api.passkeyCreationOptions()
      if (start.kind === 'reauthenticate') {
        if (!(await reauthenticate())) return
        start = await api.passkeyCreationOptions()
      }
      if (start.kind !== 'ok') {
        if (start.kind === 'error') setError(start.message)
        return
      }
      const credential = await createPasskey(start.options)
      const result = await api.addPasskey(name.trim(), credential)
      if (result.kind === 'reauthenticate') {
        setError(t('Die Bestätigung ist abgelaufen. Bitte noch einmal versuchen.'))
        return
      }
      if (result.kind === 'error') {
        setError(result.message)
        return
      }
      setName('')
      setMessage(t('Der Passkey ist eingerichtet. Du kannst dich jetzt damit anmelden.'))
      if (result.recoveryCodes) setRecoveryCodes(await api.getRecoveryCodes())
    })
  }

  function rename(id: number, current: string) {
    void run(async () => {
      const value = await promptDialog({
        title: t('Passkey umbenennen'),
        label: t('Name'),
        defaultValue: current,
        confirmLabel: t('Speichern'),
        danger: false,
      })
      if (value === null || !value.trim() || value.trim() === current) return
      if (await change(() => api.renamePasskey(id, value.trim())))
        setMessage(t('Der Passkey wurde umbenannt.'))
    })
  }

  function remove(id: number, label: string) {
    void run(async () => {
      const ok = await confirmDialog({
        title: t('Passkey entfernen?'),
        message: t(
          '„{name}“ kann danach nicht mehr zum Anmelden benutzt werden. Lösche den Passkey zusätzlich auf deinem Gerät oder im Passwortmanager.',
          { name: label },
        ),
        confirmLabel: t('Entfernen'),
      })
      if (!ok) return
      if (await change(() => api.deletePasskey(id))) setMessage(t('Der Passkey wurde entfernt.'))
    })
  }

  if (list && !list.enabled) return null

  return (
    <div className="card">
      <h2>{t('Passkeys')}</h2>
      <p className="muted">
        {t(
          'Mit einem Passkey meldest du dich per Fingerabdruck, Gesicht oder Geräte-PIN an, ohne Passwort und ohne Code. Er zählt als Zwei-Faktor-Anmeldung. Ein Passkey gilt nur für die Adresse, unter der du ihn einrichtest.',
        )}
      </p>
      <StatusMessage message={message} />
      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
      {recoveryCodes.length > 0 && (
        <div className="recovery-codes">
          <p>
            <strong>{t('Wiederherstellungscodes')}</strong>{' '}
            {t(
              '– sicher aufbewahren. Jeder Code funktioniert einmal, falls du deinen Passkey nicht zur Hand hast.',
            )}
          </p>
          <ul>
            {recoveryCodes.map((c) => (
              <li key={c}>
                <code>{c}</code>
              </li>
            ))}
          </ul>
        </div>
      )}

      {list === null && !loadFailed && <Loading />}
      {list === null && loadFailed && (
        <div className="alert alert-error" role="alert">
          {t('Die Passkeys konnten nicht geladen werden.')}{' '}
          <button type="button" className="button" onClick={() => void load()}>
            {t('Erneut laden')}
          </button>
        </div>
      )}

      {list && list.passkeys.length === 0 && (
        <p className="muted">{t('Noch kein Passkey eingerichtet.')}</p>
      )}
      {list && list.passkeys.length > 0 && (
        <ul className="item-list">
          {list.passkeys.map((p) => (
            <li key={p.id} className="item-row">
              <div className="item-row-info">
                <span>
                  <strong>{p.name}</strong>{' '}
                  <span className="muted small">
                    {p.here
                      ? t('gilt für diese Adresse')
                      : p.host
                        ? t('gilt für {host}', { host: p.host })
                        : t('gilt für eine andere Adresse')}
                  </span>
                </span>
                <span className="small muted">
                  {t('eingerichtet am {day}', { day: formatDay(p.created_at) })}
                  {p.last_used_at &&
                    ` · ${t('zuletzt benutzt am {day}', { day: formatDay(p.last_used_at) })}`}
                </span>
              </div>
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => rename(p.id, p.name)}
                >
                  {t('Umbenennen')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => remove(p.id, p.name)}
                >
                  {t('Entfernen')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {list &&
        (passkeysSupported() ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              add()
            }}
          >
            <label className="field">
              <span>{t('Name (optional, z. B. „Handy“ oder „Laptop“)')}</span>
              <input value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
            </label>
            <button type="submit" className="button button-primary" disabled={busy}>
              {t('Passkey hinzufügen')}
            </button>
          </form>
        ) : (
          <p className="muted small">
            {t('Dieser Browser kann keine Passkeys verwenden. Melde dich wie gewohnt an.')}
          </p>
        ))}
    </div>
  )
}
