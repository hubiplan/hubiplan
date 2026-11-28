import { useState } from 'react'
import { todayIso } from '../../api/members.ts'
import { PERM } from '../../api/orgs.ts'
import { peeringApi } from '../../api/peering.ts'
import type { Coupling, RemoteTransfer } from '../../api/peering.ts'
import { errorMessage, formatDate } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { useMemberTypes } from '../../components/masterData.ts'

export function TransferCard({ coupling, onChange }: { coupling: Coupling; onChange: () => void }) {
  const org = useActiveOrg()
  const canEdit = org.permissions.includes(PERM.membersEdit)
  const { data: types } = useMemberTypes(org.id)
  const [form, setForm] = useState({
    last_name: '',
    first_name: '',
    birth_date: '',
    member_type: '',
    entry_date: todayIso(),
    message: '',
  })
  const [showForm, setShowForm] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(fn: () => Promise<unknown>) {
    setErr(null)
    setBusy(true)
    try {
      await fn()
      onChange()
      return true
    } catch (e) {
      setErr(errorMessage(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  const active = (types ?? []).filter((tm) => tm.active && !tm.is_archived)
  const passive = (types ?? []).filter((tm) => !tm.active && !tm.is_archived)
  return (
    <div>
      <h4>
        {t('Wechselanfragen über')} {coupling.remote.name}
      </h4>
      <p className="muted small">
        {t(
          'Ist jemand in einer anderen Einheit {name} aktiv, läuft die Aufnahme als aktives Mitglied über eine Wechselanfrage. Die andere Einheit bestätigt Austritt oder eine nicht aktive Art.',
          { name: coupling.remote.name },
        )}
      </p>
      {coupling.transfers.length > 0 && (
        <ul className="plain-list">
          {coupling.transfers.map((tm) => (
            <TransferRow
              key={tm.id}
              t={tm}
              passive={passive}
              disabled={busy || !canEdit}
              onDecide={(data) =>
                void run(() => peeringApi.decideTransfer(org.id, coupling.id, tm.id, data))
              }
            />
          ))}
        </ul>
      )}
      {canEdit && !showForm && (
        <button type="button" className="button" onClick={() => setShowForm(true)}>
          {t('Wechselanfrage stellen')}
        </button>
      )}
      {showForm && (
        <div className="card">
          <div className="grid-2">
            <Field
              label={t('Name')}
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
            <Field
              label={t('Vorname')}
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
            <Field
              label={t('Geburtsdatum')}
              type="date"
              value={form.birth_date}
              onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
            />
            <Field
              label={t('Eintritt')}
              type="date"
              value={form.entry_date}
              onChange={(e) => setForm({ ...form, entry_date: e.target.value })}
            />
          </div>
          <label className="field">
            <span>{t('Mitgliedsart')}</span>
            <select
              value={form.member_type}
              onChange={(e) => setForm({ ...form, member_type: e.target.value })}
            >
              <option value="">{t('bitte wählen')}</option>
              {active.map((tm) => (
                <option key={tm.id} value={tm.id}>
                  {tm.name}
                </option>
              ))}
            </select>
          </label>
          <Field
            label={t('Nachricht')}
            value={form.message}
            onChange={(e) => setForm({ ...form, message: e.target.value })}
          />
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy || !form.last_name || !form.birth_date || !form.member_type}
              onClick={() =>
                void run(() =>
                  peeringApi.requestTransfer(org.id, coupling.id, {
                    ...form,
                    member_type: Number(form.member_type),
                  }),
                ).then((ok) => ok && setShowForm(false))
              }
            >
              {t('Anfrage senden')}
            </button>
            <button type="button" className="link-button" onClick={() => setShowForm(false)}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      )}
      {err && <Alert kind="error">{err}</Alert>}
    </div>
  )
}

function TransferRow({
  t: tm,
  passive,
  disabled,
  onDecide,
}: {
  t: RemoteTransfer
  passive: { id: number; name: string }[]
  disabled: boolean
  onDecide: (data: {
    decision: 'exit' | 'change_type' | 'reject'
    member_type?: number
    response?: string
  }) => void
}) {
  const [type, setType] = useState('')
  const [response, setResponse] = useState('')
  const outgoing = tm.role === 'to'
  return (
    <li>
      <strong>{tm.name}</strong>{' '}
      {outgoing
        ? t('· Aufnahme als {x}', { x: tm.member_type_name || t('aktives Mitglied') })
        : t('· möchte zu {to_unit} wechseln ({member_type_name})', {
            to_unit: tm.to_unit,
            member_type_name: tm.member_type_name,
          })}
      {tm.entry_date && t(' ab {x}', { x: formatDate(tm.entry_date) })} · {tm.status_label}
      {tm.message && <span className="muted small"> · „{tm.message}“</span>}
      {tm.response && (
        <span className="muted small">
          {' '}
          {t('· Antwort:')} {tm.response}
        </span>
      )}
      {!outgoing && tm.status === 'pending' && (
        <div className="button-row">
          <button
            type="button"
            className="button"
            disabled={disabled}
            onClick={() => onDecide({ decision: 'exit', response })}
          >
            {t('Austritt bestätigen')}
          </button>
          <select
            aria-label={t('nicht aktive Art')}
            value={type}
            onChange={(e) => setType(e.target.value)}
            disabled={disabled}
          >
            <option value="">{t('nicht aktive Art …')}</option>
            {passive.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button"
            disabled={disabled || !type}
            onClick={() =>
              onDecide({ decision: 'change_type', member_type: Number(type), response })
            }
          >
            {t('Art ändern')}
          </button>
          <input
            aria-label={t('Antwort')}
            placeholder={t('Antwort (optional)')}
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            disabled={disabled}
          />
          <button
            type="button"
            className="link-button"
            disabled={disabled}
            onClick={() => onDecide({ decision: 'reject', response })}
          >
            {t('ablehnen')}
          </button>
        </div>
      )}
    </li>
  )
}
