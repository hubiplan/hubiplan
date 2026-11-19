// Öffentliche Anmeldung zu einem Termin (konzepte/veranstaltungen-anmeldung-gebuehr.md, Stufe A4):
// Formular für Nichtmitglieder unter /anmeldung/<key>, Bestätigungslink aus der Mail unter
// /anmeldung/bestaetigen/<token> und die eigene Anmeldung unter /meine-anmeldung/<token>.
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../api/client.ts'
import { euro } from '../../api/finance.ts'
import { solveChallenge } from '../../api/admission.ts'
import { publicRegistrationApi } from '../../api/registrations.ts'
import type {
  Price,
  PublicEvent,
  PublicMine,
  PublicRegistrationForm,
} from '../../api/registrations.ts'
import { errorMessage } from '../../components/forms.ts'
import { Logo } from '../../components/Logo.tsx'
import { Alert, Checkbox, Field, Loading, SelectField } from '../../components/ui.tsx'
import { CancelPanel } from '../../components/calendar/RegistrationCancel.tsx'
import { PriceList } from '../../components/calendar/Registration.tsx'
import { ExtrasFields, HealthConsent } from '../../components/calendar/RegistrationExtras.tsx'
import {
  asksHealth,
  bookingText,
  emptyExtras,
  extrasPayload,
  extrasReady,
  extrasSum,
  isMinor,
} from '../../components/calendar/extras.ts'
import type { ExtrasState } from '../../components/calendar/extras.ts'
import { berlin, formatDay } from '../../components/calendar/time.ts'
import { lang, t, tc } from '../../i18n/index.ts'

interface Row {
  name: string
  price_id: number | ''
  birth_date: string
  extras: ExtrasState
}

const emptyRow = (name = ''): Row => ({ name, price_id: '', birth_date: '', extras: emptyExtras() })

function priceName(p: Price): string {
  return lang() === 'en' && p.name_en ? p.name_en : p.name
}

function whenText(e: PublicEvent): string {
  const s = berlin(e.starts_at)
  return e.all_day
    ? formatDay(s.date)
    : t('{x}, {time} Uhr', { x: formatDay(s.date), time: s.time })
}

function EventFacts({ event }: { event: PublicEvent }) {
  const place = [event.location, event.address].filter(Boolean).join(', ')
  return (
    <div className="stack-sm">
      <p>
        <strong>{whenText(event)}</strong>
        {place && (
          <>
            <br />
            {place}
          </>
        )}
      </p>
      {event.description && <p className="event-description">{event.description}</p>}
      {event.programme && (
        <details>
          <summary>{t('Ablauf')}</summary>
          <p className="event-description">{event.programme}</p>
        </details>
      )}
      {event.directions && (
        <p className="muted small">{t('Anfahrt: {text}', { text: event.directions })}</p>
      )}
    </div>
  )
}

function Frame({
  title,
  organization,
  logoUrl,
  children,
}: {
  title: string
  organization?: string
  logoUrl?: string | null
  children: React.ReactNode
}) {
  return (
    <main className="login-page">
      <div className="card public-photo stack-sm">
        <div className="login-logo">
          <Logo name={organization} logoUrl={logoUrl ?? null} />
        </div>
        <h1>{title}</h1>
        {organization && <p className="muted">{organization}</p>}
        {children}
      </div>
    </main>
  )
}

