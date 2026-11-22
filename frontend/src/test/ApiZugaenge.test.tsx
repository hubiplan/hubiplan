// Einstellungen › API-Zugänge: anlegen, Schlüssel einmal zeigen, Bereiche (erfundene Daten).
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider, useOrg } from '../org/OrgContext.tsx'
import { ApiAccessPage } from '../pages/settings/ApiAccessPage.tsx'
import type { OrgSummary } from '../api/orgs.ts'
import { settingsItems } from '../pages/settings/items.ts'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const session = () => ({
  status: 200,
  body: { status: 200, data: { user: testUser, methods: [] }, meta: { is_authenticated: true } },
})

const scopes = [
  {
    scope: 'einheit.lesen',
    label: 'Einheit lesen',
    description: 'Name, Anschrift, Kontakt, Logo und die Untereinheiten als Baum',
    unit_ok: true,
    needs: '',
  },
  {
    scope: 'termine.lesen',
    label: 'Öffentliche Termine lesen',
    description: 'Termine mit der Sichtbarkeit „nach außen öffentlich“',
    unit_ok: true,
    needs: '',
  },
  {
    scope: 'termine.mitglieder',
    label: 'Auch Termine für Mitglieder lesen',
    description: 'Zusätzlich Termine mit der Sichtbarkeit „Mitglieder“',
    unit_ok: true,
    needs: 'termine.lesen',
  },
  {
    scope: 'vorstand.lesen',
    label: 'Vorstand und Ämter lesen',
    description: 'Rollen mit „auf der Webseite zeigen“',
    unit_ok: false,
    needs: '',
  },
]

const access = {
  id: 4,
  name: 'Verbandssoftware',
  purpose: 'Terminliste des Verbands',
  recipient: 'Musterverband',
  scopes: ['einheit.lesen', 'termine.lesen'],
  unit: null,
  key_hint: 'Ab3x',
  key_created_at: '2026-11-22T08:00:00Z',
  previous_until: null,
  expires_at: '2027-11-20T22:59:59Z',
  allowed_networks: [],
  embeddable: false,
  state: 'idle',
  idle_at: '2027-02-20T08:00:00Z',
  created_at: '2026-11-22T08:00:00Z',
  created_by: 'Erika Beispiel',
  last_used_at: null,
  last_used_ip: '',
  request_count: 0,
}

const list = (accesses: object[]) => ({
  address: 'https://verein.example/api/partner/v1/',
  docs: 'https://verein.example/api/partner/v1/openapi.json',
  requests_per_hour: 600,
  max_days: 365,
  idle_days: 90,
  overlap_days: 7,
  scopes,
  units: [{ id: 12, name: 'Jugend' }],
  accesses,
})

function WhenActive() {
  const { active } = useOrg()
  return active ? <ApiAccessPage /> : null
}

function renderPage(routes: Parameters<typeof fakeApi>[0]) {
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': session,
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ type: 'club', permissions: ['settings.view', 'api.manage'] })],
    }),
    ...routes,
  })
  render(
    <MemoryRouter>
      <AuthProvider>
        <OrgProvider>
          <WhenActive />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return calls
}

describe('API-Zugänge', () => {
  it('Menüpunkt nur mit Modul und Zusatzrecht', () => {
    const has = (org: object) =>
      settingsItems(org as unknown as OrgSummary).some((item) => item.to === '/einstellungen/api')
    const permissions = ['settings.view', 'api.manage']
    expect(has(testOrg({ type: 'club', permissions, modules: ['api'] }))).toBe(true)
    expect(has(testOrg({ type: 'club', permissions, modules: [] }))).toBe(false)
    expect(has(testOrg({ type: 'club', permissions: ['settings.view'], modules: ['api'] }))).toBe(
      false,
    )
  })

  it('anlegen zeigt den Schlüssel einmal; ein Bereich nimmt den vorausgesetzten mit', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([]) }),
      'POST /api/orgs/7/api-accesses/': () => ({
        status: 201,
        body: { ...access, state: 'active', key: 'hpk_erfundenerSchluessel' },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText('Noch keine API-Zugänge angelegt.')).toBeInTheDocument()
    expect(screen.getByText('https://verein.example/api/partner/v1/')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    await user.type(screen.getByLabelText(/^Name/), 'Verbandssoftware')
    await user.click(screen.getByRole('checkbox', { name: 'Auch Termine für Mitglieder lesen' }))
    expect(screen.getByRole('checkbox', { name: 'Öffentliche Termine lesen' })).toBeChecked()
    // Für eine Untereinheit gibt es den Vorstand nicht
    await user.selectOptions(screen.getByLabelText('Gilt für'), '12')
    expect(screen.getByRole('checkbox', { name: /Vorstand und Ämter lesen/ })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Zugang anlegen' }))
    expect(await screen.findByDisplayValue('hpk_erfundenerSchluessel')).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/orgs/7/api-accesses/')
    expect(JSON.parse(String(post?.init?.body))).toMatchObject({
      name: 'Verbandssoftware',
      unit: 12,
      scopes: ['termine.mitglieder', 'termine.lesen'],
      allowed_networks: [],
      embeddable: false,
    })
    await user.click(screen.getByRole('button', { name: 'Fertig' }))
    expect(screen.queryByDisplayValue('hpk_erfundenerSchluessel')).not.toBeInTheDocument()
    expect(screen.getByText(/Schlüssel endet auf …Ab3x/)).toBeInTheDocument()
  })

  it('ruhender Zugang lässt sich wieder einschalten', async () => {
    const calls = renderPage({
      'GET /api/orgs/7/api-accesses/': () => ({ status: 200, body: list([access]) }),
      'POST /api/orgs/7/api-accesses/4/resume/': () => ({
        status: 200,
        body: { ...access, state: 'active' },
      }),
    })
    const user = userEvent.setup()
    expect(await screen.findByText('ruht')).toBeInTheDocument()
    expect(screen.getByText('Einheit lesen, Öffentliche Termine lesen')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Wieder einschalten' }))
    expect(await screen.findByText('aktiv')).toBeInTheDocument()
    expect(calls.some((c) => c.key === 'POST /api/orgs/7/api-accesses/4/resume/')).toBe(true)
  })
})
