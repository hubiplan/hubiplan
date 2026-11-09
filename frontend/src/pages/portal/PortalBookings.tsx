// Belegung im Mitgliederbereich: belegte Zeiten ansehen, Anfragen stellen und stornieren.
import { useState } from 'react'
import { portalBookingApi } from '../../api/bookings.ts'
import type { PortalOwnBooking } from '../../api/bookings.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'

const ZONE = 'Europe/Berlin'

function dayKey(value: Date | string) {
  return new Date(value).toLocaleDateString('sv-SE', { timeZone: ZONE })
}

function addDays(key: string, days: number) {
  const d = new Date(key + 'T12:00:00Z')
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

function monday(key: string) {
  const d = new Date(key + 'T12:00:00Z')
  return addDays(key, -((d.getUTCDay() + 6) % 7))
}

function when(row: { starts_at: string; ends_at: string; all_day: boolean }) {
  const opts: Intl.DateTimeFormatOptions = row.all_day
    ? { timeZone: ZONE, dateStyle: 'short' }
    : { timeZone: ZONE, dateStyle: 'short', timeStyle: 'short' }
  const end = row.all_day ? new Date(new Date(row.ends_at).getTime() - 1) : new Date(row.ends_at)
  const a = new Date(row.starts_at).toLocaleString(locale(), opts)
  const b = end.toLocaleString(locale(), opts)
  return a === b ? `${a} · ${t('ganztägig')}` : `${a} – ${b}`
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

export function PortalBookings({ accessId }: { accessId: number }) {
  const [start, setStart] = useState(() => monday(dayKey(new Date())))
  const { data, error, reload } = useLoad(
    () => portalBookingApi.list(accessId, start),
    [accessId, start],
  )
  const empty = { item: 0, title: '', all_day: false, starts_at: '', ends_at: '', note: '' }
  const [form, setForm] = useState(empty)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  if (data.items.length === 0)
    return <p className="muted">{t('Zurzeit lassen sich hier keine Objekte anfragen.')}</p>
  const item = form.item || data.items[0].id
  const cancel = async (booking: PortalOwnBooking) => {
    setBusy(true)
    setFailure(null)
    try {
      await portalBookingApi.cancel(accessId, booking)
      await reload()
    } catch (err) {
      setFailure(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <section className="card">
        <h2>{t('Belegte Zeiten')}</h2>
        <div className="button-row">
          <button className="button button-ghost" onClick={() => setStart(addDays(start, -7))}>
            {t('Vorige Woche')}
          </button>
          <button className="button button-ghost" onClick={() => setStart(addDays(start, 7))}>
            {t('Nächste Woche')}
          </button>
        </div>
        {data.items.map((i) => {
          const rows = data.occurrences.filter((o) => o.item === i.id)
          return (
            <div key={i.id}>
              <h3>{i.title}</h3>
              {rows.length ? (
                <ul>
                  {rows.map((o) => (
                    <li key={`${o.starts_at}-${o.title}`}>
                      {when(o)} · {o.title}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">{t('In dieser Woche frei.')}</p>
              )}
            </div>
          )
        })}
      </section>
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault()
          setBusy(true)
          setFailure(null)
          setSent(false)
          try {
            await portalBookingApi.request(accessId, {
              item,
              title: form.title,
              note: form.note,
              all_day: form.all_day,
              starts_at: form.all_day ? `${form.starts_at}T00:00:00` : `${form.starts_at}:00`,
              ends_at: form.all_day
                ? `${form.ends_at || form.starts_at}T00:00:00`
                : `${form.ends_at}:00`,
            })
            setForm(empty)
            setSent(true)
            await reload()
          } catch (err) {
            setFailure(errorMessage(err))
          } finally {
            setBusy(false)
          }
        }}
      >
        <h2>{t('Anfrage stellen')}</h2>
        <p className="muted">
          {t('Die Verwaltung bestätigt deine Anfrage oder lehnt sie ab; du bekommst eine E-Mail.')}
        </p>
        <fieldset disabled={busy}>
          <label>
            {t('Objekt')}
            <select
              value={item}
              onChange={(e) => setForm({ ...form, item: Number(e.target.value) })}
            >
              {data.items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.title}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t('Zweck')}
            <input
              required
              maxLength={200}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </label>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.all_day}
              onChange={(e) =>
                setForm({ ...form, all_day: e.target.checked, starts_at: '', ends_at: '' })
              }
            />{' '}
            {t('ganztägig')}
          </label>
          <label>
            {t('Beginn')}
            <input
              required
              type={form.all_day ? 'date' : 'datetime-local'}
              value={form.starts_at}
              onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
            />
          </label>
          <label>
            {t('Ende')}
            <input
              required={!form.all_day}
              type={form.all_day ? 'date' : 'datetime-local'}
              value={form.ends_at}
              onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
            />
          </label>
          <label>
            {t('Notiz')}
            <textarea
              maxLength={2000}
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
          </label>
          <button className="button button-primary" type="submit">
            {t('Anfrage senden')}
          </button>
        </fieldset>
        {sent && <p role="status">{t('Deine Anfrage ist eingegangen.')}</p>}
        {failure && <p role="alert">{failure}</p>}
      </form>
      <section className="card">
        <h2>{t('Meine Anfragen und Buchungen')}</h2>
        {data.own.length === 0 ? (
          <p className="muted">{t('Noch keine.')}</p>
        ) : (
          <ul>
            {data.own.map((b) => (
              <li key={b.id}>
                <strong>{b.title}</strong> · {b.item_title} · {when(b)} · {statusLabel(b.status)}{' '}
                {(b.status === 'requested' || b.status === 'confirmed') && (
                  <button
                    className="button button-ghost"
                    disabled={busy}
                    onClick={() => void cancel(b)}
                  >
                    {t('Buchung stornieren')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}
