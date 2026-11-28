// Termin ansehen; mit Recht auch bearbeiten, einzelne Serientermine ändern, Anhänge.
// Aufbau (Ralf 15.11.2026): Kopf mit Wann/Ort/Kalender, Aktionsleiste, Rückmeldungen als Karte,
// „Zu diesem Termin“ als Karte mit einer Zeile je Bereich, Löschen allein unten.
import { NextcloudPick } from '../NextcloudFiles.tsx'
import { RouteLinks } from './RouteLinks.tsx'
import { VideoRoom } from './VideoRoom.tsx'
import { EventTaskRow } from '../TodoEventLink.tsx'
import { Link, useNavigate } from 'react-router-dom'
import { useOptionalOrg } from '../../org/OrgContext.tsx'
import { EventMaterialRow } from '../MaterialReferences.tsx'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { eventApi } from '../../api/events.ts'
import type {
  CalendarBase,
  EventCategory,
  EventDetail,
  EventUnit,
  Occurrence,
} from '../../api/events.ts'
import { errorMessage, useLoad } from '../forms.ts'
import { Alert, Checkbox, Field, Loading } from '../ui.tsx'
import { EventForm } from './EventForm.tsx'
import { MyResponsePanel, ResponsesPanel } from './Rsvp.tsx'
import { RegistrationPanel } from './Registration.tsx'
import { EventProjectPanel } from './EventProject.tsx'
import { useEventDocumentLink } from './EventDocumentLink.tsx'
import { EventRow } from './EventRow.tsx'
import { berlin, formatDay, formatRange, toApi } from './time.ts'
import { alertDialog, confirmDialog, promptDialog } from '../dialog.ts'
import { circularApi } from '../../api/circulars.ts'
import { contentApi } from '../../api/website.ts'
import { Modal } from '../Modal.tsx'
import type { CloseGuard } from './EventForm.tsx'
import { t, tc } from '../../i18n/index.ts'

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
      {visibility === 'public' ? t('nach außen öffentlich') : t('nur Vorstand')}
    </span>
  )
}

/** Rundschreiben zum Termin schreiben: an die Eingeladenen, mit den PDF-Anhängen des Termins. */
function useCircularWriter(base: string, event: EventDetail) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
  return { busy, error, write }
}

/**
 * Eigene Veranstaltungsseite auf der Webseite (Anmeldung A4, nur bei öffentlichen Terminen):
 * Titel, Text und Abschnitte unter Webseite › Inhalte, Eckdaten und Anmeldeknopf aus dem Termin.
 */
