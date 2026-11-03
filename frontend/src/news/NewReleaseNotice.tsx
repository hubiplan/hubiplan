// Hinweis für Plattformverwalter: Es gibt ein neueres Release (konzepte/releases.md, E9).
// Der Server fragt dafür einmal am Tag den Releases-Feed auf GitHub ab (core/update_check.py).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { platformApi } from '../api/orgs.ts'
import type { PlatformUpdate } from '../api/orgs.ts'
import { t } from '../i18n/index.ts'

const HIDDEN_KEY = 'hubiplan.release-hinweis.ausgeblendet'

function hiddenVersion(): string | null {
  try {
    return localStorage.getItem(HIDDEN_KEY)
  } catch {
    return null
  }
}

export function NewReleaseNotice() {
  const [update, setUpdate] = useState<PlatformUpdate['update']>(null)
  const [hidden, setHidden] = useState(hiddenVersion)
  useEffect(() => {
    let alive = true
    platformApi
      .newRelease()
      .then((d) => alive && setUpdate(d.update))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [])
  if (!update || hidden === update.version) return null
  const hide = () => {
    try {
      localStorage.setItem(HIDDEN_KEY, update.version)
    } catch {
      // Ohne Speicher erscheint der Hinweis beim nächsten Laden wieder
    }
    setHidden(update.version)
  }
  return (
    <div className="alert alert-info update-notice" role="status">
      {t('Es gibt eine neuere Version von HUBIplan: {x} (hier läuft {y}).', {
        x: update.version,
        y: update.running,
      })}{' '}
      <Link to="/plattform/version">{t('Zur Versionsseite')}</Link>{' '}
      {update.url && (
        <>
          <a href={update.url} target="_blank" rel="noreferrer noopener">
            {t('Änderungen ansehen')}
          </a>{' '}
        </>
      )}
      <button type="button" className="link-button" onClick={hide}>
        {t('Ausblenden')}
      </button>
    </div>
  )
}
