// Farbrollen (Ralf 13.11.2026): Bei jeder Farbe ankreuzen, wofür sie da ist; mit Schalter
// färben die Rollen auch HUBIplan im hellen Modus, mit Kontrastschutz. Erfundene Farben.
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { appColors, applyTheme, setThemeScheme } from '../theme/theme.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

const PALETTE = [
  { color: '#05487a' },
  { color: '#032e52' },
  { color: '#3c3d3e' },
  { color: '#5c5d5e' },
  { color: '#eef2f6' },
  { color: '#ffffff' },
]

const theme = {
  primary_color: '#05487a',
  accent_color: '#032e52',
  primary_color_name: 'Blau',
  accent_color_name: 'Dunkelblau',
  extra_colors: [
    { color: '#3c3d3e', name: 'Anthrazit' },
    { color: '#eef2f6', name: 'Hellblau-Grau' },
  ],
  gradients: [{ name: 'Grau', from: 2, to: 3, direction: 'right' }],
  palette_roles: { text: 2 },
  palette_roles_in_app: false,
  logo_url: null,
  effective: {
    primary: '#05487a',
    on_primary: '#ffffff',
    accent: '#032e52',
    on_accent: '#ffffff',
    logo_url: null,
    inherited_from: { colors: null, logo: null },
  },
}

function renderPage() {
  const org = testOrg({ permissions: ['org.edit', 'theme.edit'] })
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    'GET /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
    'PATCH /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
  })
  render(
    <MemoryRouter initialEntries={['/einstellungen/erscheinungsbild']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  const patched = () =>
    calls
      .filter((c) => c.key === 'PATCH /api/orgs/7/theme/')
      .map((c) => JSON.parse(String(c.init?.body)))
  return { patched }
}

describe('Farbrollen in den Einstellungen', () => {
  it('kreuzt eine Rolle an und nimmt sie der vorigen Farbe', async () => {
    const { patched } = renderPage()
    const user = userEvent.setup()
    const third = await screen.findByRole(
      'group',
      { name: '3. Farbe verwendet für' },
      { timeout: 5000 },
    )
    expect(within(third).getByRole('checkbox', { name: 'Fließtext' })).toBeChecked()
    const fourth = screen.getByRole('group', { name: '4. Farbe verwendet für' })
    await user.click(within(fourth).getByRole('checkbox', { name: 'Flächen und Tabellenzeilen' }))
    await user.click(within(fourth).getByRole('checkbox', { name: 'Fließtext' }))
    expect(within(third).getByRole('checkbox', { name: 'Fließtext' })).not.toBeChecked()
    await waitFor(() => expect(patched().at(-1)?.palette_roles).toEqual({ text: 3, surface: 3 }), {
      timeout: 3000,
    })
  })

  it('Verschieben hält Rollen und Verläufe bei ihrer Farbe', async () => {
    const { patched } = renderPage()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: '3. Farbe nach unten' }, { timeout: 5000 }),
    )
    await waitFor(
      () => {
        const last = patched().at(-1)
        expect(last?.palette_roles).toEqual({ text: 3 })
        expect(last?.gradients?.[0]).toMatchObject({ from: 3, to: 2 })
      },
      { timeout: 3000 },
    )
  })

  it('Entfernen löst die Rolle und den Verlauf der Farbe', async () => {
    const { patched } = renderPage()
    const user = userEvent.setup()
    const buttons = await screen.findAllByRole('button', { name: 'Entfernen' }, { timeout: 5000 })
    // erster „Entfernen“ gehört zur 3. Farbe (Anthrazit)
    await user.click(buttons[0])
    await waitFor(
      () => {
        const last = patched().at(-1)
        expect(last?.palette_roles).toEqual({})
        expect(last?.gradients).toEqual([])
      },
      { timeout: 3000 },
    )
  })
})

describe('Farbrollen in der Oberfläche', () => {
  afterEach(() => {
    setThemeScheme('light')
    applyTheme(null)
  })
  const vereinstheme = {
    primary: '#05487a',
    on_primary: '#ffffff',
    accent: '#032e52',
    on_accent: '#ffffff',
    palette: PALETTE,
    palette_roles: { text: 2, muted: 3, surface: 4, background: 5 },
    palette_roles_in_app: true,
  }

  it('setzt Text, Flächen und Hintergrund nur im hellen Modus', () => {
    const root = document.documentElement
    applyTheme(vereinstheme)
    expect(root.style.getPropertyValue('--color-text')).toBe('#3c3d3e')
    expect(root.style.getPropertyValue('--color-surface')).toBe('#eef2f6')
    expect(root.style.getPropertyValue('--color-bg')).toBe('#ffffff')
    setThemeScheme('dark')
    expect(root.style.getPropertyValue('--color-text')).toBe('')
    expect(root.style.getPropertyValue('--color-bg')).toBe('')
  })

  it('ohne Schalter bleibt die Oberfläche, wie sie ist', () => {
    applyTheme({ ...vereinstheme, palette_roles_in_app: false })
    expect(document.documentElement.style.getPropertyValue('--color-text')).toBe('')
  })

  it('Kontrastschutz: zu helle Fläche fällt auf die Vorgabe zurück', () => {
    // Text Hellblau-Grau auf weißer Fläche wäre unlesbar: erst fällt die Fläche, dann der Text
    const { colors, dropped } = appColors(PALETTE, { text: 4, surface: 5 })
    expect(dropped).toContain('surface')
    expect(colors).toEqual({})
  })

  it('lesbare Rollen bleiben', () => {
    const { colors, dropped } = appColors(PALETTE, { text: 2, muted: 3, surface: 4, background: 5 })
    expect(dropped).toEqual([])
    expect(colors).toEqual({
      text: '#3c3d3e',
      muted: '#5c5d5e',
      surface: '#eef2f6',
      background: '#ffffff',
    })
  })
})
