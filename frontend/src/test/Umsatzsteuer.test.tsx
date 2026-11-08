import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'
const YEAR = new Date().getFullYear()
const QUARTER = Math.ceil((new Date().getMonth() + 1) / 3)

const settings = {
  current_year: YEAR,
  years: [{ year: YEAR, label: String(YEAR) }],
  tax_areas: [],
  tax_areas_enabled: true,
  vat_registered: true,
  vat_period: 'quarter',
  vat_flat_rate: false,
  can_edit: true,
}

const report = {
  year: YEAR,
  period: 'quarter',
  index: QUARTER,
  label: `${QUARTER}. Quartal ${YEAR}`,
  start: `${YEAR}-01-01`,
  end: `${YEAR}-03-31`,
  periods: [1, 2, 3, 4].map((i) => ({ index: i, label: `${i}. Quartal ${YEAR}` })),
  registered: true,
  flat_rate: false,
  flat_rate_used: false,
  flat_rate_allowed: true,
  previous_taxable: '1200.00',
  actual_input_tax: '28.50',
  flat_input_tax: '14.00',
  lines: [
    {
      code: '81',
      label: 'Steuerpflichtige Umsätze zu 19 %',
      base: '100.40',
      base_euros: 100,
      tax: '19.08',
    },
    {
      code: '86',
      label: 'Steuerpflichtige Umsätze zu 7 %',
      base: '100.00',
      base_euros: 100,
      tax: '7.00',
    },
    {
      code: '48',
      label: 'Steuerfreie Umsätze ohne Vorsteuerabzug',
      base: '0.00',
      base_euros: 0,
      tax: null,
    },
    {
      code: '66',
      label: 'Vorsteuerbeträge aus Rechnungen',
      base: null,
      base_euros: null,
      tax: '28.50',
    },
    {
      code: '83',
      label: 'Verbleibende Umsatzsteuer-Vorauszahlung bzw. Überschuss (−)',
      base: null,
      base_euros: null,
      tax: '-2.42',
    },
  ],
  units: [],
  counted_at: '',
  warnings: [],
}

describe('Umsatzsteuer', () => {
  it('zeigt die Kennzahlen der Voranmeldung und speichert die Pauschale', async () => {
    const org = testOrg({
      modules: ['members', 'finance', 'tax'],
      permissions: ['finance.view', 'finance.edit'],
      parent_name: null,
    })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/settings/`]: () => ({ status: 200, body: settings }),
      [`PATCH ${F}/settings/`]: () => ({ status: 200, body: { ...settings, vat_flat_rate: true } }),
      [`GET ${F}/vat/?jahr=${YEAR}&art=quarter&zeitraum=${QUARTER}`]: () => ({
        status: 200,
        body: report,
      }),
    })
    render(
      <MemoryRouter initialEntries={['/finanzen/abschluss/umsatzsteuer']}>
        <AuthProvider>
          <OrgProvider>
            <App />
          </OrgProvider>
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(await screen.findByText('Steuerpflichtige Umsätze zu 19 %')).toBeInTheDocument()
    expect(screen.getAllByText('einzutragen: 100 €')).toHaveLength(2)
    expect(screen.getByText('Vorsteuerbeträge aus Rechnungen')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Vorsteuer pauschal nach § 23a UStG/ }))
    await waitFor(() =>
      expect(
        calls.some(
          (c) => c.key === `PATCH ${F}/settings/` && String(c.init?.body).includes('vat_flat_rate'),
        ),
      ).toBe(true),
    )
  })
})
