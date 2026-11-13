import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { LiveState, Meeting, Poll, PortalLive } from '../api/meetings.ts'
import { LiveCard } from '../pages/meetings/LiveCard.tsx'
import { checkinLink } from '../pages/meetings/live.ts'
import { PortalMeetingLive } from '../pages/portal/PortalMeetingLive.tsx'
import { fakeApi } from './fakeApi.ts'

// Versammlungen V7, erfundene Daten
const poll: Poll = {
  id: 4,
  agenda_item: 11,
  agenda_position: 7,
  agenda_title: 'Entlastung des Vorstands',
  kind: 'resolution',
  question: 'Entlastung des Vorstands',
  office: '',
  candidate: '',
  secret: true,
  status: 'open',
  opened_at: '2099-01-15T19:00:00Z',
  closed_at: null,
  cast: 1,
  entitled: 3,
  options: [
    { id: 21, role: 'yes', label: 'Ja' },
    { id: 22, role: 'no', label: 'Nein' },
    { id: 23, role: 'abstain', label: 'Enthaltung' },
  ],
  result: null,
  resolution: null,
}

const state: LiveState = {
  meeting: 5,
  organization: 7,
  status: 'invited',
  online_voting: true,
  remote_allowed: true,
  checkin_open: true,
  remote: false,
  live: true,
  voters: 10,
  present_app: 2,
  present_online: 0,
  entitled: 3,
  polls: [poll],
  code: '123-abc',
  refresh_in: 20,
}

describe('Versammlung: Anmelden per App und Online-Abstimmung', () => {
  it('QR-Code führt in den Mitgliederbereich mit Verein und Code', () => {
    expect(checkinLink(state)).toBe(
      `${window.location.origin}/mein-bereich/versammlungen/da/5?v=7&c=123-abc`,
    )
  })

  it('Leitung sieht Code, Zahlen und beendet eine Abstimmung', async () => {
    const api = fakeApi({
      'GET /api/orgs/7/meetings/5/live/': () => ({ status: 200, body: state }),
      'POST /api/orgs/7/meetings/5/polls/4/': () => ({
        status: 200,
        body: {
          ...state,
          polls: [
            {
              ...poll,
              status: 'closed',
              result: poll.options.map((o, i) => ({ ...o, votes: [2, 1, 0][i] })),
            },
          ],
        },
      }),
    })
    const meeting = {
      id: 5,
      status: 'invited',
      can_edit: true,
      agenda: [{ id: 11, position: 7, title: 'Entlastung des Vorstands', type: 'resolution' }],
    } as Meeting
    render(<LiveCard base="/api/orgs/7/meetings/" meeting={meeting} onChanged={async () => {}} />)
    expect(await screen.findByTitle('QR-Code zum Anmelden')).toBeInTheDocument()
    expect(screen.getByText(/Per App angemeldet: 2/)).toBeInTheDocument()
    expect(screen.getByText('1 von 3 Stimmen abgegeben.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Abstimmung beenden' }))
    // Es fehlen noch Stimmen: erst nachfragen
    fireEvent.click(await screen.findByRole('button', { name: 'Beenden' }))
    await waitFor(() => expect(screen.getByText('Ja:')).toBeInTheDocument())
    const call = api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/polls/4/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({ action: 'close' })
  })

  it('Mitglied meldet sich mit dem Code an und stimmt mit Vollmacht ab', async () => {
    let present = false
    const live = (): PortalLive => ({
      id: 5,
      title: 'Jahreshauptversammlung 2099',
      kind_name: 'Jahreshauptversammlung',
      unit: '',
      starts_at: '2099-01-15T18:00:00Z',
      location: 'Vereinsheim',
      checkin_open: true,
      remote: false,
      voter: true,
      is_organization: false,
      status: present ? 'present' : '',
      mode: present ? 'app' : '',
      votes: present ? 2 : 0,
      polls: present
        ? [
            {
              ...poll,
              votes: [
                { attendance: 31, name: 'Erika Beispiel', how: 'own', done: false },
                { attendance: 32, name: 'Max Muster', how: 'proxy', done: false },
              ],
            },
          ]
        : [],
    })
    const api = fakeApi({
      'GET /api/portal/9/meetings/5/live/': () => ({ status: 200, body: live() }),
      'POST /api/portal/9/meetings/5/live/checkin/': () => {
        present = true
        return { status: 200, body: live() }
      },
      'POST /api/portal/9/meetings/5/polls/4/vote/': () => ({ status: 200, body: live() }),
    })
    render(
      <MemoryRouter>
        <PortalMeetingLive accessId={9} meetingId={5} code="123-abc" />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Ich bin da' }))
    expect(await screen.findByText(/Du hast 2 Stimmen/)).toBeInTheDocument()
    const checkin = api.find((c) => c.key === 'POST /api/portal/9/meetings/5/live/checkin/')!
    expect(JSON.parse(String(checkin.init?.body))).toEqual({ code: '123-abc' })
    expect(screen.getByText('Vollmacht von Max Muster')).toBeInTheDocument()
    const yes = screen.getAllByLabelText('Ja')
    fireEvent.click(yes[0])
    fireEvent.click(screen.getAllByLabelText('Nein')[1])
    fireEvent.click(screen.getByRole('button', { name: 'Stimmen abgeben' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/portal/9/meetings/5/polls/4/vote/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/portal/9/meetings/5/polls/4/vote/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      votes: [
        { attendance: 31, option: 21 },
        { attendance: 32, option: 22 },
      ],
    })
  })
})
