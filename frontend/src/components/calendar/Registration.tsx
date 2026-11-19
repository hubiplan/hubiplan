// Verbindliche Anmeldung mit Teilnahmegebühr am Termin (konzepte/veranstaltungen-anmeldung-gebuehr.md,
// Stufen A1–A3): Verwaltung richtet Tarife, Preisstufen, Warteliste und Stornostaffel ein und
// sieht alle Anmeldungen, Mitglieder melden sich und ihre Familie an und ab.
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { registrationApi } from '../../api/registrations.ts'
import type {
  BoardRegistrations,
  CancelRule,
  Participant,
  Offer,
  Price,
  PriceInput,
  Registration,
  SetupInput,
  SubstituteInput,
} from '../../api/registrations.ts'
import { euro, financeApi, parseAmount } from '../../api/finance.ts'
import type { PickedMember } from '../../api/members.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, Loading, SelectField } from '../ui.tsx'
import { MemberPicker } from '../MemberPicker.tsx'
import { useRowSearch } from '../RowSearch.tsx'
import { confirmDialog } from '../dialog.ts'
import { CancelPanel, SubstitutePanel } from './RegistrationCancel.tsx'
import {
  AddOnsEditor,
  ExtrasFields,
  HealthConsent,
  QuestionsEditor,
} from './RegistrationExtras.tsx'
import {
  addonInputs,
  answerText,
  asksHealth,
  bookingText,
  cleanAddons,
  emptyExtras,
  extrasPayload,
  extrasReady,
  extrasSum,
  isMinor,
  questionInputs,
} from './extras.ts'
import type { ExtrasState } from './extras.ts'
import { berlin, formatDay, toApi } from './time.ts'
import { PaidBadge } from './PaidBadge.tsx'
import { CheckInPanel } from './CheckIn.tsx'
import { QualificationPanel } from './AfterEvent.tsx'
import { ScanLinksPanel } from './ScanLinks.tsx'
import { ClubRegistrationCard } from './ClubRegistration.tsx'
import { Modal } from '../Modal.tsx'
import { lang, t, tc } from '../../i18n/index.ts'

/** Liegt der Zeitpunkt noch in der Zukunft? */
function stillFree(iso: string): boolean {
  return Date.parse(iso) > Date.now()
}

function priceName(p: Price): string {
  return lang() === 'en' && p.name_en ? p.name_en : p.name
}

function when(iso: string): string {
  const d = berlin(iso)
  return t('{x}, {time} Uhr', { x: formatDay(d.date), time: d.time })
}

/** „29,00 € (Early Bird bis 31.03.2027, noch 5 Plätze) · danach 35,00 €“ */
function priceText(p: Price): string {
  if (!p.current) return t('nicht mehr buchbar')
  const extra: string[] = []
  if (p.current.name) extra.push(p.current.name)
  if (p.current.until_date)
    extra.push(t('bis {date}', { date: formatDay(p.current.until_date, false) }))
  if (p.current.remaining !== null)
    extra.push(t('noch {n} zu diesem Preis', { n: p.current.remaining }))
  let text = euro(p.current.amount)
  if (extra.length) text += ` (${extra.join(', ')})`
  if (p.next) text += t(' · danach {amount}', { amount: euro(p.next.amount) })
  return text
}

function conditions(p: Price): string {
  const parts: string[] = []
  if (p.applies === 'members') parts.push(t('nur Mitglieder'))
  if (p.applies === 'guests') parts.push(t('nur Gäste'))
  if (p.age_from !== null && p.age_to !== null)
    parts.push(t('{a} bis {b} Jahre', { a: p.age_from, b: p.age_to }))
  else if (p.age_from !== null) parts.push(t('ab {a} Jahren', { a: p.age_from }))
  else if (p.age_to !== null) parts.push(t('bis {b} Jahre', { b: p.age_to }))
  return parts.join(', ')
}

