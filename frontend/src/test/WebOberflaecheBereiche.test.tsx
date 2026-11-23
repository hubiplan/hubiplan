// Bereichsübersicht (Konzept Web-Oberfläche W4): Seiten eines Bereichs mit Beschreibung.
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { AREAS, modules } from '../modules.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Bereiche des Menüs', () => {
  it('jeder Menüpunkt gehört zu einem der neun Bereiche und hat eine Beschreibung', () => {
    const ids = AREAS.map((a) => a.id)
    expect(ids).toEqual([
      'start',
      'mitglieder',
      'untereinheiten',
      'planung',
      'kommunikation',
      'webseite',
      'vereinsleben',
      'finanzen',
      'verein',
    ])
    for (const m of modules) {
      expect(ids, m.id).toContain(m.area)
      expect(m.text, m.id).toBeTruthy()
    }
  })

  it('Bereich „Einstellungen“ statt „Verein“, Material & Räume unter Planung (Issue #703)', () => {
    expect(AREAS.find((a) => a.id === 'verein')?.label).toBe('Einstellungen')
    const areaOf = (id: string) => modules.find((m) => m.id === id)?.area
    expect(areaOf('material')).toBe('planung')
    expect(['einstellungen', 'dsgvo', 'plattform'].map(areaOf)).toEqual([
      'verein',
      'verein',
      'verein',
    ])
  })

  it('das Bereichsmenü hat keinen Link „Menü anordnen“ mehr (Issue #702)', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['settings.view', 'settings.edit', 'members.view'] })],
      }),
    })
    renderApp('/bereich/verein')
    const nav = await screen.findByRole('navigation', { name: 'Hauptmenü' })
    expect((await within(nav).findAllByText('Einstellungen')).length).toBeGreaterThan(0)
    expect(screen.queryByRole('link', { name: 'Menü anordnen' })).not.toBeInTheDocument()
  })

  it('Einstellungen: Unterpunkte direkt im Bereichsmenü, DSGVO darunter unter Recht', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [
          testOrg({
            permissions: ['settings.view', 'settings.edit', 'members.view', 'privacy.view'],
          }),
        ],
      }),
    })
    renderApp('/bereich/verein')
    const menu = await screen.findByRole('list', { name: 'Einstellungen' })
    const links = within(menu)
      .getAllByRole('link')
      .map((l) => l.textContent)
    expect(links).toContain('Organisation')
    expect(links).not.toContain('Einstellungen')
    expect(links.indexOf('DSGVO')).toBe(links.indexOf('Datenschutz') + 1)
  })

  it('die Bereichsübersicht zeigt die Seiten des Bereichs mit Beschreibung und Offenem', async () => {
    const org = testOrg({
      modules: ['events', 'meetings'],
      permissions: ['events.view', 'meetings.view', 'todos.view'],
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      'GET /api/orgs/7/open-tasks/': () => ({
        status: 200,
        body: {
          items: [
            {
              kind: 'meeting_minutes',
              kind_label: 'Protokoll',
              title: 'Protokoll der Generalversammlung offen',
              detail: '',
              created_at: null,
              link: '/versammlungen/3',
            },
          ],
        },
      }),
    })
    renderApp('/bereich/planung')
    expect(await screen.findByRole('heading', { level: 1, name: 'Planung' })).toBeInTheDocument()
    const main = within(screen.getByRole('main'))
    const card = await main.findByRole('link', { name: /Versammlungen/ })
    expect(card).toHaveAttribute('href', '/versammlungen')
    expect(card).toHaveTextContent('Einladen, Tagesordnung, Beschlüsse und Protokoll')
    expect(await main.findByText('Protokoll der Generalversammlung offen')).toBeInTheDocument()
    expect(main.getByRole('link', { name: /Termine/ })).toBeInTheDocument()
    expect(main.getByRole('link', { name: /Aufgaben/ })).toBeInTheDocument()
    // Der Name des Bereichs über dem Bereichsmenü führt zur Übersicht
    const nav = within(screen.getByRole('navigation', { name: 'Hauptmenü' }))
    expect(nav.getByRole('link', { name: 'Übersicht des Bereichs Planung' })).toHaveAttribute(
      'href',
      '/bereich/planung',
    )
  })
})
