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

const report = {
  year: 2025,
  label: '2025',
  start_date: '2025-01-01',
  end_date: '2025-12-31',
  accounts: [{ id: 1, name: 'Girokonto', kind: 'bank', balance: '5000.00' }],
  cash: '5000.00',
  receivables: { total: '120.00', count: 1 },
  fixed_assets: { total: '11100.00', count: 1 },
  liabilities: {
    total: '450.00',
    count: 1,
    items: [
      {
        seller: 'Zeltverleih Muster',
        number: 'ZV-77',
        date: '2025-12-20',
        due_date: '2026-01-19',
        amount: '450.00',
      },
    ],
  },
  assets_total: '16220.00',
  net: '15770.00',
  reserves: { total: '2000.00', items: [{ name: 'Neues Dach', balance: '2000.00' }] },
  free: '13770.00',
}

describe('Vermögensübersicht', () => {
  it('zeigt Vermögen, Verbindlichkeiten und Rücklagen zum Jahresende', async () => {
    const org = testOrg({
      modules: ['members', 'finance', 'tax'],
      permissions: ['finance.view'],
      parent_name: null,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/settings/`]: () => ({
        status: 200,
        body: {
          current_year: 2025,
          years: [{ year: 2025, label: '2025' }],
          tax_areas: [],
          tax_areas_enabled: false,
        },
      }),
      [`GET ${F}/net-assets/?jahr=2025`]: () => ({ status: 200, body: report }),
    })
    render(
      <MemoryRouter initialEntries={['/finanzen/abschluss/vermoegen']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByTestId('net-assets')).toBeInTheDocument()
    expect(screen.getByText('Zeltverleih Muster')).toBeInTheDocument()
    expect(screen.getByText(/15\.770,00/)).toBeInTheDocument()
    expect(screen.getByText(/13\.770,00/)).toBeInTheDocument()
    expect(screen.getByText('davon in Rücklagen gebunden')).toBeInTheDocument()
  })
})
