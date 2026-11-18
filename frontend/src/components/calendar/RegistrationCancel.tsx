// Abmelden mit Vorschau der Stornogebühr und Ersatzperson (konzepte/veranstaltungen-anmeldung-gebuehr.md,
// Stufe A3), für die Verwaltung und den Mitgliederbereich.
import { useEffect, useState } from 'react'
import type { FeeQuote, Offer, Participant, Registration } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import type { PickedMember } from '../../api/members.ts'
import { errorMessage } from '../forms.ts'
import { Alert, Checkbox, Field, SelectField } from '../ui.tsx'
import { MemberPicker } from '../MemberPicker.tsx'
import { t, tc } from '../../i18n/index.ts'

/** Wofür die Gebühr anfällt oder warum nicht. */
function feeText(q: FeeQuote): string {
  if (q.free_reason === 'event_cancelled') return t('Kostenfrei: Der Termin ist abgesagt.')
  if (q.free_reason === 'waitlist') return t('Kostenfrei: Die Anmeldung steht auf der Warteliste.')
  if (q.free_reason === 'moved_up')
    return t('Kostenfrei: innerhalb von 48 Stunden nach dem Nachrücken von der Warteliste.')
  if (Number(q.fee) <= 0) return t('Es fällt keine Stornogebühr an.')
  if (q.percent > 0)
    return t('Stornogebühr: {fee} ({percent} % von {base} nach den Teilnahmebedingungen).', {
      fee: euro(q.fee),
      percent: q.percent,
      base: euro(q.base),
    })
  return t('Stornogebühr: {fee} (Bearbeitungsgebühr).', { fee: euro(q.fee) })
}

export interface CancelChoice {
  participants: number[]
  reason: string
  waive: boolean
}

