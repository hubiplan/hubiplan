import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const kind = {
  id: 1,
  name: 'Jahreshauptversammlung',
  base: 'general',
  invite_days: 14,
  invite_form: 'mail',
  voter_types: [],
  voter_min_age: null,
  quorum_percent: null,
  quorum_count: null,
  proxies_allowed: false,
  minutes_for: 'voters',
  position: 0,
  active: true,
  used: true,
}
const meeting = {
  id: 5,
  kind: 1,
  kind_name: 'Jahreshauptversammlung',
  base: 'general',
  title: 'Jahreshauptversammlung 2099',
  starts_at: '2099-01-15T18:00:00Z',
  ends_at: '2099-01-15T21:00:00Z',
  location: 'Schützenhaus',
  address: '',
  event: 40,
  status: 'draft',
  invite_by: '2099-01-01',
  version: 3,
  can_edit: true,
  chair: '',
  minute_taker: '',
  note: '',
  agenda: [
    { id: 11, position: 1, title: 'Begrüßung', description: '', type: 'other' },
    { id: 12, position: 2, title: 'Kassenbericht', description: '', type: 'report' },
  ],
}

function show(permissions: string[], path = '/versammlungen') {
  const api = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['meetings'], permissions })],
    }),
    'GET /api/orgs/7/meetings/': () => ({ status: 200, body: [meeting] }),
    'GET /api/orgs/7/meetings/kinds/': () => ({ status: 200, body: [kind] }),
    'GET /api/orgs/7/meetings/5/': () => ({ status: 200, body: meeting }),
    'PUT /api/orgs/7/meetings/5/agenda/': () => ({
      status: 200,
      body: { ...meeting, version: 4 },
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
  return api
}

describe('Versammlungen', () => {
  it('zeigt anstehende Versammlungen', async () => {
    show(['meetings.view'])
    expect(
      await screen.findByRole('heading', { name: 'Versammlungen', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Jahreshauptversammlung 2099')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neue Versammlung' })).not.toBeInTheDocument()
  })

  it('ändert die Reihenfolge der Tagesordnung', async () => {
    const api = show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5')
    const agenda = (await screen.findByRole('heading', { name: 'Tagesordnung' })).closest('form')!
    expect(within(agenda).getByDisplayValue('Begrüßung')).toBeInTheDocument()
    fireEvent.click(within(agenda).getByRole('button', { name: 'TOP 2 nach oben' }))
    fireEvent.click(within(agenda).getByRole('button', { name: 'Tagesordnung speichern' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'PUT /api/orgs/7/meetings/5/agenda/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'PUT /api/orgs/7/meetings/5/agenda/')!
    const body = JSON.parse(String(call.init?.body))
    expect(body.version).toBe(3)
    expect(body.items.map((i: { title: string }) => i.title)).toEqual([
      'Kassenbericht',
      'Begrüßung',
    ])
  })

  it('ohne Recht kein Zugang', async () => {
    show(['events.view'])
    expect(await screen.findByText('Dafür fehlt dir die Berechtigung.')).toBeInTheDocument()
  })
})
