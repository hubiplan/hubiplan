import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalMeetings } from '../pages/portal/PortalMeetings.tsx'
import { ResolutionBook } from '../pages/meetings/ResolutionBook.tsx'
import { fakeApi } from './fakeApi.ts'

const row = {
  id: 7,
  number: '2099/01',
  kind: 'resolution',
  text: 'Der Beitrag steigt auf 60 Euro.',
  result: 'accepted',
  votes_yes: 40,
  votes_no: 3,
  votes_abstain: 1,
  unanimous: false,
  office: '',
  elected_name: '',
  status: 'open',
  meeting: 5,
  meeting_title: 'Jahreshauptversammlung 2099',
  meeting_kind: 1,
  meeting_kind_name: 'Jahreshauptversammlung',
  date: '2099-01-15',
  agenda_title: 'Beiträge',
  has_todo: false,
  todo: null,
}
const BASE = '/api/orgs/7/meetings/'

describe('Beschlussbuch', () => {
  it('filtert, ändert den Stand und legt eine Aufgabe an', async () => {
    let todo = false
    const book = () => ({
      status: 200,
      body: {
        rows: [
          todo
            ? { ...row, has_todo: true, todo: { id: 3, title: 'Umsetzen', status: 'open' } }
            : row,
        ],
        years: [2099],
        can_todo: true,
      },
    })
    const api = fakeApi({
      [`GET ${BASE}resolutions/`]: book,
      [`GET ${BASE}resolutions/?typ=election`]: () => ({
        status: 200,
        body: { rows: [], years: [2099], can_todo: true },
      }),
      [`PATCH ${BASE}resolutions/7/`]: () => ({ status: 200, body: { ...row, status: 'done' } }),
      [`POST ${BASE}resolutions/7/todo/`]: () => {
        todo = true
        return { status: 201, body: row }
      },
    })
    render(
      <MemoryRouter>
        <ResolutionBook base={BASE} canEdit kinds={[]} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Der Beitrag steigt auf 60 Euro.')).toBeInTheDocument()
    expect(screen.getByText('Ja 40 · Nein 3 · Enthaltung 1')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Stand von Beschluss 2099/01'), {
      target: { value: 'done' },
    })
    await waitFor(() => expect(api.some((c) => c.key === `PATCH ${BASE}resolutions/7/`)).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Beschluss 2099/01 als Aufgabe anlegen' }))
    expect(await screen.findByText('Aufgabe: Umsetzen')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Beschluss oder Wahl'), {
      target: { value: 'election' },
    })
    expect(await screen.findByText('Keine Beschlüsse gefunden.')).toBeInTheDocument()
  })

  it('ohne Bearbeitungsrecht nur lesen', async () => {
    fakeApi({
      [`GET ${BASE}resolutions/`]: () => ({
        status: 200,
        body: { rows: [{ ...row, status: 'repealed' }], years: [2099], can_todo: false },
      }),
    })
    render(
      <MemoryRouter>
        <ResolutionBook base={BASE} canEdit={false} kinds={[]} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('aufgehoben')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: /^Stand von/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /als Aufgabe anlegen/ })).not.toBeInTheDocument()
  })
})

describe('Versammlungen im Mitgliederbereich', () => {
  it('zeigt Einladung mit Tagesordnung und Protokolle', async () => {
    fakeApi({
      'GET /api/portal/9/meetings/': () => ({
        status: 200,
        body: {
          upcoming: [
            {
              id: 6,
              title: 'Jahreshauptversammlung 2099',
              kind_name: 'Jahreshauptversammlung',
              unit: '',
              starts_at: '2099-01-15T18:00:00Z',
              location: 'Schützenhaus',
              address: '',
              agenda: [{ position: 1, title: 'Begrüßung', description: '' }],
            },
          ],
          minutes: [
            {
              id: 5,
              title: 'Jahreshauptversammlung 2098',
              kind_name: 'Jahreshauptversammlung',
              unit: '',
              starts_at: '2098-01-15T18:00:00Z',
            },
          ],
        },
      }),
    })
    render(
      <MemoryRouter>
        <PortalMeetings accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('Begrüßung')).toBeInTheDocument()
    expect(screen.getByText(/Schützenhaus/)).toBeInTheDocument()
    expect(
      screen.getByRole('button', {
        name: 'Protokoll herunterladen: Jahreshauptversammlung 2098',
      }),
    ).toBeInTheDocument()
  })
})
