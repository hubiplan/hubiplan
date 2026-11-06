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
  years: [
    { year: 2026, label: '2026' },
    { year: 2025, label: '2025' },
  ],
  tax_areas: [],
  tax_areas_enabled: true,
}

const report = {
  year: 2026,
  label: '2026',
  start_date: '2026-01-01',
  end_date: '2026-12-31',
  period: 2026,
  enabled: true,
  root: { id: 7, name: 'Verein A', is_self: true },
  units: [
    {
      id: 9,
      name: 'Spielmannszug',
      tax_areas_enabled: true,
      business_income: '12000.00',
      turnover: '12000.00',
    },
  ],
  own_areas: [
    {
      area: 'business',
      label: 'wirtschaftlicher Geschäftsbetrieb',
      income: '30000.00',
      expense: '5000.00',
      result: '25000.00',
    },
  ],
  areas: [
    {
      area: 'business',
      label: 'wirtschaftlicher Geschäftsbetrieb',
      income: '42000.00',
      expense: '5000.00',
      result: '37000.00',
    },
  ],
  free_limit: { limit: '50000.00', income: '42000.00', status: 'warn', percent: 84 },
  business_result: '37000.00',
  history: [
    { year: 2024, label: '2024', income: '10000.00', result: '2000.00' },
    { year: 2025, label: '2025', income: '20000.00', result: '3000.00' },
  ],
  small_business: {
    previous: '20000.00',
    previous_limit: '25000.00',
    current: '42000.00',
    current_limit: '100000.00',
    status: 'warn',
  },
  warnings: [],
  declaration: {
    known: true,
    due: false,
    next_from: 2024,
    next_to: 2026,
    text: 'Die Jahre 2024 bis 2026 sind noch nicht vom Finanzamt geprüft.',
  },
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

describe('Steuerliche Auswertung', () => {
  it('zeigt Ampel, enthaltene Kassen, Kleinunternehmer und Erklärungshinweis', async () => {
    const org = testOrg({
      modules: ['members', 'finance'],
      permissions: ['finance.view'],
      parent_name: null,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/settings/`]: () => ({ status: 200, body: settings }),
      [`GET ${F}/tax/?jahr=2026`]: () => ({ status: 200, body: report }),
    })
    renderApp('/finanzen/abschluss/steuern')
    const meter = await screen.findByRole('meter', { name: 'Anteil an der Freigrenze' })
    expect(meter).toHaveAttribute('value', '42000')
    expect(screen.getByTestId('tax-free-limit')).toHaveTextContent('84 %')
    expect(screen.getByTestId('tax-free-limit')).toHaveTextContent('nahe an der Grenze')
    expect(screen.getByText('Spielmannszug')).toBeInTheDocument()
    expect(screen.getByText(/Vorjahr 20\.000,00/)).toBeInTheDocument()
    expect(screen.getByText(/2024 bis 2026 sind noch nicht/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Excel' })).toHaveAttribute(
      'href',
      expect.stringContaining('/finance/tax/?jahr=2026&als=xlsx'),
    )
  })

  it('erklärt, wie man die Auswertung einschaltet', async () => {
    const org = testOrg({
      modules: ['members', 'finance'],
      permissions: ['finance.view'],
      parent_name: null,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/settings/`]: () => ({
        status: 200,
        body: { ...settings, tax_areas_enabled: false },
      }),
      [`GET ${F}/tax/?jahr=2026`]: () => ({ status: 200, body: { ...report, enabled: false } }),
    })
    renderApp('/finanzen/abschluss/steuern')
    expect(await screen.findByRole('link', { name: 'Zu den Kategorien' })).toBeInTheDocument()
  })
})
