// Termin ansehen; mit Recht auch bearbeiten, einzelne Serientermine ändern, Anhänge.
import { RouteLinks } from './RouteLinks.tsx'
import { EventTaskLink } from '../TodoEventLink.tsx'
import { Link, useNavigate } from 'react-router-dom'
import { useOptionalOrg } from '../../org/OrgContext.tsx'
import { MaterialReferences } from '../MaterialReferences.tsx'
import { useRef, useState } from 'react'
import { eventApi } from '../../api/events.ts'
import type {
  CalendarBase,
  EventCategory,
  EventDetail,
  EventUnit,
  Occurrence,
} from '../../api/events.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Field, Loading } from '../ui.tsx'
import { EventForm } from './EventForm.tsx'
import { MyResponsePanel, ResponsesPanel } from './Rsvp.tsx'
import { EventProjectPanel } from './EventProject.tsx'
import { EventDocumentLink } from './EventDocumentLink.tsx'
import { berlin, formatDay, formatRange, toApi } from './time.ts'
import { alertDialog, confirmDialog, promptDialog } from '../dialog.ts'
import { circularApi } from '../../api/circulars.ts'
import { Modal } from '../Modal.tsx'
import type { CloseGuard } from './EventForm.tsx'
import { t } from '../../i18n/index.ts'

export { Modal }

const MAX_BYTES = 15 * 1024 * 1024

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? t('{x} MB', { x: (bytes / 1024 / 1024).toFixed(1).replace('.', ',') })
    : t('{x} KB', { x: Math.max(1, Math.round(bytes / 1024)) })
}

export function VisibilityBadge({ visibility }: { visibility: string }) {
  if (visibility === 'members') return null
  return (
    <span className={`badge badge-${visibility}`}>
      {visibility === 'public' ? t('öffentlich') : t('nur Vorstand')}
    </span>
  )
}

function MusicLink({ eventId }: { eventId: number }) {
  const org = useOptionalOrg()?.active
  return org?.modules.includes('music') && org.permissions.includes('music.view') ? (
    <Link to={`/musik?art=performances&termin=${eventId}`}>{t('Auftritt planen')}</Link>
  ) : null
}

