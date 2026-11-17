// Finanzen › Beitragssätze: Ermäßigung mit Nachweis einrichten (Frist, Kulanzzeit, Erinnerungen,
// Arten von Nachweisen) und automatische Anerkennung (docs/beitragsnachweise.md).
import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../api/client.ts'
import { euro, parseAmount } from '../../api/finance.ts'
import { feeProofApi } from '../../api/feeProofs.ts'
import type { DiscountInput, ProofDiscount } from '../../api/feeProofs.ts'
import { memberApi } from '../../api/members.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

const DEFAULT_KINDS = [
  'Immatrikulationsbescheinigung',
  'Bestätigung der Annahme als Doktorand/in',
  'Vergleichbarer Nachweis',
]

interface Draft {
  name: string
  member_type: string
  mode: 'amount' | 'percent'
  value: string
  deadline: string
  grace_days: string
  late_join_days: string
  notify_after: boolean
  kinds: string
}

function emptyDraft(): Draft {
  return {
    name: '',
    member_type: '',
    mode: 'amount',
    value: '',
    deadline: '28.02.',
    grace_days: '',
    late_join_days: '28',
    notify_after: true,
    kinds: DEFAULT_KINDS.join('\n'),
  }
}

function draftOf(d: ProofDiscount): Draft {
  return {
    name: d.name,
    member_type: d.member_type ? String(d.member_type) : '',
    mode: d.amount !== null ? 'amount' : 'percent',
    value: (d.amount ?? d.discount_percent ?? '').replace('.', ','),
    deadline: `${String(d.deadline_day).padStart(2, '0')}.${String(d.deadline_month).padStart(2, '0')}.`,
    grace_days: d.grace_days !== null ? String(d.grace_days) : '',
    late_join_days: String(d.late_join_days),
    notify_after: d.notify_after,
    kinds: d.kinds.join('\n'),
  }
}

function deadlineText(d: ProofDiscount): string {
  return `${String(d.deadline_day).padStart(2, '0')}.${String(d.deadline_month).padStart(2, '0')}.`
}

