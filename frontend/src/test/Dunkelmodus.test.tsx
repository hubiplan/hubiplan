// Dunkelmodus der Web-App, Stufe D1 (konzepte/dunkelmodus-web.md, UX-Audit 08.11. X-02).
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { contrastRatio } from '../theme/contrast.ts'
import {
  darkAllowed,
  resolveScheme,
  setColorSchemeChoice,
  setColorSchemePath,
} from '../theme/colorScheme.ts'
import {
  applyTheme,
  buttonColorsDark,
  DARK_BG,
  DARK_SURFACE,
  linkColorDark,
  themeVars,
} from '../theme/theme.ts'
import { AppearanceCard } from '../pages/settings/AppearanceCard.tsx'
import { fakeApi } from './fakeApi.ts'

const CSS = import.meta.glob(['../**/*.css'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const DARK = CSS['../theme/theme.css'].match(/:root\[data-theme='dark'\] \{([^}]*)\}/)![1]

function darkToken(name: string): string {
  const m = DARK.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))
  if (!m) throw new Error(name)
  return m[1]
}

const FARBEN = ['#14365d', '#1f4e2c', '#0e7c66', '#8b0000', '#c9a227', '#ffd700', '#7fb3d5']
const ALLE = [...FARBEN, '#000000', '#ffffff', '#0000ff', '#6a1b9a']

afterEach(() => {
  setColorSchemeChoice('auto')
  setColorSchemePath('/')
  applyTheme(null)
})

describe('X-02 Umfang D1', () => {
  it.each(['/', '/anmelden', '/termine', '/termine/5', '/mein-konto/app', '/mein-bereich'])(
    '%s darf dunkel sein',
    (path) => expect(darkAllowed(path)).toBe(true),
  )

  it.each(['/finanzen', '/mitglieder', '/einstellungen/organisation', '/terminplan'])(
    '%s bleibt hell',
    (path) => expect(darkAllowed(path)).toBe(false),
  )

  it('folgt dem Gerät, außer das Konto wählt hell oder dunkel', () => {
    expect(resolveScheme('auto', '/termine', true)).toBe('dark')
    expect(resolveScheme('auto', '/termine', false)).toBe('light')
    expect(resolveScheme('light', '/termine', true)).toBe('light')
    expect(resolveScheme('dark', '/termine', false)).toBe('dark')
    expect(resolveScheme('dark', '/finanzen', true)).toBe('light')
  })

  it('setzt data-theme nur auf den Seiten für Mitglieder', () => {
    setColorSchemeChoice('dark')
    setColorSchemePath('/termine')
    expect(document.documentElement.dataset.theme).toBe('dark')
    setColorSchemePath('/finanzen')
    expect(document.documentElement.dataset.theme).toBeUndefined()
  })
})

describe('X-02 Farben gegen dunklen Grund', () => {
  it('dunkle Tokens: Text, gedämpfter Text, Feldrahmen und Karten lesbar', () => {
    expect(darkToken('--color-bg')).toBe(DARK_BG)
    expect(darkToken('--color-surface')).toBe(DARK_SURFACE)
    for (const bg of [DARK_BG, DARK_SURFACE]) {
      expect(contrastRatio(darkToken('--color-text'), bg)).toBeGreaterThanOrEqual(7)
      expect(contrastRatio(darkToken('--color-text-muted'), bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(darkToken('--color-link'), bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(darkToken('--color-error'), bg)).toBeGreaterThanOrEqual(4.5)
      expect(contrastRatio(darkToken('--color-success'), bg)).toBeGreaterThanOrEqual(4.5)
    }
    expect(contrastRatio(darkToken('--color-input-border'), DARK_SURFACE)).toBeGreaterThanOrEqual(3)
    expect(contrastRatio(darkToken('--color-card-border'), DARK_BG)).toBeGreaterThanOrEqual(1.5)
    expect(darkToken('--color-link')).toBe(linkColorDark('#0e7c66'))
  })

  it.each(ALLE)('%s: Links 4,5 : 1 auf Grund und Karte', (primary) => {
    const link = linkColorDark(primary)
    expect(contrastRatio(link, DARK_BG)).toBeGreaterThanOrEqual(4.5)
    expect(contrastRatio(link, DARK_SURFACE)).toBeGreaterThanOrEqual(4.5)
  })

  it.each(ALLE)('%s: Aktionsknöpfe heben sich ab, Schrift bleibt lesbar', (primary) => {
    const b = buttonColorsDark(
      primary,
      contrastRatio(primary, '#ffffff') >= 4.5 ? '#ffffff' : '#1d2421',
    )
    for (const bg of [b.background, b.hover]) {
      expect(contrastRatio(bg, DARK_BG)).toBeGreaterThanOrEqual(1.35)
      expect(contrastRatio(bg, b.foreground)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('Vereinsfarben werden beim Wechsel neu gerechnet', () => {
    const theme = {
      primary: '#14365d',
      on_primary: '#ffffff',
      accent: '#f2b33d',
      on_accent: '#1d2421',
    }
    applyTheme(theme)
    const root = document.documentElement
    expect(root.style.getPropertyValue('--color-link')).toBe(themeVars(theme)['--color-link'])
    setColorSchemeChoice('dark')
    setColorSchemePath('/mein-bereich')
    expect(root.style.getPropertyValue('--color-link')).toBe(linkColorDark('#14365d'))
    setColorSchemePath('/finanzen')
    expect(root.style.getPropertyValue('--color-link')).toBe(themeVars(theme)['--color-link'])
  })
})

describe('X-02 Schalter in Mein Konto', () => {
  it('speichert die Wahl im Konto und wendet sie sofort an', async () => {
    const calls = fakeApi({
      'PATCH /api/me/appearance/': (init) => ({
        status: 200,
        body: JSON.parse(String(init?.body)),
      }),
    })
    setColorSchemePath('/mein-konto')
    render(<AppearanceCard />)
    await userEvent.selectOptions(screen.getByLabelText('Hell oder dunkel'), 'Dunkel')
    await waitFor(() => expect(calls.some((c) => c.key === 'PATCH /api/me/appearance/')).toBe(true))
    const patch = calls.find((c) => c.key === 'PATCH /api/me/appearance/')!
    expect(JSON.parse(String(patch.init?.body))).toEqual({ color_scheme: 'dark' })
    expect(document.documentElement.dataset.theme).toBe('dark')
  })
})

describe('X-02 feste Farbwerte', () => {
  it('keine neuen festen Farbwerte in CSS außerhalb von theme.css', () => {
    // Heutiger Bestand; neue Farben gehören als Token nach theme.css (hell und dunkel).
    // Sinkt die Zahl, hier mitsenken.
    const BESTAND = 104
    let n = 0
    for (const [path, css] of Object.entries(CSS)) {
      if (path === '../theme/theme.css') continue
      n += css.match(/#[0-9a-f]{3,8}\b/gi)?.length ?? 0
    }
    expect(n).toBeLessThanOrEqual(BESTAND)
  })
})
