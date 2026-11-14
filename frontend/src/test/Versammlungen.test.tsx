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
  can_invite: true,
  invited_at: null,
  circular: null,
  circular_status: '',
  chair: '',
  minute_taker: '',
  note: '',
  can_attendance: true,
  agenda: [
    { id: 11, position: 1, title: 'Begrüßung', description: '', type: 'other' },
    { id: 12, position: 2, title: 'Kassenbericht', description: '', type: 'report' },
  ],
}

const attendance = {
  voters: 3,
  present: 1,
  represented: 0,
  guests: 0,
  quorum: { needed: 2, reached: false, rule: true },
  proxies_allowed: false,
  editable: true,
  rows: [
    {
      id: 91,
      membership: 31,
      name: 'Anna Muster',
      voter: true,
      status: 'present',
      represented_by: null,
    },
    {
      id: null,
      membership: 32,
      name: 'Bernd Beispiel',
      voter: true,
      status: '',
      represented_by: null,
    },
    {
      id: null,
      membership: 33,
      name: 'Carla Probe',
      voter: true,
      status: '',
      represented_by: null,
    },
    {
      id: null,
      membership: 34,
      name: 'Musterbau GmbH',
      kind: 'organization',
      voter: true,
      status: '',
      represented_by: null,
      delegates: [{ id: 5, name: 'Erika Muster', function: 'Geschäftsführerin', membership: null }],
    },
  ],
}

