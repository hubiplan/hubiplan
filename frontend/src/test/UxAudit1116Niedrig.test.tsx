// UX-Audit 16.11.2026, niedrige Befunde der Verwaltung:
// VW-28 Das Hauptmenü sagt seine Gruppen an. VW-30 Auffangmeldungen nennen die richtige
// Ursache. VW-42 Zielgrößen von mindestens 24 px. VW-44 Die Kachel „Nächste Termine“ nennt
// die Einheit, wenn Termine mehrerer Einheiten erscheinen.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { ApiError, statusMessage } from '../api/client.ts'
import { errorMessage } from '../components/forms.ts'

describe('VW-30 Auffangmeldungen', () => {
  it('nennt bei einem Programmfehler nicht den Server als Ursache', () => {
    expect(errorMessage(new RangeError('kaputt'))).toMatch(/Fehlers im Programm/)
    expect(errorMessage(new TypeError('Failed to fetch'))).toBe('Der Server ist nicht erreichbar.')
    expect(errorMessage(new ApiError(400, { detail: 'Bitte einen Namen angeben.' }))).toBe(
      'Bitte einen Namen angeben.',
    )
  })

  it('sagt bei 404 und unbekannten Fehlern, was zu tun ist', () => {
    expect(statusMessage(404)).toMatch(/gelöscht, oder die Adresse stimmt nicht/)
    expect(statusMessage(418)).toMatch(/versuche es noch einmal/)
  })
})

describe('VW-28 und VW-42 im Quelltext', () => {
  it('gibt jeder Menügruppe eine Überschrift mit eigener Liste', () => {
    const layout = readFileSync('src/components/Layout.tsx', 'utf8')
    expect(layout).toMatch(/<h2 className="sidebar-group-label" id=\{`menue-gruppe-/)
    expect(layout).toMatch(/<ul aria-labelledby=\{`menue-gruppe-/)
    expect(layout).toContain("aria-label={t('Hauptmenü')}")
  })

  it('macht Fußzeilenlinks und Lernhaken mindestens 24 px groß', () => {
    const css = readFileSync('src/index.css', 'utf8')
    const footer = css.slice(css.indexOf('.site-footer a {'))
    expect(footer.slice(0, footer.indexOf('}'))).toContain('min-height: 1.5rem')
    const help = readFileSync('src/help/help.css', 'utf8')
    const box = help.slice(help.indexOf(".help-steps input[type='checkbox'] {"))
    expect(box.slice(0, box.indexOf('}'))).toContain('width: 1.5rem')
  })

  it('nennt in der Terminkachel die Einheit, sobald mehrere vorkommen', () => {
    const tile = readFileSync('src/components/calendar/UpcomingTile.tsx', 'utf8')
    expect(tile).toContain('new Set(items.map((o) => o.owner)).size > 1')
    expect(tile).toMatch(/showOwner && o\.owner && \(/)
  })
})
