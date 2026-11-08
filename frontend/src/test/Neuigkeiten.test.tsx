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

function renderApp(
  path: string,
  files: Record<string, string>,
  orgs: Record<string, unknown>[] = [testOrg()],
  routes: Parameters<typeof fakeApi>[0] = {},
) {
  fakeApi({
    [SESSION]: () => ({ status: 200, body: { status: 200, data: { user: testUser } } }),
    'GET /api/me/organizations/': () => ({ status: 200, body: orgs }),
    ...routes,
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

  it('Reiter der Hilfe: Überblick nach Monaten und Änderungen der laufenden Fassung', async () => {
    renderApp('/hilfe/neuigkeiten', {
      '/lizenzen/CHANGELOG.md': CHANGELOG,
      '/lizenzen/version.txt': '2026.11.1\n',
    })
    // Unterseite mit eigener H1 (UX-Audit 08.11., W-02)
    expect(await screen.findByRole('heading', { level: 1, name: 'Neuigkeiten' })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Neuigkeiten' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(await screen.findByRole('heading', { level: 2, name: 'Was ist neu' })).toBeVisible()
    expect(await screen.findByRole('heading', { level: 3, name: 'November 2026' })).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'Änderungen je Version' })).toBeVisible()
    expect(await screen.findByRole('heading', { name: '2026.11.1 (2026-11-20)' })).toBeVisible()
    expect(screen.getByText('Erfundene Neuerung für den Test')).toBeVisible()
    expect(screen.queryByText(/Einleitung/)).toBeNull()
    expect(await screen.findByText(/Laufende Version: 2026\.11\.1\./)).toBeVisible()
  })

  it('alte Adresse „Was ist neu“ führt zum Reiter Neuigkeiten', async () => {
    renderApp('/hilfe/was-ist-neu', {})
    expect(await screen.findByRole('heading', { level: 2, name: 'Was ist neu' })).toBeVisible()
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

  it('Plattformverwalter sehen ein neueres Release (E9), andere nicht', async () => {
    const user = userEvent.setup()
    const platform = testOrg({
      id: 1,
      name: 'Plattform',
      type: 'platform',
      permissions: ['platform.manage'],
    })
    const update = {
      'GET /api/platform/update/': () => ({
        status: 200,
        body: {
          enabled: true,
          update: {
            version: '2026.12.0',
            url: 'https://github.com/hubiplan/hubiplan/releases/tag/v2026.12.0',
            running: '2026.11.0',
          },
        },
      }),
    }
    renderApp('/', {}, [platform], update)
    expect(
      await screen.findByText(
        /neuere Version von HUBIplan: 2026\.12\.0 \(hier läuft 2026\.11\.0\)/,
      ),
    ).toBeVisible()
    expect(screen.getByRole('link', { name: 'Änderungen ansehen' })).toHaveAttribute(
      'href',
      'https://github.com/hubiplan/hubiplan/releases/tag/v2026.12.0',
    )
    await user.click(screen.getByRole('button', { name: 'Ausblenden' }))
    await waitFor(() => expect(screen.queryByText(/neuere Version/)).toBeNull())
    expect(localStorage.getItem('hubiplan.release-hinweis.ausgeblendet')).toBe('2026.12.0')
  })

  it('ohne Plattformrecht keine Abfrage des Update-Hinweises', async () => {
    renderApp('/', {})
    expect(await screen.findByRole('navigation', { name: 'Rechtliches' })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    const calls = vi.mocked(globalThis.fetch).mock.calls.map(([input]) => String(input))
    expect(calls).not.toContain('/api/platform/update/')
  })

  it('Selbstupdate (7c): Auftrag mit Passwort, danach Hinweis „läuft“', async () => {
    const user = userEvent.setup()
    const platform = testOrg({
      id: 1,
      name: 'Plattform',
      type: 'platform',
      permissions: ['platform.manage'],
    })
    let sent: unknown = null
    const release = {
      version: '2026.12.0',
      url: 'https://github.com/hubiplan/hubiplan/releases/tag/v2026.12.0',
      running: '2026.11.0',
    }
    const routes = {
      'GET /api/platform/update/': () => ({
        status: 200,
        body: {
          enabled: true,
          update: release,
          selfupdate: {
            enabled: true,
            pending: false,
            result: {
              status: 'fehler',
              version: '2026.11.0',
              zeit: '2026-11-02T02:00:00Z',
              text: 'Erfundener Fehler.',
            },
          },
        },
      }),
      'POST /api/platform/update/': (init: RequestInit | undefined) => {
        sent = JSON.parse(String(init?.body))
        return { status: 202, body: { enabled: true, pending: true, result: null } }
      },
    }
    renderApp('/plattform/version', { '/lizenzen/version.txt': '2026.11.0\n' }, [platform], routes)
    expect(await screen.findByText(/Hier läuft HUBIplan 2026\.11\.0/)).toBeVisible()
    expect(screen.getByText(/fehlgeschlagen/)).toHaveTextContent('Erfundener Fehler.')
    const button = screen.getByRole('button', { name: 'Auf 2026.12.0 aktualisieren' })
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Dein Passwort zur Bestätigung'), 'geheim-test')
    await user.click(button)
    expect(await screen.findByText(/Die Aktualisierung läuft/)).toBeVisible()
    expect(sent).toEqual({ version: '2026.12.0', password: 'geheim-test' })
    expect(screen.queryByRole('button', { name: /aktualisieren/ })).toBeNull()
  })

  it('Selbstupdate aus: kein Knopf, nur Hinweis', async () => {
    const platform = testOrg({
      id: 1,
      name: 'Plattform',
      type: 'platform',
      permissions: ['platform.manage'],
    })
    const routes = {
      'GET /api/platform/update/': () => ({
        status: 200,
        body: {
          enabled: true,
          update: { version: '2026.12.0', url: '', running: '2026.11.0' },
          selfupdate: { enabled: false, pending: false, result: null },
        },
      }),
    }
    renderApp('/plattform/version', {}, [platform], routes)
    expect(
      await screen.findByText(/Selbstupdate ist auf diesem Server nicht eingeschaltet/),
    ).toBeVisible()
    expect(screen.queryByRole('button', { name: /aktualisieren/ })).toBeNull()
  })
})
