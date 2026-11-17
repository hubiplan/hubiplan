// Zu- und Absagen: eigene Rückmeldung, Teilnehmerliste des Vorstands, Kalender-Abo.
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { eventApi } from '../../api/events.ts'
import type {
  CalendarBase,
  EventDetail,
  FeedInfo,
  Occurrence,
  ResponseRow,
  ResponseStatus,
} from '../../api/events.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Field, Loading } from '../ui.tsx'
import { berlin, formatDay } from './time.ts'
import { confirmDialog } from '../dialog.ts'
import { useTerms } from '../../org/terms.ts'
import { t, tc, tn } from '../../i18n/index.ts'

const STATUS_LABEL: Record<ResponseStatus, string> = {
  get yes() {
    return t('Zusage')
  },
  get no() {
    return t('Absage')
  },
  get maybe() {
    return t('Vielleicht')
  },
}

function deadlineText(iso: string): string {
  const d = berlin(iso)
  return t('{x}, {time} Uhr', { x: formatDay(d.date), time: d.time })
}

/** Kennzeichen in Listen: eigene Rückmeldung oder „Rückmeldung offen“. */
export function RsvpBadge({ o }: { o: Occurrence }) {
  if (!o.rsvp_enabled || o.is_cancelled) return null
  if (o.my_response === 'yes') return <span className="badge badge-yes">{t('zugesagt')}</span>
  if (o.my_response === 'no') return <span className="badge">{t('abgesagt')}</span>
  if (o.my_response === 'maybe') return <span className="badge">{t('vielleicht')}</span>
  if (o.my_response === null)
    return <span className="badge badge-open">{t('Rückmeldung offen')}</span>
  return null
}

