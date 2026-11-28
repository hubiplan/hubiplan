import { portalApi } from '../../api/portal.ts'
import { OutboxBrowser } from '../../components/OutboxList.tsx'
import { t } from '../../i18n/index.ts'

/** Test-Postfach: alle Mails, die die Plattform verschickt hat. */
export function PlatformMailPage() {
  return (
    <div className="card card-wide">
      <h2>{t('Postfach')}</h2>
      <p className="muted small">
        {t(
          'Alle Mails der Plattform. Solange kein Mailserver hinterlegt ist, werden Mails nur hier gesammelt und nicht zugestellt.',
        )}
      </p>
      <OutboxBrowser
        load={portalApi.platformOutbox}
        deps={[]}
        attachmentUrl={portalApi.platformAttachmentUrl}
        showOrg
      />
    </div>
  )
}
