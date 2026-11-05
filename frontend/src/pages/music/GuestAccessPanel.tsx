import { useState } from 'react'
import { api, newRequestKey } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { Alert } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

type Access = {
  active: boolean
  has_email: boolean
  expires_at?: string
  auto_notify?: boolean
  url?: string
  sent?: boolean
}

export function GuestAccessPanel({
  assignment,
  name,
  onClose,
}: {
  assignment: number
  name: string
  onClose: () => void
}) {
  const org = useActiveOrg()
  const url = `/api/orgs/${org.id}/music/assignments/${assignment}/guest-access/`
  const load = useLoad(() => api.get<Access>(url), [org.id, assignment])
  const [value, setValue] = useState<Access | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [keys] = useState(() => new Map<string, string>())
  const data = value || load.data
  async function act(action: string) {
    if (
      (action === 'revoke' || action === 'rotate') &&
      !(await confirmDialog(
        action === 'revoke'
          ? t('Diesen Einladungslink widerrufen?')
          : t('Ein neuer Link macht den bisherigen Link ungültig. Fortfahren?'),
      ))
    )
      return
    setBusy(true)
    setError('')
    setMessage('')
    if (!keys.has(action)) keys.set(action, newRequestKey())
    try {
      const next = await api.post<Access>(url, { action }, keys.get(action))
      setValue(next)
      keys.delete(action)
      if (action === 'send') {
        if (next.sent) setMessage(t('Die Gasteinladung wurde an die Ausgangspost übergeben.'))
        else setError(t('Der Versand ist fehlgeschlagen. Ein erneuter Versuch ist möglich.'))
      } else if (action === 'revoke') setMessage(t('Der Einladungslink wurde widerrufen.'))
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack music-record">
      <h2>{t('Gasteinladung für {name}', { name })}</h2>
      <p>
        {t(
          'Der persönliche Link gibt nur diese Auftrittseinteilung frei. Bitte vertraulich weitergeben.',
        )}
      </p>
      {(error || load.error) && <Alert kind="error">{error || load.error}</Alert>}
      {message && <Alert kind="success">{message}</Alert>}
      {data && (
        <>
          {data.active && data.url && (
            <>
              <label>
                {t('Persönlicher Einladungslink')}
                <input readOnly value={data.url} onFocus={(e) => e.target.select()} />
              </label>
              <p>
                {t('Gültig bis')}: {data.expires_at ? formatDateTime(data.expires_at) : '—'}
              </p>
              <button
                type="button"
                className="button button-ghost"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(data.url!)
                    setMessage(t('Link kopiert.'))
                  } catch {
                    setError(t('Bitte den angezeigten Link markieren und kopieren.'))
                  }
                }}
              >
                {t('Link kopieren')}
              </button>
            </>
          )}
          {!data.has_email && (
            <p className="muted">
              {t('Zum Versand die E-Mail-Adresse für Gasteinladungen beim Musiker hinterlegen.')}
            </p>
          )}
          <div className="music-actions">
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => void act(data.active ? 'rotate' : 'create')}
            >
              {data.active ? t('Neuen Einladungslink erstellen') : t('Einladungslink erstellen')}
            </button>
            <button
              className="button button-ghost"
              disabled={busy || !data.has_email}
              onClick={() => void act('send')}
            >
              {t('Gasteinladung senden')}
            </button>
            {data.active && (
              <button
                className="button button-ghost"
                disabled={busy}
                onClick={() => void act('revoke')}
              >
                {t('Einladungslink widerrufen')}
              </button>
            )}
            <button className="button button-ghost" disabled={busy} onClick={onClose}>
              {t('Schließen')}
            </button>
          </div>
          {data.auto_notify && data.active && (
            <p className="muted">
              {t('Änderungshinweise und Erinnerungen werden auch an diesen Gast gesendet.')}
            </p>
          )}
        </>
      )}
    </section>
  )
}
