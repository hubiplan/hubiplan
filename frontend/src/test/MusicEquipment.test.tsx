import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { expect, it, vi } from 'vitest'
import { EquipmentPage } from '../pages/music/EquipmentPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({
    id: 7,
    modules: ['music', 'material'],
    permissions: ['music.view', 'music.edit', 'material.view', 'material.edit'],
  }),
}))

it('registers existing inventory without duplicating material records', async () => {
  const url = '/api/orgs/7/music/equipment/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({
      status: 200,
      body: {
        items: [],
        available: [{ id: 12, title: 'Vereinstuba', number: 'MAT-000012', version: 3 }],
        musicians: [],
      },
    }),
    [`POST ${url}`]: () => ({ status: 200, body: { id: 4 } }),
  })
  render(
    <MemoryRouter>
      <EquipmentPage />
    </MemoryRouter>,
  )
  await userEvent.click(
    await screen.findByRole('button', { name: 'Material als Musikausstattung verbinden' }),
  )
  fireEvent.change(screen.getByLabelText('Vorhandenes Material'), { target: { value: '12' } })
  fireEvent.change(screen.getByLabelText('Instrument'), { target: { value: 'Tuba' } })
  await userEvent.click(screen.getByRole('button', { name: 'Speichern' }))
  await screen.findByText('Musikausstattung wurde gespeichert.')
  const request = calls.find((c) => c.key.startsWith('POST'))!
  expect(JSON.parse(String(request.init?.body))).toMatchObject({
    action: 'register',
    item: 12,
    version: 3,
    instrument: 'Tuba',
  })
  expect(new Headers(request.init?.headers).get('Idempotency-Key')).toBeTruthy()
  expect(calls.filter((c) => c.key.startsWith('POST'))).toHaveLength(1)
})

it('shows custody and requires an explicit return destination and condition', async () => {
  const url = '/api/orgs/7/music/equipment/'
  const calls = fakeApi({
    [`GET ${url}`]: () => ({
      status: 200,
      body: {
        items: [
          {
            id: 4,
            item: 12,
            title: 'Vereinstuba',
            number: 'MAT-000012',
            version: 4,
            kind: 'instrument',
            instrument: 'Tuba',
            size: 'B',
            condition: 'ready',
            active_loan: 9,
            return_location: { location_kind: 'address' },
            loans: [
              {
                id: 9,
                name: 'Muster Gast',
                issued_at: '2026-11-01T12:00:00Z',
                due_date: '2026-11-03',
                returned_at: null,
                overdue: true,
                note: '',
              },
            ],
            maintenance: [],
          },
        ],
        available: [],
        musicians: [],
      },
    }),
    [`POST ${url}`]: () => ({ status: 200, body: { id: 4 } }),
  })
  render(
    <MemoryRouter>
      <EquipmentPage />
    </MemoryRouter>,
  )
  await screen.findByText(/Ausgegeben an Muster Gast/)
  await userEvent.click(screen.getByRole('button', { name: 'Ausstattung zurücknehmen' }))
  expect(screen.getByLabelText('Bisherigen Lagerort bei Rückgabe wiederherstellen')).toBeChecked()
  fireEvent.change(screen.getByLabelText('Zustand'), { target: { value: 'defective' } })
  await userEvent.click(
    within(
      screen
        .getByLabelText('Bisherigen Lagerort bei Rückgabe wiederherstellen')
        .closest('fieldset')!,
    ).getByRole('button', { name: 'Speichern' }),
  )
  await screen.findByText('Musikausstattung wurde gespeichert.')
  expect(JSON.parse(String(calls.find((c) => c.key.startsWith('POST'))?.init?.body))).toMatchObject(
    { action: 'return', loan: 9, restore_location: true, condition: 'defective', version: 4 },
  )
})
