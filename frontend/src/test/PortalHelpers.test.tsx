import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalHelpers } from '../pages/portal/PortalHelpers.tsx'
import { fakeApi } from './fakeApi.ts'

const shift = (id: number, mine: number | null, start: string) => ({
  id,
  starts_at: `2099-06-20T${start}:00Z`,
  ends_at: `2099-06-20T${start}:00Z`,
  needed: 2,
  taken: mine ? 1 : 0,
  note: '',
  names: mine ? ['Erika Beispiel'] : [],
  mine,
  can_cancel: Boolean(mine),
  past: false,
})

describe('Helferdienste im Mitgliederbereich', () => {
  it('trägt in eine freie Schicht ein und zeigt meine Dienste', async () => {
    let signed = false
    const plan = () => ({
      id: 1,
      title: 'Schützenfest 2099',
      unit: '',
      event_title: '',
      signup: 'self',
      cancel_days: 2,
      max_shifts: 1,
      note: '',
      duties: [
        {
          id: 3,
          name: 'Kasse',
          description: '',
          location: 'Festzelt',
          min_age: null,
          shifts: [shift(7, signed ? 11 : null, '08'), shift(8, null, '12')],
        },
      ],
    })
    fakeApi({
      'GET /api/portal/9/helpers/': () => ({
        status: 200,
        body: {
          plans: [plan()],
          mine: signed
            ? [
                {
                  id: 11,
                  plan: 'Schützenfest 2099',
                  duty: 'Kasse',
                  location: 'Festzelt',
                  starts_at: '2099-06-20T08:00:00Z',
                  ends_at: '2099-06-20T12:00:00Z',
                },
              ]
            : [],
        },
      }),
      'POST /api/portal/9/helpers/shifts/7/signup/': () => {
        signed = true
        return { status: 201, body: plan() }
      },
    })
    render(
      <MemoryRouter>
        <PortalHelpers accessId={9} />
      </MemoryRouter>,
    )
    expect(
      await screen.findByText('Du bist zurzeit für keinen Dienst eingetragen.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Höchstens 1 Schichten je Person/)).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: /^Eintragen: Kasse/ })
    await userEvent.click(buttons[0])
    expect(await screen.findByRole('button', { name: /^Absagen: Kasse/ })).toBeInTheDocument()
    const mine = screen.getByRole('heading', { name: 'Meine Dienste' }).closest('section')!
    expect(within(mine).getByText('Kasse')).toBeInTheDocument()
    expect(
      within(mine).getByRole('button', { name: 'In den Kalender übernehmen' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Erika Beispiel')).toBeInTheDocument()
  })
})
