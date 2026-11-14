import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { forgetPlaces } from '../components/places.ts'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

interface Row {
  id: number
  parent: number | null
  name: string
  address: string
  directions: string
  own: boolean
  owner: string | null
  can_edit: boolean
}

// Wie die Schnittstelle: Räume mit „Gebäude, Raum“ und Anschrift des Gebäudes
function place(row: Row, building?: Row) {
  const full = building ? `${building.name}, ${row.name}` : row.name
  return {
    latitude: null,
    longitude: null,
    is_active: true,
    ...row,
    full_name: full,
    pick: {
      name: full,
      address: building ? building.address : row.address,
      directions: [building?.directions, row.directions].filter(Boolean).join('\n'),
      latitude: null,
      longitude: null,
    },
  }
}

const schuetzenhaus = place({
  id: 1,
  parent: null,
  name: 'Schützenhaus',
  address: 'Musterweg 1, 12345 Musterstadt',
  directions: 'Parkplatz hinter der Halle',
  own: true,
  owner: null,
  can_edit: true,
})
const saal = place(
  {
    id: 3,
    parent: 1,
    name: 'Saal',
    address: '',
    directions: 'Eingang über den Hof',
    own: true,
    owner: null,
    can_edit: true,
  },
  schuetzenhaus,
)
const festplatz = place({
  id: 2,
  parent: null,
  name: 'Bundesfestplatz',
  address: 'Am Rhein 5',
  directions: '',
  own: false,
  owner: 'Testbund',
  can_edit: false,
})

const plan = {
  id: 5,
  title: 'Schützenfest 2099',
  event: null,
  event_title: '',
  event_starts_at: null,
  status: 'draft',
  signup: 'self',
  cancel_days: 2,
  max_shifts: null,
  show_names: true,
  version: 1,
  can_edit: true,
  can_callout: true,
  needed: 0,
  open: 0,
  note: '',
  duties: [],
}

function show(path: string, permissions: string[], routes = {}) {
  const api = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['helpers', 'events'], permissions })],
    }),
    'GET /api/orgs/7/places/': () => ({
      status: 200,
      body: { places: [schuetzenhaus, saal, festplatz], can_edit: true, can_manage: true },
    }),
    'GET /api/orgs/7/places/?alle=1': () => ({
      status: 200,
      body: { places: [schuetzenhaus, saal, festplatz], can_edit: true, can_manage: true },
    }),
    'GET /api/orgs/7/places/suggestions/': () => ({
      status: 200,
      body: [{ name: 'Schießstand', address: 'Waldweg 3', count: 4 }],
    }),
    'POST /api/orgs/7/places/': (init?: RequestInit) => {
      const data = JSON.parse(String(init?.body ?? '{}'))
      const row = { ...schuetzenhaus, id: 9, parent: null, directions: '', ...data }
      return { status: 201, body: place(row, row.parent ? schuetzenhaus : undefined) }
    },
    'GET /api/orgs/7/helpers/': () => ({ status: 200, body: [plan] }),
    'GET /api/orgs/7/helpers/5/': () => ({ status: 200, body: plan }),
    'GET /api/orgs/7/helpers/events/': () => ({ status: 200, body: [] }),
    'GET /api/orgs/7/helpers/units/': () => ({ status: 200, body: [] }),
    ...routes,
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
  return api
}

