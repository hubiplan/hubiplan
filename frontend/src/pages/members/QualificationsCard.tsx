// Qualifikationen in der Mitgliedsakte: Nachweise mit Gültigkeit, eintragen, verlängern,
// bearbeiten, löschen. Frühere Nachweise derselben Art stehen als Verlauf darunter.
// Einsichtsvermerke (z. B. Führungszeugnis) haben nur das Datum der Einsicht, keine Bemerkung.
import { useState } from 'react'
import type { FormEvent } from 'react'
import { todayIso } from '../../api/members.ts'
import { addMonths, qualificationApi } from '../../api/qualifications.ts'
import type {
  Qualification,
  QualificationStatus,
  QualificationType,
} from '../../api/qualifications.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, formatDate, useLoad } from '../../components/forms.ts'
import { DeleteIcon, EditIcon, IconButton } from '../../components/icons.tsx'
import { Alert, LoadError } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { untilText } from './qualificationText.ts'

export function StatusBadge({ status }: { status: QualificationStatus }) {
  if (status === 'expired') return <span className="badge badge-cancelled">{t('abgelaufen')}</span>
  if (status === 'expiring') return <span className="badge badge-open">{t('läuft bald ab')}</span>
  return <span className="badge badge-yes">{t('gültig')}</span>
}

function sinceText(q: { inspection_only: boolean; acquired_on: string }): string {
  return q.inspection_only
    ? t('eingesehen am {date}', { date: formatDate(q.acquired_on) })
    : t('seit {date}', { date: formatDate(q.acquired_on) })
}

/** Eingabefelder für einen Nachweis (neu, verlängern, bearbeiten). */
function RecordForm({
  label,
  types,
  initial,
  submitLabel,
  busy,
  fixedKind,
  onSave,
  onCancel,
}: {
  label: string
  types: QualificationType[]
  initial?: Qualification
  submitLabel: string
  busy: boolean
  fixedKind?: boolean
  onSave: (data: Partial<Qualification>) => Promise<boolean>
  onCancel?: () => void
}) {
  const [kind, setKind] = useState(initial ? String(initial.kind) : '')
  const [from, setFrom] = useState(initial?.acquired_on ?? todayIso())
  const [until, setUntil] = useState(initial?.valid_until ?? '')
  const [untilTouched, setUntilTouched] = useState(!!initial && !fixedKind)
  const [note, setNote] = useState(initial?.note ?? '')
  const type = types.find((k) => String(k.id) === kind)
  const inspection = type?.inspection_only ?? initial?.inspection_only ?? false
  // Übliche Gültigkeit der Art schlägt das Ablaufdatum vor, bis es von Hand geändert wird
  const suggested = type?.validity_months && from ? addMonths(from, type.validity_months) : ''
  const shownUntil = untilTouched ? until : suggested

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!kind) return
    const ok = await onSave({
      kind: Number(kind),
      acquired_on: from,
      valid_until: shownUntil || null,
      note: inspection ? '' : note,
    })
    if (ok && !initial) {
      setKind('')
      setUntil('')
      setUntilTouched(false)
      setNote('')
    }
  }

  return (
    <form className="inline-edit" aria-label={label} onSubmit={(e) => void submit(e)}>
      <select
        aria-label={t('Qualifikation')}
        value={kind}
        required
        disabled={fixedKind}
        onChange={(e) => {
          setKind(e.target.value)
          if (!initial) setUntilTouched(false)
        }}
      >
        <option value="">{t('Qualifikation eintragen …')}</option>
        {types.map((k) => (
          <option key={k.id} value={k.id}>
            {k.name}
          </option>
        ))}
      </select>
      <label className="inline-label">
        <span className="small">{inspection ? t('eingesehen am') : t('erworben am')}</span>
        <input
          type="date"
          required
          max={todayIso()}
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      </label>
      <label className="inline-label">
        <span className="small">{t('gültig bis (leer: unbefristet)')}</span>
        <input
          type="date"
          value={shownUntil}
          onChange={(e) => {
            setUntil(e.target.value)
            setUntilTouched(true)
          }}
        />
      </label>
      {!inspection && (
        <input
          type="text"
          aria-label={t('Bemerkung')}
          placeholder={t('Bemerkung (optional)')}
          maxLength={200}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      )}
      <span className="button-row">
        <button type="submit" className="button" disabled={busy || !kind}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="button button-ghost" onClick={onCancel}>
            {t('Abbrechen')}
          </button>
        )}
      </span>
      {inspection && (
        <p className="muted small">
          {t('Nur das Datum der Einsicht wird festgehalten, nie der Inhalt des Nachweises.')}
        </p>
      )}
    </form>
  )
}

