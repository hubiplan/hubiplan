import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { Meeting } from '../api/meetings.ts'
import { MotionsCard } from '../pages/meetings/MotionsCard.tsx'
import { PortalMeetings } from '../pages/portal/PortalMeetings.tsx'
import { fakeApi } from './fakeApi.ts'

const motion = {
  id: 3,
  name: 'Erika Beispiel',
  title: 'Neue Fahne',
  text: 'Die alte Fahne ist verschlissen.',
  status: 'submitted' as const,
  reply: '',
  agenda_item: null,
  created_at: '2099-01-01T10:00:00Z',
  decided_at: null,
}

describe('Anträge', () => {
  it('Verwaltung lehnt einen Antrag mit Begründung ab', async () => {
    const api = fakeApi({
      'POST /api/orgs/7/meetings/5/motions/3/': () => ({ status: 200, body: {} }),
    })
    const meeting = { id: 5, status: 'invited', can_edit: true, motions: [motion] } as Meeting
    render(
      <MotionsCard base="/api/orgs/7/meetings/" meeting={meeting} onChanged={async () => {}} />,
    )
    expect(screen.getByText('Antrag von Erika Beispiel')).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'In die Tagesordnung aufnehmen: Neue Fahne' }),
    ).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Ablehnen' }))
    const form = screen.getByRole('form', { name: 'Antrag ablehnen: Neue Fahne' })
    fireEvent.change(within(form).getByLabelText('Begründung für das Mitglied'), {
      target: { value: 'Passt nicht.' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Antrag ablehnen' }))
    await waitFor(() =>
      expect(api.some((c) => c.key === 'POST /api/orgs/7/meetings/5/motions/3/')).toBe(true),
    )
    const call = api.find((c) => c.key === 'POST /api/orgs/7/meetings/5/motions/3/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      decision: 'reject',
      reply: 'Passt nicht.',
    })
  })

  it('Mitglied stellt einen Antrag im Mitgliederbereich', async () => {
    let sent = false
    const upcoming = () => ({
      id: 6,
      title: 'Jahreshauptversammlung 2099',
      kind_name: 'Jahreshauptversammlung',
      unit: '',
      starts_at: '2099-01-15T18:00:00Z',
      location: '',
      address: '',
      motion_until: '2099-01-08T18:00:00Z',
      motions: sent
        ? [
            {
              id: 3,
              title: 'Neue Fahne',
              text: 'x',
              status: 'submitted',
              reply: '',
              created_at: '',
            },
          ]
        : [],
      agenda: [{ position: 1, title: 'Begrüßung', description: '' }],
    })
    const api = fakeApi({
      'GET /api/portal/9/meetings/': () => ({
        status: 200,
        body: { upcoming: [upcoming()], minutes: [] },
      }),
      'POST /api/portal/9/meetings/6/motions/': () => {
        sent = true
        return { status: 201, body: [] }
      },
    })
    render(
      <MemoryRouter>
        <PortalMeetings accessId={9} />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Antrag stellen' }))
    const form = screen.getByRole('form', { name: /^Antrag stellen:/ })
    fireEvent.change(within(form).getByLabelText('Titel des Antrags'), {
      target: { value: 'Neue Fahne' },
    })
    fireEvent.change(within(form).getByLabelText('Begründung'), {
      target: { value: 'Die alte Fahne ist verschlissen.' },
    })
    fireEvent.click(within(form).getByRole('button', { name: 'Antrag einreichen' }))
    expect(
      await screen.findByRole('button', { name: 'Antrag zurückziehen: Neue Fahne' }),
    ).toBeInTheDocument()
    const call = api.find((c) => c.key === 'POST /api/portal/9/meetings/6/motions/')!
    expect(JSON.parse(String(call.init?.body))).toEqual({
      title: 'Neue Fahne',
      text: 'Die alte Fahne ist verschlissen.',
    })
  })
})
