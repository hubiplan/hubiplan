// Versammlungen im Mitgliederbereich (konzepte/versammlungen.md, Schritte V5 bis V7):
// Einladungen mit Tagesordnung, eigene Anträge und freigegebene Protokolle für Stimmberechtigte.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { saveBlob } from '../../api/client.ts'
import { portalMeetingApi } from '../../api/meetings.ts'
import type { PortalMeetings as Data } from '../../api/meetings.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { LoadError, Loading } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'
import { motionStatusLabel } from '../meetings/MotionsCard.tsx'

const ZONE = 'Europe/Berlin'

function when(value: string) {
  const d = new Date(value)
  const day = d.toLocaleDateString(locale(), {
    timeZone: ZONE,
    weekday: 'long',
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
  const time = d.toLocaleTimeString(locale(), {
    timeZone: ZONE,
    hour: '2-digit',
    minute: '2-digit',
  })
  return `${day}, ${time}`
}

export function PortalMeetings({ accessId }: { accessId: number }) {
  const { data, error, reload } = useLoad(() => portalMeetingApi.list(accessId), [accessId])
  const [failure, setFailure] = useState<string | null>(null)
  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return <Loading />
  const download = async (id: number, date: string) => {
    setFailure(null)
    try {
      saveBlob(await portalMeetingApi.minutes(accessId, id), `protokoll-${date.slice(0, 10)}.pdf`)
    } catch (err) {
      setFailure(errorMessage(err))
    }
  }
  return (
    <>
      {failure && <p role="alert">{failure}</p>}
      <section className="card stack">
        <h2>{t('Einladungen')}</h2>
        {data.upcoming.length === 0 ? (
          <p className="muted">{t('Zurzeit bist du zu keiner Versammlung eingeladen.')}</p>
        ) : (
          data.upcoming.map((m) => (
            <article key={m.id} className="stack">
              <h3>
                {m.title}
                {m.unit && <span className="badge">{m.unit}</span>}
              </h3>
              <p>
                {when(m.starts_at)}
                {m.location && ` · ${m.location}`}
                {m.address && <span className="muted"> · {m.address}</span>}
              </p>
              {(m.checkin_open || m.remote) && (
                <p>
                  <Link className="button" to={`/mein-bereich/versammlungen/live/${m.id}`}>
                    {m.remote
                      ? t('Zur Versammlung: online teilnehmen und abstimmen')
                      : t('Zur Versammlung: Anmeldung und Abstimmungen')}
                  </Link>
                </p>
              )}
              <h4>{t('Tagesordnung')}</h4>
              <ol className="portal-agenda">
                {m.agenda.map((item) => (
                  <li key={item.position} className={item.level ? 'portal-agenda-sub' : undefined}>
                    {t('TOP {n}', { n: item.number || item.position })}: {item.title}
                    {item.description && (
                      <div className="muted small" style={{ whiteSpace: 'pre-wrap' }}>
                        {item.description}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
              <Motions accessId={accessId} meeting={m} onChanged={reload} />
            </article>
          ))
        )}
      </section>
      <section className="card stack">
        <h2>{t('Protokolle')}</h2>
        {data.minutes.length === 0 ? (
          <p className="muted">{t('Es gibt noch kein freigegebenes Protokoll für dich.')}</p>
        ) : (
          <ul>
            {data.minutes.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  className="link-button"
                  aria-label={t('Protokoll herunterladen: {title}', { title: m.title })}
                  onClick={() => download(m.id, m.starts_at)}
                >
                  {m.title}
                </button>
                <span className="muted">
                  {' '}
                  · {new Date(m.starts_at).toLocaleDateString(locale(), { timeZone: ZONE })}
                  {m.unit && ` · ${m.unit}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

function Motions({
  accessId,
  meeting,
  onChanged,
}: {
  accessId: number
  meeting: Data['upcoming'][number]
  onChanged: () => Promise<void>
}) {
  const [writing, setWriting] = useState(false)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [now] = useState(() => Date.now())
  const own = meeting.motions ?? []
  const open = !!meeting.motion_until && new Date(meeting.motion_until).getTime() > now
  if (!open && own.length === 0) return null
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await action()
      await onChanged()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="stack">
      <h4>{t('Anträge')}</h4>
      {own.length > 0 && (
        <ul>
          {own.map((m) => (
            <li key={m.id}>
              <strong>{m.title}</strong> · {motionStatusLabel(m.status)}
              {m.reply && <div className="muted small">{m.reply}</div>}
              {m.status === 'submitted' && (
                <button
                  type="button"
                  className="link-button"
                  disabled={busy}
                  aria-label={t('Antrag zurückziehen: {title}', { title: m.title })}
                  onClick={async () => {
                    const yes = await confirmDialog({
                      title: t('Antrag zurückziehen?'),
                      message: m.title,
                      confirmLabel: t('Zurückziehen'),
                    })
                    if (yes) await act(() => portalMeetingApi.withdrawMotion(accessId, m.id))
                  }}
                >
                  {t('Zurückziehen')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert">{error}</p>}
      {open &&
        (writing ? (
          <form
            className="stack"
            aria-label={t('Antrag stellen: {title}', { title: meeting.title })}
            onSubmit={async (e) => {
              e.preventDefault()
              const done = await act(() =>
                portalMeetingApi.submitMotion(accessId, meeting.id, { title, text }),
              )
              if (done) {
                setWriting(false)
                setTitle('')
                setText('')
              }
            }}
          >
            <label className="field">
              <span>{t('Titel des Antrags')}</span>
              <input
                value={title}
                maxLength={300}
                required
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label className="field">
              <span>{t('Begründung')}</span>
              <textarea
                value={text}
                maxLength={10000}
                required
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setWriting(false)}
              >
                {t('Abbrechen')}
              </button>
              <button className="button" disabled={busy || !title.trim() || !text.trim()}>
                {t('Antrag einreichen')}
              </button>
            </div>
          </form>
        ) : (
          <div className="button-row">
            <button type="button" className="button button-ghost" onClick={() => setWriting(true)}>
              {t('Antrag stellen')}
            </button>
            <span className="muted small">
              {t('Anträge bis {day}', {
                day: new Date(meeting.motion_until!).toLocaleDateString(locale(), {
                  timeZone: ZONE,
                }),
              })}
            </span>
          </div>
        ))}
    </div>
  )
}