export function PublicRegistrationPage() {
  const key = useParams().key ?? ''
  const [form, setForm] = useState<PublicRegistrationForm | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [booker, setBooker] = useState({ name: '', email: '', phone: '', address: '' })
  const [rows, setRows] = useState<Row[]>([emptyRow()])
  const [regExtras, setRegExtras] = useState<ExtrasState>(emptyExtras)
  const [note, setNote] = useState('')
  const [terms, setTerms] = useState(false)
  const [privacy, setPrivacy] = useState(false)
  const [consent, setConsent] = useState(false)
  const [homepage, setHomepage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const solved = useRef<Promise<number> | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)

  useEffect(() => {
    let alive = true
    publicRegistrationApi
      .form(key, lang())
      .then((d) => {
        if (!alive) return
        setForm(d)
        if (d.challenge) {
          solved.current = solveChallenge(d.challenge.salt, d.challenge.difficulty)
          solved.current.catch(() => undefined)
        }
      })
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status === 404) setInvalid(true)
        else setLoadError(errorMessage(err))
      })
    return () => {
      alive = false
    }
  }, [key])

  useEffect(() => {
    if (sent) heading.current?.focus()
  }, [sent])

  if (invalid)
    return (
      <Frame title={t('Anmeldung')}>
        <Alert kind="error">
          {t('Dieses Anmeldeformular gibt es nicht oder nicht mehr. Bitte frage beim Verein nach.')}
        </Alert>
      </Frame>
    )
  if (loadError)
    return (
      <Frame title={t('Anmeldung')}>
        <Alert kind="error">{loadError}</Alert>
      </Frame>
    )
  if (!form)
    return (
      <Frame title={t('Anmeldung')}>
        <Loading />
      </Frame>
    )

  const offer = form.offer
  const event = form.event
  const prices = offer.prices.filter((p) => p.current)
  const open = offer.state === 'open' || (offer.state === 'full' && offer.waitlist)
  const needsBirth = (r: Row) =>
    !!offer.minors ||
    prices.some((p) => p.id === r.price_id && (p.age_from !== null || p.age_to !== null))
  const minor = (r: Row) => !!offer.minors && isMinor(r.birth_date, event.starts_at)
  const update = (i: number, patch: Partial<Row>) =>
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const sum = rows.reduce(
    (s, r) => {
      const p = prices.find((x) => x.id === r.price_id)
      return s + Number(p?.current?.amount ?? 0) + extrasSum(offer, r.extras)
    },
    extrasSum(offer, regExtras),
  )
  const health = asksHealth(offer) && rows.some((r) => r.extras.health.trim())
  const ready =
    booker.name.trim() !== '' &&
    booker.email.trim() !== '' &&
    rows.length > 0 &&
    rows.every(
      (r) =>
        r.name.trim() &&
        r.price_id !== '' &&
        (!needsBirth(r) || r.birth_date) &&
        extrasReady(offer, r.extras, 'person', minor(r)),
    ) &&
    extrasReady(offer, regExtras, 'registration') &&
    (!health || consent) &&
    (!offer.terms || terms) &&
    privacy

  async function submit() {
    if (!form) return
    setBusy(true)
    setError(null)
    try {
      const nonce = await (solved.current ??
        solveChallenge(form.challenge?.salt ?? '', form.challenge?.difficulty ?? 0))
      await publicRegistrationApi.submit(key, {
        ...booker,
        persons: rows.map((r) => ({
          name: r.name,
          price_id: Number(r.price_id),
          birth_date: r.birth_date || null,
          ...extrasPayload(offer, r.extras, minor(r)),
        })),
        ...extrasPayload(offer, regExtras),
        note,
        terms_accepted: terms,
        privacy_accepted: privacy,
        health_consent: health && consent,
        language: lang(),
        challenge: form.challenge?.token,
        nonce,
        homepage,
      })
      setSent(true)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (sent)
    return (
      <Frame title={event.title} organization={form.organization} logoUrl={form.logo_url}>
        <h2 ref={heading} tabIndex={-1}>
          {t('Fast geschafft')}
        </h2>
        <Alert kind="success">
          {t(
            'Wir haben dir eine E-Mail an {email} geschickt. Bitte bestätige die Anmeldung mit dem Link darin; erst dann ist sie verbindlich. Der Link gilt 24 Stunden.',
            { email: booker.email },
          )}
        </Alert>
      </Frame>
    )

  return (
    <Frame title={event.title} organization={form.organization} logoUrl={form.logo_url}>
      <EventFacts event={event} />
      <p>{offer.state_text}</p>
      {offer.free !== null && offer.state === 'open' && (
        <p className="muted small">{t('Noch {n} Plätze frei.', { n: offer.free })}</p>
      )}
      <PriceList prices={offer.prices} />
      {form.cancel_text && <p className="muted small">{form.cancel_text}</p>}
      {open && (
        <form
          className="stack-sm"
          onSubmit={(e) => {
            e.preventDefault()
            if (ready && !busy) void submit()
          }}
        >
          <h2>{t('Deine Angaben')}</h2>
          <Field
            label={t('Name')}
            value={booker.name}
            maxLength={200}
            autoComplete="name"
            required
            onChange={(e) => {
              const name = e.target.value
              // Die erste Person ist meist die anmeldende selbst
              if (rows[0] && rows[0].name === booker.name) update(0, { name })
              setBooker({ ...booker, name })
            }}
          />
          <Field
            label={t('E-Mail')}
            type="email"
            value={booker.email}
            maxLength={254}
            autoComplete="email"
            required
            onChange={(e) => setBooker({ ...booker, email: e.target.value })}
          />
          <Field
            label={t('Telefon (optional)')}
            type="tel"
            value={booker.phone}
            maxLength={50}
            autoComplete="tel"
            onChange={(e) => setBooker({ ...booker, phone: e.target.value })}
          />
          <Field
            label={t('Anschrift für die Rechnung (optional)')}
            value={booker.address}
            maxLength={1000}
            autoComplete="street-address"
            onChange={(e) => setBooker({ ...booker, address: e.target.value })}
          />
          <h2>{t('Wer nimmt teil?')}</h2>
          {rows.map((r, i) => (
            <fieldset key={i} className="stack-sm">
              <legend>{t('Person {n}', { n: i + 1 })}</legend>
              <Field
                label={t('Name')}
                value={r.name}
                maxLength={200}
                required
                onChange={(e) => update(i, { name: e.target.value })}
              />
              <SelectField
                label={t('Tarif')}
                value={String(r.price_id)}
                onChange={(e) =>
                  update(i, { price_id: e.target.value ? Number(e.target.value) : '' })
                }
              >
                <option value="">{t('bitte wählen …')}</option>
                {prices.map((p) => (
                  <option key={p.id} value={p.id}>
                    {priceName(p)} – {euro(p.current?.amount)}
                  </option>
                ))}
              </SelectField>
              {needsBirth(r) && (
                <Field
                  label={t('Geburtsdatum')}
                  type="date"
                  value={r.birth_date}
                  required
                  onChange={(e) => update(i, { birth_date: e.target.value })}
                />
              )}
              <ExtrasFields
                offer={offer}
                per="person"
                state={r.extras}
                who={rows.length > 1 ? r.name : undefined}
                minor={minor(r)}
                onChange={(extras) => update(i, { extras })}
              />
              {rows.length > 1 && (
                <div className="button-row">
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  >
                    {t('Entfernen')}
                  </button>
                </div>
              )}
            </fieldset>
          ))}
          {rows.length < offer.max_persons && (
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setRows([...rows, emptyRow()])}
              >
                <span aria-hidden="true">+</span> {t('Weitere Person')}
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
          {/* Honigtopf: für Menschen unsichtbar */}
          <div className="sr-only" aria-hidden="true">
            <label>
              {t('Webseite')}
              <input
                tabIndex={-1}
                autoComplete="off"
                value={homepage}
                onChange={(e) => setHomepage(e.target.value)}
              />
            </label>
          </div>
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
          <details>
            <summary>{t('Datenschutzhinweis')}</summary>
            <p className="small">{form.privacy_text}</p>
          </details>
          <Checkbox
            label={t('Ich habe den Datenschutzhinweis gelesen.')}
            checked={privacy}
            onChange={setPrivacy}
          />
          <p>{t('Summe: {sum}', { sum: euro(sum) })}</p>
          {error && <Alert kind="error">{error}</Alert>}
          <div className="button-row">
            <button type="submit" className="button button-primary" disabled={busy || !ready}>
              {offer.state === 'full'
                ? t('Auf die Warteliste')
                : sum > 0
                  ? t('Zahlungspflichtig anmelden')
                  : t('Verbindlich anmelden')}
            </button>
          </div>
          <p className="muted small">
            {t('Du bekommst eine E-Mail mit einem Link; erst damit ist die Anmeldung verbindlich.')}
          </p>
        </form>
      )}
    </Frame>
  )
}

/** Bestätigungslink aus der Mail: einmal bestätigen, dann weiter zur eigenen Anmeldung */
export function PublicRegistrationConfirmPage() {
  const token = useParams().token ?? ''
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    publicRegistrationApi
      .confirm(token)
      .then((d) => {
        if (d.token)
          navigate(`/meine-anmeldung/${encodeURIComponent(d.token)}?neu=1`, { replace: true })
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404)
          setError(
            t(
              'Diesen Link gibt es nicht mehr. Er gilt 24 Stunden und nur einmal; die Bestätigung mit dem Link zu deiner Anmeldung kam per E-Mail.',
            ),
          )
        else setError(errorMessage(err))
      })
  }, [token, navigate])

  return (
    <Frame title={t('Anmeldung bestätigen')}>
      {error ? <Alert kind="error">{error}</Alert> : <Loading />}
    </Frame>
  )
}

