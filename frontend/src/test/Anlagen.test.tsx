import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'

const settings = {
  current_year: 2026,
  years: [{ year: 2026, label: '2026' }],
  tax_areas: [
    { value: 'ideal', label: 'ideeller Bereich' },
    { value: 'business', label: 'wirtschaftlicher Geschäftsbetrieb' },
  ],
  tax_areas_enabled: true,
}

const register = {
  year: 2026,
  label: '2026',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  suggest_from: '250.00',
  totals: { depreciation: '1200.00', residual: '0.00', book_end: '9900.00' },
  assets: [
    {
      id: 3,
      name: 'Festzelt',
      acquired_on: '2025-04-10',
      cost: '12000.00',
      net_cost: null,
      tax_area: 'business',
      tax_area_label: 'wirtschaftlicher Geschäftsbetrieb',
      method: 'linear',
      method_label: 'linear über die Nutzungsdauer',
      useful_life: 10,
      booking: 12,
      booking_number: '2025-0012',
      material_item: null,
      material_name: null,
      disposal: '',
      disposal_label: 'im Bestand',
      disposed_on: null,
      note: '',
      values: {
        depreciation: '1200.00',
        residual: '0.00',
        book_start: '11100.00',
        book_end: '9900.00',
      },
    },
  ],
}

function renderApp(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <OrgProvider>
          <App />
        </OrgProvider>
      </AuthProvider>
    </MemoryRouter>,
  )
}

function api() {
  const org = testOrg({
    modules: ['members', 'finance', 'tax'],
    permissions: ['finance.view', 'finance.edit'],
    parent_name: null,
  })
  return fakeApi({
    [SESSION]: loggedIn,
    'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
    [`GET ${F}/settings/`]: () => ({ status: 200, body: settings }),
    [`GET ${F}/assets/?jahr=2026`]: () => ({ status: 200, body: register }),
    [`GET ${F}/assets/materials/`]: () => ({ status: 200, body: [] }),
  })
}

describe('Anlagenverzeichnis', () => {
  it('zeigt Anlagen mit Abschreibung und Buchwert des Jahres', async () => {
    api()
    renderApp('/finanzen/anlagen')
    expect(await screen.findByRole('button', { name: 'Festzelt' })).toBeInTheDocument()
    expect(screen.getByText('2025-0012')).toBeInTheDocument()
    expect(screen.getAllByText(/9\.900,00/).length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'Excel' })).toHaveAttribute(
      'href',
      expect.stringContaining('/finance/assets/?jahr=2026&als=xlsx'),
    )
  })

  it('übernimmt die Ausgabe aus dem Kassenbuch in eine neue Anlage', async () => {
    api()
    renderApp('/finanzen/abschluss/anlagen?buchung=12&betrag=1500.00&datum=2026-03-02&name=Beamer')
    expect(await screen.findByRole('heading', { name: 'Neue Anlage' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Bezeichnung/)).toHaveValue('Beamer')
    expect(screen.getByLabelText(/^Anschaffungskosten/)).toHaveValue('1500,00')
    expect(
      screen.getByText('Wird mit der Ausgabe aus dem Kassenbuch verknüpft.'),
    ).toBeInTheDocument()
  })
})
