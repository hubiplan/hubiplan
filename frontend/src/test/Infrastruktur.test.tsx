import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const house = {
  id: 3,
  kind: 'facility',
  inventory_number: 'INF-000003',
  title: 'Schützenhaus',
  description: 'Vereinsheim mit Saal',
  purpose: '',
  location_kind: 'address',
  member: null,
  member_name: '',
  address: { street: 'Musterweg 1', postal_code: '12345', city: 'Musterstadt', country: 'DE' },
  facility: null,
  facility_title: '',
  belongs_to: null,
  belongs_to_title: '',
  facility_type: 'building',
  ownership: 'own',
  capacity: 120,
  lanes: [],
  access_note: 'Schlüsselkasten am Seiteneingang',
  location_note: '',
  condition: 'ready',
  condition_note: '',
  version: 1,
  deleted_at: null,
  location_review: false,
  photo_url: null,
  events: [],
  todos: [],
  documents: [],
  uses: [],
  parent: null,
  areas: [
    {
      id: 4,
      kind: 'facility',
      inventory_number: 'INF-000004',
      title: 'Luftgewehrstand',
      condition: 'ready',
      location_kind: 'facility',
      member_name: '',
      location_note: '',
    },
  ],
  contents: [],
  accessories: [
    {
      id: 5,
      kind: 'material',
      inventory_number: 'MAT-000005',
      title: 'Schlüssel Haupteingang',
      condition: 'ready',
      location_kind: 'member',
      member_name: 'Erika Beispiel',
      location_note: '',
    },
  ],
}

function setup(permissions: string[]) {
  return fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['material', 'infrastructure'], permissions })],
    }),
    'GET /api/orgs/7/facilities/?': () => ({
      status: 200,
      body: { items: [house], count: 1, page: 1, can_edit: true },
    }),
    'GET /api/orgs/7/facilities/3/': () => ({ status: 200, body: house }),
    'GET /api/orgs/7/facilities/3/history/': () => ({ status: 200, body: [] }),
  })
}

function show(path: string, permissions: string[]) {
  setup(permissions)
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

describe('Infrastruktur', () => {
  it('listet Infrastruktur mit Art', async () => {
    show('/infrastruktur', ['infrastructure.view', 'infrastructure.edit'])
    expect(
      await screen.findByRole('heading', { name: 'Räume und Anlagen', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByRole('link', { name: 'Schützenhaus' })).toBeInTheDocument()
    expect(screen.getByText('Gebäude oder Vereinsheim')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Raum oder Anlage anlegen' })).toBeInTheDocument()
  })

  it('zeigt Bereiche, zugehöriges Material und den Zugangshinweis', async () => {
    show('/infrastruktur/3', ['infrastructure.view', 'material.view'])
    expect(await screen.findByRole('heading', { name: 'Schützenhaus' })).toBeInTheDocument()
    expect(screen.getByText(/Schlüsselkasten am Seiteneingang/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'INF-000004 · Luftgewehrstand' })).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'MAT-000005 · Schlüssel Haupteingang' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Bereich anlegen' })).not.toBeInTheDocument()
  })

  it('verlangt das Leserecht für Infrastruktur', async () => {
    show('/infrastruktur', ['material.view'])
    expect(await screen.findByText('Dafür fehlt dir die Berechtigung.')).toBeInTheDocument()
  })
})
