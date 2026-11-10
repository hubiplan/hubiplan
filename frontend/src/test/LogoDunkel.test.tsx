// Zweites Logo/Wappen für den Dunkelmodus (Ralf 10.11.2026)
import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Logo, ThemedLogo } from '../components/Logo.tsx'
import { PRODUCT_NAME, setPlatform } from '../theme/platform.ts'

const THEME_CSS = (
  import.meta.glob('../theme/theme.css', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>
)['../theme/theme.css']

const HELL = '/media/logos/organisationen/1-20261110120000.png'
const DUNKEL = '/media/logos/organisationen/1-dunkel-20261110120000.png'

afterEach(() => {
  act(() => setPlatform({ name: PRODUCT_NAME, short_name: '', logo_url: null, theme: null }))
})

function sources(container: HTMLElement) {
  return [...container.querySelectorAll('img')].map((img) => ({
    src: img.getAttribute('src'),
    light: img.classList.contains('logo-for-light'),
    dark: img.classList.contains('logo-for-dark'),
  }))
}

describe('Logo für den Dunkelmodus', () => {
  it('ohne dunkles Logo nur das helle, ohne Umschaltklassen', () => {
    const { container } = render(<Logo name="Schützenverein Musterstadt" logoUrl={HELL} />)
    expect(sources(container)).toEqual([{ src: HELL, light: false, dark: false }])
  })

  it('mit dunklem Logo beide Bilder, je eins für hell und dunkel', () => {
    const { container } = render(
      <Logo name="Schützenverein Musterstadt" logoUrl={HELL} logoDarkUrl={DUNKEL} />,
    )
    expect(sources(container)).toEqual([
      { src: HELL, light: true, dark: false },
      { src: DUNKEL, light: false, dark: true },
    ])
  })

  it('gleiche Adresse für hell und dunkel: ein Bild', () => {
    const { container } = render(<ThemedLogo light={HELL} dark={HELL} />)
    expect(container.querySelectorAll('img')).toHaveLength(1)
  })

  it('nur dunkles Logo: hell bleibt das H-Zeichen', () => {
    const { container } = render(<ThemedLogo light={null} dark={DUNKEL} />)
    expect(container.querySelector('svg')?.classList.contains('logo-for-light')).toBe(true)
    expect(sources(container)).toEqual([{ src: DUNKEL, light: false, dark: true }])
  })

  it('Anmeldeseite: dunkles Logo der Instanz', () => {
    act(() =>
      setPlatform({
        name: 'Vereinsportal Musterkreis',
        short_name: '',
        logo_url: HELL,
        logo_dark_url: DUNKEL,
        theme: null,
      }),
    )
    const { container } = render(<Logo />)
    expect(sources(container).map((s) => s.src)).toEqual([HELL, DUNKEL])
  })

  it('Stylesheet blendet je nach Darstellung eins der beiden aus', () => {
    expect(THEME_CSS).toMatch(
      /:root:not\(\[data-theme='dark'\]\) \.logo-for-dark,\s*:root\[data-theme='dark'\] \.logo-for-light \{\s*display: none;/,
    )
  })
})
