import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { OwnPracticePanel } from './OwnPractice.tsx'
import { OwnAvailability, AvailabilityHint } from './AvailabilityPage.tsx'
import { MusicStatus } from './MusicLayout.tsx'

export function OwnMusic({ accessId }: { accessId: number }) {
  const url = `/api/portal/${accessId}/music/`
  const load = useLoad(
    () =>
      api.get<
        {
          id: number
          title: string
          starts_at: string
          instrument: string
          register: string
          status: string
          location: string
          meeting_at: string | null
          meeting_place: string
          uniform: string
          cancelled: boolean
          availability?: string[]
          program?: { title: string; kind: string; duration_seconds: number }[]
          settlement?: {
            fee: string
            allowance: string
            expenses: string
            total: string
            paid: boolean
          } | null
        }[]
      >(url),
    [accessId],
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <>
      {load.error && <Alert kind="error">{load.error}</Alert>}
      <OwnAvailability accessId={accessId} />
      {!!load.data?.length && (
        <section className="card stack music-personal">
          <h2>{t('Meine Auftritte')}</h2>
          {error && <Alert kind="error">{error}</Alert>}
          {load.data?.map((r) => (
            <article className="stack" key={r.id}>
              <strong>{r.title}</strong>
              {(r.program?.length || 0) > 0 && (
                <ol>
                  {r.program!.map((p, index) => (
                    <li key={index}>
                      {p.kind === 'pause' ? t('Pause') : p.title}{' '}
                      {p.kind === 'encore' ? `(${t('Zugabe')})` : ''}
                    </li>
                  ))}
                </ol>
              )}
              {r.settlement && (
                <p>
                  {t('Meine Vergütung')}: {r.settlement.total} EUR ·{' '}
                  {r.settlement.paid ? t('Ausgezahlt') : t('Freigegeben')} ({t('Gage')}:{' '}
                  {r.settlement.fee} EUR, {t('Pauschale')}: {r.settlement.allowance} EUR,{' '}
                  {t('Auslagen')}: {r.settlement.expenses} EUR)
                </p>
              )}
              <p>
                {new Date(r.starts_at).toLocaleString()} · {r.location} · {r.instrument}{' '}
                {r.register}
              </p>
              <dl className="music-details">
                {(r.meeting_at || r.meeting_place) && (
                  <div>
                    <dt>{t('Treffpunkt')}</dt>
                    <dd>
                      {[
                        r.meeting_at ? new Date(r.meeting_at).toLocaleString() : '',
                        r.meeting_place,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </dd>
                  </div>
                )}
                {!!r.uniform && (
                  <div>
                    <dt>{t('Uniform')}</dt>
                    <dd>{r.uniform}</dd>
                  </div>
                )}
              </dl>
              <MusicStatus status={r.cancelled ? 'declined' : r.status} />
              {!r.cancelled && (
                <div className="actions">
                  {[
                    ['accepted', t('Zusagen')],
                    ['declined', t('Absagen')],
                  ].map(([status, label]) => (
                    <button
                      key={status}
                      className="button button-ghost"
                      aria-pressed={r.status === status}
                      disabled={busy || (status === 'accepted' && !!r.availability?.length)}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await api.post(url, { id: r.id, status })
                          await load.reload()
                        } catch (err) {
                          setError(errorMessage(err))
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
              {!!r.availability?.length && <AvailabilityHint reasons={r.availability} />}
            </article>
          ))}
        </section>
      )}
      <OwnPracticePanel accessId={accessId} />
    </>
  )
}
