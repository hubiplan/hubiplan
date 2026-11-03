// /hilfe/neuigkeiten: Änderungen je Version aus CHANGELOG.md bzw. CHANGELOG.en.md.
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { HelpMarkdown } from '../help/HelpMarkdown.tsx'
import { lang, t } from '../i18n/index.ts'
import { CHANGELOG_FILES, changelogBody, markSeen } from './changelog.ts'
import { RELEASE_PATTERN, useRunningVersion } from './version.ts'

async function loadChangelog(): Promise<string | null> {
  // Englisch fehlt (ältere Fassung)? Dann Deutsch statt gar nichts
  const files = [...new Set([CHANGELOG_FILES[lang()], CHANGELOG_FILES.de])]
  for (const file of files) {
    try {
      const resp = await fetch(file)
      const body = resp.ok ? changelogBody(await resp.text()) : null
      if (body) return body
    } catch {
      // nächste Datei versuchen
    }
  }
  return null
}

export function NewsPage() {
  const version = useRunningVersion()
  const [body, setBody] = useState<string | null | undefined>(undefined)
  useEffect(() => {
    let alive = true
    loadChangelog().then((b) => alive && setBody(b))
    return () => {
      alive = false
    }
  }, [])
  // Wer die Seite gesehen hat, braucht den Hinweis „Das ist neu“ nicht mehr
  useEffect(() => {
    if (version && RELEASE_PATTERN.test(version)) markSeen(version)
  }, [version])
  return (
    <section className="help-page news-page">
      <h1>{t('Neuigkeiten')}</h1>
      <p className="muted">
        {version
          ? t('Laufende Version: {x}. Die neueste Version steht oben.', { x: version })
          : t('Die neueste Version steht oben.')}{' '}
        <Link to="/hilfe/was-ist-neu">{t('Überblick nach Monaten')}</Link>
      </p>
      {body === undefined && (
        <p className="muted" role="status">
          {t('Lädt …')}
        </p>
      )}
      {body === null && (
        <p role="status">{t('Die Änderungshinweise liegen dieser Fassung nicht bei.')}</p>
      )}
      {body && <HelpMarkdown body={body} />}
    </section>
  )
}
