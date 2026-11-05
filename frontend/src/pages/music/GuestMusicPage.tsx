import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { ApiError, parseBody, send, saveBlob } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { usePublicImprint } from '../../components/publicImprint.ts'
import { Alert } from '../../components/ui.tsx'
import { lang, t } from '../../i18n/index.ts'
import { MusicStatus } from './MusicLayout.tsx'
import { AvailabilityHint } from './AvailabilityPage.tsx'

type GuestPerformance = {
  kind?: string
  scores?: { id: number; title: string; filename: string; usage_note: string }[]
  title: string
  organization: string
  imprint_key: string
  starts_at: string
  ends_at: string
  location: string
  meeting_at: string | null
  meeting_place: string
  setup_at: string | null
  formation: string
  uniform: string
  notes: string
  instrument: string
  register: string
  status: string
  cancelled: boolean
  can_respond: boolean
  availability: string[]
  program: { title: string; kind: string; duration_seconds: number }[]
}

export function GuestMusicPage() {
  const { hash } = useLocation()
  const rehearsal = hash.startsWith('#probe-')
  const token = hash.slice(rehearsal ? 7 : 1)
  if (!/^[0-9a-f]{64}$/.test(token))
    return (
      <main className="music-guest-page">
        <h1>{t('Meine Auftrittseinteilung')}</h1>
        <Alert kind="error">{t('Diese Einladung ist ungültig oder abgelaufen.')}</Alert>
      </main>
    )
  return <GuestAssignment key={token} token={token} rehearsal={rehearsal} />
}

function GuestAssignment({ token, rehearsal }: { token: string; rehearsal: boolean }) {
  const endpoint = rehearsal ? '/api/music/guest-rehearsal/' : '/api/music/guest/'
  async function call(method: 'GET' | 'POST', status?: string) {
    const response = await send(
      endpoint,
      {
        method,
        credentials: 'omit',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Accept-Language': lang(),
        },
        body: method === 'POST' ? JSON.stringify({ status }) : undefined,
      },
      method === 'GET',
    )
    const body = parseBody(await response.text())
    if (!response.ok)
      throw new ApiError(
        response.status,
        response.status === 404
          ? { detail: t('Diese Einladung ist ungültig oder abgelaufen.') }
          : body,
      )
    return body as GuestPerformance
  }
  const load = useLoad(() => call('GET'), [token])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const row = load.data
  usePublicImprint(row?.imprint_key, row?.organization)
  if (load.error)
    return (
      <main className="music-guest-page">
        <Alert kind="error">{load.error}</Alert>
      </main>
    )
  if (!row)
    return (
      <main className="music-guest-page">
        <p>{t('Lädt …')}</p>
      </main>
    )
  return (
    <main className="music-guest-page music-personal stack">
      <meta name="referrer" content="no-referrer" />
      <meta name="robots" content="noindex,nofollow" />
      <header className="music-page-header">
        <h1>{rehearsal ? t('Meine Probeneinteilung') : t('Meine Auftrittseinteilung')}</h1>
        <p className="muted">{row.organization}</p>
      </header>
      <article className="card stack music-record">
        <h2>{row.title}</h2>
        <MusicStatus status={row.cancelled ? 'declined' : row.status} />
        {error && <Alert kind="error">{error}</Alert>}
        {message && <Alert kind="success">{message}</Alert>}
        {row.cancelled && (
          <Alert kind="error">{rehearsal ? t('Probe abgesagt') : t('Auftritt abgesagt')}</Alert>
        )}
        <dl className="music-details">
          <div>
            <dt>{t('Termin')}</dt>
            <dd>
              {formatDateTime(row.starts_at)} – {formatDateTime(row.ends_at)}
            </dd>
          </div>
          <div>
            <dt>{t('Ort')}</dt>
            <dd>{row.location || '—'}</dd>
          </div>
          <div>
            <dt>{t('Instrument')}</dt>
            <dd>
              {row.instrument} {row.register}
            </dd>
          </div>
          {(row.meeting_at || row.meeting_place) && (
            <div>
              <dt>{t('Treffpunkt')}</dt>
              <dd>
                {[row.meeting_at ? formatDateTime(row.meeting_at) : '', row.meeting_place]
                  .filter(Boolean)
                  .join(' · ')}
              </dd>
            </div>
          )}
          {row.uniform && (
            <div>
              <dt>{t('Uniform')}</dt>
              <dd>{row.uniform}</dd>
            </div>
          )}
          {row.setup_at && (
            <div>
              <dt>{t('Aufbauzeit')}</dt>
              <dd>{formatDateTime(row.setup_at)}</dd>
            </div>
          )}
          <div>
            <dt>{t('Spielform')}</dt>
            <dd>
              {{ seated: t('Sitzend'), standing: t('Stehend'), march: t('Umzug') }[row.formation] ||
                '—'}
            </dd>
          </div>
        </dl>
        {row.notes && <p className="music-guest-notes">{row.notes}</p>}
        {!!row.program.length && (
          <section className="stack">
            <h3>{t('Musikalisches Programm')}</h3>
            <ol>
              {row.program.map((entry, index) => (
                <li key={index}>
                  {entry.kind === 'pause' ? t('Pause') : entry.title}
                  {entry.kind === 'encore' ? ` (${t('Zugabe')})` : ''}
                </li>
              ))}
            </ol>
          </section>
        )}
        {!!row.scores?.length && (
          <section className="stack">
            <h3>{t('Freigegebene Noten')}</h3>
            {row.scores.map((score) => (
              <div key={score.id}>
                <button
                  className="button button-ghost"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    setError('')
                    try {
                      const response = await send(`${endpoint}?score=${score.id}`, {
                        method: 'GET',
                        credentials: 'omit',
                        headers: { Authorization: `Bearer ${token}` },
                      })
                      if (!response.ok)
                        throw new ApiError(response.status, parseBody(await response.text()))
                      saveBlob(await response.blob(), score.filename)
                    } catch (e) {
                      setError(errorMessage(e))
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  {score.title}
                </button>
                {score.usage_note && <p>{score.usage_note}</p>}
              </div>
            ))}
          </section>
        )}
        {!!row.availability.length && <AvailabilityHint reasons={row.availability} />}
        {row.can_respond && (
          <div className="music-actions">
            {[
              ['accepted', t('Zusagen')],
              ['declined', t('Absagen')],
            ].map(([status, label]) => (
              <button
                key={status}
                className="button button-ghost"
                aria-pressed={row.status === status}
                disabled={busy || (status === 'accepted' && row.availability.length > 0)}
                onClick={async () => {
                  setBusy(true)
                  setError('')
                  setMessage('')
                  try {
                    await call('POST', status)
                    await load.reload()
                    setMessage(t('Rückmeldung gespeichert.'))
                  } catch (e) {
                    setError(errorMessage(e))
                    await load.reload()
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <p className="muted">
          {t('Dieser persönliche Link ist nur für Sie bestimmt. Bitte nicht weitergeben.')}
        </p>
      </article>
    </main>
  )
}
