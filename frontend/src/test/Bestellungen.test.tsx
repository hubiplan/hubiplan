import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PortalOrders } from '../pages/portal/PortalOrders.tsx'
import { fakeApi } from './fakeApi.ts'

const articles = [
  {
    id: 1,
    name: 'Poloshirt',
    text: 'mit Vereinswappen',
    price: '25.00',
    variants: ['S', 'M', 'L'],
    variant_label: 'Größe',
    max_per_member: 3,
    max_total: null,
  },
  {
    id: 2,
    name: 'Festschrift',
    text: '',
    price: '10.00',
    variants: [],
    variant_label: '',
    max_per_member: null,
    max_total: 50,
    left: 12,
  },
]

const campaign = (extra = {}) => ({
  id: 7,
  title: 'Vereinskleidung 2027',
  deadline: '2099-06-30',
  state: 'open',
  from: 'Musterverein',
  club_pays: false,
  ordered: false,
  can_order: true,
  order: null,
  ...extra,
})

describe('Bestellungen im Mitgliederbereich', () => {
  it('bestellt je Größe mit Summe', async () => {
    let sent: { lines: unknown[]; note: string } | null = null
    fakeApi({
      'GET /api/portal/9/orders/': () => ({ status: 200, body: { campaigns: [campaign()] } }),
      'GET /api/portal/9/orders/7/': () => ({
        status: 200,
        body: campaign({ text: 'Ausgabe beim Sommerfest', articles }),
      }),
      'PUT /api/portal/9/orders/7/order/': (init) => {
        sent = JSON.parse(String(init?.body))
        return { status: 200, body: campaign({ ordered: true }) }
      },
    })
    render(
      <MemoryRouter>
        <PortalOrders accessId={9} />
      </MemoryRouter>,
    )
    await userEvent.click(await screen.findByRole('button', { name: 'Jetzt bestellen' }))
    expect(await screen.findByText('Ausgabe beim Sommerfest')).toBeInTheDocument()
    expect(screen.getByText('noch 12 von 50 verfügbar')).toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Poloshirt, Größe M: Menge'), '2')
    await userEvent.type(screen.getByLabelText('Festschrift: Menge'), '1')
    expect(screen.getByText('Summe: 60,00 €')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Bestellen' }))
    expect(await screen.findByText('Danke, deine Bestellung ist gespeichert.')).toBeInTheDocument()
    expect(sent!.lines).toEqual([
      { article: 1, variant: 'M', quantity: 2 },
      { article: 2, variant: '', quantity: 1 },
    ])
  })

  it('zeigt bei „Verein bezahlt“ keine Preise und die eigene Bestellung', async () => {
    const order = {
      id: 3,
      lines: [
        { article: 1, name: 'Poloshirt', variant: 'L', quantity: 1, price: null, amount: null },
      ],
      note: '',
      total: null,
      handed_out: true,
      handed_out_at: '2099-07-01T10:00:00Z',
      updated_at: '2099-06-01T10:00:00Z',
      invoice: null,
    }
    fakeApi({
      'GET /api/portal/9/orders/': () => ({
        status: 200,
        body: {
          campaigns: [
            campaign({ state: 'closed', club_pays: true, ordered: true, can_order: false, order }),
          ],
        },
      }),
    })
    render(
      <MemoryRouter>
        <PortalOrders accessId={9} />
      </MemoryRouter>,
    )
    expect(await screen.findByText('1 × Poloshirt (L)')).toBeInTheDocument()
    expect(screen.getByText('Ausgegeben')).toBeInTheDocument()
    expect(screen.queryByText(/€/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Jetzt bestellen' })).not.toBeInTheDocument()
  })
})