export function QualificationsCard({
  orgId,
  memberId,
  canEdit,
}: {
  orgId: number
  memberId: number
  canEdit: boolean
}) {
  const rows = useLoad(() => qualificationApi.records(orgId, memberId), [orgId, memberId])
  const types = useLoad(() => qualificationApi.types(orgId), [orgId])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [renewing, setRenewing] = useState<number | null>(null)
  const options = types.data?.filter((k) => !k.is_archived) ?? []
  const list = rows.data ?? []
  const current = list.filter((q) => q.current)
  const history = list.filter((q) => !q.current)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      await rows.reload()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }

  async function remove(q: Qualification) {
    const ok = await confirmDialog({
      title: t('„{name}“ löschen?', { name: q.kind_name }),
      message: t('Nur für falsche Einträge. Bei einer Verlängerung besser „verlängern“ wählen.'),
      confirmLabel: t('Löschen'),
    })
    if (ok) await run(() => qualificationApi.deleteRecord(orgId, memberId, q.id))
  }

  function line(q: Qualification) {
    if (canEdit && editing === q.id) {
      const known = options.some((k) => k.id === q.kind)
      return (
        <li key={q.id}>
          <RecordForm
            label={t('{name} bearbeiten', { name: q.kind_name })}
            types={
              known
                ? options
                : [
                    ...options,
                    {
                      id: q.kind,
                      name: q.kind_name,
                      inspection_only: q.inspection_only,
                    } as QualificationType,
                  ]
            }
            initial={q}
            submitLabel={t('Speichern')}
            busy={busy}
            onCancel={() => setEditing(null)}
            onSave={(data) =>
              run(() => qualificationApi.updateRecord(orgId, memberId, q.id, data)).then((ok) => {
                if (ok) setEditing(null)
                return ok
              })
            }
          />
        </li>
      )
    }
    return (
      <li key={q.id} className="item-row">
        <span className="item-row-info">
          <strong>{q.kind_name}</strong> · {sinceText(q)} · {untilText(q.valid_until)}
          {q.current && <StatusBadge status={q.status} />}
          {q.note && <span className="muted small"> · {q.note}</span>}
        </span>
        {canEdit && (
          <span className="button-row">
            {q.current && q.valid_until && options.some((k) => k.id === q.kind) && (
              <button
                type="button"
                className="link-button"
                disabled={busy}
                onClick={() => setRenewing(q.id)}
              >
                {t('verlängern')}
              </button>
            )}
            <IconButton
              label={t('{name} bearbeiten', { name: q.kind_name })}
              icon={<EditIcon />}
              disabled={busy}
              onClick={() => setEditing(q.id)}
            />
            <IconButton
              label={t('{name} löschen', { name: q.kind_name })}
              icon={<DeleteIcon />}
              danger
              disabled={busy}
              onClick={() => void remove(q)}
            />
          </span>
        )}
      </li>
    )
  }

  const renewed = list.find((q) => q.id === renewing)

  return (
    <div className="card card-wide">
      <h2>{t('Qualifikationen')}</h2>
      {rows.error ? (
        <LoadError message={rows.error} onRetry={() => void rows.reload()} />
      ) : !rows.data ? (
        <p className="muted small">{t('Qualifikationen werden geladen …')}</p>
      ) : current.length === 0 ? (
        <p className="muted">{t('Keine.')}</p>
      ) : (
        <ul className="item-list">{current.map(line)}</ul>
      )}
      {renewed && canEdit && (
        <RecordForm
          key={`renew-${renewed.id}`}
          label={t('{name} verlängern', { name: renewed.kind_name })}
          types={options}
          initial={{
            ...renewed,
            acquired_on: todayIso(),
            valid_until: null,
            note: '',
          }}
          fixedKind
          submitLabel={t('Verlängerung speichern')}
          busy={busy}
          onCancel={() => setRenewing(null)}
          onSave={(data) =>
            run(() => qualificationApi.addRecord(orgId, memberId, data)).then((ok) => {
              if (ok) setRenewing(null)
              return ok
            })
          }
        />
      )}
      {history.length > 0 && (
        <details>
          <summary>{t('Frühere Nachweise ({n})', { n: history.length })}</summary>
          <ul className="item-list">{history.map(line)}</ul>
        </details>
      )}
      {canEdit &&
        (options.length > 0 ? (
          <RecordForm
            label={t('Qualifikation eintragen')}
            types={options}
            submitLabel={t('Eintragen')}
            busy={busy}
            onSave={(data) => run(() => qualificationApi.addRecord(orgId, memberId, data))}
          />
        ) : types.error ? (
          <LoadError message={types.error} onRetry={() => void types.reload()} />
        ) : types.data ? (
          <p className="muted small">
            {t('Noch keine Qualifikationen angelegt (Mitglieder › Einrichtung › Qualifikationen).')}
          </p>
        ) : null)}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}
