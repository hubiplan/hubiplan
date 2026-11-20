import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { publicConfirmApi } from '../api/circulars.ts'
import type { PublicConfirm, PublicConfirmEvent } from '../api/circulars.ts'
import { ApiError } from '../api/client.ts'
import { MarkupPreview } from '../components/circulars/MarkupEditor.tsx'
import { errorMessage } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { Alert, Checkbox, Loading } from '../components/ui.tsx'
import { formatDateTime } from '../components/forms.ts'
import { formatDay } from '../i18n/format.ts'
import { t } from '../i18n/index.ts'

/** Bestätigungslink aus der Mail an den Absender eines Verteilers (ohne Anmeldung).
 *  Erst der Knopf versendet: Virenscanner öffnen Links in Mails oft vorab. */
export function PublicCircularConfirmPage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<PublicConfirm | null>(null)
  const [invalid, setInvalid] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [choice, setChoice] = useState<{ rsvp?: boolean; video?: boolean }>({})

  useEffect(() => {
    let alive = true
    publicConfirmApi
      .get(token)
      .then((d) => alive && setInfo(d))
      .catch((err) => {
        if (!alive) return
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) setInvalid(true)
        else setUnavailable(true)
      })
    return () => {
      alive = false
    }
  }, [token, attempt])

  async function act(action: 'send' | 'discard') {
    setBusy(true)
    setError(null)
    try {
      setInfo(await publicConfirmApi.act(token, action, info?.event ? choice : undefined))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const counts = info?.counts
  return (
    <main className="login-page">
      <div className="card public-photo">
        <div className="login-logo">
          <Logo name={info?.organization} logoUrl={null} />
        </div>
        <h1>{info?.event ? t('Termin bestätigen') : t('Rundschreiben bestätigen')}</h1>
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
        {info?.event && (
          <EventConfirm
            info={info}
            event={info.event}
            choice={choice}
            setChoice={setChoice}
            busy={busy}
            act={(action) => void act(action)}
          />
        )}
        {info && !info.event && (
          <>
            <p>
              <strong>{info.subject}</strong>
              <br />
              <span className="muted small">
                {t('an den Verteiler {list} ({address})', {
                  list: info.list,
                  address: info.address,
                })}
              </span>
            </p>
            {counts && (
              <p>
                {t('Empfänger:')}{' '}
                {'app' in counts && counts.app ? t('{app} per App, ', { app: counts.app }) : ''}
                {counts.mail} {t('per E-Mail')}
                {counts.letter ? t(', {letter} per Brief', { letter: counts.letter }) : ''}
              </p>
            )}
            {info.body && (
              <div className="subcard">
                <MarkupPreview text={info.body} />
              </div>
            )}
            {info.attachments.length > 0 && (
              <p className="small">
                {t('Anhänge:')} {info.attachments.join(', ')}
              </p>
            )}
            {info.status === 'waiting' ? (
              <div className="button-row">
                <button
                  type="button"
                  className="button button-primary"
                  disabled={busy}
                  onClick={() => void act('send')}
                >
                  {t('Jetzt versenden')}
                </button>
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void act('discard')}
                >
                  {t('Verwerfen')}
                </button>
              </div>
            ) : (
              <Alert kind={info.status === 'sent' ? 'success' : 'info'}>
                {info.status === 'sent'
                  ? t(
                      'Das Rundschreiben wird versendet. Briefe für Mitglieder ohne E-Mail findest du in HUBIplan unter Rundschreiben.',
                    )
                  : t('Stand: {status_label}.', { status_label: info.status_label })}
              </Alert>
            )}
          </>
        )}
        {error && <Alert kind="error">{error}</Alert>}
      </div>
    </main>
  )
}

const ACTION_LABELS = {
  new: () => t('Neuer Termin'),
  update: () => t('Geänderter Termin'),
  cancel: () => t('Absage'),
}

function when(e: PublicConfirmEvent): string {
  if (e.all_day) {
    const day = formatDay(e.starts_at)
    return t('{day}, ganztägig', { day })
  }
  return t('{start} bis {end}', {
    start: formatDateTime(e.starts_at),
    end: formatDateTime(e.ends_at),
  })
}

/** Termineinladung an einen Verteiler (Termine aus dem Mailprogramm) bestätigen. */
function EventConfirm({
  info,
  event: e,
  choice,
  setChoice,
  busy,
  act,
}: {
  info: PublicConfirm
  event: PublicConfirmEvent
  choice: { rsvp?: boolean; video?: boolean }
  setChoice: (c: { rsvp?: boolean; video?: boolean }) => void
  busy: boolean
  act: (action: 'send' | 'discard') => void
}) {
  const options = e.options
  return (
    <>
      <p>
        <span className="muted small">{ACTION_LABELS[e.action]()}</span>
        <br />
        <strong>{e.title}</strong>
        <br />
        <span className="muted small">
          {t('an den Verteiler {list} ({address})', { list: info.list, address: info.address })}
        </span>
      </p>
      <ul className="plain-list">
        <li>{t('Wann: {when}', { when: when(e) })}</li>
        {e.location && <li>{t('Wo: {where}', { where: e.location })}</li>}
        {e.video_url && (
          <li>
            {t('Video:')}{' '}
            <a href={e.video_url} target="_blank" rel="noreferrer noopener">
              {e.video_url}
            </a>
          </li>
        )}
        {e.repeat && <li>{t('Wiederholt sich')}</li>}
        {e.visibility && (
          <li>
            {e.visibility === 'board'
              ? t('Sichtbar: nur Vorstand')
              : t('Sichtbar: Mitglieder (nicht öffentlich)')}
          </li>
        )}
      </ul>
      {e.description && e.action !== 'cancel' && (
        <div className="subcard">
          <p className="pre-line">{e.description}</p>
        </div>
      )}
      {e.attachments.length > 0 && (
        <p className="small">
          {t('Anhänge:')} {e.attachments.join(', ')}
        </p>
      )}
      {e.skipped.length > 0 && (
        <p className="small muted">
          {t('Nicht übernommen:')} {e.skipped.join('; ')}
        </p>
      )}
      {info.status === 'waiting' && options ? (
        <>
          {options.rsvp_possible && (
            <Checkbox
              label={t('Zu- und Absagen anbieten')}
              checked={choice.rsvp ?? options.rsvp}
              onChange={(on) => setChoice({ ...choice, rsvp: on })}
            />
          )}
          {options.video_possible && (
            <Checkbox
              label={t('Neuen Videoraum (Nextcloud Talk) anlegen')}
              checked={choice.video ?? options.video}
              onChange={(on) => setChoice({ ...choice, video: on })}
            />
          )}
          <div className="button-row">
            <button
              type="button"
              className="button button-primary"
              disabled={busy}
              onClick={() => act('send')}
            >
              {e.action === 'cancel' ? t('Absage übernehmen') : t('Übernehmen und informieren')}
            </button>
            <button
              type="button"
              className="button button-ghost"
              disabled={busy}
              onClick={() => act('discard')}
            >
              {t('Verwerfen')}
            </button>
          </div>
        </>
      ) : (
        <Alert kind={info.status === 'sent' ? 'success' : 'info'}>
          {info.status === 'sent'
            ? t('Übernommen. Der Verteiler wird informiert.')
            : t('Stand: {status_label}.', { status_label: info.status_label })}{' '}
          {e.event_url && <a href={e.event_url}>{t('Termin in HUBIplan ansehen')}</a>}
        </Alert>
      )}
    </>
  )
}
