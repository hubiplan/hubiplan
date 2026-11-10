import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const partner = {
  id: 4,
  name: 'Getränke Beispiel GmbH',
  kind: 'company',
  roles: ['supplier', 'sponsor'],
  number: 'GP-0001',
  unit: null,
  unit_name: '',
  membership: null,
  membership_name: '',
  details: {
    name: 'Getränke Beispiel GmbH',
    street: 'Musterweg 1',
    postcode: '12345',
    city: 'Musterstadt',
    country: 'DE',
    email: 'info@example.org',
    phone: '+49 30 123456',
    vat_id: '',
    tax_number: '',
    contact: '',
    identifier: '',
  },
  bank: { iban: 'DE89370400440532013000', bic: '', holder: '', changed_at: '', changed_by: '' },
  our_customer_number: '',
  default_category: null,
  payment_terms_days: null,
  artist: false,
  notes: '',
  is_customer: false,
  is_supplier: true,
  is_active: true,
  contacts: [
    {
      id: 9,
      last_name: 'Muster',
      first_name: 'Kim',
      function: 'Vertrieb',
      email: '',
      phone: '+49 30 654321',
      is_primary: true,
      receives_invoices: true,
      receives_mail: true,
      notes: '',
    },
  ],
  updated_at: '2026-11-10T20:00:00Z',
}

function show(permissions: string[], body: unknown[] = [partner]) {
  fakeApi({
    'GET /_allauth/browser/v1/auth/session': () => ({
      status: 200,
      body: { status: 200, data: { user: testUser } },
    }),
    'GET /api/me/organizations/': () => ({
      status: 200,
      body: [testOrg({ permissions })],
    }),
    'GET /api/orgs/7/billing/partners/': () => ({ status: 200, body }),
    'GET /api/orgs/7/finance/categories/': () => ({ status: 200, body: [] }),
  })
  render(
    <MemoryRouter initialEntries={['/geschaeftspartner']}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

describe('Geschäftspartner', () => {
  it('listet Partner mit Rollen und Hauptansprechpartner', async () => {
    show(['partners.view', 'partners.edit'])
    expect(
      await screen.findByRole('button', { name: 'Getränke Beispiel GmbH' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Lieferant, Sponsor')).toBeInTheDocument()
    expect(screen.getByText('Kim Muster')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Geschäftspartner anlegen' })).toBeInTheDocument()
  })

  it('zeigt den Abschnitt Kasse nur mit Kassenrecht', async () => {
    show(['partners.view', 'partners.edit'], [{ ...partner, bank: undefined }])
    fireEvent.click(await screen.findByRole('button', { name: 'Getränke Beispiel GmbH' }))
    expect(await screen.findByText('Ansprechpartner hinzufügen')).toBeInTheDocument()
    expect(screen.queryByLabelText('IBAN')).not.toBeInTheDocument()
  })

  it('verlangt ein Leserecht', async () => {
    show(['events.view'])
    expect(await screen.findByText('Dafür fehlt dir die Berechtigung.')).toBeInTheDocument()
  })
})
