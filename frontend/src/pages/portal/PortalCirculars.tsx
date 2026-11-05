// Mitgliederbereich: empfangene Mitteilungen (Rundschreiben) lesen, Informationen abbestellen.
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { portalCircularApi } from '../../api/circulars.ts'
import { errorMessage, formatDate, useLoad, useQueryLoad } from '../../components/forms.ts'
import { Alert, Checkbox, LoadError, StatusMessage } from '../../components/ui.tsx'
import { MarkupPreview } from '../../components/circulars/MarkupEditor.tsx'
import { t } from '../../i18n/index.ts'

export function PortalCirculars({ accessId }: { accessId: number }) {
  const list = useLoad(() => portalCircularApi.list(accessId), [accessId])
  const settings = useLoad(() => portalCircularApi.settings(accessId), [accessId])
  const [params, setParams] = useSearchParams()
  const raw = params.get('schreiben')
  const linked =
    raw && /^[1-9]\d*$/.test(raw) && Number.isSafeInteger(Number(raw)) ? Number(raw) : null
  const detail = useQueryLoad(
    () => portalCircularApi.get(accessId, linked!),
    [accessId, linked],
    linked !== null,
  )
  const heading = useRef<HTMLHeadingElement>(null)
  const listHeading = useRef<HTMLHeadingElement>(null)
  const opener = useRef<HTMLButtonElement | null>(null)
  const previous = useRef<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (detail.data) heading.current?.focus()
    if (linked === null && previous.current !== null)
      (opener.current ?? listHeading.current)?.focus()
    previous.current = linked
  }, [linked, detail.data])

  function show(id: number | null) {
    const next = new URLSearchParams(params)
    if (id === null) next.delete('schreiben')
    else next.set('schreiben', String(id))
    setParams(next)
  }

  async function setOptOut(value: boolean) {
    if (busy) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const confirmed = await portalCircularApi.setOptOut(accessId, value)
      settings.setData(confirmed)
      setNotice(
        confirmed.info_opt_out
          ? t('Informationen per E-Mail sind abbestellt.')
          : t('Informationen per E-Mail sind wieder aktiviert.'),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card card-wide">
      <h2 ref={listHeading} tabIndex={-1}>
        {t('Mitteilungen')}
      </h2>
      {raw !== null && (
        <section className="subcard" aria-busy={detail.loading}>
          <button type="button" className="button button-ghost" onClick={() => show(null)}>
            {t('Zur Übersicht')}
          </button>
          {linked === null && (
            <Alert kind="error">{t('Dieser Link zur Mitteilung ist ungültig.')}</Alert>
          )}
          {detail.loading && <p role="status">{t('Mitteilung wird geladen …')}</p>}
          {detail.error && (
            <LoadError
              message={t('Die Mitteilung konnte nicht geladen werden ({error}).', {
                error: detail.error,
              })}
              onRetry={() => void detail.reload()}
            />
          )}
          {detail.data && (
            <>
              <h3 ref={heading} tabIndex={-1}>
                {detail.data.subject || t('(ohne Betreff)')}
              </h3>
              <p className="muted small">
                {detail.data.sender} · {formatDate(detail.data.sent_at)}
              </p>
              <MarkupPreview text={detail.data.body ?? ''} />
              {!!detail.data.attachments?.length && (
                <section aria-label={t('Anhänge')}>
                  <h4>{t('Anhänge')}</h4>
                  <ul>
                    {detail.data.attachments.map((attachment) => (
                      <li key={attachment.id}>
                        <a href={attachment.url} target="_blank" rel="noreferrer">
                          {attachment.name}
                        </a>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}
        </section>
      )}
      {list.data && list.data.length === 0 && (
        <p className="muted">{t('Du hast noch keine Mitteilungen bekommen.')}</p>
      )}
      {list.data && list.data.length > 0 && (
        <ul className="plain-list">
          {list.data.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className="link-button"
                aria-expanded={linked === c.id}
                onClick={(event) => {
                  opener.current = event.currentTarget
                  show(linked === c.id ? null : c.id)
                }}
              >
                {c.subject}
              </button>{' '}
              <span className="muted small">
                {c.sender} · {formatDate(c.sent_at)}
                {c.channel === 'letter' && t(' · per Brief')}
                {c.channel === 'app' && t(' · per App')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {settings.data && (
        <Checkbox
          label={t('Informationen per E-Mail erhalten (offizielle Mitteilungen kommen immer)')}
          checked={!settings.data.info_opt_out}
          busy={busy}
          onChange={(on) => void setOptOut(!on)}
        />
      )}
      {error && <Alert kind="error">{error}</Alert>}
      {list.error && <LoadError message={list.error} onRetry={() => void list.reload()} />}
      {settings.error && (
        <LoadError message={settings.error} onRetry={() => void settings.reload()} />
      )}
      <StatusMessage message={notice} />
    </div>
  )
}
