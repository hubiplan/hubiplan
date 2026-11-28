import { useState } from 'react'
import { websiteApi } from '../../api/website.ts'
import type { PreviewLink, Website, WebsiteData } from '../../api/website.ts'
import { errorMessage, formatDateTime } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

export function PreviewCard({
  data,
  website,
  onChange,
}: {
  data: WebsiteData
  website: Website
  onChange: () => void
}) {
  const org = useActiveOrg()
  const [label, setLabel] = useState('')
  const [days, setDays] = useState(7)
  const [created, setCreated] = useState<PreviewLink | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Nach dem Warten blockt mancher Browser das neue Fenster: dann hilft der Link
  const [opened, setOpened] = useState<string | null>(null)

  async function open() {
    setError(null)
    setOpened(null)
    try {
      const result = await websiteApi.openPreview(org.id)
      if (result.url) {
        window.open(result.url, '_blank', 'noopener')
        setOpened(result.url)
      } else setError(t('Für die Vorschau fehlt noch eine Domain.'))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function create() {
    setError(null)
    try {
      setCreated(await websiteApi.addPreviewLink(org.id, label, days))
      setLabel('')
      onChange()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  async function revoke(link: PreviewLink) {
    setError(null)
    try {
      await websiteApi.revokePreviewLink(org.id, link.id)
      onChange()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Vorschau')}</h2>
      <p className="muted small">
        {t(
          'In der Vorschau siehst du die vollständige Webseite, auch im Wartungsmodus, mit dem Hinweis „Vorschau – nicht öffentlich“.',
        )}
      </p>
      {error && <Alert kind="error">{error}</Alert>}
      <button type="button" className="button" onClick={() => void open()}>
        {t('Vorschau öffnen')}
      </button>
      {opened && (
        <p className="muted small">
          {t('Kein neues Fenster?')}{' '}
          <a href={opened} target="_blank" rel="noopener noreferrer">
            {t('Vorschau hier öffnen')}
          </a>
          .
        </p>
      )}
      {data.can_manage && (
        <>
          <h3>{t('Vorschau-Links zum Weitergeben')}</h3>
          <p className="muted small">
            {t(
              'Zum Beispiel für Vorstandsmitglieder ohne Zugang zu HUBIplan. Jeder Link gilt höchstens 14 Tage und lässt sich jederzeit widerrufen.',
            )}
          </p>
          {created?.url && (
            <Alert kind="success">
              {t('Neuer Link (wird nur jetzt angezeigt):')} <code>{created.url}</code>
            </Alert>
          )}
          {created && !created.url && (
            <Alert kind="info">
              {t('Link angelegt. Für eine Adresse fehlt noch eine Domain; Schlüssel:')}{' '}
              <code>{created.token}</code>
            </Alert>
          )}
          <ul className="plain-list">
            {website.preview_links.map((link) => (
              <li key={link.id}>
                {link.label || t('Vorschau-Link')} {t('· gültig bis')}{' '}
                {formatDateTime(link.expires_at)}
                {!link.is_active ? t(' (abgelaufen)') : ''}{' '}
                <button
                  type="button"
                  className="button button-ghost"
                  onClick={() => void revoke(link)}
                >
                  {t('Widerrufen')}
                </button>
              </li>
            ))}
          </ul>
          <div className="grid-2">
            <Field
              label={t('Bezeichnung (z. B. für wen)')}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <Field
              label={t('Gültig (Tage)')}
              type="number"
              min={1}
              max={14}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
            />
          </div>
          <button type="button" className="button" onClick={() => void create()}>
            {t('Vorschau-Link erzeugen')}
          </button>
        </>
      )}
    </div>
  )
}
