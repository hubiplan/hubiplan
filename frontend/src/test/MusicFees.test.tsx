import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { FeeBatchPanel } from '../pages/music/FeeBatchPanel.tsx'
import { SettlementPanel } from '../pages/music/SettlementPanel.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({
    id: 7,
    modules: ['music', 'finance'],
    permissions: ['music.view', 'finance.view', 'finance.edit'],
  }),
}))

it('requires selection and copies explicitly confirmed attendance into protected batch drafts', async () => {
  const url = '/api/orgs/7/music/performances/9/settlement/'
  const calls = fakeApi({
    'GET /api/orgs/7/music/fee-templates/': () => ({
      status: 200,
      body: [{ id: 1, name: 'Konzert', fee: '40', allowance: '10', active: true }],
    }),
    [`POST ${url}`]: () => ({ status: 200, body: {} }),
  })
  const saved = vi.fn(async () => {})
  render(
    <FeeBatchPanel
      url={url}
      assignments={[
        { id: 3, name: 'Muster Eins' },
        { id: 4, name: 'Muster Zwei' },
      ]}
      onSaved={saved}
    />,
  )
  expect(screen.getByRole('button', { name: 'Vergütungsentwürfe anlegen' })).toBeDisabled()
  await screen.findByRole('option', { name: /Konzert/ })
  fireEvent.change(screen.getByLabelText('Vergütungsvorlage'), { target: { value: '1' } })
  await userEvent.click(screen.getByRole('button', { name: 'Alle ohne Vergütung auswählen' }))
  await userEvent.click(screen.getByLabelText('Teilnahme bestätigt für Muster Eins'))
  await userEvent.click(screen.getByRole('button', { name: 'Vergütungsentwürfe anlegen' }))
  await screen.findByText('Vergütungsentwürfe wurden angelegt.')
  const request = calls.find((c) => c.key.startsWith('POST'))!
  expect(new Headers(request.init?.headers).get('Idempotency-Key')).toBeTruthy()
  expect(JSON.parse(String(request.init?.body))).toEqual({
    action: 'batch_claims',
    template: 1,
    rows: [
      { assignment: 3, attended: true },
      { assignment: 4, attended: false },
    ],
  })
  expect(saved).toHaveBeenCalledOnce()
})

it('shows partial payouts and the balance without permitting approval reversal', async () => {
  fakeApi({
    'GET /api/orgs/7/music/performances/9/settlement/': () => ({
      status: 200,
      body: {
        claims: [
          {
            id: 2,
            assignment: 3,
            fee: '100',
            allowance: '0',
            expenses: '0',
            total: '100',
            status: 'approved',
            paid: false,
            paid_amount: '40',
            outstanding: '60',
          },
        ],
        payments: [],
      },
    }),
    'GET /api/orgs/7/music/fee-templates/': () => ({ status: 200, body: [] }),
    'GET /api/orgs/7/finance/bookings/?art=expense&suche=&page=1': () => ({
      status: 200,
      body: { results: [], next: null },
    }),
  })
  render(
    <MemoryRouter>
      <SettlementPanel
        performance={9}
        title="Musterkonzert"
        customer={null}
        assignments={[{ id: 3, name: 'Muster Eins' }]}
      />
    </MemoryRouter>,
  )
  await screen.findByText('Teilweise ausgezahlt')
  expect(screen.getByText(/Offener Vergütungsbetrag/)).toHaveTextContent('60,00 €')
  await waitFor(() =>
    expect(screen.queryByRole('button', { name: 'Freigabe aufheben' })).not.toBeInTheDocument(),
  )
  const musician = screen.getByText('Muster Eins').closest('article')!
  expect(within(musician).getByRole('button', { name: 'Auszahlung zuordnen' })).toBeDisabled()
})