function WebPageRow({ orgId, event }: { orgId: number; event: EventDetail }) {
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const page = event.web_page
  async function create() {
    setBusy(true)
    setError(null)
    try {
      const text = await contentApi.eventPage(orgId, event.id)
      navigate(`/webseite/inhalte?text=${text.id}`)
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }
  return (
    <EventRow
      label={t('Webseite')}
      actions={
        page ? (
          <Link
            className="button button-ghost"
            to={`/webseite/inhalte?text=${page.id}`}
            aria-label={t('Veranstaltungsseite bearbeiten')}
          >
            {t('Bearbeiten')}
          </Link>
        ) : (
          <button
            type="button"
            className="button button-ghost"
            disabled={busy}
            onClick={() => void create()}
            aria-label={t('Eigene Seite auf der Webseite anlegen')}
          >
            <span aria-hidden="true">+</span> {t('Anlegen')}
          </button>
        )
      }
    >
      {page ? (
        <>
          {t('Veranstaltungsseite: {title}', { title: page.title })}{' '}
          <span className="muted small">
            {page.is_published ? t('veröffentlicht') : t('Entwurf, nicht veröffentlicht')}
          </span>
        </>
      ) : (
        <span className="muted small">
          {t('keine eigene Seite; Termin erscheint in der Terminliste')}
        </span>
      )}
      {error && <Alert kind="error">{error}</Alert>}
    </EventRow>
  )
}

/**
 * Was am Termin hängt, je eine Zeile: Rundschreiben, Versammlung, Dienstpläne, Belegungen,
 * Aufgaben, Musik, Material, Abrechnung, Anhänge (Menüprüfung 2, N-02; neu gegliedert
 * Ralf 15.11.2026). Leere Bereiche bleiben einzeilig, Auswahlen klappen erst auf Klick auf.
 */
function RelatedCard({
  base,
  event,
  originalStart,
  onChanged,
  attachments,
}: {
  base: CalendarBase
  event: EventDetail
  originalStart: string
  onChanged: (event: EventDetail) => void
  attachments: ReactNode
}) {
  const org = useOptionalOrg()?.active
  const plans = event.helper_plans
  const bookings = event.bookings
  const circulars = event.circulars ?? []
  const book = new URLSearchParams({
    buchen: '1',
    termin: String(event.id),
    titel: event.title,
    vorkommen: originalStart,
  })
  const music = !!org?.modules.includes('music') && !!org.permissions.includes('music.view')
  return (
    <section className="card event-card event-related">
      <h3 className="event-card-title">{t('Zu diesem Termin')}</h3>
      {circulars.length > 0 && (
        <EventRow label={t('Rundschreiben')}>
          <ul className="plain-list">
            {circulars.map((c) => (
              <li key={c.id}>
                <Link to={`/rundschreiben/${c.id}`}>
                  {t('Rundschreiben: {subject}', { subject: c.subject })}
                </Link>{' '}
                <span className="muted small">{c.status_label}</span>
              </li>
            ))}
          </ul>
        </EventRow>
      )}
      {event.meeting && (
        <EventRow
          label={t('Versammlung')}
          actions={
            <Link
              className="button button-ghost"
              to={`/versammlungen?versammlung=${event.meeting.id}`}
              aria-label={t('Zur Versammlung')}
            >
              {t('Öffnen')}
            </Link>
          }
        >
          {event.meeting.status_label}
        </EventRow>
      )}
      {plans && (plans.length > 0 || event.can_create_helper_plan) && (
        <EventRow
          label={t('Dienstplan')}
          actions={
            event.can_create_helper_plan &&
            plans.length === 0 && (
              <Link
                className="button button-ghost"
                to={`/helferdienste?neu=1&termin=${event.id}`}
                aria-label={t('Dienstplan für diesen Termin anlegen')}
              >
                <span aria-hidden="true">+</span> {t('Anlegen')}
              </Link>
            )
          }
        >
          {plans.length === 0 ? (
            <span className="muted small">{t('keiner')}</span>
          ) : (
            <ul className="plain-list">
              {plans.map((p) => (
                <li key={p.id}>
                  <Link to={`/helferdienste?plan=${p.id}`}>
                    {t('Dienstplan: {title}', { title: p.title })}
                  </Link>{' '}
                  <span className="muted small">{p.status_label}</span>
                </li>
              ))}
            </ul>
          )}
        </EventRow>
      )}
      {bookings && (
        <EventRow
          label={t('Belegung')}
          actions={
            <Link
              className="button button-ghost"
              to={`/belegung?${book}`}
              aria-label={t('Raum oder Gerät für diesen Termin buchen')}
            >
              {t('Buchen')}
            </Link>
          }
        >
          {bookings.length === 0 ? (
            <span className="muted small">{t('nichts gebucht')}</span>
          ) : (
            <ul className="plain-list">
              {bookings.map((b) => (
                <li key={b.id}>
                  {t('Belegt: {item}', { item: b.item })}{' '}
                  <span className="muted small">{b.status_label}</span>
                </li>
              ))}
            </ul>
          )}
        </EventRow>
      )}
      {event.web_page !== undefined && org && <WebPageRow orgId={org.id} event={event} />}
      <EventTaskRow base={base} eventId={event.id} />
      {music && (
        <EventRow
          label={t('Musik')}
          actions={
            <Link className="button button-ghost" to={`/musik?art=performances&termin=${event.id}`}>
              {t('Auftritt planen')}
            </Link>
          }
        />
      )}
      <EventMaterialRow id={event.id} originalStart={originalStart} sourceBase={base} />
      <EventProjectPanel base={base} event={event} onChanged={onChanged} />
      {attachments}
    </section>
  )
}

function rsvpNote(event: EventDetail): string {
  // X-13: „Rückmeldung“ als Oberbegriff; ganze Sätze (VW-15)
  return event.remind_days
    ? t('Rückmeldungen sind eingeschaltet, Erinnerung {remind_days} Tage vorher.', {
        remind_days: event.remind_days,
      })
    : t('Rückmeldungen sind eingeschaltet.')
}

/** Aktionsleiste unter dem Kopf: alles, was man mit dem Termin tut, als gleichartige Knöpfe. */
function EventActions({
  base,
  event,
  busy,
  onEdit,
  onHide,
}: {
  base: CalendarBase
  event: EventDetail
  busy: boolean
  onEdit: () => void
  onHide: () => void
}) {
  const circular = useCircularWriter(base, event)
  const series = event.repeat !== 'none'
  return (
    <div className="stack-sm">
      <div className="button-row event-actions">
        {event.can_edit && (
          <button type="button" className="button button-primary" onClick={onEdit}>
            {series ? t('Serie bearbeiten') : t('Bearbeiten')}
          </button>
        )}
        {event.can_circular && (
          <button
            type="button"
            className="button button-ghost"
            disabled={circular.busy}
            onClick={() => void circular.write()}
          >
            {event.registration?.enabled
              ? event.circulars?.length
                ? t('Weiteres Infoschreiben an Angemeldete')
                : t('Infoschreiben an Angemeldete')
              : event.circulars?.length
                ? t('Weiteres Rundschreiben dazu schreiben')
                : t('Rundschreiben dazu schreiben')}
          </button>
        )}
        {event.can_circular && event.rsvp.enabled && (
          <button
            type="button"
            className="button button-ghost"
            disabled={circular.busy}
            onClick={() => void circular.write(true)}
          >
            {t('Erinnerung an alle ohne Rückmeldung')}
          </button>
        )}
        <a className="button button-ghost" href={eventApi.icsUrl(base, event.id)} download>
          {series ? t('Serie in den eigenen Kalender') : t('In den eigenen Kalender')}
        </a>
        {event.can_hide && (
          <button type="button" className="button button-ghost" disabled={busy} onClick={onHide}>
            {t('Hier ausblenden')}
          </button>
        )}
      </div>
      {circular.error && <Alert kind="error">{circular.error}</Alert>}
    </div>
  )
}

/** Zeile „Anhänge“: Liste, Hochladen und Verknüpfen aus der Ablage als Knöpfe nebeneinander. */
function AttachmentsRow({
  base,
  event,
  busy,
  inputKey,
  onUpload,
  onChanged,
  onError,
  setBusy,
}: {
  base: CalendarBase
  event: EventDetail
  busy: boolean
  inputKey: number
  onUpload: (file: File) => void
  onChanged: (event: EventDetail) => void
  onError: (text: string) => void
  setBusy: (busy: boolean) => void
}) {
  const input = useRef<HTMLInputElement>(null)
  const documents = useEventDocumentLink({ base, event, disabled: busy, onChanged }, true)
  const items = event.attachments
  return (
    <EventRow
      label={t('Anhänge')}
      actions={
        event.can_edit && (
          <>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              aria-describedby={`event-${event.id}-file-hint`}
              onClick={() => input.current?.click()}
            >
              <span aria-hidden="true">+</span> {t('Datei hinzufügen')}
            </button>
            <input
              key={inputKey}
              ref={input}
              type="file"
              hidden
              aria-label={t('Anhang hinzufügen (PDF, JPEG oder PNG, höchstens 15 MB)')}
              accept="application/pdf,image/jpeg,image/png"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) onUpload(file)
              }}
            />
            {!busy && (
              <NextcloudPick accept={['.pdf', 'image/jpeg', 'image/png']} onFile={onUpload} />
            )}
            {documents.button}
          </>
        )
      }
      extra={documents.panel}
    >
      {items.length === 0 && <span className="muted small">{t('keine')}</span>}
      {items.length > 0 && (
        <ul className="plain-list">
          {items.map((a) => (
            <li key={a.id}>
              {a.available === false ? (
                <span className="muted">{a.name}</span>
              ) : (
                <a href={a.url} target="_blank" rel="noreferrer">
                  {a.name}
                </a>
              )}{' '}
              {a.available !== false && <span className="muted small">{formatSize(a.size)}</span>}
              {a.kind === 'document' && (
                <span className="muted small"> · {t('aus der Ablage')}</span>
              )}
              {event.can_edit && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  onClick={async () => {
                    if (
                      !(await confirmDialog({
                        final: false,
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
                      onChanged(await eventApi.get(base, event.id))
                    } catch (err) {
                      onError(errorMessage(err))
                    }
                  }}
                >
                  {t('entfernen')}
                </button>
              )}
              {event.can_edit && event.visibility === 'public' && a.available !== false && (
                <Checkbox
                  label={t('auf der Webseite zeigen')}
                  checked={!!a.on_website}
                  busy={busy}
                  onChange={async (value) => {
                    setBusy(true)
                    try {
                      onChanged(await eventApi.showOnWebsite(a.url, value))
                    } catch (err) {
                      onError(errorMessage(err))
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
      {event.can_edit && (
        <div id={`event-${event.id}-file-hint`} className="muted small">
          {t('PDF, JPEG oder PNG, höchstens 15 MB')}
        </div>
      )}
    </EventRow>
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
                  confirmLabel: tc('event', 'Absagen'),
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
            {!occurrence.is_cancelled && <VideoRoom base={base} event={data} onChanged={changed} />}
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
          {data.programme && (
            <section className="stack-sm">
              <h3 className="event-card-title">{t('Ablauf')}</h3>
              <p className="event-description">{data.programme}</p>
            </section>
          )}
          <EventActions
            base={base}
            event={data}
            busy={busy}
            onEdit={() => setEditing(true)}
            onHide={async () => {
              if (
                !(await confirmDialog({
                  final: false,
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
          />
          {data.rsvp.can_respond !== undefined && (
            <MyResponsePanel base={base} event={data} onChanged={changed} />
          )}
          {data.rsvp.can_view_list && (
            <ResponsesPanel
              base={base}
              event={data}
              note={data.can_edit && data.rsvp.enabled ? rsvpNote(data) : undefined}
            />
          )}
          {!data.rsvp.can_view_list && data.can_edit && data.rsvp.enabled && (
            <p className="muted small">{rsvpNote(data)}</p>
          )}
          <RegistrationPanel base={base} event={data} />
          <RelatedCard
            base={base}
            event={data}
            originalStart={occurrence.original_start}
            onChanged={changed}
            attachments={
              (data.attachments.length > 0 || data.can_edit) && (
                <AttachmentsRow
                  base={base}
                  event={data}
                  busy={busy}
                  inputKey={inputKey}
                  onUpload={(file) => void upload(file)}
                  onChanged={changed}
                  onError={(text) => setMessage({ kind: 'error', text })}
                  setBusy={setBusy}
                />
              )
            }
          />
          {data.can_edit && data.repeat !== 'none' && (
            <OccurrencePanel base={base} event={data} occurrence={occurrence} onChanged={changed} />
          )}
          {data.can_edit && (
            <div className="button-row event-danger-row">
              <button
                type="button"
                className="button button-danger"
                disabled={busy}
                onClick={async () => {
                  const what = data.repeat !== 'none' ? t('die ganze Serie') : t('den Termin')
                  if (
                    !(await confirmDialog({
                      final: false,
                      title: t('Wirklich {what} „{title}“ löschen?', { what, title: data.title }),
                      confirmLabel: t('Löschen'),
                    }))
                  )
                    return
                  try {
                    await eventApi.remove(base, data.id, data.version)
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
