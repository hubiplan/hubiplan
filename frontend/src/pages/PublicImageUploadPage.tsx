import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { imageUploadApi } from '../api/imageUpload.ts'
import type { ImageUploadInfo } from '../api/imageUpload.ts'
import { formatDateTime } from '../components/forms.ts'
import { Logo } from '../components/Logo.tsx'
import { Alert, Loading } from '../components/ui.tsx'
import { usePublicImprint } from '../components/publicImprint.ts'
import { applyTheme } from '../theme/theme.ts'
import { t } from '../i18n/index.ts'

interface Row {
  name: string
  state: 'waiting' | 'busy' | 'done' | 'error'
  message?: string
}

/** Link zum Hochladen von Bildern für die Webseite, den ein KI-Assistent angelegt hat. */
export function PublicImageUploadPage() {
  const token = useParams().token ?? ''
  const [info, setInfo] = useState<ImageUploadInfo | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'invalid' | 'unavailable'>('loading')
  const [rows, setRows] = useState<Row[]>([])
  const [busy, setBusy] = useState(false)
  usePublicImprint(info?.imprint_key, info?.organization)

  useEffect(() => {
    let alive = true
    imageUploadApi
      .info(token)
      .then(({ status, body }) => {
        if (!alive) return
        if (status === 200) {
          setInfo(body)
          applyTheme(body.theme)
          setState('ready')
        } else if (status === 404 || status === 410 || status === 429) {
          setState('invalid')
        } else {
          setState('unavailable')
        }
      })
      .catch(() => alive && setState('unavailable'))
    return () => {
      alive = false
    }
  }, [token])

  async function upload(files: File[]) {
    if (!info || files.length === 0) return
    const chosen = files.slice(0, info.remaining)
    const start = rows.length
    setRows((r) => [...r, ...chosen.map((f) => ({ name: f.name, state: 'waiting' as const }))])
    setBusy(true)
    let left = info.remaining
    for (const [i, file] of chosen.entries()) {
      const at = start + i
      const mark = (row: Partial<Row>) =>
        setRows((r) => r.map((x, j) => (j === at ? { ...x, ...row } : x)))
      mark({ state: 'busy' })
      try {
        const { status, body } = await imageUploadApi.upload(token, file)
        if (status === 201) {
          left = typeof body.remaining === 'number' ? body.remaining : left - 1
          mark({ state: 'done' })
        } else if (status === 404) {
          mark({ state: 'error', message: t('Der Link ist nicht mehr gültig.') })
          left = 0
          break
        } else if (status === 429) {
          const detail = typeof body.detail === 'string' ? body.detail : ''
          mark({
            state: 'error',
            message: detail || t('Zu viele Versuche. Bitte später erneut versuchen.'),
          })
          break
        } else {
          const text = Object.values(body).flat().join(' ')
          mark({ state: 'error', message: text || t('Das hat nicht geklappt.') })
        }
      } catch {
        mark({ state: 'error', message: t('Der Server ist nicht erreichbar.') })
      }
    }
    setInfo((x) => (x ? { ...x, remaining: Math.max(0, left) } : x))
    setBusy(false)
  }

  const done = rows.filter((r) => r.state === 'done').length

  return (
    <main className="login-page">
      <div className="card public-photo">
        <div className="login-logo">
          <Logo name={info?.organization} logoUrl={info?.logo_url ?? null} />
        </div>
        {state === 'loading' && <Loading />}
        {state === 'invalid' && (
          <Alert kind="error">
            {t('Dieser Link ist nicht (mehr) gültig. Lass dir im Chat einen neuen geben.')}
          </Alert>
        )}
        {state === 'unavailable' && (
          <Alert kind="error">
            {t(
              'Die Seite kann gerade nicht geladen werden. Bitte Verbindung prüfen und erneut versuchen.',
            )}
          </Alert>
        )}
        {state === 'ready' && info && (
          <>
            <h1>{t('Bilder für die Webseite')}</h1>
            <p>
              {t(
                'Wähle Fotos für die Webseite von {organization}. Sie landen unter Webseite › Bilder und sind erst öffentlich, wenn jemand sie in einen veröffentlichten Text oder Abschnitt einbaut.',
                { organization: info.organization },
              )}
            </p>
            <p className="muted small">
              {t('Gültig bis {x}, noch {n} Bilder.', {
                x: formatDateTime(info.expires_at),
                n: info.remaining,
              })}
            </p>
            {info.remaining > 0 && (
              <label className="button button-primary">
                {t('Bilder auswählen')}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  multiple
                  hidden
                  disabled={busy}
                  onChange={(e) => {
                    const files = Array.from(e.target.files ?? [])
                    e.target.value = ''
                    void upload(files)
                  }}
                />
              </label>
            )}
            {rows.length > 0 && (
              <ul className="plain-list">
                {rows.map((r, i) => (
                  <li key={i}>
                    {r.name}: {r.state === 'waiting' && t('wartet')}
                    {r.state === 'busy' && t('wird hochgeladen …')}
                    {r.state === 'done' && t('gespeichert')}
                    {r.state === 'error' && (r.message ?? t('Das hat nicht geklappt.'))}
                  </li>
                ))}
              </ul>
            )}
            {done > 0 && !busy && (
              <Alert kind="success">
                {t(
                  'Fertig. Sag im Chat Bescheid; der Assistent sieht die neuen Bilder und kann sie beschreiben und einbauen.',
                )}
              </Alert>
            )}
          </>
        )}
      </div>
    </main>
  )
}
