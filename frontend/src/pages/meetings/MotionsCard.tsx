// Anträge von Mitgliedern zu einer Versammlung (konzepte/versammlungen.md, Schritt V6):
// in die Tagesordnung aufnehmen oder mit Begründung ablehnen.
import { useState } from 'react'
import { meetingApi } from '../../api/meetings.ts'
import type { Meeting, Motion, MotionStatus } from '../../api/meetings.ts'
import { errorMessage } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'

export function motionStatusLabel(status: MotionStatus) {
  if (status === 'accepted') return t('in die Tagesordnung aufgenommen')
  if (status === 'rejected') return t('nicht aufgenommen')
  if (status === 'withdrawn') return t('zurückgezogen')
  return t('eingereicht')
}

export function MotionsCard({
  base,
  meeting,
  onChanged,
}: {
  base: string
  meeting: Meeting
  onChanged: () => Promise<void>
}) {
  const open = meeting.status === 'draft' || meeting.status === 'invited'
  return (
    <section className="card stack" aria-labelledby="motions">
      <h2 id="motions">{t('Anträge')}</h2>
      {(meeting.motions ?? []).map((m) => (
        <MotionRow
          key={m.id}
          base={base}
          meeting={meeting}
          motion={m}
          editable={meeting.can_edit && open && m.status === 'submitted'}
          onChanged={onChanged}
        />
      ))}
    </section>
  )
}

function MotionRow({
  base,
  meeting,
  motion,
  editable,
  onChanged,
}: {
  base: string
  meeting: Meeting
  motion: Motion
  editable: boolean
  onChanged: () => Promise<void>
}) {
  const [rejecting, setRejecting] = useState(false)
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const decide = async (data: object) => {
    setBusy(true)
    setError('')
    try {
      await meetingApi.decideMotion(base, meeting.id, motion.id, data)
      await onChanged()
    } catch (err) {
      setError(errorMessage(err))
      setBusy(false)
    }
  }
  return (
    <article className="stack motion">
      <h3>
        {motion.title}
        <span className="badge">{motionStatusLabel(motion.status)}</span>
      </h3>
      <p className="muted small">{t('Antrag von {name}', { name: motion.name })}</p>
      <p style={{ whiteSpace: 'pre-wrap' }}>{motion.text}</p>
      {motion.reply && <p className="muted">{t('Antwort: {reply}', { reply: motion.reply })}</p>}
      {error && <p role="alert">{error}</p>}
      {editable &&
        (rejecting ? (
          <form
            className="stack"
            aria-label={t('Antrag ablehnen: {title}', { title: motion.title })}
            onSubmit={(e) => {
              e.preventDefault()
              decide({ decision: 'reject', reply })
            }}
          >
            <label className="field">
              <span>{t('Begründung für das Mitglied')}</span>
              <textarea
                value={reply}
                maxLength={2000}
                required
                onChange={(e) => setReply(e.target.value)}
              />
            </label>
            <div className="button-row">
              <button
                type="button"
                className="button button-ghost"
                onClick={() => setRejecting(false)}
              >
                {t('Abbrechen')}
              </button>
              <button className="button button-danger" disabled={busy || !reply.trim()}>
                {t('Antrag ablehnen')}
              </button>
            </div>
          </form>
        ) : (
          <div className="button-row">
            <button
              type="button"
              className="button"
              disabled={busy}
              aria-label={t('In die Tagesordnung aufnehmen: {title}', { title: motion.title })}
              onClick={() => decide({ decision: 'accept' })}
            >
              {t('In die Tagesordnung aufnehmen')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => setRejecting(true)}
            >
              {t('Ablehnen')}
            </button>
          </div>
        ))}
    </article>
  )
}
