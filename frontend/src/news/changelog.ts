// Änderungshinweise (CHANGELOG.md, CHANGELOG.en.md) der laufenden Fassung. deploy/web.Dockerfile
// legt beide Dateien unter /lizenzen/ ab; die Seite „Neuigkeiten“ zeigt sie in der Sprache
// der Oberfläche (konzepte/releases.md, docs/releases.md).
import type { Lang } from '../i18n/index.ts'

export const CHANGELOG_FILES: Record<Lang, string> = {
  de: '/lizenzen/CHANGELOG.md',
  en: '/lizenzen/CHANGELOG.en.md',
}

/** Marke, unter der scripts/release.sh neue Versionen einfügt; darüber steht nur die Einleitung. */
const MARKER = '<!-- Neue Versionen hier einfügen (scripts/release.sh) -->'

/**
 * Versionen aus dem Changelog, ohne Titel und Einleitung. null, wenn der Text kein Changelog ist
 * (der Webserver liefert für fehlende Dateien die App-Seite aus).
 */
export function changelogBody(raw: string): string | null {
  const text = raw.replace(/\r\n/g, '\n')
  if (!text.startsWith('# ')) return null
  const at = text.indexOf(MARKER)
  const body = at >= 0 ? text.slice(at + MARKER.length) : text.replace(/^# .*\n/, '')
  return body.trim()
}

/** Merkt sich je Browser, zu welcher Version der Hinweis „Das ist neu“ schon gesehen wurde. */
const SEEN_KEY = 'hubiplan.neuigkeiten.gesehen'

export function seenVersion(): string | null {
  try {
    return localStorage.getItem(SEEN_KEY)
  } catch {
    return null
  }
}

export function markSeen(version: string) {
  try {
    localStorage.setItem(SEEN_KEY, version)
  } catch {
    // Ohne Speicher erscheint der Hinweis eben beim nächsten Laden wieder
  }
}
