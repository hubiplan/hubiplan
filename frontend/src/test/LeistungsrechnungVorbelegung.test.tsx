import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { CommercialForm } from '../pages/billing/EInvoicesPage.tsx'
import { fakeApi } from './fakeApi.ts'

vi.mock('../org/OrgContext.tsx', () => ({
  useActiveOrg: () => ({ id: 7, name: 'Kassenverein Musterstadt', modules: [], permissions: [] }),
}))

describe('Leistungsrechnung: Rechnungssteller vorbelegt', () => {
  it('übernimmt Anschrift, Kennung und IBAN des Vereins in eine neue Rechnung', async () => {
    fakeApi({
      'GET /api/orgs/7/billing/partners/': () => ({ status: 200, body: [] }),
      'GET /api/orgs/7/billing/settings/': () => ({
        status: 200,
        body: {
          categories: [],
          einvoice_iban: 'DE89370400440532013000',
          einvoice_seller: {
            name: 'Kassenverein Musterstadt e. V.',
            street: 'Musterweg 3',
            postcode: '12345',
            city: 'Musterstadt',
            country: 'DE',
            email: 'kasse@example.org',
            vat_id: '',
            tax_number: '',
            contact: 'Erika Muster',
            phone: '+49 30 123456',
            identifier: 'VR 1234',
          },
        },
      }),
    })
    render(
      <MemoryRouter>
        <CommercialForm onSaved={() => undefined} onClose={() => undefined} />
      </MemoryRouter>,
    )
    await waitFor(() => expect(screen.getByDisplayValue('Musterweg 3')).toBeInTheDocument())
    expect(screen.getByDisplayValue('VR 1234')).toBeInTheDocument()
    expect(screen.getByDisplayValue('DE89370400440532013000')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Kassenverein Musterstadt e. V.')).toBeInTheDocument()
  })
})
