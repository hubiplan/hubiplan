// Releases R6 (konzepte/releases.md): Seite „Neuigkeiten“ und Hinweis „Das ist neu“ nach dem Update.
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { changelogBody } from '../news/changelog.ts'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const CHANGELOG = `# Änderungen an HUBIplan

Einleitung, die auf der Seite nicht erscheint.

<!-- Neue Versionen hier einfügen (scripts/release.sh) -->

## 2026.11.1 (2026-11-20)

### Neu

- Erfundene Neuerung für den Test
`

function renderApp(path: string, files: Record<string, string>, orgs = [testOrg()]) {
  fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: orgs }),
  })
  const api = vi.mocked(globalThis.fetch).getMockImplementation()!
  vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
    const file = files[String(input)]
    if (file !== undefined) return new Response(file)
    // Fehlende statische Dateien: der Webserver liefert die App-Seite
    if (String(input).startsWith('/lizenzen/')) return new Response('<!doctype html>')
    return api(input, init)
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
}

describe('Neuigkeiten', () => {
  it('Changelog ohne Titel und Einleitung; App-Seite statt Datei gilt als fehlend', () => {
    expect(changelogBody(CHANGELOG)).toMatch(/^## 2026\.11\.1/)
    expect(changelogBody(CHANGELOG)).not.toMatch(/Einleitung/)
    expect(changelogBody('<!doctype html><html></html>')).toBeNull()
  })

  it('Seite zeigt die Änderungen der laufenden Fassung', async () => {
    renderApp('/hilfe/neuigkeiten', {
      '/lizenzen/CHANGELOG.md': CHANGELOG,
      '/lizenzen/version.txt': '2026.11.1\n',
    })
    expect(await screen.findByRole('heading', { level: 1, name: 'Neuigkeiten' })).toBeVisible()
    expect(await screen.findByRole('heading', { name: '2026.11.1 (2026-11-20)' })).toBeVisible()
    expect(screen.getByText('Erfundene Neuerung für den Test')).toBeVisible()
    expect(screen.queryByText(/Einleitung/)).toBeNull()
    expect(await screen.findByText(/Laufende Version: 2026\.11\.1\./)).toBeVisible()
  })

  it('ohne Changelog ein Hinweis statt einer leeren Seite', async () => {
    renderApp('/hilfe/neuigkeiten', {})
    expect(
      await screen.findByText('Die Änderungshinweise liegen dieser Fassung nicht bei.'),
    ).toBeVisible()
  })

  it('Hinweis „Das ist neu“ einmal nach dem Update, Ausblenden merkt sich die Version', async () => {
    const user = userEvent.setup()
    renderApp('/', { '/lizenzen/version.txt': '2026.11.1\n' })
    expect(
      await screen.findByText(/HUBIplan wurde auf Version 2026\.11\.1 aktualisiert/),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: 'Das ist neu' })).toHaveAttribute(
      'href',
      '/hilfe/neuigkeiten',
    )
    await user.click(screen.getByRole('button', { name: 'Ausblenden' }))
    await waitFor(() => expect(screen.queryByText(/aktualisiert/)).toBeNull())
    expect(localStorage.getItem('hubiplan.neuigkeiten.gesehen')).toBe('2026.11.1')
  })

  it('kein Hinweis bei Zwischenständen', async () => {
    renderApp('/', { '/lizenzen/version.txt': '2026.11.1+3.0a5d21e\n' })
    expect(await screen.findByRole('navigation', { name: 'Rechtliches' })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(/aktualisiert/)).toBeNull()
  })

  it('kein Hinweis, wenn die Version schon gesehen wurde', async () => {
    localStorage.setItem('hubiplan.neuigkeiten.gesehen', '2026.11.1')
    renderApp('/', { '/lizenzen/version.txt': '2026.11.1\n' })
    expect(await screen.findByRole('navigation', { name: 'Rechtliches' })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(/aktualisiert/)).toBeNull()
  })

  it('kein Hinweis für Mitglieder ohne Verwaltungsrechte', async () => {
    renderApp('/', { '/lizenzen/version.txt': '2026.11.1\n' }, [])
    expect(await screen.findByRole('navigation', { name: 'Rechtliches' })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText(/aktualisiert/)).toBeNull()
  })
})