function show(permissions: string[], path = '/versammlungen', current: object = meeting) {
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
    'GET /api/orgs/7/meetings/5/': () => ({ status: 200, body: current }),
    'POST /api/orgs/7/meetings/5/minutes/confirm/': () => ({
      status: 200,
      body: {
        ...current,
        version: 10,
        chair_confirmed: { name: 'Erika Vorsitz', at: '2099-01-16T10:00:00Z' },
      },
    }),
    'PUT /api/orgs/7/meetings/5/minutes/': () => ({
      status: 200,
      body: { ...current, version: 9 },
    }),
    'POST /api/orgs/7/meetings/5/invitation/': () => ({
      status: 200,
      body: { ...meeting, version: 4, circular: 77, circular_status: 'draft' },
    }),
    'GET /api/orgs/7/meetings/5/attendance/': () => ({ status: 200, body: attendance }),
    'POST /api/orgs/7/meetings/5/attendance/': () => ({
      status: 200,
      body: {
        ...attendance,
        present: 2,
        quorum: { needed: 2, reached: true, rule: true },
        rows: attendance.rows.map((r) =>
          r.membership === 32 ? { ...r, id: 92, status: 'present' } : r,
        ),
      },
    }),
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

  it('legt Unterpunkte an und hängt Punkte um', async () => {
    const api = show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5')
    const agenda = (await screen.findByRole('heading', { name: 'Tagesordnung' })).closest('form')!
    fireEvent.click(within(agenda).getAllByRole('button', { name: 'Unterpunkt hinzufügen' })[1])
    fireEvent.change(within(agenda).getByLabelText('TOP 2.1'), {
      target: { value: 'Wahl der Kassenprüfer' },
    })
    // TOP 2 unter TOP 1 hängen: TOP 2 und sein Unterpunkt werden 1.1 und 1.2
    fireEvent.change(within(agenda).getAllByLabelText('Gehört zu')[0], {
      target: { value: 'id-11' },
    })
    expect(within(agenda).getByLabelText('TOP 1.1')).toHaveValue('Kassenbericht')
    expect(within(agenda).getByLabelText('TOP 1.2')).toHaveValue('Wahl der Kassenprüfer')
    fireEvent.click(within(agenda).getByRole('button', { name: 'Tagesordnung speichern' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'PUT /api/orgs/7/meetings/5/agenda/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'PUT /api/orgs/7/meetings/5/agenda/')!
    const body = JSON.parse(String(call.init?.body))
    expect(body.items.map((i: { title: string; level: number }) => [i.title, i.level])).toEqual([
      ['Begrüßung', 0],
      ['Kassenbericht', 1],
      ['Wahl der Kassenprüfer', 1],
    ])
    expect(body.items[0]).not.toHaveProperty('key')
  })

  it('auf einen Punkt gezogen wird zum Unterpunkt', async () => {
    show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5')
    const agenda = (await screen.findByRole('heading', { name: 'Tagesordnung' })).closest('form')!
    const rows = agenda.querySelectorAll<HTMLElement>('.agenda-row')
    rows.forEach((el, i) => {
      el.getBoundingClientRect = () =>
        ({ top: i * 100, bottom: i * 100 + 100, height: 100, left: 0, right: 500 }) as DOMRect
    })
    const handle = within(agenda).getByRole('button', { name: 'TOP 2 verschieben' })
    fireEvent.pointerDown(handle, { button: 0, clientX: 10, clientY: 150, pointerId: 1 })
    fireEvent.pointerMove(handle, { clientX: 10, clientY: 50, pointerId: 1 })
    expect(rows[0]).toHaveClass('agenda-drop-onto')
    fireEvent.pointerUp(handle, { clientX: 10, clientY: 50, pointerId: 1 })
    expect(within(agenda).getByLabelText('TOP 1.1')).toHaveValue('Kassenbericht')
  })

  it('bereitet die Einladung als Rundschreiben vor', async () => {
    const api = show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5')
    fireEvent.click(await screen.findByRole('button', { name: 'Einladung vorbereiten' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/meetings/5/invitation/')).toBe(true),
    )
  })

  it('erfasst die Anwesenheit und zeigt die Beschlussfähigkeit', async () => {
    const api = show(
      ['meetings.view', 'meetings.edit', 'members.view'],
      '/versammlungen?versammlung=5',
    )
    expect(
      await screen.findByText('Noch nicht beschlussfähig: 1 Stimmen, nötig sind 2.'),
    ).toBeInTheDocument()
    const bernd = screen.getByRole('group', { name: 'Bernd Beispiel' })
    expect(within(bernd).queryByRole('button', { name: 'Vertreten' })).not.toBeInTheDocument()
    fireEvent.click(within(bernd).getByRole('button', { name: 'Anwesend' }))
    expect(await screen.findByText('Beschlussfähig: 2 Stimmen, nötig sind 2.')).toBeInTheDocument()
    const call = api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/attendance/')!
    expect(JSON.parse(String(call.init?.body))).toMatchObject({ membership: 32, status: 'present' })
  })

  it('Organisation ist durch Vertreter anwesend', async () => {
    const api = show(
      ['meetings.view', 'meetings.edit', 'members.view'],
      '/versammlungen?versammlung=5',
    )
    const firma = await screen.findByRole('group', { name: 'Musterbau GmbH' })
    expect(within(firma).queryByRole('button', { name: 'Anwesend' })).not.toBeInTheDocument()
    fireEvent.click(within(firma).getByRole('button', { name: 'Durch Vertreter' }))
    fireEvent.change(await screen.findByLabelText('Vertreter'), { target: { value: '5' } })
    await waitFor(() =>
      expect(api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/attendance/')).toBeTruthy(),
    )
    const call = api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/attendance/')!
    expect(JSON.parse(String(call.init?.body))).toMatchObject({
      membership: 34,
      status: 'delegate',
      delegate: 5,
    })
  })

  it('schreibt das Protokoll mit Beschluss', async () => {
    const held = { ...meeting, status: 'held', version: 8 }
    const api = show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5', held)
    const form = (
      await screen.findByRole('heading', { name: 'Protokoll der Versammlung' })
    ).closest('form')!
    fireEvent.change(within(form).getByLabelText('Protokoll zu TOP 2'), {
      target: { value: 'Bericht vorgetragen.' },
    })
    fireEvent.click(within(form).getAllByRole('button', { name: 'Beschluss hinzufügen' })[1])
    fireEvent.change(within(form).getByLabelText('Beschlusstext'), {
      target: { value: 'Entlastung des Vorstands.' },
    })
    fireEvent.click(within(form).getByLabelText('einstimmig'))
    fireEvent.click(within(form).getByRole('button', { name: 'Protokoll speichern' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'PUT /api/orgs/7/meetings/5/minutes/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'PUT /api/orgs/7/meetings/5/minutes/')!
    const body = JSON.parse(String(call.init?.body))
    expect(body.version).toBe(8)
    expect(body.items[1]).toMatchObject({
      id: 12,
      minutes: 'Bericht vorgetragen.',
      resolutions: [{ text: 'Entlastung des Vorstands.', unanimous: true, result: 'accepted' }],
    })
  })

  it('bestätigt das Protokoll als Leitung', async () => {
    const minutes = {
      ...meeting,
      status: 'minutes',
      version: 9,
      chair: 'Erika Vorsitz',
      minute_taker: 'Max Schrift',
      chair_confirmed: null,
      taker_confirmed: null,
    }
    const api = show(['meetings.view', 'meetings.edit'], '/versammlungen?versammlung=5', minutes)
    fireEvent.click(await screen.findByRole('button', { name: 'Als Leitung bestätigen' }))
    const dialog = await screen.findByRole('alertdialog')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Bestätigen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/meetings/5/minutes/confirm/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/minutes/confirm/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({ version: 9, role: 'chair' })
    expect(screen.getByRole('button', { name: 'Vorschau als PDF' })).toBeInTheDocument()
  })

  it('ohne Recht kein Zugang', async () => {
    show(['events.view'])
    expect(await screen.findByText('Dafür fehlt dir die Berechtigung.')).toBeInTheDocument()
  })
})
