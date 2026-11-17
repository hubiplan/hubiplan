// UX-Audit 16.11.2026, mittlere Befunde der Verwaltung:
// VW-06 Zwischenüberschriften der Unterpunkte, VW-37 ruhende Rechte ohne Platzhalter,
// VW-55 Auswahl mit vollem Namen, VW-56 Reichweite von „Letzte Schritte“.
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { unitName } from '../api/orgs.ts'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { SubNavList } from '../components/SubNavList.tsx'
import type { NavNode } from '../components/subnav.ts'
import { UndoControls } from '../components/UndoControls.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { settingsItems } from '../pages/settings/items.ts'
import { musicSections } from '../pages/music/access.ts'
import { websiteSections } from '../pages/website/sections.ts'
import type { OrgSummary } from '../api/orgs.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const node = (to: string, label: string, section?: string): NavNode => ({
  to,
  label,
  section,
  end: true,
  children: [],
})

describe('VW-06 Zwischenüberschriften in der Seitenleiste', () => {
  it('setzt vor den ersten Punkt jedes Abschnitts eine Überschrift', () => {
    render(
      <MemoryRouter>
        <SubNavList
          pathname="/einstellungen"
          onChoose={() => {}}
          nodes={[
            node('/a', 'Verein', 'Allgemein'),
            node('/b', 'Module', 'Allgemein'),
            node('/c', 'Impressum', 'Recht'),
            node('/d', 'Protokoll', 'Daten'),
          ]}
        />
      </MemoryRouter>,
    )
    const items = screen.getAllByRole('list')[0].querySelectorAll(':scope > li')
    expect(Array.from(items).map((li) => li.textContent)).toEqual([
      'Allgemein',
      'Verein',
      'Module',
      'Recht',
      'Impressum',
      'Daten',
      'Protokoll',
    ])
    expect(document.querySelectorAll('.sidebar-sub-heading')).toHaveLength(3)
  })

  it('lässt die Überschrift weg, wenn es nur einen Abschnitt gibt', () => {
    render(
      <MemoryRouter>
        <SubNavList
          pathname="/x"
          onChoose={() => {}}
          nodes={[node('/a', 'Eins', 'Allgemein'), node('/b', 'Zwei', 'Allgemein')]}
        />
      </MemoryRouter>,
    )
    expect(document.querySelector('.sidebar-sub-heading')).toBeNull()
  })

  it('Einstellungen, Webseite und Musik liefern mehrere Abschnitte', () => {
    const org = testOrg({
      permissions: ['org.edit', 'roles.manage', 'audit.view', 'website.manage', 'music.view'],
      modules: ['members', 'website', 'music'],
    }) as unknown as OrgSummary
    const count = (items: { section?: string }[]) =>
      new Set(items.map((i) => i.section).filter(Boolean)).size
    expect(count(settingsItems(org))).toBeGreaterThan(1)
    expect(count(websiteSections(org))).toBeGreaterThan(1)
    expect(count(musicSections(org))).toBeGreaterThan(1)
  })
})

describe('VW-55 Auswahl von Untereinheiten', () => {
  it('nennt oben den vollen Namen mit Kurzname in Klammern, darunter den Pfad', () => {
    expect(unitName({ name: 'Grenadierkorps', display_name: 'Gren' })).toBe('Grenadierkorps (Gren)')
    expect(unitName({ name: 'Jugend', display_name: 'Jugend' })).toBe('Jugend')
    expect(unitName({ name: 'Jugend' })).toBe('Jugend')
    expect(
      unitName({ name: 'Zug 1', display_name: 'Z1', depth: 1, path: 'Grenadierkorps › Zug 1' }),
    ).toBe('Grenadierkorps › Zug 1')
  })
})

describe('VW-56 Letzte Schritte', () => {
  it('sagt, wie weit die Liste reicht, und verweist auf das Protokoll', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <UndoControls base="/api/orgs/7" logTo="/einstellungen/protokoll" />
      </MemoryRouter>,
    )
    await user.click(screen.getByRole('button', { name: 'Letzte Schritte' }))
    expect(
      screen.getByText(/In diesem Browserfenster gibt es noch keine Schritte/),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Einstellungen › Protokoll' })).toHaveAttribute(
      'href',
      '/einstellungen/protokoll',
    )
  })
})

describe('VW-37 Ruhende Rechte ohne Zwei-Faktor-Anmeldung', () => {
  it('zeigt auf der Startseite den einen nächsten Schritt statt eines Platzhalters', async () => {
    fakeApi({
      'GET /_allauth/browser/v1/auth/session': () => ({
        status: 200,
        body: {
          status: 200,
          data: {
            user: { ...testUser, mfa_required_by: '2026-11-01T00:00:00Z', mfa_overdue: true },
          },
        },
      }),
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: [], modules: [] })],
      }),
    })
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const step = await screen.findByTestId('mfa-schritt')
    expect(
      within(step).getByRole('heading', { name: 'Zwei-Faktor-Anmeldung einrichten' }),
    ).toBeInTheDocument()
    expect(within(step).getByRole('link', { name: 'Jetzt einrichten' })).toHaveAttribute(
      'href',
      '/mein-konto/anmeldung#zwei-faktor',
    )
    expect(screen.queryByText('Hier erscheinen Kacheln der Module.')).not.toBeInTheDocument()
  })
})
