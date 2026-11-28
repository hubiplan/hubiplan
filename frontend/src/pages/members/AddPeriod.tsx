import { useState } from 'react'
import type { FormEvent } from 'react'
import { memberApi } from '../../api/members.ts'
import type { MemberDetail } from '../../api/members.ts'
import type { OrgSummary } from '../../api/orgs.ts'
import { useForm } from '../../components/forms.ts'
import { confirmDiscard, useChangesGuard } from '../../components/leaveGuard.ts'
import { Alert, Field, SelectField } from '../../components/ui.tsx'
import { orgTerms } from '../../org/terms.ts'
import { t } from '../../i18n/index.ts'
import { useMemberTypes } from '../../components/masterData.ts'

export function AddPeriod({
  org,
  member,
  onAdded,
}: {
  org: OrgSummary
  member: MemberDetail
  onAdded: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const types = useMemberTypes(org.id)
  const empty = { entry_date: '', exit_date: '', exit_reason: 'exit', member_type: '' }
  const form = useForm(empty)
  // Nachtrag vor dem Speichern nicht unbemerkt verlieren (UX-Audit 31.10. W01)
  const { dirty } = useChangesGuard(form.values, open)
  if (!open) {
    return (
      <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
        {t('Früheren Zeitraum nachtragen')}
      </button>
    )
  }
  async function save(ev: FormEvent) {
    ev.preventDefault()
    const { member_type, ...rest } = form.values
    const ok = await form.submit(() =>
      memberApi.addPeriod(org.id, member.id, {
        ...rest,
        member_type: member_type ? Number(member_type) : null,
      }),
    )
    if (ok) {
      form.setValues(empty)
      setOpen(false)
      await onAdded()
    }
  }
  return (
    <form className="subcard" onSubmit={save}>
      <div className="grid-3">
        <Field
          label={t('Eintritt')}
          type="date"
          required
          value={form.values.entry_date}
          error={form.errors.entry_date}
          onChange={(e) => form.set('entry_date', e.target.value)}
        />
        <Field
          label={t('Austritt')}
          type="date"
          required
          value={form.values.exit_date}
          error={form.errors.exit_date}
          onChange={(e) => form.set('exit_date', e.target.value)}
        />
        <SelectField
          label={t('Grund')}
          value={form.values.exit_reason}
          error={form.errors.exit_reason}
          onChange={(e) => form.set('exit_reason', e.target.value)}
        >
          {member.exit_reasons.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </SelectField>
      </div>
      <SelectField
        label={t('Mitgliedsart in diesem Zeitraum')}
        value={form.values.member_type}
        error={form.errors.member_type}
        onChange={(e) => form.set('member_type', e.target.value)}
      >
        <option value="">{t('– unbekannt –')}</option>
        {types.data?.map((tmx) => (
          <option key={tmx.id} value={tmx.id}>
            {tmx.name}
          </option>
        ))}
      </SelectField>
      {orgTerms(org).dv_has && (
        <p className="muted small">
          {t('Nur Zeiten mit einer gemeldeten Art zählen für {dv_akk}.', {
            dv_akk: orgTerms(org).dv_akk,
          })}
        </p>
      )}
      {form.message?.kind === 'error' && <Alert kind="error">{form.message.text}</Alert>}
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={form.busy}>
          {t('Speichern')}
        </button>
        <button
          type="button"
          className="button button-ghost"
          onClick={() =>
            void confirmDiscard(dirty).then((yes) => {
              if (!yes) return
              form.setValues(empty)
              setOpen(false)
            })
          }
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}
