import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
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

const portalEntry = {
  id: 5,
  club_id: 7,
  club_name: 'TV Beispielhausen',
  first_name: 'Erika',
  last_name: 'Muster',
  theme: testOrg().theme,
}

const request = {
  id: 3,
  member_id: 11,
  member_name: 'Erika Muster',
  exit_date: '2027-12-31',
  earliest_date: '2027-12-31',
  message: 'Umzug',
  status: 'pending',
  status_label: 'offen',
  response: '',
  created_at: '2026-11-12T20:00:00Z',
  decided_at: null,
}

const detail = (cancellation: object) => ({
  id: 11,
  last_name: 'Muster',
  first_name: 'Erika',
  birth_date: '1980-05-17',
  club_number: '42',
  member_type: 'aktiv',
  entry_date: '2015-01-01',
  departments: [],
  contact: null,
  status: 'active',
  contact_changes_need_approval: false,
  club: {
    name: 'TV Beispielhausen',
    street: '',
    postal_code: '',
    city: '',
    email: '',
    phone: '',
    website: '',
  },
  change_requests: [],
  cancellation,
})

const info = {
  enabled: true,
  possible: true,
  earliest_date: '2027-12-31',
  rule: 'mit einer Frist von 3 Monaten zum Ende des Geschäftsjahres',
  planned_exit: null,
  requests: [],
}

describe('Kündigung im Mitgliederbereich', () => {
  it('sendet die Kündigung mit dem frühesten Datum nach Rückfrage', async () => {
    let sent = false
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: { departments: [], portal: [portalEntry] },
      }),
      'GET /api/portal/5/': () => ({
        status: 200,
        body: detail(sent ? { ...info, possible: false, requests: [request] } : info),
      }),
      'POST /api/portal/5/cancellation/': () => {
        sent = true
        return { status: 201, body: request }
      },
    })
    renderApp('/mein-bereich/daten')
    expect(await screen.findByText(/heute also frühestens zum 31\.12\.2027/)).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Kündigen' }))
    expect(screen.getByLabelText('Austritt zum')).toHaveValue('2027-12-31')
    await user.click(screen.getByRole('button', { name: 'Kündigung absenden' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Kündigung absenden' }))
    expect(await screen.findByText(/Eingangsbestätigung per Mail/)).toBeInTheDocument()
    const call = calls.find((c) => c.key === 'POST /api/portal/5/cancellation/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      exit_date: '2027-12-31',
      message: '',
      confirm: true,
    })
    expect(await screen.findByRole('button', { name: 'Zurücknehmen' })).toBeInTheDocument()
  })

  it('zeigt nichts, wenn der Verein es nicht eingeschaltet hat', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/contexts/': () => ({
        status: 200,
        body: { departments: [], portal: [portalEntry] },
      }),
      'GET /api/portal/5/': () => ({
        status: 200,
        body: detail({ ...info, enabled: false, possible: false }),
      }),
    })
    renderApp('/mein-bereich/daten')
    expect(await screen.findByRole('button', { name: 'Daten ändern' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Mitgliedschaft kündigen' })).toBeNull()
  })
})

describe('Kündigungen im Verein', () => {
  it('bestätigt den Austritt', async () => {
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ permissions: ['members.view', 'members.edit'] })],
      }),
      'GET /api/orgs/7/cancellations/?status=pending': () => ({ status: 200, body: [request] }),
      'POST /api/orgs/7/cancellations/3/decide/': () => ({
        status: 200,
        body: { ...request, status: 'accepted', status_label: 'bestätigt' },
      }),
    })
    renderApp('/mitglieder/anfragen/kuendigungen')
    expect(await screen.findByRole('link', { name: 'Erika Muster' })).toBeInTheDocument()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Austritt bestätigen' }))
    const dialog = await screen.findByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: 'Austritt bestätigen' }))
    await screen.findByRole('link', { name: 'Erika Muster' })
    const call = calls.find((c) => c.key === 'POST /api/orgs/7/cancellations/3/decide/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({ accept: true, response: '' })
  })
})
