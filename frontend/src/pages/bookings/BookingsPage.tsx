import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client.ts'
import { bookingApi } from '../../api/bookings.ts'
import type { BookableItem, Booking, Occurrence } from '../../api/bookings.ts'
import type { MaterialChoice } from '../../api/materials.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { HowTo, Term } from '../../learning/Aids.tsx'
import { locale, t } from '../../i18n/index.ts'
import { useOrg } from '../../org/OrgContext.tsx'
import { MaterialPicker } from '../materials/MaterialsPage.tsx'
import { PageHeader } from '../../components/PageHeader.tsx'
import { Loading } from '../../components/ui.tsx'
import './bookings.css'

const ZONE = 'Europe/Berlin'

// Tag in deutscher Zeit als JJJJ-MM-TT
function dayKey(value: Date | string) {
  return new Date(value).toLocaleDateString('sv-SE', { timeZone: ZONE })
}

function noon(key: string) {
  return new Date(key + 'T12:00:00Z')
}

function addDays(key: string, days: number) {
  const d = new Date(`${key}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

function monday(key: string) {
  const d = new Date(`${key}T12:00:00Z`)
  return addDays(key, -((d.getUTCDay() + 6) % 7))
}

function time(value: string) {
  return new Date(value).toLocaleTimeString(locale(), {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusLabel(status: string) {
  return (
    {
      requested: t('angefragt'),
      confirmed: t('bestätigt'),
      rejected: t('abgelehnt'),
      cancelled: t('storniert'),
    }[status] ?? status
  )
}

function span(row: { starts_at: string; ends_at: string; all_day: boolean }) {
  if (row.all_day) {
    const last = addDays(dayKey(row.ends_at), -1)
    const first = dayKey(row.starts_at)
    const fmt = (k: string) =>
      new Date(`${k}T12:00:00Z`).toLocaleDateString(locale(), { timeZone: 'UTC' })
    return first === last ? `${fmt(first)} · ${t('ganztägig')}` : `${fmt(first)} – ${fmt(last)}`
  }
  const start = new Date(row.starts_at).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  })
  return dayKey(row.starts_at) === dayKey(row.ends_at)
    ? `${start} – ${time(row.ends_at)}`
    : `${start} – ${new Date(row.ends_at).toLocaleString(locale(), {
        timeZone: ZONE,
        dateStyle: 'short',
        timeStyle: 'short',
      })}`
}

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
  if (!allowed) return <p>{t('Dafür fehlt dir die Berechtigung.')}</p>
  const base = active
    ? `/api/orgs/${active.id}/bookings/`
    : `/api/depts/${activeDept!.id}/bookings/`
  return <Bookings key={base} base={base} />
}

function Bookings({ base }: { base: string }) {
  const [params, setParams] = useSearchParams()
  const [today] = useState(() => dayKey(new Date()))
  const from = monday(params.get('ab') ?? today)
  const until = addDays(from, 7)
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
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i))
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
          <button className="button button-ghost" onClick={() => set('ab', addDays(from, -7))}>
            {t('Vorige Woche')}
          </button>
          <button className="button button-ghost" onClick={() => set('ab', '')}>
            {t('Heute')}
          </button>
          <button className="button button-ghost" onClick={() => set('ab', addDays(from, 7))}>
            {t('Nächste Woche')}
          </button>
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
      {rows.length > 0 && (
        <div className="booking-scroll">
          <table className="booking-grid">
            <caption className="visually-hidden">{t('Belegung dieser Woche')}</caption>
            <thead>
              <tr>
                <th scope="col">{t('Objekt')}</th>
                {days.map((d) => (
                  <th scope="col" key={d} className={d === today ? 'booking-today' : ''}>
                    {noon(d).toLocaleDateString(locale(), {
                      timeZone: 'UTC',
                      weekday: 'short',
                      day: 'numeric',
                      month: 'numeric',
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
                      {(list.data?.occurrences ?? [])
                        .filter(
                          (o) =>
                            // Wer das ganze Gebäude bucht, belegt auch die Bereiche
                            (o.item === item.id || o.item === item.facility) &&
                            dayKey(o.starts_at) <= d &&
                            (o.all_day ? addDays(dayKey(o.ends_at), -1) : dayKey(o.ends_at)) >= d,
                        )
                        .map((o) => (
                          <OccurrenceChip
                            key={`${o.booking}-${o.original_start}`}
                            occurrence={o}
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
  onSelect,
}: {
  occurrence: Occurrence
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={`booking-chip booking-${o.status}${o.own ? ' booking-own' : ''}`}
      onClick={onSelect}
    >
      <span>{o.all_day ? t('ganztägig') : `${time(o.starts_at)}–${time(o.ends_at)}`}</span>{' '}
      <strong>{o.title}</strong>
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

function BookingDetail({
  base,
  id,
  original,
  items,
  onClose,
  onChanged,
}: {
  base: string
  id: number
  original: string
  items: BookableItem[]
  onClose: () => void
  onChanged: () => Promise<void>
}) {
  const { data, error, reload } = useLoad(() => bookingApi.get(base, id), [base, id])
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setFailure(null)
    try {
      await fn()
      await reload()
      await onChanged()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  if (error)
    return (
      <section className="card" aria-live="polite">
        <p>{t('Diese Buchung ist belegt; Einzelheiten sind nur für die Verwaltung sichtbar.')}</p>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </section>
    )
  if (!data) return <Loading />
  if (editing)
    return (
      <BookingForm
        base={base}
        items={items}
        booking={data}
        onDone={async (saved) => {
          setEditing(false)
          if (saved) {
            await reload()
            await onChanged()
          }
        }}
      />
    )
  const active = data.status === 'requested' || data.status === 'confirmed'
  return (
    <section className="card booking-detail" aria-live="polite">
      <div className="page-heading">
        <h2>{data.title}</h2>
        <button className="button button-ghost" onClick={onClose}>
          {t('Schließen')}
        </button>
      </div>
      <p>
        {data.item_title} · {statusLabel(data.status)}
      </p>
      <p>{span(data)}</p>
      {data.repeat !== 'none' && (
        <p>
          {
            {
              weekly: t('wöchentlich'),
              monthly: t('monatlich'),
              yearly: t('jährlich'),
            }[data.repeat]
          }
          {data.repeat_until ? ` · ${t('bis {date}', { date: data.repeat_until })}` : ''}
        </p>
      )}
      {data.event_title && (
        <p>
          {t('Termin')}: <Link to={`/termine?termin=${data.event}`}>{data.event_title}</Link>
        </p>
      )}
      {data.competition_title && (
        <p>
          {t('Wettbewerb')}: {data.competition_title}
        </p>
      )}
      {data.note && <p>{data.note}</p>}
      {(data.contact.name || data.contact.email || data.contact.phone) && (
        <p>
          {t('Extern')}:{' '}
          {[data.contact.name, data.contact.email, data.contact.phone].filter(Boolean).join(' · ')}
        </p>
      )}
      {data.booked_by && (
        <p className="muted">{t('Gebucht von {name}', { name: data.booked_by })}</p>
      )}
      {data.needs_review && (
        <p role="status">
          {t(
            'Termin oder Rüstzeit haben sich geändert und die neue Zeit ist nicht frei. Bitte prüfen.',
          )}
        </p>
      )}
      {data.loan && data.status === 'confirmed' && (
        <Handover base={base} booking={data} busy={busy} act={act} />
      )}
      {failure && <p role="alert">{failure}</p>}
      {active && (
        <div className="button-row">
          {data.can_manage && data.status === 'requested' && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => act(() => bookingApi.decide(base, data, 'confirm'))}
            >
              {t('Bestätigen')}
            </button>
          )}
          {data.can_manage && data.status === 'requested' && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.decide(base, data, 'reject'))}
            >
              {t('Ablehnen')}
            </button>
          )}
          {data.can_cancel && !data.event && !data.competition && (
            <button className="button" disabled={busy} onClick={() => setEditing(true)}>
              {t('Bearbeiten')}
            </button>
          )}
          {data.can_cancel && data.repeat !== 'none' && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.skip(base, data, original))}
            >
              {t('Nur diesen Termin absagen')}
            </button>
          )}
          {data.can_cancel && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.decide(base, data, 'cancel'))}
            >
              {data.repeat !== 'none' ? t('Ganze Serie stornieren') : t('Buchung stornieren')}
            </button>
          )}
        </div>
      )}
      {data.can_cancel && data.exceptions.length > 0 && (
        <details>
          <summary>{t('Abgesagte Termine')}</summary>
          <ul>
            {data.exceptions.map((e) => (
              <li key={e}>
                {span({ starts_at: e, ends_at: e, all_day: data.all_day })}{' '}
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => act(() => bookingApi.skip(base, data, e, true))}
                >
                  {t('Wieder aufnehmen')}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

function stamp(value: string) {
  return new Date(value).toLocaleString(locale(), {
    timeZone: ZONE,
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

function Handover({
  base,
  booking,
  busy,
  act,
}: {
  base: string
  booking: Booking
  busy: boolean
  act: (fn: () => Promise<unknown>) => Promise<void>
}) {
  const [update, setUpdate] = useState(false)
  const [condition, setCondition] = useState('ready')
  const [note, setNote] = useState('')
  const out = booking.handed_out_at
  const back = booking.returned_at
  return (
    <div className="booking-handover">
      <h3>
        <Term k="loan">{t('Ausleihe')}</Term>
      </h3>
      {out ? (
        <p>
          {t('Ausgegeben am {date}', { date: stamp(out) })}
          {booking.handed_out_by ? ` · ${booking.handed_out_by}` : ''}
        </p>
      ) : (
        <p>{t('Noch nicht ausgegeben.')}</p>
      )}
      {back && (
        <p>
          {t('Zurückgegeben am {date}', { date: stamp(back) })}
          {booking.returned_by ? ` · ${booking.returned_by}` : ''}
        </p>
      )}
      {booking.can_manage && out && !back && (
        <fieldset disabled={busy}>
          <label className="checkbox">
            <input type="checkbox" checked={update} onChange={(e) => setUpdate(e.target.checked)} />{' '}
            {t('Zustand des Materials bei der Rückgabe übernehmen')}
          </label>
          {update && (
            <>
              <label>
                {t('Zustand')}
                <select value={condition} onChange={(e) => setCondition(e.target.value)}>
                  <option value="ready">{t('Einsatzbereit')}</option>
                  <option value="limited">{t('Eingeschränkt nutzbar')}</option>
                  <option value="defective">{t('Defekt')}</option>
                </select>
              </label>
              <label>
                {t('Hinweis zum Zustand')}
                <input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
              </label>
            </>
          )}
        </fieldset>
      )}
      {booking.can_manage && (
        <div className="button-row">
          {!out && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() => act(() => bookingApi.handover(base, booking, 'out'))}
            >
              {t('Ausgabe bestätigen')}
            </button>
          )}
          {out && !back && (
            <button
              className="button button-primary"
              disabled={busy}
              onClick={() =>
                act(() =>
                  bookingApi.handover(
                    base,
                    booking,
                    'return',
                    update ? { update_item: true, condition, condition_note: note } : {},
                  ),
                )
              }
            >
              {t('Rückgabe bestätigen')}
            </button>
          )}
          {out && (
            <button
              className="button button-ghost"
              disabled={busy}
              onClick={() => act(() => bookingApi.handover(base, booking, 'undo'))}
            >
              {back ? t('Rückgabe zurücknehmen') : t('Ausgabe zurücknehmen')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function local(value: string | undefined, allDay: boolean) {
  if (!value) return ''
  const d = new Date(value)
  const date = dayKey(d)
  if (allDay) return date
  return `${date}T${d.toLocaleTimeString('sv-SE', { timeZone: ZONE, hour: '2-digit', minute: '2-digit' })}`
}

function BookingForm({
  base,
  items,
  booking,
  initialItem,
  initialLink,
  onDone,
}: {
  base: string
  items: BookableItem[]
  booking?: Booking
  initialItem?: number
  initialLink?: {
    kind: 'event' | 'competition'
    choice: MaterialChoice
    occurrence?: string
  }
  onDone: (saved: boolean) => Promise<void>
}) {
  const allDay = booking?.all_day ?? false
  const lastDay = booking && allDay ? addDays(dayKey(booking.ends_at), -1) : undefined
  const initial = {
    item: booking?.item ?? initialItem ?? items[0]?.id ?? 0,
    title: booking?.title ?? '',
    all_day: allDay,
    starts_at: local(booking?.starts_at, allDay),
    ends_at: lastDay ?? local(booking?.ends_at, allDay),
    repeat: booking?.repeat ?? 'none',
    repeat_until: booking?.repeat_until ?? '',
    visibility: booking?.visibility ?? 'members',
    note: booking?.note ?? '',
    contact: { name: '', email: '', phone: '', ...(booking?.contact ?? {}) },
  }
  const [values, setValues] = useState(initial)
  const [link, setLink] = useState<{
    kind: 'event' | 'competition'
    choice: MaterialChoice
    occurrence?: string
  } | null>(initialLink ?? null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  useDraftGuard(!saved && JSON.stringify(values) !== JSON.stringify(initial), () =>
    setValues(initial),
  )
  const item = items.find((i) => i.id === values.item)
  const manage = item?.can_manage ?? false
  return (
    <form
      className="card booking-form"
      onSubmit={async (e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        try {
          const payload: Record<string, unknown> = {
            item: values.item,
            title: values.title,
            note: values.note,
            visibility: values.visibility,
          }
          if (link) {
            payload[link.kind] = link.choice.id
            if (link.occurrence) payload.occurrence = link.occurrence
          } else {
            payload.all_day = values.all_day
            payload.starts_at = values.all_day
              ? `${values.starts_at}T00:00:00`
              : `${values.starts_at}:00`
            payload.ends_at = values.all_day
              ? `${values.ends_at || values.starts_at}T00:00:00`
              : `${values.ends_at}:00`
            payload.repeat = values.repeat
            payload.repeat_until =
              values.repeat !== 'none' && values.repeat_until ? values.repeat_until : null
          }
          if (manage && Object.values(values.contact).some(Boolean))
            payload.contact = values.contact
          if (booking) await bookingApi.update(base, booking, payload)
          else await bookingApi.create(base, payload)
          setSaved(true)
          await onDone(true)
        } catch (err) {
          setError(errorMessage(err))
        } finally {
          setBusy(false)
        }
      }}
    >
      <h2>{booking ? t('Buchung bearbeiten') : t('Buchen')}</h2>
      <fieldset disabled={busy}>
        <label>
          {t('Objekt')}
          <select
            value={values.item}
            disabled={!!booking}
            onChange={(e) => setValues({ ...values, item: Number(e.target.value) })}
          >
            {items.map((i) => (
              <option key={i.id} value={i.id}>
                {i.title}
              </option>
            ))}
          </select>
        </label>
        {item?.rules.approval && !manage && (
          <p className="muted">
            {t('Dieses Objekt braucht eine Freigabe; die Buchung ist zunächst eine Anfrage.')}
          </p>
        )}
        {!booking && (
          <details open={!!initialLink}>
            <summary>{t('Zeit aus einem Termin oder Wettbewerb übernehmen')}</summary>
            {link ? (
              <p className="material-selection">
                <span>
                  {link.choice.title}
                  {link.occurrence ? ` · ${stamp(link.occurrence)}` : ''}
                </span>
                <button className="button button-ghost" type="button" onClick={() => setLink(null)}>
                  {t('Entfernen')}
                </button>
              </p>
            ) : (
              <>
                <p className="muted">
                  {t('Die Buchung folgt dann dem Termin, wenn er verschoben oder abgesagt wird.')}
                </p>
                <MaterialPicker
                  base={base}
                  kind="event"
                  onSelect={(choice) => setLink({ kind: 'event', choice })}
                />
                <MaterialPicker
                  base={base}
                  kind="competition"
                  onSelect={(choice) => setLink({ kind: 'competition', choice })}
                />
              </>
            )}
          </details>
        )}
        <label>
          {t('Zweck')}
          <input
            required={!link}
            maxLength={200}
            value={values.title}
            onChange={(e) => setValues({ ...values, title: e.target.value })}
          />
        </label>
        {!link && (
          <>
            <label>
              <input
                type="checkbox"
                checked={values.all_day}
                onChange={(e) =>
                  setValues({
                    ...values,
                    all_day: e.target.checked,
                    starts_at: values.starts_at.slice(0, 10),
                    ends_at: values.ends_at.slice(0, 10),
                  })
                }
              />{' '}
              {t('ganztägig')}
            </label>
            <div className="booking-times">
              <label>
                {t('Beginn')}
                <input
                  required
                  type={values.all_day ? 'date' : 'datetime-local'}
                  value={values.starts_at}
                  onChange={(e) => setValues({ ...values, starts_at: e.target.value })}
                />
              </label>
              <label>
                {values.all_day ? t('Letzter Tag') : t('Ende')}
                <input
                  required={!values.all_day}
                  type={values.all_day ? 'date' : 'datetime-local'}
                  value={values.ends_at}
                  onChange={(e) => setValues({ ...values, ends_at: e.target.value })}
                />
              </label>
              <label>
                {t('Wiederholung')}
                <select
                  value={values.repeat}
                  onChange={(e) =>
                    setValues({ ...values, repeat: e.target.value as Booking['repeat'] })
                  }
                >
                  <option value="none">{t('einmalig')}</option>
                  <option value="weekly">{t('wöchentlich')}</option>
                  <option value="monthly">{t('monatlich')}</option>
                  <option value="yearly">{t('jährlich')}</option>
                </select>
              </label>
              {values.repeat !== 'none' && (
                <label>
                  {t('wiederholen bis')}
                  <input
                    type="date"
                    value={values.repeat_until}
                    onChange={(e) => setValues({ ...values, repeat_until: e.target.value })}
                  />
                </label>
              )}
            </div>
          </>
        )}
        <label>
          {t('Sichtbarkeit')}
          <select
            value={values.visibility}
            onChange={(e) =>
              setValues({ ...values, visibility: e.target.value as Booking['visibility'] })
            }
          >
            <option value="members">{t('Mitglieder sehen den Zweck')}</option>
            <option value="public">{t('Öffentlich (auch auf der Webseite)')}</option>
            <option value="board">{t('Nur die Verwaltung sieht den Zweck')}</option>
          </select>
        </label>
        <label>
          {t('Notiz')}
          <textarea
            maxLength={2000}
            value={values.note}
            onChange={(e) => setValues({ ...values, note: e.target.value })}
          />
        </label>
        {manage && (
          <fieldset>
            <legend>{t('Externe Buchung (optional)')}</legend>
            <div className="booking-times">
              {(['name', 'email', 'phone'] as const).map((key, index) => (
                <label key={key}>
                  {[t('Name'), t('E-Mail'), t('Telefon')][index]}
                  <input
                    type={key === 'email' ? 'email' : 'text'}
                    maxLength={200}
                    value={values.contact[key] ?? ''}
                    onChange={(e) =>
                      setValues({
                        ...values,
                        contact: { ...values.contact, [key]: e.target.value },
                      })
                    }
                  />
                </label>
              ))}
            </div>
            <p className="muted">{t('Kontaktdaten sieht nur die Verwaltung.')}</p>
          </fieldset>
        )}
      </fieldset>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button className="button button-primary" disabled={busy}>
          {t('Speichern')}
        </button>
        <button
          className="button button-ghost"
          type="button"
          disabled={busy}
          onClick={() => {
            setSaved(true)
            void onDone(false)
          }}
        >
          {t('Abbrechen')}
        </button>
      </div>
    </form>
  )
}

/** Einstellungen des Buchungskalenders auf der Detailseite eines Objekts. */
export function BookingRulesCard({
  itemBase,
  item,
  editable,
  onSaved,
}: {
  itemBase: string
  item: {
    id: number
    version: number
    booking_rules?: Partial<import('../../api/bookings.ts').BookingRules>
  }
  editable: boolean
  onSaved: () => void
}) {
  const initial = {
    enabled: false,
    approval: false,
    buffer_before: 0,
    buffer_after: 0,
    horizon_days: 365,
    website: 'off' as 'off' | 'busy' | 'titles',
    portal: false,
    ...(item.booking_rules ?? {}),
  }
  const [rules, setRules] = useState(initial)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  if (!editable && !initial.enabled) return null
  return (
    <section className="card">
      <h2>{t('Buchungskalender')}</h2>
      <HowTo k="how_booking_requests" />
      {initial.enabled && (
        <p>
          <Link to={`/belegung?objekt=${item.id}`}>{t('Belegung ansehen und buchen')}</Link>
        </p>
      )}
      {editable && (
        <form
          onSubmit={async (e) => {
            e.preventDefault()
            setBusy(true)
            setError(null)
            try {
              await api.patch(`${itemBase}${item.id}/`, {
                booking_rules: rules,
                version: item.version,
              })
              onSaved()
            } catch (err) {
              setError(errorMessage(err))
            } finally {
              setBusy(false)
            }
          }}
        >
          <fieldset disabled={busy}>
            <label>
              <input
                type="checkbox"
                checked={rules.enabled}
                onChange={(e) => setRules({ ...rules, enabled: e.target.checked })}
              />{' '}
              {t('Buchungskalender einschalten')}
            </label>
            {rules.enabled && (
              <>
                <label>
                  <input
                    type="checkbox"
                    checked={rules.approval}
                    onChange={(e) => setRules({ ...rules, approval: e.target.checked })}
                  />{' '}
                  {t('Buchungen ohne Freigaberecht sind Anfragen')}
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={rules.portal}
                    onChange={(e) => setRules({ ...rules, portal: e.target.checked })}
                  />{' '}
                  {t('Mitglieder dürfen im Mitgliederbereich anfragen')}
                </label>
                <div className="booking-times">
                  <label>
                    {t('Rüstzeit vorher (Minuten)')}
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      step={5}
                      value={rules.buffer_before}
                      onChange={(e) =>
                        setRules({ ...rules, buffer_before: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    {t('Rüstzeit nachher (Minuten)')}
                    <input
                      type="number"
                      min={0}
                      max={1440}
                      step={5}
                      value={rules.buffer_after}
                      onChange={(e) => setRules({ ...rules, buffer_after: Number(e.target.value) })}
                    />
                  </label>
                  <label>
                    {t('Buchbar bis (Tage im Voraus)')}
                    <input
                      type="number"
                      min={1}
                      max={1095}
                      value={rules.horizon_days}
                      onChange={(e) => setRules({ ...rules, horizon_days: Number(e.target.value) })}
                    />
                  </label>
                  <label>
                    {t('Auf der Webseite')}
                    <select
                      value={rules.website}
                      onChange={(e) =>
                        setRules({ ...rules, website: e.target.value as typeof rules.website })
                      }
                    >
                      <option value="off">{t('nicht zeigen')}</option>
                      <option value="busy">{t('nur belegt oder frei')}</option>
                      <option value="titles">{t('mit Zweck öffentlicher Buchungen')}</option>
                    </select>
                  </label>
                </div>
              </>
            )}
            <button className="button" disabled={busy}>
              {t('Speichern')}
            </button>
          </fieldset>
          {error && <p role="alert">{error}</p>}
        </form>
      )}
    </section>
  )
}
