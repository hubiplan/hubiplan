import { useState } from 'react'
import { bookingApi } from '../../api/bookings.ts'
import type { BookableItem, Booking } from '../../api/bookings.ts'
import type { MaterialChoice } from '../../api/materials.ts'
import { errorMessage } from '../../components/forms.ts'
import { useDraftGuard } from '../../components/leaveGuard.ts'
import { t } from '../../i18n/index.ts'
import { MaterialPicker } from '../materials/MaterialPicker.tsx'
import './bookings.css'
import { ZONE, addDays, dayKey } from './format.ts'
import { stamp } from './bookingsHelpers.ts'

function local(value: string | undefined, allDay: boolean) {
  if (!value) return ''
  const d = new Date(value)
  const date = dayKey(d)
  if (allDay) return date
  return `${date}T${d.toLocaleTimeString('sv-SE', { timeZone: ZONE, hour: '2-digit', minute: '2-digit' })}`
}

export function BookingForm({
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
    member: booking?.member
      ? ({ id: booking.member, title: booking.member_name } as MaterialChoice)
      : null,
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
          if (manage) {
            if (values.member || booking?.member) payload.member = values.member?.id ?? null
            // Für ein Mitglied stehen die Kontaktdaten in der Akte, nicht noch einmal hier
            if (values.member) {
              if (Object.values(booking?.contact ?? {}).some(Boolean))
                payload.contact = { name: '', email: '', phone: '' }
            } else if (Object.values(values.contact).some(Boolean)) payload.contact = values.contact
          }
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
        <label className="field">
          <span>{t('Objekt')}</span>
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
        <label className="field">
          <span>{t('Zweck')}</span>
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
              <label className="field">
                <span>{t('Beginn')}</span>
                <input
                  required
                  type={values.all_day ? 'date' : 'datetime-local'}
                  value={values.starts_at}
                  onChange={(e) => setValues({ ...values, starts_at: e.target.value })}
                />
              </label>
              <label className="field">
                <span>{values.all_day ? t('Letzter Tag') : t('Ende')}</span>
                <input
                  required={!values.all_day}
                  type={values.all_day ? 'date' : 'datetime-local'}
                  value={values.ends_at}
                  onChange={(e) => setValues({ ...values, ends_at: e.target.value })}
                />
              </label>
              <label className="field">
                <span>{t('Wiederholung')}</span>
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
                <label className="field">
                  <span>{t('wiederholen bis')}</span>
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
        <label className="field">
          <span>{t('Sichtbarkeit')}</span>
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
        <label className="field">
          <span>{t('Notiz')}</span>
          <textarea
            maxLength={2000}
            value={values.note}
            onChange={(e) => setValues({ ...values, note: e.target.value })}
          />
        </label>
        {manage && (
          <fieldset>
            <legend>{t('Für ein Mitglied (optional)')}</legend>
            {values.member ? (
              <p className="material-selection">
                <span>{values.member.title}</span>
                <button
                  className="button button-ghost"
                  type="button"
                  onClick={() => setValues({ ...values, member: null })}
                >
                  {t('Entfernen')}
                </button>
              </p>
            ) : (
              <MaterialPicker
                base={base}
                kind="member"
                onSelect={(choice) => setValues({ ...values, member: choice })}
              />
            )}
            <p className="muted">
              {t('Die Buchung erscheint dann in der Mitgliedsakte und im Mitgliederbereich.')}
            </p>
          </fieldset>
        )}
        {manage && !values.member && (
          <fieldset>
            <legend>{t('Externe Buchung (optional)')}</legend>
            <div className="booking-times">
              {(['name', 'email', 'phone'] as const).map((key, index) => (
                <label className="field" key={key}>
                  <span>{[t('Name'), t('E-Mail'), t('Telefon')][index]}</span>
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
