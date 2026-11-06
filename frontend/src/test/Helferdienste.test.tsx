import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const shift = {
  id: 31,
  starts_at: '2099-06-10T12:00:00Z',
  ends_at: '2099-06-10T16:00:00Z',
  needed: 2,
  note: '',
  taken: 1,
  assignments: [
    {
      id: 41,
      membership: 7,
      name: 'Anna Muster',
      external: false,
      origin: 'assigned',
      status: 'active',
      done: null,
      phone: '',
    },
  ],
}
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
  needed: 2,
  open: 1,
  note: '',
  duties: [
    {
      id: 21,
      name: 'Theke',
      description: '',
      location: 'Festzelt',
      min_age: 18,
      position: 0,
      shifts: [shift],
    },
  ],
}

function show(permissions: string[], path = '/helferdienste', overlap = false) {
  let calls = 0
  const api = fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['helpers'], permissions })],
    }),
    'GET /api/orgs/7/helpers/': () => ({ status: 200, body: [plan] }),
    'GET /api/orgs/7/helpers/5/': () => ({ status: 200, body: plan }),
    'GET /api/orgs/7/helpers/events/': () => ({ status: 200, body: [] }),
    'POST /api/orgs/7/helpers/duties/21/shifts/': () => ({ status: 201, body: [] }),
    'POST /api/orgs/7/helpers/shifts/31/assignments/': () => {
      calls += 1
      if (overlap && calls === 1)
        return {
          status: 400,
          body: { detail: ['Überschneidet sich mit Kasse.'], warnings: ['overlap'] },
        }
      return { status: 201, body: { ...shift.assignments[0], id: 42, name: 'Gerd Gast' } }
    },
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

describe('Helferdienste', () => {
  it('zeigt Dienstpläne mit offenen Plätzen', async () => {
    show(['helpers.view'])
    expect(
      await screen.findByRole('heading', { name: 'Helferdienste', level: 1 }),
    ).toBeInTheDocument()
    expect(await screen.findByText('Schützenfest 2099')).toBeInTheDocument()
    expect(screen.getByText('1 von 2')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Neuer Dienstplan' })).not.toBeInTheDocument()
  })

  it('legt Schichten per Schnelleingabe an', async () => {
    const api = show(['helpers.view', 'helpers.edit'], '/helferdienste?plan=5')
    const form = await screen.findByRole('form', { name: 'Schichten für Theke anlegen' })
    fireEvent.change(within(form).getByLabelText('Tag'), { target: { value: '2099-06-11' } })
    fireEvent.change(within(form).getByLabelText('Zeiten'), {
      target: { value: '14-18, 18-22' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Schichten anlegen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/helpers/duties/21/shifts/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/orgs/7/helpers/duties/21/shifts/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      day: '2099-06-11',
      quick: '14-18, 18-22',
      needed: 2,
    })
  })

  it('teilt Externe nach Rückfrage trotzdem ein', async () => {
    const api = show(['helpers.view', 'helpers.edit'], '/helferdienste?plan=5', true)
    fireEvent.click(await screen.findByRole('button', { name: /^Person einteilen:/ }))
    const form = screen.getByRole('form', { name: /^Einteilen:/ })
    fireEvent.click(within(form).getByRole('button', { name: 'Externe Person' }))
    fireEvent.change(within(form).getByLabelText('Name'), { target: { value: 'Gerd Gast' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Einteilen' }))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Trotzdem einteilen' }))
    await waitFor(() =>
      expect(
        api.filter((c) => c.key === 'POST /api/orgs/7/helpers/shifts/31/assignments/').length,
      ).toBe(2),
    )
    const last = api.filter((c) => c.key === 'POST /api/orgs/7/helpers/shifts/31/assignments/')[1]
    expect(JSON.parse(String(last.init?.body))).toMatchObject({ name: 'Gerd Gast', force: true })
  })

  it('ohne Recht kein Zugang', async () => {
    show(['events.view'])
    expect(await screen.findByText('Dafür fehlt dir die Berechtigung.')).toBeInTheDocument()
  })
})
