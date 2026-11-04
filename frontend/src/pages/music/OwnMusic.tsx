import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

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
        }[]
      >(url),
    [accessId],
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  if (!load.data?.length) return null
  return (
    <section className="card stack">
      <h2>{t('Meine Auftritte')}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      {load.data.map((r) => (
        <article className="stack" key={r.id}>
          <strong>{r.title}</strong>
          <p>
            {new Date(r.starts_at).toLocaleString()} · {r.location} · {r.instrument} {r.register}
          </p>
          <p>
            {r.meeting_at ? new Date(r.meeting_at).toLocaleString() : ''} · {r.meeting_place} ·{' '}
            {r.uniform}
          </p>
          <p>
            {r.cancelled
              ? t('Abgesagt')
              : r.status === 'accepted'
                ? t('Zugesagt')
                : r.status === 'declined'
                  ? t('Abgesagt')
                  : t('Angefragt')}
          </p>
          {!r.cancelled && (
            <div className="actions">
              {[
                ['accepted', t('Zusagen')],
                ['declined', t('Absagen')],
              ].map(([status, label]) => (
                <button
                  key={status}
                  className="button button-ghost"
                  disabled={busy}
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
        </article>
      ))}
    </section>
  )
}
