import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const rules = {
  enabled: true,
  approval: true,
  buffer_before: 0,
  buffer_after: 30,
  horizon_days: 365,
  website: 'off',
}
const item = (id: number, title: string, facility: number | null) => ({
  id,
  kind: 'facility',
  inventory_number: `INF-00000${id}`,
  title,
  facility,
  facility_type: facility ? 'room' : 'building',
  condition: 'ready',
  rules,
  can_book: true,
  can_manage: true,
})
const request = {
  id: 9,
  item: 4,
  item_title: 'Saal',
  title: 'Geburtstag',
  details: true,
  note: '',
  starts_at: '2026-11-06T17:00:00Z',
  ends_at: '2026-11-06T21:00:00Z',
  all_day: false,
  repeat: 'none',
  repeat_interval: 1,
  repeat_until: null,
  status: 'requested',
  visibility: 'members',
  contact: {},
  event: null,
  event_title: '',
  competition: null,
  competition_title: '',
  needs_review: false,
  own: false,
  booked_by: 'Erika Beispiel',
  can_manage: true,
  can_cancel: true,
  version: 1,
  loan: false,
  handed_out_at: null,
  handed_out_by: '',
  returned_at: null,
  returned_by: '',
  exceptions: [],
}

function show(
  permissions: string[],
  extra: Parameters<typeof fakeApi>[0] = {},
  more: object[] = [],
) {
  const api = fakeApi({
    ...extra,
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ modules: ['infrastructure', 'bookings'], permissions })],
    }),
    'GET /api/orgs/7/bookings/items/': () => ({
      status: 200,
      body: { items: [item(3, 'Schützenhaus', null), item(4, 'Saal', 3)], can_manage_all: true },
    }),
    'GET /api/orgs/7/bookings/?start=2026-11-02&end=2026-11-09': () => ({
      status: 200,
      body: {
        occurrences: [
          {
            booking: 8,
            item: 3,
            item_title: 'Schützenhaus',
            title: 'Jahreshauptversammlung',
            starts_at: '2026-11-04T18:00:00Z',
            ends_at: '2026-11-04T21:00:00Z',
            original_start: '2026-11-04T18:00:00Z',
            all_day: false,
            status: 'confirmed',
            series: false,
            own: false,
            needs_review: false,
          },
          ...more,
        ],
        requests: [request],
      },
    }),
    'POST /api/orgs/7/bookings/9/decision/': () => ({
      status: 200,
      body: { ...request, status: 'confirmed', version: 2 },
    }),
  })
  render(
    <MemoryRouter initialEntries={['/belegung?ab=2026-11-04']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
  return api
}

describe('Belegung', () => {
  it('zeigt die Woche und belegt mit dem Gebäude auch den Bereich', async () => {
    show(['infrastructure.view', 'infrastructure.edit'])
    expect(await screen.findByRole('heading', { name: 'Belegung', level: 1 })).toBeInTheDocument()
    const table = await screen.findByRole('table')
    const hall = within(table).getByRole('row', { name: /Saal/ })
    expect(await within(hall).findByText('Jahreshauptversammlung')).toBeInTheDocument()
    const house = within(table).getByRole('row', { name: /Schützenhaus/ })
    expect(within(house).getByText('Jahreshauptversammlung')).toBeInTheDocument()
  })

  it('gibt eine offene Anfrage frei', async () => {
    const api = show(['infrastructure.view', 'infrastructure.edit'])
    expect(await screen.findByRole('heading', { name: 'Offene Anfragen' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Bestätigen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/bookings/9/decision/')).toBe(true),
    )
  })

  it('verlangt ein Leserecht', async () => {
    show(['members.view'])
    expect(
      await screen.findByRole('heading', { name: 'Kein Zugriff in dieser Einheit' }),
    ).toBeInTheDocument()
  })

  it('bestätigt die Ausgabe einer Ausleihe', async () => {
    const loan = {
      ...request,
      id: 11,
      item: 6,
      item_title: 'Beamer',
      title: 'Vortrag',
      status: 'confirmed',
      loan: true,
    }
    const api = show(
      ['infrastructure.view', 'infrastructure.edit'],
      {
        'GET /api/orgs/7/bookings/11/': () => ({ status: 200, body: loan }),
        'POST /api/orgs/7/bookings/11/handover/': () => ({
          status: 200,
          body: { ...loan, version: 2, handed_out_at: '2026-11-06T08:00:00Z' },
        }),
      },
      [
        {
          booking: 11,
          item: 3,
          item_title: 'Schützenhaus',
          title: 'Vortrag',
          starts_at: '2026-11-05T08:00:00Z',
          ends_at: '2026-11-05T10:00:00Z',
          original_start: '2026-11-05T08:00:00Z',
          all_day: false,
          status: 'confirmed',
          series: false,
          own: false,
          needs_review: false,
        },
      ],
    )
    fireEvent.click((await screen.findAllByRole('button', { name: /Vortrag/ }))[0])
    fireEvent.click(await screen.findByRole('button', { name: 'Ausgabe bestätigen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/bookings/11/handover/')).toBe(true),
    )
  })
})

describe('Belegung: Monat, Jahr und Mitglied', () => {
  const occurrence = {
    booking: 8,
    item: 4,
    item_title: 'Saal',
    title: 'Geburtstag',
    starts_at: '2026-11-20T17:00:00Z',
    ends_at: '2026-11-20T21:00:00Z',
    original_start: '2026-11-20T17:00:00Z',
    all_day: false,
    status: 'confirmed',
    series: false,
    own: false,
    needs_review: false,
    member_name: 'Beispiel, Erika',
  }
  const listed = { status: 200, body: { occurrences: [occurrence], requests: [] } }

  it('schaltet auf Monat und Jahr um', async () => {
    const api = show(['infrastructure.view', 'infrastructure.edit'], {
      'GET /api/orgs/7/bookings/?start=2026-11-01&end=2026-12-01': () => listed,
      'GET /api/orgs/7/bookings/?start=2026-01-01&end=2027-01-01': () => listed,
    })
    fireEvent.click(await screen.findByRole('button', { name: 'Monat' }))
    expect(await screen.findByRole('heading', { name: 'November 2026' })).toBeInTheDocument()
    const chip = await screen.findByRole('button', { name: 'Geburtstag' })
    expect(chip).toHaveAttribute('title', expect.stringContaining('Beispiel, Erika'))
    expect(screen.getByRole('button', { name: 'Nächster Monat' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Jahr' }))
    expect(await screen.findByRole('heading', { name: '2026' })).toBeInTheDocument()
    const hall = within(await screen.findByRole('table')).getByRole('row', { name: /Saal/ })
    fireEvent.click(await within(hall).findByRole('button', { name: '1 Tag' }))
    expect(await screen.findByRole('heading', { name: 'November 2026' })).toBeInTheDocument()
    expect(api.some((c) => c.key.includes('start=2026-01-01&end=2027-01-01'))).toBe(true)
  })

  it('bucht für ein Mitglied ohne Kontaktdaten', async () => {
    const api = show(['infrastructure.view', 'infrastructure.edit', 'members.view'], {
      'GET /api/orgs/7/bookings/choices/?kind=member&q=Bei': () => ({
        status: 200,
        body: { items: [{ id: 17, title: 'Beispiel, Erika' }], more: false },
      }),
      'POST /api/orgs/7/bookings/': () => ({
        status: 201,
        body: { ...request, id: 12, status: 'confirmed', member: 17 },
      }),
    })
    const user = userEvent.setup()
    fireEvent.click(await screen.findByRole('button', { name: 'Buchen' }))
    const group = await screen.findByRole('group', { name: 'Für ein Mitglied (optional)' })
    await user.type(within(group).getByRole('searchbox'), 'Bei')
    await user.click(await within(group).findByRole('button', { name: 'Beispiel, Erika' }))
    expect(within(group).getByText('Beispiel, Erika')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'Externe Buchung (optional)' })).toBeNull()
    fireEvent.change(screen.getByLabelText('Zweck'), { target: { value: 'Geburtstag' } })
    fireEvent.change(screen.getByLabelText('Beginn'), { target: { value: '2026-11-20T18:00' } })
    fireEvent.change(screen.getByLabelText('Ende'), { target: { value: '2026-11-20T22:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))
    await waitFor(() => expect(api.some((c) => c.key === 'POST /api/orgs/7/bookings/')).toBe(true))
    const body = JSON.parse(
      String(api.find((c) => c.key === 'POST /api/orgs/7/bookings/')!.init!.body),
    )
    expect(body.member).toBe(17)
    expect(body.contact).toBeUndefined()
  })
})

describe('Material & Räume in der Seitenleiste', () => {
  it('zeigt Räume und Anlagen und Belegung unter einem Punkt', async () => {
    show(['infrastructure.view'])
    await screen.findByRole('heading', { name: 'Belegung', level: 1 })
    const nav = screen.getByRole('navigation', { name: 'Hauptmenü' })
    // Hauptpunkt und Unterpunkt heißen gleich, wenn nur Räume eingeschaltet sind
    for (const link of within(nav).getAllByRole('link', { name: 'Räume und Anlagen' }))
      expect(link).toHaveAttribute('href', '/infrastruktur')
    expect(within(nav).getByRole('link', { name: 'Belegung' })).toHaveAttribute('href', '/belegung')
    expect(within(nav).queryByRole('link', { name: 'Material' })).toBeNull()
  })
})