export function PriceList({ prices }: { prices: Price[] }) {
  return (
    <ul className="plain-list">
      {prices.map((p) => (
        <li key={p.id}>
          <strong>{priceName(p)}</strong>
          {conditions(p) && <span className="muted small"> ({conditions(p)})</span>}: {priceText(p)}
          {p.free !== null && (
            <span className="muted small"> · {t('{n} Plätze frei', { n: p.free })}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

/** Link zum öffentlichen Formular mit „Link kopieren“ (A4) */
function PublicLink({ url }: { url: string }) {
  const [note, setNote] = useState('')
  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setNote(t('Link kopiert.'))
    } catch {
      setNote(t('Kopieren ging nicht. Bitte den Link markieren.'))
    }
  }
  return (
    <p className="small">
      {t('Öffentliches Formular:')}{' '}
      <a href={url} target="_blank" rel="noreferrer">
        {url}
      </a>{' '}
      <button type="button" className="button button-ghost small" onClick={() => void copy()}>
        {t('Link kopieren')}
      </button>
      {note && <span className="muted"> {note}</span>}
    </p>
  )
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card event-card">
      <h3 className="event-card-title">{title}</h3>
      <div className="stack-sm">{children}</div>
    </section>
  )
}

export function RegistrationPanel({ base, event }: { base: CalendarBase; event: EventDetail }) {
  const info = event.registration
  if (!info) return null
  if (info.club_register && info.enabled) return <ClubRegistrationCard base={base} event={event} />
  if (info.can_register && info.enabled) return <MemberRegistrationCard base={base} event={event} />
  if (info.can_setup || info.can_view_list)
    return <BoardRegistrationCard base={base} event={event} />
  return null
}

function RegistrationTable({
  rows,
  offer,
  canEdit,
  onCancel,
  onSubstitute,
  ticketsUrl,
}: {
  rows: Registration[]
  offer: Offer
  canEdit: boolean
  ticketsUrl: (reg: Registration) => string
  onCancel: (reg: Registration) => void
  onSubstitute: (reg: Registration, p: Participant) => void
}) {
  const search = useRowSearch(
    rows,
    (r) => [r.number, r.name, r.email ?? '', ...r.participants.map((p) => p.name)].join(' '),
    t('Anmeldungen'),
  )
  return (
    <>
      {search.field}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>{t('Anmeldung')}</th>
              <th>{t('Personen')}</th>
              <th>{t('Betrag')}</th>
              <th>{t('Stand')}</th>
              <th>
                <span className="sr-only">{t('Aktionen')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {search.shown.map((reg) => (
              <tr key={reg.id}>
                <td>
                  {reg.number}
                  <div className="muted small">
                    {reg.name}
                    {reg.source_label ? ` · ${reg.source_label}` : ''}
                  </div>
                </td>
                <td>
                  {reg.participants.map((p) => (
                    <div key={p.id}>
                      {p.status === 'cancelled' ? <s>{p.name}</s> : p.name}{' '}
                      <span className="muted small">{p.price_name}</span>
                      {p.bookings?.length ? (
                        <div className="muted small">{bookingText(p.bookings)}</div>
                      ) : null}
                      {answerText(offer, p.answers) && (
                        <div className="muted small">{answerText(offer, p.answers)}</div>
                      )}
                      {p.health && (
                        <div className="muted small">
                          {t('Allergien: {text}', { text: p.health })}
                        </div>
                      )}
                      {p.guardians?.map((g, k) => (
                        <div key={k} className="muted small">
                          {t('Erziehungsberechtigt: {who}', {
                            who: [g.name, g.phone, g.email].filter(Boolean).join(', '),
                          })}
                        </div>
                      ))}
                      {canEdit && reg.status !== 'cancelled' && p.status === 'active' && (
                        <button
                          type="button"
                          className="button button-ghost small"
                          aria-label={t('Ersatzperson für {name}', { name: p.name })}
                          onClick={() => onSubstitute(reg, p)}
                        >
                          {t('Ersatzperson')}
                        </button>
                      )}
                    </div>
                  ))}
                  {reg.bookings?.length ? (
                    <div className="muted small">{bookingText(reg.bookings)}</div>
                  ) : null}
                  {answerText(offer, reg.answers) && (
                    <div className="muted small">{answerText(offer, reg.answers)}</div>
                  )}
                  {reg.note && <div className="muted small">{reg.note}</div>}
                </td>
                <td>
                  {euro(reg.total)}
                  {reg.invoice && <div className="muted small">{reg.invoice.number}</div>}
                  {Number(reg.cancel_fee) > 0 && (
                    <div className="muted small">
                      {t('Stornogebühr {fee}', { fee: euro(reg.cancel_fee) })}
                      {reg.fee_invoice ? ` · ${reg.fee_invoice.number}` : ''}
                    </div>
                  )}
                </td>
                <td>
                  <PaidBadge state={reg.paid_state} />
                  {reg.waitlist_position !== null && (
                    <div className="muted small">
                      {t('Platz {n}', { n: reg.waitlist_position })}
                    </div>
                  )}
                  {reg.moved_up_at && (
                    <div className="muted small">
                      {t('nachgerückt am {when}', { when: when(reg.moved_up_at) })}
                    </div>
                  )}
                </td>
                <td>
                  {reg.has_tickets && (
                    <a
                      className="button button-ghost"
                      href={ticketsUrl(reg)}
                      aria-label={t('Eintrittskarten von {number}', { number: reg.number })}
                    >
                      {t('Eintrittskarten')}
                    </a>
                  )}
                  {canEdit && reg.status !== 'cancelled' && (
                    <button
                      type="button"
                      className="button button-ghost"
                      onClick={() => onCancel(reg)}
                    >
                      {tc('anmeldung', 'Abmelden')}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

// --- Mitglied ---

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

function MemberRegistrationCard({ base, event }: { base: CalendarBase; event: EventDetail }) {
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
    <Card title={t('Anmeldung')}>
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
    </Card>
  )
}

// --- Verwaltung ---

function BoardRegistrationCard({ base, event }: { base: CalendarBase; event: EventDetail }) {
  const { data, error, setData, reload } = useLoad(
    () => registrationApi.board(base, event.id),
    [base, event.id],
  )
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [cancelling, setCancelling] = useState<Registration | null>(null)
  const [replacing, setReplacing] = useState<{ reg: Registration; p: Participant } | null>(null)
  const [checkIn, setCheckIn] = useState(false)
  const [qualifying, setQualifying] = useState(false)
  const [scanLinks, setScanLinks] = useState(false)
  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading small />
  const offer = data.offer
  if (editing || (!offer && editing))
    return (
      <Card title={t('Anmeldung einrichten')}>
        <SetupForm
          base={base}
          event={event}
          data={data}
          onCancel={() => setEditing(false)}
          onSaved={(next) => {
            setData(next)
            setEditing(false)
          }}
        />
      </Card>
    )
  if (!offer)
    return data.can_edit ? (
      <Card title={t('Anmeldung')}>
        {event.rsvp.enabled ? (
          <p className="muted small">
            {t(
              'Der Termin hat Zu- und Absagen. Für eine verbindliche Anmeldung mit Teilnahmegebühr diese bitte zuerst ausschalten.',
            )}
          </p>
        ) : (
          <>
            <p className="muted small">
              {t(
                'Verbindliche Anmeldung mit Tarifen, Preisstufen (z. B. Early Bird), Platzgrenze, Rechnung und Bestätigungen per E-Mail.',
              )}
            </p>
            <div className="button-row">
              <button type="button" className="button" onClick={() => setEditing(true)}>
                {t('Verbindliche Anmeldung einrichten')}
              </button>
            </div>
          </>
        )}
      </Card>
    ) : null

  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)

  const s = data.summary
  const hasRegistered = data.registrations.some((r) => r.status === 'registered')
  return (
    <Card title={t('Anmeldungen')}>
      <p>
        {offer.state_text}{' '}
        {offer.capacity !== null &&
          t('{taken} von {capacity} Plätzen belegt.', {
            taken: offer.taken,
            capacity: offer.capacity,
          })}
      </p>
      <PriceList prices={offer.prices.filter((p) => p.is_active)} />
      {offer.public_url && <PublicLink url={offer.public_url} />}
      {s && (
        <p className="muted small">
          {t('{r} Anmeldungen, {p} Personen · Summe {total}, bezahlt {paid}, offen {open}', {
            r: s.registrations,
            p: s.persons,
            total: euro(s.total),
            paid: euro(s.paid),
            open: euro(s.open),
          })}
          {s.waiting > 0 && ` · ${t('{n} auf der Warteliste', { n: s.waiting })}`}
          {Number(s.fees) > 0 && ` · ${t('Stornogebühren {fees}', { fees: euro(s.fees) })}`}
          {Number(s.refund) > 0 && ` · ${t('zu erstatten {refund}', { refund: euro(s.refund) })}`}
        </p>
      )}
      <div className="button-row">
        {data.can_edit && (
          <>
            <button type="button" className="button" onClick={() => setAdding(!adding)}>
              <span aria-hidden="true">+</span> {t('Anmeldung erfassen')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setEditing(true)}>
              {t('Einstellungen')}
            </button>
          </>
        )}
        {hasRegistered && (
          <button type="button" className="button button-ghost" onClick={() => setCheckIn(true)}>
            {t('Einlass')}
          </button>
        )}
        {hasRegistered && data.can_edit && (
          <button type="button" className="button button-ghost" onClick={() => setScanLinks(true)}>
            {t('Scan-Links für Personal')}
          </button>
        )}
        {hasRegistered && (
          <a
            className="button button-ghost"
            href={registrationApi.badgesUrl(base, event.id)}
            target="_blank"
            rel="noopener"
          >
            {t('Namensschilder (PDF)')}
          </a>
        )}
        {hasRegistered && data.can_edit && (
          <a
            className="button button-ghost"
            href={registrationApi.certificatesUrl(base, event.id)}
            target="_blank"
            rel="noopener"
          >
            {t('Teilnahmebescheinigungen (PDF)')}
          </a>
        )}
        {hasRegistered && (data.qualification_kinds?.length ?? 0) > 0 && (
          <button type="button" className="button button-ghost" onClick={() => setQualifying(true)}>
            {t('Qualifikation eintragen')}
          </button>
        )}
        {data.registrations.length > 0 && (
          <a className="button button-ghost" href={registrationApi.exportUrl(base, event.id)}>
            {t('Teilnehmerliste (Excel)')}
          </a>
        )}
        {data.registrations.length > 0 && asksHealth(offer) && (
          <a className="button button-ghost" href={registrationApi.exportUrl(base, event.id, true)}>
            {t('Liste mit Allergien (Excel)')}
          </a>
        )}
      </div>
      {checkIn && (
        <Modal
          title={t('Einlass: {title}', { title: event.title })}
          guard={false}
          onClose={() => {
            setCheckIn(false)
            void reload()
          }}
        >
          <CheckInPanel base={base} eventId={event.id} />
        </Modal>
      )}
      {scanLinks && (
        <Modal
          title={t('Scan-Links für Personal: {title}', { title: event.title })}
          guard={false}
          onClose={() => setScanLinks(false)}
        >
          <ScanLinksPanel base={base} eventId={event.id} />
        </Modal>
      )}
      {qualifying && (
        <Modal
          title={t('Qualifikation eintragen: {title}', { title: event.title })}
          guard={false}
          onClose={() => setQualifying(false)}
        >
          <QualificationPanel
            base={base}
            eventId={event.id}
            kinds={data.qualification_kinds ?? []}
            lastDay={berlin(event.ends_at ?? event.starts_at).date}
          />
        </Modal>
      )}
      {adding && (
        <BoardAddForm
          base={base}
          event={event}
          offer={offer}
          onDone={(next) => {
            setData(next)
            setAdding(false)
          }}
        />
      )}
      {cancelling && (
        <CancelPanel
          key={cancelling.id}
          reg={cancelling}
          offer={offer}
          board
          quote={(ids) => registrationApi.quote(base, event.id, cancelling.id, ids)}
          onConfirm={async (choice) => {
            setData(await registrationApi.cancel(base, event.id, cancelling.id, choice))
            setCancelling(null)
          }}
          onClose={() => setCancelling(null)}
        />
      )}
      {replacing && (
        <SubstitutePanel
          key={replacing.p.id}
          participant={replacing.p}
          offer={offer}
          orgId={orgId}
          onConfirm={async (choice) => {
            setData(
              await registrationApi.substitute(
                base,
                event.id,
                replacing.reg.id,
                replacing.p.id,
                choice,
              ),
            )
            setReplacing(null)
          }}
          onClose={() => setReplacing(null)}
        />
      )}
      {data.registrations.length > 0 && (
        <RegistrationTable
          rows={data.registrations}
          offer={offer}
          canEdit={data.can_edit}
          ticketsUrl={(reg) => registrationApi.ticketsUrl(base, event.id, reg.id)}
          onCancel={(reg) => {
            setReplacing(null)
            setCancelling(reg)
          }}
          onSubstitute={(reg, p) => {
            setCancelling(null)
            setReplacing({ reg, p })
          }}
        />
      )}
      {!data.registrations.length && <p className="muted small">{t('Noch keine Anmeldungen.')}</p>}
      <button type="button" className="button button-ghost small" onClick={() => void reload()}>
        {t('Aktualisieren')}
      </button>
    </Card>
  )
}

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

function BoardAddForm({
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

function emptyPrice(): PriceInput {
  return {
    id: null,
    name: '',
    name_en: '',
    applies: 'all',
    age_from: null,
    age_to: null,
    capacity: null,
    vat_rate: null,
    is_active: true,
    steps: [{ name: '', amount: '', until_date: null, until_count: null }],
  }
}

function num(value: string): number | null {
  return value.trim() === '' ? null : Number(value)
}

function SetupForm({
  base,
  event,
  data,
  onCancel,
  onSaved,
}: {
  base: CalendarBase
  event: EventDetail
  data: BoardRegistrations
  onCancel: () => void
  onSaved: (data: BoardRegistrations) => void
}) {
  const offer = data.offer
  const orgId = Number(/\/api\/orgs\/(\d+)\//.exec(base)?.[1] ?? 0)
  const categories = useLoad(
    () => (orgId ? financeApi.categories(orgId) : Promise.resolve([])),
    [orgId],
  )
  const close = offer ? berlin(offer.closes_at) : berlin(event.starts_at)
  const open = offer?.opens_at ? berlin(offer.opens_at) : null
  const [v, setV] = useState({
    closes_date: close.date,
    closes_time: offer ? close.time : '23:59',
    opens_date: open?.date ?? '',
    opens_time: open?.time ?? '00:00',
    is_open: offer?.is_open ?? true,
    capacity: offer?.capacity ? String(offer.capacity) : '',
    max_persons: String(offer?.max_persons ?? 6),
    guests_allowed: offer?.guests_allowed ?? true,
    due_days: String(offer?.due_days ?? 14),
    category: offer?.category ? String(offer.category) : '',
    terms: offer?.terms ?? '',
    waitlist: offer?.waitlist ?? false,
    substitute_allowed: offer?.substitute_allowed ?? true,
    cancel_fee_fixed: offer?.cancel_fee_fixed ? offer.cancel_fee_fixed.replace('.', ',') : '',
    expire_unpaid_days: offer?.expire_unpaid_days ? String(offer.expire_unpaid_days) : '',
    catering: offer?.catering ?? false,
    minors: offer?.minors ?? false,
    public: offer?.public ?? false,
    club_registration: offer?.club_registration ?? false,
  })
  const [addons, setAddons] = useState(() => addonInputs(offer))
  const [questions, setQuestions] = useState(() => questionInputs(offer))
  const healthAllowed = v.catering || addons.some((a) => a.is_active && a.kind === 'meal')
  const dropsHealth =
    !healthAllowed && (offer?.questions ?? []).some((q) => q.kind === 'health' && q.is_active)
  const [rules, setRules] = useState<CancelRule[]>(offer?.cancel_rules ?? [])
  const [prices, setPrices] = useState<PriceInput[]>(
    offer
      ? offer.prices.map((p) => ({
          id: p.id,
          name: p.name,
          name_en: p.name_en,
          applies: p.applies,
          age_from: p.age_from,
          age_to: p.age_to,
          capacity: p.capacity,
          vat_rate: p.vat_rate,
          is_active: p.is_active,
          steps: (p.steps ?? []).map((s) => ({
            name: s.name,
            amount: s.amount.replace('.', ','),
            until_date: s.until_date,
            until_count: s.until_count,
          })),
        }))
      : [emptyPrice()],
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const setPrice = (i: number, patch: Partial<PriceInput>) =>
    setPrices(prices.map((p, j) => (j === i ? { ...p, ...patch } : p)))
  const setStep = (i: number, k: number, patch: Partial<PriceInput['steps'][number]>) =>
    setPrice(i, { steps: prices[i].steps.map((s, j) => (j === k ? { ...s, ...patch } : s)) })

  async function save() {
    setBusy(true)
    setError(null)
    const input: SetupInput = {
      closes_at: toApi(v.closes_date, v.closes_time || '23:59'),
      opens_at: v.opens_date ? toApi(v.opens_date, v.opens_time || '00:00') : null,
      is_open: v.is_open,
      capacity: num(v.capacity),
      max_persons: Number(v.max_persons) || 1,
      guests_allowed: v.guests_allowed,
      due_days: Number(v.due_days) || 0,
      category: v.category ? Number(v.category) : null,
      terms: v.terms,
      waitlist: v.waitlist,
      substitute_allowed: v.substitute_allowed,
      cancel_rules: rules.filter((x) => x.days > 0),
      cancel_fee_fixed: v.cancel_fee_fixed.trim() ? parseAmount(v.cancel_fee_fixed) || '0' : null,
      expire_unpaid_days: num(v.expire_unpaid_days),
      catering: v.catering,
      minors: v.minors,
      public: v.public && event.visibility === 'public',
      ...(data.club_registration_possible ? { club_registration: v.club_registration } : {}),
      addons: cleanAddons(addons),
      questions: questions
        .filter((q) => healthAllowed || q.kind !== 'health')
        .map((q) => ({ ...q, text: q.text.trim(), choices: q.choices.filter((c) => c.trim()) })),
      prices: prices.map((p, i) => ({
        ...p,
        steps: p.steps.map((s, k) => ({
          ...s,
          amount: parseAmount(s.amount) || '0',
          // die letzte Stufe gilt bis zum Anmeldeschluss
          until_date: k === p.steps.length - 1 ? null : s.until_date || null,
          until_count: k === p.steps.length - 1 ? null : s.until_count,
        })),
        name: p.name.trim() || t('Tarif {n}', { n: i + 1 }),
      })),
    }
    try {
      onSaved(await registrationApi.save(base, event.id, input))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (
      !(await confirmDialog({
        final: false,
        title: t('Anmeldung vom Termin entfernen?'),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    try {
      await registrationApi.remove(base, event.id)
      onSaved({ ...data, offer: null, registrations: [] })
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const income = (categories.data ?? []).filter((c) => c.kind === 'income')
  return (
    <div className="stack">
      {error && <Alert kind="error">{error}</Alert>}
      {!data.can_set_prices && (
        <Alert kind="info">
          {t(
            'Preise legt fest, wer Rechnungen bearbeiten darf. Ohne dieses Recht sind nur kostenlose Tarife möglich.',
          )}
        </Alert>
      )}
      <div className="form-grid">
        <Field
          label={t('Anmeldeschluss')}
          type="date"
          value={v.closes_date}
          onChange={(e) => setV({ ...v, closes_date: e.target.value })}
        />
        <Field
          label={t('Uhrzeit')}
          type="time"
          value={v.closes_time}
          onChange={(e) => setV({ ...v, closes_time: e.target.value })}
        />
        <Field
          label={t('Anmeldung ab (optional)')}
          type="date"
          value={v.opens_date}
          onChange={(e) => setV({ ...v, opens_date: e.target.value })}
        />
        <Field
          label={t('Plätze (leer: unbegrenzt)')}
          type="number"
          min={1}
          value={v.capacity}
          onChange={(e) => setV({ ...v, capacity: e.target.value })}
        />
        <Field
          label={t('Personen je Anmeldung')}
          type="number"
          min={1}
          max={20}
          value={v.max_persons}
          onChange={(e) => setV({ ...v, max_persons: e.target.value })}
        />
        <Field
          label={t('Zahlungsziel in Tagen')}
          type="number"
          min={0}
          max={90}
          value={v.due_days}
          onChange={(e) => setV({ ...v, due_days: e.target.value })}
        />
        <SelectField
          label={t('Kategorie in der Kasse')}
          value={v.category}
          onChange={(e) => setV({ ...v, category: e.target.value })}
          hint={t('leer: Kategorie für Zahlungen aus der Einrichtung')}
        >
          <option value="">{t('Vorgabe')}</option>
          {income.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectField>
      </div>
      <Checkbox
        label={t('Mitglieder dürfen Gäste mit anmelden')}
        checked={v.guests_allowed}
        onChange={(x) => setV({ ...v, guests_allowed: x })}
      />
      {offer && (
        <Checkbox
          label={t('Anmeldung offen')}
          hint={t('ausschalten, um vor dem Anmeldeschluss zu schließen')}
          checked={v.is_open}
          onChange={(x) => setV({ ...v, is_open: x })}
        />
      )}
      <label className="field">
        <span>{t('Teilnahmebedingungen (optional)')}</span>
        <textarea
          rows={4}
          maxLength={5000}
          value={v.terms}
          onChange={(e) => setV({ ...v, terms: e.target.value })}
        />
      </label>
      <h4>{t('Warteliste und Abmeldung')}</h4>
      <Checkbox
        label={t('Warteliste, wenn alle Plätze vergeben sind')}
        hint={t(
          'Wird ein Platz frei, rückt die nächste Anmeldung automatisch verbindlich nach und bekommt die Rechnung. Nachgerückte können sich 48 Stunden lang kostenfrei abmelden.',
        )}
        checked={v.waitlist}
        onChange={(x) => setV({ ...v, waitlist: x })}
      />
      <Checkbox
        label={t('Mitglieder dürfen eine Ersatzperson eintragen')}
        hint={t('zum selben Tarif und Preis; die Rechnung bleibt')}
        checked={v.substitute_allowed}
        onChange={(x) => setV({ ...v, substitute_allowed: x })}
      />
      <p className="muted small">
        {t(
          'Stornogebühren nach den Teilnahmebedingungen: Prozent des Betrags, wenn weniger als die genannten Tage bis zum Beginn bleiben. Ohne Stufen ist das Abmelden bis zum Anmeldeschluss kostenfrei. Rückt jemand von der Warteliste nach oder wird der Termin abgesagt, entfällt die Gebühr.',
        )}
      </p>
      {rules.map((rule, i) => (
        <div key={i} className="form-grid">
          <Field
            label={t('weniger als … Tage vorher')}
            type="number"
            min={1}
            max={365}
            value={rule.days || ''}
            onChange={(e) =>
              setRules(rules.map((x, j) => (j === i ? { ...x, days: Number(e.target.value) } : x)))
            }
          />
          <Field
            label={t('Gebühr in Prozent')}
            type="number"
            min={0}
            max={100}
            value={rule.percent}
            onChange={(e) =>
              setRules(
                rules.map((x, j) => (j === i ? { ...x, percent: Number(e.target.value) } : x)),
              )
            }
          />
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setRules(rules.filter((_, j) => j !== i))}
          >
            {t('Stufe entfernen')}
          </button>
        </div>
      ))}
      <div className="button-row">
        {rules.length < 6 && (
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setRules([...rules, { days: 0, percent: 50 }])}
          >
            <span aria-hidden="true">+</span> {t('Stufe für Stornogebühr')}
          </button>
        )}
      </div>
      <div className="form-grid">
        <Field
          label={t('Bearbeitungsgebühr bei Abmeldung in € (optional)')}
          inputMode="decimal"
          hint={t('kommt dazu, sobald eine Stufe greift; ohne Stufen bei jeder Abmeldung')}
          value={v.cancel_fee_fixed}
          onChange={(e) => setV({ ...v, cancel_fee_fixed: e.target.value })}
        />
        <Field
          label={t('Unbezahlte Anmeldungen verfallen … Tage vor Beginn (optional)')}
          type="number"
          min={1}
          max={90}
          hint={t('leer: nie; der Platz geht dann an die Warteliste')}
          value={v.expire_unpaid_days}
          onChange={(e) => setV({ ...v, expire_unpaid_days: e.target.value })}
        />
      </div>
      <h4>{t('Tarife')}</h4>
      {prices.map((p, i) => (
        <fieldset key={i} className="card stack-sm">
          <legend>{p.name || t('Tarif {n}', { n: i + 1 })}</legend>
          <div className="form-grid">
            <Field
              label={t('Name')}
              value={p.name}
              maxLength={100}
              onChange={(e) => setPrice(i, { name: e.target.value })}
            />
            <Field
              label={t('Name auf Englisch (optional)')}
              value={p.name_en ?? ''}
              maxLength={100}
              onChange={(e) => setPrice(i, { name_en: e.target.value })}
            />
            <SelectField
              label={t('Gilt für')}
              value={p.applies}
              onChange={(e) => setPrice(i, { applies: e.target.value as PriceInput['applies'] })}
            >
              <option value="all">{t('alle')}</option>
              <option value="members">{t('nur Mitglieder')}</option>
              <option value="guests">{t('nur Gäste')}</option>
            </SelectField>
            <Field
              label={t('Alter von')}
              type="number"
              min={0}
              value={p.age_from ?? ''}
              onChange={(e) => setPrice(i, { age_from: num(e.target.value) })}
            />
            <Field
              label={t('Alter bis')}
              type="number"
              min={0}
              value={p.age_to ?? ''}
              onChange={(e) => setPrice(i, { age_to: num(e.target.value) })}
            />
            <Field
              label={t('Plätze in diesem Tarif (optional)')}
              type="number"
              min={1}
              value={p.capacity ?? ''}
              onChange={(e) => setPrice(i, { capacity: num(e.target.value) })}
            />
            <SelectField
              label={t('Umsatzsteuer im Preis')}
              value={p.vat_rate ? String(Number(p.vat_rate)) : ''}
              onChange={(e) => setPrice(i, { vat_rate: e.target.value || null })}
            >
              <option value="">{t('keine')}</option>
              <option value="7">7 %</option>
              <option value="19">19 %</option>
            </SelectField>
          </div>
          <p className="muted small">
            {t(
              'Preisstufen gelten nacheinander, z. B. Early Bird bis zu einem Datum oder für die ersten Plätze. Die letzte Stufe gilt bis zum Anmeldeschluss.',
            )}
          </p>
          {p.steps.map((s, k) => {
            const last = k === p.steps.length - 1
            return (
              <div key={k} className="form-grid">
                <Field
                  label={t('Stufe {n}: Name (optional)', { n: k + 1 })}
                  value={s.name}
                  maxLength={60}
                  placeholder={k === 0 && p.steps.length > 1 ? t('Early Bird') : ''}
                  onChange={(e) => setStep(i, k, { name: e.target.value })}
                />
                <Field
                  label={t('Betrag in €')}
                  inputMode="decimal"
                  value={s.amount}
                  onChange={(e) => setStep(i, k, { amount: e.target.value })}
                />
                {!last && (
                  <>
                    <Field
                      label={t('gilt bis (Datum)')}
                      type="date"
                      value={s.until_date ?? ''}
                      onChange={(e) => setStep(i, k, { until_date: e.target.value || null })}
                    />
                    <Field
                      label={t('für die ersten … Personen')}
                      type="number"
                      min={1}
                      value={s.until_count ?? ''}
                      onChange={(e) => setStep(i, k, { until_count: num(e.target.value) })}
                    />
                  </>
                )}
                {p.steps.length > 1 && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setPrice(i, { steps: p.steps.filter((_, j) => j !== k) })}
                  >
                    {t('Stufe entfernen')}
                  </button>
                )}
              </div>
            )
          })}
          <div className="button-row">
            {p.steps.length < 6 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  setPrice(i, {
                    steps: [
                      { name: '', amount: '', until_date: null, until_count: null },
                      ...p.steps,
                    ],
                  })
                }
              >
                <span aria-hidden="true">+</span> {t('Frühere Preisstufe')}
              </button>
            )}
            {prices.length > 1 && (
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setPrices(prices.filter((_, j) => j !== i))}
              >
                {t('Tarif entfernen')}
              </button>
            )}
          </div>
        </fieldset>
      ))}
      <div className="button-row">
        <button
          type="button"
          className="button button-ghost"
          onClick={() => setPrices([...prices, emptyPrice()])}
        >
          <span aria-hidden="true">+</span> {t('Tarif hinzufügen')}
        </button>
      </div>
      <h4>{t('Öffentliche Anmeldung')}</h4>
      <Checkbox
        label={t('Auch Nichtmitglieder können sich anmelden (Formular mit Link)')}
        hint={
          event.visibility === 'public'
            ? t(
                'Wer sich so anmeldet, bestätigt die E-Mail-Adresse; erst dann gilt die Anmeldung und die Rechnung kommt. Den Link zum Formular siehst du nach dem Speichern.',
              )
            : t('Nur bei Terminen mit der Sichtbarkeit „öffentlich“.')
        }
        checked={v.public && event.visibility === 'public'}
        disabled={event.visibility !== 'public'}
        onChange={(on) => setV({ ...v, public: on })}
      />
      {data.club_registration_possible && (
        <>
          <h4>{t('Sammelanmeldung')}</h4>
          <Checkbox
            label={t('Vereine melden ihre Mitglieder gesammelt an')}
            hint={t(
              'Die Vereine sehen den Termin in ihrem Kalender und melden dort Mitglieder an. Die Rechnung geht an den Verein. Die Vereine brauchen dafür das Modul Anmeldungen.',
            )}
            checked={v.club_registration}
            onChange={(on) => setV({ ...v, club_registration: on })}
          />
        </>
      )}
      <h4>{t('Zusatzleistungen und Fragen')}</h4>
      <Checkbox
        label={t('mit Verpflegung')}
        hint={t('Nur dann darf nach Allergien und Unverträglichkeiten gefragt werden.')}
        checked={v.catering}
        onChange={(on) => setV({ ...v, catering: on })}
      />
      <Checkbox
        label={t('Minderjährige möglich')}
        hint={t(
          'Fragt immer das Geburtsdatum ab; unter 18 sind Name, Telefon und E-Mail einer oder eines Erziehungsberechtigten Pflicht.',
        )}
        checked={v.minors}
        onChange={(on) => setV({ ...v, minors: on })}
      />
      <AddOnsEditor addons={addons} onChange={setAddons} canSetPrices={data.can_set_prices} />
      <QuestionsEditor
        questions={questions}
        onChange={setQuestions}
        healthAllowed={healthAllowed}
      />
      {dropsHealth && (
        <Alert kind="info">
          {t(
            'Ohne Verpflegung fällt die Frage nach Allergien weg; schon erfasste Angaben werden beim Speichern gelöscht.',
          )}
        </Alert>
      )}
      <div className="button-row">
        <button type="button" className="button" disabled={busy} onClick={() => void save()}>
          {t('Speichern')}
        </button>
        <button type="button" className="button button-ghost" onClick={onCancel}>
          {t('Abbrechen')}
        </button>
        {offer && data.registrations.length === 0 && (
          <button type="button" className="button button-danger" onClick={() => void remove()}>
            {t('Anmeldung entfernen')}
          </button>
        )}
      </div>
    </div>
  )
}
