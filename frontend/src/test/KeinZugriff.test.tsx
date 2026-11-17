// UX-Audit 16.11.2026, VW-09 und VW-35: Fehlende Rechte, ein ausgeschaltetes Modul und der
// falsche Arbeitsbereich zeigen überall dieselbe Karte mit Überschrift und Ausweg. Keine stille
// Umleitung auf die Startseite, kein scheinbarer Ladefehler.
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })

function renderAt(path: string, orgs: unknown[]) {
  fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: orgs }),
  })
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

async function expectNoAccess() {
  expect(
    await screen.findByRole('heading', { name: 'Kein Zugriff in dieser Einheit' }),
  ).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Zur Startseite' })).toBeInTheDocument()
  expect(screen.queryByText(/ließ sich nicht laden/)).not.toBeInTheDocument()
}

// Alle Module an, aber nur ein Recht, das zu keiner der geprüften Seiten gehört
const OHNE_RECHT = testOrg({
  permissions: ['members.view'],
  // ohne Dachverband gibt es auch nichts zu empfangen
  has_federation: false,
  modules: [
    'members',
    'finance',
    'billing',
    'circulars',
    'website',
    'surveys',
    'meetings',
    'chronicle',
    'music',
    'scores',
    'todos',
    'bookings',
    'helpers',
    'obligations',
  ],
})

describe('Kein Zugriff: dieselbe Karte auf jeder Seite', () => {
  it.each([
    '/rundschreiben',
    '/finanzen',
    '/einstellungen',
    '/webseite',
    '/umfragen',
    '/versammlungen',
    '/chronik',
    '/noten',
    '/musik',
    '/aufgaben',
    '/helferdienste',
  ])('%s ohne Recht', async (path) => {
    renderAt(path, [OHNE_RECHT])
    await expectNoAccess()
  })

  it.each(['/chronik', '/fristenkalender', '/noten', '/aufgaben/erinnerungen', '/einstellungen'])(
    '%s ohne gewählte Einheit zeigt „Kein Zugriff“ statt eines Ladefehlers',
    async (path) => {
      renderAt(path, [])
      await expectNoAccess()
    },
  )
})
