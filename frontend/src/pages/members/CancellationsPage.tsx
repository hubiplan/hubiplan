// Kündigungen aus dem Mitgliederbereich prüfen: Austritt bestätigen oder ablehnen.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PERM } from '../../api/orgs.ts'
import { portalApi } from '../../api/portal.ts'
import type { Cancellation } from '../../api/portal.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function CancellationsPage() {
  const org = useActiveOrg()
  const [status, setStatus] = useState('pending')
  const loaded = useLoad(
    () => portalApi.cancellations(org.id, status).then((items) => ({ status, items })),
    [org.id, status],
  )
  const data = loaded.data?.status === status ? loaded.data.items : null
  const { error, reload } = loaded
  const canEdit = org.permissions.includes(PERM.membersEdit)

  return (
    <>
      <div className="card card-wide filters">
        <select aria-label={t('Status')} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">{t('offen')}</option>
          <option value="accepted">{t('bestätigt')}</option>
          <option value="rejected">{t('abgelehnt')}</option>
          <option value="withdrawn">{t('zurückgenommen')}</option>
          <option value="alle">{t('alle')}</option>
        </select>
      </div>
      {error && (
        <LoadError
          message={t('Die Kündigungen konnten nicht geladen werden. {error}', { error })}
          onRetry={() => void reload()}
        />
      )}
      {!data ? (
        !error && (
          <p className="muted" role="status">
            {t('Wird geladen …')}
          </p>
        )
      ) : data.length === 0 ? (
        <div className="card empty-state">
          <p>{t('Keine Kündigungen.')}</p>
        </div>
      ) : (
        <div className="stack">
          {data.map((c) => (
            <CancellationCard
              key={c.id}
              orgId={org.id}
              item={c}
              canEdit={canEdit}
              onDone={reload}
            />
          ))}
        </div>
      )}
    </>
  )
}

function CancellationCard({
  orgId,
  item: c,
  canEdit,
  onDone,
}: {
  orgId: number
  item: Cancellation
  canEdit: boolean
  onDone: () => void
}) {
  const [response, setResponse] = useState('')
  const [exitDate, setExitDate] = useState(c.exit_date)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function decide(accept: boolean) {
    const ok = await confirmDialog(
      accept
        ? {
            title: t('Austritt von {name} zum {date} eintragen?', {
              name: c.member_name,
              date: formatDate(exitDate),
            }),
            message: t(
              'Mitgliedsart, Untereinheiten und Ämter enden mit dem Austritt. Das Mitglied bekommt eine Austrittsbestätigung per Mail.',
            ),
            confirmLabel: t('Austritt bestätigen'),
          }
        : {
            title: t('Kündigung von {name} ablehnen?', { name: c.member_name }),
            message: t(
              'Die Mitgliedschaft läuft weiter. Das Mitglied bekommt deine Antwort per Mail.',
            ),
            confirmLabel: t('Ablehnen'),
          },
    )
    if (!ok) return
    setBusy(true)
    setError(null)
    try {
      await portalApi.decideCancellation(orgId, c.id, {
        accept,
        response,
        ...(accept && exitDate !== c.exit_date ? { exit_date: exitDate } : {}),
      })
      onDone()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <div className="card-head">
        <h2>
          <Link to={`/mitglieder/${c.member_id}`}>{c.member_name}</Link>
        </h2>
        <span className="muted small push-right">
          {c.status_label} {t('· gesendet')} {formatDateTime(c.created_at)}
        </span>
      </div>
      <p>
        {t('Austritt zum {date}', { date: formatDate(c.exit_date) })}
        {c.exit_date !== c.earliest_date && (
          <span className="muted small">
            {' '}
            {t('(frühestens möglich: {date})', { date: formatDate(c.earliest_date) })}
          </span>
        )}
      </p>
      {c.message && (
        <p className="small">
          {t('Nachricht:')} {c.message}
        </p>
      )}
      {c.response && (
        <p className="small">
          {t('Antwort:')} {c.response}
        </p>
      )}
      {c.status === 'pending' && canEdit && (
        <>
          <div className="grid-2">
            <Field
              label={t('Austrittsdatum')}
              type="date"
              value={exitDate}
              hint={t('Nur ändern, wenn die Satzung ein anderes Datum vorgibt.')}
              onChange={(e) => setExitDate(e.target.value)}
            />
          </div>
          <Field
            label={t('Antwort an das Mitglied (optional)')}
            value={response}
            maxLength={500}
            onChange={(e) => setResponse(e.target.value)}
          />
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || !exitDate}
              onClick={() => void decide(true)}
            >
              {t('Austritt bestätigen')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void decide(false)}
            >
              {t('Ablehnen')}
            </button>
          </div>
        </>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
