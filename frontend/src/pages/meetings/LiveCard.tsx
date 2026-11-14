// Versammlungen V7: Anmelden per App (wechselnder QR-Code), Teilnahme aus der Ferne und
// Online-Abstimmung aus Sicht der Leitung (docs/versammlungen.md).
import { useEffect, useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { meetingApi } from '../../api/meetings.ts'
import type { LiveState, Meeting, Poll } from '../../api/meetings.ts'
import { confirmDialog } from '../../components/dialog.ts'
import { errorMessage } from '../../components/forms.ts'
import { t } from '../../i18n/index.ts'
import { Loading } from '../../components/ui.tsx'
import { checkinLink } from './live.ts'

function pollStatusLabel(poll: Poll) {
  if (poll.status === 'draft') return t('vorbereitet')
  if (poll.status === 'open') return t('läuft')
  return t('beendet')
}

export function LiveCard({
  base,
  meeting,
  onChanged,
}: {
  base: string
  meeting: Meeting
  onChanged: () => Promise<void>
}) {
  const [state, setState] = useState<LiveState | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [big, setBig] = useState(false)
  useEffect(() => {
    let stopped = false
    const timer = { id: 0 }
    const load = async () => {
      try {
        const next = await meetingApi.live(base, meeting.id)
        if (stopped) return
        setState(next)
        // Neu laden, sobald der Code wechselt, sonst alle 5 Sekunden (Stimmen zählen mit)
        const wait = next.checkin_open ? Math.min(5, next.refresh_in ?? 5) : 15
        timer.id = window.setTimeout(load, wait * 1000)
      } catch (err) {
        if (stopped) return
        setError(errorMessage(err))
        timer.id = window.setTimeout(load, 15000)
      }
    }
    void load()
    return () => {
      stopped = true
      window.clearTimeout(timer.id)
    }
  }, [base, meeting.id])
  if (!state) return error ? <p role="alert">{error}</p> : <Loading />
  const send = async (action: () => Promise<LiveState>, reloadMeeting = false) => {
    setBusy(true)
    setError('')
    try {
      setState(await action())
      if (reloadMeeting) await onChanged()
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  const link = state.checkin_open && state.code ? checkinLink(state) : ''
  return (
    <section className="card stack live-card">
      <h2>{t('Anmelden per App und Online-Abstimmung')}</h2>
      <p className="muted">
        {t(
          'Mitglieder scannen den Code mit der HUBIplan-App oder der Handykamera und tippen „Ich bin da“. Der Code wechselt alle 30 Sekunden, ein Foto davon hilft also niemandem außerhalb des Saals.',
        )}
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="button-row">
        <button
          type="button"
          className={state.checkin_open ? 'button button-ghost' : 'button'}
          disabled={busy}
          onClick={() =>
            send(() => meetingApi.setLive(base, meeting.id, { open: !state.checkin_open }), true)
          }
        >
          {state.checkin_open ? t('Anmeldung schließen') : t('Anmeldung per App öffnen')}
        </button>
        {state.checkin_open && (
          <button type="button" className="button button-ghost" onClick={() => setBig(true)}>
            {t('Code groß zeigen')}
          </button>
        )}
      </div>
      {state.remote_allowed && (
        <label className="checkbox">
          <input
            type="checkbox"
            checked={state.remote}
            disabled={busy}
            onChange={(e) =>
              send(() => meetingApi.setLive(base, meeting.id, { remote: e.target.checked }), true)
            }
          />
          {t('Teilnahme aus der Ferne für diese Versammlung erlauben')}
        </label>
      )}
      {link && (
        <div className="live-code">
          <QRCodeSVG value={link} size={220} marginSize={2} title={t('QR-Code zum Anmelden')} />
          <p className="muted small">
            {t('Neuer Code in {n} Sekunden.', { n: state.refresh_in ?? 0 })}
          </p>
        </div>
      )}
      <p role="status">
        {t(
          'Per App angemeldet: {app}. Aus der Ferne: {online}. Stimmen insgesamt (mit Vollmachten): {entitled} von {voters} Stimmberechtigten.',
          {
            app: state.present_app,
            online: state.present_online,
            entitled: state.entitled,
            voters: state.voters,
          },
        )}
      </p>
      {big && link && (
        <div
          className="live-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t('QR-Code zum Anmelden')}
        >
          <QRCodeSVG value={link} size={520} marginSize={2} title={t('QR-Code zum Anmelden')} />
          <p>{t('Mit der HUBIplan-App oder der Handykamera scannen.')}</p>
          <button type="button" className="button" onClick={() => setBig(false)} autoFocus>
            {t('Schließen')}
          </button>
        </div>
      )}
      <h3>{t('Online-Abstimmungen')}</h3>
      {!state.online_voting ? (
        <p className="muted">
          {t(
            'Bei dieser Art ist die Online-Abstimmung ausgeschaltet. Einschalten lässt sie sich unter Arten (Einstellungen der Art).',
          )}
        </p>
      ) : (
        <>
          {state.polls.length === 0 && (
            <p className="muted">{t('Noch keine Abstimmung angelegt.')}</p>
          )}
          {state.polls.map((poll) => (
            <PollRow
              key={poll.id}
              poll={poll}
              busy={busy}
              onAction={(action) =>
                send(
                  () => meetingApi.pollAction(base, meeting.id, poll.id, action),
                  action === 'apply',
                )
              }
              onRemove={() => send(() => meetingApi.removePoll(base, meeting.id, poll.id))}
            />
          ))}
          <NewPoll
            meeting={meeting}
            busy={busy}
            onCreate={(draft) => send(() => meetingApi.createPoll(base, meeting.id, draft))}
          />
        </>
      )}
    </section>
  )
}

function PollRow({
  poll,
  busy,
  onAction,
  onRemove,
}: {
  poll: Poll
  busy: boolean
  onAction: (action: 'open' | 'close' | 'apply') => void
  onRemove: () => void
}) {
  return (
    <div className="poll-row stack">
      <div>
        <strong>
          {poll.agenda_number || poll.agenda_position}. {poll.agenda_title}
        </strong>
        {' · '}
        {poll.question}
        {poll.candidate && ` · ${poll.candidate}`}
        {poll.office && ` · ${poll.office}`} <span className="badge">{pollStatusLabel(poll)}</span>{' '}
        <span className="badge">{poll.secret ? t('geheim') : t('offen')}</span>
      </div>
      {poll.status !== 'draft' && (
        <p role="status">
          {t('{cast} von {entitled} Stimmen abgegeben.', {
            cast: poll.cast,
            entitled: poll.entitled,
          })}
        </p>
      )}
      {poll.result && (
        <ul className="poll-result">
          {poll.result.map((r) => (
            <li key={r.id}>
              {r.label}: <strong>{r.votes}</strong>
            </li>
          ))}
        </ul>
      )}
      {poll.open_votes && poll.open_votes.length > 0 && (
        <details>
          <summary>{t('Wer wie gestimmt hat')}</summary>
          <ul>
            {poll.open_votes.map((v, i) => (
              <li key={i}>
                {v.name}: {v.option}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="button-row">
        {poll.status === 'draft' && (
          <>
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => onAction('open')}
            >
              {t('Abstimmung starten')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={onRemove}
            >
              {t('Löschen')}
            </button>
          </>
        )}
        {poll.status === 'open' && (
          <button
            type="button"
            className="button"
            disabled={busy}
            onClick={async () => {
              const missing = poll.entitled - poll.cast
              if (
                missing > 0 &&
                !(await confirmDialog({
                  title: t('Abstimmung beenden?'),
                  message: t('{n} Stimmen fehlen noch. Danach kann niemand mehr abstimmen.', {
                    n: missing,
                  }),
                  confirmLabel: t('Beenden'),
                }))
              )
                return
              onAction('close')
            }}
          >
            {t('Abstimmung beenden')}
          </button>
        )}
        {poll.status === 'closed' && (
          <button
            type="button"
            className={poll.resolution ? 'button button-ghost' : 'button'}
            disabled={busy}
            onClick={() => onAction('apply')}
          >
            {poll.resolution ? t('Erneut ins Protokoll übernehmen') : t('Ins Protokoll übernehmen')}
          </button>
        )}
      </div>
    </div>
  )
}

function NewPoll({
  meeting,
  busy,
  onCreate,
}: {
  meeting: Meeting
  busy: boolean
  onCreate: (draft: {
    agenda_item: number
    question: string
    secret: boolean
    office: string
    candidates: { name: string }[]
  }) => Promise<void>
}) {
  const items = (meeting.agenda ?? []).filter(
    (a) => a.id && (a.type === 'resolution' || a.type === 'election'),
  )
  const [item, setItem] = useState<number | ''>('')
  const [question, setQuestion] = useState('')
  const [secret, setSecret] = useState(false)
  const [office, setOffice] = useState('')
  const [candidates, setCandidates] = useState('')
  if (items.length === 0)
    return (
      <p className="muted">{t('Die Tagesordnung hat keinen Punkt vom Typ Beschluss oder Wahl.')}</p>
    )
  const chosen = items.find((a) => a.id === item)
  const election = chosen?.type === 'election'
  return (
    <form
      className="stack poll-new"
      onSubmit={async (e) => {
        e.preventDefault()
        if (!item) return
        await onCreate({
          agenda_item: item,
          question,
          secret,
          office: election ? office : '',
          candidates: election
            ? candidates
                .split('\n')
                .map((name) => name.trim())
                .filter(Boolean)
                .map((name) => ({ name }))
            : [],
        })
        setQuestion('')
        setOffice('')
        setCandidates('')
      }}
    >
      <h4>{t('Neue Abstimmung')}</h4>
      <label className="field">
        <span>{t('Tagesordnungspunkt')}</span>
        <select
          value={item}
          onChange={(e) => setItem(e.target.value ? Number(e.target.value) : '')}
          required
        >
          <option value="">{t('Bitte wählen')}</option>
          {items.map((a) => (
            <option key={a.id} value={a.id ?? ''}>
              {a.number || a.position}. {a.title}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>
          {election
            ? t('Frage (leer: Titel des Punkts)')
            : t('Antrag oder Frage (leer: Titel des Punkts)')}
        </span>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={2000} />
      </label>
      {election && (
        <>
          <label className="field">
            <span>{t('Amt')}</span>
            <input value={office} onChange={(e) => setOffice(e.target.value)} maxLength={200} />
          </label>
          <label className="field">
            <span>
              {t('Zur Wahl (eine Person je Zeile; bei einer Person: Ja, Nein, Enthaltung)')}
            </span>
            <textarea
              rows={3}
              value={candidates}
              onChange={(e) => setCandidates(e.target.value)}
              required
            />
          </label>
        </>
      )}
      <label className="checkbox">
        <input type="checkbox" checked={secret} onChange={(e) => setSecret(e.target.checked)} />
        {t('Geheim abstimmen (niemand sieht, wer wie gestimmt hat)')}
      </label>
      <div className="button-row">
        <button type="submit" className="button" disabled={busy || !item}>
          {t('Abstimmung anlegen')}
        </button>
      </div>
    </form>
  )
}
