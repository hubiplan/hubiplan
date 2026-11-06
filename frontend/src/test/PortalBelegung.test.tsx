import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalBookings } from '../pages/portal/PortalBookings.tsx'
import { fakeApi } from './fakeApi.ts'

function thisMonday() {
  const key = new Date().toLocaleDateString('sv-SE', { timeZone: 'Europe/Berlin' })
  const d = new Date(key + 'T12:00:00Z')
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7))
  return d.toISOString().slice(0, 10)
}

describe('Belegung im Mitgliederbereich', () => {
  it('zeigt belegte Zeiten ohne fremden Zweck und schickt eine Anfrage', async () => {
    const own = {
      id: 5,
      item: 4,
      item_title: 'Saal',
      title: 'Geburtstag',
      note: '',
      starts_at: '2026-11-20T14:00:00Z',
      ends_at: '2026-11-20T19:00:00Z',
      all_day: false,
      status: 'requested',
      version: 1,
    }
    let sent: Record<string, unknown> | null = null
    fakeApi({
      [`GET /api/portal/9/bookings/?start=${thisMonday()}`]: () => ({
        status: 200,
        body: {
          items: [{ id: 4, kind: 'facility', title: 'Saal', facility: 3, horizon_days: 365 }],
          occurrences: [
            {
              item: 4,
              title: 'Belegt',
              starts_at: '2026-11-06T17:00:00Z',
              ends_at: '2026-11-06T19:00:00Z',
              all_day: false,
              own: false,
            },
          ],
          own: sent ? [own] : [],
        },
      }),
      'POST /api/portal/9/bookings/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { status: 201, body: own }
      },
    })
    render(
      <MemoryRouter>
        <PortalBookings accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByText(/· Belegt$/)).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Zweck'), 'Geburtstag')
    await userEvent.type(screen.getByLabelText('Beginn'), '2026-11-20T15:00')
    await userEvent.type(screen.getByLabelText('Ende'), '2026-11-20T20:00')
    await userEvent.click(screen.getByRole('button', { name: 'Anfrage senden' }))
    expect(await screen.findByText('Deine Anfrage ist eingegangen.')).toBeInTheDocument()
    expect(sent).toMatchObject({ item: 4, title: 'Geburtstag', starts_at: '2026-11-20T15:00:00' })
    expect(await screen.findByRole('button', { name: 'Buchung stornieren' })).toBeInTheDocument()
  })
})