/** Eigene Anmeldung über den Link aus der Mail: Stand, Rechnung, abmelden */
export function PublicMyRegistrationPage() {
  const token = useParams().token ?? ''
  const [search] = useSearchParams()
  const fresh = search.get('neu') === '1'
  const [data, setData] = useState<PublicMine | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [cancelling, setCancelling] = useState(false)

  useEffect(() => {
    let alive = true
    publicRegistrationApi
      .mine(token)
      .then((d) => alive && setData(d))
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status === 404) setInvalid(true)
        else setError(errorMessage(err))
      })
    return () => {
      alive = false
    }
  }, [token])

  if (invalid)
    return (
      <Frame title={t('Deine Anmeldung')}>
        <Alert kind="error">
          {t(
            'Diesen Link gibt es nicht mehr. Ein halbes Jahr nach der Veranstaltung werden die Angaben gelöscht.',
          )}
        </Alert>
      </Frame>
    )
  if (!data)
    return (
      <Frame title={t('Deine Anmeldung')}>
        {error ? <Alert kind="error">{error}</Alert> : <Loading />}
      </Frame>
    )
  const reg = data.registration
  return (
    <Frame title={data.event.title} organization={data.organization}>
      <EventFacts event={data.event} />
      {fresh && reg.status === 'registered' && (
        <Alert kind="success">
          {t(
            'Danke, du bist verbindlich angemeldet. Die Bestätigung mit der Rechnung kommt per E-Mail.',
          )}
        </Alert>
      )}
      {fresh && reg.status === 'waiting' && (
        <Alert kind="success">
          {t('Du stehst auf der Warteliste. Die Bestätigung kommt per E-Mail.')}
        </Alert>
      )}
      {notice && <Alert kind="success">{notice}</Alert>}
      {error && <Alert kind="error">{error}</Alert>}
      <h2>{t('Anmeldung {number}', { number: reg.number })}</h2>
      <p>
        <strong>
          {reg.status === 'cancelled'
            ? t('abgemeldet')
            : reg.status === 'waiting'
              ? t('Warteliste')
              : t('angemeldet')}
        </strong>
      </p>
      {reg.waitlist_position !== null && (
        <p className="muted small">
          {t(
            'Du stehst auf Platz {n} der Warteliste. Wird ein Platz frei, rückst du automatisch verbindlich nach und bekommst die Rechnung per E-Mail.',
            { n: reg.waitlist_position },
          )}
        </p>
      )}
      <ul className="plain-list">
        {reg.participants.map((p) => (
          <li key={p.id}>
            {p.status === 'cancelled' ? <s>{p.name}</s> : p.name}: {p.price_name}, {euro(p.amount)}
            {p.bookings?.length ? ` · ${bookingText(p.bookings)}` : ''}
          </li>
        ))}
      </ul>
      {reg.bookings?.length ? <p className="small">{bookingText(reg.bookings)}</p> : null}
      {reg.invoice && reg.status !== 'cancelled' && (
        <p className="small">
          {t('Rechnung {number} über {total}, zahlbar bis {due}', {
            number: reg.invoice.number,
            total: euro(reg.invoice.total),
            due: formatDay(reg.invoice.due_date, false),
          })}
        </p>
      )}
      {Number(reg.cancel_fee) > 0 && (
        <p className="small">{t('Stornogebühr {fee}', { fee: euro(reg.cancel_fee) })}</p>
      )}
      {reg.has_tickets && (
        <p>
          <a className="button button-ghost" href={publicRegistrationApi.ticketsUrl(token)}>
            {t('Eintrittskarten (PDF)')}
          </a>
        </p>
      )}
      {data.cancel_text && <p className="muted small">{data.cancel_text}</p>}
      {cancelling ? (
        <CancelPanel
          reg={reg}
          offer={data.offer}
          board={false}
          quote={(ids) => publicRegistrationApi.quote(token, ids)}
          onConfirm={async (choice) => {
            try {
              setData(await publicRegistrationApi.cancel(token, choice.participants))
              setCancelling(false)
              setNotice(t('Abgemeldet. Die Bestätigung kommt per E-Mail.'))
            } catch (err) {
              setError(errorMessage(err))
            }
          }}
          onClose={() => setCancelling(false)}
        />
      ) : (
        reg.status !== 'cancelled' &&
        reg.can_cancel && (
          <div className="button-row">
            <button type="button" className="button" onClick={() => setCancelling(true)}>
              {tc('anmeldung', 'Abmelden')}
            </button>
          </div>
        )
      )}
      {reg.status !== 'cancelled' && !reg.can_cancel && (
        <p className="muted small">
          {t('Abmelden geht jetzt nur noch über den Verein. Antworte dafür auf die Bestätigung.')}
        </p>
      )}
    </Frame>
  )
}
