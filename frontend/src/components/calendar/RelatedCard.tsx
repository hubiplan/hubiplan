import { EventTaskRow } from '../TodoEventLink.tsx'
import { Link, useNavigate } from 'react-router-dom'
import { useOptionalOrg } from '../../org/OrgContext.tsx'
import { EventMaterialRow } from '../MaterialReferences.tsx'
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { errorMessage } from '../forms.ts'
import { Alert } from '../ui.tsx'
import { EventProjectPanel } from './EventProject.tsx'
import { EventRow } from './EventRow.tsx'
import { contentApi } from '../../api/website.ts'
import { Modal } from '../Modal.tsx'
import { t } from '../../i18n/index.ts'

export { Modal }

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
export function RelatedCard({
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
