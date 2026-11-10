import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError } from '../api/client.ts'
import type { ResponseStatus } from '../api/events.ts'
import { publicRsvpApi } from '../api/publicRsvp.ts'
import type { PublicRsvp } from '../api/publicRsvp.ts'
import { RouteLinks } from '../components/calendar/RouteLinks.tsx'
import { berlin, formatDay } from '../components/calendar/time.ts'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { usePublicImprint } from '../components/publicImprint.ts'
import { Alert, Field, Loading } from '../components/ui.tsx'
import { t, tn } from '../i18n/index.ts'

function statusLabel(status: ResponseStatus): string {
  if (status === 'yes') return t('Zusage')
  if (status === 'maybe') return t('Vielleicht')
  return t('Absage')
}

function size(bytes: number): string {
  return bytes >= 1024 * 1024
    ? t('{x} MB', { x: (bytes / 1024 / 1024).toFixed(1).replace('.', ',') })
    : t('{x} KB', { x: Math.max(1, Math.round(bytes / 1024)) })
}

/** Rückmeldung über den persönlichen Link aus der Mail (ohne Anmeldung). */
export function PublicRsvpPage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<PublicRsvp | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [status, setStatus] = useState<ResponseStatus | ''>('')
  const [guests, setGuests] = useState('0')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  usePublicImprint(info?.imprint_key, info?.club)

  function take(d: PublicRsvp) {
    setInfo(d)
    const mine = d.rsvp.mine
    setStatus(mine?.status ?? '')
    setGuests(String(mine?.guests ?? 0))
    setNote(mine?.note ?? '')
  }

  useEffect(() => {
    let alive = true
    publicRsvpApi
      .get(token)
      .then((d) => alive && take(d))
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) setInvalid(true)
        else setUnavailable(true)
      })
    return () => {
      alive = false
    }
  }, [token, attempt])

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!info || !status) return
    setBusy(true)
    setError(null)
    setNotice('')
    try {
      take(
        await publicRsvpApi.save(token, {
          status,
          guests: status === 'yes' && info.rsvp.guests_allowed ? Number(guests) || 0 : 0,
          note: info.rsvp.note_allowed ? note : '',
        }),
      )
      setNotice(t('Deine Rückmeldung ist gespeichert. Du kannst sie über denselben Link ändern.'))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const ev = info?.event
  const r = info?.rsvp
  const where = ev ? [ev.location, ev.address].filter(Boolean).join(', ') : ''
  const options: ResponseStatus[] = r?.maybe_allowed ? ['yes', 'maybe', 'no'] : ['yes', 'no']

  return (
    <main className="login-page">
      <div className="card public-photo stack-sm rsvp-public">
        <div className="login-logo">
          <Logo name={info?.club} logoUrl={null} />
        </div>
        <h1>{ev ? ev.title : t('Rückmeldung zum Termin')}</h1>
        {invalid && <Alert kind="error">{t('Dieser Link ist ungültig oder abgelaufen.')}</Alert>}
        {unavailable && (
          <>
            <Alert kind="error">
              {t('Die Seite kann gerade nicht geladen werden. Bitte später erneut versuchen.')}
            </Alert>
            <div className="button-row">
              <button
                type="button"
                className="button button-primary"
                onClick={() => {
                  setUnavailable(false)
                  setAttempt((n) => n + 1)
                }}
              >
                {t('Erneut versuchen')}
              </button>
            </div>
          </>
        )}
        {!info && !invalid && !unavailable && <Loading />}
        {info && ev && r && (
          <>
            <p className="muted">{info.owner}</p>
            {ev.is_cancelled && (
              <Alert kind="error">
                {t('Dieser Termin ist abgesagt.')} {ev.cancel_note}
              </Alert>
            )}
            <dl className="rsvp-public-facts">
              <dt>{t('Wann')}</dt>
              <dd>{ev.when}</dd>
              {where && (
                <>
                  <dt>{t('Wo')}</dt>
                  <dd>
                    {where}
                    <RouteLinks directions={ev.directions} links={ev.map_links} />
                  </dd>
                </>
              )}
              {r.deadline && (
                <>
                  <dt>{t('Anmeldeschluss')}</dt>
                  <dd>
                    {t('{x}, {time} Uhr', {
                      x: formatDay(berlin(r.deadline).date),
                      time: berlin(r.deadline).time,
                    })}
                  </dd>
                </>
              )}
            </dl>
            {ev.description && <p className="rsvp-public-text">{ev.description}</p>}
            {info.attachments.length > 0 && (
              <section className="stack-sm" aria-label={t('Anhänge')}>
                <strong>{t('Anhänge')}</strong>
                <ul className="plain-list">
                  {info.attachments.map((a) => (
                    <li key={a.id}>
                      <a href={a.url} target="_blank" rel="noreferrer">
                        {a.name}
                      </a>{' '}
                      <span className="muted small">({size(a.size)})</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <p>
              {t('Hallo {first_name},', { first_name: info.first_name })}{' '}
              {r.mine
                ? t('deine Rückmeldung: {x}.', { x: statusLabel(r.mine.status) })
                : t('du hast dich noch nicht zurückgemeldet.')}
              {r.mine &&
                r.mine.guests > 0 &&
                tn(' Mit {n} Begleitperson.', ' Mit {n} Begleitpersonen.', r.mine.guests)}
            </p>
            {r.free !== null && (
              <p className="muted small">
                {r.free > 0
                  ? t('Noch {free} Plätze frei.', { free: r.free })
                  : t('Alle Plätze sind vergeben.')}
              </p>
            )}
            {notice && <Alert kind="success">{notice}</Alert>}
            {error && <Alert kind="error">{error}</Alert>}
            {r.can_respond ? (
              <form className="stack-sm" onSubmit={save} aria-label={t('Rückmeldung')}>
                <fieldset className="stack-sm">
                  <legend>{t('Kommst du?')}</legend>
                  {options.map((o) => (
                    <label key={o} className="checkbox">
                      <input
                        type="radio"
                        name="status"
                        value={o}
                        checked={status === o}
                        onChange={() => setStatus(o)}
                      />
                      <span>
                        {o === 'yes'
                          ? t('Ich komme')
                          : o === 'maybe'
                            ? t('Vielleicht')
                            : t('Ich komme nicht')}
                      </span>
                    </label>
                  ))}
                </fieldset>
                {status === 'yes' && r.guests_allowed && (
                  <Field
                    label={t('Begleitpersonen')}
                    type="number"
                    min={0}
                    max={r.max_guests}
                    value={guests}
                    onChange={(e) => setGuests(e.target.value)}
                  />
                )}
                {r.note_allowed && (
                  <Field
                    label={r.note_question || t('Bemerkung (optional)')}
                    value={note}
                    maxLength={200}
                    onChange={(e) => setNote(e.target.value)}
                  />
                )}
                <div className="button-row">
                  <button
                    type="submit"
                    className="button button-primary"
                    disabled={busy || !status}
                  >
                    {t('Speichern')}
                  </button>
                </div>
              </form>
            ) : (
              r.reason && <p className="muted small">{r.reason}</p>
            )}
          </>
        )}
      </div>
    </main>
  )
}
