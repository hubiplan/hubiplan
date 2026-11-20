// Videoraum am Termin (Nextcloud Talk): Link und Passwort für alle, die den Termin sehen;
// anlegen und entfernen, wer den Termin bearbeitet und die Einheit Talk eingerichtet hat.
import { useState } from 'react'
import { eventApi } from '../../api/events.ts'
import type { CalendarBase, EventDetail } from '../../api/events.ts'
import { t } from '../../i18n/index.ts'
import { confirmDialog } from '../dialog.ts'
import { errorMessage } from '../forms.ts'
import { Alert } from '../ui.tsx'

export function VideoRoom({
  base,
  event,
  onChanged,
}: {
  base: CalendarBase
  event: EventDetail
  onChanged: (event: EventDetail) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const video = event.video
  if (!video && !event.video_available) return null

  async function run(action: () => Promise<EventDetail>) {
    setBusy(true)
    setError(null)
    try {
      onChanged(await action())
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function copy() {
    if (!video) return
    const text = video.password
      ? t('{url} (Passwort: {password})', { url: video.url, password: video.password })
      : video.url
    try {
      await navigator.clipboard.writeText(text)
      setNote(t('Link kopiert.'))
    } catch {
      setNote(t('Kopieren ging nicht. Bitte den Link markieren.'))
    }
  }

  async function remove() {
    if (
      !(await confirmDialog({
        final: false,
        title: t('Videoraum entfernen?'),
        message: t(
          'Der Raum wird in der Nextcloud gelöscht, mit seinem Chat. Wer den Link hat, kommt nicht mehr hinein.',
        ),
        confirmLabel: t('Entfernen'),
      }))
    )
      return
    await run(() => eventApi.removeVideo(base, event.id))
  }

  return (
    <>
      <dt>{t('Videoraum')}</dt>
      <dd>
        {error && <Alert kind="error">{error}</Alert>}
        {video ? (
          <div className="stack-sm">
            <div>
              <a href={video.url} target="_blank" rel="noopener noreferrer" className="break-all">
                {t('Videoraum öffnen')}
              </a>
              {video.password && (
                <div className="small">
                  {t('Passwort:')} <code>{video.password}</code>
                </div>
              )}
            </div>
            <div className="button-row">
              <button type="button" className="button button-ghost" onClick={() => void copy()}>
                {t('Link kopieren')}
              </button>
              {event.video_available !== undefined && (
                <button
                  type="button"
                  className="button button-ghost"
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  {t('Videoraum entfernen')}
                </button>
              )}
            </div>
            {note && <div className="muted small">{note}</div>}
          </div>
        ) : (
          <div className="stack-sm">
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void run(() => eventApi.createVideo(base, event.id))}
            >
              {t('Videoraum anlegen')}
            </button>
            <div className="muted small">
              {t(
                'Legt in der Nextcloud ein Gespräch mit Link und Passwort an. Beides sehen alle, die den Termin sehen, auch in Einladung und Erinnerung. Nach dem Termin wird der Raum gelöscht.',
              )}
            </div>
          </div>
        )}
      </dd>
    </>
  )
}
