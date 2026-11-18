// UX-Audit 16.11.2026, Verwaltung (Rest): VW-32, VW-41, VW-45, VW-47, X-12
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { bottomNavIds } from '../modules.tsx'
import { contrastRatio } from '../theme/contrast.ts'
import { blend, SIDEBAR_TEXT, sidebarColor, sidebarColorDark, themeVars } from '../theme/theme.ts'

const css = readFileSync('src/index.css', 'utf8')

describe('VW-32: untere Leiste nach Rolle', () => {
  const all = [
    'start',
    'mein-bereich',
    'termine',
    'versammlungen',
    'mitglieder',
    'finanzen',
    'einstellungen',
  ]

  it('Kasse bekommt Finanzen, Schriftführung Versammlungen', () => {
    expect(bottomNavIds(all, ['finance'])).toEqual(['start', 'finanzen', 'termine'])
    expect(bottomNavIds(all, ['minutes'])).toEqual(['start', 'versammlungen', 'termine'])
    expect(bottomNavIds(all, [])).toEqual(['start', 'termine', 'mitglieder'])
  })

  it('füllt immer drei Bereiche, auch ohne Termine und Mitglieder', () => {
    expect(bottomNavIds(['start', 'finanzen', 'aufgaben', 'einstellungen'], undefined)).toEqual([
      'start',
      'finanzen',
      'aufgaben',
    ])
    // Einstellungen nie in der Leiste
    expect(bottomNavIds(['start', 'einstellungen'], undefined)).toEqual(['start'])
  })
})

describe('VW-47: Seitenleiste im dunklen Modus abgedunkelt', () => {
  it.each(['#b40808', '#0a5a4a', '#ffd700', '#14365d'])('%s', (primary) => {
    const dark = themeVars(
      { primary, on_primary: '#fff', accent: '#000', on_accent: '#fff' },
      'dark',
    )
    const bg = dark['--sidebar-bg']
    expect(bg).toBe(sidebarColorDark(primary))
    expect(bg).not.toBe(sidebarColor(primary))
    expect(contrastRatio(SIDEBAR_TEXT, bg)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(SIDEBAR_TEXT, blend('#ffffff', bg, 0.12))).toBeGreaterThanOrEqual(4.5)
  })

  it('hell bleibt die kräftige Vereinsfarbe', () => {
    const light = themeVars({
      primary: '#b40808',
      on_primary: '#fff',
      accent: '#000',
      on_accent: '#fff',
    })
    expect(light['--sidebar-bg']).toBe(sidebarColor('#b40808'))
  })
})

describe('VW-41 und VW-45: Startseitenlisten', () => {
  it('heutiger Geburtstag in Textfarbe statt Vereinsfarbe auf getönter Fläche', () => {
    expect(css).toMatch(
      /li\.tile-entry-today \.tile-entry-title,[^{]*\{\s*color: var\(--color-text\)/,
    )
  })

  it('Name der Einheit bricht um statt mit Auslassung zu enden', () => {
    const rule = css.slice(css.indexOf('.tile-entry-meta > .tile-entry-org {'))
    const body = rule.slice(0, rule.indexOf('}'))
    expect(body).toContain('white-space: normal')
    expect(body).not.toContain('text-overflow: ellipsis')
  })
})

describe('X-12: öffentlich heißt nicht „für alle Mitglieder“', () => {
  it('Hinweis am Feld nennt Webseite und Mitglieder getrennt', () => {
    const form = readFileSync('src/components/calendar/EventForm.tsx', 'utf8')
    expect(form).toContain('Auf der Webseite und ohne Anmeldung zu sehen. In HUBIplan sehen ihn')
  })
})