/** Rundschreiben zum Termin: an die Eingeladenen, mit den PDF-Anhängen des Termins. */
function CircularLinks({ base, event }: { base: string; event: EventDetail }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const rows = event.circulars
  if (rows === undefined || (rows.length === 0 && !event.can_circular)) return null
  const write = async (reminder = false) => {
    setBusy(true)
    setError(null)
    try {
      const created = await circularApi.fromEvent(`${base}circulars/`, event.id, reminder)
      if (created.skipped_attachments?.length)
        await alertDialog(
          t('Nicht übernommen (Rundschreiben haben nur PDF-Anhänge bis 10 MB): {names}', {
            names: created.skipped_attachments.join(', '),
          }),
        )
      navigate(`/rundschreiben/${created.id}`)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }
  return (
    <div className="stack-sm">
      {rows.map((c) => (
        <p key={c.id}>
          <Link to={`/rundschreiben/${c.id}`}>
            {t('Rundschreiben: {subject}', { subject: c.subject })}
          </Link>{' '}
          <span className="muted small">{c.status_label}</span>
        </p>
      ))}
      {event.can_circular && (
        <p>
          <button
            type="button"
            className="link-button"
            disabled={busy}
            onClick={() => void write()}
          >
            {rows.length
              ? t('Weiteres Rundschreiben dazu schreiben')
              : t('Rundschreiben dazu schreiben')}
          </button>
          {event.rsvp.enabled && (
            <>
              {' · '}
              <button
                type="button"
                className="link-button"
                disabled={busy}
                onClick={() => void write(true)}
              >
                {t('Erinnerung an alle ohne Rückmeldung')}
              </button>
            </>
          )}
        </p>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  )
}

/** Was am Termin hängt: Versammlung, Dienstpläne, Belegungen (Menüprüfung 2, N-02). */
function RelatedLinks({ event, originalStart }: { event: EventDetail; originalStart: string }) {
  const plans = event.helper_plans
  const bookings = event.bookings
  if (event.meeting === undefined && plans === undefined && bookings === undefined) return null
  const book = new URLSearchParams({
    buchen: '1',
    termin: String(event.id),
    titel: event.title,
    vorkommen: originalStart,
  })
  return (
    <>
      {event.meeting && (
        <p>
          <Link to={`/versammlungen?versammlung=${event.meeting.id}`}>{t('Zur Versammlung')}</Link>{' '}
          <span className="muted small">{event.meeting.status_label}</span>
        </p>
      )}
      {plans && (plans.length > 0 || event.can_create_helper_plan) && (
        <div className="stack-sm">
          {plans.map((p) => (
            <p key={p.id}>
              <Link to={`/helferdienste?plan=${p.id}`}>
                {t('Dienstplan: {title}', { title: p.title })}
              </Link>{' '}
              <span className="muted small">{p.status_label}</span>
            </p>
          ))}
          {event.can_create_helper_plan && plans.length === 0 && (
            <p>
              <Link to={`/helferdienste?neu=1&termin=${event.id}`}>
                {t('Dienstplan für diesen Termin anlegen')}
              </Link>
            </p>
          )}
        </div>
      )}
      {bookings && (
        <div className="stack-sm">
          {bookings.map((b) => (
            <p key={b.id}>
              {t('Belegt: {item}', { item: b.item })}{' '}
              <span className="muted small">{b.status_label}</span>
            </p>
          ))}
          <p>
            <Link to={`/belegung?${book}`}>{t('Raum oder Gerät für diesen Termin buchen')}</Link>
          </p>
        </div>
      )}
    </>
  )
}

function RelatedSection({
  base,
  event,
  originalStart,
}: {
  base: string
  event: EventDetail
  originalStart: string
}) {
  const context = useOptionalOrg()
  const org = context?.active
  const permissions = org?.permissions ?? context?.activeDept?.permissions ?? []
  const any =
    event.meeting !== undefined ||
    event.helper_plans !== undefined ||
    event.bookings !== undefined ||
    event.circulars !== undefined ||
    (/^\/api\/(orgs|depts)\//.test(base) && permissions.includes('todos.view')) ||
    (!!org?.modules.includes('music') && permissions.includes('music.view'))
  if (!any) return null
  return (
    <section className="stack-sm">
      <strong>{t('Zu diesem Termin')}</strong>
      <CircularLinks base={base} event={event} />
      <RelatedLinks event={event} originalStart={originalStart} />
      <EventTaskLink base={base} eventId={event.id} />
      <MusicLink eventId={event.id} />
    </section>
  )
}

/** Neuen Termin anlegen (Dialog). */
export function NewEventDialog({
  base,
  date,
  categories,
  units,
  rsvpAllowed,
  onClose,
  onSaved,
}: {
  base: CalendarBase
  date: string
  categories: EventCategory[]
  units?: EventUnit[]
  rsvpAllowed?: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const guard = useRef<CloseGuard | null>(null)
  return (
    <Modal
      title={t('Neuer Termin')}
      onClose={onClose}
      beforeClose={() => guard.current?.() ?? true}
    >
      <EventForm
        guardRef={guard}
        base={base}
        event={null}
        date={date}
        categories={categories}
        units={units}
        rsvpAllowed={rsvpAllowed}
        onCancel={onClose}
        onSaved={onSaved}
      />
    </Modal>
  )
}

/** Einzelnen Termin einer Serie verschieben oder absagen. */
function OccurrencePanel({
  base,
  event,
  occurrence,
  onChanged,
}: {
  base: CalendarBase
  event: EventDetail
  occurrence: Occurrence
  onChanged: (event: EventDetail) => void
}) {
  const s = berlin(occurrence.starts_at)
  const e = berlin(occurrence.ends_at)
  const [mode, setMode] = useState<'none' | 'move'>('none')
  const [date, setDate] = useState(s.date)
  const [start, setStart] = useState(s.time)
  const [end, setEnd] = useState(e.time)
  const [note, setNote] = useState(occurrence.note)
  const [error, setError] = useState<string | null>(null)
  const exception = event.exceptions.find(
    (x) => new Date(x.original_start).getTime() === new Date(occurrence.original_start).getTime(),
  )

  async function run(action: () => Promise<EventDetail>) {
    setError(null)
    try {
      onChanged(await action())
      setMode('none')
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  const original = occurrence.original_start
  return (
    <div className="subcard stack-sm">
      <strong>{t('Nur dieser Termin ({x})', { x: formatDay(berlin(original).date) })}</strong>
      {error && <Alert kind="error">{error}</Alert>}
      {mode === 'move' ? (
        <div className="stack-sm">
          <div className="grid-3">
            <Field
              label={t('Neues Datum')}
              type="date"
              value={date}
              onChange={(x) => setDate(x.target.value)}
            />
            {!event.all_day && (
              <>
                <Field
                  label={t('Beginn')}
                  type="time"
                  value={start}
                  onChange={(x) => setStart(x.target.value)}
                />
                <Field
                  label={t('Ende')}
                  type="time"
                  value={end}
                  onChange={(x) => setEnd(x.target.value)}
                />
              </>
            )}
          </div>
          <Field label={t('Hinweis')} value={note} onChange={(x) => setNote(x.target.value)} />
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              onClick={() =>
                run(() =>
                  eventApi.setOccurrence(base, event.id, {
                    original_start: original,
                    starts_at: toApi(date, event.all_day ? '00:00' : start),
                    ends_at: event.all_day ? null : toApi(date, end),
                    note,
                  }),
                )
              }
            >
              {t('Verschieben')}
            </button>
            <button type="button" className="button button-ghost" onClick={() => setMode('none')}>
              {t('Abbrechen')}
            </button>
          </div>
        </div>
      ) : (
        <div className="button-row">
          <button type="button" className="button button-ghost" onClick={() => setMode('move')}>
            {t('Verschieben')}
          </button>
          {!occurrence.is_cancelled && (
            <button
              type="button"
              className="button button-ghost"
              onClick={async () => {
                const reason = await promptDialog({
                  title: t('Diesen Termin absagen?'),
                  label: t('Hinweis zur Absage (optional)'),
                  confirmLabel: t('Absagen'),
                  danger: true,
                })
                if (reason === null) return
                void run(() =>
                  eventApi.setOccurrence(base, event.id, {
                    original_start: original,
                    is_cancelled: true,
                    note: reason,
                  }),
                )
              }}
            >
              {t('Nur diesen absagen')}
            </button>
          )}
          {exception && (
            <button
              type="button"
              className="button button-ghost"
              onClick={() => run(() => eventApi.resetOccurrence(base, event.id, original))}
            >
              {t('Wie in der Serie')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function EventDialog({
  base,
  occurrence,
  categories,
  units,
  rsvpAllowed,
  onClose,
  onChanged,
}: {
  base: CalendarBase
  occurrence: Occurrence
  categories: EventCategory[]
  units?: EventUnit[]
  rsvpAllowed?: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const { data, error, setData } = useLoad(
    () => eventApi.get(base, occurrence.event_id),
    [base, occurrence.event_id],
  )
  const [editing, setEditing] = useState(false)
  const [message, setMessage] = useState<{ kind: 'error' | 'success'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [inputKey, setInputKey] = useState(0)
  const guard = useRef<CloseGuard | null>(null)

  function changed(event: EventDetail) {
    setData(event)
    onChanged()
  }

  async function upload(file: File) {
    if (file.size > MAX_BYTES) {
      setMessage({ kind: 'error', text: t('Die Datei ist größer als 15 MB.') })
      return
    }
    setBusy(true)
    setMessage(null)
    try {
      changed(await eventApi.upload(base, occurrence.event_id, file))
      setInputKey((k) => k + 1)
    } catch (err) {
      setMessage({ kind: 'error', text: errorMessage(err) })
    } finally {
      setBusy(false)
    }
  }

  const title = data?.title ?? occurrence.title
  return (
    <Modal
      title={editing ? t('Termin bearbeiten') : title}
      onClose={onClose}
      beforeClose={() => (editing ? (guard.current?.() ?? true) : true)}
    >
      {error && <Alert kind="error">{error}</Alert>}
      {!data && !error && <Loading />}
      {data && editing && (
        <EventForm
          guardRef={guard}
          base={base}
          event={data}
          date={berlin(data.starts_at).date}
          categories={categories}
          units={units}
          rsvpAllowed={rsvpAllowed}
          onCancel={() => setEditing(false)}
          onSaved={(saved) => {
            changed(saved)
            setEditing(false)
          }}
        />
      )}
      {data && !editing && (
        <div className="stack">
          {message && <Alert kind={message.kind}>{message.text}</Alert>}
          {occurrence.is_cancelled && (
            <Alert kind="error">
              {t('Abgesagt')}
              {occurrence.note ? t(': {note}', { note: occurrence.note }) : ''}
            </Alert>
          )}
          <dl className="event-facts">
            <dt>{t('Wann')}</dt>
            <dd>
              {formatRange(occurrence.starts_at, occurrence.ends_at, occurrence.all_day)}
              {occurrence.is_moved && <span className="badge"> {t('verschoben')}</span>}
              {data.repeat !== 'none' && (
                <div className="muted small">
                  {t('Serie:')} {data.repeat_label}
                  {data.repeat_interval > 1 && t(' (alle {x0})', { x0: data.repeat_interval })}
                  {data.repeat_until && t(' bis {x}', { x: formatDay(data.repeat_until, false) })}
                </div>
              )}
            </dd>
            {(data.location || data.address) && (
              <>
                <dt>{t('Ort')}</dt>
                <dd>
                  {data.location}
                  {data.address && <div className="muted small">{data.address}</div>}
                  <RouteLinks directions={data.directions} links={data.map_links} />
                </dd>
              </>
            )}
            <dt>{t('Kalender')}</dt>
            <dd>
              {data.owner} <VisibilityBadge visibility={data.visibility} />
            </dd>
            {data.source && (
              <>
                <dt>{t('Herkunft')}</dt>
                <dd>
                  {t('aus {name} ({kind})', {
                    name: data.source.name,
                    kind: data.source.kind_label,
                  })}
                  <div className="muted small">
                    {t(
                      'Diesen Termin pflegt der fremde Kalender; hier lässt er sich nicht ändern.',
                    )}
                  </div>
                </dd>
              </>
            )}
            {data.category && (
              <>
                <dt>{t('Kategorie')}</dt>
                <dd>
                  <span className="event-dot" style={{ background: data.category.color }} />{' '}
                  {data.category.name}
                </dd>
              </>
            )}
            {data.changed_at && (
              <>
                <dt>{t('Geändert')}</dt>
                <dd>
                  {t('Zeit oder Ort geändert am')} {formatDay(berlin(data.changed_at).date, false)}
                </dd>
              </>
            )}
          </dl>
          {data.description && <p className="event-description">{data.description}</p>}
          {data.rsvp.can_respond !== undefined && (
            <MyResponsePanel base={base} event={data} onChanged={changed} />
          )}
          {data.rsvp.can_view_list && <ResponsesPanel base={base} event={data} />}
          {data.can_edit && data.rsvp.enabled && (
            <p className="muted small">
              {t('Zu- und Absagen sind eingeschaltet')}
              {data.remind_days
                ? t(', Erinnerung {remind_days} Tage vorher', { remind_days: data.remind_days })
                : ''}
              .
            </p>
          )}
          <RelatedSection base={base} event={data} originalStart={occurrence.original_start} />
          <MaterialReferences
            kind="event"
            id={data.id}
            originalStart={occurrence.original_start}
            sourceBase={base}
          />
          <EventProjectPanel base={base} event={data} onChanged={changed} />
          {(data.attachments.length > 0 || data.can_edit) && (
            <div className="stack-sm">
              <strong>{t('Anhänge')}</strong>
              {data.attachments.length === 0 && (
                <p className="muted small">{t('Keine Anhänge.')}</p>
              )}
              <ul className="plain-list">
                {data.attachments.map((a) => (
                  <li key={a.id}>
                    {a.available === false ? (
                      <span className="muted">{a.name}</span>
                    ) : (
                      <a href={a.url} target="_blank" rel="noreferrer">
                        {a.name}
                      </a>
                    )}{' '}
                    {a.available !== false && (
                      <span className="muted small">{formatSize(a.size)}</span>
                    )}
                    {a.kind === 'document' && (
                      <span className="muted small"> · {t('aus der Ablage')}</span>
                    )}
                    {data.can_edit && (
                      <button
                        type="button"
                        className="link-button"
                        disabled={busy}
                        onClick={async () => {
                          if (
                            !(await confirmDialog({
                              title: t('Anhang „{name}“ entfernen?', { name: a.name }),
                              message:
                                a.kind === 'document'
                                  ? t('Das Dokument bleibt in der Ablage.')
                                  : undefined,
                              confirmLabel: t('Entfernen'),
                            }))
                          )
                            return
                          try {
                            await eventApi.removeAttachment(a.url)
                            changed(await eventApi.get(base, data.id))
                          } catch (err) {
                            setMessage({ kind: 'error', text: errorMessage(err) })
                          }
                        }}
                      >
                        {t('entfernen')}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
              {data.can_edit && (
                <label className="field">
                  <span>{t('Anhang hinzufügen (PDF, JPEG oder PNG, höchstens 15 MB)')}</span>
                  <input
                    key={inputKey}
                    type="file"
                    accept="application/pdf,image/jpeg,image/png"
                    disabled={busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0]
                      if (file) void upload(file)
                    }}
                  />
                </label>
              )}
              {data.can_edit && (
                <EventDocumentLink base={base} event={data} disabled={busy} onChanged={changed} />
              )}
            </div>
          )}
          <p className="small">
            <a href={eventApi.icsUrl(base, data.id)} download>
              {data.repeat !== 'none' ? t('Serie') : t('Termin')}{' '}
              {t('in den eigenen Kalender (.ics)')}
            </a>
          </p>
          {data.can_edit && data.repeat !== 'none' && (
            <OccurrencePanel base={base} event={data} occurrence={occurrence} onChanged={changed} />
          )}
          {data.can_hide && (
            <div className="button-row">
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={async () => {
                  if (
                    !(await confirmDialog({
                      title: t('„{title}“ hier ausblenden?', { title: data.title }),
                      message: t(
                        'Der Termin verschwindet aus diesem Kalender und bleibt auch bei jedem Abruf ausgeblendet. Unter „Fremde Kalender“ lässt er sich wieder zeigen.',
                      ),
                      confirmLabel: t('Ausblenden'),
                    }))
                  )
                    return
                  try {
                    await eventApi.hide(base, data.id)
                    onChanged()
                    onClose()
                  } catch (err) {
                    setMessage({ kind: 'error', text: errorMessage(err) })
                  }
                }}
              >
                {t('Hier ausblenden')}
              </button>
            </div>
          )}
          {data.can_edit && (
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                onClick={() => setEditing(true)}
              >
                {data.repeat !== 'none' ? t('Serie bearbeiten') : t('Bearbeiten')}
              </button>
              <button
                type="button"
                className="button button-danger"
                disabled={busy}
                onClick={async () => {
                  const what = data.repeat !== 'none' ? t('die ganze Serie') : t('den Termin')
                  if (
                    !(await confirmDialog({
                      title: t('Wirklich {what} „{title}“ löschen?', { what, title: data.title }),
                      confirmLabel: t('Löschen'),
                    }))
                  )
                    return
                  try {
                    await eventApi.remove(base, data.id)
                    onChanged()
                    onClose()
                  } catch (err) {
                    setMessage({ kind: 'error', text: errorMessage(err) })
                  }
                }}
              >
                {t('Löschen')}
              </button>
            </div>
          )}
        </div>
      )}
    </Modal>
  )
}
