import { useState } from 'react'
import { api } from '../../api/client.ts'
import { errorMessage, formatDateTime, useLoad } from '../../components/forms.ts'
import { Alert } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'
import { AvailabilityHint } from './AvailabilityPage.tsx'
import { MusicStatus, MusicEmptyState } from './MusicLayout.tsx'

type Score = { id: number; piece: string; title: string; url: string; usage_note: string }

export function OwnPracticePanel({ accessId }: { accessId: number }) {
  const url = `/api/portal/${accessId}/music/practice/`
  const load = useLoad(
    () =>
      api.get<{
        rehearsals: {
          id: number
          title: string
          original_start: string
          starts_at: string
          ends_at: string
          focus: string
          location: string
          cancelled: boolean
          can_respond: boolean
          status: string
          availability?: string[]
          items: { title: string; focus: string }[]
          scores?: Score[]
          overridden?: boolean
        }[]
        scores: Score[]
        loans: {
          id: number
          title: string
          quantity: number
          returned: number
          due_on: string
          overdue: boolean
        }[]
      }>(url),
    [accessId],
  )
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false)
  const d = load.data
  if (load.error) return <Alert kind="error">{load.error}</Alert>
  if (!d || (!d.rehearsals.length && !d.scores.length && !d.loans.length)) return null
  return (
    <section className="card stack music-personal">
      <h2>{t('Meine Proben und Noten')}</h2>
      {error && <Alert kind="error">{error}</Alert>}
      {d.rehearsals.map((r) => (
        <article className="stack" key={`${r.id}-${r.original_start}`}>
          <strong>
            {r.title} · {formatDateTime(r.starts_at)}
          </strong>
          <p>{[r.location, r.focus].filter(Boolean).join(' · ')}</p>
          <MusicStatus status={r.cancelled ? 'declined' : r.status} />
          {r.items.map((i, index) => (
            <p key={index}>
              {i.title} · {i.focus}
            </p>
          ))}
          {r.overridden && <p>{t('Eigenes Programm für diesen Termin')}</p>}
          {r.scores && r.scores.length > 0 && (
            <div>
              <h3>{t('Noten für diesen Probentermin')}</h3>
              {r.scores.map((s) => (
                <p key={s.id}>
                  <a href={s.url}>
                    {s.piece} · {s.title}
                  </a>{' '}
                  · {s.usage_note}
                </p>
              ))}
            </div>
          )}
          {r.can_respond && (
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
                      await api.post(url, { id: r.id, original_start: r.original_start, status })
                      await load.reload()
                    } catch (e) {
                      setError(errorMessage(e))
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
      <h3>{t('Meine Notenunterlagen')}</h3>
      {!d.scores.length && <MusicEmptyState />}
      {d.scores.map((s) => (
        <p key={s.id}>
          <a href={s.url}>
            {s.piece} · {s.title}
          </a>{' '}
          · {s.usage_note}
        </p>
      ))}
      <h3>{t('Meine Notenausgaben')}</h3>
      {!d.loans.length && <MusicEmptyState />}
      {d.loans.map((l) => (
        <p key={l.id}>
          {l.title} · {t('Noch zurückzugeben')}: {l.quantity - l.returned} · {t('Rückgabe bis')}:{' '}
          {l.due_on} {l.overdue ? t('Rückgabe überfällig') : ''}
        </p>
      ))}
    </section>
  )
}
