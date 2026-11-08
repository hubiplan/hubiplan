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
const YEAR = new Date().getFullYear()

const report = {
  year: YEAR,
  limits: { trainer: '3300.00', volunteer: '960.00' },
  board_pay_allowed: false,
  units: ['Spielmannszug'],
  counted_at: '',
  people: [
    {
      key: 'm5',
      name: 'Erika Musterfrau',
      membership: 5,
      board: true,
      board_warning: true,
      kinds: [
        {
          kind: 'volunteer',
          label: 'Ehrenamtspauschale (§ 3 Nr. 26a EStG)',
          total: '900.00',
          limit: '960.00',
          percent: 93,
          status: 'warn',
        },
      ],
      bookings: [
        {
          id: 3,
          source: 'waiver',
          display_number: 'Verzicht (Aufwandsspende)',
          date: `${YEAR}-03-01`,
          amount: '900.00',
          allowance: 'volunteer',
          text: '',
          unit: 'Spielmannszug',
        },
      ],
    },
  ],
  warnings: [{ kind: 'board', text: 'Vorstandsmitglieder erhalten eine Vergütung.' }],
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

describe('Aufwandsvergütungen', () => {
  it('zeigt Summe je Person, Vorstandswarnung und die Erklärung als PDF', async () => {
    const org = testOrg({
      modules: ['members', 'finance', 'tax'],
      permissions: ['finance.view'],
      parent_name: null,
    })
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [org] }),
      [`GET ${F}/allowances/?jahr=${YEAR}`]: () => ({ status: 200, body: report }),
    })
    renderApp('/finanzen/abschluss/pauschalen')
    expect(await screen.findByText('Erika Musterfrau')).toBeInTheDocument()
    expect(screen.getByText(/93 %, nahe am Freibetrag/)).toBeInTheDocument()
    expect(screen.getByTestId('allowance-units')).toHaveTextContent('Spielmannszug')
    expect(screen.getByText('1 Zahlungen')).toBeInTheDocument()
    expect(screen.getByText(/Verzicht \(Aufwandsspende\) · 900,00/)).toBeInTheDocument()
    expect(screen.getByText('Vorstandsmitglieder erhalten eine Vergütung.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PDF' })).toHaveAttribute(
      'href',
      expect.stringContaining(`/finance/allowances/?jahr=${YEAR}&als=pdf&person=m5`),
    )
    // Ohne Bearbeitungsrecht lässt sich der Satzungsschalter nicht ändern
    expect(
      screen.getByRole('checkbox', { name: /Satzung erlaubt eine Vergütung des Vorstands/ }),
    ).toBeDisabled()
  })
})