export function FeeProofDiscountsCard({ orgId, canEdit }: { orgId: number; canEdit: boolean }) {
  const list = useLoad(() => feeProofApi.discounts(orgId), [orgId])
  const settings = useLoad(() => feeProofApi.settings(orgId), [orgId])
  const types = useLoad(() => memberApi.types(orgId), [orgId])
  const [editing, setEditing] = useState<number | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft())
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (list.error) return null // Modul Beiträge aus
  if (!list.data) return null
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft({ ...draft, [key]: value })

  async function save(e: FormEvent) {
    e.preventDefault()
    const m = /^\s*(\d{1,2})\.(\d{1,2})\.?\s*$/.exec(draft.deadline)
    if (!m) {
      setErrors({ deadline_day: t('Bitte als Tag.Monat. angeben, z. B. 28.02.') })
      return
    }
    const value = parseAmount(draft.value)
    const data: DiscountInput = {
      name: draft.name,
      member_type: draft.member_type ? Number(draft.member_type) : null,
      amount: draft.mode === 'amount' ? value : null,
      discount_percent: draft.mode === 'percent' ? value : null,
      deadline_day: Number(m[1]),
      deadline_month: Number(m[2]),
      grace_days: draft.grace_days ? Number(draft.grace_days) : null,
      late_join_days: Number(draft.late_join_days || 0),
      notify_after: draft.notify_after,
      kinds: draft.kinds
        .split('\n')
        .map((k) => k.trim())
        .filter(Boolean),
    }
    setBusy(true)
    setErrors({})
    try {
      if (editing === 'new') await feeProofApi.createDiscount(orgId, data)
      else if (editing !== null) await feeProofApi.updateDiscount(orgId, editing, data)
      setEditing(null)
      await list.reload()
    } catch (err) {
      setErrors({ ...(err instanceof ApiError ? err.fieldErrors : {}), detail: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function archive(d: ProofDiscount, value: boolean) {
    setMessage(null)
    try {
      await feeProofApi.updateDiscount(orgId, d.id, { is_archived: value })
      await list.reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function remove(d: ProofDiscount) {
    const ok = await confirmDialog({
      title: t('„{name}“ löschen?', { name: d.name }),
      confirmLabel: t('Löschen'),
    })
    if (!ok) return
    setMessage(null)
    try {
      await feeProofApi.removeDiscount(orgId, d.id)
      await list.reload()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  async function setAuto(value: boolean) {
    setMessage(null)
    try {
      settings.setData(await feeProofApi.saveSettings(orgId, { auto_accept: value }))
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Ermäßigung mit Nachweis')}</h2>
      <p className="muted small">
        {t(
          'Zum Beispiel für Studierende: Der ermäßigte Beitrag gilt nur mit einem Nachweis, der jedes Jahr bis zur Frist vorliegen muss. HUBIplan erinnert die Mitglieder, nimmt Nachweise per App, Mitgliederbereich, Link oder Antwort-Mail an und berechnet ohne Nachweis den normalen Beitrag. Zugeordnet wird in der Mitgliedsakte.',
        )}
      </p>
      {list.data.length === 0 ? (
        <p className="muted">{t('Keine.')}</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t('Ermäßigung')}</th>
              <th>{t('Beitrag')}</th>
              <th>{t('Frist')}</th>
              <th>{t('gilt für')}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((d) => (
              <tr key={d.id}>
                <td>
                  <strong>{d.name}</strong>
                  {d.is_archived && (
                    <span className="muted small"> · {t('nicht mehr verwendet')}</span>
                  )}
                </td>
                <td>
                  {d.amount !== null
                    ? t('{x} im Jahr', { x: euro(d.amount) })
                    : t('{p} % weniger', { p: Number(d.discount_percent).toLocaleString() })}
                </td>
                <td>
                  {deadlineText(d)}
                  {d.grace_days ? ` + ${t('{n} Tage Kulanz', { n: d.grace_days })}` : ''}
                </td>
                <td>{d.member_type_name ?? t('alle Mitgliedsarten')}</td>
                <td className="actions">
                  {canEdit && (
                    <span className="button-row">
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => {
                          setEditing(d.id)
                          setDraft(draftOf(d))
                          setErrors({})
                        }}
                      >
                        {t('Bearbeiten')}
                      </button>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => void archive(d, !d.is_archived)}
                      >
                        {d.is_archived ? t('wieder verwenden') : t('nicht mehr verwenden')}
                      </button>
                      {!d.in_use && (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => void remove(d)}
                        >
                          {t('Löschen')}
                        </button>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {settings.data && list.data.length > 0 && (
        <Checkbox
          label={t('Eindeutige Nachweise automatisch anerkennen')}
          hint={t(
            'nur wenn die Vorprüfung grün ist (Name, Studium und Gültigkeit gefunden) und die Frist läuft; alle anderen prüft der Vorstand',
          )}
          checked={settings.data.auto_accept}
          disabled={!canEdit}
          onChange={(value) => void setAuto(value)}
        />
      )}
      {settings.data && !settings.data.mail_replies && list.data.length > 0 && (
        <p className="muted small">
          {t(
            'Antworten per E-Mail mit Anhang gehen erst, wenn das Rechnungspostfach eingerichtet ist. Link, App und Mitgliederbereich gehen immer.',
          )}
        </p>
      )}
      {message && <Alert kind="error">{message}</Alert>}
      {canEdit && editing === null && (
        <div className="button-row">
          <button
            type="button"
            className="button"
            onClick={() => {
              setEditing('new')
              setDraft(emptyDraft())
              setErrors({})
            }}
          >
            {t('Ermäßigung anlegen')}
          </button>
        </div>
      )}
      {canEdit && editing !== null && (
        <form className="subcard" onSubmit={(e) => void save(e)}>
          <h3>
            {editing === 'new' ? t('Neue Ermäßigung mit Nachweis') : t('Ermäßigung bearbeiten')}
          </h3>
          <div className="grid-3">
            <Field
              label={t('Bezeichnung')}
              required
              placeholder={t('z. B. Studierende')}
              value={draft.name}
              error={errors.name}
              onChange={(e) => set('name', e.target.value)}
            />
            <SelectField
              label={t('gilt für')}
              value={draft.member_type}
              error={errors.member_type}
              onChange={(e) => set('member_type', e.target.value)}
            >
              <option value="">{t('alle Mitgliedsarten')}</option>
              {(types.data ?? []).map((mt) => (
                <option key={mt.id} value={mt.id}>
                  {mt.name}
                </option>
              ))}
            </SelectField>
            <SelectField
              label={t('Ermäßigung als')}
              value={draft.mode}
              onChange={(e) => set('mode', e.target.value as Draft['mode'])}
            >
              <option value="amount">{t('ermäßigter Jahresbeitrag (€)')}</option>
              <option value="percent">{t('Abschlag in Prozent')}</option>
            </SelectField>
            <Field
              label={draft.mode === 'amount' ? t('Jahresbeitrag (€)') : t('Abschlag (%)')}
              inputMode="decimal"
              required
              value={draft.value}
              error={
                draft.mode === 'amount' ? errors.amount : (errors.discount_percent ?? errors.amount)
              }
              onChange={(e) => set('value', e.target.value)}
            />
            <Field
              label={t('Frist im Beitragsjahr')}
              required
              placeholder="28.02."
              hint={t('Tag.Monat.')}
              value={draft.deadline}
              error={errors.deadline_day}
              onChange={(e) => set('deadline', e.target.value)}
            />
            <Field
              label={t('Kulanzzeit in Tagen (freiwillig)')}
              type="number"
              min={0}
              max={365}
              value={draft.grace_days}
              error={errors.grace_days}
              onChange={(e) => set('grace_days', e.target.value)}
            />
            <Field
              label={t('Nachreichen nach Eintritt in Tagen')}
              type="number"
              min={0}
              max={365}
              value={draft.late_join_days}
              error={errors.late_join_days}
              onChange={(e) => set('late_join_days', e.target.value)}
            />
          </div>
          <label className="field">
            <span>{t('Arten von Nachweisen (eine je Zeile)')}</span>
            <textarea rows={3} value={draft.kinds} onChange={(e) => set('kinds', e.target.value)} />
            {errors.kinds && <small className="field-error">{errors.kinds}</small>}
          </label>
          <Checkbox
            label={t('Nach Fristablauf mitteilen, dass der normale Beitrag gilt')}
            checked={draft.notify_after}
            onChange={(value) => set('notify_after', value)}
          />
          <p className="muted small">
            {t(
              'Erinnerungen gehen am 15.01. und 14 Tage vor der Frist an alle, die noch keinen Nachweis haben.',
            )}
          </p>
          {errors.detail && <Alert kind="error">{errors.detail}</Alert>}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy}>
              {t('Speichern')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setEditing(null)}>
              {t('Abbrechen')}
            </button>
          </div>
        </form>
      )}
    </div>
  )
}