/** Abmelden ganz oder für einzelne Personen, mit Vorschau der Gebühr. */
export function CancelPanel({
  reg,
  offer,
  board,
  quote,
  onConfirm,
  onClose,
}: {
  reg: Registration
  offer: Offer
  board: boolean
  quote: (participants: number[]) => Promise<FeeQuote>
  onConfirm: (choice: CancelChoice) => Promise<void>
  onClose: () => void
}) {
  const active = reg.participants.filter((p) => p.status === 'active')
  const [chosen, setChosen] = useState<number[]>(active.map((p) => p.id))
  const [reason, setReason] = useState('')
  const [waive, setWaive] = useState(false)
  const [preview, setPreview] = useState<FeeQuote | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const whole = chosen.length === active.length
  const key = chosen.join(',')

  useEffect(() => {
    if (!chosen.length) return
    let alive = true
    quote(whole ? [] : chosen).then(
      (q) => alive && setPreview(q),
      (err: unknown) => alive && setError(errorMessage(err)),
    )
    return () => {
      alive = false
    }
    // quote ändert sich mit jedem Rendern; es zählt nur die Auswahl
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await onConfirm({ participants: whole ? [] : chosen, reason, waive })
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  const fee = preview ? Number(preview.fee) : 0
  return (
    <div className="card stack-sm" role="group" aria-label={tc('anmeldung', 'Abmelden')}>
      <h4>{t('Anmeldung {number} abmelden', { number: reg.number })}</h4>
      {error && <Alert kind="error">{error}</Alert>}
      {active.length > 1 && (
        <fieldset className="stack-sm">
          <legend>{t('Wer wird abgemeldet?')}</legend>
          {active.map((p) => (
            <Checkbox
              key={p.id}
              label={`${p.name} (${p.price_name}, ${euro(p.amount)})`}
              checked={chosen.includes(p.id)}
              onChange={(on) =>
                setChosen(on ? [...chosen, p.id] : chosen.filter((id) => id !== p.id))
              }
            />
          ))}
        </fieldset>
      )}
      {preview && chosen.length > 0 && (
        <p>{waive ? t('Die Gebühr wird erlassen.') : feeText(preview)}</p>
      )}
      {fee > 0 && offer.waitlist && offer.waiting > 0 && (
        <p className="muted small">
          {t('Rückt dafür jemand von der Warteliste nach, entfällt die Gebühr.')}
        </p>
      )}
      {reg.invoice && reg.paid_state !== 'waiting' && (
        <p className="muted small">
          {whole && fee <= 0
            ? Number(reg.invoice.paid) > 0
              ? t('Die Rechnung wird storniert; den gezahlten Betrag erstattet der Verein.')
              : t('Die Rechnung wird storniert.')
            : t(
                'Die Rechnung wird storniert, und es kommt eine neue Rechnung über den Rest. Schon Gezahltes wird damit verrechnet.',
              )}
        </p>
      )}
      {board && (
        <>
          <Field
            label={t('Grund (optional, steht auf der Stornorechnung)')}
            value={reason}
            maxLength={300}
            onChange={(e) => setReason(e.target.value)}
          />
          {fee > 0 && (
            <Checkbox
              label={t('Stornogebühr erlassen')}
              hint={t('nur mit Grund')}
              checked={waive}
              onChange={setWaive}
            />
          )}
        </>
      )}
      <div className="button-row">
        <button
          type="button"
          className="button button-danger"
          disabled={busy || !chosen.length || (waive && !reason.trim())}
          onClick={() => void confirm()}
        >
          {whole ? t('Verbindlich abmelden') : t('Ausgewählte abmelden')}
        </button>
        <button type="button" className="button button-ghost" onClick={onClose}>
          {t('Abbrechen')}
        </button>
      </div>
    </div>
  )
}

export interface SubstituteChoice {
  membership_id: number | null
  name: string
  birth_date: string | null
}

/** Ersatzperson zum selben Tarif und Preis. Mitglieder wählen aus der Familie oder nennen einen
 * Gast, die Verwaltung sucht ein Mitglied oder nennt einen Namen. */
export function SubstitutePanel({
  participant,
  offer,
  family,
  orgId,
  onConfirm,
  onClose,
}: {
  participant: Participant
  offer: Offer
  family?: { membership_id: number; name: string; has_birth_date: boolean }[]
  orgId?: number
  onConfirm: (choice: SubstituteChoice) => Promise<void>
  onClose: () => void
}) {
  const [member, setMember] = useState<string>('')
  const [picked, setPicked] = useState<PickedMember | null>(null)
  const [name, setName] = useState('')
  const [birth, setBirth] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const price = offer.prices.find((p) => p.id === participant.price_id)
  const ageRule = !!price && (price.age_from !== null || price.age_to !== null)
  const fromFamily = family?.find((f) => String(f.membership_id) === member)
  const membershipId = fromFamily?.membership_id ?? picked?.id ?? null
  const needsBirth = ageRule && (fromFamily ? !fromFamily.has_birth_date : !picked)
  const guestOk = !family || offer.guests_allowed

  async function confirm() {
    setBusy(true)
    setError(null)
    try {
      await onConfirm({
        membership_id: membershipId,
        name: membershipId ? '' : name.trim(),
        birth_date: needsBirth && birth ? birth : null,
      })
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="card stack-sm" role="group" aria-label={t('Ersatzperson')}>
      <h4>{t('Ersatzperson für {name}', { name: participant.name })}</h4>
      <p className="muted small">
        {t('Tarif und Preis bleiben, die Rechnung auch: {price}, {amount}', {
          price: participant.price_name,
          amount: euro(participant.amount),
        })}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      {family && family.length > 0 && (
        <SelectField
          label={t('Ersatzperson')}
          value={member}
          onChange={(e) => setMember(e.target.value)}
        >
          {guestOk && <option value="">{t('ein Gast (Name eingeben)')}</option>}
          {!guestOk && <option value="">{t('bitte wählen …')}</option>}
          {family.map((f) => (
            <option key={f.membership_id} value={f.membership_id}>
              {f.name}
            </option>
          ))}
        </SelectField>
      )}
      {orgId !== undefined && (
        <MemberPicker
          orgId={orgId}
          value={picked}
          label={t('Mitglied (optional)')}
          onChange={setPicked}
        />
      )}
      {!membershipId && guestOk && (
        <Field
          label={t('Name')}
          value={name}
          maxLength={200}
          onChange={(e) => setName(e.target.value)}
        />
      )}
      {needsBirth && (
        <Field
          label={t('Geburtsdatum')}
          type="date"
          value={birth}
          onChange={(e) => setBirth(e.target.value)}
        />
      )}
      <div className="button-row">
        <button
          type="button"
          className="button"
          disabled={busy || (!membershipId && !name.trim())}
          onClick={() => void confirm()}
        >
          {t('Ersatzperson eintragen')}
        </button>
        <button type="button" className="button button-ghost" onClick={onClose}>
          {t('Abbrechen')}
        </button>
      </div>
    </div>
  )
}
