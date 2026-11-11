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
  website_consent: false,
  website_url: '',
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

const agreement = {
  id: 2,
  kind: 'sponsoring',
  title: 'Hauptsponsor Schützenfest',
  start: '2026-01-01',
  end: '2026-12-31',
  amount: '1500.00',
  in_kind: '',
  benefits: ['banner'],
  benefits_text: '',
  tax_kind: 'advertising',
  category: null,
  notice_days: null,
  auto_renew: false,
  notice_by: null,
  remind_days: 60,
  reminder: 5,
  reminder_due: '2026-11-01',
  thanked_at: null,
  notes: '',
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
    'GET /api/orgs/7/billing/partners/4/agreements/': () => ({ status: 200, body: [agreement] }),
    'GET /api/orgs/7/billing/partners/4/fields/': () => ({
      status: 200,
      body: [
        {
          definition: {
            id: 1,
            label: 'Sponsorstufe',
            key: 'sponsorstufe',
            field_type: 'choice',
            choices: ['Gold', 'Silber'],
            repeatable: false,
            subfields: [],
            federation_wide: false,
            help_text: '',
            sort_order: 0,
            is_archived: false,
            inherited: false,
            owner_name: 'TV Beispielhausen',
            in_use: true,
          },
          value: 'Gold',
        },
      ],
    }),
    'GET /api/orgs/7/billing/partners/4/documents/': () => ({
      status: 200,
      body: [
        {
          id: 3,
          title: 'Wartungsvertrag',
          name: 'vertrag.pdf',
          size: 2048,
          content_type: 'application/pdf',
          agreement: null,
          uploaded_at: '2026-11-10T20:00:00Z',
          uploaded_by: 'Kim Muster',
          url: '/api/orgs/7/billing/partners/4/documents/3/',
        },
      ],
    }),
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

  it('zeigt Vereinbarungen mit Erinnerung und Dankesbrief', async () => {
    show(['partners.view', 'partners.edit'])
    fireEvent.click(await screen.findByRole('button', { name: 'Getränke Beispiel GmbH' }))
    expect(await screen.findByText('Hauptsponsor Schützenfest')).toBeInTheDocument()
    expect(screen.getByText(/Gegenleistung: Bande oder Banner/)).toBeInTheDocument()
    expect(screen.getByText(/Erinnerung am/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dankesbrief' })).toBeInTheDocument()
    expect(await screen.findByText('Wartungsvertrag')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dokument hochladen' })).toBeInTheDocument()
    expect(
      screen.getByLabelText('Darf auf unserer Webseite als Partner oder Sponsor genannt werden'),
    ).toBeInTheDocument()
  })

  it('zeigt Zusatzfelder in der Partnerakte', async () => {
    show(['partners.view', 'partners.edit'])
    fireEvent.click(await screen.findByRole('button', { name: 'Getränke Beispiel GmbH' }))
    expect(await screen.findByText('Zusatzfelder')).toBeInTheDocument()
    expect(screen.getByLabelText('Sponsorstufe')).toHaveValue('Gold')
  })

  it('verlangt ein Leserecht', async () => {
    show(['events.view'])
    expect(
      await screen.findByText(
        /Für diese Seite fehlt dir im aktuellen Arbeitsbereich das nötige Recht/,
      ),
    ).toBeInTheDocument()
  })
})
