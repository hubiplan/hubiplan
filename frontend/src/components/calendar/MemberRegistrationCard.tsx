import { useState } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type { Participant, Registration, SubstituteInput } from '../../api/registrations.ts'
import { euro } from '../../api/finance.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, Loading, SelectField } from '../ui.tsx'
import { CancelPanel, SubstitutePanel } from './RegistrationCancel.tsx'
import { ExtrasFields, HealthConsent } from './RegistrationExtras.tsx'
import {
  asksHealth,
  bookingText,
  emptyExtras,
  extrasPayload,
  extrasReady,
  extrasSum,
  isMinor,
} from './extras.ts'
import type { ExtrasState } from './extras.ts'
import { formatDay } from './time.ts'
import { PaidBadge } from './PaidBadge.tsx'
import { t, tc } from '../../i18n/index.ts'
import { priceName, when } from './registrationHelpers.ts'
import { PriceList } from './PriceList.tsx'
import { RegistrationCard } from './RegistrationCard.tsx'

/** Liegt der Zeitpunkt noch in der Zukunft? */
function stillFree(iso: string): boolean {
  return Date.parse(iso) > Date.now()
}

interface Pick {
  membership_id: number | null
  name: string
  price_id: number | ''
  birth_date: string
  checked: boolean
  needsBirth: boolean
  /** Mitglied ist unter 18 (vom Server) */
  minor: boolean
  extras: ExtrasState
}

/** Braucht die Person Erziehungsberechtigte? Mitglieder sagt der Server, sonst das Datum. */
function pickMinor(offer: { minors?: boolean }, r: Pick, startsAt: string): boolean {
  if (!offer.minors) return false
  return r.minor || isMinor(r.birth_date, startsAt)
}

