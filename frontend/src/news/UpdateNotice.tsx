// Einmaliger Hinweis für Verwalter nach dem Update auf ein neues Release (konzepte/releases.md, E6).
// Zwischenstände („2026.11.0+3.0a5d21e“) lösen ihn nicht aus.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { t } from '../i18n/index.ts'
import { markSeen, seenVersion } from './changelog.ts'
import { RELEASE_PATTERN, useRunningVersion } from './version.ts'

export function UpdateNotice() {
  const version = useRunningVersion()
  const [closed, setClosed] = useState<string | null>(null)
  if (!version || !RELEASE_PATTERN.test(version)) return null
  if (closed === version || seenVersion() === version) return null
  const close = () => {
    markSeen(version)
    setClosed(version)
  }
  return (
    <div className="alert alert-info update-notice" role="status">
      {t('HUBIplan wurde auf Version {x} aktualisiert.', { x: version })}{' '}
      <Link to="/hilfe/neuigkeiten" onClick={close}>
        {t('Das ist neu')}
      </Link>{' '}
      <button type="button" className="link-button" onClick={close}>
        {t('Ausblenden')}
      </button>
    </div>
  )
}
