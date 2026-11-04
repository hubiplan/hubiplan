import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const item = {
  id: 1,
  inventory_number: 'MAT-000001',
  title: 'Beamer',
  description: 'Im schwarzen Koffer',
  purpose: 'Präsentationen',
  location_kind: 'address',
  member: null,
  member_name: '',
  address: {
    street: 'Musterweg 1',
    postal_code: '12345',
    city: 'Musterstadt',
    country: 'Deutschland',
  },
  location_note: '',
  condition: 'ready',
  condition_note: '',
  version: 2,
  deleted_at: null,
  location_review: false,
  photo_url: null,
  events: [],
  todos: [],
  documents: [],
  uses: [],
}

function setup(path: string, permissions = ['material.view', 'material.edit']) {
  const calls = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['material'], permissions })],
    }),
    'GET /api/orgs/7/materials/?': () => ({
      status: 200,
      body: {
        items: [item],
        count: 1,
        page: 1,
        can_edit: permissions.includes('material.edit'),
      },
    }),
    'GET /api/orgs/7/materials/1/': () => ({ status: 200, body: item }),
    'GET /api/orgs/7/materials/1/history/': () => ({ status: 200, body: [] }),
    'POST /api/orgs/7/materials/': () => ({ status: 201, body: item }),
    'GET /api/orgs/7/todos/': () => ({ status: 200, body: { items: [] } }),
    'POST /api/orgs/7/todos/': (init) => ({
      status: 201,
      body: {
        ...JSON.parse(String(init?.body)),
        id: 9,
        version: 1,
        status: 'open',
        can_edit: false,
        can_delete: false,
        shared: false,
      },
    }),
    'POST /api/orgs/7/materials/1/photo/': () => ({ status: 200, body: item }),
    'DELETE /api/orgs/7/materials/1/': () => ({
      status: 409,
      body: {
        detail: 'Das Material wurde inzwischen geändert. Bitte neu laden.',
      },
    }),
    'GET /api/orgs/7/materials/choices/?kind=todo&q=': () => ({
      status: 200,
      body: { items: [] },
    }),
    'GET /api/orgs/7/materials/choices/?kind=document&q=': () => ({
      status: 200,
      body: { items: [] },
    }),
    'GET /api/orgs/7/materials/choices/?kind=event&q=': () => ({
      status: 200,
      body: { items: [] },
    }),
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

describe('Materialverwaltung', () => {
  it('übernimmt den Materialbezug in den neuen Aufgabendialog', async () => {
    window.history.replaceState(null, '', '/aufgaben?neu=1&material=1')
    try {
      const calls = setup('/aufgaben?neu=1&material=1', [
        'material.view',
        'material.edit',
        'todos.view',
      ])
      const user = userEvent.setup()
      await user.type(await screen.findByLabelText('Titel'), 'Beamer abholen')
      await user.click(screen.getByRole('button', { name: 'Anlegen' }))
      await waitFor(() => expect(calls.some((c) => c.key === 'POST /api/orgs/7/todos/')).toBe(true))
      const payload = JSON.parse(
        String(calls.find((c) => c.key === 'POST /api/orgs/7/todos/')?.init?.body),
      )
      expect(payload).toMatchObject({ title: 'Beamer abholen', material: 1 })
      expect(await screen.findByRole('dialog', { name: 'Aufgabe angelegt' })).toBeInTheDocument()
    } finally {
      window.history.replaceState(null, '', '/')
    }
  })

  it('zeigt Material auch mit reinem Leserecht ohne Bearbeitungsaktionen', async () => {
    setup('/material/1', ['material.view'])
    expect(await screen.findByRole('heading', { name: 'Beamer' })).toBeInTheDocument()
    expect(screen.getByText('Musterweg 1, 12345, Musterstadt, Deutschland')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Bearbeiten' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Bild hinzufügen oder ersetzen')).not.toBeInTheDocument()
  })

  it('legt ein Teil mit Freitext und Adresse an', async () => {
    const calls = setup('/material/neu')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText('Bezeichnung'), 'Beamer')
    await user.type(screen.getByLabelText('Kurzbeschreibung'), 'Im schwarzen Koffer')
    await user.type(screen.getByLabelText('Verwendungszweck'), 'Präsentationen')
    await user.type(screen.getByLabelText('Straße und Hausnummer'), 'Musterweg 1')
    await user.type(screen.getByLabelText('Postleitzahl'), '12345')
    await user.type(screen.getByLabelText('Ort'), 'Musterstadt')
    await user.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/orgs/7/materials/')).toBe(true),
    )
    const payload = JSON.parse(
      String(calls.find((c) => c.key === 'POST /api/orgs/7/materials/')?.init?.body),
    )
    expect(payload).toMatchObject({
      title: 'Beamer',
      location_kind: 'address',
      member: null,
      address: { city: 'Musterstadt' },
    })
    expect(await screen.findByRole('heading', { name: 'Beamer' })).toBeInTheDocument()
  })

  it('lädt ein Materialfoto mit der aktuellen Version hoch', async () => {
    const calls = setup('/material/1')
    const user = userEvent.setup()
    const input = await screen.findByLabelText('Bild hinzufügen oder ersetzen')
    await user.upload(input, new File(['photo'], 'beamer.png', { type: 'image/png' }))
    await waitFor(() =>
      expect(calls.some((c) => c.key === 'POST /api/orgs/7/materials/1/photo/')).toBe(true),
    )
    const form = calls.find((c) => c.key === 'POST /api/orgs/7/materials/1/photo/')?.init
      ?.body as FormData
    expect(form.get('version')).toBe('2')
    expect((form.get('file') as File).name).toBe('beamer.png')
  })

  it('bleibt bei einem Löschkonflikt auf dem Material und zeigt den Fehler', async () => {
    setup('/material/1')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'In den Papierkorb' }))
    expect(
      await screen.findByText('Das Material wurde inzwischen geändert. Bitte neu laden.'),
    ).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Beamer' })).toBeInTheDocument()
  })
})
