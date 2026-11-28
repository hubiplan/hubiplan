import { useState } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { BoardRegistrations } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import type { PickedMember } from '../../api/members.ts'
import { errorMessage } from '../forms.ts'
import { Alert, Field, SelectField } from '../ui.tsx'
import { MemberPicker } from '../MemberPicker.tsx'
import { ExtrasFields, HealthConsent } from './RegistrationExtras.tsx'
import { asksHealth, emptyExtras, extrasPayload, isMinor } from './extras.ts'
import type { ExtrasState } from './extras.ts'
import { t } from '../../i18n/index.ts'
import { priceName } from './registrationHelpers.ts'

interface PersonRow {
  name: string
  price_id: number | ''
  member: PickedMember | null
  birth_date: string
  extras: ExtrasState
}

const emptyRow = (): PersonRow => ({
  name: '',
  price_id: '',
  member: null,
  birth_date: '',
  extras: emptyExtras(),
})

export function BoardAddForm({
  base,
  event,
  offer,
  onDone,
}: {
  base: CalendarBase
  event: EventDetail
  offer: NonNullable<BoardRegistrations['offer']>
  onDone: (data: BoardRegistrations) => void
}) {
  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)
  const [booker, setBooker] = useState<PickedMember | null>(null)
  const [contact, setContact] = useState({ name: '', email: '', phone: '', address: '' })
  const [persons, setPersons] = useState<PersonRow[]>(() => [emptyRow()])
  const [regExtras, setRegExtras] = useState<ExtrasState>(emptyExtras)
  const [consent, setConsent] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const prices = offer.prices.filter((p) => p.is_active)
  const set = (i: number, patch: Partial<PersonRow>) =>
    setPersons(persons.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  const minor = (p: PersonRow) => !!offer.minors && isMinor(p.birth_date, event.starts_at)
  const health = asksHealth(offer) && persons.some((p) => p.extras.health.trim())

  async function save() {
    setBusy(true)
    setError(null)
    try {
      onDone(
        await registrationApi.add(base, event.id, {
          membership_id: booker?.id ?? null,
          ...contact,
          note,
          persons: persons.map((p) => ({
            membership_id: p.member?.id ?? null,
            name: p.member ? `${p.member.first_name} ${p.member.last_name}` : p.name,
            price_id: Number(p.price_id),
            birth_date: p.birth_date || null,
            ...extrasPayload(offer, p.extras, minor(p)),
          })),
          ...extrasPayload(offer, regExtras),
          health_consent: health && consent,
        }),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack-sm">
      {error && <Alert kind="error">{error}</Alert>}
      <MemberPicker
        orgId={orgId}
        value={booker}
        label={t('Angemeldet von (Mitglied, optional)')}
        onChange={(m) => {
          setBooker(m)
          if (m && !persons[0].member && !persons[0].name) set(0, { member: m })
        }}
      />
      {!booker && (
        <>
          <Field
            label={t('Name')}
            value={contact.name}
            maxLength={200}
            onChange={(e) => setContact({ ...contact, name: e.target.value })}
          />
          <Field
            label={t('E-Mail (für Bestätigung und Rechnung)')}
            type="email"
            value={contact.email}
            onChange={(e) => setContact({ ...contact, email: e.target.value })}
          />
          <Field
            label={t('Telefon')}
            value={contact.phone}
            maxLength={50}
            onChange={(e) => setContact({ ...contact, phone: e.target.value })}
          />
          <label className="field">
            <span>{t('Anschrift (für die Rechnung)')}</span>
            <textarea
              rows={3}
              value={contact.address}
              onChange={(e) => setContact({ ...contact, address: e.target.value })}
            />
          </label>
        </>
      )}
      {persons.map((p, i) => (
        <div key={i} className="stack-sm">
          <MemberPicker
            orgId={orgId}
            value={p.member}
            label={t('Person {n}: Mitglied (optional)', { n: i + 1 })}
            onChange={(m) => set(i, { member: m })}
          />
          {!p.member && (
            <Field
              label={t('Person {n}: Name', { n: i + 1 })}
              value={p.name}
              maxLength={200}
              onChange={(e) => set(i, { name: e.target.value })}
            />
          )}
          <SelectField
            label={t('Tarif')}
            value={String(p.price_id)}
            onChange={(e) => set(i, { price_id: e.target.value ? Number(e.target.value) : '' })}
          >
            <option value="">{t('bitte wählen …')}</option>
            {prices.map((x) => (
              <option key={x.id} value={x.id}>
                {priceName(x)} – {x.current ? euro(x.current.amount) : t('nicht mehr buchbar')}
              </option>
            ))}
          </SelectField>
          {offer.minors && !p.member && (
            <Field
              label={t('Geburtsdatum')}
              type="date"
              value={p.birth_date}
              onChange={(e) => set(i, { birth_date: e.target.value })}
            />
          )}
          <ExtrasFields
            offer={offer}
            per="person"
            state={p.extras}
            who={persons.length > 1 ? t('Person {n}', { n: i + 1 }) : undefined}
            minor={minor(p)}
            onChange={(extras) => set(i, { extras })}
          />
        </div>
      ))}
      <div className="button-row">
        {persons.length < offer.max_persons && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setPersons([...persons, emptyRow()])}
          >
            <span aria-hidden="true">+</span> {t('Weitere Person')}
          </button>
        )}
      </div>
      <ExtrasFields offer={offer} per="registration" state={regExtras} onChange={setRegExtras} />
      <Field
        label={t('Bemerkung (optional)')}
        value={note}
        maxLength={500}
        onChange={(e) => setNote(e.target.value)}
      />
      {health && <HealthConsent checked={consent} onChange={setConsent} />}
      <div className="button-row">
        <button
          type="button"
          className="button"
          disabled={
            busy ||
            (health && !consent) ||
            persons.some((p) => p.price_id === '' || (!p.member && !p.name.trim()))
          }
          onClick={() => void save()}
        >
          {t('Anmelden')}
        </button>
      </div>
    </div>
  )
}

// --- Einrichten ---