/** Mitgliederbereich: zu- oder absagen. */
export function MyResponsePanel({
  base,
  event,
  onChanged,
}: {
  base: CalendarBase
  event: EventDetail
  onChanged: (event: EventDetail) => void
}) {
  const info = event.rsvp
  const mine = info.mine ?? null
  const [guests, setGuests] = useState(String(mine?.guests ?? 0))
  const [note, setNote] = useState(mine?.note ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const responseAction = useRef<HTMLButtonElement>(null)
  const focusAfterWithdrawal = useRef(false)
  useLayoutEffect(() => {
    if (notice && focusAfterWithdrawal.current) {
      responseAction.current?.focus()
      focusAfterWithdrawal.current = false
    }
  }, [notice])

  async function run(action: () => Promise<EventDetail>, success: string, withdrawing = false) {
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      onChanged(await action())
      // Die Rücknahme entfernt ihren eigenen Knopf. Danach zur nächsten Antwortaktion.
      focusAfterWithdrawal.current = withdrawing
      setNotice(success)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const noteAllowed = info.note_allowed ?? true
  const send = (status: ResponseStatus) =>
    run(
      () =>
        eventApi.respond(base, event.id, {
          status,
          guests: status === 'yes' && info.guests_allowed ? Number(guests) || 0 : 0,
          note: noteAllowed ? note : '',
        }),
      status === 'yes'
        ? t('Deine Zusage ist gespeichert.')
        : status === 'maybe'
          ? t('Deine Antwort „Vielleicht“ ist gespeichert.')
          : t('Deine Absage ist gespeichert.'),
    )

  return (
    <div className="subcard stack-sm rsvp-panel">
      <strong>{t('Deine Rückmeldung')}</strong>
      <p className={notice ? 'muted small' : 'sr-only'} role="status" aria-atomic="true">
        {notice}
      </p>
      {mine ? (
        <p>
          <span className={mine.status === 'yes' ? 'badge badge-yes' : 'badge'}>
            {STATUS_LABEL[mine.status]}
          </span>
          {mine.guests > 0 && tn(' mit {n} Begleitperson', ' mit {n} Begleitpersonen', mine.guests)}
          {mine.source === 'board' && (
            <span className="muted small">{t(' (vom Vorstand eingetragen)')}</span>
          )}
          {mine.source === 'link' && (
            <span className="muted small">{t(' (über den Link in der Mail)')}</span>
          )}
          {mine.note && <span className="muted small"> · {mine.note}</span>}
        </p>
      ) : (
        <p className="muted">{t('Du hast dich noch nicht zurückgemeldet.')}</p>
      )}
      {info.deadline && (
        <p className="muted small">
          {t('Anmeldeschluss:')} {deadlineText(info.deadline)}
        </p>
      )}
      {info.free !== undefined && (
        <p className="muted small">
          {info.free > 0
            ? t('Noch {free} Plätze frei.', { free: info.free })
            : t('Alle Plätze sind vergeben.')}
        </p>
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {info.can_respond ? (
        <>
          {mine && (
            <p className="muted small">
              {t('Du kannst deine Rückmeldung bis zum Anmeldeschluss jederzeit ändern.')}
            </p>
          )}
          <div className="grid-2">
            {info.guests_allowed && (
              <Field
                label={t('Begleitpersonen')}
                type="number"
                min={0}
                max={info.max_guests}
                value={guests}
                onChange={(e) => setGuests(e.target.value)}
              />
            )}
            {noteAllowed && (
              <Field
                label={info.note_question || t('Bemerkung (optional)')}
                value={note}
                maxLength={200}
                onChange={(e) => setNote(e.target.value)}
              />
            )}
          </div>
          <div className="button-row">
            <button
              ref={responseAction}
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() => void send('yes')}
            >
              {tc('action', 'Zusagen')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => void send('no')}
            >
              {tc('action', 'Absagen')}
            </button>
            {info.maybe_allowed && (
              <button
                type="button"
                className="button button-ghost"
                disabled={busy}
                onClick={() => void send('maybe')}
              >
                {t('Vielleicht')}
              </button>
            )}
            {mine && (
              <button
                type="button"
                className="link-button"
                disabled={busy}
                onClick={() =>
                  void run(
                    () => eventApi.withdraw(base, event.id),
                    t('Deine Rückmeldung ist zurückgenommen.'),
                    true,
                  )
                }
              >
                {t('Rückmeldung zurücknehmen')}
              </button>
            )}
          </div>
        </>
      ) : (
        info.reason && <p className="muted small">{info.reason}</p>
      )}
    </div>
  )
}

/** Vorstand: Teilnehmerliste mit Eintragen von Hand und Export. */
export function ResponsesPanel({
  base,
  event,
  note,
}: {
  base: CalendarBase
  event: EventDetail
  /** Hinweis im Kopf, z. B. „Zu- und Absagen eingeschaltet“ */
  note?: string
}) {
  const tm = useTerms()
  // Seitenweise zu je 200 (Gesamtaudit 15.11., PF-28); „Weitere laden“ holt die nächste
  const [pages, setPages] = useState(1)
  const { data, error, reload } = useLoad(
    () => eventApi.responsePages(base, event.id, pages),
    [base, event.id, pages],
  )
  const [filter, setFilter] = useState('')
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const canEnter = !!event.rsvp.can_enter

  async function enter(membershipId: number, status: ResponseStatus, guests = 0, note = '') {
    setMessage(null)
    try {
      await eventApi.enterResponse(base, event.id, {
        membership_id: membershipId,
        status,
        guests,
        note,
      })
      await reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  async function remove(row: ResponseRow) {
    if (
      !(await confirmDialog({
        title: t('Rückmeldung von {name} entfernen?', { name: row.name }),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    try {
      await eventApi.removeResponse(base, event.id, row.membership_id)
      await reload()
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    }
  }

  const open = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const rows = data?.open ?? []
    return q ? rows.filter((r) => r.name.toLowerCase().includes(q)) : rows
  }, [data, filter])

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  const s = data.summary
  return (
    <section className="card event-card stack-sm responses">
      <div className="responses-head">
        <div>
          <h3 className="event-card-title">
            {t('Rückmeldungen')}
            {/* VW-13: Bezeichnung der Einheit statt fest „Zug“ */}
            {data.scope === 'department' ? t(' (nur {unit})', { unit: tm.sg }) : ''}
          </h3>
          {note && <span className="muted small">{note}</span>}
        </div>
        <span className="button-row">
          <a
            className="button button-ghost"
            href={eventApi.exportUrl(base, event.id, 'xlsx')}
            download
          >
            {t('Excel')}
          </a>
          <a
            className="button button-ghost"
            href={eventApi.exportUrl(base, event.id, 'pdf')}
            target="_blank"
            rel="noreferrer"
          >
            PDF
          </a>
        </span>
      </div>
      {/* Zahlen groß nebeneinander (Ralf 15.11.2026: Terminansicht übersichtlicher) */}
      <dl className="responses-numbers">
        <div>
          <dt>{t('Zusagen')}</dt>
          <dd>{s.yes}</dd>
        </div>
        {!!s.maybe && (
          <div>
            <dt>{t('Vielleicht')}</dt>
            <dd>{s.maybe}</dd>
          </div>
        )}
        <div>
          <dt>{t('Absagen')}</dt>
          <dd>{s.no}</dd>
        </div>
        <div>
          <dt>{t('noch offen')}</dt>
          <dd>{s.open}</dd>
        </div>
      </dl>
      {(s.guests > 0 || !!data.capacity) && (
        <p className="small">
          {s.guests > 0 &&
            t('{yes} Zusagen + {guests} Begleitpersonen = {persons} Personen', {
              yes: s.yes,
              guests: s.guests,
              persons: s.persons,
            })}
          {data.capacity
            ? (s.guests > 0 ? ' ' : '') +
              t('Höchstens {capacity} Personen.', { capacity: data.capacity })
            : ''}
        </p>
      )}
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Name')}</th>
                <th>{tm.sg}</th>
                <th>{t('Rückmeldung')}</th>
                <th>{t('Bemerkung')}</th>
                {canEnter && <th />}
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.membership_id}>
                  <td>{r.name}</td>
                  <td>{r.departments}</td>
                  <td>
                    {r.status && STATUS_LABEL[r.status]}
                    {r.guests > 0 && t(' + {guests}', { guests: r.guests })}
                    {r.source === 'board' && (
                      <span className="muted small">{t(' (Vorstand)')}</span>
                    )}
                    {r.source === 'link' && (
                      <span className="muted small">{t(' (Mail-Link)')}</span>
                    )}
                  </td>
                  <td>{r.note}</td>
                  {canEnter && (
                    <td>
                      <button type="button" className="link-button" onClick={() => remove(r)}>
                        {t('entfernen')}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.page?.more && (
        <button type="button" className="button" onClick={() => setPages((n) => n + 1)}>
          {t('Weitere laden ({n} von {total})', {
            n: data.items.length + data.open.length,
            total:
              data.summary.yes + data.summary.no + (data.summary.maybe ?? 0) + data.summary.open,
          })}
        </button>
      )}
      {data.open.length > 0 && (
        <details className="responses-open">
          <summary>
            {t('Noch keine Rückmeldung ({n})', { n: data.summary.open })}
            {canEnter && t(' – hier für Mitglieder ohne Zugang eintragen')}
          </summary>
          <Field
            label={t('Mitglied suchen')}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <ul className="plain-list">
            {open.slice(0, 200).map((r) => (
              <li key={r.membership_id} className="responses-open-row">
                <span>
                  {r.name}
                  {r.departments && <span className="muted small"> · {r.departments}</span>}
                </span>
                {canEnter && (
                  <span className="button-row">
                    <button
                      type="button"
                      className="link-button"
                      aria-label={t('Zusage für {name} eintragen', { name: r.name })}
                      onClick={() => void enter(r.membership_id, 'yes')}
                    >
                      {t('Zusage')}
                    </button>
                    <button
                      type="button"
                      className="link-button"
                      aria-label={t('Absage für {name} eintragen', { name: r.name })}
                      onClick={() => void enter(r.membership_id, 'no')}
                    >
                      {t('Absage')}
                    </button>
                    {event.rsvp.maybe_allowed && (
                      <button
                        type="button"
                        className="link-button"
                        aria-label={t('„Vielleicht“ für {name} eintragen', { name: r.name })}
                        onClick={() => void enter(r.membership_id, 'maybe')}
                      >
                        {t('Vielleicht')}
                      </button>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {open.length > 200 && (
            <p className="muted small">
              {t('Weitere')} {open.length - 200} {t('– bitte die Suche nutzen.')}
            </p>
          )}
        </details>
      )}
    </section>
  )
}

/** Mitgliederbereich: persönliches Kalender-Abo. */
export function FeedPanel({ base }: { base: CalendarBase }) {
  const { data, error, setData } = useLoad(() => eventApi.feed(base), [base])
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(action: () => Promise<FeedInfo>, text: string) {
    setBusy(true)
    setMessage(null)
    try {
      setData(await action())
      setMessage({ kind: 'success', text })
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      setMessage({ kind: 'success', text: t('Link kopiert.') })
    } catch {
      setMessage({ kind: 'error', text: t('Kopieren ging nicht. Bitte den Link markieren.') })
    }
  }

  if (error) return <Alert kind="error">{error}</Alert>
  if (!data) return <Loading />
  return (
    <div className="card card-wide stack">
      <p className="muted small">
        {t(
          'Mit diesem persönlichen Link erscheinen deine Termine im Kalender von Handy oder Outlook („Kalender abonnieren“ bzw. „Kalender aus dem Internet hinzufügen“). Der Link ist nur für dich. Gib ihn nicht weiter. Du kannst ihn jederzeit erneuern, dann gilt der alte nicht mehr.',
        )}
      </p>
      {message && <Alert kind={message.kind}>{message.text}</Alert>}
      {data.active ? (
        <>
          {data.ics_url ? (
            <>
              <div className="statute-link">
                <code>{data.ics_url}</code>
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => copy(data.ics_url!)}
                >
                  {t('Link kopieren')}
                </button>
              </div>
              <p className="muted small">
                {t(
                  'Kopiere den Link jetzt. Aus Sicherheitsgründen zeigen wir ihn nur dieses eine Mal an.',
                )}
              </p>
            </>
          ) : (
            <p className="muted small">
              {t(
                'Dein Kalender-Abo ist eingerichtet. Den Link zeigen wir aus Sicherheitsgründen nur direkt nach dem Erstellen. Brauchst du ihn wieder, erstelle einen neuen Link.',
              )}
            </p>
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={async () => {
                if (
                  await confirmDialog({
                    title: t('Neuen Link erstellen?'),
                    message: t('Der alte Link gilt dann nicht mehr.'),
                    confirmLabel: t('Neuen Link erstellen'),
                    danger: false,
                  })
                ) {
                  void run(() => eventApi.renewFeed(base), t('Neuer Link erstellt.'))
                }
              }}
            >
              {t('Neuen Link erstellen')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() =>
                void run(() => eventApi.removeFeed(base), t('Das Abo ist abgeschaltet.'))
              }
            >
              {t('Abo abschalten')}
            </button>
          </div>
        </>
      ) : (
        <button
          type="button"
          className="button button-primary"
          disabled={busy}
          onClick={() => void run(() => eventApi.renewFeed(base), t('Dein Link ist bereit.'))}
        >
          {t('Persönlichen Link erstellen')}
        </button>
      )}
    </div>
  )
}
