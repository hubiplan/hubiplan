import { useState } from 'react'
import { PERM } from '../../api/orgs.ts'
import { portalApi } from '../../api/portal.ts'
import { OutboxBrowser } from '../../components/OutboxList.tsx'
import { errorMessage, useLoad } from '../../components/forms.ts'
import { Alert, Checkbox } from '../../components/ui.tsx'
import { useActiveOrg, useOrg } from '../../org/OrgContext.tsx'
import { t } from '../../i18n/index.ts'

/** Freigabe der Inhalte für die Plattform-Betreuung (Gesamtaudit 05.11. F-04). */
function PlatformContentSetting({ orgId, editable }: { orgId: number; editable: boolean }) {
  const settings = useLoad(() => portalApi.outboxSettings(orgId), [orgId])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!settings.data) return null
  const save = async (value: boolean) => {
    setBusy(true)
    setError(null)
    try {
      settings.setData(await portalApi.saveOutboxSettings(orgId, value))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <Checkbox
        label={t('Plattform-Betreuung darf Text und Anhänge sehen')}
        hint={t('Sonst sieht sie nur Empfänger, Betreff und Status, etwa zur Fehlersuche.')}
        checked={settings.data.platform_content}
        onChange={(value) => void save(value)}
        disabled={!editable}
        busy={busy}
      />
      {error && <Alert kind="error">{error}</Alert>}
    </>
  )
}

export function OutboxPage() {
  const org = useActiveOrg()
  const { can } = useOrg()
  return (
    <div className="card card-wide">
      <h2>{t('Postausgang')}</h2>
      <p className="muted small">
        {t('Alle Mails, die die Software im Namen von {name} versendet hat.', { name: org.name })}
      </p>
      <PlatformContentSetting orgId={org.id} editable={can(PERM.orgEdit)} />
      <OutboxBrowser
        load={(query) => portalApi.outbox(org.id, query)}
        deps={[org.id]}
        attachmentUrl={(mail, index) => portalApi.outboxAttachmentUrl(org.id, mail, index)}
      />
    </div>
  )
}
