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

  it('eigenes Symbol: Browser-Tab, Apple-Symbol und Manifest kommen von der Instanz', () => {
    document.head.insertAdjacentHTML(
      'beforeend',
      '<link rel="icon" type="image/svg+xml" href="/favicon.svg" id="t-icon">' +
        '<link rel="apple-touch-icon" href="/apple-touch-icon.png" id="t-apple">' +
        '<link rel="manifest" href="/manifest.webmanifest" id="t-manifest">' +
        '<meta name="theme-color" content="#0e7c66" id="t-color">',
    )
    const href = (id: string) => document.getElementById(id)?.getAttribute('href')
    act(() => setPlatform({ ...MUSTERKREIS, icon: true }))
    expect(href('t-icon')).toBe('/api/public/platform/icon-32.png')
    expect(href('t-apple')).toBe('/api/public/platform/icon-180.png')
    expect(href('t-manifest')).toBe('/api/public/platform/manifest.webmanifest')
    expect(document.getElementById('t-color')?.getAttribute('content')).toBe('#1f4e79')
    // Ohne Symbol: wieder die Dateien aus index.html, das Manifest bleibt das der Instanz
    act(() => setPlatform({ ...MUSTERKREIS, icon: false }))
    expect(href('t-icon')).toBe('/favicon.svg')
    expect(href('t-apple')).toBe('/apple-touch-icon.png')
    expect(href('t-manifest')).toBe('/api/public/platform/manifest.webmanifest')
    standard()
    expect(href('t-manifest')).toBe('/manifest.webmanifest')
    expect(document.getElementById('t-color')?.getAttribute('content')).toBe('#0e7c66')
    for (const id of ['t-icon', 't-apple', 't-manifest', 't-color'])
      document.getElementById(id)?.remove()
  })
})
