import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { bookingApi } from '../../api/bookings.ts'
import type { BookableItem, Booking, Occurrence } from '../../api/bookings.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { locale, t, tn } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import './bookings.css'
import {
  addDays,
  addMonths,
  dayKey,
  daysOf,
  monday,
  monthStart,
  noon,
  span,
  time,
} from './format.ts'
import { NoAccessPage } from '../NoticePages.tsx'
import { BookingDetail } from './BookingDetail.tsx'
import { BookingForm } from './BookingForm.tsx'

const VIEWS = ['woche', 'monat', 'jahr'] as const
type View = (typeof VIEWS)[number]

export function BookingsPage() {
  const { active, activeDept } = useOrg()
  const permissions = active?.permissions ?? activeDept?.permissions ?? []
  const modules = active
    ? active.modules
    : [
        ...(activeDept?.material_enabled ? ['material'] : []),
        ...(activeDept?.infrastructure_enabled ? ['infrastructure'] : []),
      ]
  const allowed =
    (modules.includes('material') &&
      (permissions.includes('material.view') || permissions.includes('bookings.view'))) ||
    (modules.includes('infrastructure') &&
      (permissions.includes('infrastructure.view') || permissions.includes('bookings.view')))
  if (!allowed) return <NoAccessPage reason="right" />
  const base = active
    ? `/api/orgs/${active.id}/bookings/`
    : `/api/depts/${activeDept!.id}/bookings/`
  return <Bookings key={base} base={base} />
}

