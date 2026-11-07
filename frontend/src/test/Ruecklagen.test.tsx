// Finanzamt-Prüfung C4: Rücklagen nach § 62 AO (erfundene Daten)
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../App.tsx'
import { AuthProvider } from '../auth/AuthContext.tsx'
import { OrgProvider } from '../org/OrgContext.tsx'
import { fakeApi, testOrg, testUser } from './fakeApi.ts'

const SESSION = 'GET /_allauth/browser/v1/auth/session'
const loggedIn = () => ({ status: 200, body: { status: 200, data: { user: testUser } } })
const F = '/api/orgs/7/finance'
const kassierer = testOrg({
  modules: ['members', 'finance', 'tax'],
  permissions: ['finance.view', 'finance.edit'],
  reserves_enabled: true,
})

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

describe('Rücklagen', () => {
  it('legt eine Rücklage an und führt ihr Geld zu', async () => {
    let balance = '0.00'
    let created = false
    const reserve = () => ({
      id: 4,
      name: 'Schützenfest 2027',
      kind: 'purpose',
      kind_label: 'Projektrücklage (§ 62 Abs. 1 Nr. 1 AO)',
      purpose: 'Festzelt',
      is_active: true,
      balance,
      movements:
        balance === '0.00'
          ? []
          : [
              {
                id: 9,
                direction: 'add',
                direction_label: 'Zuführung',
                date: '2026-10-01',
                year: 2026,
                year_label: '2026',
                amount: '1500.00',
                note: 'Beschluss Vorstand',
                created_by_name: 'Karla Kasse',
                created_at: '2026-10-01T10:00:00Z',
                open: true,
              },
            ],
    })
    const calls = fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [kassierer] }),
      [`GET ${F}/reserves/`]: () => ({
        status: 200,
        body: {
          reserves: created ? [reserve()] : [],
          total: balance,
          funds: '5000.00',
          free: (5000 - Number(balance)).toFixed(2),
        },
      }),
      [`POST ${F}/reserves/`]: () => {
        created = true
        return { status: 201, body: reserve() }
      },
      [`POST ${F}/reserves/4/movements/`]: () => {
        balance = '1500.00'
        return { status: 201, body: reserve().movements[0] ?? {} }
      },
    })
    renderApp('/finanzen/ruecklagen')
    const user = userEvent.setup()
    expect(await screen.findByText('Noch keine Rücklagen.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Neue Rücklage' }))
    await user.type(screen.getByLabelText('Bezeichnung'), 'Schützenfest 2027')
    await user.type(screen.getByLabelText('Zweck bzw. Vorhaben'), 'Festzelt')
    await user.click(screen.getByRole('button', { name: 'Anlegen' }))
    expect(await screen.findByText('Rücklage „Schützenfest 2027“ angelegt.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Zuführen' }))
    await user.type(screen.getByLabelText('Zuführung in €'), '1.500,00')
    await user.type(screen.getByLabelText('Begründung'), 'Beschluss Vorstand')
    const form = screen.getByLabelText('Zuführung in €').closest('form')!
    await user.click(within(form).getByRole('button', { name: 'Zuführen' }))
    expect(await screen.findByText(/Zuführung von 1\.500,00\s€ für/)).toBeInTheDocument()
    expect(screen.getByText(/erfasst von Karla Kasse/)).toBeInTheDocument()
    const post = calls.find((c) => c.key === `POST ${F}/reserves/4/movements/`)!
    expect(JSON.parse(String(post.init?.body))).toMatchObject({
      direction: 'add',
      amount: '1500.00',
      note: 'Beschluss Vorstand',
    })
    const create = calls.find((c) => c.key === `POST ${F}/reserves/`)!
    expect(JSON.parse(String(create.init?.body))).toEqual({
      name: 'Schützenfest 2027',
      kind: 'purpose',
      purpose: 'Festzelt',
    })
  })

  it('zeigt den Höchstbetrag der freien Rücklage und warnt bei Überschreitung', async () => {
    fakeApi({
      [SESSION]: loggedIn,
      'GET /api/me/organizations/': () => ({ status: 200, body: [kassierer] }),
      [`GET ${F}/reserves/`]: () => ({
        status: 200,
        body: { reserves: [], total: '0.00', funds: '5000.00', free: '5000.00' },
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
      [`GET ${F}/reserves/limits/?jahr=2025`]: () => ({
        status: 200,
        body: {
          year: 2025,
          label: '2025',
          free: {
            assets_surplus: '600.00',
            ideal_income: '4000.00',
            purpose_surplus: '0.00',
            business_surplus: '1000.00',
            other_funds: '5000.00',
            limit: '700.00',
            income: '7600.00',
            carry: '400.00',
            available: '1100.00',
            added: '1150.00',
            over: '50.00',
          },
          replacement: { depreciation: '1200.00', added: '0.00' },
          use_of_funds: false,
          use_of_funds_from: '100000.00',
        },
      }),
    })
    renderApp('/finanzen/ruecklagen')
    const card = await screen.findByTestId('reserve-limits')
    expect(within(card).getByText('zulässig in 2025')).toBeInTheDocument()
    expect(within(card).getByText(/1\.100,00/)).toBeInTheDocument()
    expect(within(card).getByText(/liegen 50,00 .* über dem Höchstbetrag/)).toBeInTheDocument()
    expect(
      within(card).getByText(/Abschreibung laut Anlagenverzeichnis beträgt 1\.200,00/),
    ).toBeInTheDocument()
  })
})
