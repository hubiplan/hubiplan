import { useState } from 'react'
import type { FormEvent } from 'react'
import { historyApi, type Grant } from '../../api/competitionHistory.ts'
import type { MemberRow } from '../../api/members.ts'
import { MemberPicker } from '../../components/MemberPicker.tsx'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

/** Früheres Jahr nachtragen (Altdaten, auch nur „Sieger je Jahr“). */
export function ManualGrant({
  org,
  defaults,
  onSaved,
  label = t('Früheres Jahr nachtragen'),
}: {
  org: number
  defaults: Partial<Grant>
  onSaved: () => void
  label?: string
}) {
  const [open, setOpen] = useState(false)
  const [member, setMember] = useState<MemberRow | null>(null)
  const [v, setV] = useState({ year: '', title: '', item: '', name: '', place: '' })
  const [message, setMessage] = useState<string | null>(null)
  if (!open)
    return (
      <div className="button-row">
        <button type="button" className="button button-ghost" onClick={() => setOpen(true)}>
          {label}
        </button>
      </div>
    )

  async function save(e: FormEvent) {
    e.preventDefault()
    setMessage(null)
    try {
      await historyApi.grants.create(org, {
        ...defaults,
        year: Number(v.year),
        title: v.title,
        item: v.item,
        place: v.place ? Number(v.place) : null,
        membership: member?.id ?? null,
        name: v.name,
      })
      setV({ year: '', title: v.title, item: '', name: '', place: '' })
      setMember(null)
      onSaved()
    } catch (err) {
      setMessage(errorMessage(err))
    }
  }

  return (
    <form onSubmit={save} className="card">
      <h3>{label}</h3>
      <div className="grid-3">
        <Field
          label={t('Jahr')}
          type="number"
          required
          value={v.year}
          onChange={(e) => setV({ ...v, year: e.target.value })}
        />
        {!defaults.trophy && (
          <Field
            label={t('Titel')}
            placeholder={t('z. B. Vereinsmeister')}
            value={v.title}
            onChange={(e) => setV({ ...v, title: e.target.value })}
          />
        )}
        <Field
          label={t('Platz')}
          type="number"
          min={1}
          value={v.place}
          onChange={(e) => setV({ ...v, place: e.target.value })}
        />
        <MemberPicker orgId={org} value={member} onChange={setMember} />
        {!member && (
          <Field
            label={t('oder Name')}
            hint={t('für frühere Mitglieder und Gäste')}
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
          />
        )}
      </div>
      {message && <Alert kind="error">{message}</Alert>}
      <div className="button-row">
        <button type="submit" className="button">
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={() => setOpen(false)}>
          {t('Schließen')}
        </button>
      </div>
    </form>
  )
}