export function MemberRegistrationCard({
  base,
  event,
}: {
  base: CalendarBase
  event: EventDetail
}) {
  const { data, error, setData } = useLoad(
    () => registrationApi.member(base, event.id),
    [base, event.id],
  )
  const [picks, setPicks] = useState<Pick[] | null>(null)
  const [note, setNote] = useState('')
  const [terms, setTerms] = useState(false)
  const [regExtras, setRegExtras] = useState<ExtrasState>(emptyExtras)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [cancelling, setCancelling] = useState<Registration | null>(null)
  const [replacing, setReplacing] = useState<{ reg: Registration; p: Participant } | null>(null)

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const offer = data.offer
  const prices = offer.prices.filter((p) => p.current)
  const rows: Pick[] =
    picks ??
    data.persons
      .filter((p) => !p.registered)
      .map((p) => ({
        membership_id: p.membership_id,
        name: p.name,
        price_id: '',
        birth_date: '',
        checked: p.self,
        needsBirth: !p.has_birth_date,
        minor: !!p.minor,
        extras: emptyExtras(),
      }))
  const update = (i: number, patch: Partial<Pick>) =>
    setPicks(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const chosen = rows.filter((r) => r.checked)
  const sum = chosen.reduce(
    (s, r) => {
      const p = prices.find((x) => x.id === r.price_id)
      return s + Number(p?.current?.amount ?? 0) + extrasSum(offer, r.extras)
    },
    extrasSum(offer, regExtras),
  )
  const health = asksHealth(offer) && chosen.some((r) => r.extras.health.trim())
  const pricesFor = (r: Pick) =>
    prices.filter((p) => (r.membership_id ? p.applies !== 'guests' : p.applies !== 'members'))

  async function submit() {
    setBusy(true)
    setMessage(null)
    try {
      const next = await registrationApi.register(base, event.id, {
        persons: chosen.map((r) => ({
          membership_id: r.membership_id,
          name: r.name,
          price_id: Number(r.price_id),
          birth_date: r.birth_date || null,
          ...extrasPayload(offer, r.extras, pickMinor(offer, r, event.starts_at)),
        })),
        note,
        terms_accepted: terms,
        ...extrasPayload(offer, regExtras),
        health_consent: health && consent,
      })
      setData(next)
      setPicks(null)
      setNote('')
      setTerms(false)
      setRegExtras(emptyExtras())
      setConsent(false)
      const waiting = next.mine[0]?.status === 'waiting'
      setMessage({
        kind: 'success',
        text: waiting
          ? t('Du stehst auf der Warteliste. Die Bestätigung kommt per E-Mail.')
          : t('Angemeldet. Die Bestätigung kommt per E-Mail.'),
      })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function cancel(reg: Registration, participants: number[]) {
    setData(await registrationApi.cancelMine(base, event.id, reg.id, participants))
    setPicks(null)
    setCancelling(null)
    setMessage({ kind: 'success', text: t('Abgemeldet. Die Bestätigung kommt per E-Mail.') })
  }

  async function replace(reg: Registration, p: Participant, choice: SubstituteInput) {
    setData(await registrationApi.substituteMine(base, event.id, reg.id, p.id, choice))
    setReplacing(null)
    setPicks(null)
    setMessage({ kind: 'success', text: t('Ersatzperson eingetragen.') })
  }

  const ready =
    chosen.length > 0 &&
    chosen.every(
      (r) =>
        r.price_id !== '' &&
        r.name.trim() &&
        (!offer.minors || !r.needsBirth || r.birth_date) &&
        extrasReady(offer, r.extras, 'person', pickMinor(offer, r, event.starts_at)),
    ) &&
    extrasReady(offer, regExtras, 'registration') &&
    (!health || consent) &&
    (!offer.terms || terms)
  return (
    <RegistrationCard title={t('Anmeldung')}>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      <p>{offer.state_text}</p>
      {offer.free !== null && offer.state === 'open' && (
        <p className="muted small">{t('Noch {n} Plätze frei.', { n: offer.free })}</p>
      )}
      <PriceList prices={offer.prices} />
      {data.mine.map((reg) => (
        <div key={reg.id} className="stack-sm">
          <div>
            <strong>{t('Deine Anmeldung {number}', { number: reg.number })}</strong>{' '}
            {reg.status === 'cancelled' ? (
              <span className="badge">{t('abgemeldet')}</span>
            ) : (
              <PaidBadge state={reg.paid_state} />
            )}
          </div>
          {reg.waitlist_position !== null && (
            <p className="muted small">
              {t(
                'Du stehst auf Platz {n} der Warteliste. Wird ein Platz frei, rückst du automatisch verbindlich nach und bekommst die Rechnung per E-Mail.',
                { n: reg.waitlist_position },
              )}
            </p>
          )}
          {reg.free_cancel_until &&
            reg.status === 'registered' &&
            stillFree(reg.free_cancel_until) && (
              <p className="muted small">
                {t('Nachgerückt: Bis {when} kannst du dich kostenfrei abmelden.', {
                  when: when(reg.free_cancel_until),
                })}
              </p>
            )}
          <ul className="plain-list">
            {reg.participants.map((p) => (
              <li key={p.id}>
                {p.status === 'cancelled' ? <s>{p.name}</s> : p.name}: {p.price_name},{' '}
                {euro(p.amount)}
                {p.bookings?.length ? ` · ${bookingText(p.bookings)}` : ''}
                {p.status === 'active' && reg.can_substitute && (
                  <>
                    {' '}
                    <button
                      type="button"
                      className="button button-ghost small"
                      aria-label={t('Ersatzperson für {name}', { name: p.name })}
                      onClick={() => setReplacing({ reg, p })}
                    >
                      {t('Ersatzperson')}
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          {replacing?.reg.id === reg.id && (
            <SubstitutePanel
              participant={replacing.p}
              offer={offer}
              family={data.persons.filter((x) => !x.registered)}
              onConfirm={(choice) => replace(reg, replacing.p, choice)}
              onClose={() => setReplacing(null)}
            />
          )}
          {Number(reg.cancel_fee) > 0 && (
            <p className="muted small">
              {t('Stornogebühr {fee}', { fee: euro(reg.cancel_fee) })}
              {reg.fee_invoice
                ? ` · ${t('Rechnung {number} über {total}, zahlbar bis {due}', {
                    number: reg.fee_invoice.number,
                    total: euro(reg.fee_invoice.total),
                    due: formatDay(reg.fee_invoice.due_date, false),
                  })}`
                : ''}
            </p>
          )}
          {reg.invoice && reg.status !== 'cancelled' && (
            <p className="muted small">
              {t('Rechnung {number} über {total}, zahlbar bis {due}', {
                number: reg.invoice.number,
                total: euro(reg.invoice.total),
                due: formatDay(reg.invoice.due_date, false),
              })}
            </p>
          )}
          {reg.has_tickets && (
            <p>
              <a
                className="button button-ghost small"
                href={registrationApi.ticketsUrl(base, event.id, reg.id)}
              >
                {t('Eintrittskarten (PDF)')}
              </a>
            </p>
          )}
          {cancelling?.id === reg.id ? (
            <CancelPanel
              reg={reg}
              offer={offer}
              board={false}
              quote={(ids) => registrationApi.quote(base, event.id, reg.id, ids)}
              onConfirm={(choice) => cancel(reg, choice.participants)}
              onClose={() => setCancelling(null)}
            />
          ) : (
            reg.status !== 'cancelled' &&
            (reg.can_cancel ?? data.can_cancel) && (
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => setCancelling(reg)}
                >
                  {tc('anmeldung', 'Abmelden')}
                </button>
              </div>
            )
          )}
        </div>
      ))}
      {(offer.state === 'open' || (offer.state === 'full' && offer.waitlist)) &&
        (rows.length > 0 || offer.guests_allowed) && (
          <div className="stack-sm">
            <h4>{t('Anmelden')}</h4>
            {rows.map((r, i) => (
              <div key={i} className="stack-sm">
                {r.membership_id ? (
                  <Checkbox
                    label={r.name}
                    checked={r.checked}
                    onChange={(x) => update(i, { checked: x })}
                  />
                ) : (
                  <div className="button-row">
                    <Field
                      label={t('Name des Gastes')}
                      value={r.name}
                      maxLength={200}
                      onChange={(e) => update(i, { name: e.target.value })}
                    />
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => setPicks(rows.filter((_, j) => j !== i))}
                    >
                      {t('Entfernen')}
                    </button>
                  </div>
                )}
                {r.checked && (
                  <SelectField
                    label={t('Tarif')}
                    value={String(r.price_id)}
                    onChange={(e) =>
                      update(i, { price_id: e.target.value ? Number(e.target.value) : '' })
                    }
                  >
                    <option value="">{t('bitte wählen …')}</option>
                    {pricesFor(r).map((p) => (
                      <option key={p.id} value={p.id}>
                        {priceName(p)} – {euro(p.current?.amount)}
                      </option>
                    ))}
                  </SelectField>
                )}
                {r.checked &&
                  (r.needsBirth || !r.membership_id) &&
                  (offer.minors ||
                    prices.find(
                      (p) => p.id === r.price_id && (p.age_from !== null || p.age_to !== null),
                    )) && (
                    <Field
                      label={t('Geburtsdatum')}
                      type="date"
                      value={r.birth_date}
                      onChange={(e) => update(i, { birth_date: e.target.value })}
                    />
                  )}
                {r.checked && (
                  <ExtrasFields
                    offer={offer}
                    per="person"
                    state={r.extras}
                    who={rows.filter((x) => x.checked).length > 1 ? r.name : undefined}
                    minor={pickMinor(offer, r, event.starts_at)}
                    onChange={(extras) => update(i, { extras })}
                  />
                )}
              </div>
            ))}
            {offer.guests_allowed && rows.length < offer.max_persons && (
              <div className="button-row">
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() =>
                    setPicks([
                      ...rows,
                      {
                        membership_id: null,
                        name: '',
                        price_id: '',
                        birth_date: '',
                        checked: true,
                        needsBirth: true,
                        minor: false,
                        extras: emptyExtras(),
                      },
                    ])
                  }
                >
                  <span aria-hidden="true">+</span> {t('Gast hinzufügen')}
                </button>
              </div>
            )}
            <ExtrasFields
              offer={offer}
              per="registration"
              state={regExtras}
              onChange={setRegExtras}
            />
            <Field
              label={t('Bemerkung (optional)')}
              value={note}
              maxLength={500}
              onChange={(e) => setNote(e.target.value)}
            />
            {health && <HealthConsent checked={consent} onChange={setConsent} />}
            {offer.terms && (
              <>
                <details>
                  <summary>{t('Teilnahmebedingungen')}</summary>
                  <p className="event-description">{offer.terms}</p>
                </details>
                <Checkbox
                  label={t('Ich habe die Teilnahmebedingungen gelesen und akzeptiere sie.')}
                  checked={terms}
                  onChange={setTerms}
                />
              </>
            )}
            <p>
              {t('Summe: {sum}', { sum: euro(sum) })}{' '}
              <span className="muted small">
                {t('Abmelden ist bis {when} möglich.', { when: when(offer.closes_at) })}
              </span>
            </p>
            <div className="button-row">
              <button
                type="button"
                className="button"
                disabled={busy || !ready}
                onClick={() => void submit()}
              >
                {offer.state === 'full'
                  ? t('Auf die Warteliste')
                  : sum > 0
                    ? t('Zahlungspflichtig anmelden')
                    : t('Verbindlich anmelden')}
              </button>
            </div>
          </div>
        )}
    </RegistrationCard>
  )
}

// --- Verwaltung ---
