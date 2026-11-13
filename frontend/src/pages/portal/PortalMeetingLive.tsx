// Versammlungen V7 im Mitgliederbereich: „Ich bin da“ per Code vom Bildschirm der Leitung,
// Teilnahme aus der Ferne, „Ich gehe“ und Online-Abstimmung (docs/versammlungen.md).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portalMeetingApi } from '../../api/meetings.ts'
import type { Poll, PortalLive } from '../../api/meetings.ts'
import { errorMessage } from '../../components/forms.ts'
import { Loading } from '../../components/ui.tsx'
import { t } from '../../i18n/index.ts'

function voteLabel(v: NonNullable<Poll['votes']>[number]) {
  if (v.how === 'own') return t('Deine Stimme')
  if (v.how === 'proxy') return t('Vollmacht von {name}', { name: v.name })
  return t('Für {name}', { name: v.name })
}

export function PortalMeetingLive({
  accessId,
  meetingId,
  code,
}: {
  accessId: number
  meetingId: number
  code?: string
}) {
  const [state, setState] = useState<PortalLive | null>(null)
  const [error, setError] = useState('')
  const [missing, setMissing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [usedCode, setUsedCode] = useState(false)
  useEffect(() => {
    let stopped = false
    const timer = { id: 0 }
    const load = async () => {
      try {
        const next = await portalMeetingApi.live(accessId, meetingId)
        if (!stopped) {
          setState(next)
          setMissing(false)
        }
      } catch (err) {
        if (!stopped) {
          if ((err as { status?: number }).status === 404) setMissing(true)
          else setError(errorMessage(err))
        }
      }
      if (!stopped) timer.id = window.setTimeout(load, 4000)
    }
    void load()
    return () => {
      stopped = true
      window.clearTimeout(timer.id)
    }
  }, [accessId, meetingId])
  const send = async (action: () => Promise<PortalLive>) => {
    setBusy(true)
    setError('')
    try {
      setState(await action())
      setMissing(false)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const present = state?.status === 'present'
  // Mit Code aus dem Scan, aber die Seite kennt die Versammlung (noch) nicht: einfach anmelden
  if (missing && !state)
    return code && !usedCode ? (
      <section className="card stack">
        <h2>{t('Anmelden zur Versammlung')}</h2>
        {error && <p role="alert">{error}</p>}
        <div className="button-row">
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={() => {
              setUsedCode(true)
              void send(() => portalMeetingApi.checkin(accessId, meetingId, { code }))
            }}
          >
            {t('Ich bin da')}
          </button>
        </div>
      </section>
    ) : (
      <section className="card stack">
        <p className="muted">
          {t('Die Anmeldung zu dieser Versammlung ist nicht geöffnet.')}{' '}
          <Link to="/mein-bereich/versammlungen">{t('Zu den Versammlungen')}</Link>
        </p>
        {error && <p role="alert">{error}</p>}
      </section>
    )
  if (!state) return error ? <p role="alert">{error}</p> : <Loading />
  return (
    <>
      <section className="card stack">
        <h2>{state.title}</h2>
        <p className="muted">
          {state.kind_name}
          {state.unit && ` · ${state.unit}`}
          {state.location && ` · ${state.location}`}
        </p>
        {error && <p role="alert">{error}</p>}
        <p role="status">
          {present
            ? state.mode === 'online'
              ? t('Du nimmst aus der Ferne teil.')
              : t('Du bist als anwesend eingetragen.')
            : state.status === 'left'
              ? t('Du hast dich abgemeldet.')
              : t('Du bist noch nicht angemeldet.')}
          {present &&
            state.votes > 1 &&
            ` ${t('Du hast {n} Stimmen (mit Vollmachten).', { n: state.votes })}`}
        </p>
        {state.is_organization && (
          <p className="muted">
            {t('Organisationsmitglieder trägt die Leitung mit ihrem Vertreter ein.')}
          </p>
        )}
        <div className="button-row">
          {!present && !state.is_organization && state.checkin_open && code && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => send(() => portalMeetingApi.checkin(accessId, meetingId, { code }))}
            >
              {t('Ich bin da')}
            </button>
          )}
          {!present && !state.is_organization && state.remote && state.voter && (
            <button
              type="button"
              className={code ? 'button button-ghost' : 'button'}
              disabled={busy}
              onClick={() =>
                send(() => portalMeetingApi.checkin(accessId, meetingId, { remote: true }))
              }
            >
              {t('Online teilnehmen')}
            </button>
          )}
          {present && (
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => send(() => portalMeetingApi.leave(accessId, meetingId))}
            >
              {t('Ich gehe')}
            </button>
          )}
        </div>
        {!present && !code && state.checkin_open && !state.remote && (
          <p className="muted">
            {t('Zum Anmelden den QR-Code im Saal mit der App oder der Handykamera scannen.')}
          </p>
        )}
      </section>
      {state.polls.length > 0 && (
        <section className="card stack">
          <h2>{t('Abstimmungen')}</h2>
          {state.polls.map((poll) => (
            <PollCard
              key={poll.id}
              poll={poll}
              busy={busy}
              onVote={(votes) =>
                send(() => portalMeetingApi.vote(accessId, meetingId, poll.id, votes))
              }
            />
          ))}
        </section>
      )}
    </>
  )
}

