// Startseite für Mitglieder (UX-Audit S-02/10.5): oben das Häufigste – nächster Termin mit
// Zu-/Absage und „Ausweis zeigen“; eine offene Rechnung nur, wenn es eine gibt.
import { Link } from 'react-router-dom'
import { calendarBase, eventApi } from '../../api/events.ts'
import { portalBillingApi } from '../../api/billing.ts'
import type { PortalEntry } from '../../api/portal.ts'
import { useLoad } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { RsvpBadge } from '../calendar/Rsvp.tsx'
import { addDays, berlin, formatDay, today } from '../calendar/time.ts'
import { euro } from '../../api/finance.ts'
import { t, tc } from '../../i18n/index.ts'

export function MemberHomeTop({ entry }: { entry: PortalEntry }) {
  return (
    <>
      <div className="tiles home-first">
        {entry.events_enabled && <NextEventCard access={entry.id} />}
        <div className="card tile home-card-action">
          <h2>{t('Mitgliedsausweis')}</h2>
          <p className="muted small">{t('QR-Code vorzeigen oder als PDF speichern')}</p>
          <Link to="/mein-bereich/ausweis" className="button button-primary button-large">
            {t('Ausweis zeigen')}
          </Link>
        </div>
      </div>
      <OpenInvoiceNotice access={entry.id} />
    </>
  )
}

function NextEventCard({ access }: { access: number }) {
  const base = calendarBase.portal(access)
  const from = today()
  const { data, error } = useLoad(
    () => eventApi.upcoming(base, from, addDays(from, 90)),
    [base, from],
  )
  const next = data?.items.find((o) => !o.is_cancelled) ?? null
  return (
    <div className="card tile">
      <h2>{t('Nächster Termin')}</h2>
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
          <div className="button-row">
            <Link
              className="button"
              to={`/termine?termin=${next.event_id}&datum=${berlin(next.original_start).date}`}
            >
              {next.rsvp_enabled
                ? next.my_response
                  ? t('Rückmeldung ändern')
                  : t('Zu- oder absagen')
                : t('Termin öffnen')}
            </Link>
            <Link to="/termine" className="button button-ghost">
              {tc('home', 'Alle Termine')}
            </Link>
          </div>
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
