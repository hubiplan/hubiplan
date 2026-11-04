import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { OwnAvailability } from '../pages/music/AvailabilityPage.tsx'
import { StaffingPage } from '../pages/music/StaffingPage.tsx'
import { OwnMusic } from '../pages/music/OwnMusic.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({
    id: 7,
    modules: ['music', 'events'],
    permissions: ['music.view', 'music.edit'],
  }),
}))

it('blockiert bekannte Konflikte und schlägt Ersatz für die abgesagte Stimme vor', async () => {
  const url = '/api/orgs/7/music/performances/9/staffing/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({
      status: 200,
      body: {
        title: 'Musterkonzert',
        cancelled: false,
        positions: [{ id: 1, instrument: 'Tuba', register: '', required: 1, assigned: 0 }],
        assignments: [{ id: 3, name: 'Muster Absage', position: 1, status: 'declined' }],
        candidates: [
          { id: 11, name: 'Muster Abwesend', positions: [1], availability: ['absence'] },
          { id: 12, name: 'Muster Belegt', positions: [1], availability: ['busy'] },
          { id: 14, name: 'Muster Nebeninstrument', positions: [1], availability: [] },
          {
            id: 13,
            name: 'Muster Hauptinstrument',
            positions: [1],
            availability: [],
            preferred_positions: [1],
          },
        ],
      },
    }),
    'GET /api/orgs/7/music/ensemble-templates/': () => ({ status: 200, body: [] }),
    [`POST ${url}`]: () => ({ status: 200, body: { created: 1 } }),
  })
  render(
    <MemoryRouter>
      <StaffingPage performance={9} />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('checkbox', { name: 'Muster Abwesend' })).toBeDisabled()
  expect(screen.getByRole('checkbox', { name: 'Muster Belegt' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Ersatz suchen' }))
  expect(screen.queryByRole('checkbox', { name: 'Muster Abwesend' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('checkbox')[0]).toHaveAccessibleName('Muster Hauptinstrument')
  await userEvent.click(screen.getByRole('checkbox', { name: 'Muster Hauptinstrument' }))
  await userEvent.click(screen.getByRole('button', { name: 'Ausgewählte Musiker anfragen' }))
  await screen.findByText('Ausgewählte Musiker wurden angefragt.')
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body))).toEqual({
    action: 'assign',
    assignments: [{ musician: 13, position: 1 }],
  })
})

it('erfasst eine eigene Abwesenheit ohne Musikerwahl oder Begründung', async () => {
  const url = '/api/portal/9/music/absences/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({ status: 200, body: { enabled: true, items: [] } }),
    [`POST ${url}`]: () => ({ status: 200, body: { id: 2 } }),
  })
  render(<OwnAvailability accessId={9} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Abwesenheit eintragen' }))
  fireEvent.change(screen.getByLabelText('Abwesend von'), { target: { value: '2026-12-01T18:00' } })
  fireEvent.change(screen.getByLabelText('Abwesend bis'), { target: { value: '2026-12-01T21:00' } })
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await waitFor(() => expect(calls.some((c) => c.key === `POST ${url}`)).toBe(true))
  const request = calls.find((c) => c.key === `POST ${url}`)!
  expect(JSON.parse(String(request.init?.body))).toEqual({
    action: 'save',
    starts_at: new Date('2026-12-01T18:00').toISOString(),
    ends_at: new Date('2026-12-01T21:00').toISOString(),
  })
  expect(new Headers(request.init?.headers).get('Idempotency-Key')).toBeTruthy()
  expect(screen.queryByLabelText('Musiker')).not.toBeInTheDocument()
})

it('zeigt den eigenen Konflikt und lässt eine Absage weiterhin zu', async () => {
  const url = '/api/portal/9/music/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({
      status: 200,
      body: [
        {
          id: 3,
          title: 'Musterkonzert',
          starts_at: '2026-12-01T18:00:00Z',
          status: 'accepted',
          availability: ['absence'],
        },
      ],
    }),
    [`POST ${url}`]: () => ({ status: 200, body: { status: 'declined' } }),
    [`GET ${url}absences/`]: () => ({ status: 200, body: { enabled: false, items: [] } }),
    [`GET ${url}practice/`]: () => ({
      status: 200,
      body: { rehearsals: [], scores: [], loans: [] },
    }),
  })
  render(<OwnMusic accessId={9} />)
  expect(await screen.findByRole('button', { name: 'Zusagen' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Absagen' }))
  expect(JSON.parse(String(calls.find((c) => c.key === `POST ${url}`)?.init?.body))).toEqual({
    id: 3,
    status: 'declined',
  })
})
