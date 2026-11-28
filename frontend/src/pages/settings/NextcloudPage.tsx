// Einstellungen › Nextcloud: Anmeldung an der Nextcloud der Einheit mit dem HUBIplan-Konto.
// HUBIplan ist dabei Anmeldedienst (OpenID Connect), die Nextcloud nutzt die App „user_oidc“.
import { useState } from 'react'
import { nextcloudApi } from '../../api/nextcloud.ts'
import type { NextcloudClient } from '../../api/nextcloud.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Field, LoadError } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { ClientCard } from './ClientCard.tsx'

export function NextcloudPage() {
  const active = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => nextcloudApi.list(active.id), [active.id])
  const [secrets, setSecrets] = useState<Record<number, string>>({})
  const [name, setName] = useState('Nextcloud')
  const [url, setUrl] = useState('')
  const [createError, setCreateError] = useState<string | null>(null)

  function remember(c: NextcloudClient) {
    if (c.client_secret) setSecrets((s) => ({ ...s, [c.id]: c.client_secret ?? '' }))
  }

  async function create() {
    setCreateError(null)
    try {
      const created = await nextcloudApi.create(active.id, { name, base_url: url })
      remember(created)
      setData([...(data ?? []), created])
      setUrl('')
    } catch (e) {
      setCreateError(errorMessage(e))
    }
  }

  if (error) return <LoadError message={error} onRetry={reload} />
  if (!data) return null
  return (
    <>
      <section className="card card-wide">
        <h2>{t('Anmeldung an der Nextcloud')}</h2>
        <p>
          {t(
            'Nutzt ihr eine Nextcloud, können sich Vorstand, Rollen und auf Wunsch Mitglieder dort mit ihrem HUBIplan-Konto anmelden. Die Nextcloud bekommt Name, E-Mail-Adresse und die Gruppen; Konten legt sie bei der ersten Anmeldung selbst an. Wer bei HUBIplan keinen Zugang mehr hat, kann sich dort nicht mehr anmelden.',
          )}
        </p>
        <p className="muted small">
          {t(
            'Bereits angemeldete Sitzungen in der Nextcloud laufen weiter, bis sie ablaufen. Zum sofortigen Sperren das Konto in der Nextcloud deaktivieren oder „Konten automatisch deaktivieren“ einschalten.',
          )}
        </p>
      </section>
      {data.map((c) => (
        <ClientCard
          key={c.id}
          org={active.id}
          isClub={active.type === 'club'}
          client={c}
          secret={secrets[c.id] ?? ''}
          onChanged={(updated) => {
            remember(updated)
            setData(data.map((x) => (x.id === updated.id ? updated : x)))
          }}
          onRemoved={() => setData(data.filter((x) => x.id !== c.id))}
        />
      ))}
      <section className="card card-wide">
        <h2>{data.length ? t('Weitere Nextcloud eintragen') : t('Nextcloud eintragen')}</h2>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void create()
          }}
        >
          <Field
            label={t('Name')}
            value={name}
            maxLength={100}
            onChange={(e) => setName(e.target.value)}
          />
          <Field
            label={t('Adresse der Nextcloud')}
            type="url"
            placeholder="https://cloud.example.org"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          {createError && <Alert kind="error">{createError}</Alert>}
          <div className="button-row">
            <button type="submit" className="button button-primary">
              {t('Eintragen')}
            </button>
          </div>
        </form>
      </section>
    </>
  )
}