describe('Orte', () => {
  beforeEach(() => forgetPlaces())

  it('zeigt eigene Orte, die des Dachverbands und übernimmt Vorschläge', async () => {
    const api = show('/einstellungen/orte', ['org.edit', 'events.manage'])
    expect(await screen.findByText('Schützenhaus')).toBeInTheDocument()
    expect(screen.getByText('Parkplatz hinter der Halle')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Orte von Testbund' })).toBeInTheDocument()
    const suggestions = (
      await screen.findByRole('heading', { name: 'Vorschläge aus bisherigen Einträgen' })
    ).closest('section')!
    expect(within(suggestions).getByText('4-mal verwendet')).toBeInTheDocument()
    fireEvent.click(within(suggestions).getByRole('button', { name: 'Übernehmen' }))
    await waitFor(() => expect(api.some((c) => c.key === 'POST /api/orgs/7/places/')).toBe(true))
    const call = api.find((c) => c.key === 'POST /api/orgs/7/places/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      name: 'Schießstand',
      address: 'Waldweg 3',
    })
    expect(await screen.findByText('Schießstand')).toBeInTheDocument()
  })

  it('bietet gespeicherte Orte im Formular an und speichert neue', async () => {
    const api = show('/helferdienste?plan=5', ['helpers.view', 'helpers.edit'])
    const field = await screen.findByLabelText('Ort')
    await waitFor(() => expect(field).toHaveAttribute('list'))
    const list = document.getElementById(field.getAttribute('list')!)!
    const options = Array.from(list.querySelectorAll('option')).map((o) => o.value)
    expect(options).toEqual(['Schützenhaus', 'Schützenhaus, Saal', 'Bundesfestplatz'])
    // Gespeicherter Ort: kein Knopf zum Speichern
    fireEvent.change(field, { target: { value: 'Schützenhaus' } })
    expect(screen.queryByRole('button', { name: 'Als Ort speichern' })).not.toBeInTheDocument()
    fireEvent.change(field, { target: { value: 'Festzelt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Als Ort speichern' }))
    expect(await screen.findByText('Ort „Festzelt“ gespeichert.')).toBeInTheDocument()
    const call = api.find((c) => c.key === 'POST /api/orgs/7/places/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({ name: 'Festzelt', address: '' })
  })

  it('zeigt Räume unter ihrem Ort und speichert neue Räume', async () => {
    const api = show('/einstellungen/orte', ['org.edit', 'events.manage'])
    const rooms = await screen.findByRole('list', { name: 'Räume in Schützenhaus' })
    expect(within(rooms).getByText('Saal')).toBeInTheDocument()
    expect(within(rooms).getByText('Eingang über den Hof')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Raum hinzufügen' }))
    fireEvent.change(within(rooms).getByLabelText('Raum'), { target: { value: 'Küche' } })
    fireEvent.click(within(rooms).getByRole('button', { name: 'Raum speichern' }))
    await waitFor(() => expect(api.some((c) => c.key === 'POST /api/orgs/7/places/')).toBe(true))
    const call = api.find((c) => c.key === 'POST /api/orgs/7/places/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      parent: 1,
      name: 'Küche',
      directions: '',
      is_active: true,
    })
    expect(await within(rooms).findByText('Küche')).toBeInTheDocument()
  })

  it('übernimmt beim Raum die Anschrift des Orts und speichert „Ort, Raum“ als Raum', async () => {
    const api = show('/helferdienste?plan=5', ['helpers.view', 'helpers.edit'])
    const field = await screen.findByLabelText('Ort')
    await waitFor(() => expect(field).toHaveAttribute('list'))
    const list = document.getElementById(field.getAttribute('list')!)!
    const room = Array.from(list.querySelectorAll('option')).find(
      (o) => o.value === 'Schützenhaus, Saal',
    )!
    expect(room.textContent).toBe('Musterweg 1, 12345 Musterstadt')
    fireEvent.change(field, { target: { value: 'Schützenhaus, Küche' } })
    fireEvent.click(screen.getByRole('button', { name: 'Als Raum speichern' }))
    expect(await screen.findByText('Raum „Schützenhaus, Küche“ gespeichert.')).toBeInTheDocument()
    const call = api.find((c) => c.key === 'POST /api/orgs/7/places/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({ parent: 1, name: 'Küche' })
  })

  it('nur mit Leserecht: kein Speichern', async () => {
    show('/helferdienste?plan=5', ['helpers.view', 'helpers.edit'], {
      'GET /api/orgs/7/places/': () => ({
        status: 200,
        body: { places: [schuetzenhaus], can_edit: false, can_manage: false },
      }),
    })
    const field = await screen.findByLabelText('Ort')
    fireEvent.change(field, { target: { value: 'Festzelt' } })
    await waitFor(() => expect(field).toHaveAttribute('list'))
    expect(screen.queryByRole('button', { name: 'Als Ort speichern' })).not.toBeInTheDocument()
  })
})
