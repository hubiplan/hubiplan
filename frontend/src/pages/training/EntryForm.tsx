// Schießtermin eintragen (Vorstand) oder melden (Mitglied).
import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Discipline, EntryDraft, WeaponClass } from '../../api/training.ts'
import { errorMessage } from '../../components/forms.ts'
import { Checkbox, Field, SelectField } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

function today() {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function emptyEntry(): EntryDraft {
  return {
    date: today(),
    discipline: '',
    weapon_class: 'short',
    caliber: '',
    permit_required: true,
    own_weapon: null,
    competition: false,
    place: '',
    external: false,
    note: '',
  }
}

export function EntryForm({
  disciplines,
  submitLabel,
  onSubmit,
}: {
  disciplines: Discipline[]
  submitLabel: string
  onSubmit: (draft: EntryDraft) => Promise<void>
}) {
  const [draft, setDraft] = useState<EntryDraft>(emptyEntry)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = <K extends keyof EntryDraft>(key: K, value: EntryDraft[K]) =>
    setDraft((d) => ({ ...d, [key]: value }))
  const pick = (name: string) => {
    const known = disciplines.find((d) => d.name === name)
    setDraft((d) => ({
      ...d,
      discipline: name,
      ...(known
        ? {
            weapon_class: known.weapon_class,
            caliber: d.caliber || known.caliber,
            permit_required: known.permit_required,
          }
        : {}),
    }))
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await onSubmit(draft)
      setDraft(emptyEntry())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="stack-sm" onSubmit={submit}>
      {error && <p role="alert">{error}</p>}
      <div className="grid-2">
        <Field
          label={t('Datum')}
          type="date"
          value={draft.date}
          max={today()}
          required
          onChange={(e) => set('date', e.target.value)}
        />
        <Field
          label={t('Disziplin')}
          value={draft.discipline}
          required
          maxLength={100}
          suggestions={disciplines.map((d) => ({ value: d.name, detail: d.caliber }))}
          onChange={(e) => pick(e.target.value)}
        />
        <SelectField
          label={t('Waffe')}
          value={draft.weapon_class}
          onChange={(e) => set('weapon_class', e.target.value as WeaponClass)}
        >
          <option value="short">{t('Kurzwaffe')}</option>
          <option value="long">{t('Langwaffe')}</option>
        </SelectField>
        <Field
          label={t('Kaliber (optional)')}
          value={draft.caliber}
          maxLength={40}
          onChange={(e) => set('caliber', e.target.value)}
        />
        <Field
          label={t('Schießstand (optional)')}
          value={draft.place}
          maxLength={200}
          hint={t('leer: Stand des eigenen Vereins')}
          onChange={(e) => set('place', e.target.value)}
        />
        <Field
          label={t('Bemerkung (optional)')}
          value={draft.note}
          maxLength={300}
          onChange={(e) => set('note', e.target.value)}
        />
      </div>
      <div className="training-checks">
        <Checkbox
          label={t('erlaubnispflichtige Waffe')}
          checked={draft.permit_required}
          onChange={(v) => set('permit_required', v)}
        />
        <Checkbox
          label={t('eigene Waffe')}
          checked={draft.own_weapon === true}
          onChange={(v) => set('own_weapon', v)}
        />
        <Checkbox
          label={t('Wettkampf')}
          checked={draft.competition}
          onChange={(v) => set('competition', v)}
        />
        <Checkbox
          label={t('in einem anderen Verein')}
          checked={draft.external}
          onChange={(v) => set('external', v)}
        />
      </div>
      <div className="button-row">
        <button type="submit" className="button button-primary" disabled={busy}>
          {submitLabel}
        </button>
      </div>
    </form>
  )
}
