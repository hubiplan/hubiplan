import { useState } from 'react'
import { websiteApi } from '../../api/website.ts'
import type { Website, WebsiteData } from '../../api/website.ts'
import { errorMessage } from '../../components/forms.ts'
import { Alert, Field } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

/** Bausteine der Startseite: ein/aus und Reihenfolge per Ziehen (Ralf 10.11., wie das Menü). */
export function DomainsCard({
  data,
  website,
  onChange,
}: {
  data: WebsiteData
  website: Website
  onChange: () => void
}) {
  const org = useActiveOrg()
  const [host, setHost] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      onChange()
      return true
    } catch (err) {
      setError(errorMessage(err))
      return false
    }
  }

  return (
    <div className="card card-wide">
      <h2>{t('Domains')}</h2>
      <p className="muted small">
        {t(
          'Unter diesen Adressen erkennt die Webseite {name}. Die Domain muss beim Anbieter auf den Server der Webseite zeigen.',
          { name: org.name },
        )}
      </p>
      {website.domains.length === 0 && (
        <p className="muted">{t('Noch keine Domain eingetragen.')}</p>
      )}
      <ul className="plain-list">
        {website.domains.map((d) => (
          <li key={d.id}>
            <strong>{d.hostname}</strong>
            {d.is_primary ? t(' (Hauptadresse)') : ''}
            {data.can_manage && (
              <span className="button-row">
                {!d.is_primary && (
                  <button
                    type="button"
                    className="button button-ghost"
                    onClick={() => void run(() => websiteApi.makePrimary(org.id, d.id))}
                  >
                    {t('Als Hauptadresse')}
                  </button>
                )}
                <button
                  type="button"
                  className="button button-ghost"
                  aria-label={t('{hostname} entfernen', { hostname: d.hostname })}
                  onClick={() => void run(() => websiteApi.removeDomain(org.id, d.id))}
                >
                  {t('Entfernen')}
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <Alert kind="error">{error}</Alert>}
      {data.can_manage && (
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault()
            void run(() => websiteApi.addDomain(org.id, host)).then((ok) => ok && setHost(''))
          }}
        >
          <Field
            label={t('Domain hinzufügen')}
            placeholder="www.beispiel-verein.de"
            value={host}
            onChange={(e) => setHost(e.target.value)}
          />
          <button type="submit" className="button" disabled={!host.trim()}>
            {t('Hinzufügen')}
          </button>
        </form>
      )}
    </div>
  )
}
