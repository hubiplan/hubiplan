// Knopf „In der HUBIplan-App öffnen“: verbindet die App auf demselben Telefon, auf dem der
// QR-Code steht (UX-Audit 08.11., X-04). Er trägt denselben Einmalcode wie der QR-Code.
import { t } from '../i18n/index.ts'
import { APP_STORE_URL, appPairLink } from './appLink.ts'

export function AppOpenLink({ pairUrl }: { pairUrl: string }) {
  const href = appPairLink(pairUrl)
  if (!href) return null
  return (
    <div className="app-open stack">
      <a className="button button-primary" href={href}>
        {t('In der HUBIplan-App öffnen')}
      </a>
      <p className="muted small">
        {t('Passiert beim Tippen nichts, ist die App noch nicht installiert:')}{' '}
        <a href={APP_STORE_URL} target="_blank" rel="noopener noreferrer">
          {t('HUBIplan bei Google Play')}
        </a>
      </p>
    </div>
  )
}
