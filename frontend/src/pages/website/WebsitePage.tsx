// Webseite der Einheit: einrichten, dann Unterpunkte (Seitenleiste) Übersicht (Prüfliste, Zustand, Vorschau),
// Inhalte, Gestaltung (Design), Aufbau (Bausteine, Personen, Untereinheiten), Domain und Kontakt. Die Datenschutzhinweise
// der Webseite stehen unter Einstellungen › Datenschutz (WebsitePrivacy.tsx).
// Die Seite selbst zeigt das Projekt „hubiplan-website“.
import { useState } from 'react'
import { websiteApi } from '../../api/website.ts'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, LoadError, Loading } from '../../components/ui.tsx'
import { useActiveOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'
import { PageHeader } from '../../components/PageHeader.tsx'
import { WebsiteAdmin } from './WebsiteAdmin.tsx'

export function WebsitePage() {
  const org = useActiveOrg()
  const { data, error, reload, setData } = useLoad(() => websiteApi.get(org.id), [org.id])
  // Zählt hoch, wenn der Entwurf von außen wechselt: die Eingaben starten dann neu
  const [generation, setGeneration] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  // Der Kopf steht auch beim Laden und bei Fehlern (Seitenkopf S-05)
  if (error)
    return (
      <section>
        <PageHeader />
        <LoadError message={error} onRetry={() => void reload()} />
      </section>
    )
  if (!data)
    return (
      <section>
        <PageHeader />
        <Loading />
      </section>
    )

  async function setup() {
    setBusy(true)
    setMessage(null)
    try {
      setData(await websiteApi.setup(org.id))
    } catch (err) {
      setMessage(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <PageHeader />
      {!data.module_enabled && (
        <Alert kind="info">
          {t(
            'Das Modul „Webseite“ ist für {name} nicht freigeschaltet. Die Plattform schaltet es für Einheiten frei, die eine eigene Webseite bekommen sollen.',
            { name: org.name },
          )}
        </Alert>
      )}
      {data.module_enabled && !data.website && (
        <div className="card card-wide">
          <h2>{t('Webseite einrichten')}</h2>
          <p>
            {t(
              'HUBIplan stellt Vorstand, Untereinheiten, Termine mit Kalender-Abo, Social-Media-Links und ein Kontaktformular für eine öffentliche Webseite bereit. Personendaten erscheinen nur nach den Regeln zu Einwilligung und Widerspruch.',
            )}
          </p>
          <p className="muted small">
            {t(
              'Eine neue Webseite startet im Wartungsmodus: Besucher sehen nur einen Hinweis, du selbst kannst sie in der Vorschau ansehen.',
            )}
          </p>
          {message && <Alert kind="error">{message}</Alert>}
          {data.can_manage && (
            <button type="button" className="button" disabled={busy} onClick={() => void setup()}>
              {t('Webseite einrichten')}
            </button>
          )}
        </div>
      )}
      {data.website && (
        <WebsiteAdmin
          key={`${data.website.public_key}:${generation}`}
          data={data}
          website={data.website}
          onChange={setData}
          onReset={(next) => {
            setData(next)
            setGeneration((g) => g + 1)
          }}
          reload={() => void reload()}
        />
      )}
    </section>
  )
}
