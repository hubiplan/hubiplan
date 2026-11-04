import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { it, expect, vi } from 'vitest'
import { SettlementPanel } from '../pages/music/SettlementPanel.tsx'
import { OwnMusic } from '../pages/music/OwnMusic.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({
    id: 7,
    name: 'Musterverein',
    modules: ['music', 'finance'],
    permissions: ['music.view', 'finance.view'],
  }),
}))

it('zeigt Finanzlesern Summen ohne Freigabe- und Eingabeaktionen', async () => {
  fakeApi({
    'GET /api/orgs/7/music/performances/3/settlement/': () => ({
      status: 200,
      body: {
        agreed: '200',
        revenue: '150',
        expenses: '50',
        result: '100',
        claims: [],
        payments: [],
      },
    }),
  })
  render(
    <MemoryRouter>
      <SettlementPanel performance={3} title="Musterkonzert" customer={null} assignments={[]} />
    </MemoryRouter>,
  )
  await screen.findByText('Ergebnis aus Zahlungen')
  expect(screen.getByText('100,00 €')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Speichern' })).not.toBeInTheDocument()
  expect(
    screen.queryByRole('button', { name: 'Veranstalterrechnung erstellen' }),
  ).not.toBeInTheDocument()
})

it('zeigt im Mitgliederbereich nur die eigene freigegebene Vergütung', async () => {
  fakeApi({
    'GET /api/portal/9/music/': () => ({
      status: 200,
      body: [
        {
          id: 1,
          title: 'Musterkonzert',
          starts_at: '2026-11-01T18:00:00Z',
          status: 'accepted',
          settlement: {
            fee: '40.00',
            allowance: '5.00',
            expenses: '5.00',
            total: '50.00',
            paid: true,
          },
        },
      ],
    }),
  })
  render(
    <MemoryRouter>
      <OwnMusic accessId={9} />
    </MemoryRouter>,
  )
  expect(await screen.findByText(/Meine Vergütung/)).toHaveTextContent('50.00 EUR')
  expect(screen.queryByText('Tatsächliche Einnahmen')).not.toBeInTheDocument()
})
