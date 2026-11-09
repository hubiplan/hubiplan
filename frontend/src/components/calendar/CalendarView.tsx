// Kalender in Monats- und Listenansicht, für Vorstand, Abteilung und Mitglieder.
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useSearchParams } from 'react-router-dom'
import { eventApi } from '../../api/events.ts'
import type { CalendarBase, EventCategory, Occurrence } from '../../api/events.ts'
import { useLoad } from '../forms.ts'
import { LoadError } from '../ui.tsx'
import { PageActions } from '../PageHeader.tsx'
import { EventDialog, NewEventDialog, VisibilityBadge } from './EventDialog.tsx'
import { RsvpBadge } from './Rsvp.tsx'
import {
  MONTHS,
  WEEKDAYS,
  addDays,
  addMonths,
  berlin,
  formatDay,
  formatRange,
  monthGrid,
  monthStart,
  today,
  daysOf,
} from './time.ts'
import { t, tc } from '../../i18n/index.ts'
import { atMost, BP_MEDIUM } from '../../theme/breakpoints.ts'
import { categoryShorts } from './categories.ts'

type View = 'month' | 'list'

const VIEW_KEY = 'hubiplan.kalenderansicht'

// Zuletzt gewählte Ansicht; auf schmalen Bildschirmen sonst die Liste, weil die
// Monatsansicht dort nur Punkte zeigt.
function initialView(): View {
  try {
    const saved = localStorage.getItem(VIEW_KEY)
    if (saved === 'month' || saved === 'list') return saved
  } catch {
    // ohne Speicher: Standard
  }
  return atMost(BP_MEDIUM) ? 'list' : 'month'
}

function itemClass(o: Occurrence): string {
  return `event-item${o.is_cancelled ? ' event-cancelled' : ''}${o.all_day ? ' event-allday' : ''}`
}

function calendarContext(o: Occurrence): string {
  return [...new Set([o.owner, o.source].filter(Boolean))].join(' · ')
}

/** Beschriftung des angezeigten Tages, nicht erneut der Beginn des ganzen Termins. */
function dayTime(o: Occurrence, day: string): string {
  const start = berlin(o.starts_at)
  const end = berlin(o.ends_at)
  if (o.all_day) return day > start.date ? t('Fortsetzung · ganztägig') : t('ganztägig')
  if (day === start.date) return start.time
  if (day === end.date || (end.time === '00:00' && day === addDays(end.date, -1))) {
    return t('Fortsetzung bis {time}', { time: end.time === '00:00' ? '24:00' : end.time })
  }
  return t('Fortsetzung')
}

const NO_CATEGORY_COLOR = '#7a847f'

function eventColor(o: Occurrence): string {
  return o.category?.color ?? NO_CATEGORY_COLOR
}

function eventName(o: Occurrence, day?: string): string {
  return [
    o.title,
    calendarContext(o),
    o.category?.name ?? '',
    day ? dayTime(o, day) : '',
    formatRange(o.starts_at, o.ends_at, o.all_day),
    o.is_cancelled ? tc('event-status', 'abgesagt') : '',
  ]
    .filter(Boolean)
    .join(' · ')
}

function EventLabel({ o, day, short }: { o: Occurrence; day: string; short?: string }) {
  return (
    <>
      <span className="event-dot" style={{ background: eventColor(o) }} />
      {short && (
        <span className="event-short" aria-hidden="true">
          {short}
        </span>
      )}
      <span className="event-summary">
        <span className="event-time">{dayTime(o, day)}</span>
        <span className="event-title">{o.title}</span>
        <span className="event-context">{calendarContext(o)}</span>
        {o.category && <span className="event-context">{o.category.name}</span>}
      </span>
    </>
  )
}

/** Legende über der Monatsansicht: Farbe, Kürzel und Name jeder sichtbaren Kategorie. */
function CategoryLegend({
  categories,
  shorts,
}: {
  categories: EventCategory[]
  shorts: Map<string, string>
}) {
  if (categories.length === 0) return null
  return (
    <ul className="calendar-legend" aria-label={t('Kategorien')}>
      {categories.map((c) => (
        <li key={c.id}>
          <span className="event-dot" style={{ background: c.color }} />
          <span className="event-short" aria-hidden="true">
            {shorts.get(c.name)}
          </span>
          <span>{c.name}</span>
        </li>
      ))}
    </ul>
  )
}

