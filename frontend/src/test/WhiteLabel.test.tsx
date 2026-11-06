// White Label W1: Name, Farben und Logo der Instanz ohne Einheit (konzepte/white-label.md)
import { act, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { formatTitle } from '../components/pageTitle.ts'
import { Logo } from '../components/Logo.tsx'
import { loadPlatform, PRODUCT_NAME, setPlatform } from '../theme/platform.ts'
import { applyTheme } from '../theme/theme.ts'
import { fakeApi } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedOut = () => ({ status: 401, body: { status: 401, data: { flows: [] } } })
const MUSTERKREIS = {
  name: 'Vereinsportal Musterkreis',
  short_name: 'Musterkreis',
  logo_url: '/media/logos/organisationen/1-musterkreis.png',
  theme: { primary: '#1f4e79', on_primary: '#ffffff', accent: '#f2b33d', on_accent: '#1d2421' },
}

function standard() {
  act(() => setPlatform({ name: PRODUCT_NAME, short_name: '', logo_url: null, theme: null }))
}

afterEach(() => {
  standard()
  applyTheme(null)
})

describe('Instanz (White Label)', () => {
  it('Standard: Titel und Logo wie bisher', () => {
    expect(formatTitle('Mitglieder')).toBe('Mitglieder · HUBIplan')
    const { container } = render(<Logo />)
    expect(container.querySelector('.logo-wordmark')?.textContent).toBe('HUBIplan')
    expect(document.getElementById('plattform-farben')).toBeNull()
  })

  it('lädt Name, Logo und Farben der Instanz', async () => {
    fakeApi({ 'GET /api/public/platform/': () => ({ status: 200, body: MUSTERKREIS }) })
    await act(async () => {
      await loadPlatform()
    })
    expect(formatTitle('Anmelden')).toBe('Anmelden · Vereinsportal Musterkreis')
    // Der Instanzname steht nicht doppelt im Titel
    expect(formatTitle('Mitglieder', 'Vereinsportal Musterkreis')).toBe(
      'Mitglieder · Vereinsportal Musterkreis',
    )
    const { container } = render(<Logo />)
    expect(screen.getByText('Vereinsportal Musterkreis')).toBeInTheDocument()
    expect(container.querySelector('img')?.getAttribute('src')).toBe(MUSTERKREIS.logo_url)
    const style = document.getElementById('plattform-farben')
    expect(style?.textContent).toContain('--color-primary: #1f4e79')
  })

  it('Farben einer Einheit gehen vor, ohne Einheit gilt die Instanz', () => {
    act(() => setPlatform(MUSTERKREIS))
    const root = document.documentElement
    applyTheme({
      primary: '#7a1f1f',
      on_primary: '#ffffff',
      accent: '#f2b33d',
      on_accent: '#000000',
    })
    // Farben der Einheit stehen direkt am Element und schlagen damit jede Stilregel
    expect(root.style.getPropertyValue('--color-primary')).toBe('#7a1f1f')
    applyTheme(null)
    expect(root.style.getPropertyValue('--color-primary')).toBe('')
    expect(document.getElementById('plattform-farben')).not.toBeNull()
  })

  it('Logo einer Einheit bleibt deren Logo', () => {
    act(() => setPlatform(MUSTERKREIS))
    const { container } = render(<Logo name="Schützenverein Musterstadt" logoUrl={null} />)
    expect(screen.getByText('Schützenverein Musterstadt')).toBeInTheDocument()
    expect(container.querySelector('img')).toBeNull()
  })

  it('Anmeldeseite zeigt „mit HUBIplan“ nur bei eigenem Instanznamen', async () => {
    fakeApi({ [SESSION]: loggedOut })
    const view = render(
      <MemoryRouter initialEntries={['/anmelden']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Anmelden' })
    expect(screen.queryByRole('link', { name: 'mit HUBIplan' })).toBeNull()
    act(() => setPlatform(MUSTERKREIS))
    const link = await screen.findByRole('link', { name: 'mit HUBIplan' })
    expect(link.getAttribute('href')).toBe('/lizenz')
    expect(screen.getByText('Vereinsportal Musterkreis')).toBeInTheDocument()
    await waitFor(() => expect(document.title).toBe('Anmelden · Vereinsportal Musterkreis'))
    view.unmount()
  })
})
