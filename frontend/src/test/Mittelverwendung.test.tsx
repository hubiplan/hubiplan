// Mittelverwendungsrechnung (Konzept vereinskasse-steuern, S5); erfundene Daten
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'

const year = (y: number, extra: Record<string, string> = {}) => ({
  year: y,
  label: String(y),
  carry_in: '0.00',
  inflow: '0.00',
  used: '0.00',
  reserve_add: '0.00',
  reserve_release: '0.00',
  uncovered: '0.00',
  carry_out: '0.00',
  ...extra,
})

describe('Mittelverwendung', () => {
  it('zeigt Vortrag, Verwendung und Fristen', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({
        status: 200,
        body: [testOrg({ modules: ['members', 'finance', 'tax'], permissions: ['finance.view'] })],
      }),
      [`GET ${F}/settings/`]: () => ({
        status: 200,
        body: {
          current_year: 2025,
          years: [{ year: 2025, label: '2025' }],
          tax_areas: [],
          tax_areas_enabled: true,
        },
      }),
      [`GET ${F}/use-of-funds/?jahr=2025`]: () => ({
        status: 200,
        body: {
          year: 2025,
          label: '2025',
          current: year(2025, { carry_in: '7000.00', carry_out: '7000.00' }),
          years: [
            year(2023, {
              carry_in: '6000.00',
              inflow: '6000.00',
              used: '3000.00',
              carry_out: '7000.00',
            }),
            year(2024, { carry_in: '7000.00', carry_out: '7000.00' }),
            year(2025, { carry_in: '7000.00', carry_out: '7000.00' }),
          ],
          by_origin: [
            {
              year: 2022,
              label: '2022',
              amount: '1000.00',
              deadline: '2024',
              overdue: true,
              due_now: false,
            },
            {
              year: 2023,
              label: '2023',
              amount: '6000.00',
              deadline: '2025',
              overdue: false,
              due_now: true,
            },
          ],
          overdue: '1000.00',
          due_now: '6000.00',
        },
      }),
    })
    render(
      <MemoryRouter initialEntries={['/finanzen/abschluss/mittelverwendung']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    const table = await screen.findByTestId('use-of-funds')
    expect(within(table).getByText('für die Satzungszwecke verwendet')).toBeInTheDocument()
    expect(screen.getByText(/nicht fristgerecht verwendet/)).toBeInTheDocument()
    expect(screen.getByText(/müssen bis zum Ende von 2025 verwendet werden/)).toBeInTheDocument()
    expect(screen.getByText('Frist abgelaufen')).toBeInTheDocument()
  })
})
