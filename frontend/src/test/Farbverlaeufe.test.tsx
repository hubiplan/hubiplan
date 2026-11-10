// Verläufe und Farbblatt (Ralf 10.11.2026, erfundene Farben)
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { ContrastWarnings } from '../pages/website/DesignChooser.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

const theme = {
  primary_color: '#05487a',
  accent_color: '#032e52',
  primary_color_name: 'Blau',
  accent_color_name: 'Dunkelblau',
  primary_color_use: 'Leitfarbe',
  accent_color_use: '',
  extra_colors: [{ color: '#3c3d3e', name: 'Anthrazit', use: 'Fließtext' }],
  gradients: [],
  logo_url: null,
  effective: {
    primary: '#05487a',
    on_primary: '#ffffff',
    accent: '#032e52',
    on_accent: '#ffffff',
    logo_url: null,
    palette: [
      { color: '#05487a', on_color: '#ffffff', name: 'Blau', use: 'Leitfarbe' },
      { color: '#032e52', on_color: '#ffffff', name: 'Dunkelblau', use: '' },
      { color: '#3c3d3e', on_color: '#ffffff', name: 'Anthrazit', use: 'Fließtext' },
    ],
    gradients: [
      {
        name: 'Blauverlauf',
        from: 0,
        to: 1,
        direction: 'right',
        colors: ['#05487a', '#032e52'],
        on_color: '#ffffff',
        contrast: 9.5,
      },
    ],
    inherited_from: { colors: null, logo: null },
  },
}

function renderAt(path: string) {
  const org = testOrg({ permissions: ['org.edit', 'theme.edit'] })
  const calls = fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    'GET /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
    'PATCH /api/orgs/7/theme/': () => ({ status: 200, body: theme }),
  })
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('Verläufe (Erscheinungsbild)', () => {
  it('legt einen Verlauf an und speichert ihn', async () => {
    const calls = renderAt('/einstellungen/erscheinungsbild')
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Verlauf hinzufügen' }, { timeout: 5000 }),
    )
    await user.type(screen.getByLabelText('Name'), 'Blauverlauf')
    await waitFor(
      () =>
        expect(
          calls.some((c) => {
            if (c.key !== 'PATCH /api/orgs/7/theme/') return false
            const g = JSON.parse(String(c.init?.body)).gradients?.[0]
            return g?.name === 'Blauverlauf' && g.from === 0 && g.to === 1
          }),
        ).toBe(true),
      { timeout: 3000 },
    )
    expect(screen.getByLabelText('Verwendung der Hauptfarbe')).toHaveValue('Leitfarbe')
  })

  it('zeigt das Farbblatt mit Verwendung und Verlauf', async () => {
    renderAt('/einstellungen/erscheinungsbild/farbblatt')
    expect(await screen.findByText('Anthrazit', {}, { timeout: 5000 })).toBeVisible()
    expect(screen.getByText('Fließtext')).toBeVisible()
    expect(screen.getByText('#05487A · RGB 5 72 122')).toBeVisible()
    expect(screen.getByText('Blauverlauf')).toBeVisible()
    expect(screen.getByText('#05487A → #032E52')).toBeVisible()
  })
})

describe('Kontrastwarnung (Gestaltung)', () => {
  it('warnt nur bei schlecht lesbarem Text', () => {
    const { rerender, container } = render(<ContrastWarnings colors={{}} />)
    expect(container).toBeEmptyDOMElement()
    rerender(
      <ContrastWarnings
        colors={{
          text: { color: '#5c5d5e', on_color: '#ffffff' },
          surface: { color: '#3c3d3e', on_color: '#ffffff' },
        }}
      />,
    )
    expect(screen.getByText(/Fließtext auf Flächen/)).toBeVisible()
  })
})
