// Kündigung der eigenen Mitgliedschaft im Mitgliederbereich (unter „Meine Daten“).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { portalApi } from '../../api/portal.ts'
import type { Cancellation, CancellationInfo } from '../../api/portal.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'

export function PortalCancellation({
  accessId,
  info,
  onChanged,
}: {
  accessId: number
  info: CancellationInfo
  onChanged: () => Promise<void> | void
}) {
  const tm = useTerms()
  const [open, setOpen] = useState(false)
  const [exitDate, setExitDate] = useState(info.earliest_date ?? '')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const pending = info.requests.find((c) => c.status === 'pending')

  if (!info.enabled && info.requests.length === 0) return null

  async function send(e: FormEvent) {
    e.preventDefault()
    const ok = await confirmDialog({
      title: t('Mitgliedschaft wirklich kündigen?'),
      message: t('Du trittst zum {date} aus. {e_Nom} bestätigt die Kündigung per Mail.', {
        date: formatDate(exitDate),
        e_Nom: tm.e_Nom,
      }),
      confirmLabel: t('Kündigung absenden'),
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await portalApi.cancel(accessId, {
        exit_date: exitDate || undefined,
        message,
      })
      setOpen(false)
      setNotice(t('Kündigung gesendet. Du bekommst eine Eingangsbestätigung per Mail.'))
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function withdraw(c: Cancellation) {
    const ok = await confirmDialog({
      title: t('Kündigung zurücknehmen?'),
      message: t('Deine Mitgliedschaft läuft dann weiter.'),
      confirmLabel: t('Zurücknehmen'),
      danger: false,
    })
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await portalApi.withdrawCancellation(accessId, c.id)
      setNotice(t('Kündigung zurückgenommen.'))
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>{t('Mitgliedschaft kündigen')}</h2>
        {info.possible && !open && (
          <button
            type="button"
            className="button button-ghost push-right"
            onClick={() => {
              setNotice(null)
              setOpen(true)
            }}
          >
            {t('Kündigen')}
          </button>
        )}
      </div>
      {info.planned_exit && !pending && (
        <p>
          {t('Dein Austritt ist zum {date} eingetragen.', { date: formatDate(info.planned_exit) })}
        </p>
      )}
      {info.possible && !open && info.earliest_date && (
        <p className="muted small">
          {t('Kündigen ist {rule} möglich, heute also frühestens zum {date}.', {
            rule: info.rule,
            date: formatDate(info.earliest_date),
          })}
        </p>
      )}
      {pending && (
        <Alert kind="info">
          {t('Deine Kündigung zum {date} vom {sent} wartet auf {e_akk}.', {
            date: formatDate(pending.exit_date),
            sent: formatDateTime(pending.created_at),
            e_akk: tm.e_akk,
          })}{' '}
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void withdraw(pending)}
          >
            {t('Zurücknehmen')}
          </button>
        </Alert>
      )}
      {open && info.earliest_date && (
        <form onSubmit={send}>
          <p className="muted small">
            {t('Kündigen ist {rule} möglich. Ein späteres Datum kannst du wählen.', {
              rule: info.rule,
            })}
          </p>
          <div className="grid-2">
            <Field
              label={t('Austritt zum')}
              type="date"
              required
              min={info.earliest_date}
              value={exitDate}
              onChange={(e) => setExitDate(e.target.value)}
            />
          </div>
          <Field
            label={t('Nachricht an {e_akk} (optional)', { e_akk: tm.e_akk })}
            value={message}
            maxLength={500}
            onChange={(e) => setMessage(e.target.value)}
          />
          <div className="button-row">
            <button type="submit" className="button button-danger" disabled={busy || !exitDate}>
              {t('Kündigung absenden')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      )}
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      {info.requests.some((c) => c.status !== 'pending') && (
        <ul className="audit-list">
          {info.requests
            .filter((c) => c.status !== 'pending')
            .map((c) => (
              <li key={c.id}>
                <strong>{c.status_label}</strong>{' '}
                <span className="muted small">
                  {t('Kündigung zum {date}, gesendet {sent}', {
                    date: formatDate(c.exit_date),
                    sent: formatDateTime(c.created_at),
                  })}
                </span>
                {c.response && (
                  <p className="small">
                    {t('Antwort {e_gen}:', { e_gen: tm.e_gen })} {c.response}
                  </p>
                )}
              </li>
            ))}
        </ul>
      )}
    </div>
  )
}
