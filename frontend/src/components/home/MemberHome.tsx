// Startseite für Mitglieder (UX-Audit S-02/10.5): oben das Häufigste – nächster Termin mit
// Zu-/Absage und „Ausweis zeigen“; eine offene Rechnung nur, wenn es eine gibt.
// W-07 (UX-Audit 08.11.): eine Karte „Nächste Termine“, der nächste Termin hervorgehoben.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { calendarBase, eventApi } from '../../api/events.ts'
import type { ResponseStatus } from '../../api/events.ts'
import { portalBillingApi } from '../../api/billing.ts'
import type { PortalEntry } from '../../api/portal.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { RsvpBadge } from '../calendar/Rsvp.tsx'
import { addDays, berlin, formatDay, today } from '../calendar/time.ts'
import { euro } from '../../api/finance.ts'
import { t, tc } from '../../i18n/index.ts'

export function MemberHomeTop({ entry }: { entry: PortalEntry }) {
  // S-04: der nächste Termin mit Zu-/Absage ganz oben, auch am Handy (W-19); der Ausweis
  // steht als erste Kachel darunter
  return (
    <>
      {entry.events_enabled && (
        <div className="tiles home-first">
          <NextEventCard access={entry.id} />
        </div>
      )}
      <OpenInvoiceNotice access={entry.id} />
    </>
  )
}

function NextEventCard({ access }: { access: number }) {
  const base = calendarBase.portal(access)
  const from = today()
  const { data, error, reload } = useLoad(
    () => eventApi.upcoming(base, from, addDays(from, 90)),
    [base, from],
  )
  const next = data?.items.find((o) => !o.is_cancelled) ?? null
  const [busy, setBusy] = useState(false)
  const [rsvpError, setRsvpError] = useState<string | null>(null)
  // S-04: Zu- und Absage gleich hier, ohne den Termin zu öffnen (nicht bei Serien: dort
  // gilt die Rückmeldung je Termin, das klärt der Termin selbst)
  const quick = !!next && next.rsvp_enabled && !next.is_series && !next.my_response
  async function respond(status: ResponseStatus) {
    if (!next) return
    setBusy(true)
    setRsvpError(null)
    try {
      await eventApi.respond(base, next.event_id, { status, guests: 0, note: '' })
      await reload()
    } catch (err) {
      setRsvpError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const later = (data?.items ?? []).filter((o) => o !== next).slice(0, 3)
  return (
    <div className="card tile tile-wide">
      <h2>{t('Nächste Termine')}</h2>
      {error && <p className="muted small">{t('Termine konnten nicht geladen werden.')}</p>}
      {data && !next && <p className="muted">{t('In den nächsten Wochen keine Termine.')}</p>}
      {next && (
        <>
          <p className="home-event">
            <strong className="event-title">{next.title}</strong> <RsvpBadge o={next} />
            <br />
            <span className="muted small">
              {formatDay(berlin(next.starts_at).date)}
              {!next.all_day && t(', {time} Uhr', { time: berlin(next.starts_at).time })}
              {next.location && ` · ${next.location}`}
            </span>
          </p>
          {rsvpError && <Alert kind="error">{rsvpError}</Alert>}
          {quick && (
            <div className="button-row home-rsvp">
              <button
                type="button"
                className="button button-primary button-large"
                disabled={busy}
                onClick={() => void respond('yes')}
              >
                {t('Zusage')}
              </button>
              <button
                type="button"
                className="button button-large"
                disabled={busy}
                onClick={() => void respond('no')}
              >
                {t('Absage')}
              </button>
            </div>
          )}
          <div className="button-row">
            <Link
              className={quick ? 'button button-ghost' : 'button'}
              to={`/termine?termin=${next.event_id}&datum=${berlin(next.original_start).date}`}
            >
              {next.rsvp_enabled && next.my_response
                ? t('Rückmeldung ändern')
                : next.rsvp_enabled && !quick
                  ? t('Zu- oder absagen')
                  : t('Termin öffnen')}
            </Link>
            <Link to="/termine" className="button button-ghost">
              {tc('home', 'Alle Termine')}
            </Link>
          </div>
          {later.length > 0 && (
            <ul className="plain-list upcoming-list">
              {later.map((o) => (
                <li key={o.key} className={o.is_cancelled ? 'event-cancelled' : undefined}>
                  <span className="muted small">
                    {formatDay(berlin(o.starts_at).date)}
                    {!o.all_day && t(', {time} Uhr', { time: berlin(o.starts_at).time })}
                  </span>
                  <div>
                    <span className="event-title">{o.title}</span>
                    {o.is_cancelled && (
                      <span className="badge badge-cancelled">
                        {' '}
                        {tc('event-status', 'abgesagt')}
                      </span>
                    )}{' '}
                    <RsvpBadge o={o} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

function OpenInvoiceNotice({ access }: { access: number }) {
  const { data } = useLoad(() => portalBillingApi.invoices(access), [access])
  const open = (data?.invoices ?? []).filter(
    (i) => Number(i.outstanding) > 0 && i.status === 'open',
  )
  if (open.length === 0) return null
  const sum = open.reduce((s, i) => s + Number(i.outstanding), 0)
  return (
    <Alert kind={open.some((i) => i.overdue) ? 'error' : 'info'}>
      {open.length === 1
        ? t('Eine Rechnung ist offen ({x}).', { x: euro(sum.toFixed(2)) })
        : t('{n} Rechnungen sind offen ({x}).', { n: open.length, x: euro(sum.toFixed(2)) })}{' '}
      <Link to="/mein-bereich/rechnungen">{t('Ansehen')}</Link>
    </Alert>
  )
}