export function CalendarView({
  base,
  emptyHint,
}: {
  base: CalendarBase
  /** Hinweis, wenn noch keine Termine eingetragen sind */
  emptyHint?: string
}) {
  const [view, setViewState] = useState<View>(initialView)
  function setView(v: View) {
    setViewState(v)
    try {
      localStorage.setItem(VIEW_KEY, v)
    } catch {
      // egal
    }
  }
  // Direktlink ?termin=<id>&datum=<JJJJ-MM-TT> öffnet den Termin (z. B. aus „Offene Aufgaben“)
  const [params, setParams] = useSearchParams()
  const linked = Number(params.get('termin')) || null
  const linkedDate = params.get('datum')
  const [month, setMonth] = useState(
    monthStart(linkedDate && /^\d{4}-\d{2}-\d{2}$/.test(linkedDate) ? linkedDate : today()),
  )
  const [picked, setPicked] = useState<Occurrence | null>(null)
  function setSelected(o: Occurrence | null) {
    setPicked(o)
    if (!o && linked) {
      const next = new URLSearchParams(params)
      next.delete('termin')
      next.delete('datum')
      setParams(next, { replace: true })
    }
  }
  const [creating, setCreating] = useState<string | null>(null)
  const grid = monthGrid(month)
  const from = view === 'month' ? grid[0] : month
  const to = view === 'month' ? grid[grid.length - 1] : addDays(addMonths(month, 12), -1)
  // Daten gehören zu genau einem Zeitraum: beim Blättern nie die Termine des vorigen
  // Monats unter der neuen Überschrift zeigen (UX-Audit 31.10. W02)
  const rangeKey = `${from}|${to}`
  const loaded = useLoad(
    () => eventApi.list(base, from, to).then((d) => ({ ...d, rangeKey })),
    [base, from, to],
  )
  const data = loaded.data?.rangeKey === rangeKey ? loaded.data : null
  const { error, reload } = loaded
  const selected =
    picked ?? (linked ? (data?.items.find((o) => o.event_id === linked) ?? null) : null)
  const year = Number(month.slice(0, 4))

  const byDay = new Map<string, Occurrence[]>()
  if (view === 'month') {
    for (const o of data?.items ?? []) {
      for (const d of daysOf(o, from, to)) {
        const list = byDay.get(d)
        if (list) list.push(o)
        else byDay.set(d, [o])
      }
    }
  }
  const todayIso = today()
  // Kategorien, die im angezeigten Monat vorkommen (für Kürzel und Legende)
  const monthCategories = [
    ...new Map(
      (view === 'month' ? (data?.items ?? []) : [])
        .map((o) => o.category)
        .filter((c): c is EventCategory => c !== null)
        .map((c) => [c.id, c] as const),
    ).values(),
  ]
  const shorts = categoryShorts(monthCategories.map((c) => c.name))

  return (
    <div className="calendar stack">
      <div className="calendar-toolbar">
        <div className="button-row">
          <button
            type="button"
            className="button button-ghost"
            aria-label={view === 'month' ? t('Vorheriger Monat') : t('Früher')}
            onClick={() => setMonth(addMonths(month, -1))}
          >
            ‹
          </button>
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setMonth(monthStart(todayIso))}
          >
            {t('Heute')}
          </button>
          <button
            type="button"
            className="button button-ghost"
            aria-label={view === 'month' ? t('Nächster Monat') : t('Später')}
            onClick={() => setMonth(addMonths(month, 1))}
          >
            ›
          </button>
          <strong className="calendar-title" aria-live="polite">
            {view === 'month'
              ? t('{x} {year}', { x: MONTHS[Number(month.slice(5, 7)) - 1], year })
              : t('ab {x} {year}', { x: MONTHS[Number(month.slice(5, 7)) - 1], year })}
          </strong>
        </div>
        <div className="button-row">
          <div className="segmented" role="group" aria-label={t('Ansicht')}>
            <button
              type="button"
              className={`button button-ghost${view === 'month' ? ' is-active' : ''}`}
              aria-pressed={view === 'month'}
              onClick={() => setView('month')}
            >
              {t('Monat')}
            </button>
            <button
              type="button"
              className={`button button-ghost${view === 'list' ? ' is-active' : ''}`}
              aria-pressed={view === 'list'}
              onClick={() => setView('list')}
            >
              {t('Liste')}
            </button>
          </div>
          {/* Hauptaktion und Jahresprogramm stehen im Seitenkopf (S-05, W-19) */}
          <PageActions
            primary={
              data?.can_manage
                ? {
                    label: t('Neuer Termin'),
                    onClick: () => setCreating(month === monthStart(todayIso) ? todayIso : month),
                  }
                : null
            }
            actions={[
              {
                label: t('Jahresprogramm {year} (PDF)', { year }),
                href: eventApi.programUrl(base, year),
                newTab: true,
              },
            ]}
          />
        </div>
      </div>

      {error && (
        <LoadError
          message={t('Die Termine konnten nicht geladen werden. {error}', { error })}
          onRetry={() => void reload()}
        />
      )}
      {!data && !error && (
        <p className="muted" role="status">
          {t('Termine')} {view === 'month' ? t('für') : t('ab')}{' '}
          {MONTHS[Number(month.slice(5, 7)) - 1]} {year} {t('werden geladen …')}
        </p>
      )}

      {data && view === 'month' && <CategoryLegend categories={monthCategories} shorts={shorts} />}
      {data && view === 'month' && (
        <div className="calendar-grid" role="group" aria-label={t('Monatsansicht')}>
          {WEEKDAYS.map((w) => (
            <div key={w} className="calendar-weekday" aria-hidden="true">
              {w}
            </div>
          ))}
          {grid.map((day) => {
            const items = byDay.get(day) ?? []
            const outside = day.slice(0, 7) !== month.slice(0, 7)
            return (
              <div
                key={day}
                role="group"
                className={`calendar-day${outside ? ' is-outside' : ''}${
                  day === todayIso ? ' is-today' : ''
                }`}
                aria-label={formatDay(day)}
              >
                <div className="calendar-day-head">
                  <span>{Number(day.slice(8, 10))}</span>
                  {data.can_manage && (
                    <button
                      type="button"
                      className="calendar-add"
                      aria-label={t('Neuer Termin am {x}', { x: formatDay(day) })}
                      onClick={() => setCreating(day)}
                    >
                      +
                    </button>
                  )}
                </div>
                {items.map((o) => (
                  <button
                    type="button"
                    key={`${o.key}-${day}`}
                    className={itemClass(o)}
                    style={{ '--event-color': eventColor(o) } as CSSProperties}
                    title={eventName(o, day)}
                    aria-label={eventName(o, day)}
                    onClick={() => setSelected(o)}
                  >
                    <EventLabel
                      o={o}
                      day={day}
                      short={o.category ? shorts.get(o.category.name) : undefined}
                    />
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}

      {data && view === 'list' && (
        <div className="calendar-list">
          {data.items.length === 0 && (
            <p className="muted">{emptyHint ?? t('Keine Termine in diesem Zeitraum.')}</p>
          )}
          {/* W-16: Zwischenüberschrift je Monat, damit lange Listen gegliedert sind */}
          {monthGroups(data.items).map(([key, items]) => (
            <section key={key} className="calendar-list-month">
              <h2 className="calendar-list-month-head">{monthHeading(key)}</h2>
              <ul className="plain-list">
                {items.map((o) => (
                  <li key={o.key}>
                    <button type="button" className={itemClass(o)} onClick={() => setSelected(o)}>
                      <span className="calendar-list-date">
                        {formatRange(o.starts_at, o.ends_at, o.all_day)}
                      </span>
                      <span className="calendar-list-main">
                        <span className="event-dot" style={{ background: eventColor(o) }} />{' '}
                        <strong className="event-title">{o.title}</strong>{' '}
                        <VisibilityBadge visibility={o.visibility} />
                        {o.is_cancelled && (
                          <span className="badge badge-cancelled">
                            {tc('event-status', 'abgesagt')}
                          </span>
                        )}
                        {o.changed_at && !o.is_cancelled && (
                          <span className="badge">{t('geändert')}</span>
                        )}
                        <RsvpBadge o={o} />
                        <span className="muted small">
                          {' '}
                          {[o.category?.name, o.location, calendarContext(o)]
                            .filter(Boolean)
                            .join(' · ')}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {data && data.items.length === 0 && view === 'month' && emptyHint && (
        <p className="muted small">{emptyHint}</p>
      )}

      {selected && data && (
        <EventDialog
          base={base}
          occurrence={selected}
          categories={data.categories}
          units={data.units}
          rsvpAllowed={data.rsvp_allowed}
          onClose={() => setSelected(null)}
          onChanged={() => void reload()}
        />
      )}
      {creating && data && (
        <NewEventDialog
          base={base}
          date={creating}
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

/** Termine der Liste nach Monat (Berliner Zeit) gruppiert, Schlüssel „JJJJ-MM“. */
function monthGroups(items: Occurrence[]): [string, Occurrence[]][] {
  const groups = new Map<string, Occurrence[]>()
  for (const o of items) {
    const key = berlin(o.starts_at).date.slice(0, 7)
    const list = groups.get(key)
    if (list) list.push(o)
    else groups.set(key, [o])
  }
  return [...groups.entries()]
}

function monthHeading(key: string): string {
  const [year, month] = key.split('-').map(Number)
  return t('{x} {year}', { x: MONTHS[month - 1], year })
}
