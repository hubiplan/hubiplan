import { useState } from 'react'
import { heldApi } from '../../api/website.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, LoadError } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function HeldCard() {
  const org = useActiveOrg()
  const { data, error, reload } = useLoad(() => heldApi.list(org.id), [org.id])
  const [message, setMessage] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setMessage(null)
    try {
      await action()
      void reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Zurückgehaltene Nachrichten')}</h2>
      <p className="muted small">
        {t(
          'Nachrichten aus dem Kontaktformular, die nach Spam aussehen oder über der Obergrenze je Stunde lagen. Sie werden nach 7 Tagen automatisch gelöscht.',
        )}
      </p>
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {data && data.length === 0 && <p className="muted">{t('Keine.')}</p>}
      <ul className="plain-list">
        {(data ?? []).map((m) => (
          <li key={m.id}>
            <strong>{m.subject}</strong>{' '}
            {t('· von {sender_name} ({sender_email}) an  {recipient_name} ·', {
              sender_name: m.sender_name,
              sender_email: m.sender_email,
              recipient_name: m.recipient_name,
            })}{' '}
            {formatDateTime(m.created_at)}
            <br />
            <small className="muted">
              {t('Grund:')} {m.reason}
            </small>
            <p className="mail-body">{m.body}</p>
            <div className="button-row">
              <button
                type="button"
                className="button"
                onClick={() => void run(() => heldApi.release(org.id, m.id))}
              >
                {t('Zustellen')}
              </button>
              <button
                type="button"
                className="button button-ghost"
                onClick={() => void run(() => heldApi.discard(org.id, m.id))}
              >
                {t('Verwerfen')}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {message && <Alert kind="error">{message}</Alert>}
    </div>
  )
}