function PollCard({
  poll,
  busy,
  onVote,
}: {
  poll: Poll
  busy: boolean
  onVote: (votes: { attendance: number; option: number }[]) => Promise<void>
}) {
  const [choice, setChoice] = useState<Record<number, number>>({})
  const open = (poll.votes ?? []).filter((v) => !v.done)
  const done = (poll.votes ?? []).filter((v) => v.done)
  return (
    <article className="stack poll-row">
      <h3>
        {poll.agenda_position}. {poll.question}
      </h3>
      <p className="muted">
        {[
          poll.candidate,
          poll.office,
          poll.secret ? t('geheime Abstimmung') : t('offene Abstimmung'),
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {poll.status === 'open' && open.length > 0 && (
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            void onVote(
              open.map((v) => ({ attendance: v.attendance, option: choice[v.attendance] })),
            )
          }}
        >
          {open.map((v) => (
            <fieldset key={v.attendance} className="stack">
              <legend>{voteLabel(v)}</legend>
              {poll.options.map((o) => (
                <label key={o.id} className="checkbox">
                  <input
                    type="radio"
                    name={`p${poll.id}-${v.attendance}`}
                    checked={choice[v.attendance] === o.id}
                    onChange={() => setChoice({ ...choice, [v.attendance]: o.id })}
                    required
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>
          ))}
          <p className="muted small">{t('Eine abgegebene Stimme lässt sich nicht mehr ändern.')}</p>
          <div className="button-row">
            <button
              type="submit"
              className="button"
              disabled={busy || open.some((v) => !choice[v.attendance])}
            >
              {open.length > 1 ? t('Stimmen abgeben') : t('Stimme abgeben')}
            </button>
          </div>
        </form>
      )}
      {poll.status === 'open' && open.length === 0 && done.length > 0 && (
        <p role="status">
          {t('Danke, deine Stimme ist abgegeben. Das Ergebnis kommt nach dem Ende.')}
        </p>
      )}
      {poll.status === 'open' && (poll.votes ?? []).length === 0 && (
        <p className="muted">{t('Abstimmen können nur anwesende Stimmberechtigte.')}</p>
      )}
      {poll.status === 'closed' && poll.result && (
        <>
          <p>{t('Ergebnis:')}</p>
          <ul className="poll-result">
            {poll.result.map((r) => (
              <li key={r.id}>
                {r.label}: <strong>{r.votes}</strong>
              </li>
            ))}
          </ul>
        </>
      )}
    </article>
  )
}
