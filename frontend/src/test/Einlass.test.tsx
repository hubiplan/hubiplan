// Einlass vor Ort (Anmeldung A6): Code scannen, Liste abhaken (Daten erfunden).
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CheckInPanel } from '../components/calendar/CheckIn.tsx'
import type { CheckInRow } from '../api/registrations.ts'
import { fakeApi } from './fakeApi.ts'

const base = '/api/orgs/1/' as const
const erika: CheckInRow = {
  id: 9,
  name: 'Erika Beispiel',
  price_name: 'Gäste',
  registration_id: 5,
  number: 'A2099-0007',
  contact: 'Erika Beispiel',
  paid_state: 'open',
  checked_in_at: null,
  minor: false,
}

describe('Einlass', () => {
  it('scannt eine Karte und zählt mit', async () => {
    const calls = fakeApi({
      'GET /api/orgs/1/events/3/registration/checkin/': () => ({
        status: 200,
        body: {
          event_id: 3,
          title: 'Sommerfest',
          can_edit: true,
          participants: [erika],
          count: 1,
          checked_in: 0,
        },
      }),
      'POST /api/orgs/1/events/3/registration/checkin/': () => ({
        status: 200,
        body: {
          result: 'ok',
          message: 'Eingelassen.',
          participant: { ...erika, checked_in_at: '2099-06-13T12:05:00Z' },
        },
      }),
    })
    render(<CheckInPanel base={base} eventId={3} />)
    expect(await screen.findByText('0 von 1 Personen eingelassen.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Code der Eintrittskarte/), {
      target: { value: 'T9:abc' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Einlassen' }))
    expect(await screen.findByText('Eingelassen.', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('1 von 1 Personen eingelassen.')).toBeInTheDocument()
    expect(screen.getByText(/Zahlung offen/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === 'POST /api/orgs/1/events/3/registration/checkin/')
    expect(JSON.parse(String(post?.init?.body))).toEqual({ code: 'T9:abc' })
  })
})
