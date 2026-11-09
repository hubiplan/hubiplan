// Startseiten-Kachel „Nächste Termine“.
import { useState } from 'react'
import { NewEventDialog } from './EventDialog.tsx'
import '../../pages/todos.css'
import { Link } from 'react-router-dom'
import { eventApi } from '../../api/events.ts'
import type { CalendarBase } from '../../api/events.ts'
import { useLoad } from '../forms.ts'
import { RsvpBadge } from './Rsvp.tsx'
import { addDays, berlin, formatDay, today } from './time.ts'
import { t, tc } from '../../i18n/index.ts'

export function UpcomingTile({ base }: { base: CalendarBase }) {
  const from = today()
  const {
    data: loaded,
    error,
    reload,
  } = useLoad(
    () => eventApi.upcoming(base, from, addDays(from, 90)).then((data) => ({ ...data, base })),
    [base, from],
  )
  const data = loaded?.base === base ? loaded : null
  const [creating, setCreating] = useState<CalendarBase | null>(null)
  const items = (data?.items ?? []).slice(0, 5)
  return (
    <div className="card tile upcoming-overview">
      <div className="task-overview-head">
        <h2>{t('Nächste Termine')}</h2>
      </div>
      {error && <p className="muted small">{t('Termine konnten nicht geladen werden.')}</p>}
      {data && items.length === 0 && (
        <p className="muted">{t('In den nächsten Wochen keine Termine.')}</p>
      )}
      {items.length > 0 && (
        <ul className="plain-list upcoming-list">
          {items.map((o) => {
            const s = berlin(o.starts_at)
            return (
              <li key={o.key} className={o.is_cancelled ? 'event-cancelled' : undefined}>
                <span className="muted small">
                  {formatDay(s.date)}
                  {!o.all_day && t(', {time} Uhr', { time: s.time })}
                </span>
                <div>
                  <span className="event-title">{o.title}</span>
                  {o.is_cancelled && (
                    <span className="badge badge-cancelled"> {tc('event-status', 'abgesagt')}</span>
                  )}{' '}
                  <RsvpBadge o={o} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <div className="home-tile-actions">
        {data?.can_manage && (
          <button type="button" className="button button-primary" onClick={() => setCreating(base)}>
            <span aria-hidden="true">+</span> {t('Neuer Termin')}
          </button>
        )}
        <Link to="/termine">{t('Zum Kalender')}</Link>
      </div>
      {creating === base && data?.can_manage && (
        <NewEventDialog
          base={base}
          date={today()}
          categories={data.categories}
          units={data.units}
          rsvpAllowed={data.rsvp_allowed}
          onClose={() => setCreating(null)}
          onSaved={() => {
            setCreating(null)
            void reload()
          }}
        />
      )}
    </div>
  )
}
