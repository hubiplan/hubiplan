// Hilfe › Neuigkeiten (/hilfe/neuigkeiten): Überblick nach Monaten, darunter die Änderungen je
// Version aus CHANGELOG.md bzw. CHANGELOG.en.md (konzepte/hilfe-neustruktur.md, HN2).
import { useEffect, useState } from 'react'
import { HelpMarkdown } from '../help/HelpMarkdown.tsx'
import { OPEN_MONTHS, loadNews } from '../help/news.ts'
import type { MonthlyNews } from '../help/news.ts'
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
  const [news, setNews] = useState<MonthlyNews | null>(null)
  useEffect(() => {
    let alive = true
    loadChangelog().then((b) => alive && setBody(b))
    loadNews(lang()).then(
      (n) => alive && setNews(n),
      () => undefined,
    )
    return () => {
      alive = false
    }
  }, [])
  // Wer die Seite gesehen hat, braucht den Hinweis „Das ist neu“ nicht mehr
  useEffect(() => {
    if (version && RELEASE_PATTERN.test(version)) markSeen(version)
  }, [version])
  return (
    <div className="news-page">
      <section aria-labelledby="neu-monate">
        <h2 id="neu-monate">{t('Was ist neu')}</h2>
        {news && (
          <>
            <HelpMarkdown body={news.intro} />
            {news.months.map((m, i) => (
              <details key={m.title} className="news-month" open={i < OPEN_MONTHS}>
                <summary>
                  <h3>{m.title}</h3>
                </summary>
                <HelpMarkdown body={m.body} />
              </details>
            ))}
          </>
        )}
      </section>
      <section aria-labelledby="neu-versionen">
        <h2 id="neu-versionen">{t('Änderungen je Version')}</h2>
        <p className="muted">
          {version
            ? t('Laufende Version: {x}. Die neueste Version steht oben.', { x: version })
            : t('Die neueste Version steht oben.')}
        </p>
        {body === undefined && (
          <p className="muted" role="status">
            {t('Wird geladen …')}
          </p>
        )}
        {body === null && (
          <p role="status">{t('Die Änderungshinweise liegen dieser Fassung nicht bei.')}</p>
        )}
        {body && <HelpMarkdown body={body} />}
      </section>
    </div>
  )
}
