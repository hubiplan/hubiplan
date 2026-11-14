// Design „Frisch“, Stufe D1 (konzepte/design-frisch.md): neue Farbtöne und Formen halten die
// Kontrastregeln der Audits (W-16, W-17, Barrierefreiheit 30.10.) für jede Vereinsfarbe.
import { describe, expect, it } from 'vitest'
import { contrastRatio } from '../theme/contrast.ts'
import {
  brandSoft,
  DARK_BG,
  DARK_SURFACE,
  linkColor,
  linkColorDark,
  PAGE_BG,
} from '../theme/theme.ts'

const CSS = import.meta.glob(['../theme/theme.css'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const THEME = CSS['../theme/theme.css']
const LIGHT = THEME.match(/:root \{([^}]*)\}/)![1]
const DARK = THEME.match(/:root\[data-theme='dark'\] \{([^}]*)\}/)![1]

function token(block: string, name: string): string {
  const m = block.match(new RegExp(`${name}:\\s*([^;]+);`))
  if (!m) throw new Error(name)
  return m[1].trim()
}

// Vereinsfarben aus den Demovereinen und Grenzfälle (sehr hell, sehr dunkel, grau, gesättigt)
const FARBEN = [
  '#0e7c66',
  '#14365d',
  '#1f4e8c',
  '#1f4e2c',
  '#a4161a',
  '#8b0000',
  '#c9a227',
  '#e8b923',
  '#ffd700',
  '#7fb3d5',
  '#000000',
  '#ffffff',
  '#7a7a7a',
  '#0000ff',
  '#6a1b9a',
  '#ff69b4',
]

describe('Design „Frisch“ D1: Farbtöne', () => {
  it.each(FARBEN)('Link-/Symbolfarbe auf getönter Fläche von %s: 4,5 : 1 (hell)', (p) => {
    expect(contrastRatio(linkColor(p), brandSoft(p))).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(linkColor(p), PAGE_BG)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(FARBEN)('Link-/Symbolfarbe auf getönter Fläche von %s: 4,5 : 1 (dunkel)', (p) => {
    const link = linkColorDark(p)
    expect(contrastRatio(link, brandSoft(p, DARK_SURFACE))).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(link, DARK_BG)).toBeGreaterThanOrEqual(4.5)
  })

  it('getönte Flächen in theme.css passen zum Anteil in theme.ts', () => {
    expect(token(LIGHT, '--color-brand-soft')).toContain('var(--color-primary) 10%')
    expect(token(DARK, '--color-brand-soft')).toContain('var(--color-primary) 22%')
  })

  it('Gold (Ehrungen) ist hell und dunkel lesbar', () => {
    expect(
      contrastRatio(token(LIGHT, '--color-gold'), token(LIGHT, '--color-gold-bg')),
    ).toBeGreaterThanOrEqual(4.5)
    expect(
      contrastRatio(token(DARK, '--color-gold'), token(DARK, '--color-gold-bg')),
    ).toBeGreaterThanOrEqual(4.5)
  })
})

describe('Design „Frisch“ D1: Formen und Schrift', () => {
  it('sachliche Rundung (Ralf 14.11.: kein Apple-Look)', () => {
    expect(token(LIGHT, '--radius')).toBe('0.375rem')
    expect(token(LIGHT, '--radius-lg')).toBe('0.5rem')
  })

  it('Inter zuerst, Systemschriften als Rückfall', () => {
    expect(token(LIGHT, '--font-family')).toMatch(/^'Inter', system-ui/)
    expect(THEME).toMatch(/font-family: 'Inter';[^}]*font-display: swap/)
  })
})
