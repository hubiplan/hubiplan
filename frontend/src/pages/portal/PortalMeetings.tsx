// Versammlungen im Mitgliederbereich (konzepte/versammlungen.md, Schritt V5): Einladungen mit
// Tagesordnung und freigegebene Protokolle für Stimmberechtigte.
import { useState } from 'react'
import { saveBlob } from '../../api/client.ts'
import { portalMeetingApi } from '../../api/meetings.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { LoadError } from '../../components/ui.tsx'
import { locale, t } from '../../i18n/index.ts'

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
  if (!data) return <p role="status">{t('Wird geladen…')}</p>
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
              <h4>{t('Tagesordnung')}</h4>
              <ol>
                {m.agenda.map((item) => (
                  <li key={item.position}>
                    {item.title}
                    {item.description && (
                      <div className="muted small" style={{ whiteSpace: 'pre-wrap' }}>
                        {item.description}
                      </div>
                    )}
                  </li>
                ))}
              </ol>
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
