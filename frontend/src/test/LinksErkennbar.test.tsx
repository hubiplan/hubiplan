// Links ohne Unterstreichung sicher erkennbar (UX-Audit 08.11., W-16, Bausteine B1–B3).
// B4, die axe-Regel link-in-text-block im echten Browser, läuft im Rundgang von
// scripts/hilfe-bilder.mjs.
import { describe, expect, it } from 'vitest'
import { contrastRatio } from '../theme/contrast.ts'
import { linkColor, PAGE_BG, TEXT_COLOR, themeVars } from '../theme/theme.ts'

const CSS = import.meta.glob(['../index.css', '../theme/theme.css'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function token(name: string): string {
  const m = CSS['../theme/theme.css'].match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))
  if (!m) throw new Error(name)
  return m[1]
}

// Erfundene Vereinsfarben von sehr dunkel bis sehr hell, dazu reine Grundfarben
const FARBEN = [
  '#14365d', // Dunkelblau (Demoverein)
  '#1f4e2c', // Dunkelgrün (Testdaten)
  '#1f4e79',
  '#123e7a',
  '#0e7c66', // Hubi-Grün
  '#8b0000',
  '#b3261e',
  '#6a1b9a',
  '#2e7d32',
  '#c9a227', // Gold
  '#ffd700', // Gelb
  '#e0a526',
  '#7fb3d5', // Hellblau
  '#909090',
  '#ff0000',
  '#00ff00',
  '#0000ff',
  '#000000',
  '#ffffff',
  PAGE_BG,
]

describe('W-16 B1 Linkfarbe', () => {
  it.each(FARBEN)('%s: 4,5 : 1 zum Grund und 3 : 1 zum Fließtext', (primary) => {
    const link = linkColor(primary)
    expect(contrastRatio(link, '#ffffff')).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(link, PAGE_BG)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(link, TEXT_COLOR)).toBeGreaterThanOrEqual(3)
  })

  it('bleibt ein Ton der Vereinsfarbe und ändert so wenig wie nötig', () => {
    // Dunkelblau wird etwas heller (Konzept links-erkennbar.md), Gelb olivbraun
    expect(linkColor('#14365d')).toBe('#4c6684')
    expect(linkColor('#ffd700')).toBe('#806c00')
    // Eine Farbe, die beide Ziele schon erreicht, bleibt unverändert
    expect(linkColor('#0d7661')).toBe('#0d7661')
  })

  it('setzt Link- und Fokusfarbe des Vereins aus derselben Rechnung', () => {
    const vars = themeVars({
      primary: '#14365d',
      on_primary: '#ffffff',
      accent: '#f2b33d',
      on_accent: '#1d2421',
    })
    expect(vars['--color-link']).toBe(linkColor('#14365d'))
    expect(vars['--color-focus']).toBe(linkColor('#14365d'))
  })
})

describe('W-16 B2 Fließtext', () => {
  it('Token und Rechnung nutzen denselben dunkleren Fließtext', () => {
    expect(token('--color-text')).toBe(TEXT_COLOR)
    expect(TEXT_COLOR).toBe('#121614')
    expect(contrastRatio(TEXT_COLOR, '#ffffff')).toBeGreaterThanOrEqual(18)
  })

  it('der Standard-Linkton hebt sich mit 3 : 1 vom Fließtext ab', () => {
    expect(contrastRatio(token('--color-link'), TEXT_COLOR)).toBeGreaterThanOrEqual(3)
    expect(contrastRatio(token('--color-link'), PAGE_BG)).toBeGreaterThanOrEqual(4.5)
  })
})

describe('W-16 B3 Zusatzmerkmal in fetter Umgebung', () => {
  const css = CSS['../index.css']

  it('Links in Überschriften, strong und Tabellenköpfen bekommen ein „ ›“', () => {
    const rule = css.match(/:where\(strong, b, h1[^{]*\)::after \{[^}]*\}/)
    expect(rule).not.toBeNull()
    expect(rule![0]).toContain('th')
    expect(rule![0]).toContain('\\203a')
  })

  it('Bildschirmleser lesen das Zeichen nicht vor', () => {
    const rule = css.match(/:where\(strong, b, h1[^{]*\)::after \{[^}]*\}/)![0]
    expect(rule).toMatch(/content: '[^']*' \/ '';/)
  })

  it('Links bleiben ohne Unterstreichung (Projektregel)', () => {
    for (const m of css.matchAll(/text-decoration(?:-line)?:\s*underline/g)) {
      // Unterstreichung nur außerhalb von Links (z. B. Rechtschreibhinweise) erlaubt
      const before = css.slice(Math.max(0, m.index - 300), m.index)
      expect(before.slice(before.lastIndexOf('}') + 1)).not.toMatch(/(^|[\s,(])a[\s:.,[{)]/)
    }
  })
})
