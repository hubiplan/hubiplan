import { Link } from 'react-router-dom'
import { t } from '../i18n/index.ts'
import { isWhiteLabel, usePlatform } from '../theme/platform.ts'

/**
 * Herkunftshinweis „mit HUBIplan“ bei eigenem Instanznamen (White Label, Fachfrage F-3):
 * fest auf der Anmeldeseite, führt zur Lizenzseite mit dem Quellcode (AGPL § 13).
 * Heißt die Instanz „HUBIplan“, steht der Name ohnehin schon da.
 */
export function PoweredBy() {
  const instance = usePlatform()
  if (!isWhiteLabel(instance)) return null
  return (
    <p className="small powered-by">
      <Link to="/lizenz">{t('mit HUBIplan')}</Link>
    </p>
  )
}