function Bookings({ base }: { base: string }) {
  const [params, setParams] = useSearchParams()
  const [today] = useState(() => dayKey(new Date()))
  const view: View = VIEWS.includes(params.get('ansicht') as View)
    ? (params.get('ansicht') as View)
    : 'woche'
  const anchor = params.get('ab') ?? today
  const from =
    view === 'woche'
      ? monday(anchor)
      : view === 'monat'
        ? monthStart(anchor)
        : `${anchor.slice(0, 4)}-01-01`
  const until =
    view === 'woche'
      ? addDays(from, 7)
      : view === 'monat'
        ? addMonths(from, 1)
        : addMonths(from, 12)
  const step = (n: number) =>
    view === 'woche' ? addDays(from, 7 * n) : addMonths(from, view === 'monat' ? n : 12 * n)
  const only = Number(params.get('objekt')) || null
  const items = useLoad(() => bookingApi.items(base), [base])
  const query = new URLSearchParams({ start: from, end: until })
  if (only) query.set('item', String(only))
  const list = useLoad(() => bookingApi.list(base, query.toString()), [base, query.toString()])
  const [selected, setSelected] = useState<{ id: number; original: string } | null>(null)
  // Aus dem Material-Bedarf: ?buchen=1&objekt=…&termin=…&titel=…[&vorkommen=…]
  const [demand] = useState(() =>
    params.get('buchen') === '1' && params.get('termin')
      ? {
          kind: 'event' as const,
          choice: { id: Number(params.get('termin')), title: params.get('titel') ?? '' },
          occurrence: params.get('vorkommen') ?? undefined,
        }
      : undefined,
  )
  const [creating, setCreating] = useState(params.get('buchen') === '1')
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const reload = async () => {
    await list.reload()
  }
  const all = items.data?.items ?? []
  const parent = all.find((i) => i.id === only)?.facility ?? null
  // Ein Gebäude zeigt seine Bereiche, ein Bereich das Gebäude
  const rows = all.filter((i) => !only || i.id === only || i.facility === only || i.id === parent)
  const days: string[] = []
  if (view !== 'jahr') for (let d = from; d < until; d = addDays(d, 1)) days.push(d)
  const months = Array.from({ length: 12 }, (_, i) => addMonths(from, i))
  const occurrences = list.data?.occurrences ?? []
  // Wer das ganze Gebäude bucht, belegt auch die Bereiche
  const onItem = (o: Occurrence, item: BookableItem) =>
    o.item === item.id || o.item === item.facility
  const label =
    view === 'woche'
      ? `${noon(from).toLocaleDateString(locale(), { timeZone: 'UTC' })} – ${noon(
          addDays(until, -1),
        ).toLocaleDateString(locale(), { timeZone: 'UTC' })}`
      : view === 'monat'
        ? noon(from).toLocaleDateString(locale(), {
            timeZone: 'UTC',
            month: 'long',
            year: 'numeric',
          })
        : from.slice(0, 4)
  const names = {
    woche: [t('Vorige Woche'), t('Nächste Woche')],
    monat: [t('Voriger Monat'), t('Nächster Monat')],
    jahr: [t('Voriges Jahr'), t('Nächstes Jahr')],
  }[view]
  const bookable = (items.data?.items ?? []).filter((i) => i.can_book)
  return (
    <div className="bookings">
      <PageHeader
        primary={
          bookable.length > 0 ? { label: t('Buchen'), onClick: () => setCreating(true) } : null
        }
      />
      {items.error && <p role="alert">{items.error}</p>}
      {items.data && items.data.items.length === 0 && (
        <p>
          {t(
            'Noch kein Objekt hat einen Buchungskalender. Er lässt sich auf der Detailseite von Infrastruktur oder Material einschalten.',
          )}
        </p>
      )}
      {creating && (
        <BookingForm
          base={base}
          items={bookable}
          initialItem={only ?? undefined}
          initialLink={demand}
          onDone={async (saved) => {
            setCreating(false)
            if (saved) await reload()
          }}
        />
      )}
      {!!list.data?.requests.length && (
        <section className="card">
          <h2>{t('Offene Anfragen')}</h2>
          {list.data.requests.map((b) => (
            <Decision key={b.id} base={base} booking={b} onChanged={reload} />
          ))}
        </section>
      )}
      <div className="card booking-toolbar">
        <div className="button-row">
          <button className="button button-ghost" onClick={() => set('ab', step(-1))}>
            {names[0]}
          </button>
          <button className="button button-ghost" onClick={() => set('ab', '')}>
            {t('Heute')}
          </button>
          <button className="button button-ghost" onClick={() => set('ab', step(1))}>
            {names[1]}
          </button>
        </div>
        <div className="segmented" role="group" aria-label={t('Ansicht')}>
          {VIEWS.map((v) => (
            <button
              key={v}
              type="button"
              className={`button ${v === view ? 'button-primary' : 'button-ghost'}`}
              aria-pressed={v === view}
              onClick={() => set('ansicht', v === 'woche' ? '' : v)}
            >
              {{ woche: t('Woche'), monat: t('Monat'), jahr: t('Jahr') }[v]}
            </button>
          ))}
        </div>
        <label className="inline-label">
          {t('Objekt')}
          <select value={only ?? ''} onChange={(e) => set('objekt', e.target.value)}>
            <option value="">{t('Alle')}</option>
            {items.data?.items.map((i) => (
              <option key={i.id} value={i.id}>
                {i.title}
              </option>
            ))}
          </select>
        </label>
      </div>
      {list.error && <p role="alert">{list.error}</p>}
      <h2 className="booking-period">{label}</h2>
      {rows.length > 0 && view !== 'jahr' && (
        <div className="booking-scroll">
          <table className={`booking-grid${view === 'monat' ? ' booking-grid-month' : ''}`}>
            <caption className="visually-hidden">
              {view === 'woche' ? t('Belegung dieser Woche') : t('Belegung im {x}', { x: label })}
            </caption>
            <thead>
              <tr>
                <th scope="col">{t('Objekt')}</th>
                {days.map((d) => (
                  <th scope="col" key={d} className={d === today ? 'booking-today' : ''}>
                    {view === 'woche'
                      ? noon(d).toLocaleDateString(locale(), {
                          timeZone: 'UTC',
                          weekday: 'short',
                          day: 'numeric',
                          month: 'numeric',
                        })
                      : noon(d).toLocaleDateString(locale(), {
                          timeZone: 'UTC',
                          weekday: 'narrow',
                          day: 'numeric',
                        })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id}>
                  <th scope="row">
                    <Link
                      to={`${item.kind === 'facility' ? '/infrastruktur' : '/material'}/${item.id}`}
                    >
                      {item.title}
                    </Link>
                  </th>
                  {days.map((d) => (
                    <td key={d}>
                      {occurrences
                        .filter(
                          (o) =>
                            onItem(o, item) &&
                            dayKey(o.starts_at) <= d &&
                            (o.all_day ? addDays(dayKey(o.ends_at), -1) : dayKey(o.ends_at)) >= d,
                        )
                        .map((o) => (
                          <OccurrenceChip
                            key={`${o.booking}-${o.original_start}`}
                            occurrence={o}
                            compact={view === 'monat'}
                            onSelect={() =>
                              setSelected({ id: o.booking, original: o.original_start })
                            }
                          />
                        ))}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 && view === 'jahr' && (
        <div className="booking-scroll">
          <table className="booking-grid booking-grid-year">
            <caption className="visually-hidden">
              {t('Belegte Tage je Monat im Jahr {x}', { x: label })}
            </caption>
            <thead>
              <tr>
                <th scope="col">{t('Objekt')}</th>
                {months.map((m) => (
                  <th
                    scope="col"
                    key={m}
                    className={m === monthStart(today) ? 'booking-today' : ''}
                  >
                    {noon(m).toLocaleDateString(locale(), { timeZone: 'UTC', month: 'short' })}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => {
                const busy = new Set(
                  occurrences.filter((o) => onItem(o, item)).flatMap((o) => daysOf(o)),
                )
                return (
                  <tr key={item.id}>
                    <th scope="row">
                      <Link
                        to={`${item.kind === 'facility' ? '/infrastruktur' : '/material'}/${item.id}`}
                      >
                        {item.title}
                      </Link>
                    </th>
                    {months.map((m) => {
                      const count = [...busy].filter((d) => d.startsWith(m.slice(0, 7))).length
                      return (
                        <td key={m}>
                          {count > 0 && (
                            <button
                              type="button"
                              className="booking-chip booking-count"
                              onClick={() => {
                                const next = new URLSearchParams(params)
                                next.set('ansicht', 'monat')
                                next.set('ab', m)
                                setParams(next, { replace: true })
                              }}
                            >
                              {tn('{n} Tag', '{n} Tage', count)}
                            </button>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <BookingDetail
          key={`${selected.id}-${selected.original}`}
          base={base}
          id={selected.id}
          original={selected.original}
          items={items.data?.items ?? []}
          onClose={() => setSelected(null)}
          onChanged={reload}
        />
      )}
    </div>
  )
}

function OccurrenceChip({
  occurrence: o,
  compact = false,
  onSelect,
}: {
  occurrence: Occurrence
  /** Monatsansicht: schmale Spalten, voller Text als Hinweis */
  compact?: boolean
  onSelect: () => void
}) {
  const when = o.all_day ? t('ganztägig') : `${time(o.starts_at)}–${time(o.ends_at)}`
  if (compact)
    return (
      <button
        type="button"
        className={`booking-chip booking-compact booking-${o.status}${o.own ? ' booking-own' : ''}`}
        title={[when, o.title, o.member_name].filter(Boolean).join(' · ')}
        onClick={onSelect}
      >
        {o.title}
      </button>
    )
  return (
    <button
      type="button"
      className={`booking-chip booking-${o.status}${o.own ? ' booking-own' : ''}`}
      onClick={onSelect}
    >
      <span>{o.all_day ? t('ganztägig') : `${time(o.starts_at)}–${time(o.ends_at)}`}</span>{' '}
      <strong>{o.title}</strong>
      {o.member_name && <span> · {o.member_name}</span>}
      {o.status === 'requested' && <span> · {t('angefragt')}</span>}
      {o.needs_review && <span> · {t('prüfen')}</span>}
    </button>
  )
}

function Decision({
  base,
  booking,
  onChanged,
}: {
  base: string
  booking: Booking
  onChanged: () => Promise<void>
}) {
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const act = async (action: 'confirm' | 'reject') => {
    setBusy(true)
    setError(null)
    try {
      await bookingApi.decide(base, booking, action)
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="booking-request">
      <div>
        <strong>{booking.item_title}</strong> · {booking.title}
        <p>
          {span(booking)}
          {booking.booked_by ? ` · ${booking.booked_by}` : ''}
          {booking.member_name ? ` · ${t('für {name}', { name: booking.member_name })}` : ''}
        </p>
        {booking.note && <p className="muted">{booking.note}</p>}
      </div>
      <div className="button-row">
        <button className="button button-primary" disabled={busy} onClick={() => act('confirm')}>
          {t('Bestätigen')}
        </button>
        <button className="button button-ghost" disabled={busy} onClick={() => act('reject')}>
          {t('Ablehnen')}
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div>
  )
}
